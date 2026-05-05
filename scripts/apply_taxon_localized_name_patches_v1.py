"""Apply taxon localized name patches with dry-run default.

Supports canonical_taxon and referenced_taxon patch application to local JSON data
artifacts. unresolved_taxon patches are audit-only and never auto-applied.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from database_core.enrichment.localized_names import (  # noqa: E402
    apply_plan_to_taxa,
    build_localized_name_apply_plan,
    write_plan_artifacts,
)

DEFAULT_PATCH_SCHEMA_PATH = Path("schemas/taxon_localized_name_patch_v1.schema.json")
DEFAULT_PATCH_FILE = Path("data/manual/taxon_localized_name_patches_v1.json")
DEFAULT_CANONICAL_PATH = Path(
    "data/normalized/palier1_be_birds_50taxa_run003_v11_baseline.normalized.json"
)
DEFAULT_REFERENCED_CANDIDATES_PATH = Path(
    "docs/audits/evidence/referenced_taxon_shell_candidates_sprint12.json"
)
DEFAULT_REFERENCED_SNAPSHOT_PATH = Path("data/review_overrides/referenced_taxa_snapshot.json")
DEFAULT_OUTPUT_CANONICAL = Path(
    "data/enriched/taxon_localized_names_v1/canonical_taxa_patched.json"
)
DEFAULT_OUTPUT_REFERENCED = Path(
    "data/enriched/taxon_localized_names_v1/referenced_taxa_patched.json"
)
DEFAULT_OUTPUT_EVIDENCE_JSON = Path(
    "docs/audits/evidence/taxon_localized_names_sprint13_apply.json"
)
DEFAULT_OUTPUT_EVIDENCE_MD = Path("docs/audits/taxon-localized-names-sprint13-apply.md")
DEFAULT_PLAN_CANONICAL_PATH = Path(
    "data/enriched/taxon_localized_names_v1/canonical_taxa_patched.json"
)
DEFAULT_PLAN_REFERENCED_PATH = Path(
    "data/enriched/taxon_localized_names_v1/referenced_taxa_patched.json"
)

LANGS = ("fr", "en", "nl")
CONFIDENCE_LEVELS = {"high", "medium", "low"}


def _clean_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "none":
        return None
    return text


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def validate_patch_records(
    patches: list[dict[str, Any]], schema: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    validator = Draft202012Validator(schema)
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []

    for index, patch in enumerate(patches):
        errors = sorted(validator.iter_errors(patch), key=lambda err: err.path)
        if errors:
            invalid.append(
                {
                    "patch_index": index,
                    "patch_id": patch.get("patch_id"),
                    "reasons": [err.message for err in errors],
                    "patch": patch,
                }
            )
        else:
            valid.append(patch)
    return valid, invalid


def load_referenced_records(
    candidates_path: Path,
    snapshot_path: Path,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    if candidates_path.exists():
        payload = load_json(candidates_path)
        for item in payload.get("items", []):
            if not isinstance(item, dict):
                continue
            source_taxon_id = str(item.get("source_taxon_id", "")).strip()
            existing_ref = _clean_optional_str(item.get("existing_referenced_taxon_id"))
            derived_ref = f"reftaxon:inaturalist:{source_taxon_id}" if source_taxon_id else None
            rid = existing_ref or derived_ref
            records.append(
                {
                    "referenced_taxon_id": rid,
                    "source_taxon_id": source_taxon_id or None,
                    "scientific_name": item.get("scientific_name"),
                    "common_names_i18n": item.get("common_names_i18n") or {},
                    "source_record": "referenced_taxon_shell_candidates_sprint12",
                }
            )

    if snapshot_path.exists():
        payload = load_json(snapshot_path)
        snapshot_items = payload.get("referenced_taxa", payload.get("items", []))
        for item in snapshot_items:
            if not isinstance(item, dict):
                continue
            records.append(
                {
                    "referenced_taxon_id": item.get("referenced_taxon_id"),
                    "source_taxon_id": item.get("source_taxon_id"),
                    "scientific_name": item.get("scientific_name"),
                    "common_names_i18n": item.get("common_names_i18n") or {},
                    "source_record": "referenced_taxa_snapshot",
                }
            )

    dedup: dict[str, dict[str, Any]] = {}
    for rec in records:
        rid = str(rec.get("referenced_taxon_id", "")).strip()
        if not rid:
            continue
        dedup[rid] = rec
    return list(dedup.values())


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


def _first_lang_name(record: dict[str, Any], lang: str) -> str | None:
    names = record.get("common_names_i18n", {}).get(lang, [])
    if isinstance(names, list) and names:
        name = str(names[0]).strip()
        return name if name else None
    return None


def _set_lang_name(record: dict[str, Any], lang: str, value: str) -> None:
    names = dict(record.get("common_names_i18n") or {})
    names[lang] = [value]
    record["common_names_i18n"] = names


def _resolve_canonical_target(
    patch: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    by_scientific: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, str | None]:
    cid = str(patch.get("canonical_taxon_id", "")).strip()
    sci = str(patch.get("scientific_name", "")).strip().lower()

    if cid:
        return by_id.get(cid), None if cid in by_id else "canonical_taxon_not_found"
    if sci:
        matches = by_scientific.get(sci, [])
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, "ambiguous_canonical_scientific_name"
    return None, "canonical_target_unresolved"


def _resolve_referenced_target(
    patch: dict[str, Any],
    by_ref_id: dict[str, dict[str, Any]],
    by_source_id: dict[str, list[dict[str, Any]]],
    by_scientific: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, str | None]:
    rid = str(patch.get("referenced_taxon_id", "")).strip()
    sid = str(patch.get("source_taxon_id", "")).strip()
    sci = str(patch.get("scientific_name", "")).strip().lower()

    if rid:
        return by_ref_id.get(rid), None if rid in by_ref_id else "referenced_taxon_not_found"
    if sid:
        matches = by_source_id.get(sid, [])
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, "ambiguous_source_taxon_id"
    if sci:
        matches = by_scientific.get(sci, [])
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, "ambiguous_referenced_scientific_name"
    return None, "referenced_target_unresolved"


def apply_patches(
    patches: list[dict[str, Any]],
    canonical_taxa: list[dict[str, Any]],
    referenced_taxa: list[dict[str, Any]],
) -> dict[str, Any]:
    canonical_work = [dict(item) for item in canonical_taxa]
    referenced_work = [dict(item) for item in referenced_taxa]

    for item in canonical_work:
        item["common_names_i18n"] = _normalize_name_map(item.get("common_names_i18n") or {})
    for item in referenced_work:
        item["common_names_i18n"] = _normalize_name_map(item.get("common_names_i18n") or {})

    by_cid = {
        item["canonical_taxon_id"]: item
        for item in canonical_work
        if item.get("canonical_taxon_id")
    }
    by_cscientific: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in canonical_work:
        sci = (
            str(item.get("scientific_name") or item.get("accepted_scientific_name") or "")
            .strip()
            .lower()
        )
        if sci:
            by_cscientific[sci].append(item)

    by_rid = {
        item["referenced_taxon_id"]: item
        for item in referenced_work
        if item.get("referenced_taxon_id")
    }
    by_source_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_rscientific: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in referenced_work:
        sid = str(item.get("source_taxon_id", "")).strip()
        if sid:
            by_source_id[sid].append(item)
        sci = str(item.get("scientific_name", "")).strip().lower()
        if sci:
            by_rscientific[sci].append(item)

    applied: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []

    for patch in patches:
        patch_id = patch.get("patch_id")
        ref_type = patch.get("taxon_ref_type")

        if ref_type == "unresolved_taxon":
            skipped.append(
                {
                    "patch_id": patch_id,
                    "reason": "unresolved_taxon_patch_is_audit_only",
                    "patch": patch,
                }
            )
            continue

        target: dict[str, Any] | None = None
        target_error: str | None = None

        if ref_type == "canonical_taxon":
            target, target_error = _resolve_canonical_target(patch, by_cid, by_cscientific)
        elif ref_type == "referenced_taxon":
            target, target_error = _resolve_referenced_target(
                patch, by_rid, by_source_id, by_rscientific
            )
        else:
            unresolved.append(
                {
                    "patch_id": patch_id,
                    "reason": "unknown_taxon_ref_type",
                    "patch": patch,
                }
            )
            continue

        if target is None:
            unresolved.append({"patch_id": patch_id, "reason": target_error, "patch": patch})
            continue

        source = str(patch.get("source", "")).strip()
        confidence = str(patch.get("confidence", "")).strip().lower()
        reviewer = str(patch.get("reviewer", "")).strip()
        can_manual_override = (
            source == "manual_override" and reviewer and confidence in CONFIDENCE_LEVELS
        )

        lang_updates = 0
        for lang in LANGS:
            key = f"common_name_{lang}"
            new_value = patch.get(key)
            if new_value is None:
                continue
            new_name = str(new_value).strip()
            if not new_name:
                continue

            existing_name = _first_lang_name(target, lang)
            if not existing_name:
                _set_lang_name(target, lang, new_name)
                lang_updates += 1
                continue

            if existing_name.lower() == new_name.lower():
                skipped.append(
                    {
                        "patch_id": patch_id,
                        "reason": f"same_value_{lang}",
                        "existing": existing_name,
                        "proposed": new_name,
                    }
                )
                continue

            if can_manual_override:
                _set_lang_name(target, lang, new_name)
                lang_updates += 1
                conflicts.append(
                    {
                        "patch_id": patch_id,
                        "lang": lang,
                        "existing": existing_name,
                        "proposed": new_name,
                        "resolution": "manual_override_applied",
                        "reviewer": reviewer,
                        "confidence": confidence,
                    }
                )
                continue

            conflicts.append(
                {
                    "patch_id": patch_id,
                    "lang": lang,
                    "existing": existing_name,
                    "proposed": new_name,
                    "resolution": "blocked_conflict",
                    "reason": "manual_override_with_reviewer_required",
                }
            )

        if lang_updates > 0:
            applied.append(
                {
                    "patch_id": patch_id,
                    "taxon_ref_type": ref_type,
                    "applied_languages_count": lang_updates,
                    "source": source,
                    "confidence": confidence,
                    "reviewer": reviewer or None,
                    "notes": patch.get("notes"),
                }
            )

    return {
        "canonical_taxa": canonical_work,
        "referenced_taxa": referenced_work,
        "applied": applied,
        "conflicts": conflicts,
        "skipped": skipped,
        "unresolved": unresolved,
    }


def run_apply(
    patch_file: Path,
    patch_schema_path: Path,
    canonical_path: Path,
    referenced_candidates_path: Path,
    referenced_snapshot_path: Path,
    dry_run: bool,
    apply: bool,
    output_canonical: Path,
    output_referenced: Path,
    output_evidence_json: Path,
    output_evidence_md: Path,
) -> dict[str, Any]:
    patch_payload = load_json(patch_file)
    raw_patches = patch_payload.get("patches", patch_payload)
    if not isinstance(raw_patches, list):
        raw_patches = []

    schema = load_json(patch_schema_path)
    valid_patches, invalid_patches = validate_patch_records(raw_patches, schema)

    canonical_payload = load_json(canonical_path)
    canonical_taxa = []
    for item in canonical_payload.get("canonical_taxa", []):
        canonical_taxa.append(
            {
                "canonical_taxon_id": item.get("canonical_taxon_id"),
                "scientific_name": item.get("accepted_scientific_name"),
                "common_names_i18n": item.get("common_names_by_language") or {},
            }
        )

    referenced_taxa = load_referenced_records(referenced_candidates_path, referenced_snapshot_path)

    apply_result = apply_patches(valid_patches, canonical_taxa, referenced_taxa)

    mode = "dry_run" if (dry_run and not apply) else "apply"
    evidence = {
        "execution_status": "complete",
        "run_date": datetime.now(UTC).isoformat(),
        "mode": mode,
        "patch_file": str(patch_file),
        "patch_schema": str(patch_schema_path),
        "input_patch_count": len(raw_patches),
        "valid_patch_count": len(valid_patches),
        "invalid_patch_count": len(invalid_patches),
        "applied_count": len(apply_result["applied"]),
        "conflict_count": len(apply_result["conflicts"]),
        "skipped_count": len(apply_result["skipped"]),
        "unresolved_count": len(apply_result["unresolved"]),
        "invalid_patches": invalid_patches,
        "applied": apply_result["applied"],
        "conflicts": apply_result["conflicts"],
        "skipped": apply_result["skipped"],
        "unresolved": apply_result["unresolved"],
        "provenance": {
            "sources": dict(Counter(str(p.get("source", "")).strip() for p in valid_patches)),
            "confidence_distribution": dict(
                Counter(str(p.get("confidence", "")).strip().lower() for p in valid_patches)
            ),
        },
    }

    if apply and not dry_run:
        dump_json(output_canonical, {"canonical_taxa": apply_result["canonical_taxa"]})
        dump_json(output_referenced, {"referenced_taxa": apply_result["referenced_taxa"]})
        evidence["outputs"] = {
            "canonical": str(output_canonical),
            "referenced": str(output_referenced),
        }
    else:
        evidence["outputs"] = {"canonical": None, "referenced": None}

    dump_json(output_evidence_json, evidence)

    decision = "LOCALIZED_NAMES_SYSTEM_READY"
    if evidence["invalid_patch_count"] > 0:
        decision = "NEEDS_NAME_PATCH_FIXES"
    elif evidence["conflict_count"] > 0:
        decision = "NEEDS_CONFLICT_REVIEW"

    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        f"last_reviewed: {evidence['run_date'][:10]}",
        "source_of_truth: docs/audits/taxon-localized-names-sprint13-apply.md",
        "scope: audit",
        "---",
        "",
        "# Taxon Localized Names Sprint 13 Apply",
        "",
        f"- mode: {mode}",
        f"- decision: {decision}",
        f"- applied_count: {evidence['applied_count']}",
        f"- conflict_count: {evidence['conflict_count']}",
        f"- skipped_count: {evidence['skipped_count']}",
        f"- unresolved_count: {evidence['unresolved_count']}",
        f"- invalid_patch_count: {evidence['invalid_patch_count']}",
    ]
    output_evidence_md.parent.mkdir(parents=True, exist_ok=True)
    output_evidence_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    evidence["decision"] = decision
    return evidence


def run_apply_plan(
    *,
    dry_run: bool,
    apply: bool,
    output_canonical: Path,
    output_referenced: Path,
    output_evidence_json: Path,
    output_evidence_md: Path,
    canonical_path: Path = DEFAULT_PLAN_CANONICAL_PATH,
    referenced_path: Path = DEFAULT_PLAN_REFERENCED_PATH,
) -> dict[str, Any]:
    plan = build_localized_name_apply_plan(Path.cwd())
    write_plan_artifacts(plan, Path.cwd())

    canonical_payload = load_json(canonical_path)
    referenced_payload = load_json(referenced_path)
    result = apply_plan_to_taxa(
        plan,
        canonical_payload.get("canonical_taxa", []),
        referenced_payload.get("referenced_taxa", []),
    )

    mode = "dry_run" if (dry_run and not apply) else "apply"
    evidence = {
        "execution_status": "complete",
        "run_date": datetime.now(UTC).isoformat(),
        "mode": mode,
        "source": "localized_name_apply_plan_v1",
        "plan_hash": plan.plan_hash,
        "applied_count": len(result["applied"]),
        "skipped_count": len(result["skipped"]),
        "conflict_count": 0,
        "unresolved_count": 0,
        "invalid_patch_count": 0,
        "applied": result["applied"],
        "skipped": result["skipped"],
        "outputs": {"canonical": None, "referenced": None},
    }

    if apply and not dry_run:
        dump_json(output_canonical, {"canonical_taxa": result["canonical_taxa"]})
        dump_json(output_referenced, {"referenced_taxa": result["referenced_taxa"]})
        evidence["outputs"] = {
            "canonical": str(output_canonical),
            "referenced": str(output_referenced),
        }

    dump_json(output_evidence_json, evidence)
    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        f"last_reviewed: {evidence['run_date'][:10]}",
        "source_of_truth: docs/audits/taxon-localized-names-source-attested-sprint14-apply.md",
        "scope: sprint14b_localized_names",
        "---",
        "",
        "# Taxon Localized Names Apply Plan",
        "",
        f"- mode: {mode}",
        f"- plan_hash: {plan.plan_hash}",
        f"- applied_count: {evidence['applied_count']}",
        f"- skipped_count: {evidence['skipped_count']}",
    ]
    output_evidence_md.parent.mkdir(parents=True, exist_ok=True)
    output_evidence_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    evidence["decision"] = "LOCALIZED_NAMES_SYSTEM_READY"
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply localized name patches (dry-run by default)"
    )
    parser.add_argument("--patch-file", type=Path, default=DEFAULT_PATCH_FILE)
    parser.add_argument("--patch-schema", type=Path, default=DEFAULT_PATCH_SCHEMA_PATH)
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
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true", default=False)
    parser.add_argument(
        "--use-localized-name-plan",
        action="store_true",
        default=False,
        help="Apply/dry-run the unified localized_name_apply_plan_v1 instead of patch JSON.",
    )
    parser.add_argument("--output-canonical", type=Path, default=DEFAULT_OUTPUT_CANONICAL)
    parser.add_argument("--output-referenced", type=Path, default=DEFAULT_OUTPUT_REFERENCED)
    parser.add_argument("--output-evidence-json", type=Path, default=DEFAULT_OUTPUT_EVIDENCE_JSON)
    parser.add_argument("--output-evidence-md", type=Path, default=DEFAULT_OUTPUT_EVIDENCE_MD)
    args = parser.parse_args()

    effective_dry_run = args.dry_run and not args.apply
    if args.use_localized_name_plan:
        result = run_apply_plan(
            dry_run=effective_dry_run,
            apply=args.apply,
            output_canonical=args.output_canonical,
            output_referenced=args.output_referenced,
            output_evidence_json=args.output_evidence_json,
            output_evidence_md=args.output_evidence_md,
        )
    else:
        result = run_apply(
            patch_file=args.patch_file,
            patch_schema_path=args.patch_schema,
            canonical_path=args.canonical_path,
            referenced_candidates_path=args.referenced_candidates_path,
            referenced_snapshot_path=args.referenced_snapshot_path,
            dry_run=effective_dry_run,
            apply=args.apply,
            output_canonical=args.output_canonical,
            output_referenced=args.output_referenced,
            output_evidence_json=args.output_evidence_json,
            output_evidence_md=args.output_evidence_md,
        )

    print(f"Decision: {result['decision']}")
    print(f"Mode: {result['mode']}")
    print(f"Applied: {result['applied_count']}")
    print(f"Conflicts: {result['conflict_count']}")
    print(f"Skipped: {result['skipped_count']}")
    print(f"Unresolved: {result['unresolved_count']}")


if __name__ == "__main__":
    main()
