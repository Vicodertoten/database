"""Tests for multilingual pedagogical surfaces (P3).

Validates:
1. CanonicalTaxon multilingual field validators
2. Enrichment multilingual extraction and merging
3. Pipeline multilingual name population
4. Round-trip from enrichment to playable items
"""

import pytest

from database_core.domain.enums import CanonicalRank, TaxonGroup, TaxonStatus
from database_core.domain.models import CanonicalTaxon
from database_core.enrichment.taxa import enrich_canonical_taxa


def test_canonical_taxon_validates_common_names_by_language_dict():
    """Test that common_names_by_language accepts valid language dicts."""
    taxon = CanonicalTaxon(
        canonical_taxon_id="taxon:birds:000001",
        taxon_group=TaxonGroup.BIRDS,
        accepted_scientific_name="Columba palumbus",
        canonical_rank=CanonicalRank.SPECIES,
        taxon_status=TaxonStatus.ACTIVE,
        common_names=[],
        common_names_by_language={
            "en": ["Common Wood-Pigeon"],
            "fr": ["Ramier", "Pigeon ramier"],
            "nl": ["Houtduif"],
        },
    )
    assert taxon.common_names_by_language is not None
    assert taxon.common_names_by_language["en"] == ["Common Wood-Pigeon"]
    assert taxon.common_names_by_language["fr"] == ["Ramier", "Pigeon ramier"]
    assert taxon.common_names_by_language["nl"] == ["Houtduif"]


def test_canonical_taxon_normalizes_common_names_by_language():
    """Test that the validator strips whitespace and removes empty strings."""
    taxon = CanonicalTaxon(
        canonical_taxon_id="taxon:birds:000001",
        taxon_group=TaxonGroup.BIRDS,
        accepted_scientific_name="Columba palumbus",
        canonical_rank=CanonicalRank.SPECIES,
        taxon_status=TaxonStatus.ACTIVE,
        common_names=[],
        common_names_by_language={
            "en": ["  Common Wood-Pigeon  ", "", "Wood Pigeon"],
            "fr": ["  Ramier  ", "Pigeon ramier"],
        },
    )
    assert taxon.common_names_by_language["en"] == ["Common Wood-Pigeon", "Wood Pigeon"]
    assert taxon.common_names_by_language["fr"] == ["Ramier", "Pigeon ramier"]


def test_canonical_taxon_rejects_invalid_common_names_by_language():
    """Test that invalid structures are rejected."""
    with pytest.raises(ValueError, match="common_names_by_language"):
        CanonicalTaxon(
            canonical_taxon_id="taxon:birds:000001",
            taxon_group=TaxonGroup.BIRDS,
            accepted_scientific_name="Columba palumbus",
            canonical_rank=CanonicalRank.SPECIES,
            taxon_status=TaxonStatus.ACTIVE,
            common_names=[],
            common_names_by_language="invalid",  # type: ignore
        )


def test_canonical_taxon_fallback_monolingual_to_multilingual():
    """Test that monolingual names populate multilingual dict at English."""
    taxon = CanonicalTaxon(
        canonical_taxon_id="taxon:birds:000001",
        taxon_group=TaxonGroup.BIRDS,
        accepted_scientific_name="Columba palumbus",
        canonical_rank=CanonicalRank.SPECIES,
        taxon_status=TaxonStatus.ACTIVE,
        common_names=["Common Wood-Pigeon", "Wood Pigeon"],
        common_names_by_language=None,  # Not populated
    )
    # After model_validator runs, should populate English from common_names
    assert taxon.common_names_by_language is not None
    assert "en" in taxon.common_names_by_language
    assert taxon.common_names_by_language["en"] == ["Common Wood-Pigeon", "Wood Pigeon"]


def test_enrichment_merges_multilingual_names():
    """Test that enrichment extraction and merging works with multilingual data."""
    base_taxon = CanonicalTaxon(
        canonical_taxon_id="taxon:birds:000014",
        taxon_group=TaxonGroup.BIRDS,
        accepted_scientific_name="Turdus merula",
        canonical_rank=CanonicalRank.SPECIES,
        taxon_status=TaxonStatus.ACTIVE,
        common_names=["Eurasian Blackbird"],
        common_names_by_language=None,
    )
    
    # Simulate iNaturalist payload with multilingual names
    payload = {
        "results": [
            {
                "id": 12716,
                "name": "Turdus merula",
                "preferred_common_name": "Eurasian Blackbird",
                "names": [
                    {"name": "Eurasian Blackbird", "language": "en"},
                    {"name": "Merle noir", "language": "fr"},
                    {"name": "Merel", "language": "nl"},
                    {"name": "Blackbird", "language": "en"},  # Duplicate for dedup test
                ],
                "key_identification_features": [],
                "similar_taxa": [],
            }
        ]
    }
    
    enriched_list = enrich_canonical_taxa(
        [base_taxon],
        taxon_payloads_by_canonical_taxon_id={"taxon:birds:000014": payload},
    )
    
    assert len(enriched_list) == 1
    enriched = enriched_list[0]
    
    # Verify multilingual names extracted
    assert enriched.common_names_by_language is not None
    assert "en" in enriched.common_names_by_language
    assert "fr" in enriched.common_names_by_language
    assert "nl" in enriched.common_names_by_language
    
    # Verify deduplication worked
    assert "Eurasian Blackbird" in enriched.common_names_by_language["en"]
    assert "Blackbird" in enriched.common_names_by_language["en"]
    assert len(enriched.common_names_by_language["en"]) >= 2
    
    # Verify other languages extracted
    assert "Merle noir" in enriched.common_names_by_language["fr"]
    assert "Merel" in enriched.common_names_by_language["nl"]


def test_enrichment_reads_localized_taxa_preferred_names_first():
    base_taxon = CanonicalTaxon(
        canonical_taxon_id="taxon:birds:000001",
        taxon_group=TaxonGroup.BIRDS,
        accepted_scientific_name="Columba palumbus",
        canonical_rank=CanonicalRank.SPECIES,
        taxon_status=TaxonStatus.ACTIVE,
        common_names=[],
    )
    payload = {
        "localized_taxa": {
            "fr": {
                "results": [
                    {
                        "preferred_common_name": "Pigeon ramier",
                        "names": [
                            {"locale": "fr", "name": "Palombe", "is_valid": True},
                            {"locale": "en", "name": "Wood Pigeon", "is_valid": True},
                        ],
                    }
                ]
            },
            "en": {
                "results": [
                    {
                        "preferred_common_name": "Common Wood-Pigeon",
                        "names": [
                            {"locale": "en", "name": "Wood Pigeon", "is_valid": True},
                            {"locale": "fr", "name": "Palombe", "is_valid": True},
                        ],
                    }
                ]
            },
            "nl": {
                "results": [
                    {
                        "preferred_common_name": "Houtduif",
                        "names": [{"locale": "nl", "name": "Houtduif", "is_valid": True}],
                    }
                ]
            },
        }
    }

    enriched = enrich_canonical_taxa(
        [base_taxon],
        taxon_payloads_by_canonical_taxon_id={"taxon:birds:000001": payload},
    )[0]

    assert enriched.common_names_by_language == {
        "fr": ["Pigeon ramier", "Palombe"],
        "en": ["Common Wood-Pigeon", "Wood Pigeon"],
        "nl": ["Houtduif"],
    }
    assert enriched.common_names == ["Common Wood-Pigeon"]


def test_enrichment_handles_missing_multilingual_data():
    """Test that enrichment gracefully handles payloads without multilingual data."""
    base_taxon = CanonicalTaxon(
        canonical_taxon_id="taxon:birds:000014",
        taxon_group=TaxonGroup.BIRDS,
        accepted_scientific_name="Turdus merula",
        canonical_rank=CanonicalRank.SPECIES,
        taxon_status=TaxonStatus.ACTIVE,
        common_names=["Eurasian Blackbird"],
    )
    
    # Payload without 'names' array (backward compatible)
    payload = {
        "results": [
            {
                "id": 12716,
                "name": "Turdus merula",
                "preferred_common_name": "Eurasian Blackbird",
                "key_identification_features": [],
                "similar_taxa": [],
            }
        ]
    }
    
    enriched_list = enrich_canonical_taxa(
        [base_taxon],
        taxon_payloads_by_canonical_taxon_id={"taxon:birds:000014": payload},
    )
    
    assert len(enriched_list) == 1
    enriched = enriched_list[0]
    
    # Should still work, just without multilingual data
    assert enriched.accepted_scientific_name == "Turdus merula"
    # Multilingual dict may be None or populated from fallback
    if enriched.common_names_by_language is not None:
        assert "en" in enriched.common_names_by_language


def test_playable_item_common_names_i18n_populated_from_multilingual():
    """Test that PlayableItems get correctly populated multilingual common names.
    
    This is an integration test validating that the pipeline's
    _build_common_names_i18n function works correctly.
    """
    from database_core.pipeline.runner import _build_common_names_i18n
    
    # Create a taxon with multilingual names
    taxon = CanonicalTaxon(
        canonical_taxon_id="taxon:birds:000014",
        taxon_group=TaxonGroup.BIRDS,
        accepted_scientific_name="Turdus merula",
        canonical_rank=CanonicalRank.SPECIES,
        taxon_status=TaxonStatus.ACTIVE,
        common_names=["Eurasian Blackbird"],
        common_names_by_language={
            "en": ["Eurasian Blackbird", "Blackbird"],
            "fr": ["Merle noir"],
            "nl": ["Merel"],
        },
    )
    
    result = _build_common_names_i18n(taxon)
    
    # Verify all required languages present
    assert "en" in result
    assert "fr" in result
    assert "nl" in result
    
    # Verify content populated
    assert "Eurasian Blackbird" in result["en"]
    assert "Merle noir" in result["fr"]
    assert "Merel" in result["nl"]


def test_playable_item_common_names_i18n_fallback_without_multilingual():
    """Test that PlayableItems fall back to common_names when multilingual unavailable."""
    from database_core.pipeline.runner import _build_common_names_i18n
    
    # Create a taxon WITHOUT multilingual names (legacy)
    taxon = CanonicalTaxon(
        canonical_taxon_id="taxon:birds:000001",
        taxon_group=TaxonGroup.BIRDS,
        accepted_scientific_name="Columba palumbus",
        canonical_rank=CanonicalRank.SPECIES,
        taxon_status=TaxonStatus.ACTIVE,
        common_names=["Common Wood-Pigeon"],
        common_names_by_language=None,
    )
    
    result = _build_common_names_i18n(taxon)
    
    # Should have all languages, with fallback
    assert "en" in result
    assert "fr" in result
    assert "nl" in result
    
    # English should be populated from monolingual fallback
    assert "Common Wood-Pigeon" in result["en"]
    
    # French and Dutch should be empty
    assert result["fr"] == []
    assert result["nl"] == []


def test_confusion_hint_includes_common_names():
    """Test that confusion hints now include common names for pedagogy."""
    from database_core.domain.enums import SimilarityRelationType, SourceName
    from database_core.domain.models import SimilarTaxon
    from database_core.pipeline.runner import _build_confusion_hint
    
    # Create similar taxon with multilingual names
    similar_taxon = CanonicalTaxon(
        canonical_taxon_id="taxon:birds:000002",
        taxon_group=TaxonGroup.BIRDS,
        accepted_scientific_name="Corvus corone",
        canonical_rank=CanonicalRank.SPECIES,
        taxon_status=TaxonStatus.ACTIVE,
        common_names=["Carrion Crow"],
        common_names_by_language={
            "en": ["Carrion Crow", "Crow"],
            "fr": ["Corneille noire"],
        },
    )
    
    # Create reference taxon with a SimilarTaxon relationship
    reference_taxon = CanonicalTaxon(
        canonical_taxon_id="taxon:birds:000003",
        taxon_group=TaxonGroup.BIRDS,
        accepted_scientific_name="Turdus merula",
        canonical_rank=CanonicalRank.SPECIES,
        taxon_status=TaxonStatus.ACTIVE,
        common_names=[],
        similar_taxa=[
            SimilarTaxon(
                target_canonical_taxon_id="taxon:birds:000002",
                source_name=SourceName.INATURALIST,
                relation_type=SimilarityRelationType.VISUAL_LOOKALIKE,
                confidence=0.8,
            )
        ],
    )
    
    canonical_by_id = {
        "taxon:birds:000002": similar_taxon,
        "taxon:birds:000003": reference_taxon,
    }
    
    hint = _build_confusion_hint(taxon=reference_taxon, canonical_by_id=canonical_by_id)
    
    # Verify hint includes both scientific and common name
    assert hint is not None
    assert "Corvus corone" in hint
    assert "(Carrion Crow)" in hint
    assert "Compare with:" in hint
