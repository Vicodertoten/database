from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from database_core.domain.enums import (
    LicenseSafetyResult,
    MediaType,
    PedagogicalQuality,
    QualificationStatus,
    TechnicalQuality,
    ViewAngle,
)
from database_core.domain.models import (
    AIQualification,
    MediaAsset,
    ProvenanceSummary,
    QualifiedResource,
    ReviewItem,
    SourceObservation,
)
from database_core.qualification.ai import AIQualificationOutcome
from database_core.review.queue import build_review_item

SAFE_LICENSES = {"cc0", "cc-by", "cc-by-sa", "public domain", "pd"}
UNSAFE_LICENSE_MARKERS = ("nc", "nd", "all rights reserved")
AI_CONFIDENCE_THRESHOLD = 0.6
QUALIFICATION_VERSION = "phase1.v1"


def qualify_media_assets(
    *,
    observations: Iterable[SourceObservation],
    media_assets: Iterable[MediaAsset],
    ai_qualifications_by_source_media_id: dict[str, AIQualification | AIQualificationOutcome],
    created_at: datetime,
) -> tuple[list[QualifiedResource], list[ReviewItem]]:
    observations_by_uid = {item.observation_uid: item for item in observations}
    qualified_resources: list[QualifiedResource] = []
    review_items: list[ReviewItem] = []

    for media_asset in sorted(media_assets, key=lambda item: item.media_id):
        observation = observations_by_uid[media_asset.source_observation_uid]
        ai_outcome = _coerce_ai_outcome(ai_qualifications_by_source_media_id.get(media_asset.source_media_id))
        resource = _qualify_single_media(
            media_asset=media_asset,
            observation=observation,
            ai_outcome=ai_outcome,
        )
        qualified_resources.append(resource)
        if resource.qualification_status == QualificationStatus.REVIEW_REQUIRED:
            review_items.append(
                build_review_item(
                    media_asset_id=media_asset.media_id,
                    canonical_taxon_id=resource.canonical_taxon_id,
                    review_reason=resource.qualification_notes or "review_required",
                    created_at=created_at,
                )
            )

    return qualified_resources, review_items


def _qualify_single_media(
    *,
    media_asset: MediaAsset,
    observation: SourceObservation,
    ai_outcome: AIQualificationOutcome | None,
) -> QualifiedResource:
    ai_qualification = ai_outcome.qualification if ai_outcome else None
    technical_quality = _resolve_technical_quality(media_asset, ai_qualification)
    pedagogical_quality = _resolve_pedagogical_quality(ai_qualification)
    life_stage = ai_qualification.life_stage if ai_qualification else "unknown"
    sex = ai_qualification.sex if ai_qualification else "unknown"
    visible_parts = list(ai_qualification.visible_parts) if ai_qualification else []
    view_angle = ai_qualification.view_angle if ai_qualification else ViewAngle.UNKNOWN
    license_safety_result = _evaluate_license_safety(
        media_license=media_asset.license,
        observation_license=observation.source_quality.observation_license,
    )
    qualification_flags: list[str] = list(ai_outcome.flags) if ai_outcome else []

    if media_asset.media_type != MediaType.IMAGE:
        qualification_flags.append("unsupported_media_type")
    if license_safety_result == LicenseSafetyResult.UNSAFE:
        qualification_flags.append("unsafe_license")
    if ai_qualification and ai_qualification.confidence < AI_CONFIDENCE_THRESHOLD:
        qualification_flags.append("low_ai_confidence")
    if not visible_parts:
        qualification_flags.append("missing_visible_parts")
    if view_angle == ViewAngle.UNKNOWN:
        qualification_flags.append("missing_view_angle")
    if technical_quality in {TechnicalQuality.LOW, TechnicalQuality.UNKNOWN}:
        qualification_flags.append("insufficient_technical_quality")
    if pedagogical_quality in {PedagogicalQuality.LOW, PedagogicalQuality.UNKNOWN}:
        qualification_flags.append("insufficient_pedagogical_quality")

    if "unsupported_media_type" in qualification_flags or "unsafe_license" in qualification_flags:
        status = QualificationStatus.REJECTED
    elif any(
        flag in qualification_flags
        for flag in (
            "missing_cached_image",
            "gemini_error",
            "invalid_gemini_json",
            "missing_fixture_ai_output",
            "incomplete_required_tags",
            "low_ai_confidence",
            "missing_visible_parts",
            "missing_view_angle",
            "insufficient_technical_quality",
            "insufficient_pedagogical_quality",
        )
    ):
        status = QualificationStatus.REVIEW_REQUIRED
    else:
        status = QualificationStatus.ACCEPTED

    provenance_summary = ProvenanceSummary(
        source_name=media_asset.source_name,
        source_observation_id=observation.source_observation_id,
        source_media_id=media_asset.source_media_id,
        raw_payload_ref=media_asset.raw_payload_ref,
        observation_license=observation.source_quality.observation_license,
        media_license=media_asset.license,
        qualification_method=_qualification_method(ai_qualification=ai_qualification, ai_outcome=ai_outcome),
        ai_model=ai_qualification.model_name if ai_qualification else None,
    )
    export_eligible = (
        status == QualificationStatus.ACCEPTED
        and license_safety_result == LicenseSafetyResult.SAFE
    )
    notes = _build_notes(qualification_flags, ai_qualification, ai_outcome)

    return QualifiedResource(
        qualified_resource_id=f"qr:{media_asset.media_id}",
        canonical_taxon_id=media_asset.canonical_taxon_id or "unresolved",
        source_observation_uid=observation.observation_uid,
        source_observation_id=observation.source_observation_id,
        media_asset_id=media_asset.media_id,
        qualification_status=status,
        qualification_version=QUALIFICATION_VERSION,
        technical_quality=technical_quality,
        pedagogical_quality=pedagogical_quality,
        life_stage=life_stage,
        sex=sex,
        visible_parts=visible_parts,
        view_angle=view_angle,
        qualification_notes=notes,
        qualification_flags=qualification_flags,
        provenance_summary=provenance_summary,
        license_safety_result=license_safety_result,
        export_eligible=export_eligible,
    )


def _evaluate_license_safety(*, media_license: str | None, observation_license: str | None) -> LicenseSafetyResult:
    media_result = _single_license_result(media_license)
    observation_result = _single_license_result(observation_license)

    if LicenseSafetyResult.UNSAFE in {media_result, observation_result}:
        return LicenseSafetyResult.UNSAFE
    if LicenseSafetyResult.REVIEW_REQUIRED in {media_result, observation_result}:
        return LicenseSafetyResult.REVIEW_REQUIRED
    return LicenseSafetyResult.SAFE


def _single_license_result(license_code: str | None) -> LicenseSafetyResult:
    if license_code is None:
        return LicenseSafetyResult.REVIEW_REQUIRED
    normalized = license_code.strip().lower()
    if normalized in SAFE_LICENSES:
        return LicenseSafetyResult.SAFE
    if any(marker in normalized for marker in UNSAFE_LICENSE_MARKERS):
        return LicenseSafetyResult.UNSAFE
    return LicenseSafetyResult.REVIEW_REQUIRED


def _resolve_technical_quality(
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


def _resolve_pedagogical_quality(ai_qualification: AIQualification | None) -> PedagogicalQuality:
    if ai_qualification and ai_qualification.confidence >= AI_CONFIDENCE_THRESHOLD:
        return ai_qualification.pedagogical_quality
    return PedagogicalQuality.UNKNOWN


def _build_notes(
    flags: list[str],
    ai_qualification: AIQualification | None,
    ai_outcome: AIQualificationOutcome | None,
) -> str:
    note_parts = []
    if flags:
        note_parts.append(",".join(flags))
    if ai_outcome and ai_outcome.note:
        note_parts.append(ai_outcome.note)
    if ai_qualification and ai_qualification.notes:
        note_parts.append(ai_qualification.notes)
    return " | ".join(note_parts)


def _coerce_ai_outcome(
    value: AIQualification | AIQualificationOutcome | None,
) -> AIQualificationOutcome | None:
    if value is None:
        return None
    if isinstance(value, AIQualificationOutcome):
        return value
    return AIQualificationOutcome(qualification=value)


def _qualification_method(
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
