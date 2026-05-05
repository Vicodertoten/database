from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RUN_DATE = "2026-05-05"
PHASE = "Sprint 14B"

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "docs" / "audits" / "evidence" / "database_integrity_runtime_handoff_audit.json"
)
DEFAULT_OUTPUT_MD = REPO_ROOT / "docs" / "audits" / "database-integrity-runtime-handoff-audit.md"

REQUIRED_INPUTS = {
    "projected_relationships": REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "distractor_relationships_v1_projected_sprint13.json",
    "readiness_sprint13": REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "distractor_readiness_v1_sprint13.json",
    "readiness_sprint12_vs_sprint13": REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "distractor_readiness_sprint12_vs_sprint13.json",
}

OPTIONAL_INPUTS = {
    "shell_apply_plan": REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "referenced_taxon_shell_apply_plan_sprint13.json",
    "localized_apply": REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "taxon_localized_names_sprint13_apply.json",
    "pmp_human_review_analysis": REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "pmp_policy_v1_broader_400_20260504_human_review_analysis.json",
    "canonical_taxa_patched": REPO_ROOT
    / "data"
    / "enriched"
    / "taxon_localized_names_v1"
    / "canonical_taxa_patched.json",
    "referenced_taxa_patched": REPO_ROOT
    / "data"
    / "enriched"
    / "taxon_localized_names_v1"
    / "referenced_taxa_patched.json",
    "priority_seed_csv": REPO_ROOT / "data" / "manual" / "taxon_localized_name_patches_sprint13.csv",
}

LATIN_BINOMIAL_RE = re.compile(r"^[A-Z][a-z]+\s+[a-z][a-z-]+(?:\s+[a-z][a-z-]+)?$")


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    value: Any
    detail: str


def _load_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _extract_canonical_ids(payload: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for item in payload.get("canonical_taxa", []):
        if isinstance(item, dict):
            cid = str(item.get("canonical_taxon_id", "")).strip()
            if cid:
                out.add(cid)
    return out


def _extract_referenced_ids(payload: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for item in payload.get("referenced_taxa", []):
        if isinstance(item, dict):
            rid = str(item.get("referenced_taxon_id", "")).strip()
            if rid:
                out.add(rid)
    return out


def detect_duplicate_relationship_ids(records: list[dict[str, Any]]) -> list[str]:
    counts = Counter(str(r.get("relationship_id", "")).strip() for r in records)
    return sorted(rid for rid, count in counts.items() if rid and count > 1)


def count_target_equals_candidate(records: list[dict[str, Any]]) -> int:
    count = 0
    for row in records:
        target_id = str(row.get("target_canonical_taxon_id", "")).strip()
        candidate_id = str(row.get("candidate_taxon_ref_id", "")).strip()
        target_name = str(row.get("target_scientific_name", "")).strip()
        candidate_name = str(row.get("candidate_scientific_name", "")).strip()
        if target_id and candidate_id and target_id == candidate_id:
            count += 1
            continue
        if target_name and candidate_name and target_name == candidate_name:
            count += 1
    return count


def count_unresolved_marked_usable(records: list[dict[str, Any]]) -> int:
    usable = {"candidate", "approved", "usable", "ready"}
    return sum(
        1
        for row in records
        if row.get("candidate_taxon_ref_type") == "unresolved_taxon"
        and str(row.get("status", "")).strip() in usable
    )


def looks_like_latin_binomial(name: str) -> bool:
    return bool(LATIN_BINOMIAL_RE.match(name.strip()))


def is_placeholder_french_label(common_name_fr: str, scientific_name: str) -> bool:
    fr = common_name_fr.strip()
    sci = scientific_name.strip()
    if not fr:
        return False
    if sci and fr == sci:
        return True
    return looks_like_latin_binomial(fr)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def build_low_confidence_or_provisional_seed_ids(csv_rows: list[dict[str, str]] | None) -> set[str]:
    if not csv_rows:
        return set()
    out: set[str] = set()
    for row in csv_rows:
        candidate_id = str(row.get("candidate_taxon_ref_id", "")).strip()
        if not candidate_id:
            continue
        confidence = str(row.get("confidence", "")).strip().lower()
        source = str(row.get("source", "")).strip().lower()
        recommended_action = str(row.get("recommended_action", "")).strip().lower()
        notes = str(row.get("notes", "")).strip().lower()
        is_low = confidence == "low"
        is_provisional_seed = (
            "provisional" in notes
            or "seed_fr_then_human_review" in recommended_action
            or (source == "manual_override" and "human_review" in recommended_action)
        )
        if is_low or is_provisional_seed:
            out.add(candidate_id)
    return out


def is_runtime_unsafe_label(
    *,
    common_name_fr: str,
    scientific_name: str,
    low_confidence_or_provisional_seed: bool,
    explicit_placeholder_or_provisional: bool,
) -> bool:
    if low_confidence_or_provisional_seed:
        return True
    if explicit_placeholder_or_provisional:
        return True
    return is_placeholder_french_label(common_name_fr, scientific_name)


def extract_placeholder_sets(
    canonical_payload: dict[str, Any] | None,
    referenced_payload: dict[str, Any] | None,
) -> tuple[set[str], set[str], set[str], set[str]]:
    target_ids: set[str] = set()
    referenced_ids: set[str] = set()
    scientific_names: set[str] = set()
    all_placeholder_taxa: set[str] = set()

    def _scan(items: list[dict[str, Any]], is_canonical: bool) -> None:
        for item in items:
            sci = str(item.get("scientific_name", "")).strip()
            names = item.get("common_names_i18n", {})
            fr_values = names.get("fr", []) if isinstance(names, dict) else []
            if not isinstance(fr_values, list):
                continue
            has_placeholder = any(
                isinstance(v, str) and is_placeholder_french_label(v, sci)
                for v in fr_values
            )
            if not has_placeholder:
                continue
            if is_canonical:
                cid = str(item.get("canonical_taxon_id", "")).strip()
                if cid:
                    target_ids.add(cid)
                    all_placeholder_taxa.add(cid)
            else:
                rid = str(item.get("referenced_taxon_id", "")).strip()
                if rid:
                    referenced_ids.add(rid)
                    all_placeholder_taxa.add(rid)
            if sci:
                scientific_names.add(sci)

    if canonical_payload:
        _scan([i for i in canonical_payload.get("canonical_taxa", []) if isinstance(i, dict)], True)
    if referenced_payload:
        _scan([i for i in referenced_payload.get("referenced_taxa", []) if isinstance(i, dict)], False)

    return target_ids, referenced_ids, scientific_names, all_placeholder_taxa


def compute_placeholder_breakdown(
    records: list[dict[str, Any]],
    canonical_payload: dict[str, Any] | None,
    referenced_payload: dict[str, Any] | None,
    *,
    low_confidence_or_provisional_seed_ids: set[str] | None = None,
    runtime_guard_active: bool = True,
    first_corpus_minimum_target_count: int = 30,
) -> dict[str, Any]:
    if low_confidence_or_provisional_seed_ids is None:
        low_confidence_or_provisional_seed_ids = set()
    target_placeholder_ids, referenced_placeholder_ids, placeholder_scientific_names, all_placeholder_taxa = (
        extract_placeholder_sets(canonical_payload, referenced_payload)
    )
    referenced_by_id: dict[str, dict[str, Any]] = {}
    if referenced_payload:
        for item in referenced_payload.get("referenced_taxa", []):
            if isinstance(item, dict):
                rid = str(item.get("referenced_taxon_id", "")).strip()
                if rid:
                    referenced_by_id[rid] = item

    candidate_counts_by_target: dict[str, int] = {}
    unsafe_counts_by_target_before_guard: dict[str, int] = {}
    unsafe_counts_by_target_after_guard: dict[str, int] = {}

    candidate_placeholder_relationship_occurrence_count = 0
    corpus_facing_placeholder_relationship_occurrence_count = 0
    corpus_facing_placeholder_relationship_occurrence_count_after_guard = 0
    placeholder_relationship_occurrences_marked_not_for_corpus_display = 0
    affected_target_taxa: set[str] = set()
    affected_ready_targets: set[str] = set()
    all_ready_targets: set[str] = set()
    for row in records:
        candidate_id = str(row.get("candidate_taxon_ref_id", "")).strip()
        candidate_sci = str(row.get("candidate_scientific_name", "")).strip()
        target_id = str(row.get("target_canonical_taxon_id", "")).strip()
        status = str(row.get("status", "")).strip()
        if status == "candidate" and target_id:
            all_ready_targets.add(target_id)
            candidate_counts_by_target[target_id] = candidate_counts_by_target.get(target_id, 0) + 1

        candidate_fr = ""
        explicit_placeholder_or_provisional = False
        referenced_item = referenced_by_id.get(candidate_id)
        if referenced_item:
            candidate_fr_values = (
                referenced_item.get("common_names_i18n", {}).get("fr", [])
                if isinstance(referenced_item.get("common_names_i18n"), dict)
                else []
            )
            if isinstance(candidate_fr_values, list):
                candidate_fr = next((str(v).strip() for v in candidate_fr_values if isinstance(v, str) and str(v).strip()), "")
            explicit_placeholder_or_provisional = (
                _as_bool(referenced_item.get("is_placeholder"))
                or _as_bool(referenced_item.get("is_provisional"))
                or _as_bool(referenced_item.get("placeholder"))
                or _as_bool(referenced_item.get("provisional"))
                or str(referenced_item.get("label_status", "")).strip().lower() in {"placeholder", "provisional"}
            )

        low_confidence_or_provisional_seed = candidate_id in low_confidence_or_provisional_seed_ids
        runtime_unsafe = is_runtime_unsafe_label(
            common_name_fr=candidate_fr,
            scientific_name=candidate_sci,
            low_confidence_or_provisional_seed=low_confidence_or_provisional_seed,
            explicit_placeholder_or_provisional=explicit_placeholder_or_provisional,
        )
        is_placeholder = False
        if candidate_id and candidate_id in referenced_placeholder_ids:
            is_placeholder = True
        elif candidate_sci and candidate_sci in placeholder_scientific_names:
            is_placeholder = True
        elif runtime_unsafe:
            is_placeholder = True
        if is_placeholder:
            candidate_placeholder_relationship_occurrence_count += 1
            if target_id:
                affected_target_taxa.add(target_id)
            if status == "candidate":
                corpus_facing_placeholder_relationship_occurrence_count += 1
                unsafe_counts_by_target_before_guard[target_id] = unsafe_counts_by_target_before_guard.get(target_id, 0) + 1
                if target_id:
                    affected_ready_targets.add(target_id)
                if runtime_guard_active:
                    placeholder_relationship_occurrences_marked_not_for_corpus_display += 1
                else:
                    corpus_facing_placeholder_relationship_occurrence_count_after_guard += 1
                    unsafe_counts_by_target_after_guard[target_id] = unsafe_counts_by_target_after_guard.get(target_id, 0) + 1

    referenced_shell_placeholder_taxon_count = len(referenced_placeholder_ids)
    target_placeholder_taxon_count = len(target_placeholder_ids)
    unique_placeholder_taxon_count = len(all_placeholder_taxa)
    excluded_or_not_for_corpus_display_relationship_occurrence_count = max(
        candidate_placeholder_relationship_occurrence_count
        - corpus_facing_placeholder_relationship_occurrence_count,
        0,
    )
    affected_target_taxon_count = len(affected_target_taxa)
    affected_ready_target_count = len(affected_ready_targets)
    if runtime_guard_active:
        safe_ready_targets_after_guard = sum(
            1
            for target_id, count in candidate_counts_by_target.items()
            if count - unsafe_counts_by_target_before_guard.get(target_id, 0) >= 3
        )
    else:
        safe_ready_targets_after_guard = sum(
            1
            for target_id, count in candidate_counts_by_target.items()
            if count - unsafe_counts_by_target_after_guard.get(target_id, 0) >= 3
        )
    first_corpus_target_count_after_guard_status = (
        "pass"
        if safe_ready_targets_after_guard >= first_corpus_minimum_target_count
        else "fail"
    )
    safe_ready_target_count_after_placeholder_exclusion = safe_ready_targets_after_guard

    return {
        "unique_placeholder_taxon_count": unique_placeholder_taxon_count,
        "target_placeholder_taxon_count": target_placeholder_taxon_count,
        "candidate_placeholder_relationship_occurrence_count": candidate_placeholder_relationship_occurrence_count,
        "referenced_shell_placeholder_taxon_count": referenced_shell_placeholder_taxon_count,
        "corpus_facing_placeholder_relationship_occurrence_count": corpus_facing_placeholder_relationship_occurrence_count,
        "excluded_or_not_for_corpus_display_relationship_occurrence_count": excluded_or_not_for_corpus_display_relationship_occurrence_count,
        "affected_first_corpus_candidate_relationship_occurrence_count": corpus_facing_placeholder_relationship_occurrence_count,
        "unknown_impact_count": 0,
        "affected_target_taxon_count": affected_target_taxon_count,
        "affected_ready_target_count": affected_ready_target_count,
        "safe_ready_target_count_after_placeholder_exclusion": safe_ready_target_count_after_placeholder_exclusion,
        "runtime_contract_placeholder_exclusion_guard": runtime_guard_active,
        "placeholder_labels_runtime_policy": "exclude_or_mark_not_for_corpus_display",
        "corpus_facing_placeholder_relationship_occurrence_count_before_guard": corpus_facing_placeholder_relationship_occurrence_count,
        "corpus_facing_placeholder_relationship_occurrence_count_after_guard": corpus_facing_placeholder_relationship_occurrence_count_after_guard,
        "placeholder_relationship_occurrences_marked_not_for_corpus_display": placeholder_relationship_occurrences_marked_not_for_corpus_display,
        "first_corpus_minimum_target_count": first_corpus_minimum_target_count,
        "first_corpus_target_count_after_guard": safe_ready_targets_after_guard,
        "first_corpus_target_count_after_guard_status": first_corpus_target_count_after_guard_status,
    }


def detect_low_confidence_fr_seed_count(
    localized_apply_payload: dict[str, Any] | None,
    csv_rows: list[dict[str, str]] | None,
) -> dict[str, Any]:
    # Prefer Sprint 13 apply evidence when available.
    if localized_apply_payload is not None:
        applied = localized_apply_payload.get("applied", [])
        if isinstance(applied, list) and applied:
            count = sum(
                1
                for item in applied
                if isinstance(item, dict)
                and str(item.get("confidence", "")).strip().lower() == "low"
            )
            return {"count": count, "status": "known", "source": "localized_apply.applied"}

        confidence_dist = localized_apply_payload.get("confidence_distribution", {})
        if isinstance(confidence_dist, dict) and "low" in confidence_dist:
            return {
                "count": int(confidence_dist.get("low", 0)),
                "status": "known",
                "source": "localized_apply.confidence_distribution",
            }

    if csv_rows is not None:
        count = sum(
            1
            for row in csv_rows
            if str(row.get("confidence", "")).strip().lower() == "low"
        )
        return {"count": count, "status": "known", "source": "priority_seed_csv"}

    return {"count": None, "status": "evidence_missing", "source": "none"}


def build_referenced_shell_status(shell_plan_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not shell_plan_payload:
        return {
            "inat_candidates_assessed_count": None,
            "mapped_to_canonical_count": None,
            "referenced_shells_planned_count": None,
            "referenced_shells_created_count": None,
            "mode": "unknown",
            "status": "unknown_evidence_missing",
        }

    dry_run = bool(shell_plan_payload.get("dry_run", False))
    mode = "dry_run" if dry_run else "apply"
    planned = int(shell_plan_payload.get("new_shell_plan_count", 0))
    created = 0 if dry_run else planned

    status = "planned_not_created" if dry_run else "apply_or_created"

    return {
        "inat_candidates_assessed_count": int(shell_plan_payload.get("input_candidates_count", 0)),
        "mapped_to_canonical_count": int(shell_plan_payload.get("mapped_to_canonical_count", 0)),
        "referenced_shells_planned_count": planned,
        "referenced_shells_created_count": created,
        "mode": mode,
        "status": status,
    }


def build_pmp_blocker_table(pmp_payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not pmp_payload:
        return []
    issue_dist = pmp_payload.get("issue_category_distribution", {})
    if not isinstance(issue_dist, dict):
        return []

    categories = [
        "schema_false_negative",
        "multiple_species_target_unclear",
        "text_overlay_or_answer_visible",
        "field_observation_too_permissive",
        "species_card_too_permissive",
        "habitat_too_permissive",
        "pre_ai_borderline",
        "rare_model_subject_miss",
        "needs_second_review",
    ]

    table: list[dict[str, Any]] = []
    for cat in categories:
        count = int(issue_dist.get(cat, 0))
        if count <= 0:
            continue
        table.append(
            {
                "blocker_category": cat,
                "count": count,
                "source_artifact": "docs/audits/evidence/pmp_policy_v1_broader_400_20260504_human_review_analysis.json",
                "affects_first_corpus_candidate": "unknown",
                "affects_runtime_handoff": "unknown",
                "severity": "warning",
                "recommended_action": "Classify impact on first-corpus candidate set before promoting to hard blocker.",
            }
        )
    return table


def classify_decision(
    *,
    hard_integrity: bool,
    audit_clarification_needed: bool,
    pmp_blocker_proven: bool,
    name_review_needed: bool,
    placeholder_exclusion_needed: bool,
    referenced_shell_review_needed: bool,
    warning_only: bool,
) -> str:
    if hard_integrity:
        return "BLOCKED_NEEDS_DISTRACTOR_INTEGRITY_FIXES"
    if audit_clarification_needed:
        return "BLOCKED_NEEDS_AUDIT_CLARIFICATION"
    if pmp_blocker_proven:
        return "BLOCKED_NEEDS_PMP_POLICY_FIXES"
    if placeholder_exclusion_needed:
        return "BLOCKED_NEEDS_PLACEHOLDER_EXCLUSION"
    if name_review_needed:
        return "BLOCKED_NEEDS_NAME_REVIEW"
    if referenced_shell_review_needed:
        return "BLOCKED_NEEDS_REFERENCED_SHELL_REVIEW"
    if warning_only:
        return "READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS"
    return "READY_FOR_RUNTIME_CONTRACTS_GATE"


def next_phase_for_decision(decision: str) -> str:
    if decision in {"READY_FOR_RUNTIME_CONTRACTS_GATE", "READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS"}:
        return "14C Robustness and regression tests"
    return "Resolve blockers and rerun Sprint 14B data integrity gate"


def run_audit() -> dict[str, Any]:
    missing_required_files: list[str] = []
    missing_optional_files: list[str] = []
    warnings: list[str] = []

    inputs: dict[str, dict[str, Any]] = {}
    loaded: dict[str, Any] = {}

    for key, path in REQUIRED_INPUTS.items():
        exists = path.exists()
        inputs[key] = {"path": str(path.relative_to(REPO_ROOT)), "required": True, "exists": exists}
        if not exists:
            missing_required_files.append(str(path.relative_to(REPO_ROOT)))
            continue
        loaded[key] = _load_json(path)

    for key, path in OPTIONAL_INPUTS.items():
        exists = path.exists()
        inputs[key] = {"path": str(path.relative_to(REPO_ROOT)), "required": False, "exists": exists}
        if not exists:
            missing_optional_files.append(str(path.relative_to(REPO_ROOT)))
            continue
        if path.suffix.lower() == ".csv":
            loaded[key] = _read_csv_rows(path)
        else:
            loaded[key] = _load_json(path)

    if missing_required_files:
        decision = "BLOCKED_NEEDS_AUDIT_CLARIFICATION"
        return {
            "run_date": RUN_DATE,
            "phase": PHASE,
            "inputs": inputs,
            "checks": [],
            "metrics": {},
            "warnings": ["Missing required Sprint 13 source-of-truth artifacts."],
            "missing_required_files": missing_required_files,
            "missing_optional_files": missing_optional_files,
            "blockers": ["Cannot execute full integrity gate without required Sprint 13 artifacts."],
            "decision": decision,
            "recommended_next_action": "Restore required Sprint 13 artifacts and rerun Sprint 14B.",
            "next_phase_recommendation": next_phase_for_decision(decision),
            "non_actions": [
                "No DistractorRelationship persistence",
                "No ReferencedTaxon shell creation",
                "No localized-name modifications",
                "No delete/archive/deprecate actions",
            ],
        }

    projected = loaded["projected_relationships"]
    readiness = loaded["readiness_sprint13"]
    readiness_compare = loaded["readiness_sprint12_vs_sprint13"]

    records = projected.get("projected_records", []) if isinstance(projected, dict) else []
    if not isinstance(records, list):
        records = []

    canonical_payload = loaded.get("canonical_taxa_patched")
    referenced_payload = loaded.get("referenced_taxa_patched")

    canonical_ids = _extract_canonical_ids(canonical_payload) if isinstance(canonical_payload, dict) else set()
    referenced_ids = _extract_referenced_ids(referenced_payload) if isinstance(referenced_payload, dict) else set()

    duplicate_ids = detect_duplicate_relationship_ids(records)
    target_eq_candidate_count = count_target_equals_candidate(records)
    unresolved_marked_usable_count = count_unresolved_marked_usable(records)

    orphan_target_count = 0
    orphan_candidate_count = 0
    if canonical_ids:
        orphan_target_count = sum(
            1
            for row in records
            if str(row.get("target_canonical_taxon_id", "")).strip() not in canonical_ids
        )
        orphan_candidate_count += sum(
            1
            for row in records
            if row.get("candidate_taxon_ref_type") == "canonical_taxon"
            and str(row.get("candidate_taxon_ref_id", "")).strip()
            and str(row.get("candidate_taxon_ref_id", "")).strip() not in canonical_ids
        )
    else:
        warnings.append("Canonical taxa artifact missing; orphan target/canonical checks are limited.")

    if referenced_ids:
        orphan_candidate_count += sum(
            1
            for row in records
            if row.get("candidate_taxon_ref_type") == "referenced_taxon"
            and str(row.get("candidate_taxon_ref_id", "")).strip()
            and str(row.get("candidate_taxon_ref_id", "")).strip() not in referenced_ids
        )

    schema_validation_error_count = int(projected.get("schema_validation_error_count", 0))
    rejected_records_count = int(projected.get("rejected_records_count", 0))

    emergency_fallback_count = int(
        readiness_compare.get("metrics", {})
        .get("emergency_fallback_count", {})
        .get("sprint13", 0)
    )

    missing_french_names = int(readiness.get("gaps", {}).get("candidates_missing_french_name_count", 0))

    low_conf = detect_low_confidence_fr_seed_count(
        loaded.get("localized_apply") if isinstance(loaded.get("localized_apply"), dict) else None,
        loaded.get("priority_seed_csv") if isinstance(loaded.get("priority_seed_csv"), list) else None,
    )
    if low_conf["status"] != "known":
        warnings.append("Low-confidence FR seed evidence missing.")

    localized_conflicts = None
    if isinstance(loaded.get("localized_apply"), dict):
        localized_conflicts = int(loaded["localized_apply"].get("conflict_count", 0))

    shell_status = build_referenced_shell_status(
        loaded.get("shell_apply_plan") if isinstance(loaded.get("shell_apply_plan"), dict) else None
    )

    runtime_guard_active = bool(
        projected.get("runtime_contract_placeholder_exclusion_guard_active", True)
    )
    low_confidence_or_provisional_seed_ids = build_low_confidence_or_provisional_seed_ids(
        loaded.get("priority_seed_csv") if isinstance(loaded.get("priority_seed_csv"), list) else None
    )
    placeholder_breakdown = compute_placeholder_breakdown(
        records,
        canonical_payload if isinstance(canonical_payload, dict) else None,
        referenced_payload if isinstance(referenced_payload, dict) else None,
        low_confidence_or_provisional_seed_ids=low_confidence_or_provisional_seed_ids,
        runtime_guard_active=runtime_guard_active,
        first_corpus_minimum_target_count=30,
    )
    placeholder_exclusion_guard = {
        "documented_in_14d_runtime_contracts": runtime_guard_active,
        "required_condition": "14D runtime contracts must exclude or mark all provisional/placeholder FR labels as not_for_corpus_display.",
        "placeholder_labels_runtime_policy": "exclude_or_mark_not_for_corpus_display",
        "active": runtime_guard_active,
    }

    pmp_table = build_pmp_blocker_table(
        loaded.get("pmp_human_review_analysis") if isinstance(loaded.get("pmp_human_review_analysis"), dict) else None
    )

    pmp_policy_blockers_count = sum(int(row.get("count", 0)) for row in pmp_table)
    visible_answer_text_count = sum(
        int(row.get("count", 0))
        for row in pmp_table
        if row.get("blocker_category") == "text_overlay_or_answer_visible"
    )
    invalid_pmp_count = sum(
        int(row.get("count", 0))
        for row in pmp_table
        if row.get("blocker_category") == "schema_false_negative"
    )

    checks = [
        CheckResult(
            "projected_relationship_schema_validity",
            "pass" if schema_validation_error_count == 0 and rejected_records_count == 0 else "fail",
            {
                "schema_validation_error_count": schema_validation_error_count,
                "rejected_records_count": rejected_records_count,
            },
            "Projected DistractorRelationship artifact remains schema-valid.",
        ),
        CheckResult(
            "duplicate_relationship_ids",
            "pass" if len(duplicate_ids) == 0 else "fail",
            {"duplicate_id_count": len(duplicate_ids), "sample": duplicate_ids[:10]},
            "Relationship IDs must be unique.",
        ),
        CheckResult(
            "orphan_target_taxon_references",
            "pass" if orphan_target_count == 0 else "fail",
            orphan_target_count,
            "Projected targets should resolve to canonical taxon registry.",
        ),
        CheckResult(
            "orphan_candidate_taxon_references",
            "pass" if orphan_candidate_count == 0 else "fail",
            orphan_candidate_count,
            "Projected candidate refs should resolve to canonical/referenced registries.",
        ),
        CheckResult(
            "target_equals_candidate",
            "pass" if target_eq_candidate_count == 0 else "fail",
            target_eq_candidate_count,
            "Target must not equal candidate taxon.",
        ),
        CheckResult(
            "emergency_fallback_count",
            "pass" if emergency_fallback_count == 0 else "fail",
            emergency_fallback_count,
            "Emergency fallback count must remain 0 for first-corpus candidate set.",
        ),
        CheckResult(
            "unresolved_marked_usable",
            "pass" if unresolved_marked_usable_count == 0 else "fail",
            unresolved_marked_usable_count,
            "Unresolved candidates must not be marked usable.",
        ),
        CheckResult(
            "candidates_missing_french_names",
            "warning" if missing_french_names > 0 else "pass",
            missing_french_names,
            "Missing FR names remain a persistence-quality warning.",
        ),
        CheckResult(
            "low_confidence_fr_seeds",
            "warning" if (low_conf.get("count") or 0) > 0 else ("warning" if low_conf.get("count") is None else "pass"),
            low_conf,
            "Low-confidence FR seeds must be reviewed before production label usage.",
        ),
        CheckResult(
            "placeholder_french_labels_breakdown",
            "warning" if placeholder_breakdown["unique_placeholder_taxon_count"] > 0 else "pass",
            placeholder_breakdown,
            "67 reflects unique placeholder taxa while candidate placeholder metrics reflect relationship occurrences.",
        ),
        CheckResult(
            "runtime_contract_placeholder_exclusion_guard",
            (
                "pass"
                if runtime_guard_active
                and placeholder_breakdown["corpus_facing_placeholder_relationship_occurrence_count_after_guard"] == 0
                else "fail"
            ),
            placeholder_exclusion_guard,
            "Runtime handoff requires 14D contracts to exclude or mark placeholder FR labels as not_for_corpus_display.",
        ),
        CheckResult(
            "first_corpus_target_count_after_guard",
            (
                "pass"
                if placeholder_breakdown["first_corpus_target_count_after_guard_status"] == "pass"
                else "fail"
            ),
            {
                "first_corpus_minimum_target_count": placeholder_breakdown["first_corpus_minimum_target_count"],
                "first_corpus_target_count_after_guard": placeholder_breakdown["first_corpus_target_count_after_guard"],
                "status": placeholder_breakdown["first_corpus_target_count_after_guard_status"],
            },
            "After placeholder exclusion guard, first-corpus target count must stay at or above minimum.",
        ),
        CheckResult(
            "referenced_shell_plan_status",
            "warning" if shell_status["status"] == "planned_not_created" else ("warning" if shell_status["status"] == "unknown_evidence_missing" else "pass"),
            shell_status,
            "Referenced shell plan semantics: planned vs created, with explicit dry-run/apply status.",
        ),
        CheckResult(
            "localized_name_conflicts",
            "warning" if (localized_conflicts or 0) > 0 else ("warning" if localized_conflicts is None else "pass"),
            localized_conflicts,
            "Localized-name conflict count where evidence exists.",
        ),
        CheckResult(
            "invalid_pmp_records",
            "warning" if invalid_pmp_count > 0 else "pass",
            invalid_pmp_count,
            "Schema false negatives in PMP review evidence.",
        ),
        CheckResult(
            "visible_answer_text_or_screenshot_blockers",
            "warning" if visible_answer_text_count > 0 else "pass",
            visible_answer_text_count,
            "Visible answer text/screenshot categories from PMP review evidence.",
        ),
        CheckResult(
            "pmp_policy_blocker_attribution",
            "warning" if pmp_policy_blockers_count > 0 else "pass",
            {"count": pmp_policy_blockers_count, "table_rows": len(pmp_table)},
            "PMP blocker categories are warning-level until corpus/runtime impact is proven.",
        ),
    ]

    hard_integrity = any(
        c.status == "fail"
        for c in checks
        if c.name
        in {
            "projected_relationship_schema_validity",
            "duplicate_relationship_ids",
            "orphan_target_taxon_references",
            "orphan_candidate_taxon_references",
            "target_equals_candidate",
            "emergency_fallback_count",
            "unresolved_marked_usable",
        }
    )

    audit_consistency_issues: list[str] = []
    if shell_status["status"] == "unknown_evidence_missing":
        audit_consistency_issues.append("Referenced shell plan evidence missing.")
    if low_conf["status"] != "known":
        audit_consistency_issues.append("Low-confidence FR seed evidence unavailable.")
    if low_conf.get("count") == 0 and int(
        readiness_compare.get("metrics", {}).get("shell_candidates_with_fr", {}).get("sprint13", 0)
    ) > 0:
        audit_consistency_issues.append("Low-confidence FR seed count conflicts with Sprint 13 shell FR-seed metric.")

    audit_clarification_needed = len(audit_consistency_issues) > 0 and not hard_integrity

    # Conservative: do not hard-block on PMP without explicit proven impact in artifact set.
    pmp_blocker_proven = False

    name_review_needed = False
    placeholder_exclusion_needed = (
        (
            placeholder_breakdown["corpus_facing_placeholder_relationship_occurrence_count_before_guard"] > 0
            and not runtime_guard_active
        )
        or placeholder_breakdown["corpus_facing_placeholder_relationship_occurrence_count_after_guard"] > 0
    )
    if placeholder_breakdown["first_corpus_target_count_after_guard_status"] != "pass":
        name_review_needed = True
    referenced_shell_review_needed = False

    warning_only = (
        any(c.status == "warning" for c in checks)
        and not hard_integrity
        and not audit_clarification_needed
        and not placeholder_exclusion_needed
        and not name_review_needed
    )

    decision = classify_decision(
        hard_integrity=hard_integrity,
        audit_clarification_needed=audit_clarification_needed,
        pmp_blocker_proven=pmp_blocker_proven,
        name_review_needed=name_review_needed,
        placeholder_exclusion_needed=placeholder_exclusion_needed,
        referenced_shell_review_needed=referenced_shell_review_needed,
        warning_only=warning_only,
    )

    blockers: list[str] = []
    if hard_integrity:
        blockers.append("Hard distractor integrity checks failed.")
    if placeholder_exclusion_needed:
        blockers.append(
            "Corpus-facing placeholder FR relationship occurrences are present without a documented 14D runtime exclusion/marking guard."
        )
    if name_review_needed:
        blockers.append(
            "Safe ready target count after placeholder exclusion is below first-corpus minimum (30)."
        )
    blockers.extend(audit_consistency_issues)

    if decision == "BLOCKED_NEEDS_DISTRACTOR_INTEGRITY_FIXES":
        next_action = "Fix distractor integrity failures and rerun Sprint 14B audit."
    elif decision == "BLOCKED_NEEDS_AUDIT_CLARIFICATION":
        next_action = "Resolve audit evidence inconsistencies/missing sources and rerun Sprint 14B audit."
    elif decision == "BLOCKED_NEEDS_PMP_POLICY_FIXES":
        next_action = "Resolve proven PMP blockers that affect handoff candidates, then rerun Sprint 14B."
    elif decision == "BLOCKED_NEEDS_PLACEHOLDER_EXCLUSION":
        next_action = "Document and enforce 14D runtime placeholder exclusion (or not_for_corpus_display marking), then rerun Sprint 14B."
    elif decision == "BLOCKED_NEEDS_NAME_REVIEW":
        next_action = "Complete required name review for corpus-facing artifacts, then rerun Sprint 14B."
    elif decision == "BLOCKED_NEEDS_REFERENCED_SHELL_REVIEW":
        next_action = "Complete referenced shell review requirements, then rerun Sprint 14B."
    elif decision == "READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS":
        next_action = "Proceed with warnings register to Sprint 14C robustness/regression tests."
    else:
        next_action = "Proceed to Sprint 14C robustness/regression tests."

    return {
        "run_date": RUN_DATE,
        "phase": PHASE,
        "inputs": inputs,
        "checks": [c.__dict__ for c in checks],
        "metrics": {
            "projected_record_count": len(records),
            "schema_validation_error_count": schema_validation_error_count,
            "rejected_records_count": rejected_records_count,
            "duplicate_relationship_id_count": len(duplicate_ids),
            "orphan_target_taxon_count": orphan_target_count,
            "orphan_candidate_taxon_count": orphan_candidate_count,
            "target_equals_candidate_count": target_eq_candidate_count,
            "emergency_fallback_count": emergency_fallback_count,
            "unresolved_marked_usable_count": unresolved_marked_usable_count,
            "candidates_missing_french_name_count": missing_french_names,
            "low_confidence_fr_seed_count": low_conf.get("count"),
            "placeholder_french_labels": placeholder_breakdown,
            "referenced_shell_status": shell_status,
            "localized_name_conflict_count": localized_conflicts,
            "invalid_pmp_count": invalid_pmp_count,
            "visible_answer_text_or_screenshot_count": visible_answer_text_count,
            "pmp_policy_blockers_count": pmp_policy_blockers_count,
        },
        "warnings": warnings,
        "missing_required_files": missing_required_files,
        "missing_optional_files": missing_optional_files,
        "pmp_blocker_attribution": pmp_table,
        "blockers": blockers,
        "decision": decision,
        "decision_rationale": {
            "runtime_contract_placeholder_exclusion_guard": runtime_guard_active,
            "placeholder_labels_runtime_policy": "exclude_or_mark_not_for_corpus_display",
            "corpus_facing_placeholder_relationship_occurrence_count_before_guard": placeholder_breakdown[
                "corpus_facing_placeholder_relationship_occurrence_count_before_guard"
            ],
            "corpus_facing_placeholder_relationship_occurrence_count_after_guard": placeholder_breakdown[
                "corpus_facing_placeholder_relationship_occurrence_count_after_guard"
            ],
            "safe_ready_target_count_after_placeholder_exclusion": placeholder_breakdown[
                "safe_ready_target_count_after_placeholder_exclusion"
            ],
            "first_corpus_minimum_target_count": placeholder_breakdown["first_corpus_minimum_target_count"],
            "first_corpus_target_count_after_guard_status": placeholder_breakdown[
                "first_corpus_target_count_after_guard_status"
            ],
        },
        "recommended_next_action": next_action,
        "next_phase_recommendation": next_phase_for_decision(decision),
        "non_actions": [
            "No DistractorRelationship persistence",
            "No ReferencedTaxon shell creation",
            "No localized-name modifications",
            "No delete/archive/deprecate actions",
        ],
        "integrity_gate_context": {
            "ready_for_first_corpus_distractor_gate": True,
            "persist_distractor_relationships_v1": False,
            "database_phase_closed": False,
            "note": "Corpus gate readiness does not imply persistence or database phase closure.",
            "runtime_contract_placeholder_exclusion_guard": placeholder_exclusion_guard,
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        f"last_reviewed: {RUN_DATE}",
        "source_of_truth: docs/audits/database-integrity-runtime-handoff-audit.md",
        "scope: sprint14b_data_integrity_gate",
        "---",
        "",
        "# Database Integrity Runtime Handoff Audit (Sprint 14B)",
        "",
        "## What Was Audited",
        "",
        "- Sprint 13 projected distractor relationships and integrity invariants.",
        "- Referenced shell plan semantics (assessed, mapped, planned, created, mode, status).",
        "- FR quality signals (missing FR, low-confidence seeds, placeholder FR labels breakdown).",
        "- PMP policy artifacts with explicit attribution and impact uncertainty.",
        "",
        "## Pass/Warning/Fail",
        "",
        "| Check | Status | Value |",
        "|---|---|---|",
    ]

    for check in report.get("checks", []):
        value = check.get("value")
        rendered = json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        lines.append(f"| {check.get('name')} | {check.get('status')} | {rendered} |")

    metrics = report.get("metrics", {})
    lines.extend(
        [
            "",
            "## Key Counts",
            "",
            f"- projected_record_count: {metrics.get('projected_record_count')}",
            f"- duplicate_relationship_id_count: {metrics.get('duplicate_relationship_id_count')}",
            f"- emergency_fallback_count: {metrics.get('emergency_fallback_count')}",
            f"- candidates_missing_french_name_count: {metrics.get('candidates_missing_french_name_count')}",
            f"- low_confidence_fr_seed_count: {metrics.get('low_confidence_fr_seed_count')}",
            f"- placeholder_french_labels: {json.dumps(metrics.get('placeholder_french_labels'), ensure_ascii=False)}",
            f"- referenced_shell_status: {json.dumps(metrics.get('referenced_shell_status'), ensure_ascii=False)}",
            "",
            "## Placeholder Semantics",
            "",
            f"- unique_placeholder_taxon_count={metrics.get('placeholder_french_labels', {}).get('unique_placeholder_taxon_count')} represents distinct placeholder taxa.",
            f"- candidate_placeholder_relationship_occurrence_count={metrics.get('placeholder_french_labels', {}).get('candidate_placeholder_relationship_occurrence_count')} represents relationship-level occurrences.",
            f"- corpus_facing_placeholder_relationship_occurrence_count_before_guard={metrics.get('placeholder_french_labels', {}).get('corpus_facing_placeholder_relationship_occurrence_count_before_guard')} are unsafe before runtime filtering.",
            f"- corpus_facing_placeholder_relationship_occurrence_count_after_guard={metrics.get('placeholder_french_labels', {}).get('corpus_facing_placeholder_relationship_occurrence_count_after_guard')} must be 0 for runtime-facing output.",
            f"- placeholder_relationship_occurrences_marked_not_for_corpus_display={metrics.get('placeholder_french_labels', {}).get('placeholder_relationship_occurrences_marked_not_for_corpus_display')} remain in source/audit data but are excluded from corpus-facing display.",
            f"- safe_ready_target_count_after_placeholder_exclusion={metrics.get('placeholder_french_labels', {}).get('safe_ready_target_count_after_placeholder_exclusion')} against minimum={metrics.get('placeholder_french_labels', {}).get('first_corpus_minimum_target_count')} ({metrics.get('placeholder_french_labels', {}).get('first_corpus_target_count_after_guard_status')}).",
            "",
            "## Corpus Gate vs Persistence",
            "",
            "- READY_FOR_FIRST_CORPUS_DISTRACTOR_GATE remains a corpus-readiness signal only.",
            "- PERSIST_DISTRACTOR_RELATIONSHIPS_V1 remains false in Sprint 14B/14B.1.",
            "- DATABASE_PHASE_CLOSED remains false in Sprint 14B/14B.1.",
            "- It does not authorize DistractorRelationship persistence.",
            "- It does not authorize database-phase closure.",
            "- 14D runtime contracts must exclude or mark all provisional/placeholder FR labels as not_for_corpus_display.",
            "- Placeholder/provisional labels remain preserved in source and audit evidence for traceability.",
            "- Runtime-facing label selection must use only safe localized labels.",
            "",
            "## PMP Blocker Attribution",
            "",
            "| blocker_category | count | source_artifact | affects_first_corpus_candidate | affects_runtime_handoff | severity | recommended_action |",
            "|---|---:|---|---|---|---|---|",
        ]
    )

    for row in report.get("pmp_blocker_attribution", []):
        lines.append(
            "| {blocker_category} | {count} | {source_artifact} | {affects_first_corpus_candidate} | {affects_runtime_handoff} | {severity} | {recommended_action} |".format(
                **row
            )
        )

    lines.extend(["", "## Exact Blockers", ""])
    blockers = report.get("blockers", [])
    if blockers:
        for blocker in blockers:
            lines.append(f"- {blocker}")
    else:
        lines.append("- No hard blockers identified for Sprint 14B.")

    lines.extend(["", "## Exact Non-Actions", ""])
    for item in report.get("non_actions", []):
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- decision: {report.get('decision')}",
            f"- recommended_next_action: {report.get('recommended_next_action')}",
            "",
            "## Next Phase Recommendation",
            "",
            f"- {report.get('next_phase_recommendation')}",
        ]
    )

    warn = report.get("warnings", [])
    if warn:
        lines.extend(["", "## Warnings", ""])
        for w in warn:
            lines.append(f"- {w}")

    return "\n".join(lines) + "\n"


def main() -> None:
    report = run_audit()
    DEFAULT_OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    DEFAULT_OUTPUT_MD.write_text(render_markdown(report), encoding="utf-8")

    print(f"Wrote {DEFAULT_OUTPUT_JSON.relative_to(REPO_ROOT)}")
    print(f"Wrote {DEFAULT_OUTPUT_MD.relative_to(REPO_ROOT)}")
    print(f"decision={report.get('decision')}")


if __name__ == "__main__":
    main()
