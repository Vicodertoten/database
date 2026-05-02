from __future__ import annotations

from pydantic import ValidationError

from database_core.domain.enums import (
    ConfusionRelevance,
    DiagnosticFeatureVisibility,
    DifficultyLevel,
    LearningSuitability,
    LicenseSafetyResult,
    MediaRole,
    PedagogicalProfileStatus,
    PedagogicalQuality,
    PedagogicalUsage,
    QualificationStatus,
    Sex,
    SourceName,
    TechnicalQuality,
    UncertaintyReason,
    ViewAngle,
)
from database_core.domain.models import (
    AIQualification,
    MediaAsset,
    PedagogicalImageSubscores,
    ProvenanceSummary,
    QualifiedResource,
)
from database_core.qualification.ai import AIQualificationOutcome
from database_core.qualification.pedagogical_image_profile import (
    build_pedagogical_image_profile,
)


def _provenance(
    *,
    ai_status: str = "ok",
    ai_model: str | None = "gemini-3.1-flash-lite-preview",
    ai_prompt_version: str | None = "phase1.inat.image.v2",
    qualification_method: str = "gemini_plus_rules",
) -> ProvenanceSummary:
    return ProvenanceSummary(
        source_name=SourceName.INATURALIST,
        source_observation_key="inaturalist::obs-1",
        source_media_key="inaturalist::media-1",
        source_observation_id="obs-1",
        source_media_id="media-1",
        raw_payload_ref="data/qualified/fixture.json",
        run_id="run:20260502T000000Z:aaaaaaaa",
        observation_license="CC-BY",
        media_license="CC-BY",
        qualification_method=qualification_method,
        ai_model=ai_model,
        ai_prompt_version=ai_prompt_version,
        ai_task_name="qualification",
        ai_status=ai_status,
    )


def _qualified_resource(
    *,
    technical_quality: TechnicalQuality = TechnicalQuality.HIGH,
    pedagogical_quality: PedagogicalQuality = PedagogicalQuality.HIGH,
    difficulty_level: DifficultyLevel = DifficultyLevel.EASY,
    media_role: MediaRole = MediaRole.PRIMARY_ID,
    confusion_relevance: ConfusionRelevance = ConfusionRelevance.MEDIUM,
    diagnostic_feature_visibility: DiagnosticFeatureVisibility = DiagnosticFeatureVisibility.HIGH,
    learning_suitability: LearningSuitability = LearningSuitability.HIGH,
    uncertainty_reason: UncertaintyReason = UncertaintyReason.NONE,
    visible_parts: list[str] | None = None,
    ai_confidence: float | None = 0.92,
    provenance: ProvenanceSummary | None = None,
    qualification_status: QualificationStatus = QualificationStatus.ACCEPTED,
    license_safety_result: LicenseSafetyResult = LicenseSafetyResult.SAFE,
    export_eligible: bool = True,
    qualification_notes: str | None = "clear field marks",
) -> QualifiedResource:
    return QualifiedResource(
        qualified_resource_id="qr:media:inaturalist:fixture-1",
        canonical_taxon_id="taxon:birds:000014",
        source_observation_uid="obs:inaturalist:obs-1",
        source_observation_id="obs-1",
        media_asset_id="media:inaturalist:media-1",
        qualification_status=qualification_status,
        qualification_version="qualification.staged.v1",
        technical_quality=technical_quality,
        pedagogical_quality=pedagogical_quality,
        life_stage="adult",
        sex=Sex.UNKNOWN,
        visible_parts=visible_parts or ["head", "beak", "wing"],
        view_angle=ViewAngle.LATERAL,
        difficulty_level=difficulty_level,
        media_role=media_role,
        confusion_relevance=confusion_relevance,
        diagnostic_feature_visibility=diagnostic_feature_visibility,
        learning_suitability=learning_suitability,
        uncertainty_reason=uncertainty_reason,
        qualification_notes=qualification_notes,
        qualification_flags=[],
        provenance_summary=provenance or _provenance(),
        license_safety_result=license_safety_result,
        export_eligible=export_eligible,
        ai_confidence=ai_confidence,
        derived_classification=None,
    )


def _media_asset(*, source_url: str = "https://example.org/bird.jpg") -> MediaAsset:
    return MediaAsset(
        media_id="media:inaturalist:media-1",
        source_name=SourceName.INATURALIST,
        source_media_id="media-1",
        media_type="image",
        source_url=source_url,
        attribution="(c) observer",
        author="observer",
        license="CC-BY",
        mime_type="image/jpeg",
        file_extension="jpg",
        width=1600,
        height=1200,
        checksum=None,
        source_observation_uid="obs:inaturalist:obs-1",
        canonical_taxon_id="taxon:birds:000014",
        raw_payload_ref="data/raw/fixture.json",
    )


def _ai_outcome(
    *,
    status: str = "ok",
    confidence: float = 0.92,
    technical_quality: TechnicalQuality = TechnicalQuality.HIGH,
    pedagogical_quality: PedagogicalQuality = PedagogicalQuality.HIGH,
    difficulty_level: DifficultyLevel = DifficultyLevel.EASY,
    media_role: MediaRole = MediaRole.PRIMARY_ID,
    confusion_relevance: ConfusionRelevance = ConfusionRelevance.MEDIUM,
    diagnostic_feature_visibility: DiagnosticFeatureVisibility = DiagnosticFeatureVisibility.HIGH,
    learning_suitability: LearningSuitability = LearningSuitability.HIGH,
    uncertainty_reason: UncertaintyReason = UncertaintyReason.NONE,
    visible_parts: list[str] | None = None,
    note: str | None = None,
) -> AIQualificationOutcome:
    qualification = AIQualification(
        technical_quality=technical_quality,
        pedagogical_quality=pedagogical_quality,
        life_stage="adult",
        sex=Sex.UNKNOWN,
        visible_parts=visible_parts or ["head", "beak", "wing"],
        view_angle=ViewAngle.LATERAL,
        difficulty_level=difficulty_level,
        media_role=media_role,
        confusion_relevance=confusion_relevance,
        diagnostic_feature_visibility=diagnostic_feature_visibility,
        learning_suitability=learning_suitability,
        uncertainty_reason=uncertainty_reason,
        confidence=confidence,
        model_name="gemini-3.1-flash-lite-preview",
        notes=note,
    )
    return AIQualificationOutcome(
        status=status,
        qualification=qualification,
        flags=(),
        note=note,
        model_name="gemini-3.1-flash-lite-preview",
        prompt_version="phase1.inat.image.v2",
    )


def test_excellent_image_profiles_with_high_score_and_primary_usages() -> None:
    resource = _qualified_resource()
    profile = build_pedagogical_image_profile(
        resource,
        ai_outcome=_ai_outcome(),
        media_asset=_media_asset(),
    )

    assert profile.profile_status in {
        PedagogicalProfileStatus.PROFILED,
        PedagogicalProfileStatus.PROFILED_WITH_WARNINGS,
    }
    assert profile.overall_score >= 70
    assert profile.score_band.value in {"A", "B"}
    assert PedagogicalUsage.PRIMARY_QUESTION_BEGINNER in profile.recommended_usages
    assert PedagogicalUsage.PRIMARY_QUESTION_INTERMEDIATE in profile.recommended_usages
    assert PedagogicalUsage.FEEDBACK_EXPLANATION in profile.recommended_usages


def test_missing_ai_forces_pending_ai_without_recommended_usage() -> None:
    resource = _qualified_resource(
        ai_confidence=None,
        provenance=_provenance(ai_status="rules_only", ai_model=None, ai_prompt_version=None),
    )

    profile = build_pedagogical_image_profile(resource, media_asset=_media_asset())

    assert profile.profile_status == PedagogicalProfileStatus.PENDING_AI
    assert profile.overall_score == 0
    assert profile.recommended_usages == []


def test_low_confidence_requires_warnings_and_review() -> None:
    resource = _qualified_resource(ai_confidence=0.45)
    profile = build_pedagogical_image_profile(
        resource,
        ai_outcome=_ai_outcome(confidence=0.45),
        media_asset=_media_asset(),
    )

    assert profile.profile_status == PedagogicalProfileStatus.MANUAL_REVIEW_REQUIRED
    assert profile.warnings


def test_contextual_image_favors_context_learning_usage() -> None:
    resource = _qualified_resource(
        technical_quality=TechnicalQuality.MEDIUM,
        pedagogical_quality=PedagogicalQuality.MEDIUM,
        media_role=MediaRole.CONTEXT,
        confusion_relevance=ConfusionRelevance.LOW,
        diagnostic_feature_visibility=DiagnosticFeatureVisibility.MEDIUM,
        learning_suitability=LearningSuitability.MEDIUM,
        visible_parts=["silhouette", "tail"],
    )
    profile = build_pedagogical_image_profile(
        resource,
        ai_outcome=_ai_outcome(
            technical_quality=TechnicalQuality.MEDIUM,
            pedagogical_quality=PedagogicalQuality.MEDIUM,
            media_role=MediaRole.CONTEXT,
            confusion_relevance=ConfusionRelevance.LOW,
            diagnostic_feature_visibility=DiagnosticFeatureVisibility.MEDIUM,
            learning_suitability=LearningSuitability.MEDIUM,
            visible_parts=["silhouette", "tail"],
            difficulty_level=DifficultyLevel.MEDIUM,
        ),
        media_asset=_media_asset(),
    )

    assert profile.usage_scores.context_learning >= 70
    assert (
        profile.usage_scores.context_learning
        >= profile.usage_scores.primary_question_beginner
    )


def test_high_confusion_relevance_increases_confusion_training() -> None:
    resource = _qualified_resource(
        confusion_relevance=ConfusionRelevance.HIGH,
        diagnostic_feature_visibility=DiagnosticFeatureVisibility.HIGH,
        visible_parts=["eye", "wing", "tail"],
    )
    profile = build_pedagogical_image_profile(
        resource,
        ai_outcome=_ai_outcome(
            confusion_relevance=ConfusionRelevance.HIGH,
            diagnostic_feature_visibility=DiagnosticFeatureVisibility.HIGH,
            visible_parts=["eye", "wing", "tail"],
        ),
        media_asset=_media_asset(),
    )

    assert profile.usage_scores.confusion_training >= 70
    assert profile.feedback.confusion_hint is not None


def test_low_technical_quality_blocks_primary_beginner_usage() -> None:
    resource = _qualified_resource(
        technical_quality=TechnicalQuality.LOW,
        pedagogical_quality=PedagogicalQuality.LOW,
        difficulty_level=DifficultyLevel.HARD,
        media_role=MediaRole.NON_DIAGNOSTIC,
        confusion_relevance=ConfusionRelevance.NONE,
        diagnostic_feature_visibility=DiagnosticFeatureVisibility.LOW,
        learning_suitability=LearningSuitability.LOW,
        uncertainty_reason=UncertaintyReason.OCCLUSION,
        visible_parts=["head"],
        ai_confidence=0.9,
    )
    profile = build_pedagogical_image_profile(
        resource,
        ai_outcome=_ai_outcome(
            confidence=0.9,
            technical_quality=TechnicalQuality.LOW,
            pedagogical_quality=PedagogicalQuality.LOW,
            difficulty_level=DifficultyLevel.HARD,
            media_role=MediaRole.NON_DIAGNOSTIC,
            confusion_relevance=ConfusionRelevance.NONE,
            diagnostic_feature_visibility=DiagnosticFeatureVisibility.LOW,
            learning_suitability=LearningSuitability.LOW,
            uncertainty_reason=UncertaintyReason.OCCLUSION,
            visible_parts=["head"],
        ),
        media_asset=_media_asset(),
    )

    assert profile.overall_score < 55
    assert profile.profile_status == PedagogicalProfileStatus.MANUAL_REVIEW_REQUIRED
    assert PedagogicalUsage.PRIMARY_QUESTION_BEGINNER not in profile.recommended_usages
    assert "technical_quality_too_low_for_primary_question" in profile.warnings


def test_license_review_required_does_not_return_profiled_status() -> None:
    resource = _qualified_resource(
        license_safety_result=LicenseSafetyResult.REVIEW_REQUIRED,
        export_eligible=False,
    )
    profile = build_pedagogical_image_profile(
        resource,
        ai_outcome=_ai_outcome(),
        media_asset=_media_asset(),
    )

    assert profile.profile_status == PedagogicalProfileStatus.MANUAL_REVIEW_REQUIRED
    assert "hard_gate_license_review_required" in profile.reason_codes
    assert "license_review_required" in profile.warnings


def test_ai_outcome_divergence_with_resource_triggers_manual_review() -> None:
    resource = _qualified_resource(
        technical_quality=TechnicalQuality.LOW,
        pedagogical_quality=PedagogicalQuality.LOW,
        ai_confidence=0.55,
    )
    profile = build_pedagogical_image_profile(
        resource,
        ai_outcome=_ai_outcome(
            confidence=0.92,
            technical_quality=TechnicalQuality.HIGH,
            pedagogical_quality=PedagogicalQuality.HIGH,
            difficulty_level=DifficultyLevel.MEDIUM,
        ),
        media_asset=_media_asset(),
    )

    assert profile.profile_status == PedagogicalProfileStatus.MANUAL_REVIEW_REQUIRED
    assert "ai_outcome_qualified_resource_divergence" in profile.warnings
    assert "manual_review_ai_outcome_resource_divergence" in profile.reason_codes


def test_builder_scores_are_clamped_between_0_and_100() -> None:
    resource = _qualified_resource()
    profile = build_pedagogical_image_profile(
        resource,
        ai_outcome=_ai_outcome(confidence=1.0),
        media_asset=_media_asset(),
    )

    subscores = profile.subscores.model_dump()
    usage_scores = profile.usage_scores.model_dump()

    assert 0 <= profile.overall_score <= 100
    for value in subscores.values():
        assert 0 <= int(value) <= 100
    for value in usage_scores.values():
        assert 0 <= int(value) <= 100


def test_subscores_validation_rejects_values_outside_range() -> None:
    try:
        PedagogicalImageSubscores(
            technical_quality=101,
            subject_visibility=50,
            diagnostic_value=50,
            pedagogical_clarity=50,
            representativeness=50,
            difficulty_fit=50,
            feedback_potential=50,
            confusion_potential=50,
            context_value=50,
            confidence=50,
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected score range validation to reject values > 100")
