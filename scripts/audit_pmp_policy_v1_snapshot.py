#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from database_core.qualification.pmp_policy_v1 import (
    PMP_POLICY_STATUS_PRE_AI_REJECTED,
    PMP_POLICY_STATUS_PROFILE_FAILED,
    PMP_POLICY_STATUS_PROFILE_VALID,
    evaluate_pmp_outcome_policy,
)

DEFAULT_SNAPSHOT_ROOT = Path("data/raw/inaturalist")
DEFAULT_OUTPUT_PATH = Path("docs/audits/evidence/pmp_policy_v1_sprint7_snapshot_audit.json")

RUNTIME_POLLUTION_KEYS = {
    "feedback",
    "feedback_short",
    "post_answer_feedback",
    "selected_option_id",
    "selectedoptionid",
    "selected_playable_item_id",
    "selectedplayableitemid",
    "playable",
    "selected_for_quiz",
    "runtime_ready",
}

DECISION_READY = "READY_FOR_BROADER_PROFILED_CORPUS_WITH_POLICY"
DECISION_ADJUST = "ADJUST_POLICY_THRESHOLDS"
DECISION_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW_CALIBRATION"
DECISION_INVESTIGATE = "INVESTIGATE_POLICY_MISMATCH"
DECISION_BLOCKED = "BLOCKED_RUN_FAILED"

USAGE_NAMES = (
    "basic_identification",
    "field_observation",
    "confusion_learning",
    "morphology_learning",
    "species_card",
    "indirect_evidence_learning",
)

TARGET_REVIEW_CONTRACT_VERSION = "pedagogical_media_profile_v1"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit pmp_qualification_policy.v1 decisions from snapshot ai_outputs.json "
            "without mutating source outputs."
        )
    )
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_SNAPSHOT_ROOT)
    parser.add_argument("--ai-outputs-path", type=Path)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def _nested_key_count(payload: Any) -> int:
    normalized_runtime_keys = {item.replace("_", "") for item in RUNTIME_POLLUTION_KEYS}
    if isinstance(payload, dict):
        count = 0
        for key, value in payload.items():
            key_norm = str(key).strip().lower().replace("_", "")
            if key_norm in normalized_runtime_keys:
                count += 1
            count += _nested_key_count(value)
        return count
    if isinstance(payload, list):
        return sum(_nested_key_count(item) for item in payload)
    return 0


def _extract_example(rows: list[dict[str, object]], predicate: Any) -> dict[str, object] | None:
    for row in rows:
        if predicate(row):
            return row
    return None


def _resolve_decision(*, report: dict[str, object]) -> str:
    if report.get("ai_outputs_broken"):
        return DECISION_BLOCKED

    doctrine = report.get("doctrine_pollution_checks")
    if isinstance(doctrine, dict) and doctrine.get("doctrine_pollution_detected"):
        return DECISION_INVESTIGATE

    generation = report.get("generation_metrics")
    if not isinstance(generation, dict):
        return DECISION_INVESTIGATE

    processed_media_count = int(generation.get("processed_media_count") or 0)
    pmp_profile_valid_count = int(generation.get("pmp_profile_valid_count") or 0)
    if processed_media_count == 0:
        return DECISION_INVESTIGATE

    valid_ratio = pmp_profile_valid_count / processed_media_count
    if valid_ratio < 0.7:
        return DECISION_INVESTIGATE

    summary = report.get("policy_summary") if isinstance(report.get("policy_summary"), dict) else {}
    global_guardrail_ok = bool(summary.get("global_quality_guardrail_ok"))
    if not global_guardrail_ok:
        return DECISION_ADJUST

    indirect = report.get("indirect_evidence_checks")
    if isinstance(indirect, dict) and not bool(indirect.get("has_indirect_eligible")):
        return DECISION_HUMAN_REVIEW

    return DECISION_READY


def audit_pmp_policy_snapshot(
    *,
    snapshot_id: str,
    snapshot_root: Path = DEFAULT_SNAPSHOT_ROOT,
    ai_outputs_path: Path | None = None,
) -> dict[str, object]:
    resolved_ai_outputs_path = (
        ai_outputs_path
        if ai_outputs_path is not None
        else snapshot_root / snapshot_id / "ai_outputs.json"
    )

    if not resolved_ai_outputs_path.exists():
        report = {
            "snapshot_id": snapshot_id,
            "ai_outputs_path": str(resolved_ai_outputs_path),
            "ai_outputs_broken": True,
            "error": "missing_ai_outputs",
            "generation_metrics": {
                "processed_media_count": 0,
                "pmp_profile_valid_count": 0,
                "pmp_profile_failed_count": 0,
                "pre_ai_rejected_count": 0,
                "policy_status_distribution": {},
                "evidence_type_distribution": {},
            },
            "usage_eligibility_counts": {usage: {} for usage in USAGE_NAMES},
            "eligible_database_uses_distribution": {},
            "top_evidence_type_usage_status_combinations": [],
            "examples": {},
            "doctrine_pollution_checks": {
                "doctrine_pollution_detected": False,
                "runtime_or_feedback_pollution_count": 0,
            },
            "policy_summary": {
                "global_quality_guardrail_ok": True,
            },
            "indirect_evidence_checks": {
                "has_indirect_eligible": False,
            },
        }
        report["decision"] = _resolve_decision(report=report)
        return report

    try:
        payload = json.loads(resolved_ai_outputs_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        report = {
            "snapshot_id": snapshot_id,
            "ai_outputs_path": str(resolved_ai_outputs_path),
            "ai_outputs_broken": True,
            "error": "invalid_ai_outputs_json",
            "generation_metrics": {
                "processed_media_count": 0,
                "pmp_profile_valid_count": 0,
                "pmp_profile_failed_count": 0,
                "pre_ai_rejected_count": 0,
                "policy_status_distribution": {},
                "evidence_type_distribution": {},
            },
            "usage_eligibility_counts": {usage: {} for usage in USAGE_NAMES},
            "eligible_database_uses_distribution": {},
            "top_evidence_type_usage_status_combinations": [],
            "examples": {},
            "doctrine_pollution_checks": {
                "doctrine_pollution_detected": False,
                "runtime_or_feedback_pollution_count": 0,
            },
            "policy_summary": {
                "global_quality_guardrail_ok": True,
            },
            "indirect_evidence_checks": {
                "has_indirect_eligible": False,
            },
        }
        report["decision"] = _resolve_decision(report=report)
        return report

    outcomes = payload if isinstance(payload, dict) else {}

    policy_status_distribution: Counter[str] = Counter()
    evidence_type_distribution: Counter[str] = Counter()
    eligible_database_uses_distribution: Counter[str] = Counter()
    evidence_usage_status_distribution: Counter[str] = Counter()
    usage_eligibility_counts: dict[str, Counter[str]] = {
        usage_name: Counter() for usage_name in USAGE_NAMES
    }

    processed_media_count = 0
    pmp_profile_valid_count = 0
    pmp_profile_failed_count = 0
    pre_ai_rejected_count = 0
    runtime_or_feedback_pollution_count = 0

    rows: list[dict[str, object]] = []

    for media_key, outcome_raw in outcomes.items():
        if not isinstance(outcome_raw, dict):
            continue
        outcome = outcome_raw
        processed_media_count += 1
        runtime_or_feedback_pollution_count += _nested_key_count(outcome)

        decision = evaluate_pmp_outcome_policy(outcome)
        policy_status = str(decision.get("policy_status") or "unknown")
        evidence_type = str(decision.get("evidence_type") or "unknown")

        policy_status_distribution[policy_status] += 1
        evidence_type_distribution[evidence_type] += 1

        if policy_status == PMP_POLICY_STATUS_PROFILE_VALID:
            pmp_profile_valid_count += 1
        elif policy_status == PMP_POLICY_STATUS_PROFILE_FAILED:
            pmp_profile_failed_count += 1
        elif policy_status == PMP_POLICY_STATUS_PRE_AI_REJECTED:
            pre_ai_rejected_count += 1

        usage_statuses_raw = decision.get("usage_statuses")
        usage_statuses = usage_statuses_raw if isinstance(usage_statuses_raw, dict) else {}
        for usage_name in USAGE_NAMES:
            status_payload = (
                usage_statuses.get(usage_name)
                if isinstance(usage_statuses.get(usage_name), dict)
                else {}
            )
            usage_status = str(status_payload.get("status") or "not_applicable")
            usage_eligibility_counts[usage_name][usage_status] += 1
            evidence_usage_status_distribution[f"{evidence_type}|{usage_name}|{usage_status}"] += 1

        eligible_database_uses = (
            decision.get("eligible_database_uses")
            if isinstance(decision.get("eligible_database_uses"), list)
            else []
        )
        for usage_name in eligible_database_uses:
            eligible_database_uses_distribution[str(usage_name)] += 1

        rows.append(
            {
                "media_key": media_key,
                "source_status": outcome.get("status"),
                "policy_status": policy_status,
                "evidence_type": evidence_type,
                "review_status": decision.get("review_status"),
                "global_quality_score": decision.get("global_quality_score"),
                "usage_statuses": usage_statuses,
                "eligible_database_uses": eligible_database_uses,
                "policy_notes": decision.get("policy_notes") or [],
            }
        )

    rows.sort(key=lambda item: str(item.get("media_key") or ""))

    examples = {
        "whole_organism_basic_identification_eligible": _extract_example(
            rows,
            lambda row: row.get("evidence_type") == "whole_organism"
            and ((row.get("usage_statuses") or {}).get("basic_identification") or {}).get("status")
            == "eligible",
        ),
        "whole_organism_basic_not_eligible_field_observation_eligible": _extract_example(
            rows,
            lambda row: row.get("evidence_type") == "whole_organism"
            and ((row.get("usage_statuses") or {}).get("basic_identification") or {}).get("status")
            != "eligible"
            and ((row.get("usage_statuses") or {}).get("field_observation") or {}).get("status")
            == "eligible",
        ),
        "indirect_evidence_indirect_learning_eligible": _extract_example(
            rows,
            lambda row: row.get("evidence_type")
            in {"feather", "nest", "habitat", "track", "scat", "burrow", "dead_organism", "egg"}
            and (
                ((row.get("usage_statuses") or {}).get("indirect_evidence_learning") or {}).get(
                    "status"
                )
                == "eligible"
            ),
        ),
        "failed_profile": _extract_example(
            rows,
            lambda row: row.get("policy_status") == PMP_POLICY_STATUS_PROFILE_FAILED,
        ),
        "pre_ai_rejected": _extract_example(
            rows,
            lambda row: row.get("policy_status") == PMP_POLICY_STATUS_PRE_AI_REJECTED,
        ),
    }

    global_quality_guardrail_violations = []
    for row in rows:
        global_quality_score = row.get("global_quality_score")
        basic_payload = (row.get("usage_statuses") or {}).get("basic_identification") or {}
        basic_status = basic_payload.get("status")
        basic_score = basic_payload.get("score")
        if not isinstance(global_quality_score, (int, float)):
            continue
        if not isinstance(basic_score, (int, float)):
            continue
        if (
            float(global_quality_score) >= 85.0
            and float(basic_score) < 70.0
            and basic_status == "eligible"
        ):
            global_quality_guardrail_violations.append(str(row.get("media_key") or ""))

    global_quality_guardrail_ok = len(global_quality_guardrail_violations) == 0

    has_indirect_eligible = any(
        row.get("evidence_type")
        in {"feather", "nest", "habitat", "track", "scat", "burrow", "dead_organism", "egg"}
        and (
            ((row.get("usage_statuses") or {}).get("indirect_evidence_learning") or {}).get(
                "status"
            )
            == "eligible"
        )
        for row in rows
    )

    report = {
        "snapshot_id": snapshot_id,
        "ai_outputs_path": str(resolved_ai_outputs_path),
        "ai_outputs_broken": False,
        "generation_metrics": {
            "processed_media_count": processed_media_count,
            "pmp_profile_valid_count": pmp_profile_valid_count,
            "pmp_profile_failed_count": pmp_profile_failed_count,
            "pre_ai_rejected_count": pre_ai_rejected_count,
            "policy_status_distribution": dict(sorted(policy_status_distribution.items())),
            "evidence_type_distribution": dict(sorted(evidence_type_distribution.items())),
        },
        "usage_eligibility_counts": {
            usage_name: dict(sorted(counter.items()))
            for usage_name, counter in usage_eligibility_counts.items()
        },
        "eligible_database_uses_distribution": dict(
            sorted(eligible_database_uses_distribution.items())
        ),
        "top_evidence_type_usage_status_combinations": [
            {"combination": key, "count": count}
            for key, count in evidence_usage_status_distribution.most_common(12)
        ],
        "examples": examples,
        "doctrine_pollution_checks": {
            "doctrine_pollution_detected": runtime_or_feedback_pollution_count > 0,
            "runtime_or_feedback_pollution_count": runtime_or_feedback_pollution_count,
        },
        "policy_summary": {
            "global_quality_guardrail_ok": global_quality_guardrail_ok,
            "global_quality_guardrail_violation_count": len(global_quality_guardrail_violations),
            "policy_output_shape": {
                "contains_playable": False,
                "contains_selected_for_quiz": False,
                "contains_runtime_ready": False,
                "contains_selectedOptionId": False,
            },
        },
        "indirect_evidence_checks": {
            "has_indirect_eligible": has_indirect_eligible,
        },
    }
    report["decision"] = _resolve_decision(report=report)
    return report


def main() -> None:
    args = _parse_args()
    report = audit_pmp_policy_snapshot(
        snapshot_id=args.snapshot_id,
        snapshot_root=args.snapshot_root,
        ai_outputs_path=args.ai_outputs_path,
    )

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        "PMP policy snapshot audit complete"
        f" | snapshot_id={args.snapshot_id}"
        f" | decision={report.get('decision')}"
        f" | output={args.output_path}"
    )


if __name__ == "__main__":
    main()
