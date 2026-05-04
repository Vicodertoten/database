#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

DEFAULT_SNAPSHOT_ROOT = Path("data/raw/inaturalist")
DEFAULT_OUTPUT_PATH = Path(
    "docs/audits/evidence/pedagogical_media_profile_v1_sprint6_snapshot_audit.json"
)

DECISION_READY_POLICY = "READY_FOR_PMP_POLICY_DESIGN"
DECISION_READY_CORPUS = "READY_FOR_CONTROLLED_PROFILED_CORPUS_RUN"
DECISION_ADJUST = "ADJUST_PMP_PIPELINE_INTEGRATION"
DECISION_INVESTIGATE = "INVESTIGATE_PMP_PIPELINE_FAILURES"
DECISION_BLOCKED_RUN = "BLOCKED_RUN_FAILED"

REQUIRED_USAGE_SCORE_KEYS = (
    "basic_identification",
    "field_observation",
    "confusion_learning",
    "morphology_learning",
    "species_card",
    "indirect_evidence_learning",
)

RUNTIME_POLLUTION_KEYS = {
    "feedback",
    "feedback_short",
    "post_answer_feedback",
    "selected_option_id",
    "selectedoptionid",
    "selected_playable_item_id",
    "selectedplayableitemid",
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit pedagogical_media_profile_v1 outcomes from a snapshot ai_outputs.json "
            "and write Sprint 6 evidence JSON."
        )
    )
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_SNAPSHOT_ROOT)
    parser.add_argument(
        "--ai-outputs-path",
        type=Path,
        help="Optional explicit ai_outputs.json path (overrides snapshot-id resolution).",
    )
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def _safe_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _min_max(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {"min": round(min(values), 2), "max": round(max(values), 2)}


def _nested_key_count(payload: Any, *, needle: str) -> int:
    lowered = needle.lower()
    if isinstance(payload, dict):
        count = 0
        for key, value in payload.items():
            key_lower = str(key).lower()
            if lowered in key_lower:
                count += 1
            count += _nested_key_count(value, needle=needle)
        return count
    if isinstance(payload, list):
        return sum(_nested_key_count(item, needle=needle) for item in payload)
    return 0


def _runtime_pollution_count(payload: Any) -> int:
    if isinstance(payload, dict):
        count = 0
        for key, value in payload.items():
            key_norm = str(key).strip().lower().replace("_", "")
            if key_norm in {item.replace("_", "") for item in RUNTIME_POLLUTION_KEYS}:
                count += 1
            count += _runtime_pollution_count(value)
        return count
    if isinstance(payload, list):
        return sum(_runtime_pollution_count(item) for item in payload)
    return 0


def _build_manual_review_sample(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    valid_items = [item for item in items if item["pmp_review_status"] == "valid"]
    failed_items = [item for item in items if item["pmp_review_status"] == "failed"]

    high_quality_valid = [
        item for item in valid_items if (item.get("global_quality_score") or -1) >= 80
    ]
    partial_or_indirect = [
        item
        for item in valid_items
        if item.get("evidence_type") in {"partial_organism", "indirect_evidence"}
    ]
    low_basic_valid = [
        item
        for item in valid_items
        if item.get("usage_scores", {}).get("basic_identification") is not None
        and item["usage_scores"]["basic_identification"] < 50
    ]

    selected_keys: list[str] = []

    def take_first(candidates: list[dict[str, Any]], n: int = 1) -> None:
        added = 0
        for candidate in candidates:
            key = str(candidate["media_key"])
            if key in selected_keys:
                continue
            selected_keys.append(key)
            added += 1
            if added >= n:
                break

    for candidate in high_quality_valid[:2]:
        take_first([candidate])
    if failed_items:
        take_first([failed_items[0]])
    if partial_or_indirect:
        take_first([partial_or_indirect[0]])
    if low_basic_valid:
        take_first([low_basic_valid[0]])

    remaining = sorted(items, key=lambda item: str(item["media_key"]))
    for item in remaining:
        if len(selected_keys) >= 5:
            break
        key = str(item["media_key"])
        if key not in selected_keys:
            selected_keys.append(key)

    sample_by_key = {str(item["media_key"]): item for item in items}
    sample: list[dict[str, Any]] = []
    for key in selected_keys[:10]:
        item = sample_by_key[key]
        sample.append(
            {
                "media_key": item["media_key"],
                "scientific_name": item.get("scientific_name"),
                "status": item["status"],
                "pmp_review_status": item["pmp_review_status"],
                "evidence_type": item.get("evidence_type"),
                "global_quality_score": item.get("global_quality_score"),
                "usage_scores": item.get("usage_scores", {}),
                "visible_field_marks": item.get("visible_field_marks", []),
                "limitations": item.get("limitations", []),
                "failure_reason": item.get("failure_reason"),
                "payload_excerpt": item.get("payload_excerpt"),
            }
        )
    return sample


def _decide_label(metrics: dict[str, Any]) -> str:
    if metrics.get("run_executed") is False:
        return DECISION_BLOCKED_RUN

    pmp_valid_rate = metrics.get("pmp_valid_rate")
    if pmp_valid_rate is None:
        return DECISION_BLOCKED_RUN

    if metrics.get("ai_outputs_broken"):
        return DECISION_INVESTIGATE

    if metrics.get("doctrine_pollution_detected"):
        return DECISION_INVESTIGATE

    if pmp_valid_rate < 0.60:
        return DECISION_INVESTIGATE
    if 0.60 <= pmp_valid_rate < 0.80:
        return DECISION_ADJUST

    if pmp_valid_rate >= 0.90 and metrics.get("plausible_distributions", False):
        return DECISION_READY_CORPUS
    if pmp_valid_rate >= 0.80:
        return DECISION_READY_POLICY
    return DECISION_ADJUST


def audit_snapshot_outputs(
    *,
    snapshot_id: str,
    snapshot_root: Path = DEFAULT_SNAPSHOT_ROOT,
    ai_outputs_path: Path | None = None,
) -> dict[str, Any]:
    resolved_ai_outputs_path = (
        ai_outputs_path
        if ai_outputs_path is not None
        else snapshot_root / snapshot_id / "ai_outputs.json"
    )

    base_result: dict[str, Any] = {
        "schema_version": "pedagogical_media_profile_v1_sprint6_snapshot_audit.v1",
        "snapshot_id": snapshot_id,
        "snapshot_root": str(snapshot_root),
        "ai_outputs_path": str(resolved_ai_outputs_path),
    }

    if not resolved_ai_outputs_path.exists():
        result = {
            **base_result,
            "run_executed": False,
            "ai_outputs_broken": True,
            "error": "ai_outputs.json missing",
            "decision": DECISION_BLOCKED_RUN,
        }
        return result

    try:
        payload = json.loads(resolved_ai_outputs_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        result = {
            **base_result,
            "run_executed": False,
            "ai_outputs_broken": True,
            "error": f"ai_outputs.json invalid JSON: {exc}",
            "decision": DECISION_BLOCKED_RUN,
        }
        return result

    rows: list[dict[str, Any]] = []
    status_distribution = Counter()
    failure_reason_distribution = Counter()
    schema_failure_cause_distribution = Counter()
    evidence_type_distribution = Counter()
    organism_group_distribution = Counter()
    model_name_distribution = Counter()
    prompt_version_distribution = Counter()
    review_contract_version_distribution = Counter()

    global_scores: list[float] = []
    usage_values: dict[str, list[float]] = {key: [] for key in REQUIRED_USAGE_SCORE_KEYS}
    low_basic_identification_valid_count = 0
    high_indirect_evidence_valid_count = 0

    pmp_valid_count = 0
    pmp_failed_count = 0
    qualification_none_count = 0
    feedback_field_count = 0
    selection_field_count = 0
    bird_image_pollution_count = 0
    unexpected_runtime_field_count = 0

    for media_key, outcome in sorted(payload.items(), key=lambda item: item[0]):
        if not isinstance(outcome, dict):
            continue
        status = str(outcome.get("status") or "unknown")
        status_distribution[status] += 1

        model_name_distribution[str(outcome.get("model_name") or "none")] += 1
        prompt_version_distribution[str(outcome.get("prompt_version") or "none")] += 1
        review_contract_version_distribution[
            str(outcome.get("review_contract_version") or "none")
        ] += 1

        if outcome.get("qualification") is None:
            qualification_none_count += 1

        if outcome.get("bird_image_pedagogical_review") is not None or outcome.get(
            "bird_image_pedagogical_score"
        ) is not None:
            bird_image_pollution_count += 1

        pmp = outcome.get("pedagogical_media_profile")
        if not isinstance(pmp, dict):
            pmp = {}

        pmp_review_status = str(pmp.get("review_status") or "missing")
        if pmp_review_status == "valid":
            pmp_valid_count += 1
        elif pmp_review_status != "missing":
            pmp_failed_count += 1

        failure_reason = pmp.get("failure_reason")
        if failure_reason:
            failure_reason_distribution[str(failure_reason)] += 1

        diagnostics = pmp.get("diagnostics")
        if isinstance(diagnostics, dict):
            for err in diagnostics.get("schema_errors") or []:
                if isinstance(err, dict) and err.get("type"):
                    schema_failure_cause_distribution[str(err["type"])] += 1

        evidence_type = pmp.get("evidence_type")
        if evidence_type:
            evidence_type_distribution[str(evidence_type)] += 1
        organism_group = pmp.get("organism_group")
        if organism_group:
            organism_group_distribution[str(organism_group)] += 1

        scores = pmp.get("scores") if isinstance(pmp.get("scores"), dict) else {}
        global_quality = _safe_float(scores.get("global_quality_score"))
        if global_quality is not None:
            global_scores.append(global_quality)

        usage_scores = (
            scores.get("usage_scores") if isinstance(scores.get("usage_scores"), dict) else {}
        )
        normalized_usage: dict[str, float] = {}
        for key in REQUIRED_USAGE_SCORE_KEYS:
            value = _safe_float(usage_scores.get(key))
            if value is not None:
                usage_values[key].append(value)
                normalized_usage[key] = value

        if pmp_review_status == "valid":
            basic = normalized_usage.get("basic_identification")
            if basic is not None and basic < 50:
                low_basic_identification_valid_count += 1
            indirect = normalized_usage.get("indirect_evidence_learning")
            if indirect is not None and indirect >= 70:
                high_indirect_evidence_valid_count += 1

        feedback_field_count += _nested_key_count(outcome, needle="feedback")
        selection_field_count += _nested_key_count(outcome, needle="selected_option")
        unexpected_runtime_field_count += _runtime_pollution_count(outcome)

        visible_field_marks = (
            (
                pmp.get("identification_profile")
                if isinstance(pmp.get("identification_profile"), dict)
                else {}
            ).get("visible_field_marks")
            or []
        )
        limitations = pmp.get("limitations") if isinstance(pmp.get("limitations"), list) else []
        payload_excerpt = json.dumps(pmp, ensure_ascii=True)[:350] if pmp else None

        rows.append(
            {
                "media_key": media_key,
                "status": status,
                "pmp_review_status": pmp_review_status,
                "failure_reason": str(failure_reason) if failure_reason else None,
                "evidence_type": str(evidence_type) if evidence_type else None,
                "organism_group": str(organism_group) if organism_group else None,
                "global_quality_score": global_quality,
                "usage_scores": normalized_usage,
                "visible_field_marks": visible_field_marks,
                "limitations": limitations,
                "scientific_name": None,
                "payload_excerpt": payload_excerpt,
            }
        )

    processed_media_count = len(rows)
    images_sent_to_gemini_count = sum(
        count
        for label, count in status_distribution.items()
        if label
        not in {
            "missing_cached_image",
            "insufficient_resolution",
            "insufficient_resolution_pre_ai",
            "decode_error_pre_ai",
            "blur_pre_ai",
            "duplicate_pre_ai",
        }
    )
    denominator = images_sent_to_gemini_count if images_sent_to_gemini_count > 0 else 0
    pmp_valid_rate = round(pmp_valid_count / denominator, 4) if denominator else None

    average_usage_scores = {
        key: _avg(values)
        for key, values in usage_values.items()
        if values
    }

    doctrine_pollution_detected = (
        feedback_field_count > 0
        or selection_field_count > 0
        or bird_image_pollution_count > 0
        or unexpected_runtime_field_count > 0
    )

    plausible_distributions = (
        pmp_valid_rate is not None
        and pmp_valid_rate >= 0.90
        and len(evidence_type_distribution) >= 1
        and len(average_usage_scores) >= 3
    )

    manual_review_sample = _build_manual_review_sample(rows)

    metrics: dict[str, Any] = {
        **base_result,
        "run_executed": True,
        "ai_outputs_broken": False,
        "generation_metrics": {
            "processed_media_count": processed_media_count,
            "images_sent_to_gemini_count": images_sent_to_gemini_count,
            "status_distribution": dict(sorted(status_distribution.items())),
            "pmp_valid_count": pmp_valid_count,
            "pmp_failed_count": pmp_failed_count,
            "pmp_valid_rate": pmp_valid_rate,
            "failure_reason_distribution": dict(sorted(failure_reason_distribution.items())),
            "schema_failure_cause_distribution": dict(
                sorted(schema_failure_cause_distribution.items())
            ),
            "evidence_type_distribution": dict(sorted(evidence_type_distribution.items())),
            "organism_group_distribution": dict(sorted(organism_group_distribution.items())),
        },
        "score_metrics": {
            "average_global_quality_score": _avg(global_scores),
            "average_usage_scores": average_usage_scores,
            "score_min_max": _min_max(global_scores),
            "low_basic_identification_valid_count": low_basic_identification_valid_count,
            "high_indirect_evidence_valid_count": high_indirect_evidence_valid_count,
        },
        "policy_legacy_metrics": {
            "qualification_none_count": qualification_none_count,
            "legacy_policy_rejection_count": None,
            "qualification_none_note": (
                "qualification=None is expected for PMP outcomes after Sprint 5 and "
                "is not a PMP generation failure."
            ),
        },
        "doctrine_pollution_checks": {
            "feedback_field_count": feedback_field_count,
            "selection_field_count": selection_field_count,
            "bird_image_pollution_count": bird_image_pollution_count,
            "unexpected_runtime_field_count": unexpected_runtime_field_count,
            "doctrine_pollution_detected": doctrine_pollution_detected,
        },
        "operational_metrics": {
            "latency_estimate": None,
            "cost_estimate": None,
            "model_name_distribution": dict(sorted(model_name_distribution.items())),
            "prompt_version_distribution": dict(sorted(prompt_version_distribution.items())),
            "review_contract_version_distribution": dict(
                sorted(review_contract_version_distribution.items())
            ),
        },
        "manual_review_sample": manual_review_sample,
        "plausible_distributions": plausible_distributions,
    }

    metrics["decision"] = _decide_label(
        {
            "run_executed": metrics["run_executed"],
            "ai_outputs_broken": metrics["ai_outputs_broken"],
            "doctrine_pollution_detected": doctrine_pollution_detected,
            "pmp_valid_rate": pmp_valid_rate,
            "plausible_distributions": plausible_distributions,
        }
    )
    return metrics


def main() -> int:
    args = _parse_args()
    result = audit_snapshot_outputs(
        snapshot_id=args.snapshot_id,
        snapshot_root=args.snapshot_root,
        ai_outputs_path=args.ai_outputs_path,
    )
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "Snapshot PMP audit complete | "
        f"snapshot_id={args.snapshot_id} | "
        f"decision={result.get('decision')} | "
        f"output={args.output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())