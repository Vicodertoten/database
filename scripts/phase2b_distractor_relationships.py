#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from jsonschema import FormatChecker, validate

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from database_core.domain.models import DistractorRelationship  # noqa: E402
from database_core.storage.services import build_storage_services  # noqa: E402

DEFAULT_ARTIFACT_PATH = Path(
    "docs/audits/evidence/distractor_relationships_v1_projected_sprint13.json"
)
DEFAULT_SCHEMA_PATH = Path("schemas/distractor_relationship_v1.schema.json")
DEFAULT_OUTPUT_JSON = Path(
    "docs/audits/evidence/phase2b/distractor_relationships_palier_a_audit.json"
)
DEFAULT_OUTPUT_MD = Path("docs/audits/phase2b-distractor-relationships-palier-a.md")
PALIER_A_AUDIT_VERSION = "phase2b.distractor_relationships_palier_a.v1"
VALIDATED_STATUS = "validated"
MIN_DISTRACTORS_PER_TARGET = 3


def load_projected_records(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("projected_records", [])
    if not isinstance(records, list):
        raise ValueError("Projected distractor artifact must contain projected_records list")
    return [record for record in records if isinstance(record, dict)]


def fetch_canonical_taxon_ids(database_url: str) -> set[str]:
    services = build_storage_services(database_url)
    with services.database.connect() as connection:
        rows = connection.execute(
            "SELECT canonical_taxon_id FROM canonical_taxa ORDER BY canonical_taxon_id"
        ).fetchall()
    return {str(row["canonical_taxon_id"]) for row in rows}


def fetch_pool_taxon_ids(database_url: str, *, pool_id: str) -> list[str]:
    services = build_storage_services(database_url)
    pool = services.dynamic_pack_store.fetch_pack_pool(pool_id=pool_id)
    if pool is None:
        raise ValueError(f"Unknown pool_id: {pool_id}")
    items = pool.get("items", [])
    if not isinstance(items, list):
        raise ValueError("pack_pool items must be a list")
    return sorted(
        {
            str(item["canonical_taxon_id"])
            for item in items
            if isinstance(item, dict) and item.get("canonical_taxon_id")
        }
    )


def build_palier_a_relationships(
    *,
    records: list[dict[str, Any]],
    canonical_taxon_ids: set[str],
    schema_path: Path = DEFAULT_SCHEMA_PATH,
) -> tuple[list[DistractorRelationship], dict[str, Any]]:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    relationships: list[DistractorRelationship] = []
    skipped: Counter[str] = Counter()
    invalid: list[dict[str, str]] = []
    non_canonical_records = 0

    for record in records:
        ref_type = str(record.get("candidate_taxon_ref_type") or "")
        if ref_type != "canonical_taxon":
            non_canonical_records += 1
            skipped[f"skipped_{ref_type or 'missing_ref_type'}"] += 1
            continue

        target_id = str(record.get("target_canonical_taxon_id") or "")
        candidate_id = str(record.get("candidate_taxon_ref_id") or "")
        source = str(record.get("source") or "")
        confusion_types = record.get("confusion_types") or []
        if target_id not in canonical_taxon_ids:
            skipped["missing_target_canonical_taxon"] += 1
            continue
        if candidate_id not in canonical_taxon_ids:
            skipped["missing_candidate_canonical_taxon"] += 1
            continue
        if target_id == candidate_id:
            skipped["self_candidate_taxon"] += 1
            continue
        if not isinstance(confusion_types, list) or not confusion_types:
            skipped["missing_confusion_types"] += 1
            continue
        if source == "emergency_diversity_fallback":
            skipped["emergency_diversity_fallback"] += 1
            continue

        payload = {**record, "status": VALIDATED_STATUS}
        try:
            validate(instance=payload, schema=schema, format_checker=FormatChecker())
            relationships.append(DistractorRelationship(**payload))
        except Exception as exc:  # noqa: BLE001 - report all validation failures.
            invalid.append(
                {
                    "relationship_id": str(record.get("relationship_id") or ""),
                    "reason": str(exc),
                }
            )

    summary = {
        "input_records": len(records),
        "non_canonical_records": non_canonical_records,
        "relationships_ready": len(relationships),
        "skipped_counts": dict(sorted(skipped.items())),
        "invalid_count": len(invalid),
        "invalid_records": invalid[:50],
        "source_counts": dict(
            sorted(Counter(str(relationship.source) for relationship in relationships).items())
        ),
    }
    return relationships, summary


def audit_artifact(
    *,
    database_url: str,
    artifact_path: Path,
    output_json: Path,
    output_md: Path,
) -> dict[str, Any]:
    records = load_projected_records(artifact_path)
    canonical_taxon_ids = fetch_canonical_taxon_ids(database_url)
    relationships, summary = build_palier_a_relationships(
        records=records,
        canonical_taxon_ids=canonical_taxon_ids,
    )
    blockers: list[str] = []
    warnings: list[str] = []
    if not relationships:
        blockers.append("no_importable_canonical_relationships")
    if summary["invalid_count"]:
        blockers.append("invalid_importable_relationships")
    if summary["non_canonical_records"]:
        warnings.append("referenced_or_unresolved_records_skipped_for_palier_a")

    report = _base_report(
        report_type="artifact_audit",
        status="NO_GO" if blockers else ("GO_WITH_WARNINGS" if warnings else "GO"),
        blockers=blockers,
        warnings=warnings,
        artifact_path=artifact_path,
        details=summary,
    )
    _write_reports(report, output_json=output_json, output_md=output_md)
    return report


def import_canonical(
    *,
    database_url: str,
    artifact_path: Path,
    output_json: Path,
    output_md: Path,
) -> dict[str, Any]:
    services = build_storage_services(database_url)
    records = load_projected_records(artifact_path)
    canonical_taxon_ids = fetch_canonical_taxon_ids(database_url)
    relationships, summary = build_palier_a_relationships(
        records=records,
        canonical_taxon_ids=canonical_taxon_ids,
    )
    blockers: list[str] = []
    warnings: list[str] = []
    if not relationships:
        blockers.append("no_importable_canonical_relationships")
    if summary["invalid_count"]:
        blockers.append("invalid_importable_relationships")
    if summary["non_canonical_records"]:
        warnings.append("referenced_or_unresolved_records_skipped_for_palier_a")

    if not blockers:
        services.distractor_relationship_store.save_distractor_relationships(relationships)

    report = _base_report(
        report_type="canonical_import",
        status="NO_GO" if blockers else ("GO_WITH_WARNINGS" if warnings else "GO"),
        blockers=blockers,
        warnings=warnings,
        artifact_path=artifact_path,
        details={
            **summary,
            "storage_mutated": not blockers,
            "relationships_persisted": len(relationships) if not blockers else 0,
        },
    )
    _write_reports(report, output_json=output_json, output_md=output_md)
    return report


def audit_db(
    *,
    database_url: str,
    pool_id: str,
    output_json: Path,
    output_md: Path,
) -> dict[str, Any]:
    services = build_storage_services(database_url)
    target_taxon_ids = fetch_pool_taxon_ids(database_url, pool_id=pool_id)
    coverage = services.distractor_relationship_store.audit_distractor_relationship_coverage(
        target_canonical_taxon_ids=target_taxon_ids,
        min_distractors_per_target=MIN_DISTRACTORS_PER_TARGET,
    )
    report = _base_report(
        report_type="db_audit",
        status=str(coverage["status"]),
        blockers=list(coverage["blockers"]),
        warnings=list(coverage["warnings"]),
        artifact_path=None,
        details={
            "pool_id": pool_id,
            "target_taxon_count": len(target_taxon_ids),
            **coverage,
        },
    )
    _write_reports(report, output_json=output_json, output_md=output_md)
    return report


def _base_report(
    *,
    report_type: str,
    status: str,
    blockers: list[str],
    warnings: list[str],
    artifact_path: Path | None,
    details: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": PALIER_A_AUDIT_VERSION,
        "report_type": report_type,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "artifact_path": str(artifact_path) if artifact_path is not None else None,
        "palier_a_policy": {
            "import_scope": "canonical_taxon_only",
            "persisted_status": VALIDATED_STATUS,
            "referenced_taxa_storage": "audit_only",
            "referenced_only_runtime_usage": False,
        },
        "details": details,
    }


def _write_reports(report: dict[str, Any], *, output_json: Path, output_md: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown_report(report), encoding="utf-8")


def _markdown_report(report: dict[str, Any]) -> str:
    details = report["details"]
    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        f"last_reviewed: {str(report['generated_at'])[:10]}",
        "source_of_truth: docs/audits/phase2b-distractor-relationships-palier-a.md",
        "scope: phase2b_distractor_relationships_palier_a",
        "---",
        "",
        "# Phase 2B Distractor Relationships Palier A",
        "",
        f"- report_type: `{report['report_type']}`",
        f"- status: `{report['status']}`",
        f"- blockers: `{len(report['blockers'])}`",
        f"- warnings: `{len(report['warnings'])}`",
    ]
    if "relationship_count" in details:
        lines.extend(
            [
                f"- relationship_count: `{details['relationship_count']}`",
                f"- source_counts: `{details['source_counts']}`",
                f"- status_counts: `{details['status_counts']}`",
                (
                    "- candidate_taxon_ref_type_counts: "
                    f"`{details['candidate_taxon_ref_type_counts']}`"
                ),
                f"- targets_below_min: `{len(details['targets_below_min'])}`",
            ]
        )
    else:
        lines.extend(
            [
                f"- input_records: `{details['input_records']}`",
                f"- relationships_ready: `{details['relationships_ready']}`",
                f"- non_canonical_records: `{details['non_canonical_records']}`",
                f"- source_counts: `{details['source_counts']}`",
                f"- skipped_counts: `{details['skipped_counts']}`",
            ]
        )
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- `{item}`" for item in report["blockers"] or ["none"])
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- `{item}`" for item in report["warnings"] or ["none"])
    return "\n".join(lines).rstrip() + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Phase 2B Palier A distractor relationship tooling."
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("PHASE1_DATABASE_URL", ""),
        help="Database URL for the corrected Phase 1/2B clone.",
    )
    parser.add_argument("--artifact-path", type=Path, default=DEFAULT_ARTIFACT_PATH)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("audit-artifact")
    subparsers.add_parser("import-canonical")
    audit_db_parser = subparsers.add_parser("audit-db")
    audit_db_parser.add_argument("--pool-id", required=True)
    return parser


def main() -> None:
    load_dotenv(dotenv_path=Path(".env"))
    parser = _build_parser()
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("PHASE1_DATABASE_URL or --database-url is required")

    if args.command == "audit-artifact":
        report = audit_artifact(
            database_url=args.database_url,
            artifact_path=args.artifact_path,
            output_json=args.output_json,
            output_md=args.output_md,
        )
    elif args.command == "import-canonical":
        report = import_canonical(
            database_url=args.database_url,
            artifact_path=args.artifact_path,
            output_json=args.output_json,
            output_md=args.output_md,
        )
    elif args.command == "audit-db":
        report = audit_db(
            database_url=args.database_url,
            pool_id=args.pool_id,
            output_json=args.output_json,
            output_md=args.output_md,
        )
    else:
        raise SystemExit(f"Unsupported command: {args.command}")

    print(
        "Phase 2B distractor relationships"
        f" | command={args.command}"
        f" | status={report['status']}"
        f" | output_json={args.output_json}"
        f" | output_md={args.output_md}"
    )


if __name__ == "__main__":
    main()
