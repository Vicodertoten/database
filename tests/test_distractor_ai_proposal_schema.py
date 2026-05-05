from __future__ import annotations

import json
from pathlib import Path

import pytest

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "schemas" / "distractor_ai_proposal_v1.schema.json"
)


def _load_schema() -> dict:
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def _valid_candidate(
    scientific_name: str = "Accipiter gentilis",
    rank: int = 1,
    source_reference: str | None = "inaturalist_similar_species",
) -> dict:
    return {
        "scientific_name": scientific_name,
        "source_reference": source_reference,
        "rank": rank,
        "confusion_types": ["visual_similarity"],
        "pedagogical_value": "high",
        "difficulty_level": "medium",
        "learner_level": "mixed",
        "reason": "Closely related accipiter, commonly confused by beginners.",
        "confidence": 0.9,
    }


def _valid_proposal(**overrides) -> dict:
    base = {
        "schema_version": "distractor_ai_proposal_v1",
        "prompt_version": "v1.0",
        "target_scientific_name": "Accipiter nisus",
        "ranked_existing_candidates": [_valid_candidate()],
        "proposed_additional_candidates": [],
        "overall_notes": None,
        "confidence": 0.85,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_valid_ai_proposal_passes_schema() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema = _load_schema()
    jsonschema.validate(instance=_valid_proposal(), schema=schema)


def test_valid_proposal_with_proposed_additional_candidates() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema = _load_schema()
    proposal = _valid_proposal(
        proposed_additional_candidates=[
            _valid_candidate(
                scientific_name="UnknownSpecies notinregistry",
                rank=1,
                source_reference="ai_proposal",
            )
        ]
    )
    # Schema allows any scientific name — post-processing must validate
    jsonschema.validate(instance=proposal, schema=schema)


def test_additional_property_fails() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema = _load_schema()
    proposal = _valid_proposal()
    proposal["unexpected_field"] = "should_not_be_here"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=proposal, schema=schema)


def test_additional_property_in_candidate_fails() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema = _load_schema()
    bad_candidate = _valid_candidate()
    bad_candidate["extra_key"] = "bad"
    proposal = _valid_proposal(ranked_existing_candidates=[bad_candidate])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=proposal, schema=schema)


def test_invalid_confusion_type_fails() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema = _load_schema()
    bad_candidate = _valid_candidate()
    bad_candidate["confusion_types"] = ["not_a_real_confusion_type"]
    proposal = _valid_proposal(ranked_existing_candidates=[bad_candidate])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=proposal, schema=schema)


def test_invalid_confidence_too_high_fails() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema = _load_schema()
    proposal = _valid_proposal(confidence=1.5)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=proposal, schema=schema)


def test_invalid_candidate_confidence_too_low_fails() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema = _load_schema()
    bad_candidate = _valid_candidate()
    bad_candidate["confidence"] = -0.1
    proposal = _valid_proposal(ranked_existing_candidates=[bad_candidate])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=proposal, schema=schema)


def test_missing_candidate_scientific_name_fails() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema = _load_schema()
    bad_candidate = _valid_candidate()
    del bad_candidate["scientific_name"]
    proposal = _valid_proposal(ranked_existing_candidates=[bad_candidate])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=proposal, schema=schema)


def test_missing_reason_fails() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema = _load_schema()
    bad_candidate = _valid_candidate()
    del bad_candidate["reason"]
    proposal = _valid_proposal(ranked_existing_candidates=[bad_candidate])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=proposal, schema=schema)


def test_wrong_schema_version_fails() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema = _load_schema()
    proposal = _valid_proposal(schema_version="distractor_ai_proposal_v2")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=proposal, schema=schema)


def test_proposed_candidate_not_in_registry_is_allowed_at_schema_level() -> None:
    """
    Schema allows any scientific name string.
    Post-processing (validation gate) is responsible for flagging names not
    in the canonical or referenced pool as unresolved_taxon.
    This test documents that invariant.
    """
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema = _load_schema()
    # A made-up name not in any real registry
    hallucinated = _valid_candidate(
        scientific_name="Fictus inventus",
        rank=1,
        source_reference="ai_proposal",
    )
    hallucinated["confidence"] = 0.4
    hallucinated["reason"] = "Possibly confused with target; uncertain — not in known pool."
    proposal = _valid_proposal(proposed_additional_candidates=[hallucinated])
    # Schema-level validation passes — name validation is a post-processing gate
    jsonschema.validate(instance=proposal, schema=schema)


def test_empty_confusion_types_fails() -> None:
    """confusion_types must have at least 1 item."""
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema = _load_schema()
    bad_candidate = _valid_candidate()
    bad_candidate["confusion_types"] = []
    proposal = _valid_proposal(ranked_existing_candidates=[bad_candidate])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=proposal, schema=schema)


def test_invalid_pedagogical_value_fails() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    schema = _load_schema()
    bad_candidate = _valid_candidate()
    bad_candidate["pedagogical_value"] = "very_high"
    proposal = _valid_proposal(ranked_existing_candidates=[bad_candidate])
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=proposal, schema=schema)
