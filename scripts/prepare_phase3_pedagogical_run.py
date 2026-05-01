from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


def _bootstrap_src_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    src_path = str(src)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def _parse_json_list(raw_value: object) -> list[dict[str, Any]]:
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
        except json.JSONDecodeError:
            return []
    elif isinstance(raw_value, list):
        parsed = raw_value
    else:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _has_inat_mapping(mappings_json: object) -> bool:
    mappings = _parse_json_list(mappings_json)
    for mapping in mappings:
        if str(mapping.get("source_name") or "") == "inaturalist":
            return True
    return False


def _has_inat_hints(hints_json: object) -> bool:
    hints = _parse_json_list(hints_json)
    return any(str(hint.get("source_name") or "") == "inaturalist" for hint in hints)


def _load_audit_module(repo_root: Path):
    audit_script = repo_root / "scripts" / "audit_phase3_distractors.py"
    spec = importlib.util.spec_from_file_location("phase3_audit_module", audit_script)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load audit_phase3_distractors.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _collect_taxon_snapshot(connection: psycopg.Connection) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            canonical_taxon_id,
            external_source_mappings_json,
            external_similarity_hints_json
        FROM canonical_taxa
        ORDER BY canonical_taxon_id
        """
    ).fetchall()
    return {str(row["canonical_taxon_id"]): dict(row) for row in rows}


def _collect_playable_counts(connection: psycopg.Connection) -> dict[str, int]:
    rows = connection.execute(
        """
        SELECT canonical_taxon_id, COUNT(*) AS item_count
        FROM playable_items
        GROUP BY canonical_taxon_id
        ORDER BY canonical_taxon_id
        """
    ).fetchall()
    return {str(row["canonical_taxon_id"]): int(row["item_count"]) for row in rows}


def _build_precheck(
    *,
    playable_counts: dict[str, int],
    taxon_snapshot: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    taxa_ge2 = [taxon_id for taxon_id, count in playable_counts.items() if count >= 2]

    taxa_with_inat_mapping = [
        taxon_id
        for taxon_id, row in taxon_snapshot.items()
        if _has_inat_mapping(row.get("external_source_mappings_json"))
    ]
    taxa_with_inat_hints = [
        taxon_id
        for taxon_id, row in taxon_snapshot.items()
        if _has_inat_hints(row.get("external_similarity_hints_json"))
    ]
    taxa_ge2_with_hints = [
        taxon_id
        for taxon_id in taxa_ge2
        if taxon_id in taxon_snapshot
        and _has_inat_hints(taxon_snapshot[taxon_id].get("external_similarity_hints_json"))
    ]

    top_counts = sorted(
        ((taxon_id, playable_counts[taxon_id]) for taxon_id in taxa_ge2),
        key=lambda item: (-item[1], item[0]),
    )
    top_10_total = sum(count for _, count in top_counts[:10])
    total_ge2_items = sum(count for _, count in top_counts)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "totals": {
            "taxa_in_canonical": len(taxon_snapshot),
            "taxa_with_playable_items": len(playable_counts),
            "taxa_with_playable_ge2": len(taxa_ge2),
            "taxa_with_inat_mapping": len(taxa_with_inat_mapping),
            "taxa_with_inat_hints": len(taxa_with_inat_hints),
            "taxa_with_playable_ge2_and_inat_hints": len(taxa_ge2_with_hints),
        },
        "concentration": {
            "top_10_taxa_share_percent": round(
                (top_10_total / total_ge2_items) * 100, 2
            )
            if total_ge2_items
            else 0.0,
            "top_10_taxa": [
                {"canonical_taxon_id": taxon_id, "playable_count": count}
                for taxon_id, count in top_counts[:10]
            ],
        },
        "coverage_assessment": {
            "inat_branch_currently_actionable": len(taxa_ge2_with_hints) > 0,
            "needs_calibration_injection": len(taxa_ge2_with_hints) == 0,
        },
    }


def _pick_calibration_taxa(
    *,
    playable_counts: dict[str, int],
    pack_taxa_count: int,
    out_of_pack_count: int = 3,
) -> tuple[list[str], list[str], list[str]]:
    candidates = [taxon_id for taxon_id, count in playable_counts.items() if count >= 2]
    candidates.sort(key=lambda taxon_id: (-playable_counts[taxon_id], taxon_id))

    minimum_required = pack_taxa_count + out_of_pack_count
    if len(candidates) < minimum_required:
        raise RuntimeError(
            "Need at least "
            f"{minimum_required} taxa with >=2 playable items for calibrated run. "
            f"Found {len(candidates)}."
        )

    pack_taxa = candidates[:pack_taxa_count]
    target_taxa = pack_taxa[: min(5, len(pack_taxa))]
    out_of_pack_taxa = candidates[pack_taxa_count : pack_taxa_count + out_of_pack_count]
    return pack_taxa, target_taxa, out_of_pack_taxa


def _backup_taxa_fields(
    connection: psycopg.Connection,
    *,
    canonical_taxon_ids: list[str],
) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            canonical_taxon_id,
            external_source_mappings_json,
            external_similarity_hints_json
        FROM canonical_taxa
        WHERE canonical_taxon_id = ANY(%s)
        """,
        (canonical_taxon_ids,),
    ).fetchall()
    return {
        str(row["canonical_taxon_id"]): {
            "external_source_mappings_json": row["external_source_mappings_json"],
            "external_similarity_hints_json": row["external_similarity_hints_json"],
        }
        for row in rows
    }


def _apply_calibration_hints(
    connection: psycopg.Connection,
    *,
    pack_taxa: list[str],
    out_of_pack_taxa: list[str],
) -> None:
    touched_taxa = sorted(set(pack_taxa + out_of_pack_taxa))
    for taxon_id in touched_taxa:
        connection.execute(
            """
            UPDATE canonical_taxa
            SET external_source_mappings_json = %s
            WHERE canonical_taxon_id = %s
            """,
            (
                json.dumps([
                    {"source_name": "inaturalist", "external_id": f"inat-{taxon_id}"}
                ]),
                taxon_id,
            ),
        )

    for index, target_taxon in enumerate(pack_taxa):
        mapped_taxon = out_of_pack_taxa[index % len(out_of_pack_taxa)]
        hints = [
            {
                "source_name": "inaturalist",
                "external_taxon_id": f"inat-{mapped_taxon}",
                "relation_type": "visual_lookalike",
                "common_name": f"Mapped lookalike {index + 1}",
                "confidence": 0.95,
            },
            {
                "source_name": "inaturalist",
                "external_taxon_id": f"inat-unknown-hi-{target_taxon}",
                "relation_type": "visual_lookalike",
                "accepted_scientific_name": f"Unknownus calibratus {index + 1}",
                "common_name": f"Unknown lookalike {index + 1}",
                "confidence": 0.92,
            },
            {
                "source_name": "inaturalist",
                "external_taxon_id": f"inat-unknown-low-{target_taxon}",
                "relation_type": "visual_lookalike",
                "accepted_scientific_name": f"Unknownus lowconf {index + 1}",
                "common_name": f"Low confidence lookalike {index + 1}",
                "confidence": 0.20,
            },
        ]
        connection.execute(
            """
            UPDATE canonical_taxa
            SET external_similarity_hints_json = %s
            WHERE canonical_taxon_id = %s
            """,
            (json.dumps(hints), target_taxon),
        )


def _restore_taxa_fields(
    connection: psycopg.Connection,
    *,
    backups: dict[str, dict[str, Any]],
) -> None:
    for taxon_id, backup in backups.items():
        connection.execute(
            """
            UPDATE canonical_taxa
            SET external_source_mappings_json = %s,
                external_similarity_hints_json = %s
            WHERE canonical_taxon_id = %s
            """,
            (
                backup.get("external_source_mappings_json"),
                backup.get("external_similarity_hints_json"),
                taxon_id,
            ),
        )


def _generate_calibrated_artifacts(
    *,
    database_url: str,
    pack_taxa: list[str],
    output_dir: Path,
    question_count: int,
) -> dict[str, Any]:
    _bootstrap_src_path()
    from database_core.domain.models import PackRevisionParameters
    from database_core.storage.services import build_storage_services

    services = build_storage_services(database_url)
    pack_store = services.pack_store

    pack_id = f"pack:phase3:pedagogical:{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    created = pack_store.create_pack(
        pack_id=pack_id,
        parameters=PackRevisionParameters(
            canonical_taxon_ids=pack_taxa,
            difficulty_policy="mixed",
            intended_use="phase3_pedagogical_calibrated",
        ),
    )

    compiled = pack_store.compile_pack_v2(
        pack_id=pack_id,
        revision=int(created["revision"]),
        question_count=question_count,
    )
    materialized = pack_store.materialize_pack_v2(
        pack_id=pack_id,
        revision=int(created["revision"]),
        question_count=question_count,
        purpose="assignment",
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    compiled_path = output_dir / "pack_compiled_v2_pedagogical_calibrated.json"
    materialized_path = output_dir / "pack_materialization_v2_pedagogical_calibrated.json"
    compiled_path.write_text(json.dumps(compiled, indent=2, ensure_ascii=True), encoding="utf-8")
    materialized_path.write_text(
        json.dumps(materialized, indent=2, ensure_ascii=True), encoding="utf-8"
    )

    return {
        "pack_id": pack_id,
        "revision": int(created["revision"]),
        "compiled_path": str(compiled_path),
        "materialized_path": str(materialized_path),
    }


def _audit_outputs(repo_root: Path, paths: list[str], output_json: Path) -> dict[str, Any]:
    audit_module = _load_audit_module(repo_root)
    reports: list[dict[str, Any]] = []
    errors: dict[str, str] = {}

    for path in paths:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            reports.append(audit_module.audit_payload(payload, source_name=path))
        except Exception as exc:  # pragma: no cover
            errors[path] = str(exc)

    aggregate = {"reports": reports, "errors": errors}
    output_json.write_text(json.dumps(aggregate, indent=2, ensure_ascii=True), encoding="utf-8")
    return aggregate


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a pedagogically relevant Phase 3 run in two steps: precheck and "
            "calibrated sample generation with forced iNat/out_of_pack/referenced_only coverage."
        )
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="Database URL (defaults to DATABASE_URL).",
    )
    parser.add_argument(
        "--question-count",
        type=int,
        default=30,
        help="Question count for calibrated compiled/materialized artifacts.",
    )
    parser.add_argument(
        "--pack-taxa-count",
        type=int,
        default=12,
        help="Number of taxa included in the calibrated pack generation.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/exports/phase3_pedagogical",
        help="Output directory for precheck, artifacts, and audit reports.",
    )
    args = parser.parse_args()

    if not args.database_url.strip():
        raise SystemExit("DATABASE_URL is required (argument or environment variable).")
    if args.pack_taxa_count < 10:
        raise SystemExit("--pack-taxa-count must be >= 10.")

    repo_root = Path(__file__).resolve().parents[1]
    output_dir = (repo_root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with psycopg.connect(args.database_url, row_factory=dict_row) as connection:
        playable_counts = _collect_playable_counts(connection)
        taxon_snapshot = _collect_taxon_snapshot(connection)
        precheck = _build_precheck(
            playable_counts=playable_counts,
            taxon_snapshot=taxon_snapshot,
        )

        pack_taxa, target_taxa, out_of_pack_taxa = _pick_calibration_taxa(
            playable_counts=playable_counts,
            pack_taxa_count=args.pack_taxa_count,
        )
        precheck["calibration_plan"] = {
            "pack_taxa": pack_taxa,
            "target_taxa": target_taxa,
            "out_of_pack_taxa": out_of_pack_taxa,
            "question_count": args.question_count,
        }

        precheck_path = output_dir / "phase3_pedagogical_precheck.json"
        precheck_path.write_text(
            json.dumps(precheck, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )

        touched_taxa = sorted(set(pack_taxa + out_of_pack_taxa + target_taxa))
        backups = _backup_taxa_fields(connection, canonical_taxon_ids=touched_taxa)

        generated: dict[str, Any]
        try:
            _apply_calibration_hints(
                connection,
                pack_taxa=pack_taxa,
                out_of_pack_taxa=out_of_pack_taxa,
            )
            # Pack generation uses a separate connection, so hints must be committed first.
            connection.commit()
            generated = _generate_calibrated_artifacts(
                database_url=args.database_url,
                pack_taxa=pack_taxa,
                output_dir=output_dir,
                question_count=args.question_count,
            )
        finally:
            _restore_taxa_fields(connection, backups=backups)
            connection.commit()

    audit_path = output_dir / "phase3_pedagogical_audit_report.json"
    audited = _audit_outputs(
        repo_root,
        [generated["materialized_path"], generated["compiled_path"]],
        audit_path,
    )

    summary = {
        "precheck_path": str(output_dir / "phase3_pedagogical_precheck.json"),
        "artifacts": generated,
        "audit_path": str(audit_path),
        "audit_errors": audited.get("errors", {}),
    }
    summary_path = output_dir / "phase3_pedagogical_run_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
