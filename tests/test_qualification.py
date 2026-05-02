from datetime import datetime

from database_core.domain.enums import MediaType, SourceName
from database_core.domain.models import (
    AIQualification,
    LocationMetadata,
    MediaAsset,
    SourceObservation,
    SourceQualityMetadata,
)
from database_core.qualification.ai import AIQualificationOutcome, source_external_key_for_media
from database_core.qualification.rules import qualify_media_assets


def _observation(
    *,
    observation_id: str,
    canonical_taxon_id: str = "taxon:birds:000014",
    observation_license: str = "CC-BY",
) -> SourceObservation:
    return SourceObservation(
        observation_uid=f"obs:inaturalist:{observation_id}",
        source_name=SourceName.INATURALIST,
        source_observation_id=observation_id,
        source_taxon_id="12716",
        observed_at=datetime.fromisoformat("2025-04-18T07:31:00+00:00"),
        location=LocationMetadata(place_name="Brussels, BE"),
        source_quality=SourceQualityMetadata(
            quality_grade="research",
            research_grade=True,
            observation_license=observation_license,
            captive=False,
        ),
        raw_payload_ref="data/fixtures/birds_pilot.json#/observations/0",
        canonical_taxon_id=canonical_taxon_id,
    )


def _media_asset(
    *,
    media_id: str,
    observation_uid: str,
    canonical_taxon_id: str = "taxon:birds:000014",
    media_license: str = "CC-BY",
    width: int = 1400,
    height: int = 1000,
) -> MediaAsset:
    return MediaAsset(
        media_id=f"media:inaturalist:{media_id}",
        source_name=SourceName.INATURALIST,
        source_media_id=media_id,
        media_type=MediaType.IMAGE,
        source_url=f"fixture://inaturalist/media/{media_id}",
        attribution=f"(c) observer ({media_license})",
        author="observer",
        license=media_license,
        mime_type="image/jpeg",
        file_extension="jpg",
        width=width,
        height=height,
        source_observation_uid=observation_uid,
        canonical_taxon_id=canonical_taxon_id,
        raw_payload_ref="data/fixtures/birds_pilot.json#/observations/0/media/0",
    )


def test_qualified_resource_is_not_exportable_without_safe_media_license() -> None:
    observation = SourceObservation(
        observation_uid="obs:inaturalist:fixture-1",
        source_name=SourceName.INATURALIST,
        source_observation_id="fixture-1",
        source_taxon_id="12716",
        observed_at=datetime.fromisoformat("2025-04-18T07:31:00+00:00"),
        location=LocationMetadata(place_name="Brussels, BE"),
        source_quality=SourceQualityMetadata(
            quality_grade="research",
            research_grade=True,
            observation_license="CC-BY",
            captive=False,
        ),
        raw_payload_ref="data/fixtures/birds_pilot.json#/observations/0",
        canonical_taxon_id="taxon:birds:000014",
    )
    media_asset = MediaAsset(
        media_id="media:inaturalist:fixture-1",
        source_name=SourceName.INATURALIST,
        source_media_id="fixture-media-1",
        media_type=MediaType.IMAGE,
        source_url="fixture://inaturalist/media/fixture-media-1",
        attribution="(c) observer, some rights reserved (CC BY-NC)",
        author="observer",
        license="CC-BY-NC",
        mime_type="image/jpeg",
        file_extension="jpg",
        width=1400,
        height=1000,
        source_observation_uid=observation.observation_uid,
        canonical_taxon_id="taxon:birds:000014",
        raw_payload_ref="data/fixtures/birds_pilot.json#/observations/0/media/0",
    )

    resources, review_items = qualify_media_assets(
        observations=[observation],
        media_assets=[media_asset],
        ai_qualifications_by_source_media_key={},
        created_at=datetime.fromisoformat("2026-04-07T00:00:00+00:00"),
        run_id="run:20260408T000000Z:aaaaaaaa",
    )

    assert len(resources) == 1
    assert resources[0].export_eligible is False
    assert resources[0].license_safety_result == "unsafe"
    assert review_items == []


def test_uncertain_policy_reject_turns_incomplete_ai_result_into_rejected() -> None:
    observation = SourceObservation(
        observation_uid="obs:inaturalist:fixture-2",
        source_name=SourceName.INATURALIST,
        source_observation_id="fixture-2",
        source_taxon_id="12716",
        observed_at=datetime.fromisoformat("2025-04-18T07:31:00+00:00"),
        location=LocationMetadata(place_name="Brussels, BE"),
        source_quality=SourceQualityMetadata(
            quality_grade="research",
            research_grade=True,
            observation_license="CC-BY",
            captive=False,
        ),
        raw_payload_ref="data/fixtures/birds_pilot.json#/observations/0",
        canonical_taxon_id="taxon:birds:000014",
    )
    media_asset = MediaAsset(
        media_id="media:inaturalist:fixture-2",
        source_name=SourceName.INATURALIST,
        source_media_id="fixture-media-2",
        media_type=MediaType.IMAGE,
        source_url="fixture://inaturalist/media/fixture-media-2",
        attribution="(c) observer, some rights reserved (CC BY)",
        author="observer",
        license="CC-BY",
        mime_type="image/jpeg",
        file_extension="jpg",
        width=1400,
        height=1000,
        source_observation_uid=observation.observation_uid,
        canonical_taxon_id="taxon:birds:000014",
        raw_payload_ref="data/fixtures/birds_pilot.json#/observations/0/media/0",
    )
    ai_outcome = AIQualificationOutcome(
        status="ok",
        qualification=AIQualification(
            technical_quality="high",
            pedagogical_quality="high",
            life_stage="adult",
            sex="unknown",
            visible_parts=[],
            view_angle="unknown",
            confidence=0.95,
            model_name="gemini-3.1-flash-lite-preview",
        ),
        flags=("incomplete_required_tags",),
    )

    resources, review_items = qualify_media_assets(
        observations=[observation],
        media_assets=[media_asset],
        ai_qualifications_by_source_media_key={
            source_external_key_for_media(media_asset): ai_outcome
        },
        created_at=datetime.fromisoformat("2026-04-07T00:00:00+00:00"),
        run_id="run:20260408T000000Z:aaaaaaaa",
        uncertain_policy="reject",
    )

    assert resources[0].qualification_status == "rejected"
    assert review_items == []


def test_low_pedagogical_quality_no_longer_blocks_acceptance() -> None:
    observation = SourceObservation(
        observation_uid="obs:inaturalist:fixture-3",
        source_name=SourceName.INATURALIST,
        source_observation_id="fixture-3",
        source_taxon_id="12716",
        observed_at=datetime.fromisoformat("2025-04-18T07:31:00+00:00"),
        location=LocationMetadata(place_name="Brussels, BE"),
        source_quality=SourceQualityMetadata(
            quality_grade="research",
            research_grade=True,
            observation_license="CC-BY",
            captive=None,
        ),
        raw_payload_ref="data/fixtures/birds_pilot.json#/observations/0",
        canonical_taxon_id="taxon:birds:000014",
    )
    media_asset = MediaAsset(
        media_id="media:inaturalist:fixture-3",
        source_name=SourceName.INATURALIST,
        source_media_id="fixture-media-3",
        media_type=MediaType.IMAGE,
        source_url="fixture://inaturalist/media/fixture-media-3",
        attribution="(c) observer, some rights reserved (CC BY)",
        author="observer",
        license="CC-BY",
        mime_type="image/jpeg",
        file_extension="jpg",
        width=1600,
        height=1200,
        source_observation_uid=observation.observation_uid,
        canonical_taxon_id="taxon:birds:000014",
        raw_payload_ref="data/fixtures/birds_pilot.json#/observations/0/media/0",
    )
    ai_outcome = AIQualificationOutcome(
        status="ok",
        qualification=AIQualification(
            technical_quality="high",
            pedagogical_quality="low",
            life_stage="unknown",
            sex="unknown",
            visible_parts=["full_body", "head", "beak"],
            view_angle="lateral",
            confidence=0.95,
            model_name="gemini-3.1-flash-lite-preview",
        ),
        flags=(),
    )

    resources, review_items = qualify_media_assets(
        observations=[observation],
        media_assets=[media_asset],
        ai_qualifications_by_source_media_key={
            source_external_key_for_media(media_asset): ai_outcome
        },
        created_at=datetime.fromisoformat("2026-04-07T00:00:00+00:00"),
        run_id="run:20260408T000000Z:aaaaaaaa",
        uncertain_policy="reject",
    )

    assert resources[0].qualification_status == "accepted"
    assert "incomplete_required_tags" not in resources[0].qualification_flags
    assert resources[0].difficulty_level == "unknown"
    assert resources[0].media_role == "context"
    assert resources[0].confusion_relevance == "none"
    assert resources[0].diagnostic_feature_visibility == "unknown"
    assert resources[0].learning_suitability == "unknown"
    assert resources[0].uncertainty_reason == "none"
    assert resources[0].ai_confidence == 0.95
    assert review_items == []


def test_review_policy_creates_structured_review_queue_item() -> None:
    observation = SourceObservation(
        observation_uid="obs:inaturalist:fixture-4",
        source_name=SourceName.INATURALIST,
        source_observation_id="fixture-4",
        source_taxon_id="12716",
        observed_at=datetime.fromisoformat("2025-04-18T07:31:00+00:00"),
        location=LocationMetadata(place_name="Brussels, BE"),
        source_quality=SourceQualityMetadata(
            quality_grade="research",
            research_grade=True,
            observation_license="CC-BY",
            captive=False,
        ),
        raw_payload_ref="data/fixtures/birds_pilot.json#/observations/0",
        canonical_taxon_id="taxon:birds:000014",
    )
    media_asset = MediaAsset(
        media_id="media:inaturalist:fixture-4",
        source_name=SourceName.INATURALIST,
        source_media_id="fixture-media-4",
        media_type=MediaType.IMAGE,
        source_url="fixture://inaturalist/media/fixture-media-4",
        attribution="(c) observer, some rights reserved (CC BY)",
        author="observer",
        license="CC-BY",
        mime_type="image/jpeg",
        file_extension="jpg",
        width=900,
        height=700,
        source_observation_uid=observation.observation_uid,
        canonical_taxon_id="taxon:birds:000014",
        raw_payload_ref="data/fixtures/birds_pilot.json#/observations/0/media/0",
    )

    resources, review_items = qualify_media_assets(
        observations=[observation],
        media_assets=[media_asset],
        ai_qualifications_by_source_media_key={},
        created_at=datetime.fromisoformat("2026-04-07T00:00:00+00:00"),
        run_id="run:20260408T000000Z:aaaaaaaa",
        uncertain_policy="review",
    )

    assert resources[0].qualification_status == "review_required"
    assert review_items[0].review_reason_code == "insufficient_resolution"
    assert review_items[0].stage_name == "fast_semantic_screening"
    assert review_items[0].priority == "medium"


def test_v11_unsafe_license_is_hard_rejected() -> None:
    observation = _observation(observation_id="v11-unsafe")
    media_asset = _media_asset(
        media_id="v11-unsafe-media",
        observation_uid=observation.observation_uid,
        media_license="CC-BY-NC",
    )
    resources, _ = qualify_media_assets(
        observations=[observation],
        media_assets=[media_asset],
        ai_qualifications_by_source_media_key={},
        created_at=datetime.fromisoformat("2026-04-07T00:00:00+00:00"),
        run_id="run:20260408T000000Z:aaaaaaaa",
        uncertain_policy="reject",
        qualification_policy="v1.1",
    )
    assert resources[0].qualification_status == "rejected"
    assert "unsafe_license" in resources[0].qualification_flags
    assert resources[0].export_eligible is False


def test_v11_pre_ai_rejection_flag_is_hard_rejected() -> None:
    observation = _observation(observation_id="v11-pre-ai")
    media_asset = _media_asset(
        media_id="v11-pre-ai-media",
        observation_uid=observation.observation_uid,
    )
    ai_outcome = AIQualificationOutcome(
        status="insufficient_resolution_pre_ai",
        qualification=None,
        flags=("insufficient_resolution_pre_ai",),
    )
    resources, _ = qualify_media_assets(
        observations=[observation],
        media_assets=[media_asset],
        ai_qualifications_by_source_media_key={
            source_external_key_for_media(media_asset): ai_outcome
        },
        created_at=datetime.fromisoformat("2026-04-07T00:00:00+00:00"),
        run_id="run:20260408T000000Z:aaaaaaaa",
        uncertain_policy="reject",
        qualification_policy="v1.1",
    )
    assert resources[0].qualification_status == "rejected"
    assert "insufficient_resolution_pre_ai" in resources[0].qualification_flags


def test_v11_low_ai_confidence_below_floor_is_hard_rejected() -> None:
    observation = _observation(observation_id="v11-low-floor")
    media_asset = _media_asset(
        media_id="v11-low-floor-media",
        observation_uid=observation.observation_uid,
    )
    ai_outcome = AIQualificationOutcome(
        status="ok",
        qualification=AIQualification(
            technical_quality="high",
            pedagogical_quality="high",
            life_stage="adult",
            sex="unknown",
            visible_parts=["head", "beak"],
            view_angle="lateral",
            confidence=0.2,
            model_name="gemini-3.1-flash-lite-preview",
        ),
        flags=(),
    )
    resources, _ = qualify_media_assets(
        observations=[observation],
        media_assets=[media_asset],
        ai_qualifications_by_source_media_key={
            source_external_key_for_media(media_asset): ai_outcome
        },
        created_at=datetime.fromisoformat("2026-04-07T00:00:00+00:00"),
        run_id="run:20260408T000000Z:aaaaaaaa",
        uncertain_policy="reject",
        qualification_policy="v1.1",
    )
    assert resources[0].qualification_status == "rejected"
    assert "low_ai_confidence_below_floor" in resources[0].qualification_flags


def test_v11_low_confidence_and_missing_parts_become_accepted_with_flags() -> None:
    observation = _observation(observation_id="v11-accepted-with-flags")
    media_asset = _media_asset(
        media_id="v11-accepted-with-flags-media",
        observation_uid=observation.observation_uid,
    )
    ai_outcome = AIQualificationOutcome(
        status="ok",
        qualification=AIQualification(
            technical_quality="medium",
            pedagogical_quality="medium",
            life_stage="adult",
            sex="unknown",
            visible_parts=[],
            view_angle="unknown",
            confidence=0.5,
            model_name="gemini-3.1-flash-lite-preview",
        ),
        flags=("incomplete_required_tags",),
    )
    resources, _ = qualify_media_assets(
        observations=[observation],
        media_assets=[media_asset],
        ai_qualifications_by_source_media_key={
            source_external_key_for_media(media_asset): ai_outcome
        },
        created_at=datetime.fromisoformat("2026-04-07T00:00:00+00:00"),
        run_id="run:20260408T000000Z:aaaaaaaa",
        uncertain_policy="reject",
        qualification_policy="v1.1",
    )
    assert resources[0].qualification_status == "accepted"
    assert "low_ai_confidence" in resources[0].qualification_flags
    assert "missing_visible_parts" in resources[0].qualification_flags
    assert "missing_view_angle" in resources[0].qualification_flags
    assert "policy:v1.1:accepted_with_flags" in (resources[0].qualification_notes or "")


def test_v11_missing_view_angle_and_low_technical_quality_do_not_auto_reject() -> None:
    observation = _observation(observation_id="v11-view-tech")
    media_asset = _media_asset(
        media_id="v11-view-tech-media",
        observation_uid=observation.observation_uid,
    )
    ai_outcome = AIQualificationOutcome(
        status="ok",
        qualification=AIQualification(
            technical_quality="low",
            pedagogical_quality="medium",
            life_stage="adult",
            sex="unknown",
            visible_parts=["head", "beak"],
            view_angle="unknown",
            confidence=0.95,
            model_name="gemini-3.1-flash-lite-preview",
        ),
        flags=(),
    )
    resources, _ = qualify_media_assets(
        observations=[observation],
        media_assets=[media_asset],
        ai_qualifications_by_source_media_key={
            source_external_key_for_media(media_asset): ai_outcome
        },
        created_at=datetime.fromisoformat("2026-04-07T00:00:00+00:00"),
        run_id="run:20260408T000000Z:aaaaaaaa",
        uncertain_policy="reject",
        qualification_policy="v1.1",
    )
    assert resources[0].qualification_status == "accepted"
    assert "missing_view_angle" in resources[0].qualification_flags
    assert "insufficient_technical_quality" in resources[0].qualification_flags


def test_v11_technical_ai_failure_does_not_become_accepted() -> None:
    observation = _observation(observation_id="v11-gemini-error")
    media_asset = _media_asset(
        media_id="v11-gemini-error-media",
        observation_uid=observation.observation_uid,
    )
    ai_outcome = AIQualificationOutcome(
        status="gemini_error",
        qualification=None,
        flags=("gemini_error",),
        note="network timeout",
    )
    resources, _ = qualify_media_assets(
        observations=[observation],
        media_assets=[media_asset],
        ai_qualifications_by_source_media_key={
            source_external_key_for_media(media_asset): ai_outcome
        },
        created_at=datetime.fromisoformat("2026-04-07T00:00:00+00:00"),
        run_id="run:20260408T000000Z:aaaaaaaa",
        uncertain_policy="reject",
        qualification_policy="v1.1",
    )
    assert resources[0].qualification_status == "rejected"
    assert "gemini_error" in resources[0].qualification_flags
