from __future__ import annotations

from dataclasses import dataclass

from database_core.domain.enums import (
    ConfusionRelevance,
    DiagnosticFeatureVisibility,
    DifficultyLevel,
    LearningSuitability,
    MediaRole,
    PedagogicalQuality,
    Sex,
    TechnicalQuality,
    UncertaintyReason,
    ViewAngle,
)
from database_core.domain.models import AIQualification, MediaAsset
from database_core.qualification.policy import (
    AI_CONFIDENCE_REJECT_FLOOR,
    AI_CONFIDENCE_THRESHOLD,
    DEFAULT_QUALIFICATION_POLICY,
    resolve_confusion_relevance,
    resolve_diagnostic_feature_visibility,
    resolve_difficulty_level,
    resolve_learning_suitability,
    resolve_media_role,
    resolve_pedagogical_quality,
    resolve_technical_quality,
    resolve_uncertainty_reason,
)


@dataclass(frozen=True)
class ExpertQualificationResult:
    technical_quality: TechnicalQuality
    pedagogical_quality: PedagogicalQuality
    life_stage: str
    sex: Sex
    visible_parts: list[str]
    view_angle: ViewAngle
    difficulty_level: DifficultyLevel
    media_role: MediaRole
    confusion_relevance: ConfusionRelevance
    diagnostic_feature_visibility: DiagnosticFeatureVisibility
    learning_suitability: LearningSuitability
    uncertainty_reason: UncertaintyReason
    flags: list[str]


def run_expert_qualification(
    *,
    media_asset: MediaAsset,
    ai_qualification: AIQualification | None,
    qualification_policy: str = DEFAULT_QUALIFICATION_POLICY,
) -> ExpertQualificationResult:
    technical_quality = resolve_technical_quality(media_asset, ai_qualification)
    pedagogical_quality = resolve_pedagogical_quality(ai_qualification)
    difficulty_level = resolve_difficulty_level(ai_qualification)
    media_role = resolve_media_role(ai_qualification)
    confusion_relevance = resolve_confusion_relevance(ai_qualification)
    diagnostic_feature_visibility = resolve_diagnostic_feature_visibility(ai_qualification)
    learning_suitability = resolve_learning_suitability(ai_qualification)
    uncertainty_reason = resolve_uncertainty_reason(ai_qualification)
    life_stage = ai_qualification.life_stage if ai_qualification else "unknown"
    sex = ai_qualification.sex if ai_qualification else Sex.UNKNOWN
    visible_parts = list(ai_qualification.visible_parts) if ai_qualification else []
    view_angle = ai_qualification.view_angle if ai_qualification else ViewAngle.UNKNOWN

    flags: list[str] = []
    if ai_qualification:
        if ai_qualification.confidence < AI_CONFIDENCE_THRESHOLD:
            flags.append("low_ai_confidence")
        if (
            qualification_policy == "v1.1"
            and ai_qualification.confidence < AI_CONFIDENCE_REJECT_FLOOR
        ):
            flags.append("low_ai_confidence_below_floor")
    if not visible_parts:
        flags.append("missing_visible_parts")
    if view_angle == ViewAngle.UNKNOWN:
        flags.append("missing_view_angle")
    if technical_quality in {TechnicalQuality.LOW, TechnicalQuality.UNKNOWN}:
        flags.append("insufficient_technical_quality")

    return ExpertQualificationResult(
        technical_quality=technical_quality,
        pedagogical_quality=pedagogical_quality,
        life_stage=life_stage,
        sex=sex,
        visible_parts=visible_parts,
        view_angle=view_angle,
        difficulty_level=difficulty_level,
        media_role=media_role,
        confusion_relevance=confusion_relevance,
        diagnostic_feature_visibility=diagnostic_feature_visibility,
        learning_suitability=learning_suitability,
        uncertainty_reason=uncertainty_reason,
        flags=flags,
    )
