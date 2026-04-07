from datetime import datetime

from database_core.domain.enums import MediaType, SourceName
from database_core.domain.models import LocationMetadata, MediaAsset, SourceObservation, SourceQualityMetadata
from database_core.qualification.rules import qualify_media_assets


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
        canonical_taxon_id="bird:turdus-merula",
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
        canonical_taxon_id="bird:turdus-merula",
        raw_payload_ref="data/fixtures/birds_pilot.json#/observations/0/media/0",
    )

    resources, review_items = qualify_media_assets(
        observations=[observation],
        media_assets=[media_asset],
        ai_qualifications_by_source_media_id={},
        created_at=datetime.fromisoformat("2026-04-07T00:00:00+00:00"),
    )

    assert len(resources) == 1
    assert resources[0].export_eligible is False
    assert resources[0].license_safety_result == "unsafe"
    assert review_items == []

