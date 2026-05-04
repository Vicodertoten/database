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

INDIRECT_EVIDENCE_TYPES = {
    "feather",
    "egg",
    "nest",
    "track",
    "scat",
    "burrow",
    "habitat",
    "dead_organism",
}

PARTIAL_OR_COMPLEX_EVIDENCE_TYPES = {
    "partial_organism",
    "multiple_organisms",
}

PRE_AI_STATUSES = {
    "missing_cached_image",
    "insufficient_resolution",
    "insufficient_resolution_pre_ai",
    "decode_error_pre_ai",
    "blur_pre_ai",
    "duplicate_pre_ai",
}

ERROR_CAUSE_KEYS = ("cause", "type", "validator", "schema_failure_cause", "error_type")
ERROR_PATH_KEYS = ("path", "loc", "instance_path", "json_path")

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
        "--manifest-path",
        type=Path,
        help="Optional explicit manifest.json path for metadata joins.",
    )
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


def _normalize_scalar(value: object, *, limit: int = 240) -> object:
    if value is None:
        return None
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, list):
        return f"<array len={len(value)}>"
    if isinstance(value, dict):
        return f"<object keys={sorted(value.keys())[:8]}>"
    return str(value)[:limit]


def _normalize_path(value: object) -> str:
    if value is None:
        return "<unknown>"
    if isinstance(value, (list, tuple)):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return ".".join(parts) if parts else "<unknown>"
    text = str(value).strip()
    return text or "<unknown>"


def _nested_key_count(payload: Any, *, needle: str) -> int:
    lowered = needle.lower()
    if isinstance(payload, dict):
        count = 0
        for key, value in payload.items():
            if lowered in str(key).lower():
                count += 1
            count += _nested_key_count(value, needle=needle)
        return count
    if isinstance(payload, list):
        return sum(_nested_key_count(item, needle=needle) for item in payload)
    return 0


def _runtime_pollution_count(payload: Any) -> int:
    normalized_runtime_keys = {item.replace("_", "") for item in RUNTIME_POLLUTION_KEYS}
    if isinstance(payload, dict):
        count = 0
        for key, value in payload.items():
            key_norm = str(key).strip().lower().replace("_", "")
            if key_norm in normalized_runtime_keys:
                count += 1
            count += _runtime_pollution_count(value)
        return count
    if isinstance(payload, list):
        return sum(_runtime_pollution_count(item) for item in payload)
    return 0


def _load_snapshot_metadata(
    *,
    snapshot_id: str,
    snapshot_root: Path,
    manifest_path: Path | None,
) -> tuple[str, dict[str, dict[str, str]]]:
    resolved_manifest = (
        manifest_path
        if manifest_path is not None
        else snapshot_root / snapshot_id / "manifest.json"
    )
    if not resolved_manifest.exists():
        return "not_available", {}

    try:
        manifest = json.loads(resolved_manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "invalid_manifest", {}

    snapshot_dir = resolved_manifest.parent
    media_to_observation: dict[str, str] = {}
    for item in manifest.get("media_downloads", []):
        if not isinstance(item, dict):
            continue
        media_id = str(item.get("source_media_id") or "").strip()
        obs_id = str(item.get("source_observation_id") or "").strip()
        if media_id:
            media_to_observation[media_id] = obs_id

    metadata_by_media_key: dict[str, dict[str, str]] = {}
    for seed in manifest.get("taxon_seeds", []):
        if not isinstance(seed, dict):
            continue
        response_path_raw = seed.get("response_path")
        if not isinstance(response_path_raw, str) or not response_path_raw.strip():
            continue
        response_path = snapshot_dir / response_path_raw
        if not response_path.exists():
            continue

        try:
            payload = json.loads(response_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        for result in payload.get("results", []):
            if not isinstance(result, dict):
                continue
            photos = result.get("photos")
            if not isinstance(photos, list) or not photos:
                continue
            primary = photos[0]
            if not isinstance(primary, dict):
                continue
            media_id = str(primary.get("id") or "").strip()
            if not media_id:
                continue

            taxon = result.get("taxon") if isinstance(result.get("taxon"), dict) else {}
            scientific_name = str(
                taxon.get("name")
                or result.get("species_guess")
                or seed.get("accepted_scientific_name")
                or ""
            ).strip()
            source_taxon_id = str(taxon.get("id") or seed.get("source_taxon_id") or "").strip()
            canonical_taxon_id = str(seed.get("canonical_taxon_id") or "").strip()
            source_observation_id = str(
                result.get("id") or media_to_observation.get(media_id) or ""
            ).strip()

            metadata_by_media_key[f"inaturalist::{media_id}"] = {
                "scientific_name": scientific_name,
                "canonical_taxon_id": canonical_taxon_id,
                "source_taxon_id": source_taxon_id,
                "source_observation_id": source_observation_id,
            }

    if not metadata_by_media_key:
        return "not_available", {}
    return "joined_from_manifest", metadata_by_media_key


def _extract_schema_errors(diagnostics: dict[str, object]) -> list[dict[str, object]]:
    raw_errors = diagnostics.get("schema_errors")
    if not isinstance(raw_errors, list):
        return []
    return [item for item in raw_errors if isinstance(item, dict)]


def _extract_error_path(error: dict[str, object]) -> str:
    for key in ERROR_PATH_KEYS:
        if key in error:
            return _normalize_path(error.get(key))
    return "<unknown>"


def _extract_error_cause(error: dict[str, object], diagnostics: dict[str, object]) -> str:
    for key in ERROR_CAUSE_KEYS:
        value = error.get(key)
        if isinstance(value, str) and value.strip():
            normalized = value.strip()
            if normalized != "unknown_schema_failure":
                return normalized
    fallback = diagnostics.get("schema_failure_cause")
    if isinstance(fallback, str) and fallback.strip():
        normalized_fallback = fallback.strip()
        if normalized_fallback:
            return normalized_fallback
    return "unknown_schema_failure"


def _extract_error_validator(error: dict[str, object]) -> str | None:
    value = error.get("validator")
    if isinstance(value, str) and value.strip():
        return value.strip()
    value = error.get("type")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _extract_error_example(
    *,
    media_key: str,
    error: dict[str, object],
    diagnostics: dict[str, object],
) -> dict[str, object]:
    return {
        "media_key": media_key,
        "path": _extract_error_path(error),
        "cause": _extract_error_cause(error, diagnostics),
        "validator": _extract_error_validator(error),
        "message": str(error.get("message") or "")[:240],
        "expected": _normalize_scalar(error.get("expected")),
        "actual": _normalize_scalar(error.get("actual")),
    }


def _append_bounded(
    target: dict[str, list[dict[str, object]]],
    key: str,
    item: dict[str, object],
    *,
    limit: int = 3,
) -> None:
    current = target.setdefault(key, [])
    if len(current) < limit:
        current.append(item)


def _build_manual_review_sample(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, bool]]:
    valid_items = [item for item in items if item.get("pmp_review_status") == "valid"]
    failed_items = [item for item in items if item.get("pmp_review_status") == "failed"]

    high_quality_whole = [
        item
        for item in valid_items
        if item.get("evidence_type") == "whole_organism"
        and (item.get("global_quality_score") or -1) >= 80
    ]
    indirect_items = [
        item for item in valid_items if item.get("evidence_type") in INDIRECT_EVIDENCE_TYPES
    ]
    partial_or_complex_items = [
        item
        for item in valid_items
        if item.get("evidence_type") in PARTIAL_OR_COMPLEX_EVIDENCE_TYPES
    ]
    low_basic_valid = [
        item
        for item in valid_items
        if item.get("usage_scores", {}).get("basic_identification") is not None
        and float(item["usage_scores"]["basic_identification"]) < 50
    ]
    low_global_valid = [
        item
        for item in valid_items
        if item.get("global_quality_score") is not None
        and float(item["global_quality_score"]) < 50
    ]

    selected_keys: list[str] = []

    def select_from(candidates: list[dict[str, Any]], *, count: int = 1) -> None:
        added = 0
        for candidate in sorted(candidates, key=lambda item: str(item["media_key"])):
            media_key = str(candidate["media_key"])
            if media_key in selected_keys:
                continue
            selected_keys.append(media_key)
            added += 1
            if added >= count:
                break

    select_from(high_quality_whole, count=2)
    select_from(failed_items)
    select_from(indirect_items)
    select_from(partial_or_complex_items)
    select_from(low_basic_valid)
    select_from(low_global_valid)

    remaining = sorted(items, key=lambda item: str(item["media_key"]))
    for item in remaining:
        if len(selected_keys) >= 10:
            break
        media_key = str(item["media_key"])
        if media_key not in selected_keys:
            selected_keys.append(media_key)

    if len(selected_keys) < 5:
        for item in remaining:
            media_key = str(item["media_key"])
            if media_key not in selected_keys:
                selected_keys.append(media_key)
            if len(selected_keys) >= 5:
                break

    by_key = {str(item["media_key"]): item for item in items}
    sample: list[dict[str, Any]] = []
    for media_key in selected_keys[:10]:
        item = by_key[media_key]
        sample.append(
            {
                "media_key": item["media_key"],
                "scientific_name": item.get("scientific_name"),
                "canonical_taxon_id": item.get("canonical_taxon_id"),
                "source_taxon_id": item.get("source_taxon_id"),
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

    coverage = {
        "has_high_quality_valid": bool(high_quality_whole),
        "has_failed": bool(failed_items),
        "has_indirect_evidence": bool(indirect_items),
        "has_partial_or_multiple": bool(partial_or_complex_items),
        "has_low_basic_identification": bool(low_basic_valid),
    }
    return sample, coverage


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
    manifest_path: Path | None = None,
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
        return {
            **base_result,
            "run_executed": False,
            "ai_outputs_broken": True,
            "error": "ai_outputs.json missing",
            "metadata_join_status": "not_available",
            "decision": DECISION_BLOCKED_RUN,
        }

    try:
        payload = json.loads(resolved_ai_outputs_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            **base_result,
            "run_executed": False,
            "ai_outputs_broken": True,
            "error": f"ai_outputs.json invalid JSON: {exc}",
            "metadata_join_status": "not_available",
            "decision": DECISION_BLOCKED_RUN,
        }

    metadata_join_status, metadata_by_media_key = _load_snapshot_metadata(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        manifest_path=manifest_path,
    )

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

    schema_error_path_distribution = Counter()
    examples_by_failure_cause: dict[str, list[dict[str, object]]] = {}
    examples_by_schema_error_path: dict[str, list[dict[str, object]]] = {}
    failed_items_summary: list[dict[str, object]] = []

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

        diagnostics = pmp.get("diagnostics") if isinstance(pmp.get("diagnostics"), dict) else {}
        schema_errors = _extract_schema_errors(diagnostics)
        raw_schema_failure_cause = str(diagnostics.get("schema_failure_cause") or "").strip()
        first_extracted_cause = (
            _extract_error_cause(schema_errors[0], diagnostics)
            if schema_errors
            else "unknown_schema_failure"
        )
        if (
            not raw_schema_failure_cause
            or raw_schema_failure_cause == "unknown_schema_failure"
        ):
            schema_failure_cause = first_extracted_cause
        else:
            schema_failure_cause = raw_schema_failure_cause
        had_schema_errors = False
        for schema_error in schema_errors:
            had_schema_errors = True
            error_path = _extract_error_path(schema_error)
            error_cause = _extract_error_cause(schema_error, diagnostics)
            schema_error_path_distribution[error_path] += 1
            schema_failure_cause_distribution[error_cause] += 1
            example = _extract_error_example(
                media_key=media_key,
                error=schema_error,
                diagnostics=diagnostics,
            )
            _append_bounded(examples_by_failure_cause, error_cause, example)
            _append_bounded(examples_by_schema_error_path, error_path, example)

        if pmp_review_status == "failed" and not had_schema_errors:
            schema_failure_cause_distribution[schema_failure_cause] += 1

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

        row = {
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
            "payload_excerpt": payload_excerpt,
            "scientific_name": None,
            "canonical_taxon_id": None,
            "source_taxon_id": None,
        }

        metadata = metadata_by_media_key.get(media_key, {})
        if metadata:
            row["scientific_name"] = metadata.get("scientific_name") or None
            row["canonical_taxon_id"] = metadata.get("canonical_taxon_id") or None
            row["source_taxon_id"] = metadata.get("source_taxon_id") or None
        if row["scientific_name"] is None:
            diag_name = diagnostics.get("scientific_name")
            if isinstance(diag_name, str) and diag_name.strip():
                row["scientific_name"] = diag_name.strip()
        if row["canonical_taxon_id"] is None:
            diag_canon = diagnostics.get("canonical_taxon_id")
            if isinstance(diag_canon, str) and diag_canon.strip():
                row["canonical_taxon_id"] = diag_canon.strip()

        rows.append(row)

        if pmp_review_status == "failed":
            failed_items_summary.append(
                {
                    "media_key": media_key,
                    "model_name": outcome.get("model_name"),
                    "prompt_version": outcome.get("prompt_version"),
                    "review_contract_version": outcome.get("review_contract_version"),
                    "failure_reason": failure_reason,
                    "schema_failure_cause": schema_failure_cause,
                    "schema_error_count": diagnostics.get("schema_error_count"),
                    "schema_errors": [
                        _extract_error_example(
                            media_key=media_key,
                            error=error,
                            diagnostics=diagnostics,
                        )
                        for error in schema_errors[:8]
                    ],
                    "raw_model_output_excerpt": (
                        str(diagnostics.get("raw_model_output_excerpt") or "")[:350] or None
                    ),
                    "scientific_name": row.get("scientific_name"),
                    "canonical_taxon_id": row.get("canonical_taxon_id"),
                }
            )

    processed_media_count = len(rows)
    images_sent_to_gemini_count = sum(
        count
        for status_label, count in status_distribution.items()
        if status_label not in PRE_AI_STATUSES
    )
    pmp_valid_rate = (
        round(pmp_valid_count / images_sent_to_gemini_count, 4)
        if images_sent_to_gemini_count > 0
        else None
    )

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

    score_metrics_by_evidence_type: dict[str, dict[str, object]] = {}
    rows_by_evidence: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        evidence_label = str(row.get("evidence_type") or "unknown_or_missing")
        rows_by_evidence.setdefault(evidence_label, []).append(row)

    for evidence_label, subset in sorted(rows_by_evidence.items()):
        valid_subset = [item for item in subset if item.get("pmp_review_status") == "valid"]
        failed_subset = [item for item in subset if item.get("pmp_review_status") == "failed"]
        valid_count = len(valid_subset)
        failed_count = len(failed_subset)
        denominator = valid_count + failed_count

        subset_global_scores = [
            float(item["global_quality_score"])
            for item in valid_subset
            if item.get("global_quality_score") is not None
        ]

        subset_usage_values: dict[str, list[float]] = {key: [] for key in REQUIRED_USAGE_SCORE_KEYS}
        for item in valid_subset:
            usage = item.get("usage_scores", {})
            if not isinstance(usage, dict):
                continue
            for key in REQUIRED_USAGE_SCORE_KEYS:
                value = _safe_float(usage.get(key))
                if value is not None:
                    subset_usage_values[key].append(value)

        low_basic_subset = sum(
            1
            for item in valid_subset
            if isinstance(item.get("usage_scores"), dict)
            and _safe_float(item["usage_scores"].get("basic_identification")) is not None
            and float(item["usage_scores"]["basic_identification"]) < 50
        )
        high_indirect_subset = sum(
            1
            for item in valid_subset
            if isinstance(item.get("usage_scores"), dict)
            and _safe_float(item["usage_scores"].get("indirect_evidence_learning")) is not None
            and float(item["usage_scores"]["indirect_evidence_learning"]) >= 70
        )

        score_metrics_by_evidence_type[evidence_label] = {
            "count": len(subset),
            "valid_count": valid_count,
            "failed_count": failed_count,
            "valid_rate": round(valid_count / denominator, 4) if denominator > 0 else None,
            "average_global_quality_score": _avg(subset_global_scores),
            "average_usage_scores": {
                key: _avg(values)
                for key, values in subset_usage_values.items()
                if values
            },
            "score_min_max": _min_max(subset_global_scores),
            "low_basic_identification_valid_count": low_basic_subset,
            "high_indirect_evidence_valid_count": high_indirect_subset,
        }

    manual_review_sample, manual_review_coverage = _build_manual_review_sample(rows)

    top_schema_error_paths = [
        {"path": path, "count": count}
        for path, count in sorted(
            schema_error_path_distribution.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]

    metrics: dict[str, Any] = {
        **base_result,
        "run_executed": True,
        "ai_outputs_broken": False,
        "metadata_join_status": metadata_join_status,
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
            "top_schema_error_paths": top_schema_error_paths,
            "evidence_type_distribution": dict(sorted(evidence_type_distribution.items())),
            "organism_group_distribution": dict(sorted(organism_group_distribution.items())),
        },
        "failure_diagnostics": {
            "failed_count": pmp_failed_count,
            "schema_failure_cause_distribution": dict(
                sorted(schema_failure_cause_distribution.items())
            ),
            "top_schema_error_paths": top_schema_error_paths,
            "examples_by_failure_cause": {
                key: value for key, value in sorted(examples_by_failure_cause.items())
            },
            "examples_by_schema_error_path": {
                key: value for key, value in sorted(examples_by_schema_error_path.items())
            },
            "failed_items_summary": failed_items_summary,
        },
        "score_metrics": {
            "average_global_quality_score": _avg(global_scores),
            "average_usage_scores": average_usage_scores,
            "score_min_max": _min_max(global_scores),
            "low_basic_identification_valid_count": low_basic_identification_valid_count,
            "high_indirect_evidence_valid_count": high_indirect_evidence_valid_count,
            "score_metrics_by_evidence_type": score_metrics_by_evidence_type,
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
            "measurement_status": "not_measured_in_sprint6_controlled_run",
            "model_name_distribution": dict(sorted(model_name_distribution.items())),
            "prompt_version_distribution": dict(sorted(prompt_version_distribution.items())),
            "review_contract_version_distribution": dict(
                sorted(review_contract_version_distribution.items())
            ),
        },
        "manual_review_sample": manual_review_sample,
        "manual_review_sample_coverage": manual_review_coverage,
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
        manifest_path=args.manifest_path,
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
