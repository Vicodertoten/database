from __future__ import annotations

from dataclasses import dataclass

from database_core.domain.enums import PedagogicalQuality, Sex, TechnicalQuality, ViewAngle
from database_core.domain.models import AIQualification, MediaAsset
from database_core.qualification.policy import (
    AI_CONFIDENCE_THRESHOLD,
    resolve_pedagogical_quality,
    resolve_technical_quality,
)


@dataclass(frozen=True)
class ExpertQualificationResult:
    technical_quality: TechnicalQuality
    pedagogical_quality: PedagogicalQuality
    life_stage: str
    sex: Sex
    visible_parts: list[str]
    view_angle: ViewAngle
    flags: list[str]


def run_expert_qualification(
    *,
    media_asset: MediaAsset,
    ai_qualification: AIQualification | None,
) -> ExpertQualificationResult:
    technical_quality = resolve_technical_quality(media_asset, ai_qualification)
    pedagogical_quality = resolve_pedagogical_quality(ai_qualification)
    life_stage = ai_qualification.life_stage if ai_qualification else "unknown"
    sex = ai_qualification.sex if ai_qualification else Sex.UNKNOWN
    visible_parts = list(ai_qualification.visible_parts) if ai_qualification else []
    view_angle = ai_qualification.view_angle if ai_qualification else ViewAngle.UNKNOWN

    flags: list[str] = []
    if ai_qualification and ai_qualification.confidence < AI_CONFIDENCE_THRESHOLD:
        flags.append("low_ai_confidence")
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
        flags=flags,
    )
