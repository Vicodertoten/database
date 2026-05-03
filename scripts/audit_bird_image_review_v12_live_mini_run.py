#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv

LIVE_AUDIT_SCHEMA_VERSION = "bird_image_review_v12_live_mini_run_audit.v1"
DEFAULT_OUTPUT_PATH = Path("docs/audits/evidence/bird_image_review_v12_live_mini_run.json")
DEFAULT_SAMPLE_SIZE = 5
MIN_SAMPLE_SIZE = 5
MAX_SAMPLE_SIZE = 10

DECISION_READY = "READY_FOR_DISTRACTORS_V1_2"
DECISION_ADJUST = "ADJUST_PROMPT_OR_VALIDATION"
DECISION_INVESTIGATE = "INVESTIGATE_LIVE_FAILURES"

IMAGE_CONTEXT_MARKERS = (
    "sur cette image",
    "dans cette image",
    "ici",
    "on voit",
    "visible",
)
FEATURE_KEYWORDS = (
    "bec",
    "tete",
    "tête",
    "poitrine",
    "aile",
    "ailes",
    "queue",
    "oeil",
    "oeils",
    "oeil",
    "dos",
    "ventre",
    "nuque",
    "calotte",
    "sourcil",
    "silhouette",
    "plumage",
    "barre alaire",
)
GENERIC_FEEDBACK_PHRASES = (
    "regarde la couleur et la forme",
    "regarde les couleurs et la forme",
    "forme generale",
    "forme generale de l oiseau",
    "couleur et forme",
    "silhouette generale",
)


def _bootstrap_src_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    src_path = str(src)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a controlled mini live Gemini audit for bird image review v1.2 "
            "and compare v1.1 vs v1.2 on the same sample."
        )
    )
    parser.add_argument(
        "--snapshot-id",
        type=str,
        help="Snapshot id under data/raw/inaturalist to audit.",
    )
    parser.add_argument(
        "--snapshot-root",
        type=Path,
        default=Path("data/raw/inaturalist"),
        help="Root directory for cached iNaturalist snapshots.",
    )
    parser.add_argument(
        "--snapshot-manifest-path",
        type=Path,
        help="Optional explicit manifest path (overrides snapshot-id resolution).",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help=f"Live mini-run sample size ({MIN_SAMPLE_SIZE}-{MAX_SAMPLE_SIZE}).",
    )
    parser.add_argument("--gemini-model", default="gemini-3.1-flash-lite-preview")
    parser.add_argument("--gemini-api-key-env", default="GEMINI_API_KEY")
    parser.add_argument(
        "--gemini-concurrency",
        type=int,
        default=1,
        help="Worker count for live Gemini requests.",
    )
    parser.add_argument(
        "--uncertain-policy",
        choices=["review", "reject"],
        default="reject",
    )
    parser.add_argument(
        "--qualification-policy",
        choices=["v1", "v1.1"],
        default="v1.1",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="JSON evidence output path.",
    )
    return parser.parse_args()


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _extract_post_answer_feedback(review_payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(review_payload, dict):
        return {}
    feedback = review_payload.get("post_answer_feedback")
    if not isinstance(feedback, dict):
        return {}
    return feedback


def _feedback_text_fragments(feedback: dict[str, Any]) -> list[str]:
    correct = feedback.get("correct")
    incorrect = feedback.get("incorrect")
    tips = feedback.get("identification_tips")
    fragments: list[str] = []
    if isinstance(correct, dict):
        fragments.append(str(correct.get("short") or ""))
        fragments.append(str(correct.get("long") or ""))
    if isinstance(incorrect, dict):
        fragments.append(str(incorrect.get("short") or ""))
        fragments.append(str(incorrect.get("long") or ""))
    if isinstance(tips, list):
        fragments.extend(str(item or "") for item in tips)
    return fragments


def _count_feature_mentions(text: str) -> int:
    normalized = _normalize_text(text)
    return sum(1 for keyword in FEATURE_KEYWORDS if keyword in normalized)


def _has_image_context(feedback_fragments: list[str]) -> bool:
    merged = _normalize_text(" ".join(feedback_fragments))
    return any(marker in merged for marker in IMAGE_CONTEXT_MARKERS)


def _is_feedback_complete(feedback: dict[str, Any]) -> bool:
    correct = feedback.get("correct")
    incorrect = feedback.get("incorrect")
    tips = feedback.get("identification_tips")
    if not isinstance(correct, dict) or not isinstance(incorrect, dict):
        return False
    required_texts = [
        str(correct.get("short") or "").strip(),
        str(correct.get("long") or "").strip(),
        str(incorrect.get("short") or "").strip(),
        str(incorrect.get("long") or "").strip(),
    ]
    if not all(required_texts):
        return False
    if not isinstance(tips, list):
        return False
    normalized_tips = [str(item).strip() for item in tips if str(item).strip()]
    if len(normalized_tips) < 2:
        return False
    return True


def _is_feedback_image_specific(feedback: dict[str, Any]) -> bool:
    fragments = _feedback_text_fragments(feedback)
    if not fragments:
        return False
    if not _has_image_context(fragments):
        return False
    return _count_feature_mentions(" ".join(fragments)) >= 2


def is_generic_feedback(feedback: dict[str, Any]) -> bool:
    fragments = _feedback_text_fragments(feedback)
    merged = _normalize_text(" ".join(fragments))
    if not merged:
        return True
    if any(phrase in merged for phrase in GENERIC_FEEDBACK_PHRASES):
        return True
    feature_mentions = _count_feature_mentions(merged)
    return feature_mentions <= 1 and not _has_image_context(fragments)


def compute_feedback_metrics(success_reviews: list[dict[str, Any]]) -> dict[str, float]:
    if not success_reviews:
        return {
            "feedback_completeness_rate": 0.0,
            "feedback_image_specificity_rate": 0.0,
            "generic_feedback_rate": 0.0,
        }

    complete_count = 0
    specific_count = 0
    generic_count = 0
    for review in success_reviews:
        feedback = _extract_post_answer_feedback(review)
        if _is_feedback_complete(feedback):
            complete_count += 1
        if _is_feedback_image_specific(feedback):
            specific_count += 1
        if is_generic_feedback(feedback):
            generic_count += 1
    denominator = len(success_reviews)
    return {
        "feedback_completeness_rate": round(complete_count / denominator, 4),
        "feedback_image_specificity_rate": round(specific_count / denominator, 4),
        "generic_feedback_rate": round(generic_count / denominator, 4),
    }


def compute_v12_failure_reason_distribution(
    v12_outcome_summaries: list[dict[str, Any]],
) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for item in v12_outcome_summaries:
        if str(item.get("status") or "") != "bird_image_review_failed":
            continue
        reason = str(item.get("failure_reason") or "unknown").strip() or "unknown"
        counter[reason] += 1
    return dict(sorted(counter.items()))


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _average_subscores(score_payloads: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for payload in score_payloads:
        subscores = payload.get("subscores")
        if not isinstance(subscores, dict):
            continue
        for key, value in subscores.items():
            if not isinstance(value, (int, float)):
                continue
            totals[key] = totals.get(key, 0.0) + float(value)
            counts[key] = counts.get(key, 0) + 1
    result: dict[str, float] = {}
    for key, total in totals.items():
        count = counts.get(key, 0)
        result[key] = round(total / count, 2) if count else 0.0
    return dict(sorted(result.items()))


def _is_mature_playable(profile_status: str | None, export_eligible: bool) -> bool:
    return bool(
        export_eligible
        and profile_status in {"profiled", "profiled_with_warnings"}
    )


def _build_qualitative_feedback_examples(
    per_image_results: list[dict[str, Any]],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for item in per_image_results:
        v12 = item.get("v1_2") or {}
        if v12.get("status") != "ok":
            continue
        feedback = v12.get("post_answer_feedback")
        if not isinstance(feedback, dict):
            continue
        correct = feedback.get("correct") if isinstance(feedback.get("correct"), dict) else {}
        incorrect = (
            feedback.get("incorrect")
            if isinstance(feedback.get("incorrect"), dict)
            else {}
        )
        tips_value = feedback.get("identification_tips")
        tips = tips_value if isinstance(tips_value, list) else []
        examples.append(
            {
                "source_media_id": item.get("source_media_id"),
                "correct_short": str(correct.get("short") or ""),
                "incorrect_short": str(incorrect.get("short") or ""),
                "tip_1": str(tips[0]) if tips else "",
                "tip_2": str(tips[1]) if len(tips) > 1 else "",
            }
        )
        if len(examples) >= limit:
            break
    return examples


def compute_comparison_summary(per_image_results: list[dict[str, Any]]) -> dict[str, Any]:
    sample_size = len(per_image_results)
    v11_entries = [item.get("v1_1") or {} for item in per_image_results]
    v12_entries = [item.get("v1_2") or {} for item in per_image_results]

    v11_success_count = sum(1 for item in v11_entries if item.get("status") == "ok")
    v12_success_count = sum(1 for item in v12_entries if item.get("status") == "ok")
    v12_fail_closed_count = sum(
        1 for item in v12_entries if item.get("status") == "bird_image_review_failed"
    )

    v11_scores = [
        float(item["profile_overall_score"])
        for item in v11_entries
        if isinstance(item.get("profile_overall_score"), (int, float))
    ]
    v12_scores = [
        float(item["score_overall"])
        for item in v12_entries
        if isinstance(item.get("score_overall"), (int, float))
        and item.get("status") == "ok"
    ]
    v12_score_payloads = [
        item["score_payload"]
        for item in v12_entries
        if isinstance(item.get("score_payload"), dict)
        and item.get("status") == "ok"
    ]
    success_reviews = [
        item["normalized_review"]
        for item in v12_entries
        if isinstance(item.get("normalized_review"), dict)
        and item.get("status") == "ok"
    ]
    feedback_metrics = compute_feedback_metrics(success_reviews)

    mature_playable_count = sum(
        1
        for item in v12_entries
        if _is_mature_playable(
            str(item.get("profile_status")) if item.get("profile_status") is not None else None,
            bool(item.get("export_eligible")),
        )
    )
    blocked_by_v12_policy_count = sum(
        1
        for item in v12_entries
        if item.get("status") == "bird_image_review_failed"
    )

    summary = {
        "sample_size": sample_size,
        "v1_1_success_count": v11_success_count,
        "v1_2_success_count": v12_success_count,
        "v1_2_fail_closed_count": v12_fail_closed_count,
        "v1_2_failure_reason_distribution": compute_v12_failure_reason_distribution(v12_entries),
        "v1_1_average_score_if_available": _average(v11_scores),
        "v1_2_average_score": _average(v12_scores),
        "v1_2_score_decomposition_average": _average_subscores(v12_score_payloads),
        "feedback_completeness_rate": feedback_metrics["feedback_completeness_rate"],
        "feedback_image_specificity_rate": feedback_metrics["feedback_image_specificity_rate"],
        "generic_feedback_rate": feedback_metrics["generic_feedback_rate"],
        "profiles_mature_playable_count": mature_playable_count,
        "profiles_blocked_by_v1_2_policy_count": blocked_by_v12_policy_count,
        "qualitative_v1_2_feedback_examples": _build_qualitative_feedback_examples(
            per_image_results,
            limit=3,
        ),
        "runtime_contract_regression_detected": False,
    }
    return summary


def decide_v12_mini_run_outcome(summary: dict[str, Any]) -> str:
    sample_size = int(summary.get("sample_size") or 0)
    if sample_size <= 0:
        return DECISION_INVESTIGATE

    success_rate = float(summary.get("v1_2_success_count", 0)) / sample_size
    fail_closed_rate = float(summary.get("v1_2_fail_closed_count", 0)) / sample_size
    completeness_rate = float(summary.get("feedback_completeness_rate", 0.0))
    generic_rate = float(summary.get("generic_feedback_rate", 1.0))

    if (
        success_rate >= 0.8
        and fail_closed_rate <= 0.2
        and completeness_rate >= 0.8
        and generic_rate <= 0.3
    ):
        return DECISION_READY

    failure_distribution = summary.get("v1_2_failure_reason_distribution") or {}
    if not isinstance(failure_distribution, dict):
        failure_distribution = {}
    fail_count = int(summary.get("v1_2_fail_closed_count") or 0)
    if fail_count > 0:
        schema_failures = int(failure_distribution.get("schema_validation_failed") or 0)
        invalid_output_failures = int(failure_distribution.get("model_output_invalid") or 0)
        dominant_parse_failures = (
            schema_failures / fail_count >= 0.5
            or invalid_output_failures / fail_count >= 0.5
        )
        if fail_closed_rate > 0.2 and dominant_parse_failures:
            return DECISION_INVESTIGATE

    return DECISION_ADJUST


def validate_comparison_report_schema(report: dict[str, Any]) -> bool:
    required_top_level = {
        "schema_version",
        "run_id",
        "generated_at",
        "execution_status",
        "ai_review_contract_version",
        "comparison_baseline_contract_version",
        "sample_size",
        "summary",
        "per_image_results",
        "decision",
    }
    missing = sorted(required_top_level - set(report))
    if missing:
        raise ValueError(f"Missing required report keys: {missing}")
    if not isinstance(report.get("summary"), dict):
        raise ValueError("summary must be an object")
    if not isinstance(report.get("per_image_results"), list):
        raise ValueError("per_image_results must be a list")
    return True


def _skipped_report(
    *,
    run_id: str,
    gemini_api_key_env: str,
    output_path: Path,
) -> dict[str, Any]:
    summary = {
        "sample_size": 0,
        "v1_1_success_count": 0,
        "v1_2_success_count": 0,
        "v1_2_fail_closed_count": 0,
        "v1_2_failure_reason_distribution": {},
        "v1_1_average_score_if_available": 0.0,
        "v1_2_average_score": 0.0,
        "v1_2_score_decomposition_average": {},
        "feedback_completeness_rate": 0.0,
        "feedback_image_specificity_rate": 0.0,
        "generic_feedback_rate": 0.0,
        "profiles_mature_playable_count": 0,
        "profiles_blocked_by_v1_2_policy_count": 0,
        "qualitative_v1_2_feedback_examples": [],
        "runtime_contract_regression_detected": False,
        "skip_reason": "missing_live_credentials",
    }
    return {
        "schema_version": LIVE_AUDIT_SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "execution_status": "skipped_missing_credentials",
        "ai_review_contract_version": "v1_2",
        "comparison_baseline_contract_version": "v1_1",
        "sample_size": 0,
        "summary": summary,
        "per_image_results": [],
        "decision": DECISION_INVESTIGATE,
        "notes": {
            "message": "Live mini-run skipped because Gemini credentials are missing.",
            "gemini_api_key_env": gemini_api_key_env,
            "output_path": str(output_path),
        },
    }


def _snapshot_scientific_name(
    *,
    canonical_taxon_id: str | None,
    canonical_by_id: dict[str, Any],
) -> str | None:
    if not canonical_taxon_id:
        return None
    taxon = canonical_by_id.get(canonical_taxon_id)
    if taxon is None:
        return None
    return str(getattr(taxon, "accepted_scientific_name", None) or "") or None


def _snapshot_common_names(
    *,
    canonical_taxon_id: str | None,
    canonical_by_id: dict[str, Any],
) -> dict[str, str]:
    if not canonical_taxon_id:
        return {}
    taxon = canonical_by_id.get(canonical_taxon_id)
    if taxon is None:
        return {}
    from database_core.qualification.ai import _resolve_primary_common_names

    return _resolve_primary_common_names(taxon)


def _summarize_v11_entry(
    *,
    outcome: Any,
    profile_by_media_id: dict[str, Any],
    resource_by_media_id: dict[str, Any],
    media_id: str,
) -> dict[str, Any]:
    profile = profile_by_media_id.get(media_id)
    resource = resource_by_media_id.get(media_id)
    return {
        "status": outcome.status,
        "flags": list(outcome.flags),
        "note": outcome.note,
        "profile_status": profile.profile_status.value if profile else None,
        "profile_overall_score": profile.overall_score if profile else None,
        "export_eligible": bool(resource.export_eligible) if resource else False,
        "mature_playable": _is_mature_playable(
            profile.profile_status.value if profile else None,
            bool(resource.export_eligible) if resource else False,
        ),
    }


def _summarize_v12_entry(
    *,
    outcome: Any,
    profile_by_media_id: dict[str, Any],
    resource_by_media_id: dict[str, Any],
    media_id: str,
) -> dict[str, Any]:
    profile = profile_by_media_id.get(media_id)
    resource = resource_by_media_id.get(media_id)
    review_payload = (
        dict(outcome.bird_image_pedagogical_review)
        if isinstance(outcome.bird_image_pedagogical_review, dict)
        else {}
    )
    score_payload = (
        dict(outcome.bird_image_pedagogical_score)
        if isinstance(outcome.bird_image_pedagogical_score, dict)
        else {}
    )
    feedback_payload = _extract_post_answer_feedback(review_payload)
    return {
        "status": outcome.status,
        "flags": list(outcome.flags),
        "note": outcome.note,
        "failure_reason": str(review_payload.get("failure_reason") or "") or None,
        "score_overall": score_payload.get("overall"),
        "score_payload": score_payload,
        "normalized_review": review_payload,
        "post_answer_feedback": feedback_payload,
        "profile_status": profile.profile_status.value if profile else None,
        "profile_overall_score": profile.overall_score if profile else None,
        "export_eligible": bool(resource.export_eligible) if resource else False,
        "mature_playable": _is_mature_playable(
            profile.profile_status.value if profile else None,
            bool(resource.export_eligible) if resource else False,
        ),
    }


def _build_profiles_for_contract(
    *,
    dataset: Any,
    sample_media_assets: list[Any],
    outcomes_by_key: dict[Any, Any],
    run_id: str,
    uncertain_policy: str,
    qualification_policy: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    from database_core.qualification.pedagogical_image_profile import (
        build_pedagogical_image_profile,
    )
    from database_core.qualification.rules import qualify_media_assets

    resources, _ = qualify_media_assets(
        canonical_taxa=dataset.canonical_taxa,
        observations=dataset.observations,
        media_assets=sample_media_assets,
        ai_qualifications_by_source_media_key=outcomes_by_key,
        created_at=dataset.captured_at,
        run_id=run_id,
        uncertain_policy=uncertain_policy,
        qualification_policy=qualification_policy,
    )
    resource_by_media_id = {item.media_asset_id: item for item in resources}

    profile_by_media_id: dict[str, Any] = {}
    for media_asset in sample_media_assets:
        resource = resource_by_media_id.get(media_asset.media_id)
        if resource is None:
            continue
        from database_core.qualification.ai import source_external_key_for_media

        outcome = outcomes_by_key.get(source_external_key_for_media(media_asset))
        profile_by_media_id[media_asset.media_id] = build_pedagogical_image_profile(
            resource,
            ai_outcome=outcome,
            media_asset=media_asset,
        )
    return profile_by_media_id, resource_by_media_id


def run_live_mini_audit(
    *,
    snapshot_id: str | None,
    snapshot_root: Path,
    snapshot_manifest_path: Path | None,
    sample_size: int,
    gemini_api_key: str | None,
    gemini_api_key_env: str,
    gemini_model: str,
    gemini_concurrency: int,
    uncertain_policy: str,
    qualification_policy: str,
    output_path: Path,
) -> dict[str, Any]:
    run_id = f"audit:bird-image-review-v12-live-mini:{uuid4().hex[:8]}"
    if not gemini_api_key:
        return _skipped_report(
            run_id=run_id,
            gemini_api_key_env=gemini_api_key_env,
            output_path=output_path,
        )

    if sample_size < MIN_SAMPLE_SIZE or sample_size > MAX_SAMPLE_SIZE:
        raise ValueError(
            f"--sample-size must be between {MIN_SAMPLE_SIZE} and {MAX_SAMPLE_SIZE}."
        )
    if snapshot_id is None and snapshot_manifest_path is None:
        raise ValueError("--snapshot-id or --snapshot-manifest-path is required for live run.")

    from database_core.adapters import load_snapshot_dataset, load_snapshot_manifest
    from database_core.adapters.inaturalist_qualification import _compute_pre_ai_rejections
    from database_core.qualification.ai import (
        AI_REVIEW_CONTRACT_V1_1,
        AI_REVIEW_CONTRACT_V1_2,
        build_bird_image_review_inputs_by_source_media_key,
        collect_ai_qualification_outcomes,
        source_external_key_for_media,
    )

    dataset = load_snapshot_dataset(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        manifest_path=snapshot_manifest_path,
    )
    manifest, snapshot_dir = load_snapshot_manifest(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        manifest_path=snapshot_manifest_path,
    )

    pre_ai_rejections = _compute_pre_ai_rejections(manifest=manifest, snapshot_dir=snapshot_dir)
    eligible_media_assets = [
        media
        for media in dataset.media_assets
        if media.source_media_id not in pre_ai_rejections
    ]
    eligible_media_assets = sorted(eligible_media_assets, key=lambda item: item.source_media_id)
    sample_media_assets = eligible_media_assets[:sample_size]
    actual_sample_size = len(sample_media_assets)

    review_inputs_by_key = build_bird_image_review_inputs_by_source_media_key(
        media_assets=sample_media_assets,
        canonical_taxa=dataset.canonical_taxa,
    )
    image_paths_by_key = {
        source_external_key_for_media(media): dataset.cached_image_paths_by_source_media_key.get(
            source_external_key_for_media(media)
        )
        for media in sample_media_assets
    }

    outcomes_v11 = collect_ai_qualification_outcomes(
        sample_media_assets,
        qualifier_mode="gemini",
        cached_image_paths_by_source_media_key=image_paths_by_key,
        bird_image_review_inputs_by_source_media_key=review_inputs_by_key,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        review_contract_version=AI_REVIEW_CONTRACT_V1_1,
        gemini_concurrency=max(1, gemini_concurrency),
    )
    outcomes_v12 = collect_ai_qualification_outcomes(
        sample_media_assets,
        qualifier_mode="gemini",
        cached_image_paths_by_source_media_key=image_paths_by_key,
        bird_image_review_inputs_by_source_media_key=review_inputs_by_key,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        review_contract_version=AI_REVIEW_CONTRACT_V1_2,
        gemini_concurrency=max(1, gemini_concurrency),
    )

    v11_profiles, v11_resources = _build_profiles_for_contract(
        dataset=dataset,
        sample_media_assets=sample_media_assets,
        outcomes_by_key=outcomes_v11,
        run_id=f"{run_id}:v1_1",
        uncertain_policy=uncertain_policy,
        qualification_policy=qualification_policy,
    )
    v12_profiles, v12_resources = _build_profiles_for_contract(
        dataset=dataset,
        sample_media_assets=sample_media_assets,
        outcomes_by_key=outcomes_v12,
        run_id=f"{run_id}:v1_2",
        uncertain_policy=uncertain_policy,
        qualification_policy=qualification_policy,
    )

    canonical_by_id = {taxon.canonical_taxon_id: taxon for taxon in dataset.canonical_taxa}
    per_image_results: list[dict[str, Any]] = []
    for media in sample_media_assets:
        source_key = source_external_key_for_media(media)
        outcome_v11 = outcomes_v11[source_key]
        outcome_v12 = outcomes_v12[source_key]
        per_image_results.append(
            {
                "source_media_id": media.source_media_id,
                "media_id": media.media_id,
                "canonical_taxon_id": media.canonical_taxon_id,
                "scientific_name": _snapshot_scientific_name(
                    canonical_taxon_id=media.canonical_taxon_id,
                    canonical_by_id=canonical_by_id,
                ),
                "common_names": _snapshot_common_names(
                    canonical_taxon_id=media.canonical_taxon_id,
                    canonical_by_id=canonical_by_id,
                ),
                "source_url": media.source_url,
                "v1_1": _summarize_v11_entry(
                    outcome=outcome_v11,
                    profile_by_media_id=v11_profiles,
                    resource_by_media_id=v11_resources,
                    media_id=media.media_id,
                ),
                "v1_2": _summarize_v12_entry(
                    outcome=outcome_v12,
                    profile_by_media_id=v12_profiles,
                    resource_by_media_id=v12_resources,
                    media_id=media.media_id,
                ),
            }
        )

    summary = compute_comparison_summary(per_image_results)
    decision = decide_v12_mini_run_outcome(summary)
    report = {
        "schema_version": LIVE_AUDIT_SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "execution_status": "completed",
        "ai_review_contract_version": "v1_2",
        "comparison_baseline_contract_version": "v1_1",
        "snapshot_id": snapshot_id or snapshot_dir.name,
        "snapshot_manifest_path": str(snapshot_manifest_path) if snapshot_manifest_path else None,
        "snapshot_root": str(snapshot_root),
        "requested_sample_size": sample_size,
        "sample_size": actual_sample_size,
        "summary": summary,
        "per_image_results": per_image_results,
        "decision": decision,
        "decision_thresholds": {
            "ready_for_distractors_v1_2": {
                "v1_2_parse_validation_success_rate_gte": 0.8,
                "v1_2_fail_closed_rate_lte": 0.2,
                "feedback_completeness_rate_gte": 0.8,
                "generic_feedback_rate_lte": 0.3,
                "runtime_contract_regression_detected": False,
            }
        },
    }
    validate_comparison_report_schema(report)
    return report


def main() -> int:
    load_dotenv(dotenv_path=Path(".env"))
    _bootstrap_src_path()
    args = _parse_args()

    gemini_api_key = os.environ.get(args.gemini_api_key_env)
    report = run_live_mini_audit(
        snapshot_id=args.snapshot_id,
        snapshot_root=args.snapshot_root,
        snapshot_manifest_path=args.snapshot_manifest_path,
        sample_size=args.sample_size,
        gemini_api_key=gemini_api_key,
        gemini_api_key_env=args.gemini_api_key_env,
        gemini_model=args.gemini_model,
        gemini_concurrency=args.gemini_concurrency,
        uncertain_policy=args.uncertain_policy,
        qualification_policy=args.qualification_policy,
        output_path=args.output_path,
    )

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "bird image review v1.2 live mini-run audit | "
        f"execution_status={report['execution_status']} | "
        f"sample_size={report['sample_size']} | "
        f"decision={report['decision']} | "
        f"output={args.output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
