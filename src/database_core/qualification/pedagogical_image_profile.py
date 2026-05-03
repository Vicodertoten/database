from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from database_core.domain.enums import (
    ConfusionRelevance,
    DiagnosticFeatureVisibility,
    DifficultyLevel,
    LicenseSafetyResult,
    MediaRole,
    MediaType,
    PedagogicalProfileStatus,
    PedagogicalQuality,
    PedagogicalScoreBand,
    PedagogicalUsage,
    QualificationStatus,
    TaxonGroup,
    TechnicalQuality,
    UncertaintyReason,
    ViewAngle,
)
from database_core.domain.models import (
    BirdImagePedagogicalFeatures,
    MediaAsset,
    PedagogicalFeedbackProfile,
    PedagogicalImageProfile,
    PedagogicalImageSubscores,
    PedagogicalUsageScores,
    PostAnswerFeedback,
    PostAnswerFeedbackVariant,
    QualifiedResource,
)
from database_core.qualification.ai import AIQualificationOutcome

PROFILE_VERSION = "pedagogical_image_profile.v1"

CONFIDENCE_REJECT_THRESHOLD = 20
CONFIDENCE_MANUAL_REVIEW_THRESHOLD = 50
PRIMARY_BLOCK_TECHNICAL_THRESHOLD = 30
RECOMMENDED_USAGE_THRESHOLD = 70
AVOID_USAGE_THRESHOLD = 35
AI_RESOURCE_DIVERGENCE_CONFIDENCE_DELTA = 0.20

MANUAL_REVIEW_WARNING_SIGNALS = {
    "ai_outcome_qualified_resource_divergence",
    "cached_prompt_version_mismatch",
    "license_review_required",
    "low_confidence_requires_manual_review",
}

PENDING_AI_STATUSES = {
    "missing_cached_ai_output",
    "missing_fixture_ai_output",
    "gemini_error",
    "invalid_gemini_json",
    "insufficient_resolution_pre_ai",
    "decode_error_pre_ai",
    "blur_pre_ai",
    "duplicate_pre_ai",
    "rules_only",
    "bird_image_review_failed",
}

MANUAL_REVIEW_AI_STATUSES = {
    "cached_prompt_version_mismatch",
}

FIELD_MARK_PARTS = {
    "head",
    "crown",
    "eye",
    "beak",
    "bill",
    "throat",
    "nape",
    "back",
    "wing",
    "tail",
    "breast",
    "belly",
    "leg",
    "feet",
}


@dataclass(frozen=True)
class _AiContext:
    has_valid_ai: bool
    ai_status: str
    confidence_score: int
    ai_profile_source: str | None
    ai_prompt_version: str | None
    model_name: str | None


def build_pedagogical_image_profile(
    qualified_resource: QualifiedResource,
    *,
    ai_outcome: AIQualificationOutcome | None = None,
    media_asset: MediaAsset | None = None,
    taxon_group: TaxonGroup = TaxonGroup.BIRDS,
) -> PedagogicalImageProfile:
    reason_codes: list[str] = []
    warnings: list[str] = []

    ai_context = _resolve_ai_context(qualified_resource=qualified_resource, ai_outcome=ai_outcome)

    blocked_status = _hard_gate_status(
        qualified_resource=qualified_resource,
        media_asset=media_asset,
        ai_context=ai_context,
        reason_codes=reason_codes,
        warnings=warnings,
    )
    if blocked_status in {
        PedagogicalProfileStatus.PENDING_AI,
        PedagogicalProfileStatus.REJECTED_FOR_PLAYABLE_USE,
    }:
        return _build_blocked_profile(
            qualified_resource=qualified_resource,
            taxon_group=taxon_group,
            profile_status=blocked_status,
            reason_codes=reason_codes,
            warnings=warnings,
            ai_context=ai_context,
            media_type=media_asset.media_type if media_asset else MediaType.IMAGE,
        )

    divergence_reason_codes = _collect_ai_resource_divergence_reason_codes(
        qualified_resource=qualified_resource,
        ai_outcome=ai_outcome,
    )
    if divergence_reason_codes:
        warnings.append("ai_outcome_qualified_resource_divergence")
        reason_codes.append("manual_review_ai_outcome_resource_divergence")
        reason_codes.extend(divergence_reason_codes)

    feedback = _build_feedback_profile(qualified_resource=qualified_resource, ai_outcome=ai_outcome)
    subscores = _compute_subscores(
        qualified_resource=qualified_resource,
        ai_confidence_score=ai_context.confidence_score,
        feedback=feedback,
    )
    overall_score = _compute_overall_score(subscores)
    score_band = _score_band_from_score(overall_score)

    technical_primary_block = subscores.technical_quality <= PRIMARY_BLOCK_TECHNICAL_THRESHOLD
    if technical_primary_block:
        warnings.append("technical_quality_too_low_for_primary_question")
        reason_codes.append("hard_gate_primary_question_block_technical")

    usage_scores = _compute_usage_scores(
        qualified_resource=qualified_resource,
        subscores=subscores,
        feedback=feedback,
        technical_primary_block=technical_primary_block,
    )

    if ai_context.confidence_score < CONFIDENCE_MANUAL_REVIEW_THRESHOLD:
        warnings.append("low_confidence_requires_manual_review")
        reason_codes.append("hard_gate_low_confidence_manual_review")

    if not _has_feedback_signal(feedback):
        warnings.append("limited_feedback_payload")
        reason_codes.append("feedback_not_available_for_explanation_usage")

    has_recommended_candidate = _has_recommended_usage_candidate(usage_scores)
    if not has_recommended_candidate:
        reason_codes.append("manual_review_no_recommended_usage")

    status = _resolve_profile_status(
        blocked_status=blocked_status,
        ai_context=ai_context,
        warnings=warnings,
        has_recommended_candidate=has_recommended_candidate,
    )

    recommended_usages, avoid_usages = _resolve_usage_classification(
        status=status,
        usage_scores=usage_scores,
        technical_primary_block=technical_primary_block,
    )

    reason_codes.append(f"score_band_{score_band.value}")

    return PedagogicalImageProfile(
        profile_version=PROFILE_VERSION,
        profile_status=status,
        qualified_resource_id=qualified_resource.qualified_resource_id,
        media_asset_id=qualified_resource.media_asset_id,
        canonical_taxon_id=qualified_resource.canonical_taxon_id,
        taxon_group=taxon_group,
        media_type=media_asset.media_type if media_asset else MediaType.IMAGE,
        overall_score=overall_score,
        score_band=score_band,
        confidence=ai_context.confidence_score,
        subscores=subscores,
        usage_scores=usage_scores,
        recommended_usages=recommended_usages,
        avoid_usages=avoid_usages,
        feedback=feedback,
        reason_codes=reason_codes,
        warnings=warnings,
        bird_image=_build_bird_image_features(qualified_resource),
        ai_required=True,
        ai_profile_source=ai_context.ai_profile_source,
        ai_prompt_version=ai_context.ai_prompt_version,
        model_name=ai_context.model_name,
    )


def _hard_gate_status(
    *,
    qualified_resource: QualifiedResource,
    media_asset: MediaAsset | None,
    ai_context: _AiContext,
    reason_codes: list[str],
    warnings: list[str],
) -> PedagogicalProfileStatus | None:
    if qualified_resource.license_safety_result == LicenseSafetyResult.UNSAFE:
        reason_codes.append("hard_gate_unsafe_license")
        return PedagogicalProfileStatus.REJECTED_FOR_PLAYABLE_USE

    if qualified_resource.license_safety_result == LicenseSafetyResult.REVIEW_REQUIRED:
        warnings.append("license_review_required")
        reason_codes.append("hard_gate_license_review_required")
        return PedagogicalProfileStatus.MANUAL_REVIEW_REQUIRED

    if qualified_resource.qualification_status == QualificationStatus.REJECTED:
        reason_codes.append("hard_gate_rejected_qualification")
        return PedagogicalProfileStatus.REJECTED_FOR_PLAYABLE_USE

    if media_asset is None:
        reason_codes.append("hard_gate_missing_media_asset")
        return PedagogicalProfileStatus.REJECTED_FOR_PLAYABLE_USE

    if not media_asset.source_url.strip():
        reason_codes.append("hard_gate_missing_media_url")
        return PedagogicalProfileStatus.REJECTED_FOR_PLAYABLE_USE

    if media_asset.media_type != MediaType.IMAGE:
        reason_codes.append("hard_gate_unsupported_media_type")
        return PedagogicalProfileStatus.REJECTED_FOR_PLAYABLE_USE

    if not ai_context.has_valid_ai:
        if ai_context.ai_status in MANUAL_REVIEW_AI_STATUSES:
            reason_codes.append("hard_gate_ai_status_requires_manual_review")
            warnings.append("cached_prompt_version_mismatch")
            return PedagogicalProfileStatus.MANUAL_REVIEW_REQUIRED
        reason_codes.append("hard_gate_missing_or_invalid_ai_qualification")
        return PedagogicalProfileStatus.PENDING_AI

    if ai_context.confidence_score <= CONFIDENCE_REJECT_THRESHOLD:
        reason_codes.append("hard_gate_very_low_confidence_rejected")
        return PedagogicalProfileStatus.REJECTED_FOR_PLAYABLE_USE

    return None


def _resolve_ai_context(
    *,
    qualified_resource: QualifiedResource,
    ai_outcome: AIQualificationOutcome | None,
) -> _AiContext:
    provenance = qualified_resource.provenance_summary
    ai_status = (provenance.ai_status or "").strip() or "unknown"
    ai_profile_source = provenance.qualification_method
    ai_prompt_version = provenance.ai_prompt_version
    model_name = provenance.ai_model

    confidence_score = _to_percent(qualified_resource.ai_confidence)
    has_valid_ai = False

    if ai_outcome is not None:
        ai_status = (ai_outcome.status or "").strip() or ai_status
        ai_prompt_version = ai_outcome.prompt_version or ai_prompt_version
        model_name = ai_outcome.model_name or model_name
        ai_profile_source = "ai_outcome"

        if ai_outcome.qualification is not None:
            confidence_score = _to_percent(ai_outcome.qualification.confidence)
            model_name = ai_outcome.qualification.model_name or model_name
            has_valid_ai = ai_status == "ok"
        elif ai_status in PENDING_AI_STATUSES:
            has_valid_ai = False
        elif ai_status in MANUAL_REVIEW_AI_STATUSES:
            has_valid_ai = False
    else:
        has_valid_ai = ai_status == "ok" and qualified_resource.ai_confidence is not None

    if ai_status in PENDING_AI_STATUSES:
        has_valid_ai = False

    return _AiContext(
        has_valid_ai=has_valid_ai,
        ai_status=ai_status,
        confidence_score=confidence_score,
        ai_profile_source=ai_profile_source,
        ai_prompt_version=ai_prompt_version,
        model_name=model_name,
    )


def _build_blocked_profile(
    *,
    qualified_resource: QualifiedResource,
    taxon_group: TaxonGroup,
    profile_status: PedagogicalProfileStatus,
    reason_codes: list[str],
    warnings: list[str],
    ai_context: _AiContext,
    media_type: MediaType,
) -> PedagogicalImageProfile:
    zero_subscores = PedagogicalImageSubscores(
        technical_quality=0,
        subject_visibility=0,
        diagnostic_value=0,
        pedagogical_clarity=0,
        representativeness=0,
        difficulty_fit=0,
        feedback_potential=0,
        confusion_potential=0,
        context_value=0,
        confidence=0,
    )
    zero_usage = PedagogicalUsageScores(
        primary_question_beginner=0,
        primary_question_intermediate=0,
        primary_question_expert=0,
        context_learning=0,
        confusion_training=0,
        feedback_explanation=0,
    )
    feedback = PedagogicalFeedbackProfile(
        feedback_short=None,
        feedback_long=None,
        what_to_look_at=[],
        why_good_example=[],
        why_not_ideal=[_reason_to_sentence(reason) for reason in reason_codes],
        beginner_hint=None,
        expert_hint=None,
        confusion_hint=None,
        post_answer_feedback=None,
        feedback_confidence=0,
    )

    return PedagogicalImageProfile(
        profile_version=PROFILE_VERSION,
        profile_status=profile_status,
        qualified_resource_id=qualified_resource.qualified_resource_id,
        media_asset_id=qualified_resource.media_asset_id,
        canonical_taxon_id=qualified_resource.canonical_taxon_id,
        taxon_group=taxon_group,
        media_type=media_type,
        overall_score=0,
        score_band=PedagogicalScoreBand.E,
        confidence=ai_context.confidence_score,
        subscores=zero_subscores,
        usage_scores=zero_usage,
        recommended_usages=[],
        avoid_usages=[usage for usage in PedagogicalUsage],
        feedback=feedback,
        reason_codes=reason_codes,
        warnings=warnings,
        bird_image=_build_bird_image_features(qualified_resource),
        ai_required=True,
        ai_profile_source=ai_context.ai_profile_source,
        ai_prompt_version=ai_context.ai_prompt_version,
        model_name=ai_context.model_name,
    )


def _compute_subscores(
    *,
    qualified_resource: QualifiedResource,
    ai_confidence_score: int,
    feedback: PedagogicalFeedbackProfile,
) -> PedagogicalImageSubscores:
    technical_score = _map_technical_quality(qualified_resource.technical_quality)
    diagnostic_visibility_score = _map_diagnostic_visibility(
        qualified_resource.diagnostic_feature_visibility
    )
    pedagogical_quality_score = _map_pedagogical_quality(qualified_resource.pedagogical_quality)
    learning_suitability_score = _map_learning_suitability(
        qualified_resource.learning_suitability
    )
    view_angle_score = _map_view_angle(qualified_resource.view_angle)
    uncertainty_penalty = _uncertainty_penalty(qualified_resource.uncertainty_reason)

    visible_parts_count = len(_dedupe_non_blank(qualified_resource.visible_parts))
    visible_parts_score = min(100, visible_parts_count * 20)

    subject_visibility = _clamp(
        (visible_parts_score * 0.45)
        + (diagnostic_visibility_score * 0.35)
        + (view_angle_score * 0.20)
        - (uncertainty_penalty * 0.35)
    )

    diagnostic_value = _clamp(
        (diagnostic_visibility_score * 0.60)
        + (learning_suitability_score * 0.25)
        + (visible_parts_score * 0.15)
    )

    pedagogical_clarity = _clamp(
        (pedagogical_quality_score * 0.65)
        + (learning_suitability_score * 0.25)
        + (100 - uncertainty_penalty * 2) * 0.10
    )

    representativeness = _clamp(
        (_map_media_role(qualified_resource.media_role) * 0.70) + (view_angle_score * 0.30)
    )

    difficulty_fit = _map_difficulty_fit(qualified_resource.difficulty_level)

    feedback_potential = _clamp(
        (visible_parts_score * 0.45)
        + (diagnostic_visibility_score * 0.30)
        + (20 if feedback.feedback_short else 0)
        + (10 if _has_post_answer_feedback(feedback) else 0)
    )

    confusion_potential = _clamp(
        (_map_confusion_relevance(qualified_resource.confusion_relevance) * 0.70)
        + (diagnostic_visibility_score * 0.20)
        + (visible_parts_score * 0.10)
    )

    context_value = _clamp(
        (_map_context_value(qualified_resource.media_role) * 0.75)
        + (view_angle_score * 0.10)
        + (visible_parts_score * 0.15)
    )

    return PedagogicalImageSubscores(
        technical_quality=technical_score,
        subject_visibility=subject_visibility,
        diagnostic_value=diagnostic_value,
        pedagogical_clarity=pedagogical_clarity,
        representativeness=representativeness,
        difficulty_fit=difficulty_fit,
        feedback_potential=feedback_potential,
        confusion_potential=confusion_potential,
        context_value=context_value,
        confidence=ai_confidence_score,
    )


def _compute_overall_score(subscores: PedagogicalImageSubscores) -> int:
    return _clamp(
        (subscores.technical_quality * 0.20)
        + (subscores.subject_visibility * 0.20)
        + (subscores.diagnostic_value * 0.25)
        + (subscores.pedagogical_clarity * 0.15)
        + (subscores.representativeness * 0.10)
        + (subscores.feedback_potential * 0.05)
        + (subscores.confidence * 0.05)
    )


def _compute_usage_scores(
    *,
    qualified_resource: QualifiedResource,
    subscores: PedagogicalImageSubscores,
    feedback: PedagogicalFeedbackProfile,
    technical_primary_block: bool,
) -> PedagogicalUsageScores:
    uncertainty_penalty = _uncertainty_penalty(qualified_resource.uncertainty_reason)

    beginner = _clamp(
        (subscores.technical_quality * 0.30)
        + (subscores.subject_visibility * 0.30)
        + (subscores.diagnostic_value * 0.25)
        + (subscores.pedagogical_clarity * 0.15)
        + _beginner_difficulty_adjustment(qualified_resource.difficulty_level)
        - (uncertainty_penalty * 0.40)
    )

    intermediate = _clamp(
        (subscores.technical_quality * 0.25)
        + (subscores.subject_visibility * 0.25)
        + (subscores.diagnostic_value * 0.30)
        + (subscores.pedagogical_clarity * 0.20)
        + _intermediate_difficulty_adjustment(qualified_resource.difficulty_level)
        - (uncertainty_penalty * 0.25)
    )

    expert = _clamp(
        (subscores.technical_quality * 0.20)
        + (subscores.subject_visibility * 0.20)
        + (subscores.diagnostic_value * 0.35)
        + (subscores.pedagogical_clarity * 0.15)
        + (subscores.confusion_potential * 0.10)
        + _expert_difficulty_adjustment(qualified_resource.difficulty_level)
        - (uncertainty_penalty * 0.15)
    )

    context_learning = _clamp(
        (subscores.context_value * 0.60)
        + (subscores.subject_visibility * 0.20)
        + (subscores.pedagogical_clarity * 0.20)
    )

    confusion_training = _clamp(
        (subscores.confusion_potential * 0.60)
        + (subscores.diagnostic_value * 0.20)
        + (subscores.subject_visibility * 0.20)
    )

    feedback_explanation = _clamp(
        (subscores.feedback_potential * 0.50)
        + (subscores.diagnostic_value * 0.20)
        + (subscores.subject_visibility * 0.15)
        + (subscores.confidence * 0.15)
    )

    if qualified_resource.confusion_relevance == ConfusionRelevance.NONE:
        confusion_training = min(confusion_training, 45)

    if technical_primary_block:
        beginner = min(beginner, 25)
        intermediate = min(intermediate, 35)

    if qualified_resource.media_role in {MediaRole.CONTEXT, MediaRole.NON_DIAGNOSTIC}:
        beginner = min(beginner, 35)

    if not _has_feedback_signal(feedback):
        feedback_explanation = min(feedback_explanation, 35)

    return PedagogicalUsageScores(
        primary_question_beginner=beginner,
        primary_question_intermediate=intermediate,
        primary_question_expert=expert,
        context_learning=context_learning,
        confusion_training=confusion_training,
        feedback_explanation=feedback_explanation,
    )


def _resolve_profile_status(
    *,
    blocked_status: PedagogicalProfileStatus | None,
    ai_context: _AiContext,
    warnings: list[str],
    has_recommended_candidate: bool,
) -> PedagogicalProfileStatus:
    if blocked_status is not None:
        return blocked_status

    if ai_context.confidence_score < CONFIDENCE_MANUAL_REVIEW_THRESHOLD:
        return PedagogicalProfileStatus.MANUAL_REVIEW_REQUIRED

    if not has_recommended_candidate:
        return PedagogicalProfileStatus.MANUAL_REVIEW_REQUIRED

    if any(signal in warnings for signal in MANUAL_REVIEW_WARNING_SIGNALS):
        return PedagogicalProfileStatus.MANUAL_REVIEW_REQUIRED

    if warnings:
        return PedagogicalProfileStatus.PROFILED_WITH_WARNINGS

    return PedagogicalProfileStatus.PROFILED


def _has_recommended_usage_candidate(usage_scores: PedagogicalUsageScores) -> bool:
    return any(
        score >= RECOMMENDED_USAGE_THRESHOLD
        for score in (
            usage_scores.primary_question_beginner,
            usage_scores.primary_question_intermediate,
            usage_scores.primary_question_expert,
            usage_scores.context_learning,
            usage_scores.confusion_training,
            usage_scores.feedback_explanation,
        )
    )


def _collect_ai_resource_divergence_reason_codes(
    *,
    qualified_resource: QualifiedResource,
    ai_outcome: AIQualificationOutcome | None,
) -> list[str]:
    if ai_outcome is None or ai_outcome.qualification is None:
        return []

    ai_qualification = ai_outcome.qualification
    reason_codes: list[str] = []

    _append_divergence_if_mismatch(
        reason_codes,
        field_name="technical_quality",
        ai_value=ai_qualification.technical_quality,
        resource_value=qualified_resource.technical_quality,
    )
    _append_divergence_if_mismatch(
        reason_codes,
        field_name="pedagogical_quality",
        ai_value=ai_qualification.pedagogical_quality,
        resource_value=qualified_resource.pedagogical_quality,
    )
    _append_divergence_if_mismatch(
        reason_codes,
        field_name="view_angle",
        ai_value=ai_qualification.view_angle,
        resource_value=qualified_resource.view_angle,
    )
    _append_divergence_if_mismatch(
        reason_codes,
        field_name="difficulty_level",
        ai_value=ai_qualification.difficulty_level,
        resource_value=qualified_resource.difficulty_level,
    )
    _append_divergence_if_mismatch(
        reason_codes,
        field_name="media_role",
        ai_value=ai_qualification.media_role,
        resource_value=qualified_resource.media_role,
    )
    _append_divergence_if_mismatch(
        reason_codes,
        field_name="confusion_relevance",
        ai_value=ai_qualification.confusion_relevance,
        resource_value=qualified_resource.confusion_relevance,
    )
    _append_divergence_if_mismatch(
        reason_codes,
        field_name="diagnostic_feature_visibility",
        ai_value=ai_qualification.diagnostic_feature_visibility,
        resource_value=qualified_resource.diagnostic_feature_visibility,
    )
    _append_divergence_if_mismatch(
        reason_codes,
        field_name="learning_suitability",
        ai_value=ai_qualification.learning_suitability,
        resource_value=qualified_resource.learning_suitability,
    )
    _append_divergence_if_mismatch(
        reason_codes,
        field_name="uncertainty_reason",
        ai_value=ai_qualification.uncertainty_reason,
        resource_value=qualified_resource.uncertainty_reason,
    )

    ai_visible_parts = set(_dedupe_non_blank(ai_qualification.visible_parts))
    resource_visible_parts = set(_dedupe_non_blank(qualified_resource.visible_parts))
    if ai_visible_parts and resource_visible_parts and ai_visible_parts != resource_visible_parts:
        reason_codes.append("divergence_visible_parts")

    if qualified_resource.ai_confidence is not None:
        confidence_delta = abs(ai_qualification.confidence - qualified_resource.ai_confidence)
        if confidence_delta > AI_RESOURCE_DIVERGENCE_CONFIDENCE_DELTA:
            reason_codes.append("divergence_ai_confidence")

    provenance_ai_status = (qualified_resource.provenance_summary.ai_status or "").strip()
    if provenance_ai_status and ai_outcome.status and ai_outcome.status != provenance_ai_status:
        reason_codes.append("divergence_ai_status")

    return list(dict.fromkeys(reason_codes))


def _append_divergence_if_mismatch(
    reason_codes: list[str],
    *,
    field_name: str,
    ai_value: object,
    resource_value: object,
) -> None:
    if str(ai_value) != str(resource_value):
        reason_codes.append(f"divergence_{field_name}")


def _resolve_usage_classification(
    *,
    status: PedagogicalProfileStatus,
    usage_scores: PedagogicalUsageScores,
    technical_primary_block: bool,
) -> tuple[list[PedagogicalUsage], list[PedagogicalUsage]]:
    usage_by_score = {
        PedagogicalUsage.PRIMARY_QUESTION_BEGINNER: usage_scores.primary_question_beginner,
        PedagogicalUsage.PRIMARY_QUESTION_INTERMEDIATE: usage_scores.primary_question_intermediate,
        PedagogicalUsage.PRIMARY_QUESTION_EXPERT: usage_scores.primary_question_expert,
        PedagogicalUsage.CONTEXT_LEARNING: usage_scores.context_learning,
        PedagogicalUsage.CONFUSION_TRAINING: usage_scores.confusion_training,
        PedagogicalUsage.FEEDBACK_EXPLANATION: usage_scores.feedback_explanation,
    }

    recommended: list[PedagogicalUsage] = []
    avoid: list[PedagogicalUsage] = []

    primary_usages = {
        PedagogicalUsage.PRIMARY_QUESTION_BEGINNER,
        PedagogicalUsage.PRIMARY_QUESTION_INTERMEDIATE,
        PedagogicalUsage.PRIMARY_QUESTION_EXPERT,
    }

    if status in {
        PedagogicalProfileStatus.PROFILED,
        PedagogicalProfileStatus.PROFILED_WITH_WARNINGS,
    }:
        for usage, score in usage_by_score.items():
            if technical_primary_block and usage in primary_usages:
                continue
            if score >= RECOMMENDED_USAGE_THRESHOLD:
                recommended.append(usage)

    for usage, score in usage_by_score.items():
        if technical_primary_block and usage in primary_usages:
            avoid.append(usage)
            continue
        if score <= AVOID_USAGE_THRESHOLD:
            avoid.append(usage)

    return recommended, list(dict.fromkeys(avoid))


def _build_feedback_profile(
    *,
    qualified_resource: QualifiedResource,
    ai_outcome: AIQualificationOutcome | None,
) -> PedagogicalFeedbackProfile:
    what_to_look_at = _dedupe_non_blank(qualified_resource.visible_parts)
    ai_note = _extract_ai_note(ai_outcome=ai_outcome, qualified_resource=qualified_resource)
    v12_feedback_profile = _build_feedback_profile_from_v12_review(
        ai_outcome=ai_outcome,
        fallback_what_to_look_at=what_to_look_at,
        ai_note=ai_note,
        qualified_resource=qualified_resource,
    )
    if v12_feedback_profile is not None:
        return v12_feedback_profile

    focus_parts = what_to_look_at[:3]
    focus_phrase = _format_focus_parts(focus_parts)
    primary_focus = focus_parts[0] if focus_parts else "la silhouette generale"

    if focus_phrase:
        feedback_short = f"Sur cette image, les indices les plus utiles sont {focus_phrase}."
        incorrect_short = (
            f"Pas tout a fait. Sur cette image, regarde d'abord {focus_phrase}."
        )
    else:
        feedback_short = (
            "Sur cette image, les meilleurs reperes sont la silhouette generale "
            "et la forme du bec."
        )
        incorrect_short = (
            "Pas tout a fait. Sur cette image, commence par la silhouette generale "
            "puis verifie la forme du bec."
        )

    correct_long_parts = [
        f"Sur cette image, le detail le plus utile est {primary_focus}.",
        (
            f"Ici, la combinaison {focus_phrase} aide a confirmer l'identification."
            if focus_phrase
            else "Ici, combine silhouette, posture et bec pour limiter les confusions."
        ),
        (
            "Pour progresser, privilegie la combinaison de plusieurs criteres visibles "
            "plutot qu'un seul detail."
        ),
        ai_note,
    ]
    correct_long = _join_sentences(correct_long_parts) or feedback_short

    incorrect_long_parts = [
        f"Sur cette image, commence par verifier {primary_focus}.",
        (
            f"Ensuite, controle {focus_phrase} avant de valider la reponse."
            if focus_phrase
            else (
                "Ensuite, controle la posture et la silhouette generale "
                "avant de valider la reponse."
            )
        ),
        "Cette sequence aide a distinguer les especes proches sur une photo similaire.",
    ]
    incorrect_long = _join_sentences(incorrect_long_parts) or incorrect_short

    why_good_example: list[str] = []
    if qualified_resource.technical_quality in {TechnicalQuality.HIGH, TechnicalQuality.MEDIUM}:
        why_good_example.append("Image quality is sufficient for identification use.")
    if qualified_resource.diagnostic_feature_visibility in {
        DiagnosticFeatureVisibility.HIGH,
        DiagnosticFeatureVisibility.MEDIUM,
    }:
        why_good_example.append("Diagnostic features are visible enough for learning.")

    why_not_ideal: list[str] = []
    if qualified_resource.technical_quality == TechnicalQuality.LOW:
        why_not_ideal.append("Low technical quality limits primary-question usage.")
    if qualified_resource.uncertainty_reason != UncertaintyReason.NONE:
        why_not_ideal.append(
            f"Uncertainty signal present: {qualified_resource.uncertainty_reason.value}."
        )
    if not what_to_look_at:
        why_not_ideal.append("No clear visible-part cue extracted for focused feedback.")

    identification_tips = _build_identification_tips(
        focus_parts=focus_parts,
        focus_phrase=focus_phrase,
    )

    feedback_confidence = _clamp(
        (_to_percent(qualified_resource.ai_confidence) * 0.70)
        + (20 if feedback_short and incorrect_short else 0)
        + (10 if len(identification_tips) >= 2 else 0)
    )

    post_answer_feedback = PostAnswerFeedback(
        correct=PostAnswerFeedbackVariant(
            short=feedback_short,
            long=correct_long,
        ),
        incorrect=PostAnswerFeedbackVariant(
            short=incorrect_short,
            long=incorrect_long,
        ),
        identification_tips=identification_tips,
        confidence=feedback_confidence,
    )

    feedback_long_parts = [
        correct_long,
        why_good_example[0] if why_good_example else None,
        why_not_ideal[0] if why_not_ideal else None,
    ]
    feedback_long = _join_sentences(feedback_long_parts)

    return PedagogicalFeedbackProfile(
        feedback_short=feedback_short,
        feedback_long=feedback_long,
        what_to_look_at=what_to_look_at,
        why_good_example=why_good_example,
        why_not_ideal=why_not_ideal,
        beginner_hint=None,
        expert_hint=None,
        confusion_hint=None,
        post_answer_feedback=post_answer_feedback,
        feedback_confidence=feedback_confidence,
    )


def _build_feedback_profile_from_v12_review(
    *,
    ai_outcome: AIQualificationOutcome | None,
    fallback_what_to_look_at: list[str],
    ai_note: str | None,
    qualified_resource: QualifiedResource,
) -> PedagogicalFeedbackProfile | None:
    review_payload = _as_mapping(
        ai_outcome.bird_image_pedagogical_review if ai_outcome is not None else None
    )
    if review_payload.get("status") != "success":
        return None

    post_answer_feedback_payload = _as_mapping(review_payload.get("post_answer_feedback"))
    correct_payload = _as_mapping(post_answer_feedback_payload.get("correct"))
    incorrect_payload = _as_mapping(post_answer_feedback_payload.get("incorrect"))

    correct_short = _first_non_blank([_as_text(correct_payload.get("short"))])
    correct_long = _first_non_blank([_as_text(correct_payload.get("long"))])
    incorrect_short = _first_non_blank([_as_text(incorrect_payload.get("short"))])
    incorrect_long = _first_non_blank([_as_text(incorrect_payload.get("long"))])
    identification_tips = _dedupe_non_blank(
        _as_string_list(post_answer_feedback_payload.get("identification_tips"))
    )

    if (
        correct_short is None
        or correct_long is None
        or incorrect_short is None
        or incorrect_long is None
        or len(identification_tips) < 2
    ):
        return None

    limitations_payload = _as_mapping(review_payload.get("limitations"))
    why_not_ideal = _dedupe_non_blank(_as_string_list(limitations_payload.get("why_not_ideal")))

    feature_payload = review_payload.get("identification_features_visible_in_this_image")
    feature_parts: list[str] = []
    if isinstance(feature_payload, Sequence) and not isinstance(feature_payload, (str, bytes)):
        for item in feature_payload:
            if not isinstance(item, Mapping):
                continue
            part = _as_text(item.get("body_part"))
            if part:
                feature_parts.append(part)

    what_to_look_at = _dedupe_non_blank([*fallback_what_to_look_at, *feature_parts])

    pedagogical_assessment = _as_mapping(review_payload.get("pedagogical_assessment"))
    image_assessment = _as_mapping(review_payload.get("image_assessment"))
    why_good_example: list[str] = []
    if _as_text(image_assessment.get("technical_quality")) in {"high", "medium"}:
        why_good_example.append("Image quality is sufficient for identification use.")
    if _as_text(pedagogical_assessment.get("diagnostic_feature_visibility")) in {
        "high",
        "medium",
    }:
        why_good_example.append("Diagnostic features are visible enough for learning.")

    feedback_confidence = _normalize_review_feedback_confidence(
        post_answer_feedback_payload.get("confidence")
    )
    if feedback_confidence == 0:
        feedback_confidence = _clamp(_to_percent(qualified_resource.ai_confidence))

    post_answer_feedback = PostAnswerFeedback(
        correct=PostAnswerFeedbackVariant(short=correct_short, long=correct_long),
        incorrect=PostAnswerFeedbackVariant(short=incorrect_short, long=incorrect_long),
        identification_tips=identification_tips,
        confidence=feedback_confidence,
    )

    feedback_long = _join_sentences(
        [
            correct_long,
            ai_note if ai_note and ai_note not in correct_long else None,
            why_good_example[0] if why_good_example else None,
            why_not_ideal[0] if why_not_ideal else None,
        ]
    )

    return PedagogicalFeedbackProfile(
        feedback_short=correct_short,
        feedback_long=feedback_long or correct_long,
        what_to_look_at=what_to_look_at,
        why_good_example=why_good_example,
        why_not_ideal=why_not_ideal,
        beginner_hint=None,
        expert_hint=None,
        confusion_hint=None,
        post_answer_feedback=post_answer_feedback,
        feedback_confidence=feedback_confidence,
    )


def _has_feedback_signal(feedback: PedagogicalFeedbackProfile) -> bool:
    if feedback.feedback_short is not None and feedback.feedback_short.strip():
        return True
    if feedback.what_to_look_at:
        return True
    return _has_post_answer_feedback(feedback)


def _has_post_answer_feedback(feedback: PedagogicalFeedbackProfile) -> bool:
    post_answer_feedback = feedback.post_answer_feedback
    if post_answer_feedback is None:
        return False
    if len(post_answer_feedback.identification_tips) < 2:
        return False
    return all(
        value is not None and value.strip()
        for value in (
            post_answer_feedback.correct.short,
            post_answer_feedback.correct.long,
            post_answer_feedback.incorrect.short,
            post_answer_feedback.incorrect.long,
        )
    )


def _build_identification_tips(
    *,
    focus_parts: list[str],
    focus_phrase: str | None,
) -> list[str]:
    tips: list[str] = []
    for part in focus_parts:
        tips.append(f"Sur cette image, repere d'abord {part}.")
    if focus_phrase:
        tips.append(f"Ici, combine {focus_phrase} plutot qu'un seul indice.")
    if len(tips) < 2:
        tips.append("Sur cette image, verifie la silhouette generale avant les details fins.")
    if len(tips) < 2:
        tips.append("Ici, combine couleur, bec et posture pour confirmer l'identification.")
    return _dedupe_non_blank(tips)


def _format_focus_parts(parts: list[str]) -> str | None:
    cleaned = _dedupe_non_blank(parts)
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} et {cleaned[1]}"
    return f"{cleaned[0]}, {cleaned[1]} et {cleaned[2]}"


def _build_bird_image_features(
    qualified_resource: QualifiedResource,
) -> BirdImagePedagogicalFeatures:
    visible_parts = _dedupe_non_blank(qualified_resource.visible_parts)
    field_marks = [part for part in visible_parts if part in FIELD_MARK_PARTS]

    sex_life_stage_relevance = None
    if qualified_resource.sex.value != "unknown" or qualified_resource.life_stage != "unknown":
        sex_life_stage_relevance = (
            f"sex={qualified_resource.sex.value};life_stage={qualified_resource.life_stage}"
        )

    habitat_visible = None
    if qualified_resource.media_role == MediaRole.CONTEXT:
        habitat_visible = "context_visible"

    pose = qualified_resource.view_angle.value
    if qualified_resource.view_angle == ViewAngle.UNKNOWN:
        pose = None

    plumage_visibility = qualified_resource.diagnostic_feature_visibility.value
    if qualified_resource.diagnostic_feature_visibility == DiagnosticFeatureVisibility.UNKNOWN:
        plumage_visibility = None

    return BirdImagePedagogicalFeatures(
        visible_bird_parts=visible_parts,
        pose=pose,
        plumage_visibility=plumage_visibility,
        field_marks_visible=field_marks,
        sex_or_life_stage_relevance=sex_life_stage_relevance,
        habitat_visible=habitat_visible,
    )


def _score_band_from_score(score: int) -> PedagogicalScoreBand:
    if score >= 85:
        return PedagogicalScoreBand.A
    if score >= 70:
        return PedagogicalScoreBand.B
    if score >= 55:
        return PedagogicalScoreBand.C
    if score >= 40:
        return PedagogicalScoreBand.D
    return PedagogicalScoreBand.E


def _map_technical_quality(value: TechnicalQuality) -> int:
    mapping = {
        TechnicalQuality.HIGH: 92,
        TechnicalQuality.MEDIUM: 70,
        TechnicalQuality.LOW: 25,
        TechnicalQuality.UNKNOWN: 45,
    }
    return mapping[value]


def _map_pedagogical_quality(value: PedagogicalQuality) -> int:
    mapping = {
        PedagogicalQuality.HIGH: 90,
        PedagogicalQuality.MEDIUM: 70,
        PedagogicalQuality.LOW: 35,
        PedagogicalQuality.UNKNOWN: 45,
    }
    return mapping[value]


def _map_diagnostic_visibility(value: DiagnosticFeatureVisibility) -> int:
    mapping = {
        DiagnosticFeatureVisibility.HIGH: 90,
        DiagnosticFeatureVisibility.MEDIUM: 70,
        DiagnosticFeatureVisibility.LOW: 35,
        DiagnosticFeatureVisibility.UNKNOWN: 45,
    }
    return mapping[value]


def _map_learning_suitability(value: object) -> int:
    normalized = str(value)
    mapping = {
        "high": 90,
        "medium": 70,
        "low": 35,
        "unknown": 45,
    }
    return mapping.get(normalized, 45)


def _map_view_angle(value: ViewAngle) -> int:
    if value == ViewAngle.UNKNOWN:
        return 45
    if value == ViewAngle.CLOSE_UP:
        return 88
    return 75


def _map_media_role(value: MediaRole) -> int:
    mapping = {
        MediaRole.PRIMARY_ID: 90,
        MediaRole.CONTEXT: 68,
        MediaRole.DISTRACTOR_RISK: 45,
        MediaRole.NON_DIAGNOSTIC: 25,
    }
    return mapping[value]


def _map_context_value(value: MediaRole) -> int:
    mapping = {
        MediaRole.CONTEXT: 90,
        MediaRole.PRIMARY_ID: 45,
        MediaRole.DISTRACTOR_RISK: 40,
        MediaRole.NON_DIAGNOSTIC: 30,
    }
    return mapping[value]


def _map_confusion_relevance(value: ConfusionRelevance) -> int:
    mapping = {
        ConfusionRelevance.NONE: 20,
        ConfusionRelevance.LOW: 45,
        ConfusionRelevance.MEDIUM: 70,
        ConfusionRelevance.HIGH: 90,
    }
    return mapping[value]


def _map_difficulty_fit(value: DifficultyLevel) -> int:
    mapping = {
        DifficultyLevel.EASY: 85,
        DifficultyLevel.MEDIUM: 80,
        DifficultyLevel.HARD: 60,
        DifficultyLevel.UNKNOWN: 45,
    }
    return mapping[value]


def _beginner_difficulty_adjustment(value: DifficultyLevel) -> int:
    mapping = {
        DifficultyLevel.EASY: 10,
        DifficultyLevel.MEDIUM: 5,
        DifficultyLevel.HARD: -15,
        DifficultyLevel.UNKNOWN: -10,
    }
    return mapping[value]


def _intermediate_difficulty_adjustment(value: DifficultyLevel) -> int:
    mapping = {
        DifficultyLevel.EASY: 4,
        DifficultyLevel.MEDIUM: 8,
        DifficultyLevel.HARD: 2,
        DifficultyLevel.UNKNOWN: -8,
    }
    return mapping[value]


def _expert_difficulty_adjustment(value: DifficultyLevel) -> int:
    mapping = {
        DifficultyLevel.EASY: -6,
        DifficultyLevel.MEDIUM: 6,
        DifficultyLevel.HARD: 12,
        DifficultyLevel.UNKNOWN: -5,
    }
    return mapping[value]


def _uncertainty_penalty(value: UncertaintyReason) -> int:
    mapping = {
        UncertaintyReason.NONE: 0,
        UncertaintyReason.OCCLUSION: 20,
        UncertaintyReason.ANGLE: 12,
        UncertaintyReason.DISTANCE: 12,
        UncertaintyReason.MOTION: 18,
        UncertaintyReason.MULTIPLE_SUBJECTS: 20,
        UncertaintyReason.MODEL_UNCERTAIN: 22,
        UncertaintyReason.TAXONOMY_AMBIGUOUS: 25,
    }
    return mapping[value]


def _extract_ai_note(
    *,
    ai_outcome: AIQualificationOutcome | None,
    qualified_resource: QualifiedResource,
) -> str | None:
    if ai_outcome is not None:
        if ai_outcome.qualification is not None and ai_outcome.qualification.notes:
            return ai_outcome.qualification.notes.strip()
        if ai_outcome.note:
            return ai_outcome.note.strip()
    if qualified_resource.qualification_notes:
        note = qualified_resource.qualification_notes.strip()
        if note:
            return note
    return None


def _reason_to_sentence(reason_code: str) -> str:
    return reason_code.replace("_", " ").strip().capitalize() + "."


def _join_sentences(parts: list[str | None]) -> str | None:
    cleaned = [part.strip() for part in parts if part and part.strip()]
    if not cleaned:
        return None
    return " ".join(cleaned)


def _first_non_blank(values: list[str | None]) -> str | None:
    for value in values:
        if value and value.strip():
            return value.strip()
    return None


def _as_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _as_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    return [text]


def _as_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_review_feedback_confidence(value: object) -> int:
    if value is None:
        return 0
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0
    if numeric < 0:
        return 0
    if numeric <= 1:
        return _clamp(round(numeric * 100))
    return _clamp(round(numeric))


def _dedupe_non_blank(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def _to_percent(value: float | None) -> int:
    if value is None:
        return 0
    return _clamp(round(float(value) * 100))


def _clamp(value: float | int) -> int:
    return max(0, min(100, int(round(value))))
