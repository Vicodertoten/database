from __future__ import annotations

from database_core.domain.enums import (
    ConfusionRelevance,
    DiagnosticFeatureVisibility,
    DifficultyLevel,
    LearningSuitability,
    LicenseSafetyResult,
    MediaRole,
    PedagogicalQuality,
    QualificationStage,
    QualificationStatus,
    ReviewPriority,
    TechnicalQuality,
    UncertaintyReason,
)
from database_core.domain.models import AIQualification, MediaAsset
from database_core.qualification.ai import AIQualificationOutcome

SAFE_LICENSES = {"cc0", "cc-by", "cc-by-sa", "public domain", "pd"}
UNSAFE_LICENSE_MARKERS = ("nc", "nd", "all rights reserved")
AI_CONFIDENCE_THRESHOLD = 0.8
MIN_ACCEPTED_WIDTH = 1000
MIN_ACCEPTED_HEIGHT = 750

COMPLIANCE_REJECTION_FLAGS = ("unsupported_media_type", "unsafe_license")
FAST_SCREENING_FLAGS = (
    "missing_cached_image",
    "missing_cached_ai_output",
    "cached_prompt_version_mismatch",
    "gemini_error",
    "invalid_gemini_json",
    "missing_fixture_ai_output",
    "insufficient_resolution",
    "insufficient_resolution_pre_ai",
    "decode_error_pre_ai",
    "blur_pre_ai",
    "duplicate_pre_ai",
)
EXPERT_REVIEW_FLAGS = (
    "incomplete_required_tags",
    "low_ai_confidence",
    "missing_visible_parts",
    "missing_view_angle",
    "insufficient_technical_quality",
)
REVIEW_PRIORITY_BY_REASON = {
    "cached_prompt_version_mismatch": ReviewPriority.HIGH,
    "gemini_error": ReviewPriority.HIGH,
    "invalid_gemini_json": ReviewPriority.HIGH,
    "missing_cached_ai_output": ReviewPriority.HIGH,
    "missing_cached_image": ReviewPriority.HIGH,
    "human_override": ReviewPriority.HIGH,
    "insufficient_resolution": ReviewPriority.MEDIUM,
    "insufficient_resolution_pre_ai": ReviewPriority.MEDIUM,
    "decode_error_pre_ai": ReviewPriority.MEDIUM,
    "blur_pre_ai": ReviewPriority.MEDIUM,
    "duplicate_pre_ai": ReviewPriority.MEDIUM,
    "low_ai_confidence": ReviewPriority.MEDIUM,
    "missing_visible_parts": ReviewPriority.MEDIUM,
    "missing_view_angle": ReviewPriority.MEDIUM,
    "insufficient_technical_quality": ReviewPriority.MEDIUM,
    "incomplete_required_tags": ReviewPriority.MEDIUM,
    "review_required": ReviewPriority.LOW,
}
REVIEW_STAGE_BY_REASON = {
    "human_override": QualificationStage.REVIEW_QUEUE_ASSEMBLY,
    "cached_prompt_version_mismatch": QualificationStage.FAST_SEMANTIC_SCREENING,
    "gemini_error": QualificationStage.FAST_SEMANTIC_SCREENING,
    "invalid_gemini_json": QualificationStage.FAST_SEMANTIC_SCREENING,
    "missing_cached_ai_output": QualificationStage.FAST_SEMANTIC_SCREENING,
    "missing_cached_image": QualificationStage.FAST_SEMANTIC_SCREENING,
    "insufficient_resolution": QualificationStage.FAST_SEMANTIC_SCREENING,
    "insufficient_resolution_pre_ai": QualificationStage.FAST_SEMANTIC_SCREENING,
    "decode_error_pre_ai": QualificationStage.FAST_SEMANTIC_SCREENING,
    "blur_pre_ai": QualificationStage.FAST_SEMANTIC_SCREENING,
    "duplicate_pre_ai": QualificationStage.FAST_SEMANTIC_SCREENING,
    "low_ai_confidence": QualificationStage.EXPERT_QUALIFICATION,
    "missing_visible_parts": QualificationStage.EXPERT_QUALIFICATION,
    "missing_view_angle": QualificationStage.EXPERT_QUALIFICATION,
    "insufficient_technical_quality": QualificationStage.EXPERT_QUALIFICATION,
    "incomplete_required_tags": QualificationStage.EXPERT_QUALIFICATION,
    "review_required": QualificationStage.REVIEW_QUEUE_ASSEMBLY,
}
PRIMARY_REVIEW_REASON_ORDER = (
    "human_override",
    "cached_prompt_version_mismatch",
    "missing_cached_image",
    "missing_cached_ai_output",
    "invalid_gemini_json",
    "gemini_error",
    "insufficient_resolution",
    "insufficient_resolution_pre_ai",
    "decode_error_pre_ai",
    "blur_pre_ai",
    "duplicate_pre_ai",
    "incomplete_required_tags",
    "low_ai_confidence",
    "missing_visible_parts",
    "missing_view_angle",
    "insufficient_technical_quality",
)


def evaluate_license_safety(
    *, media_license: str | None, observation_license: str | None
) -> LicenseSafetyResult:
    media_result = _single_license_result(media_license)
    observation_result = _single_license_result(observation_license)

    if LicenseSafetyResult.UNSAFE in {media_result, observation_result}:
        return LicenseSafetyResult.UNSAFE
    if LicenseSafetyResult.REVIEW_REQUIRED in {media_result, observation_result}:
        return LicenseSafetyResult.REVIEW_REQUIRED
    return LicenseSafetyResult.SAFE


def is_safe_license(license_code: str | None) -> bool:
    return _single_license_result(license_code) == LicenseSafetyResult.SAFE


def resolve_qualification_status(
    flags: list[str],
    *,
    uncertain_policy: str,
) -> QualificationStatus:
    if uncertain_policy not in {"review", "reject"}:
        raise ValueError(f"Unsupported uncertain_policy: {uncertain_policy}")
    if any(flag in flags for flag in COMPLIANCE_REJECTION_FLAGS):
        return QualificationStatus.REJECTED
    if any(flag in flags for flag in FAST_SCREENING_FLAGS + EXPERT_REVIEW_FLAGS):
        if uncertain_policy == "review":
            return QualificationStatus.REVIEW_REQUIRED
        return QualificationStatus.REJECTED
    return QualificationStatus.ACCEPTED


def resolve_technical_quality(
    media_asset: MediaAsset,
    ai_qualification: AIQualification | None,
) -> TechnicalQuality:
    if ai_qualification and ai_qualification.confidence >= AI_CONFIDENCE_THRESHOLD:
        return ai_qualification.technical_quality

    if media_asset.width is None or media_asset.height is None:
        return TechnicalQuality.UNKNOWN
    if media_asset.width >= 1400 and media_asset.height >= 1000:
        return TechnicalQuality.HIGH
    if media_asset.width >= 1000 and media_asset.height >= 750:
        return TechnicalQuality.MEDIUM
    return TechnicalQuality.LOW


def resolve_pedagogical_quality(ai_qualification: AIQualification | None) -> PedagogicalQuality:
    if ai_qualification and ai_qualification.confidence >= AI_CONFIDENCE_THRESHOLD:
        return ai_qualification.pedagogical_quality
    return PedagogicalQuality.UNKNOWN


def resolve_difficulty_level(ai_qualification: AIQualification | None) -> DifficultyLevel:
    if ai_qualification and ai_qualification.confidence >= AI_CONFIDENCE_THRESHOLD:
        return ai_qualification.difficulty_level
    return DifficultyLevel.UNKNOWN


def resolve_media_role(ai_qualification: AIQualification | None) -> MediaRole:
    if ai_qualification and ai_qualification.confidence >= AI_CONFIDENCE_THRESHOLD:
        return ai_qualification.media_role
    return MediaRole.CONTEXT


def resolve_confusion_relevance(ai_qualification: AIQualification | None) -> ConfusionRelevance:
    if ai_qualification and ai_qualification.confidence >= AI_CONFIDENCE_THRESHOLD:
        return ai_qualification.confusion_relevance
    return ConfusionRelevance.NONE


def resolve_diagnostic_feature_visibility(
    ai_qualification: AIQualification | None,
) -> DiagnosticFeatureVisibility:
    if ai_qualification and ai_qualification.confidence >= AI_CONFIDENCE_THRESHOLD:
        return ai_qualification.diagnostic_feature_visibility
    return DiagnosticFeatureVisibility.UNKNOWN


def resolve_learning_suitability(ai_qualification: AIQualification | None) -> LearningSuitability:
    if ai_qualification and ai_qualification.confidence >= AI_CONFIDENCE_THRESHOLD:
        return ai_qualification.learning_suitability
    return LearningSuitability.UNKNOWN


def resolve_uncertainty_reason(ai_qualification: AIQualification | None) -> UncertaintyReason:
    if ai_qualification and ai_qualification.confidence >= AI_CONFIDENCE_THRESHOLD:
        return ai_qualification.uncertainty_reason
    return UncertaintyReason.NONE


def build_notes(
    flags: list[str],
    ai_qualification: AIQualification | None,
    ai_outcome: AIQualificationOutcome | None,
) -> str:
    note_parts: list[str] = []
    if flags:
        note_parts.append(",".join(flags))
    if ai_outcome and ai_outcome.note:
        note_parts.append(ai_outcome.note)
    if ai_qualification and ai_qualification.notes:
        note_parts.append(ai_qualification.notes)
    unique_note_parts = list(dict.fromkeys(part for part in note_parts if part))
    return " | ".join(unique_note_parts)


def primary_review_reason_code(flags: list[str]) -> str:
    for reason_code in PRIMARY_REVIEW_REASON_ORDER:
        if reason_code in flags:
            return reason_code
    return "review_required"


def qualification_method(
    *,
    ai_qualification: AIQualification | None,
    ai_outcome: AIQualificationOutcome | None,
) -> str:
    if ai_qualification:
        if ai_qualification.model_name.startswith("gemini"):
            return "gemini_plus_rules"
        return "fixture_ai_plus_rules"
    if ai_outcome:
        return "ai_attempt_plus_rules"
    return "rules_only"


def _single_license_result(license_code: str | None) -> LicenseSafetyResult:
    if license_code is None:
        return LicenseSafetyResult.REVIEW_REQUIRED
    normalized = license_code.strip().lower()
    if normalized in SAFE_LICENSES:
        return LicenseSafetyResult.SAFE
    if any(marker in normalized for marker in UNSAFE_LICENSE_MARKERS):
        return LicenseSafetyResult.UNSAFE
    return LicenseSafetyResult.REVIEW_REQUIRED
