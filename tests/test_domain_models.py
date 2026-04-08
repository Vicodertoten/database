from pydantic import ValidationError

from database_core.domain.enums import CanonicalRank, MediaType, SimilarityRelationType, SourceName
from database_core.domain.models import CanonicalTaxon, ExternalMapping, MediaAsset, SimilarTaxon


def test_canonical_taxon_requires_stable_lowercase_identifier() -> None:
    try:
        CanonicalTaxon(
            canonical_taxon_id="Bird:Turdus-merula",
            scientific_name="Turdus merula",
            canonical_rank=CanonicalRank.SPECIES,
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected canonical taxon validation to reject unstable identifier")


def test_media_asset_preserves_provenance_fields() -> None:
    media_asset = MediaAsset(
        media_id="media:inaturalist:fixture-1",
        source_name=SourceName.INATURALIST,
        source_media_id="fixture-1",
        media_type=MediaType.IMAGE,
        source_url="fixture://inaturalist/media/fixture-1",
        attribution="(c) observer, some rights reserved (CC BY)",
        author="observer",
        license="CC-BY",
        mime_type="image/jpeg",
        file_extension="jpg",
        source_observation_uid="obs:inaturalist:fixture-1",
        canonical_taxon_id="bird:turdus-merula",
        raw_payload_ref="data/fixtures/birds_pilot.json#/observations/0/media/0",
    )

    assert media_asset.source_url == "fixture://inaturalist/media/fixture-1"
    assert media_asset.raw_payload_ref == "data/fixtures/birds_pilot.json#/observations/0/media/0"
    assert media_asset.source_observation_uid == "obs:inaturalist:fixture-1"


def test_external_mapping_uses_non_blank_identifier() -> None:
    mapping = ExternalMapping(source_name=SourceName.INATURALIST, external_id="12716")
    assert mapping.external_id == "12716"


def test_canonical_taxon_derives_similar_taxon_ids_from_similarity_graph() -> None:
    taxon = CanonicalTaxon(
        canonical_taxon_id="bird:turdus-merula",
        scientific_name="Turdus merula",
        canonical_rank=CanonicalRank.SPECIES,
        similar_taxa=[
            SimilarTaxon(
                target_canonical_taxon_id="bird:erithacus-rubecula",
                source_name=SourceName.INATURALIST,
                relation_type=SimilarityRelationType.SIMILAR_SPECIES,
                confidence=0.71,
            )
        ],
    )

    assert taxon.similar_taxon_ids == ["bird:erithacus-rubecula"]
