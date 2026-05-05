"""Prepare a governed dry-run/apply plan for ReferencedTaxon shell candidates.

Sprint 13C scope:
- Reuse existing canonical/referenced mappings when available.
- Produce auditable plan artifacts for new referenced shells.
- Default to dry-run. Apply requires explicit confirmation.
- Never promote referenced taxa to canonical taxa.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_SHELL_CANDIDATES_PATH = Path(
    "docs/audits/evidence/referenced_taxon_shell_candidates_sprint12.json"
)
DEFAULT_RELATIONSHIP_CANDIDATES_PATH = Path(
    "docs/audits/evidence/distractor_relationship_candidates_v1_sprint12.json"
)
DEFAULT_CANONICAL_PATH = Path(
    "data/normalized/palier1_be_birds_50taxa_run003_v11_baseline.normalized.json"
)
DEFAULT_EXISTING_REFERENCED_PATH = Path("data/review_overrides/referenced_taxa_snapshot.json")
DEFAULT_LOCALIZED_AUDIT_PATH = Path(
    "docs/audits/evidence/taxon_localized_names_sprint13_audit.json"
)
DEFAULT_LOCALIZED_PATCH_FILE = Path("data/manual/taxon_localized_name_patches_v1.json")

DEFAULT_OUTPUT_JSON = Path("docs/audits/evidence/referenced_taxon_shell_apply_plan_sprint13.json")
DEFAULT_OUTPUT_MD = Path("docs/audits/referenced-taxon-shell-apply-plan-sprint13.md")
DEFAULT_APPLY_OUTPUT_REFERENCED = Path("data/review_overrides/referenced_taxa_snapshot.json")

APPLY_CONFIRMATION_TOKEN = "APPLY_REFERENCED_TAXON_SHELLS"
LANGS = ("fr", "en", "nl")


def load_json_if_exists(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _normalize_name_map(name_map: dict[str, Any] | None) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for lang in LANGS:
        values = [] if name_map is None else name_map.get(lang, [])
        if not isinstance(values, list):
            values = []
        cleaned = [str(v).strip() for v in values if str(v).strip()]
        out[lang] = cleaned
    return out


def _has_fr(name_map: dict[str, list[str]]) -> bool:
    return bool(name_map.get("fr"))


def _clean_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "none":
        return None
    return text


def _canonical_indexes(
    canonical_taxa: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, list[str]]]:
    by_source_id: dict[str, str] = {}
    by_scientific: dict[str, list[str]] = {}

    for item in canonical_taxa:
        canonical_id = str(item.get("canonical_taxon_id", "")).strip()
        scientific_name = str(item.get("accepted_scientific_name", "")).strip().lower()
        if canonical_id and scientific_name:
            by_scientific.setdefault(scientific_name, []).append(canonical_id)

        for mapping in item.get("external_source_mappings", []):
            source_name = str(mapping.get("source_name", "")).strip()
            source_id = str(mapping.get("external_id", "")).strip()
            if source_name == "inaturalist" and source_id and canonical_id:
                by_source_id[source_id] = canonical_id

    return by_source_id, by_scientific


def _referenced_indexes(
    referenced_payload: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_source_id: dict[str, dict[str, Any]] = {}
    by_scientific: dict[str, dict[str, Any]] = {}
    if not referenced_payload:
        return by_source_id, by_scientific

    rows = referenced_payload.get("referenced_taxa", referenced_payload.get("items", []))
    if not isinstance(rows, list):
        rows = []

    for item in rows:
        if not isinstance(item, dict):
            continue
        source_taxon_id = str(item.get("source_taxon_id", "")).strip()
        scientific_name = str(item.get("scientific_name", "")).strip().lower()
        if source_taxon_id:
            by_source_id[source_taxon_id] = item
        if scientific_name:
            by_scientific[scientific_name] = item
    return by_source_id, by_scientific


def _patch_name_indexes(
    patch_payload: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, list[str]]], dict[str, dict[str, list[str]]]]:
    by_source_id: dict[str, dict[str, list[str]]] = {}
    by_scientific: dict[str, dict[str, list[str]]] = {}
    if not patch_payload:
        return by_source_id, by_scientific

    rows = patch_payload.get("patches", patch_payload)
    if not isinstance(rows, list):
        return by_source_id, by_scientific

    for row in rows:
        if not isinstance(row, dict):
            continue
        source_taxon_id = str(row.get("source_taxon_id", "")).strip()
        scientific_name = str(row.get("scientific_name", "")).strip().lower()

        names = {
            "fr": [str(row["common_name_fr"]).strip()]
            if str(row.get("common_name_fr", "")).strip()
            else [],
            "en": [str(row["common_name_en"]).strip()]
            if str(row.get("common_name_en", "")).strip()
            else [],
            "nl": [str(row["common_name_nl"]).strip()]
            if str(row.get("common_name_nl", "")).strip()
            else [],
        }

        if source_taxon_id:
            by_source_id[source_taxon_id] = names
        if scientific_name:
            by_scientific[scientific_name] = names
    return by_source_id, by_scientific


def _merge_names(
    candidate_names: dict[str, Any] | None,
    existing_names: dict[str, Any] | None,
    patch_names: dict[str, list[str]] | None,
) -> tuple[dict[str, list[str]], str]:
    merged = _normalize_name_map(candidate_names)
    name_source_status = "candidate"

    existing_norm = _normalize_name_map(existing_names)
    for lang in LANGS:
        if not merged[lang] and existing_norm[lang]:
            merged[lang] = existing_norm[lang]
            name_source_status = "existing_referenced"

    if patch_names:
        for lang in LANGS:
            if patch_names.get(lang):
                merged[lang] = [str(patch_names[lang][0]).strip()]
                name_source_status = "localized_patch"

    if not any(merged.values()):
        name_source_status = "missing"

    return merged, name_source_status


def _build_relationship_usage(
    relationship_payload: dict[str, Any] | None,
) -> dict[str, int]:
    usage: dict[str, int] = {}
    if not relationship_payload:
        return usage

    rows = relationship_payload.get("relationships", [])
    if not isinstance(rows, list):
        return usage

    for row in rows:
        if not isinstance(row, dict):
            continue
        ref_type = str(row.get("candidate_taxon_ref_type", "")).strip()
        ref_id = str(row.get("candidate_taxon_ref_id", "")).strip()
        scientific = str(row.get("candidate_scientific_name", "")).strip().lower()
        key = f"{ref_type}:{ref_id or scientific}"
        usage[key] = usage.get(key, 0) + 1
    return usage


def _decision_label(
    *,
    new_shell_plan_count: int,
    ambiguous_count: int,
    conflicts_count: int,
    shells_with_fr_name_count: int,
    shells_missing_fr_name_count: int,
) -> str:
    if ambiguous_count > 0:
        return "BLOCKED_BY_AMBIGUOUS_TAXA"
    if conflicts_count > 0:
        return "NEEDS_REFERENCED_TAXON_REVIEW"
    if new_shell_plan_count == 0:
        return "READY_TO_APPLY_REFERENCED_TAXON_SHELLS"
    if shells_missing_fr_name_count == 0:
        return "READY_TO_APPLY_REFERENCED_TAXON_SHELLS"
    if shells_with_fr_name_count == 0:
        return "NEEDS_NAME_COMPLETION_FOR_SHELLS"
    return "READY_FOR_PRIORITY_NAME_COMPLETION"


def prepare_apply_plan(
    *,
    shell_candidates_payload: dict[str, Any],
    relationship_candidates_payload: dict[str, Any] | None,
    canonical_payload: dict[str, Any],
    existing_referenced_payload: dict[str, Any] | None,
    localized_audit_payload: dict[str, Any] | None,
    localized_patch_payload: dict[str, Any] | None,
    dry_run: bool,
) -> dict[str, Any]:
    shell_candidates = shell_candidates_payload.get("items", [])
    if not isinstance(shell_candidates, list):
        shell_candidates = []

    canonical_taxa = canonical_payload.get("canonical_taxa", [])
    if not isinstance(canonical_taxa, list):
        canonical_taxa = []

    canonical_by_source_id, canonical_by_scientific = _canonical_indexes(canonical_taxa)
    existing_by_source_id, existing_by_scientific = _referenced_indexes(existing_referenced_payload)
    patch_by_source_id, patch_by_scientific = _patch_name_indexes(localized_patch_payload)
    relationship_usage = _build_relationship_usage(relationship_candidates_payload)

    apply_records: list[dict[str, Any]] = []
    skipped_records: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    seen_source_ids: dict[str, str] = {}

    mapped_to_canonical_count = 0
    existing_referenced_count = 0
    ambiguous_count = 0
    ignored_count = 0
    shells_with_fr_name_count = 0
    shells_missing_fr_name_count = 0

    for candidate in shell_candidates:
        if not isinstance(candidate, dict):
            ignored_count += 1
            skipped_records.append(
                {
                    "reason": "invalid_candidate_row",
                    "candidate": candidate,
                }
            )
            continue

        source = str(candidate.get("source", "")).strip() or "inaturalist"
        source_taxon_id = str(candidate.get("source_taxon_id", "")).strip()
        scientific_name = str(candidate.get("scientific_name", "")).strip()
        scientific_key = scientific_name.lower()

        mapped_canonical_taxon_id = _clean_optional_str(
            candidate.get("mapped_canonical_taxon_id")
        )
        if mapped_canonical_taxon_id is None and source == "inaturalist" and source_taxon_id:
            mapped_canonical_taxon_id = canonical_by_source_id.get(source_taxon_id)
        if mapped_canonical_taxon_id is None and scientific_key:
            sci_matches = canonical_by_scientific.get(scientific_key, [])
            if len(sci_matches) == 1:
                mapped_canonical_taxon_id = sci_matches[0]

        existing_referenced_taxon_id = _clean_optional_str(
            candidate.get("existing_referenced_taxon_id")
        )
        existing_referenced = None
        if source_taxon_id and source_taxon_id in existing_by_source_id:
            existing_referenced = existing_by_source_id[source_taxon_id]
        elif scientific_key and scientific_key in existing_by_scientific:
            existing_referenced = existing_by_scientific[scientific_key]

        if existing_referenced and not existing_referenced_taxon_id:
            existing_referenced_taxon_id = _clean_optional_str(
                existing_referenced.get("referenced_taxon_id")
            )

        if mapped_canonical_taxon_id:
            mapped_to_canonical_count += 1
            skipped_records.append(
                {
                    "source_taxon_id": source_taxon_id or None,
                    "scientific_name": scientific_name or None,
                    "reason": "mapped_to_existing_canonical_taxon",
                    "mapped_canonical_taxon_id": mapped_canonical_taxon_id,
                }
            )
            continue

        if existing_referenced_taxon_id:
            existing_referenced_count += 1
            skipped_records.append(
                {
                    "source_taxon_id": source_taxon_id or None,
                    "scientific_name": scientific_name or None,
                    "reason": "existing_referenced_taxon_reused",
                    "existing_referenced_taxon_id": existing_referenced_taxon_id,
                }
            )
            continue

        if not scientific_name:
            if source_taxon_id:
                ambiguous_count += 1
                skipped_records.append(
                    {
                        "source_taxon_id": source_taxon_id,
                        "scientific_name": None,
                        "reason": "ambiguous_missing_scientific_name",
                        "manual_review_required": True,
                    }
                )
            else:
                ignored_count += 1
                skipped_records.append(
                    {
                        "source_taxon_id": None,
                        "scientific_name": None,
                        "reason": "ignored_missing_source_taxon_id_and_scientific_name",
                    }
                )
            continue

        if not source_taxon_id:
            ambiguous_count += 1
            skipped_records.append(
                {
                    "source_taxon_id": None,
                    "scientific_name": scientific_name,
                    "reason": "ambiguous_missing_source_taxon_id",
                    "manual_review_required": True,
                }
            )
            continue

        if (
            source_taxon_id in seen_source_ids
            and seen_source_ids[source_taxon_id] != scientific_key
        ):
            ambiguous_count += 1
            conflicts.append(
                {
                    "source_taxon_id": source_taxon_id,
                    "reason": "source_taxon_id_with_multiple_scientific_names",
                    "existing_scientific_name": seen_source_ids[source_taxon_id],
                    "incoming_scientific_name": scientific_key,
                }
            )
            skipped_records.append(
                {
                    "source_taxon_id": source_taxon_id,
                    "scientific_name": scientific_name,
                    "reason": "ambiguous_conflicting_scientific_name_for_source_taxon_id",
                    "manual_review_required": True,
                }
            )
            continue
        seen_source_ids[source_taxon_id] = scientific_key

        patch_names = patch_by_source_id.get(source_taxon_id)
        if patch_names is None and scientific_key:
            patch_names = patch_by_scientific.get(scientific_key)

        existing_names = None
        if existing_referenced:
            existing_names = existing_referenced.get("common_names_i18n")

        common_names_i18n, name_source_status = _merge_names(
            candidate.get("common_names_i18n"),
            existing_names,
            patch_names,
        )

        has_fr = _has_fr(common_names_i18n)
        if has_fr:
            shells_with_fr_name_count += 1
        else:
            shells_missing_fr_name_count += 1

        proposed_ref_id = f"reftaxon:{source}:{source_taxon_id}"
        relation_key = f"referenced_taxon:reftaxon:{source}:{source_taxon_id}"
        relation_count = relationship_usage.get(relation_key, 0)

        apply_records.append(
            {
                "operation": "create_referenced_taxon_shell",
                "source": source,
                "source_taxon_id": source_taxon_id,
                "scientific_name": scientific_name,
                "common_names_i18n": common_names_i18n,
                "proposed_mapping_status": str(
                    candidate.get("proposed_mapping_status", "auto_referenced_low_confidence")
                ),
                "confidence": candidate.get("confidence"),
                "reason_codes": candidate.get("reason_codes", []),
                "mapped_canonical_taxon_id": None,
                "existing_referenced_taxon_id": None,
                "proposed_referenced_taxon_id": proposed_ref_id,
                "can_be_distractor_fr": has_fr,
                "name_source_status": name_source_status,
                "notes": candidate.get("notes", []),
                "manual_review_required": False,
                "relationship_usage_count": relation_count,
                "rollback_note": (
                    "Delete created referenced taxon by source+source_taxon_id or "
                    "restore snapshot backup before apply."
                ),
            }
        )

    new_shell_plan_count = len(apply_records)

    decision = _decision_label(
        new_shell_plan_count=new_shell_plan_count,
        ambiguous_count=ambiguous_count,
        conflicts_count=len(conflicts),
        shells_with_fr_name_count=shells_with_fr_name_count,
        shells_missing_fr_name_count=shells_missing_fr_name_count,
    )

    localized_audit_note = None
    if localized_audit_payload:
        localized_audit_note = {
            "localized_audit_decision": localized_audit_payload.get("decision"),
            "localized_candidate_missing_fr": localized_audit_payload.get(
                "distractor_candidate_taxa_missing_fr"
            ),
        }

    rollback_notes = [
        "Before apply, create timestamped backup of referenced snapshot.",
        "Rollback by restoring the backup file if apply output is rejected in review.",
        "For targeted rollback, remove rows created by this run_date and source_taxon_id set.",
    ]

    execution_status = "complete"
    if decision in {"BLOCKED_BY_AMBIGUOUS_TAXA", "NEEDS_REFERENCED_TAXON_REVIEW"}:
        execution_status = "blocked_pending_review"

    return {
        "execution_status": execution_status,
        "dry_run": dry_run,
        "input_candidates_count": len(shell_candidates),
        "mapped_to_canonical_count": mapped_to_canonical_count,
        "existing_referenced_count": existing_referenced_count,
        "new_shell_plan_count": new_shell_plan_count,
        "ambiguous_count": ambiguous_count,
        "ignored_count": ignored_count,
        "shells_with_fr_name_count": shells_with_fr_name_count,
        "shells_missing_fr_name_count": shells_missing_fr_name_count,
        "apply_records": apply_records,
        "skipped_records": skipped_records,
        "conflicts": conflicts,
        "rollback_notes": rollback_notes,
        "decision": decision,
        "localized_name_context": localized_audit_note,
        "run_date": datetime.now(UTC).isoformat(),
    }


def apply_referenced_shell_plan(
    *,
    plan: dict[str, Any],
    existing_referenced_payload: dict[str, Any] | None,
    apply_output_referenced_path: Path,
) -> dict[str, Any]:
    if plan["dry_run"]:
        return {
            "storage_mutated": False,
            "records_created": 0,
            "records_skipped": len(plan["apply_records"]),
            "output_path": None,
            "backup_path": None,
        }

    if plan["decision"] in {"BLOCKED_BY_AMBIGUOUS_TAXA", "NEEDS_REFERENCED_TAXON_REVIEW"}:
        return {
            "storage_mutated": False,
            "records_created": 0,
            "records_skipped": len(plan["apply_records"]),
            "output_path": None,
            "backup_path": None,
        }

    existing = existing_referenced_payload or {}
    referenced_rows = existing.get("referenced_taxa", existing.get("items", []))
    if not isinstance(referenced_rows, list):
        referenced_rows = []

    by_source_id = {
        str(row.get("source_taxon_id", "")).strip(): row
        for row in referenced_rows
        if isinstance(row, dict) and str(row.get("source_taxon_id", "")).strip()
    }

    backup_path: str | None = None
    if apply_output_referenced_path.exists():
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = apply_output_referenced_path.with_suffix(
            apply_output_referenced_path.suffix + f".bak.{timestamp}"
        )
        backup.write_text(
            apply_output_referenced_path.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        backup_path = str(backup)

    created = 0
    for record in plan["apply_records"]:
        source_taxon_id = str(record.get("source_taxon_id", "")).strip()
        if not source_taxon_id or source_taxon_id in by_source_id:
            continue
        row = {
            "referenced_taxon_id": record["proposed_referenced_taxon_id"],
            "source": record["source"],
            "source_taxon_id": source_taxon_id,
            "scientific_name": record["scientific_name"],
            "common_names_i18n": record["common_names_i18n"],
            "mapping_status": "shell_planned_sprint13c",
            "name_source_status": record["name_source_status"],
            "can_be_distractor_fr": record["can_be_distractor_fr"],
            "created_at": plan["run_date"],
            "notes": record.get("notes", []),
        }
        referenced_rows.append(row)
        by_source_id[source_taxon_id] = row
        created += 1

    payload = {
        "referenced_taxa": referenced_rows,
        "updated_at": datetime.now(UTC).isoformat(),
        "source_of_truth": "scripts/prepare_referenced_taxon_shell_apply_plan_v1.py",
    }
    dump_json(apply_output_referenced_path, payload)

    return {
        "storage_mutated": True,
        "records_created": created,
        "records_skipped": len(plan["apply_records"]) - created,
        "output_path": str(apply_output_referenced_path),
        "backup_path": backup_path,
    }


def write_markdown_report(plan: dict[str, Any], output_md: Path) -> None:
    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        f"last_reviewed: {plan['run_date'][:10]}",
        "source_of_truth: docs/audits/referenced-taxon-shell-apply-plan-sprint13.md",
        "scope: audit",
        "---",
        "",
        "# Referenced Taxon Shell Apply Plan — Sprint 13C",
        "",
        "## Purpose",
        "",
        (
            "Create a governed dry-run/apply pathway for ReferencedTaxon "
            "shells needed by distractor candidates."
        ),
        "",
        "## Inputs",
        "",
        "- docs/audits/evidence/referenced_taxon_shell_candidates_sprint12.json",
        "- docs/audits/evidence/distractor_relationship_candidates_v1_sprint12.json",
        "- Sprint 13B localized name audit/patch artifacts when available",
        "- canonical/referenced stores when available",
        "",
        "## Shell Creation Rules",
        "",
        "- mapped canonical candidates never create shells",
        "- existing referenced taxa are reused",
        "- source_taxon_id + scientific_name creates shell plan",
        "- missing scientific_name becomes ambiguous or ignored",
        "- ambiguous rows require manual review and are never auto-applied",
        "- no canonical promotion",
        "",
        "## Breakdown",
        "",
        f"- input_candidates_count: {plan['input_candidates_count']}",
        f"- mapped_to_canonical_count: {plan['mapped_to_canonical_count']}",
        f"- existing_referenced_count: {plan['existing_referenced_count']}",
        f"- new_shell_plan_count: {plan['new_shell_plan_count']}",
        f"- ambiguous_count: {plan['ambiguous_count']}",
        f"- ignored_count: {plan['ignored_count']}",
        "",
        "## Localized Name Status",
        "",
        f"- shells_with_fr_name_count: {plan['shells_with_fr_name_count']}",
        f"- shells_missing_fr_name_count: {plan['shells_missing_fr_name_count']}",
        "",
        "## Dry-Run/Apply Status",
        "",
        f"- dry_run: {plan['dry_run']}",
        f"- decision: {plan['decision']}",
        f"- execution_status: {plan['execution_status']}",
        "",
        "## Risks",
        "",
        "- ambiguous taxa require manual adjudication before apply",
        "- missing FR names reduce FR distractor usability",
        "- source_taxon_id conflicts require review before mutation",
        "",
        "## Next Phase Recommendation",
        "",
    ]

    if plan["decision"] == "READY_TO_APPLY_REFERENCED_TAXON_SHELLS":
        lines.append("- proceed with explicit --apply + governance review of created rows")
    elif plan["decision"] == "READY_FOR_PRIORITY_NAME_COMPLETION":
        lines.append("- apply shells, then prioritize FR name completion for missing shells")
    elif plan["decision"] == "NEEDS_NAME_COMPLETION_FOR_SHELLS":
        lines.append("- complete FR naming pipeline before enabling FR-first distractor readiness")
    elif plan["decision"] == "NEEDS_REFERENCED_TAXON_REVIEW":
        lines.append("- resolve conflicts and rerun plan")
    else:
        lines.append("- resolve ambiguous taxa manually before apply")

    lines.extend(["", "## Rollback Notes", ""])
    for note in plan["rollback_notes"]:
        lines.append(f"- {note}")

    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_prepare(
    *,
    shell_candidates_path: Path,
    relationship_candidates_path: Path,
    canonical_path: Path,
    existing_referenced_path: Path,
    localized_audit_path: Path,
    localized_patch_file: Path,
    output_json: Path,
    output_md: Path,
    apply_output_referenced_path: Path,
    apply: bool,
    confirm_apply: str | None,
) -> dict[str, Any]:
    if apply and confirm_apply != APPLY_CONFIRMATION_TOKEN:
        raise ValueError(
            "--apply requires --confirm-apply APPLY_REFERENCED_TAXON_SHELLS"
        )

    shell_candidates_payload = load_json_if_exists(shell_candidates_path)
    if shell_candidates_payload is None:
        raise FileNotFoundError(f"Missing shell candidates: {shell_candidates_path}")

    canonical_payload = load_json_if_exists(canonical_path)
    if canonical_payload is None:
        raise FileNotFoundError(f"Missing canonical payload: {canonical_path}")

    relationship_candidates_payload = load_json_if_exists(relationship_candidates_path)
    existing_referenced_payload = load_json_if_exists(existing_referenced_path)
    localized_audit_payload = load_json_if_exists(localized_audit_path)
    localized_patch_payload = load_json_if_exists(localized_patch_file)

    plan = prepare_apply_plan(
        shell_candidates_payload=shell_candidates_payload,
        relationship_candidates_payload=relationship_candidates_payload,
        canonical_payload=canonical_payload,
        existing_referenced_payload=existing_referenced_payload,
        localized_audit_payload=localized_audit_payload,
        localized_patch_payload=localized_patch_payload,
        dry_run=not apply,
    )

    apply_result = apply_referenced_shell_plan(
        plan=plan,
        existing_referenced_payload=existing_referenced_payload,
        apply_output_referenced_path=apply_output_referenced_path,
    )
    plan["apply_result"] = apply_result
    plan["inputs"] = {
        "shell_candidates_path": str(shell_candidates_path),
        "relationship_candidates_path": str(relationship_candidates_path),
        "canonical_path": str(canonical_path),
        "existing_referenced_path": str(existing_referenced_path),
        "localized_audit_path": str(localized_audit_path),
        "localized_patch_file": str(localized_patch_file),
    }

    dump_json(output_json, plan)
    write_markdown_report(plan, output_md)
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare ReferencedTaxon shell apply plan (dry-run by default)"
    )
    parser.add_argument(
        "--shell-candidates",
        type=Path,
        default=DEFAULT_SHELL_CANDIDATES_PATH,
    )
    parser.add_argument(
        "--relationship-candidates",
        type=Path,
        default=DEFAULT_RELATIONSHIP_CANDIDATES_PATH,
    )
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument(
        "--existing-referenced",
        type=Path,
        default=DEFAULT_EXISTING_REFERENCED_PATH,
    )
    parser.add_argument(
        "--localized-audit",
        type=Path,
        default=DEFAULT_LOCALIZED_AUDIT_PATH,
    )
    parser.add_argument(
        "--localized-patch-file",
        type=Path,
        default=DEFAULT_LOCALIZED_PATCH_FILE,
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument(
        "--apply-output-referenced",
        type=Path,
        default=DEFAULT_APPLY_OUTPUT_REFERENCED,
    )
    parser.add_argument("--apply", action="store_true", default=False)
    parser.add_argument("--confirm-apply", type=str, default=None)
    args = parser.parse_args()

    result = run_prepare(
        shell_candidates_path=args.shell_candidates,
        relationship_candidates_path=args.relationship_candidates,
        canonical_path=args.canonical,
        existing_referenced_path=args.existing_referenced,
        localized_audit_path=args.localized_audit,
        localized_patch_file=args.localized_patch_file,
        output_json=args.output_json,
        output_md=args.output_md,
        apply_output_referenced_path=args.apply_output_referenced,
        apply=args.apply,
        confirm_apply=args.confirm_apply,
    )

    print(f"Decision: {result['decision']}")
    print(f"Dry run: {result['dry_run']}")
    print(f"New shell plan count: {result['new_shell_plan_count']}")
    print(f"Shells missing FR: {result['shells_missing_fr_name_count']}")


if __name__ == "__main__":
    main()
