from __future__ import annotations

import json

import pytest

from database_core.qualification.pedagogical_media_profile_v1 import (
    build_failed_pedagogical_media_profile_v1,
    collect_schema_validation_errors_pmp_v1,
    compute_pedagogical_media_scores_v1,
    parse_pedagogical_media_profile_v1,
    validate_pedagogical_media_profile_v1,
)


def _valid_payload_without_scores() -> dict[str, object]:
    return {
        "schema_version": "pedagogical_media_profile.v1",
        "review_status": "valid",
        "review_confidence": 0.9,
        "organism_group": "bird",
        "evidence_type": "whole_organism",
        "technical_profile": {
            "technical_quality": "high",
            "sharpness": "high",
            "lighting": "high",
            "contrast": "high",
            "background_clutter": "low",
            "framing": "good",
            "distance_to_subject": "close",
        },
        "observation_profile": {
            "subject_presence": "clear",
            "subject_visibility": "high",
            "visible_parts": ["head", "beak", "breast", "wing", "tail"],
            "view_angle": "lateral",
            "occlusion": "none",
            "context_visible": ["vegetation"],
        },
        "biological_profile_visible": {
            "sex": {
                "value": "unknown",
                "confidence": "low",
                "visible_basis": None,
            },
            "life_stage": {
                "value": "adult",
                "confidence": "medium",
                "visible_basis": "adult-like plumage and body size",
            },
            "plumage_state": {
                "value": "unknown",
                "confidence": "low",
                "visible_basis": None,
            },
            "seasonal_state": {
                "value": "unknown",
                "confidence": "low",
                "visible_basis": None,
            },
        },
        "identification_profile": {
            "visual_evidence_strength": "high",
            "diagnostic_feature_visibility": "high",
            "identification_confidence_from_image": "high",
            "ambiguity_level": "low",
            "visible_field_marks": [
                {
                    "feature": "orange breast",
                    "body_part": "breast",
                    "visibility": "high",
                    "importance": "high",
                    "confidence": 0.93,
                }
            ],
            "missing_key_features": [],
            "identification_limitations": [],
        },
        "pedagogical_profile": {
            "learning_value": "high",
            "difficulty": "easy",
            "beginner_accessibility": "high",
            "expert_interest": "medium",
            "field_realism": "medium",
            "cognitive_load": "low",
            "requires_prior_knowledge": "low",
        },
        "group_specific_profile": {
            "bird": {
                "bird_visible_parts": ["head", "beak", "breast", "wing", "tail"],
                "posture": "perched",
                "behavior_visible": "perched",
                "plumage_pattern_visible": "high",
                "bill_shape_visible": "high",
                "wing_pattern_visible": "medium",
                "tail_shape_visible": "medium",
            }
        },
        "limitations": [],
    }


def _valid_payload() -> dict[str, object]:
    payload = _valid_payload_without_scores()
    payload["scores"] = compute_pedagogical_media_scores_v1(payload)
    return payload


def test_valid_payload_passes_validation() -> None:
    payload = _valid_payload()

    validate_pedagogical_media_profile_v1(payload)


def test_parse_valid_payload_computes_scores() -> None:
    payload = _valid_payload_without_scores()

    parsed = parse_pedagogical_media_profile_v1(json.dumps(payload))

    assert parsed["review_status"] == "valid"
    scores = parsed["scores"]
    assert 0 <= scores["global_quality_score"] <= 100
    assert set(scores["usage_scores"].keys()) == {
        "basic_identification",
        "field_observation",
        "confusion_learning",
        "morphology_learning",
        "species_card",
        "indirect_evidence_learning",
    }


def test_parse_invalid_json_fails_closed() -> None:
    parsed = parse_pedagogical_media_profile_v1("{not-valid-json")

    assert parsed["review_status"] == "failed"
    assert parsed["failure_reason"] == "model_output_invalid"


def test_parse_non_object_json_fails_closed() -> None:
    parsed = parse_pedagogical_media_profile_v1(json.dumps(["not", "an", "object"]))

    assert parsed["review_status"] == "failed"
    assert parsed["failure_reason"] == "model_output_invalid"


def test_schema_mismatch_fails_closed_with_diagnostics() -> None:
    payload = _valid_payload_without_scores()
    del payload["technical_profile"]

    parsed = parse_pedagogical_media_profile_v1(json.dumps(payload))

    assert parsed["review_status"] == "failed"
    assert parsed["failure_reason"] == "schema_validation_failed"
    diagnostics = parsed.get("diagnostics") or {}
    assert diagnostics.get("parsed_json_available") is True
    assert diagnostics.get("schema_error_count", 0) >= 1
    assert diagnostics.get("schema_failure_cause")
    assert diagnostics.get("raw_model_output_sha256")
    assert diagnostics.get("raw_model_output_excerpt")


def test_biological_rule_visible_basis_required_for_asserted_value() -> None:
    payload = _valid_payload()
    payload["biological_profile_visible"]["life_stage"] = {
        "value": "adult",
        "confidence": "medium",
        "visible_basis": None,
    }

    with pytest.raises(ValueError, match="visible_basis"):
        validate_pedagogical_media_profile_v1(payload)


def test_biological_rule_unknown_disallows_high_confidence() -> None:
    payload = _valid_payload()
    payload["biological_profile_visible"]["sex"] = {
        "value": "unknown",
        "confidence": "high",
        "visible_basis": None,
    }

    with pytest.raises(ValueError, match="confidence"):
        validate_pedagogical_media_profile_v1(payload)


def test_low_basic_identification_remains_valid() -> None:
    payload = _valid_payload_without_scores()
    payload["evidence_type"] = "feather"
    payload["observation_profile"]["subject_presence"] = "indirect"
    payload["observation_profile"]["subject_visibility"] = "none"
    payload["observation_profile"]["visible_parts"] = ["feather"]
    payload["identification_profile"]["visual_evidence_strength"] = "low"
    payload["identification_profile"]["diagnostic_feature_visibility"] = "medium"
    payload["identification_profile"]["identification_confidence_from_image"] = "low"
    payload["identification_profile"]["ambiguity_level"] = "high"
    payload["identification_profile"]["visible_field_marks"] = [
        {
            "feature": "feather pattern",
            "body_part": "feather",
            "visibility": "medium",
            "importance": "medium",
            "confidence": 0.65,
        }
    ]
    payload["group_specific_profile"]["bird"] = {
        "bird_visible_parts": ["unknown"],
        "posture": "unknown",
        "behavior_visible": "unknown",
        "plumage_pattern_visible": "medium",
        "bill_shape_visible": "none",
        "wing_pattern_visible": "unknown",
        "tail_shape_visible": "unknown",
    }

    parsed = parse_pedagogical_media_profile_v1(json.dumps(payload))

    assert parsed["review_status"] == "valid"
    usage_scores = parsed["scores"]["usage_scores"]
    assert usage_scores["basic_identification"] <= 25
    assert usage_scores["indirect_evidence_learning"] >= 60


def test_failed_payload_remains_failed() -> None:
    failed_payload = build_failed_pedagogical_media_profile_v1(
        failure_reason="media_not_accessible",
    )

    validate_pedagogical_media_profile_v1(failed_payload)
    parsed = parse_pedagogical_media_profile_v1(json.dumps(failed_payload))

    assert parsed["review_status"] == "failed"
    assert parsed["failure_reason"] == "media_not_accessible"


def test_scores_are_deterministic() -> None:
    payload = _valid_payload_without_scores()

    score_a = compute_pedagogical_media_scores_v1(payload)
    score_b = compute_pedagogical_media_scores_v1(payload)

    assert score_a == score_b


def test_selection_fields_are_rejected_by_schema() -> None:
    payload = _valid_payload()
    payload["selected_for_quiz"] = True

    errors = collect_schema_validation_errors_pmp_v1(payload)

    assert errors
    assert any(error.get("cause") == "additional_property" for error in errors)
