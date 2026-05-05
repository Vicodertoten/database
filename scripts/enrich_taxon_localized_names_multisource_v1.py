from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from database_core.enrichment.localized_names import (  # noqa: E402,F401
    build_localized_name_apply_plan,
    is_empty_name,
    is_internal_placeholder,
    is_scientific_name_as_common_name,
    looks_like_latin_binomial,
    names_equivalent,
    normalize_compare_text,
    normalize_whitespace,
    write_backward_compatible_csvs,
    write_plan_artifacts,
)

RUN_DATE = "2026-05-05"
PHASE = "Sprint 14B.3"
POLICY_DOC = "docs/foundation/localized-name-source-policy-v1.md"
OUTPUT_JSON = (
    REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "taxon_localized_names_multisource_sprint14_dry_run.json"
)
OUTPUT_MD = REPO_ROOT / "docs" / "audits" / "taxon-localized-names-multisource-sprint14-dry-run.md"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def build_multisource_dry_run() -> dict[str, Any]:
    plan = build_localized_name_apply_plan(REPO_ROOT)
    write_plan_artifacts(plan, REPO_ROOT)
    write_backward_compatible_csvs(plan, REPO_ROOT)

    metrics = plan.metrics
    decision = (
        "READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS"
        if metrics["safe_ready_target_count_from_plan"]
        >= metrics["first_corpus_minimum_target_count"]
        else "BLOCKED_NEEDS_NAME_SOURCE_ENRICHMENT"
    )
    payload = {
        "run_date": RUN_DATE,
        "phase": PHASE,
        "policy_doc": POLICY_DOC,
        "plan_artifact": "docs/audits/evidence/localized_name_apply_plan_v1.json",
        "plan_hash": plan.plan_hash,
        "providers": ["inaturalist", "wikipedia", "wikidata"],
        "provider_status": {
            "inaturalist": "available_local_artifact_or_cache",
            "wikipedia": "offline_cache_only_unless_refreshed",
            "wikidata": "offline_cache_only_unless_refreshed",
        },
        "taxa_considered_count": len({(item.taxon_kind, item.taxon_id) for item in plan.items}),
        "candidate_names_by_language": metrics["by_locale"],
        "decision_count_by_type": metrics["by_decision"],
        "decision_count_by_reason": metrics["by_reason"],
        "projected_safe_ready_target_count_after_source_attested_names": metrics[
            "safe_ready_target_count_from_plan"
        ],
        "current_safe_ready_target_count_after_guard": metrics["safe_ready_target_count_from_plan"],
        "first_corpus_minimum_target_count": metrics["first_corpus_minimum_target_count"],
        "projected_decision": decision,
        "review_queue_required_count": len(plan.review_items_required),
        "optional_coverage_gap_count": len(plan.optional_coverage_gaps),
        "non_actions": [
            "No DistractorRelationship persistence",
            "No ReferencedTaxon shell creation",
            "No PMP/media score changes",
            "No runtime app code",
            "No invented names",
        ],
    }
    _write_json(OUTPUT_JSON, payload)
    _write_markdown(payload)
    return payload


def _write_markdown(payload: dict[str, Any]) -> None:
    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        "last_reviewed: 2026-05-05",
        "source_of_truth: docs/audits/taxon-localized-names-multisource-sprint14-dry-run.md",
        "scope: sprint14b_localized_names",
        "---",
        "",
        "# Taxon Localized Names Multisource Sprint 14 Dry Run",
        "",
        "Dry-run now delegates localized-name decisions to `LocalizedNameApplyPlan`.",
        "",
        f"- plan_hash: {payload['plan_hash']}",
        f"- plan_artifact: `{payload['plan_artifact']}`",
        "- projected safe ready targets: "
        f"{payload['projected_safe_ready_target_count_after_source_attested_names']} / "
        f"{payload['first_corpus_minimum_target_count']}",
        f"- projected decision: {payload['projected_decision']}",
        f"- required review items: {payload['review_queue_required_count']}",
        f"- optional coverage gaps: {payload['optional_coverage_gap_count']}",
        "",
        "## Non-Actions",
        "",
        "- No DistractorRelationship persistence",
        "- No ReferencedTaxon shell creation",
        "- No runtime app changes",
        "- No invented labels",
    ]
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    evidence = build_multisource_dry_run()
    print(f"Decision: {evidence['projected_decision']}")
    print(f"Plan hash: {evidence['plan_hash']}")
    print(
        "Projected safe-ready targets from apply plan: "
        f"{evidence['projected_safe_ready_target_count_after_source_attested_names']}"
    )


if __name__ == "__main__":
    main()
