"""Audit localized taxon names coverage for canonical and referenced taxa.

Sprint 13B:
- Reports FR/EN/NL gaps.
- Supports optional patch preview through patch apply logic (dry-run simulation).
- Emits JSON and Markdown evidence for governance.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.apply_taxon_localized_name_patches_v1 import (
        apply_patches,
        load_json,
        load_referenced_records,
        validate_patch_records,
    )
except ModuleNotFoundError:
    from apply_taxon_localized_name_patches_v1 import (  # type: ignore[no-redef]
        apply_patches,
        load_json,
        load_referenced_records,
        validate_patch_records,
    )


DEFAULT_CANONICAL_PATH = Path(
    "data/normalized/palier1_be_birds_50taxa_run003_v11_baseline.normalized.json"
)
DEFAULT_REFERENCED_CANDIDATES_PATH = Path(
    "docs/audits/evidence/referenced_taxon_shell_candidates_sprint12.json"
)
DEFAULT_REFERENCED_SNAPSHOT_PATH = Path("data/review_overrides/referenced_taxa_snapshot.json")
DEFAULT_CANDIDATE_REL_PATH = Path(
    "docs/audits/evidence/distractor_relationship_candidates_v1_sprint12.json"
)
DEFAULT_PATCH_SCHEMA_PATH = Path("schemas/taxon_localized_name_patch_v1.schema.json")
DEFAULT_PATCH_FILE = Path("data/manual/taxon_localized_name_patches_v1.json")
DEFAULT_OUTPUT_JSON = Path("docs/audits/evidence/taxon_localized_names_sprint13_audit.json")
DEFAULT_OUTPUT_MD = Path("docs/audits/taxon-localized-names-sprint13-audit.md")

LANGS = ("fr", "en", "nl")


def _normalize_name_map(name_map: dict[str, Any]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for lang in LANGS:
        values = name_map.get(lang, [])
        if not isinstance(values, list):
            values = []
        cleaned = [str(val).strip() for val in values if str(val).strip()]
        if cleaned:
            out[lang] = cleaned
    return out


def _has_lang(record: dict[str, Any], lang: str) -> bool:
    values = (record.get("common_names_i18n") or {}).get(lang, [])
    return isinstance(values, list) and any(str(item).strip() for item in values)


def _extract_canonical_records(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    out: list[dict[str, Any]] = []
    for item in payload.get("canonical_taxa", []):
        out.append(
            {
                "canonical_taxon_id": item.get("canonical_taxon_id"),
                "scientific_name": item.get("accepted_scientific_name"),
                "source_taxon_id": None,
                "referenced_taxon_id": None,
                "common_names_i18n": _normalize_name_map(
                    item.get("common_names_by_language") or {}
                ),
            }
        )
    return out


def _build_candidate_taxon_usability(
    relationships: list[dict[str, Any]],
    canonical_by_id: dict[str, dict[str, Any]],
    referenced_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    unique_candidates: dict[str, dict[str, Any]] = {}

    for rel in relationships:
        ref_type = str(rel.get("candidate_taxon_ref_type", "")).strip()
        ref_id = rel.get("candidate_taxon_ref_id")
        sci = str(rel.get("candidate_scientific_name", "")).strip()
        key = f"{ref_type}:{ref_id or sci}"
        if key in unique_candidates:
            continue

        names: dict[str, list[str]] = {}
        if ref_type == "canonical_taxon" and ref_id in canonical_by_id:
            names = canonical_by_id[ref_id].get("common_names_i18n", {})
        elif ref_type == "referenced_taxon" and ref_id in referenced_by_id:
            names = referenced_by_id[ref_id].get("common_names_i18n", {})

        has_fr = bool(names.get("fr"))
        has_en = bool(names.get("en"))
        has_nl = bool(names.get("nl"))

        unique_candidates[key] = {
            "candidate_key": key,
            "candidate_taxon_ref_type": ref_type,
            "candidate_taxon_ref_id": ref_id,
            "candidate_scientific_name": sci,
            "can_be_used_now_fr": has_fr,
            "can_be_used_now_multilingual": has_fr and has_en and has_nl,
        }

    rows = list(unique_candidates.values())
    return {
        "candidate_taxa_count": len(rows),
        "candidate_taxa_missing_fr": sum(1 for row in rows if not row["can_be_used_now_fr"]),
        "can_be_used_now_fr_count": sum(1 for row in rows if row["can_be_used_now_fr"]),
        "can_be_used_now_multilingual_count": sum(
            1 for row in rows if row["can_be_used_now_multilingual"]
        ),
    }


def run_audit(
    canonical_path: Path,
    referenced_candidates_path: Path,
    referenced_snapshot_path: Path,
    candidate_relationship_path: Path,
    patch_schema_path: Path,
    patch_file: Path | None,
    output_json: Path,
    output_md: Path,
) -> dict[str, Any]:
    canonical_records = _extract_canonical_records(canonical_path)
    referenced_records = load_referenced_records(
        candidates_path=referenced_candidates_path,
        snapshot_path=referenced_snapshot_path,
    )
    for item in referenced_records:
        item["common_names_i18n"] = _normalize_name_map(item.get("common_names_i18n") or {})

    canonical_by_id = {
        row["canonical_taxon_id"]: row
        for row in canonical_records
        if row.get("canonical_taxon_id")
    }
    referenced_by_id = {
        row["referenced_taxon_id"]: row
        for row in referenced_records
        if row.get("referenced_taxon_id")
    }

    relationships_payload = load_json(candidate_relationship_path)
    relationships = relationships_payload.get("relationships", [])
    if not isinstance(relationships, list):
        relationships = []

    canonical_missing = {
        f"canonical_taxa_missing_{lang}": sum(
            1 for rec in canonical_records if not _has_lang(rec, lang)
        )
        for lang in LANGS
    }
    referenced_missing = {
        f"referenced_taxa_missing_{lang}": sum(
            1 for rec in referenced_records if not _has_lang(rec, lang)
        )
        for lang in LANGS
    }

    inat_available_existing = {
        "names_available_from_existing_common_names_i18n": {
            "canonical_with_any_localized_name": sum(
                1 for rec in canonical_records if any(_has_lang(rec, lang) for lang in LANGS)
            ),
            "referenced_with_any_localized_name": sum(
                1 for rec in referenced_records if any(_has_lang(rec, lang) for lang in LANGS)
            ),
        },
        "names_available_from_inaturalist_payloads": {
            "canonical_with_inat_mapping_assumed": sum(1 for rec in canonical_records),
            "referenced_with_shell_names": sum(
                1 for rec in referenced_records if any(_has_lang(rec, lang) for lang in LANGS)
            ),
        },
    }

    usability_before = _build_candidate_taxon_usability(
        relationships, canonical_by_id, referenced_by_id
    )

    manual_patch_count = 0
    conflicts: list[dict[str, Any]] = []
    unresolved_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    invalid_patches: list[dict[str, Any]] = []
    usability_after = dict(usability_before)

    if patch_file and patch_file.exists():
        patch_payload = load_json(patch_file)
        patch_rows = patch_payload.get("patches", patch_payload)
        if not isinstance(patch_rows, list):
            patch_rows = []
        schema = load_json(patch_schema_path)
        valid_patches, invalid_patches = validate_patch_records(patch_rows, schema)
        manual_patch_count = len(valid_patches)

        simulated = apply_patches(valid_patches, canonical_records, referenced_records)
        conflicts = simulated["conflicts"]
        unresolved_rows = simulated["unresolved"]
        skipped_rows = simulated["skipped"]

        patched_canonical_by_id = {
            row["canonical_taxon_id"]: row
            for row in simulated["canonical_taxa"]
            if row.get("canonical_taxon_id")
        }
        patched_referenced_by_id = {
            row["referenced_taxon_id"]: row
            for row in simulated["referenced_taxa"]
            if row.get("referenced_taxon_id")
        }
        usability_after = _build_candidate_taxon_usability(
            relationships, patched_canonical_by_id, patched_referenced_by_id
        )

    if invalid_patches:
        decision = "NEEDS_NAME_PATCH_FIXES"
    elif conflicts:
        decision = "NEEDS_CONFLICT_REVIEW"
    elif usability_after["candidate_taxa_missing_fr"] > 0:
        decision = "BLOCKED_BY_NAME_SOURCE_GAPS"
    else:
        decision = "LOCALIZED_NAMES_SYSTEM_READY"

    result = {
        "execution_status": "complete",
        "run_date": datetime.now(UTC).isoformat(),
        "decision": decision,
        "total_taxa_inspected": len(canonical_records) + len(referenced_records),
        "canonical_taxa_count": len(canonical_records),
        "referenced_taxa_count": len(referenced_records),
        **canonical_missing,
        **referenced_missing,
        "distractor_candidate_taxa_missing_fr": usability_before["candidate_taxa_missing_fr"],
        **inat_available_existing,
        "manual_patches_available": manual_patch_count,
        "conflicts": conflicts,
        "unresolved_rows": unresolved_rows,
        "skipped_rows": skipped_rows,
        "invalid_patches": invalid_patches,
        "before": {
            "can_be_used_now_fr": usability_before["can_be_used_now_fr_count"],
            "can_be_used_now_multilingual": usability_before[
                "can_be_used_now_multilingual_count"
            ],
        },
        "after": {
            "can_be_used_now_fr": usability_after["can_be_used_now_fr_count"],
            "can_be_used_now_multilingual": usability_after[
                "can_be_used_now_multilingual_count"
            ],
        },
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        f"last_reviewed: {result['run_date'][:10]}",
        "source_of_truth: docs/audits/taxon-localized-names-sprint13-audit.md",
        "scope: audit",
        "---",
        "",
        "# Taxon Localized Names Sprint 13 Audit",
        "",
        "## Purpose",
        "",
        (
            "Assess FR/EN/NL localized name readiness for canonical and referenced "
            "taxa, including distractor candidate usability impact."
        ),
        "",
        "## Summary",
        "",
        f"- decision: {decision}",
        f"- total_taxa_inspected: {result['total_taxa_inspected']}",
        f"- canonical_taxa_missing_fr: {result['canonical_taxa_missing_fr']}",
        f"- referenced_taxa_missing_fr: {result['referenced_taxa_missing_fr']}",
        f"- distractor_candidate_taxa_missing_fr: {result['distractor_candidate_taxa_missing_fr']}",
        "",
        "## Before/After Candidate Usability",
        "",
        f"- can_be_used_now_fr before: {result['before']['can_be_used_now_fr']}",
        f"- can_be_used_now_fr after: {result['after']['can_be_used_now_fr']}",
        (
            "- can_be_used_now_multilingual before: "
            f"{result['before']['can_be_used_now_multilingual']}"
        ),
        (
            "- can_be_used_now_multilingual after: "
            f"{result['after']['can_be_used_now_multilingual']}"
        ),
        "",
        "## Patch Processing",
        "",
        f"- manual_patches_available: {result['manual_patches_available']}",
        f"- conflicts: {len(result['conflicts'])}",
        f"- unresolved_rows: {len(result['unresolved_rows'])}",
        f"- skipped_rows: {len(result['skipped_rows'])}",
        f"- invalid_patches: {len(result['invalid_patches'])}",
        "",
    ]
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit taxon localized names readiness")
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument(
        "--referenced-candidates-path",
        type=Path,
        default=DEFAULT_REFERENCED_CANDIDATES_PATH,
    )
    parser.add_argument(
        "--referenced-snapshot-path",
        type=Path,
        default=DEFAULT_REFERENCED_SNAPSHOT_PATH,
    )
    parser.add_argument(
        "--candidate-relationships-path",
        type=Path,
        default=DEFAULT_CANDIDATE_REL_PATH,
    )
    parser.add_argument("--patch-schema", type=Path, default=DEFAULT_PATCH_SCHEMA_PATH)
    parser.add_argument("--patch-file", type=Path, default=DEFAULT_PATCH_FILE)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    args = parser.parse_args()

    patch_file = args.patch_file if args.patch_file.exists() else None
    result = run_audit(
        canonical_path=args.canonical_path,
        referenced_candidates_path=args.referenced_candidates_path,
        referenced_snapshot_path=args.referenced_snapshot_path,
        candidate_relationship_path=args.candidate_relationships_path,
        patch_schema_path=args.patch_schema,
        patch_file=patch_file,
        output_json=args.output_json,
        output_md=args.output_md,
    )

    print(f"Decision: {result['decision']}")
    print(f"Total taxa: {result['total_taxa_inspected']}")
    print(f"Candidate taxa missing FR: {result['distractor_candidate_taxa_missing_fr']}")


if __name__ == "__main__":
    main()
