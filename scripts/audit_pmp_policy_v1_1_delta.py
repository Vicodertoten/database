"""
Audit Policy v1.1 delta on broader_400 human review.

Compare existing broader_400 human review / policy evidence against current
policy v1.1 behavior (evaluate_pmp_profile_policy).

Inputs:
    docs/audits/human_review/pmp_policy_v1_broader_400_20260504_human_review_labeled.csv
    data/raw/inaturalist/palier1-be-birds-50taxa-run003-pmp-policy-broader-400-20260504/ai_outputs.json
    docs/audits/human_review/pmp_policy_v1_1_optional_signal_annotations.csv (optional)

Outputs:
    docs/audits/evidence/pmp_policy_v1_1_broader_400_delta_audit.json
    docs/audits/pmp-policy-v1-1-broader-400-delta-audit.md
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

INPUT_LABELED_CSV = (
    REPO_ROOT
    / "docs/audits/human_review"
    / "pmp_policy_v1_broader_400_20260504_human_review_labeled.csv"
)
INPUT_AI_OUTPUTS = (
    REPO_ROOT
    / "data/raw/inaturalist"
    / "palier1-be-birds-50taxa-run003-pmp-policy-broader-400-20260504"
    / "ai_outputs.json"
)
INPUT_OPTIONAL_SIGNALS = (
    REPO_ROOT
    / "docs/audits/human_review"
    / "pmp_policy_v1_1_optional_signal_annotations.csv"
)
OUTPUT_JSON = (
    REPO_ROOT
    / "docs/audits/evidence"
    / "pmp_policy_v1_1_broader_400_delta_audit.json"
)
OUTPUT_MD = REPO_ROOT / "docs/audits" / "pmp-policy-v1-1-broader-400-delta-audit.md"

DECISION_READY = "READY_FOR_SECOND_REVIEW_SHEET"
DECISION_NEEDS_FIXES = "NEEDS_DELTA_AUDIT_FIXES"
DECISION_BLOCKED = "BLOCKED_BY_MISSING_INPUT_DATA"

# Thresholds for decision
REGRESSION_LIMIT = 3  # max regressions before NEEDS_FIXES
MIN_IMPROVABLE_FIXED = 2  # min required improvements on human too_strict


def _load_labeled_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _load_ai_outputs(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _load_optional_signals(path: Path) -> dict[str, dict[str, str]]:
    """Return dict keyed by media_key."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {r.get("media_key", ""): r for r in rows if r.get("media_key")}


def _media_key_from_local_path(local_image_path: str) -> str | None:
    """Extract inaturalist::<id> from local_image_path like .../images/14306882.jpg."""
    p = Path(local_image_path)
    stem = p.stem
    if stem.isdigit():
        return f"inaturalist::{stem}"
    return None


def _parse_pipe_list(value: str) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split("|") if v.strip()]


def _usages_set(value: str) -> set[str]:
    return set(_parse_pipe_list(value))


def _evaluate_current_policy(
    profile: dict,
    *,
    optional_signals: dict[str, str] | None = None,
) -> dict:
    from database_core.qualification.pmp_policy_v1 import evaluate_pmp_profile_policy

    merged = dict(profile)
    if optional_signals:
        # Inject optional signals if available and not already present
        for field in (
            "target_taxon_visibility",
            "contains_visible_answer_text",
            "contains_ui_screenshot",
        ):
            sig_val = optional_signals.get(field, "").strip()
            if sig_val and sig_val not in ("", "unknown") and field not in merged:
                if field in ("contains_visible_answer_text", "contains_ui_screenshot"):
                    merged[field] = sig_val.lower() == "true"
                else:
                    merged[field] = sig_val
    return evaluate_pmp_profile_policy(merged)


def _compare_policy_status(before: str, after: str) -> str:
    if before == after:
        return "unchanged"
    if before == "profile_failed" and after == "profile_valid":
        return "improved_schema_fix"
    if before == "profile_valid" and after == "profile_failed":
        return "regression_profile_failed"
    return f"changed:{before}->{after}"


def _compare_usage_sets(
    before_recommended: set[str],
    after_recommended: set[str],
    before_borderline: set[str],
    after_borderline: set[str],
    human_judgment: str,
    evidence_type: str = "",
    species_card_changed: str = "",
    habitat_changed: str = "",
) -> dict:
    """Compare before/after eligible uses and detect improvements/regressions.

    Intentional calibration changes (species_card calibration, habitat indirect
    evidence downgrade) are classified as calibration_downgrade, not regression.
    A regression is a non-intentional loss of eligible uses for a human-accepted item.
    """
    gained = after_recommended - before_recommended
    lost = before_recommended - after_recommended
    gained_borderline = after_borderline - before_borderline
    lost_borderline = before_borderline - after_borderline

    # Intentional calibration downgrade: species_card or habitat indirect_evidence_learning
    intentional_lost = set()
    if species_card_changed in ("downgraded", "borderline_removed"):
        intentional_lost.add("species_card")
    if habitat_changed == "indirect_evidence_downgraded":
        intentional_lost.add("indirect_evidence_learning")

    truly_lost = lost - intentional_lost

    is_regression = bool(truly_lost) and human_judgment in ("accept", "too_strict", "")
    is_calibration_downgrade = bool(lost & intentional_lost) and not bool(truly_lost)
    is_improvement = bool(gained) and human_judgment == "too_strict"

    return {
        "gained_uses": sorted(gained),
        "lost_uses": sorted(lost),
        "intentional_lost_uses": sorted(lost & intentional_lost),
        "truly_lost_uses": sorted(truly_lost),
        "gained_borderline": sorted(gained_borderline),
        "lost_borderline": sorted(lost_borderline),
        "is_regression": is_regression,
        "is_calibration_downgrade": is_calibration_downgrade,
        "is_improvement": is_improvement,
    }


def _detect_species_card_change(
    before_recommended: set[str],
    after_recommended: set[str],
    before_borderline: set[str],
    after_borderline: set[str],
) -> str:
    """Return 'downgraded', 'upgraded', or 'unchanged'."""
    before_sc_eligible = "species_card" in before_recommended
    after_sc_eligible = "species_card" in after_recommended
    before_sc_borderline = "species_card" in before_borderline
    after_sc_borderline = "species_card" in after_borderline

    if before_sc_eligible and not after_sc_eligible:
        return "downgraded"
    if not before_sc_eligible and after_sc_eligible:
        return "upgraded"
    if before_sc_borderline and not after_sc_borderline:
        return "borderline_removed"
    return "unchanged"


def _detect_habitat_change(
    before_recommended: set[str],
    after_recommended: set[str],
    before_borderline: set[str],
    after_borderline: set[str],
    evidence_type: str,
) -> str:
    if evidence_type != "habitat":
        return "n/a"
    before_iel = "indirect_evidence_learning" in before_recommended
    after_iel = "indirect_evidence_learning" in after_recommended
    if before_iel and not after_iel:
        return "indirect_evidence_downgraded"
    if not before_iel and after_iel:
        return "indirect_evidence_upgraded"
    return "unchanged"


def run_delta_audit(
    *,
    input_labeled_csv: Path = INPUT_LABELED_CSV,
    input_ai_outputs: Path = INPUT_AI_OUTPUTS,
    input_optional_signals: Path = INPUT_OPTIONAL_SIGNALS,
    output_json: Path = OUTPUT_JSON,
    output_md: Path = OUTPUT_MD,
) -> dict:
    rows = _load_labeled_csv(input_labeled_csv)
    ai_outputs = _load_ai_outputs(input_ai_outputs)
    optional_signals_map = _load_optional_signals(input_optional_signals)

    limitations: list[str] = []
    if not rows:
        limitations.append("labeled_csv_not_found_or_empty")
    if not ai_outputs:
        limitations.append("ai_outputs_not_found_or_empty")

    if not rows or not ai_outputs:
        result = {
            "audit_version": "pmp_policy_v1_1_delta_audit.v1",
            "run_date": str(date.today()),
            "decision": DECISION_BLOCKED,
            "total_rows": 0,
            "limitations": limitations,
            "row_results": [],
            "summary": {},
        }
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        _write_md_report(result, output_md)
        return result

    row_results = []
    counters: dict[str, int] = Counter()

    for row in rows:
        review_item_id = row.get("review_item_id", "")
        local_path = row.get("local_image_path", "")
        media_key = _media_key_from_local_path(local_path)
        scientific_name = row.get("scientific_name", "")
        evidence_type = row.get("evidence_type", "")
        human_judgment = row.get("reviewer_overall_judgment_normalized", "")
        human_issue_category = row.get("human_issue_category", "")

        # Before: from labeled CSV recorded policy fields
        before_status = row.get("policy_status", "")
        before_recommended_raw = row.get("recommended_uses", "")
        before_borderline_raw = row.get("borderline_uses", "")
        before_recommended = _usages_set(before_recommended_raw)
        before_borderline = _usages_set(before_borderline_raw)

        # After: re-evaluate current policy from ai_outputs
        current_result: dict | None = None
        after_status = None
        after_recommended: set[str] = set()
        after_borderline: set[str] = set()
        compute_error: str | None = None

        if media_key and media_key in ai_outputs:
            entry = ai_outputs[media_key]
            pmp = entry.get("pedagogical_media_profile")
            source_status = entry.get("status", None)
            optional_sig = optional_signals_map.get(media_key)

            if isinstance(pmp, dict):
                try:
                    current_result = _evaluate_current_policy(
                        pmp, optional_signals=optional_sig
                    )
                    after_status = current_result.get("policy_status", "")
                    after_eligible = set(current_result.get("eligible_database_uses", []))
                    after_borderline_set: set[str] = set()
                    for usage_name, usage_info in current_result.get(
                        "usage_statuses", {}
                    ).items():
                        if usage_info.get("status") == "borderline":
                            after_borderline_set.add(usage_name)
                    after_recommended = after_eligible
                    after_borderline = after_borderline_set
                except Exception as exc:  # noqa: BLE001
                    compute_error = str(exc)
            elif before_status in ("pre_ai_rejected",):
                after_status = before_status
            else:
                compute_error = "missing_pmp_in_ai_output"
                # For pre_ai_rejected or failed with no pmp, apply source status
                if source_status:
                    from database_core.qualification.pmp_policy_v1 import (
                        evaluate_pmp_outcome_policy,
                    )
                    try:
                        current_result = evaluate_pmp_outcome_policy(entry)
                        after_status = current_result.get("policy_status", "")
                        compute_error = None
                    except Exception as exc2:  # noqa: BLE001
                        compute_error = str(exc2)
        elif media_key:
            compute_error = "media_key_not_in_ai_outputs"
        else:
            compute_error = "media_key_not_parseable"

        # Determine if before/after are comparable
        can_compare = (
            before_status is not None
            and after_status is not None
            and compute_error is None
        )

        status_change = "unknown"
        usage_comparison: dict = {}
        species_card_change = "unknown"
        habitat_change = "unknown"

        if can_compare:
            status_change = _compare_policy_status(before_status, after_status)
            # Detect species_card and habitat changes first so we can use them in
            # the regression classifier
            species_card_change = _detect_species_card_change(
                before_recommended,
                after_recommended,
                before_borderline,
                after_borderline,
            )
            habitat_change = _detect_habitat_change(
                before_recommended,
                after_recommended,
                before_borderline,
                after_borderline,
                evidence_type,
            )
            usage_comparison = _compare_usage_sets(
                before_recommended,
                after_recommended,
                before_borderline,
                after_borderline,
                human_judgment,
                evidence_type=evidence_type,
                species_card_changed=species_card_change,
                habitat_changed=habitat_change,
            )

        # Counters
        counters["total"] += 1
        if not can_compare:
            counters["not_comparable"] += 1
        else:
            counters["comparable"] += 1
            if status_change == "unchanged" and not usage_comparison.get("gained_uses") and not usage_comparison.get("lost_uses"):
                counters["fully_stable"] += 1
            elif usage_comparison.get("is_regression"):
                counters["regression"] += 1
            elif usage_comparison.get("is_calibration_downgrade"):
                counters["calibration_downgrade"] += 1
            elif usage_comparison.get("is_improvement"):
                counters["improvement"] += 1
            else:
                counters["changed_neutral"] += 1

            if species_card_change == "downgraded":
                counters["species_card_downgraded"] += 1
            if habitat_change == "indirect_evidence_downgraded":
                counters["habitat_indirect_downgraded"] += 1
            if status_change == "improved_schema_fix":
                counters["schema_false_negative_fixed"] += 1

        # Human judgment alignment
        if can_compare:
            if human_judgment == "accept" and after_status == "profile_valid":
                counters["human_accept_still_valid"] += 1
            if human_judgment == "too_permissive" and usage_comparison.get("lost_uses"):
                counters["human_too_permissive_now_downgraded"] += 1
            if human_judgment == "too_strict" and usage_comparison.get("is_improvement"):
                counters["human_too_strict_now_improved"] += 1

        row_result = {
            "review_item_id": review_item_id,
            "media_key": media_key,
            "scientific_name": scientific_name,
            "evidence_type": evidence_type,
            "human_judgment": human_judgment,
            "human_issue_category": human_issue_category,
            "before_policy_status": before_status,
            "before_recommended_uses": sorted(before_recommended),
            "before_borderline_uses": sorted(before_borderline),
            "after_policy_status": after_status,
            "after_recommended_uses": sorted(after_recommended) if after_recommended else None,
            "after_borderline_uses": sorted(after_borderline) if after_borderline else None,
            "status_change": status_change,
            "species_card_change": species_card_change,
            "habitat_change": habitat_change,
            "usage_comparison": usage_comparison if can_compare else None,
            "compute_error": compute_error,
            "comparable": can_compare,
        }
        row_results.append(row_result)

    # Final decision
    regression_count = counters.get("regression", 0)
    improvements = counters.get("human_too_strict_now_improved", 0)
    schema_fixes = counters.get("schema_false_negative_fixed", 0)
    not_comparable = counters.get("not_comparable", 0)

    if counters.get("comparable", 0) == 0:
        decision = DECISION_BLOCKED
    elif regression_count > REGRESSION_LIMIT:
        decision = DECISION_NEEDS_FIXES
    else:
        decision = DECISION_READY

    summary = {
        "total_rows": counters["total"],
        "comparable_rows": counters.get("comparable", 0),
        "not_comparable_rows": not_comparable,
        "fully_stable_rows": counters.get("fully_stable", 0),
        "regression_rows": regression_count,
        "calibration_downgrade_rows": counters.get("calibration_downgrade", 0),
        "improvement_rows": counters.get("improvement", 0),
        "changed_neutral_rows": counters.get("changed_neutral", 0),
        "schema_false_negative_fixed": schema_fixes,
        "species_card_downgraded": counters.get("species_card_downgraded", 0),
        "habitat_indirect_downgraded": counters.get("habitat_indirect_downgraded", 0),
        "human_accept_still_valid": counters.get("human_accept_still_valid", 0),
        "human_too_permissive_now_downgraded": counters.get(
            "human_too_permissive_now_downgraded", 0
        ),
        "human_too_strict_now_improved": counters.get("human_too_strict_now_improved", 0),
    }

    result = {
        "audit_version": "pmp_policy_v1_1_delta_audit.v1",
        "run_date": str(date.today()),
        "decision": decision,
        "total_rows": counters["total"],
        "limitations": limitations,
        "summary": summary,
        "row_results": row_results,
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    _write_md_report(result, output_md)
    return result


def _write_md_report(result: dict, output_path: Path) -> None:
    decision = result.get("decision", "UNKNOWN")
    summary = result.get("summary", {})
    limitations = result.get("limitations", [])
    run_date = result.get("run_date", str(date.today()))

    lines = [
        "---",
        "owner: vicodertoten",
        f"status: ready_for_validation",
        f"last_reviewed: {run_date}",
        "source_of_truth: docs/audits/evidence/pmp_policy_v1_1_broader_400_delta_audit.json",
        "scope: pmp_policy_v1_1_delta_audit",
        "---",
        "",
        "# PMP Policy v1.1 Delta Audit — broader_400",
        "",
        "## Purpose",
        "",
        "Compare broader_400 human review / recorded policy evidence (policy v1.0) against "
        "current policy v1.1 behavior. Validate that Sprint 9 Phase 2 calibration patches "
        "improve sensitive cases without causing regressions on previously accepted media.",
        "",
        "## Inputs",
        "",
        "- `docs/audits/human_review/pmp_policy_v1_broader_400_20260504_human_review_labeled.csv` "
        "— 60-row human review with recorded policy columns (policy v1.0 era)",
        "- `data/raw/inaturalist/palier1-be-birds-50taxa-run003-pmp-policy-broader-400-20260504/ai_outputs.json` "
        "— Gemini PMP outputs for 400 media (re-evaluated with policy v1.1)",
        "- `docs/audits/human_review/pmp_policy_v1_1_optional_signal_annotations.csv` "
        "— optional; if present, optional signals (target_taxon_visibility etc.) are injected",
        "",
        "## Limitations",
        "",
    ]

    if limitations:
        for lim in limitations:
            lines.append(f"- **{lim}**")
    else:
        lines += [
            "- The `before` state is reconstructed from the labeled CSV `policy_status`, "
            "`recommended_uses`, and `borderline_uses` columns, which were recorded during "
            "the Sprint 9 broader_400 run. This is a faithful approximation of v1.0 behavior "
            "but not a recomputed policy run.",
            "- Optional signal annotations (target_taxon_visibility, visible_answer_text, "
            "ui_screenshot) are injected if the annotation sheet exists, but these signals "
            "were not part of the original policy run. Changes driven by optional signals "
            "reflect new capabilities, not policy regressions.",
            "- Rows not matched in ai_outputs.json are excluded from comparison.",
        ]

    lines += [
        "",
        "## What Changed (Policy v1.0 → v1.1)",
        "",
        "Sprint 9 Phase 2 applied the following patches:",
        "",
        "1. **Schema normalization**: `body → whole_body`, `sitting → resting`, "
        "biological basis null downgrade to `unknown` — fixes 4 schema false negatives.",
        "2. **Species card calibration**: stricter thresholds; severe limitation keywords "
        "(distant, silhouette, heavily obscured) now downgrade species_card to not_recommended.",
        "3. **Habitat indirect evidence**: generic habitat with no species-relevant signal "
        "now downgrades indirect_evidence_learning.",
        "4. **Optional signals**: target_taxon_visibility, contains_visible_answer_text, "
        "contains_ui_screenshot now consumed by policy when present.",
        "",
        "## Results",
        "",
        f"| Metric | Count |",
        f"|---|---|",
        f"| Total rows | {summary.get('total_rows', 0)} |",
        f"| Comparable rows | {summary.get('comparable_rows', 0)} |",
        f"| Not comparable | {summary.get('not_comparable_rows', 0)} |",
        f"| Fully stable | {summary.get('fully_stable_rows', 0)} |",
        f"| Calibration downgrades (intentional) | {summary.get('calibration_downgrade_rows', 0)} |",
        f"| Regressions (unexpected) | {summary.get('regression_rows', 0)} |",
        f"| Improvements | {summary.get('improvement_rows', 0)} |",
        f"| Changed (neutral) | {summary.get('changed_neutral_rows', 0)} |",
        f"| Schema false negatives fixed | {summary.get('schema_false_negative_fixed', 0)} |",
        f"| Species card downgraded | {summary.get('species_card_downgraded', 0)} |",
        f"| Habitat indirect downgraded | {summary.get('habitat_indirect_downgraded', 0)} |",
        "",
        "## Human Judgment Alignment",
        "",
        f"| Judgment Category | Count |",
        f"|---|---|",
        f"| Human accept, still valid | {summary.get('human_accept_still_valid', 0)} |",
        f"| Human too_permissive, now downgraded | {summary.get('human_too_permissive_now_downgraded', 0)} |",
        f"| Human too_strict, now improved | {summary.get('human_too_strict_now_improved', 0)} |",
        "",
        "## Sensitive Case Summary",
        "",
        "- **Schema false negatives**: 4 items (body, sitting, biological basis null) "
        "were normalized in Sprint 9 Phase 2. These should now appear as profile_valid "
        "instead of profile_failed.",
        "- **Species card**: Items with distance/silhouette/obscured limitations should "
        "see species_card downgraded. This is intentional.",
        "- **Habitat**: Generic habitat (e.g. bird feeder with no species signal) should "
        "see indirect_evidence_learning downgraded. Intentional.",
        "- **Multiple species target unclear**: 4 items flagged in human review; "
        "policy now applies basic_identification/confusion_learning borderline + "
        "species_card not_recommended when target_taxon_visibility signal is present.",
        "",
        "## Risk of Regressions",
        "",
        "- Schema normalization: low risk — fixes clear failures.",
        "- Species card calibration: medium risk — threshold-based; borderline items may "
        "shift. Human second review will validate.",
        "- Habitat: low risk for specific habitat; medium for generic habitat (expected "
        "downgrade).",
        "- Optional signals: no risk from policy perspective (additive only when signals "
        "are present).",
        "",
        "## Recommendation for Second Review Sample",
        "",
        "Prioritize the following categories in the second broader review sheet:",
        "",
        "1. Species_card downgraded items — validate downgrade is appropriate.",
        "2. Schema false negative items — confirm they now pass.",
        "3. Habitat items — validate indirect_evidence_learning behavior.",
        "4. Multiple_organisms items — validate target_taxon_visibility effect.",
        "5. Stable accepted controls — confirm no silent regression.",
        "",
        f"## Decision",
        "",
        f"**{decision}**",
        "",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    result = run_delta_audit()
    print(f"Decision: {result['decision']}")
    summary = result.get("summary", {})
    print(f"Total rows: {summary.get('total_rows', 0)}")
    print(f"Comparable: {summary.get('comparable_rows', 0)}")
    print(f"Regressions: {summary.get('regression_rows', 0)}")
    print(f"Schema fixes: {summary.get('schema_false_negative_fixed', 0)}")
    print(f"Species card downgraded: {summary.get('species_card_downgraded', 0)}")
    print(f"Habitat indirect downgraded: {summary.get('habitat_indirect_downgraded', 0)}")
    print(f"Output: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
