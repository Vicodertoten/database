"""
Analyze the second broader review sheet for PMP policy v1.1.

Input:
    docs/audits/human_review/pmp_policy_v1_1_second_broader_review_sheet.csv

Outputs:
    docs/audits/evidence/pmp_policy_v1_1_second_broader_review_analysis.json
    docs/audits/pmp-policy-v1-1-second-broader-review-analysis.md

Behavior:
    - Before the sheet is filled: outputs NEEDS_SECOND_REVIEW_COMPLETION.
    - After the sheet is filled: computes full analysis with decision label.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

INPUT_REVIEW_CSV = (
    REPO_ROOT
    / "docs/audits/human_review"
    / "pmp_policy_v1_1_second_broader_review_sheet.csv"
)
OUTPUT_JSON = (
    REPO_ROOT
    / "docs/audits/evidence"
    / "pmp_policy_v1_1_second_broader_review_analysis.json"
)
OUTPUT_MD = (
    REPO_ROOT
    / "docs/audits"
    / "pmp-policy-v1-1-second-broader-review-analysis.md"
)

DECISION_READY = "READY_FOR_FIRST_PROFILED_CORPUS_CANDIDATE"
DECISION_NEEDS_CALIBRATION = "NEEDS_POLICY_V1_2_CALIBRATION"
DECISION_NEEDS_SIGNAL_WORK = "NEEDS_MORE_TARGET_SIGNAL_WORK"
DECISION_NEEDS_COMPLETION = "NEEDS_SECOND_REVIEW_COMPLETION"
DECISION_INVESTIGATE = "INVESTIGATE_REGRESSIONS"

VALID_DECISIONS = {"accept", "too_strict", "too_permissive", "reject", "unclear"}
VALID_MAIN_ISSUES = {
    "none",
    "still_too_strict",
    "still_too_permissive",
    "fixed",
    "regression",
    "target_taxon_issue",
    "habitat_issue",
    "species_card_issue",
    "visible_text_issue",
    "schema_failure",
    "other",
}

# Decision thresholds
REGRESSION_LIMIT = 3
NEEDS_CALIBRATION_STRICT_LIMIT = 5
NEEDS_SIGNAL_WORK_TARGET_ISSUES = 3


def _load_review_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _normalize_decision(value: str) -> str:
    v = value.strip().lower()
    return v if v in VALID_DECISIONS else ""


def _normalize_main_issue(value: str) -> str:
    v = value.strip().lower()
    return v if v in VALID_MAIN_ISSUES else ""


def _is_row_reviewed(row: dict[str, str]) -> bool:
    return bool(row.get("second_review_decision", "").strip())


def _count_reviewed(rows: list[dict[str, str]]) -> int:
    return sum(1 for r in rows if _is_row_reviewed(r))


def run_analysis(
    *,
    input_review_csv: Path = INPUT_REVIEW_CSV,
    output_json: Path = OUTPUT_JSON,
    output_md: Path = OUTPUT_MD,
) -> dict:
    rows = _load_review_csv(input_review_csv)

    total_rows = len(rows)
    reviewed_count = _count_reviewed(rows)

    if total_rows == 0:
        result = {
            "analysis_version": "pmp_policy_v1_1_second_review_analysis.v1",
            "run_date": str(date.today()),
            "decision": DECISION_NEEDS_COMPLETION,
            "total_rows": 0,
            "reviewed_rows": 0,
            "fill_rate": 0.0,
            "summary": {},
            "category_outcomes": {},
            "decision_rationale": "No review file found or empty.",
        }
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        _write_md_report(result, output_md)
        return result

    fill_rate = reviewed_count / total_rows if total_rows > 0 else 0.0

    # If fewer than 50% filled, report as incomplete
    if fill_rate < 0.5:
        result = {
            "analysis_version": "pmp_policy_v1_1_second_review_analysis.v1",
            "run_date": str(date.today()),
            "decision": DECISION_NEEDS_COMPLETION,
            "total_rows": total_rows,
            "reviewed_rows": reviewed_count,
            "fill_rate": round(fill_rate, 3),
            "summary": {},
            "category_outcomes": {},
            "decision_rationale": f"Review fill rate {fill_rate:.1%} is below 50% threshold.",
        }
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        _write_md_report(result, output_md)
        return result

    # Full analysis
    decision_counter: Counter = Counter()
    main_issue_counter: Counter = Counter()
    regression_count = 0
    fixed_count = 0
    still_too_strict_count = 0
    still_too_permissive_count = 0

    # Category-specific counters
    category_counters: dict[str, Counter] = defaultdict(Counter)
    habitat_outcomes: Counter = Counter()
    species_card_outcomes: Counter = Counter()
    target_taxon_outcomes: Counter = Counter()
    schema_outcomes: Counter = Counter()
    control_stability: Counter = Counter()

    for row in rows:
        if not _is_row_reviewed(row):
            continue

        decision = _normalize_decision(row.get("second_review_decision", ""))
        main_issue = _normalize_main_issue(row.get("second_review_main_issue", ""))

        if not decision:
            continue

        decision_counter[decision] += 1
        if main_issue:
            main_issue_counter[main_issue] += 1

        if main_issue == "regression":
            regression_count += 1
        if main_issue == "fixed":
            fixed_count += 1
        if main_issue == "still_too_strict":
            still_too_strict_count += 1
        if main_issue == "still_too_permissive":
            still_too_permissive_count += 1

        # Per-category outcomes
        why_selected = row.get("why_selected_for_second_review", "")
        cats = [c.strip() for c in why_selected.split(",") if c.strip()]

        for cat in cats:
            category_counters[cat][decision] += 1

        # Specific category analysis
        if "habitat_generic" in cats or "habitat_species_relevant" in cats or main_issue == "habitat_issue":
            habitat_outcomes[decision] += 1

        if "species_card_downgraded" in cats or "species_card_eligible" in cats or main_issue == "species_card_issue":
            species_card_outcomes[decision] += 1

        if "multiple_species_target_unclear" in cats or main_issue == "target_taxon_issue":
            target_taxon_outcomes[decision] += 1

        if "schema_false_negative" in cats or "profile_failed_current" in cats or main_issue == "schema_failure":
            schema_outcomes[decision] += 1

        if "stable_accepted_control" in cats:
            control_stability[decision] += 1

    # Compute decision
    accept_rate = decision_counter["accept"] / reviewed_count if reviewed_count else 0.0
    control_regression = control_stability.get("too_strict", 0) + control_stability.get("reject", 0)

    target_taxon_issues = target_taxon_outcomes.get("too_strict", 0) + target_taxon_outcomes.get("unclear", 0)

    if regression_count > REGRESSION_LIMIT or control_regression > 0:
        decision = DECISION_INVESTIGATE
    elif still_too_strict_count > NEEDS_CALIBRATION_STRICT_LIMIT or still_too_permissive_count > NEEDS_CALIBRATION_STRICT_LIMIT:
        decision = DECISION_NEEDS_CALIBRATION
    elif target_taxon_issues >= NEEDS_SIGNAL_WORK_TARGET_ISSUES:
        decision = DECISION_NEEDS_SIGNAL_WORK
    else:
        decision = DECISION_READY

    summary = {
        "total_rows": total_rows,
        "reviewed_rows": reviewed_count,
        "fill_rate": round(fill_rate, 3),
        "accept_count": decision_counter["accept"],
        "too_strict_count": decision_counter["too_strict"],
        "too_permissive_count": decision_counter["too_permissive"],
        "reject_count": decision_counter["reject"],
        "unclear_count": decision_counter["unclear"],
        "fixed_count": fixed_count,
        "still_too_strict_count": still_too_strict_count,
        "still_too_permissive_count": still_too_permissive_count,
        "regression_count": regression_count,
        "accept_rate": round(accept_rate, 3),
        "issue_distribution": dict(main_issue_counter),
    }

    category_outcomes = {
        cat: dict(counter)
        for cat, counter in category_counters.items()
    }

    result = {
        "analysis_version": "pmp_policy_v1_1_second_review_analysis.v1",
        "run_date": str(date.today()),
        "decision": decision,
        "total_rows": total_rows,
        "reviewed_rows": reviewed_count,
        "fill_rate": round(fill_rate, 3),
        "summary": summary,
        "category_outcomes": category_outcomes,
        "habitat_outcomes": dict(habitat_outcomes),
        "species_card_outcomes": dict(species_card_outcomes),
        "target_taxon_outcomes": dict(target_taxon_outcomes),
        "schema_outcomes": dict(schema_outcomes),
        "control_stability": dict(control_stability),
        "decision_rationale": _compute_rationale(
            decision,
            regression_count=regression_count,
            still_too_strict_count=still_too_strict_count,
            still_too_permissive_count=still_too_permissive_count,
            target_taxon_issues=target_taxon_issues,
            control_regression=control_regression,
        ),
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    _write_md_report(result, output_md)
    return result


def _compute_rationale(
    decision: str,
    *,
    regression_count: int,
    still_too_strict_count: int,
    still_too_permissive_count: int,
    target_taxon_issues: int,
    control_regression: int,
) -> str:
    if decision == DECISION_INVESTIGATE:
        return (
            f"Regressions detected: regression_count={regression_count}, "
            f"control_regression={control_regression}. Investigate before proceeding."
        )
    if decision == DECISION_NEEDS_CALIBRATION:
        return (
            f"Still too_strict: {still_too_strict_count}, "
            f"still too_permissive: {still_too_permissive_count}. "
            "Policy v1.2 calibration needed."
        )
    if decision == DECISION_NEEDS_SIGNAL_WORK:
        return (
            f"Target taxon issues: {target_taxon_issues}. "
            "More signal annotation or prompt-side work needed."
        )
    return "Calibration patches validated; acceptable distribution of accept/edge cases."


def _write_md_report(result: dict, output_path: Path) -> None:
    decision = result.get("decision", "UNKNOWN")
    summary = result.get("summary", {})
    run_date = result.get("run_date", str(date.today()))
    fill_rate = result.get("fill_rate", 0.0)
    reviewed = result.get("reviewed_rows", 0)
    total = result.get("total_rows", 0)

    lines = [
        "---",
        "owner: vicodertoten",
        "status: ready_for_validation",
        f"last_reviewed: {run_date}",
        "source_of_truth: docs/audits/evidence/pmp_policy_v1_1_second_broader_review_analysis.json",
        "scope: pmp_policy_v1_1_second_review_analysis",
        "---",
        "",
        "# PMP Policy v1.1 — Second Broader Review Analysis",
        "",
        "## Purpose",
        "",
        "Analyze results of the targeted second broader review (Sprint 10).",
        "Validate whether Sprint 9 Phase 2 calibration patches (policy v1.1) improve "
        "sensitive cases without regressions.",
        "",
        f"## Review Status: {decision}",
        "",
        f"- Total rows: {total}",
        f"- Reviewed rows: {reviewed}",
        f"- Fill rate: {fill_rate:.1%}",
        "",
    ]

    if decision == DECISION_NEEDS_COMPLETION:
        lines += [
            "## ⚠ Review Not Yet Complete",
            "",
            result.get("decision_rationale", ""),
            "",
            "Fill in `second_review_decision` for each row in the review sheet, then re-run this script.",
        ]
    else:
        accept = summary.get("accept_count", 0)
        too_strict = summary.get("too_strict_count", 0)
        too_permissive = summary.get("too_permissive_count", 0)
        reject = summary.get("reject_count", 0)
        unclear = summary.get("unclear_count", 0)

        lines += [
            "## Decision Distribution",
            "",
            "| Decision | Count | % |",
            "|---|---|---|",
            f"| accept | {accept} | {accept/reviewed:.1%} |",
            f"| too_strict | {too_strict} | {too_strict/reviewed:.1%} |",
            f"| too_permissive | {too_permissive} | {too_permissive/reviewed:.1%} |",
            f"| reject | {reject} | {reject/reviewed:.1%} |",
            f"| unclear | {unclear} | {unclear/reviewed:.1%} |",
            "",
            "## Patch Effectiveness",
            "",
            "| Metric | Count |",
            "|---|---|",
            f"| Fixed | {summary.get('fixed_count', 0)} |",
            f"| Still too strict | {summary.get('still_too_strict_count', 0)} |",
            f"| Still too permissive | {summary.get('still_too_permissive_count', 0)} |",
            f"| Regression | {summary.get('regression_count', 0)} |",
            "",
            "## Category Outcomes",
            "",
        ]

        cat_outcomes = result.get("category_outcomes", {})
        if cat_outcomes:
            lines += [
                "| Category | accept | too_strict | too_permissive | reject | unclear |",
                "|---|---|---|---|---|---|",
            ]
            for cat, counts in sorted(cat_outcomes.items()):
                lines.append(
                    f"| {cat} "
                    f"| {counts.get('accept', 0)} "
                    f"| {counts.get('too_strict', 0)} "
                    f"| {counts.get('too_permissive', 0)} "
                    f"| {counts.get('reject', 0)} "
                    f"| {counts.get('unclear', 0)} |"
                )

        lines += [
            "",
            "## Target Taxon Visibility Outcomes",
            "",
            f"Outcomes for items with target_taxon_visibility annotations: "
            f"{result.get('target_taxon_outcomes', {})}",
            "",
            "## Habitat Outcomes",
            "",
            f"Outcomes for habitat evidence items: {result.get('habitat_outcomes', {})}",
            "",
            "## Species Card Outcomes",
            "",
            f"Outcomes for species_card items: {result.get('species_card_outcomes', {})}",
            "",
            "## Schema/Profile Outcomes",
            "",
            f"Outcomes for schema_false_negative / profile_failed items: "
            f"{result.get('schema_outcomes', {})}",
            "",
            "## Control Case Stability",
            "",
            f"Stable accepted control outcomes: {result.get('control_stability', {})}",
            "",
            "## Decision Rationale",
            "",
            result.get("decision_rationale", ""),
            "",
            f"## Final Decision: **{decision}**",
            "",
        ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    result = run_analysis()
    print(f"Decision: {result['decision']}")
    print(f"Total rows: {result['total_rows']}")
    print(f"Reviewed rows: {result['reviewed_rows']}")
    fill = result.get("fill_rate", 0.0)
    print(f"Fill rate: {fill:.1%}")
    print(f"Output: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
