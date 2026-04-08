import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from database_core.adapters.inaturalist_snapshot import load_pilot_taxa
from database_core.domain.canonical_governance import derive_canonical_governance_decisions
from database_core.domain.canonical_ids import CANONICAL_TAXON_ID_PATTERN, next_canonical_taxon_id
from database_core.domain.canonical_reconciliation import (
    reconcile_canonical_taxa_with_previous_state,
)
from database_core.domain.enums import CanonicalRank, MediaType, SourceName, TaxonGroup
from database_core.domain.models import (
    AIQualification,
    CanonicalTaxon,
    ExternalMapping,
    LocationMetadata,
    MediaAsset,
    SourceObservation,
    SourceQualityMetadata,
)
from database_core.pipeline.runner import run_pipeline
from database_core.qualification.ai import AIQualificationOutcome, source_external_key_for_media
from database_core.qualification.rules import qualify_media_assets


def test_r1_creates_canonical_taxon_id_for_unknown_inat_seed(tmp_path: Path) -> None:
    payload = [
        {
            "canonical_taxon_id": None,
            "accepted_scientific_name": "Parus major",
            "canonical_rank": "species",
            "taxon_status": "active",
            "authority_source": "inaturalist",
            "source_taxon_id": "12716",
        }
    ]
    temp_path = tmp_path / "r1-pilot-seed.json"
    try:
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        seeds = load_pilot_taxa(temp_path)
    finally:
        temp_path.unlink(missing_ok=True)

    assert len(seeds) == 1
    assert seeds[0].canonical_taxon_id is not None


def test_r2_generated_id_matches_canonical_pattern() -> None:
    generated = next_canonical_taxon_id(
        existing_ids=["taxon:birds:000001", "taxon:birds:000099"],
        group=TaxonGroup.BIRDS,
    )
    assert generated == "taxon:birds:000100"
    assert CANONICAL_TAXON_ID_PATTERN.fullmatch(generated) is not None


def test_r3_display_slug_is_generated_automatically() -> None:
    taxon = _taxon(canonical_taxon_id="taxon:birds:000001", name="Parus major")
    assert taxon.display_slug == "parus-major"


def test_r4_name_change_produces_name_update_event() -> None:
    previous = [_taxon(canonical_taxon_id="taxon:birds:000001", name="Parus major")]
    current = [_taxon(canonical_taxon_id="taxon:birds:000001", name="Parus major updated")]

    decisions = derive_canonical_governance_decisions(
        previous_taxa=previous,
        current_taxa=current,
        effective_at=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
    )
    assert any(item.event.event_type == "name_update" for item in decisions)


def test_r5_previous_accepted_name_is_added_to_synonyms_on_reconciliation() -> None:
    previous = [
        _taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
            synonyms=["Great tit"],
        )
    ]
    current = [_taxon(canonical_taxon_id="taxon:birds:000001", name="Parus major updated")]

    reconciled = reconcile_canonical_taxa_with_previous_state(
        current_taxa=current,
        previous_taxa=previous,
    )

    assert reconciled[0].accepted_scientific_name == "Parus major updated"
    assert reconciled[0].synonyms == ["Great tit", "Parus major"]


def test_r6_rejects_new_media_assets_for_deprecated_taxon(tmp_path: Path) -> None:
    fixture_payload = {
        "dataset_id": "fixture:r6",
        "captured_at": "2026-04-08T00:00:00Z",
        "canonical_taxa": [
            {
                "canonical_taxon_id": "taxon:birds:000001",
                "accepted_scientific_name": "Parus major",
                "canonical_rank": "species",
                "taxon_group": "birds",
                "taxon_status": "deprecated",
                "authority_source": "inaturalist",
                "external_source_mappings": [
                    {"source_name": "inaturalist", "external_id": "12716"}
                ],
            }
        ],
        "observations": [
            {
                "source_name": "inaturalist",
                "source_observation_id": "obs-r6-1",
                "source_taxon_id": "12716",
                "observed_at": "2026-04-08T00:00:00Z",
                "location": {"place_name": "Brussels"},
                "source_quality": {
                    "quality_grade": "research",
                    "research_grade": True,
                    "observation_license": "CC-BY",
                    "captive": False,
                },
                "raw_payload_ref": "fixture://r6/obs/0",
                "canonical_taxon_id": "taxon:birds:000001",
                "media": [
                    {
                        "source_media_id": "media-r6-1",
                        "media_type": "image",
                        "source_url": "fixture://r6/media/1",
                        "attribution": "(c) observer, some rights reserved (CC BY)",
                        "license": "CC-BY",
                        "mime_type": "image/jpeg",
                        "file_extension": "jpg",
                        "width": 1400,
                        "height": 1000,
                    }
                ],
            }
        ],
    }
    fixture_path = tmp_path / "r6.json"
    fixture_path.write_text(
        json.dumps(fixture_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="deprecated taxa cannot receive new media assets"):
        run_pipeline(
            fixture_path=fixture_path,
            db_path=tmp_path / "r6.sqlite",
            normalized_snapshot_path=tmp_path / "r6.normalized.json",
            qualification_snapshot_path=tmp_path / "r6.qualified.json",
            export_path=tmp_path / "r6.export.json",
        )


def test_r7_replacement_auto_deprecates_source_taxon() -> None:
    taxon = _taxon(
        canonical_taxon_id="taxon:birds:000001",
        name="Parus major",
        status="active",
        replaced_by="taxon:birds:000002",
    )
    assert taxon.taxon_status == "deprecated"


def test_r8_split_merge_replace_relationship_fields_are_preserved() -> None:
    taxon = _taxon(
        canonical_taxon_id="taxon:birds:000001",
        name="Parus major",
        status="active",
        split_into=["taxon:birds:000002"],
        merged_into="taxon:birds:000003",
        replaced_by="taxon:birds:000004",
    )
    assert taxon.split_into == ["taxon:birds:000002"]
    assert taxon.merged_into == "taxon:birds:000003"
    assert taxon.replaced_by == "taxon:birds:000004"
    assert taxon.taxon_status == "deprecated"


def test_r9_provisional_taxon_is_not_exportable_by_default() -> None:
    observation = _observation(canonical_taxon_id="taxon:birds:000001")
    media_asset = _media_asset(observation=observation, canonical_taxon_id="taxon:birds:000001")
    ai_outcome = AIQualificationOutcome(
        status="ok",
        qualification=AIQualification(
            technical_quality="high",
            pedagogical_quality="high",
            confidence=0.95,
            model_name="gemini-3.1-flash-lite-preview",
        ),
    )

    resources, _ = qualify_media_assets(
        canonical_taxa=[
            _taxon(
                canonical_taxon_id="taxon:birds:000001",
                name="Parus major",
                status="provisional",
            )
        ],
        observations=[observation],
        media_assets=[media_asset],
        ai_qualifications_by_source_media_key={
            source_external_key_for_media(media_asset): ai_outcome
        },
        created_at=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
        run_id="run:20260408T000000Z:aaaaaaaa",
        uncertain_policy="reject",
    )

    assert resources[0].export_eligible is False


def test_r10_rejects_secondary_source_for_auto_creation(tmp_path: Path) -> None:
    payload = [
        {
            "canonical_taxon_id": None,
            "accepted_scientific_name": "Parus major",
            "canonical_rank": "species",
            "taxon_status": "active",
            "authority_source": "gbif",
            "source_taxon_id": "12716",
        }
    ]
    temp_path = tmp_path / "r10-pilot-seed.json"
    try:
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="unsupported authority_source"):
            load_pilot_taxa(temp_path)
    finally:
        temp_path.unlink(missing_ok=True)


def test_r11_ambiguous_transition_is_routed_to_manual_review() -> None:
    previous = [_taxon(canonical_taxon_id="taxon:birds:000001", name="Parus major")]
    current = [
        _taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
            split_into=["taxon:birds:999999"],
        )
    ]
    decisions = derive_canonical_governance_decisions(
        previous_taxa=previous,
        current_taxa=current,
        effective_at=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
    )
    split_decision = [item for item in decisions if item.event.event_type == "split"][0]

    assert split_decision.decision_status == "manual_reviewed"
    assert split_decision.decision_reason == "ambiguous_transition_missing_target"


def test_r12_ai_enrichment_cannot_change_canonical_identity() -> None:
    observation = _observation(canonical_taxon_id="taxon:birds:000001")
    media_asset = _media_asset(observation=observation, canonical_taxon_id="taxon:birds:000001")
    ai_outcome = AIQualificationOutcome(
        status="ok",
        qualification=AIQualification(
            technical_quality="high",
            pedagogical_quality="high",
            confidence=0.95,
            model_name="gemini-3.1-flash-lite-preview",
        ),
    )

    resources, _ = qualify_media_assets(
        canonical_taxa=[_taxon(canonical_taxon_id="taxon:birds:000001", name="Parus major")],
        observations=[observation],
        media_assets=[media_asset],
        ai_qualifications_by_source_media_key={
            source_external_key_for_media(media_asset): ai_outcome
        },
        created_at=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
        run_id="run:20260408T000000Z:aaaaaaaa",
        uncertain_policy="reject",
    )

    assert resources[0].canonical_taxon_id == "taxon:birds:000001"


def _taxon(
    *,
    canonical_taxon_id: str,
    name: str,
    status: str = "active",
    synonyms: list[str] | None = None,
    split_into: list[str] | None = None,
    merged_into: str | None = None,
    replaced_by: str | None = None,
) -> CanonicalTaxon:
    return CanonicalTaxon(
        canonical_taxon_id=canonical_taxon_id,
        accepted_scientific_name=name,
        canonical_rank=CanonicalRank.SPECIES,
        taxon_group=TaxonGroup.BIRDS,
        taxon_status=status,
        authority_source=SourceName.INATURALIST,
        display_slug=None,
        synonyms=synonyms or [],
        common_names=[],
        key_identification_features=[],
        source_enrichment_status="seeded",
        bird_scope_compatible=True,
        external_source_mappings=[
            ExternalMapping(source_name=SourceName.INATURALIST, external_id="12716")
        ],
        external_similarity_hints=[],
        similar_taxa=[],
        similar_taxon_ids=[],
        split_into=split_into or [],
        merged_into=merged_into,
        replaced_by=replaced_by,
        derived_from=None,
    )


def _observation(*, canonical_taxon_id: str) -> SourceObservation:
    return SourceObservation(
        observation_uid="obs:inaturalist:r-rules-1",
        source_name=SourceName.INATURALIST,
        source_observation_id="rules-1",
        source_taxon_id="12716",
        observed_at=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
        location=LocationMetadata(place_name="Brussels, BE"),
        source_quality=SourceQualityMetadata(
            quality_grade="research",
            research_grade=True,
            observation_license="CC-BY",
            captive=False,
        ),
        raw_payload_ref="fixture://rules/observation/1",
        canonical_taxon_id=canonical_taxon_id,
    )


def _media_asset(*, observation: SourceObservation, canonical_taxon_id: str) -> MediaAsset:
    return MediaAsset(
        media_id="media:inaturalist:r-rules-1",
        source_name=SourceName.INATURALIST,
        source_media_id="rules-media-1",
        media_type=MediaType.IMAGE,
        source_url="fixture://rules/media/1",
        attribution="(c) observer, some rights reserved (CC BY)",
        author="observer",
        license="CC-BY",
        mime_type="image/jpeg",
        file_extension="jpg",
        width=1600,
        height=1200,
        source_observation_uid=observation.observation_uid,
        canonical_taxon_id=canonical_taxon_id,
        raw_payload_ref="fixture://rules/observation/1/media/1",
    )
