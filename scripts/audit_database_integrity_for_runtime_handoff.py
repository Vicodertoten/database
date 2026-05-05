from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from database_core.enrichment.localized_names import (  # noqa: E402
    build_localized_name_apply_plan,
    write_plan_artifacts,
)

RUN_DATE = "2026-05-05"
PHASE = "Sprint 14B.3"
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "docs" / "audits" / "evidence" / "database_integrity_runtime_handoff_audit.json"
)
DEFAULT_OUTPUT_MD = REPO_ROOT / "docs" / "audits" / "database-integrity-runtime-handoff-audit.md"
POLICY_DOC = "docs/foundation/localized-name-source-policy-v1.md"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    value: Any
    detail: str


def classify_decision(
    *,
    hard_integrity: bool,
    source_attested_policy_enabled: bool,
    runtime_facing_unsafe_labels: bool,
    safe_ready_target_count_after_source_attested_policy: int,
    first_corpus_minimum_target_count: int,
    needs_review_conflict_count: int,
    not_displayable_missing_count: int,
) -> str:
    if hard_integrity:
        return "BLOCKED_NEEDS_DISTRACTOR_INTEGRITY_FIXES"
    if not source_attested_policy_enabled:
        return "BLOCKED_NEEDS_NAME_POLICY"
    if runtime_facing_unsafe_labels:
        return "BLOCKED_NEEDS_PLACEHOLDER_EXCLUSION"
    if safe_ready_target_count_after_source_attested_policy >= first_corpus_minimum_target_count:
        return "READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS"
    if needs_review_conflict_count > 0:
        return "BLOCKED_NEEDS_NAME_CONFLICT_REVIEW"
    if not_displayable_missing_count > 0:
        return "BLOCKED_NEEDS_NAME_SOURCE_ENRICHMENT"
    return "BLOCKED_NEEDS_NAME_SOURCE_ENRICHMENT"


def next_phase_for_decision(decision: str) -> str:
    if decision == "READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS":
        return "14C Robustness and regression tests"
    if decision == "BLOCKED_NEEDS_NAME_CONFLICT_REVIEW":
        return "Resolve localized-name conflicts then rerun Sprint 14B"
    if decision == "BLOCKED_NEEDS_NAME_SOURCE_ENRICHMENT":
        return "Add missing source-attested localized names then rerun Sprint 14B"
    if decision == "BLOCKED_NEEDS_NAME_POLICY":
        return "Document and enable localized-name source policy then rerun Sprint 14B"
    if decision == "BLOCKED_NEEDS_PLACEHOLDER_EXCLUSION":
        return "Remove runtime-facing placeholder/scientific-fallback labels then rerun Sprint 14B"
    return "Fix integrity blockers then rerun Sprint 14B"


def run_audit(
    output_json: Path = DEFAULT_OUTPUT_JSON, output_md: Path = DEFAULT_OUTPUT_MD
) -> dict[str, Any]:
    plan = build_localized_name_apply_plan(REPO_ROOT)
    write_plan_artifacts(plan, REPO_ROOT)

    item_decisions = Counter(item.decision for item in plan.items if item.locale == "fr")
    item_reasons = Counter(item.reason for item in plan.items if item.locale == "fr")
    required_review_reasons = Counter(item.reason for item in plan.review_items_required)

    displayable_source_attested_label_count = item_decisions.get("auto_accept", 0)
    displayable_curated_label_count = item_decisions.get("same_value", 0)
    not_displayable_missing_count = required_review_reasons.get("missing_required_locale", 0)
    not_displayable_scientific_fallback_count = required_review_reasons.get(
        "scientific_fallback", 0
    )
    not_displayable_placeholder_count = required_review_reasons.get("source_low_confidence", 0)
    needs_review_conflict_count = sum(
        count
        for reason, count in required_review_reasons.items()
        if reason.startswith("existing_value_conflict")
    )
    runtime_facing_unsafe_labels = any(
        item.reason in {"scientific_fallback", "source_ambiguous"}
        for item in plan.review_items_required
    )

    safe_ready_targets = int(plan.metrics["safe_ready_target_count_from_plan"])
    first_corpus_minimum_target_count = int(plan.metrics["first_corpus_minimum_target_count"])
    source_attested_display_policy_enabled = Path(REPO_ROOT / POLICY_DOC).exists()

    decision = classify_decision(
        hard_integrity=False,
        source_attested_policy_enabled=source_attested_display_policy_enabled,
        runtime_facing_unsafe_labels=runtime_facing_unsafe_labels,
        safe_ready_target_count_after_source_attested_policy=safe_ready_targets,
        first_corpus_minimum_target_count=first_corpus_minimum_target_count,
        needs_review_conflict_count=needs_review_conflict_count,
        not_displayable_missing_count=not_displayable_missing_count,
    )

    warnings = [
        "Source-attested names not human-reviewed remain warning-level for MVP display.",
        "Runtime must display only auto_accept/same_value localized-name apply-plan decisions.",
        "Runtime must not invent/fetch localized names.",
    ]

    payload = {
        "run_date": RUN_DATE,
        "phase": PHASE,
        "decision": decision,
        "localized_name_source_policy": POLICY_DOC,
        "localized_name_apply_plan": "docs/audits/evidence/localized_name_apply_plan_v1.json",
        "plan_hash": plan.plan_hash,
        "source_attested_display_policy_enabled": source_attested_display_policy_enabled,
        "displayable_source_attested_label_count": displayable_source_attested_label_count,
        "displayable_curated_label_count": displayable_curated_label_count,
        "non_human_reviewed_source_attested_label_count": displayable_source_attested_label_count,
        "not_displayable_missing_count": not_displayable_missing_count,
        "not_displayable_placeholder_count": not_displayable_placeholder_count,
        "not_displayable_scientific_fallback_count": not_displayable_scientific_fallback_count,
        "needs_review_conflict_count": needs_review_conflict_count,
        "safe_ready_target_count_after_source_attested_policy": safe_ready_targets,
        "first_corpus_minimum_target_count": first_corpus_minimum_target_count,
        "first_corpus_target_count_after_source_policy_status": (
            "pass" if safe_ready_targets >= first_corpus_minimum_target_count else "fail"
        ),
        "runtime_display_name_policy_warnings": warnings,
        "decision_count_by_reason_fr": dict(item_reasons),
        "non_actions": [
            "PERSIST_DISTRACTOR_RELATIONSHIPS_V1 remains false",
            "DATABASE_PHASE_CLOSED remains false",
            "No runtime app code created",
            "No invented names",
        ],
        "recommended_next_phase": next_phase_for_decision(decision),
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_markdown(output_md, payload)
    return payload


def _write_markdown(output_md: Path, payload: dict[str, Any]) -> None:
    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        "last_reviewed: 2026-05-05",
        "source_of_truth: docs/audits/database-integrity-runtime-handoff-audit.md",
        "scope: sprint14b_data_integrity_gate",
        "---",
        "",
        "# Database Integrity Runtime Handoff Audit (Sprint 14B)",
        "",
        f"- decision: {payload['decision']}",
        f"- plan_hash: {payload['plan_hash']}",
        "- source_attested_display_policy_enabled: "
        f"{str(payload['source_attested_display_policy_enabled']).lower()}",
        "- safe_ready_target_count_after_source_attested_policy: "
        f"{payload['safe_ready_target_count_after_source_attested_policy']}",
        f"- first_corpus_minimum_target_count: {payload['first_corpus_minimum_target_count']}",
        "",
        "Runtime readiness is derived from `localized_name_apply_plan_v1.json`; "
        "audit no longer recalculates displayability from CSV or patched snapshots.",
        "Runtime must not display placeholders/scientific fallbacks/conflicts "
        "and must not invent or fetch labels.",
        "",
        "## Key Counts",
        "",
        "- displayable_source_attested_label_count: "
        f"{payload['displayable_source_attested_label_count']}",
        f"- displayable_curated_label_count: {payload['displayable_curated_label_count']}",
        f"- not_displayable_missing_count: {payload['not_displayable_missing_count']}",
        f"- not_displayable_placeholder_count: {payload['not_displayable_placeholder_count']}",
        "- not_displayable_scientific_fallback_count: "
        f"{payload['not_displayable_scientific_fallback_count']}",
        f"- needs_review_conflict_count: {payload['needs_review_conflict_count']}",
        "",
        "## Exact Non-Actions",
        "",
        "- PERSIST_DISTRACTOR_RELATIONSHIPS_V1 remains false",
        "- DATABASE_PHASE_CLOSED remains false",
        "- No runtime app code created",
        "- No names invented",
        "",
        "## Next Phase Recommendation",
        "",
        f"- {payload['recommended_next_phase']}",
    ]
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    result = run_audit()
    print(f"Decision: {result['decision']}")
    print(f"Plan hash: {result['plan_hash']}")
    print(f"Safe ready targets: {result['safe_ready_target_count_after_source_attested_policy']}")


if __name__ == "__main__":
    main()
