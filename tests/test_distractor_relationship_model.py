from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from database_core.domain.enums import (
    CandidateTaxonRefType,
    DistractorConfusionType,
    DistractorDifficultyLevel,
    DistractorLearnerLevel,
    DistractorPedagogicalValue,
    DistractorRelationshipSource,
    DistractorRelationshipStatus,
)
from database_core.domain.models import DistractorRelationship

_NOW = datetime(2026, 5, 5, 12, 0, 0)

SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "distractor_relationship_v1.schema.json"


def _base(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "relationship_id": "dr-test-001",
        "target_canonical_taxon_id": "taxon:birds:001234",
        "target_scientific_name": "Accipiter nisus",
        "candidate_taxon_ref_type": CandidateTaxonRefType.CANONICAL_TAXON,
        "candidate_taxon_ref_id": "taxon:birds:005678",
        "candidate_scientific_name": "Accipiter gentilis",
        "source": DistractorRelationshipSource.INATURALIST_SIMILAR_SPECIES,
        "source_rank": 1,
        "status": DistractorRelationshipStatus.CANDIDATE,
        "created_at": _NOW,
    }
    base.update(overrides)
    return base


# --- Valid relationship tests ---


def test_valid_canonical_candidate_relationship() -> None:
    rel = DistractorRelationship(**_base())
    assert rel.relationship_id == "dr-test-001"
    assert rel.candidate_taxon_ref_type == CandidateTaxonRefType.CANONICAL_TAXON
    assert rel.candidate_taxon_ref_id == "taxon:birds:005678"
    assert rel.status == DistractorRelationshipStatus.CANDIDATE


def test_valid_referenced_taxon_candidate_relationship() -> None:
    rel = DistractorRelationship(
        **_base(
            candidate_taxon_ref_type=CandidateTaxonRefType.REFERENCED_TAXON,
            candidate_taxon_ref_id="ref:inat:12345",
        )
    )
    assert rel.candidate_taxon_ref_type == CandidateTaxonRefType.REFERENCED_TAXON
    assert rel.candidate_taxon_ref_id == "ref:inat:12345"


def test_valid_unresolved_candidate_relationship() -> None:
    rel = DistractorRelationship(
        **_base(
            candidate_taxon_ref_type=CandidateTaxonRefType.UNRESOLVED_TAXON,
            candidate_taxon_ref_id=None,
            candidate_scientific_name="Accipiter brevipes",
            status=DistractorRelationshipStatus.NEEDS_REVIEW,
        )
    )
    assert rel.candidate_taxon_ref_type == CandidateTaxonRefType.UNRESOLVED_TAXON
    assert rel.candidate_taxon_ref_id is None
    assert rel.status == DistractorRelationshipStatus.NEEDS_REVIEW


# --- Validation failure tests ---


def test_unresolved_candidate_cannot_be_validated() -> None:
    with pytest.raises(ValueError, match="unresolved_taxon cannot have status=validated"):
        DistractorRelationship(
            **_base(
                candidate_taxon_ref_type=CandidateTaxonRefType.UNRESOLVED_TAXON,
                candidate_taxon_ref_id=None,
                candidate_scientific_name="Accipiter brevipes",
                status=DistractorRelationshipStatus.VALIDATED,
            )
        )


def test_emergency_diversity_fallback_cannot_be_validated() -> None:
    with pytest.raises(
        ValueError,
        match="emergency_diversity_fallback relationships cannot be status=validated",
    ):
        DistractorRelationship(
            **_base(
                source=DistractorRelationshipSource.EMERGENCY_DIVERSITY_FALLBACK,
                status=DistractorRelationshipStatus.VALIDATED,
                confusion_types=[DistractorConfusionType.SAME_GENUS],
            )
        )


def test_missing_candidate_scientific_name_fails() -> None:
    with pytest.raises(ValueError):
        DistractorRelationship(**_base(candidate_scientific_name=""))


def test_canonical_taxon_ref_requires_ref_id() -> None:
    with pytest.raises(ValueError, match="candidate_taxon_ref_id is required"):
        DistractorRelationship(
            **_base(
                candidate_taxon_ref_type=CandidateTaxonRefType.CANONICAL_TAXON,
                candidate_taxon_ref_id=None,
            )
        )


def test_referenced_taxon_ref_requires_ref_id() -> None:
    with pytest.raises(ValueError, match="candidate_taxon_ref_id is required"):
        DistractorRelationship(
            **_base(
                candidate_taxon_ref_type=CandidateTaxonRefType.REFERENCED_TAXON,
                candidate_taxon_ref_id=None,
            )
        )


def test_unresolved_taxon_requires_null_ref_id() -> None:
    with pytest.raises(ValueError, match="candidate_taxon_ref_id must be null"):
        DistractorRelationship(
            **_base(
                candidate_taxon_ref_type=CandidateTaxonRefType.UNRESOLVED_TAXON,
                candidate_taxon_ref_id="some-id",
                candidate_scientific_name="Accipiter brevipes",
                status=DistractorRelationshipStatus.NEEDS_REVIEW,
            )
        )


def test_validated_requires_at_least_one_confusion_type() -> None:
    with pytest.raises(ValueError, match="validated relationships must have at least one"):
        DistractorRelationship(
            **_base(
                status=DistractorRelationshipStatus.VALIDATED,
                confusion_types=[],
            )
        )


def test_target_cannot_equal_candidate_scientific_name() -> None:
    with pytest.raises(
        ValueError,
        match="target_scientific_name must not equal candidate_scientific_name",
    ):
        DistractorRelationship(
            **_base(
                target_scientific_name="Accipiter nisus",
                candidate_scientific_name="Accipiter nisus",
            )
        )


# --- Optional fields ---


def test_valid_relationship_with_all_optional_fields() -> None:
    rel = DistractorRelationship(
        **_base(
            status=DistractorRelationshipStatus.VALIDATED,
            confusion_types=[
                DistractorConfusionType.VISUAL_SIMILARITY,
                DistractorConfusionType.SAME_GENUS,
            ],
            pedagogical_value=DistractorPedagogicalValue.HIGH,
            difficulty_level=DistractorDifficultyLevel.HARD,
            learner_level=DistractorLearnerLevel.INTERMEDIATE,
            reason="Both are small accipiters with similar flight silhouette.",
            constraints={"region_hint": "BE"},
            updated_at=_NOW,
        )
    )
    assert rel.status == DistractorRelationshipStatus.VALIDATED
    assert DistractorConfusionType.VISUAL_SIMILARITY in rel.confusion_types
    assert rel.pedagogical_value == DistractorPedagogicalValue.HIGH


# --- Schema tests ---


def _load_schema() -> dict[str, object]:
    return json.loads(SCHEMA_PATH.read_text())


def test_schema_validates_a_valid_relationship() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema = _load_schema()
    instance = {
        "relationship_id": "dr-001",
        "target_canonical_taxon_id": "taxon:birds:001234",
        "target_scientific_name": "Accipiter nisus",
        "candidate_taxon_ref_type": "canonical_taxon",
        "candidate_taxon_ref_id": "taxon:birds:005678",
        "candidate_scientific_name": "Accipiter gentilis",
        "source": "inaturalist_similar_species",
        "source_rank": 1,
        "status": "candidate",
        "created_at": "2026-05-05T12:00:00",
    }
    jsonschema.validate(instance, schema)


def test_schema_rejects_additional_properties() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema = _load_schema()
    instance = {
        "relationship_id": "dr-001",
        "target_canonical_taxon_id": "taxon:birds:001234",
        "target_scientific_name": "Accipiter nisus",
        "candidate_taxon_ref_type": "canonical_taxon",
        "candidate_taxon_ref_id": "taxon:birds:005678",
        "candidate_scientific_name": "Accipiter gentilis",
        "source": "inaturalist_similar_species",
        "source_rank": 1,
        "status": "candidate",
        "created_at": "2026-05-05T12:00:00",
        "unknown_extra_field": "should_fail",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)
