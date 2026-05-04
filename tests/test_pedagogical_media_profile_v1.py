from __future__ import annotations

import copy
import json
from collections.abc import Mapping

import pytest

from database_core.qualification.pedagogical_media_profile_v1 import (
    build_failed_pedagogical_media_profile_v1,
    collect_schema_validation_errors_pmp_v1,
    compute_pedagogical_media_scores_v1,
    parse_pedagogical_media_profile_v1,
    validate_pedagogical_media_profile_v1,
)


def _clear_bird_profile_payload() -> dict[str, object]:
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


def _partial_occluded_bird_profile_payload() -> dict[str, object]:
    payload = copy.deepcopy(_clear_bird_profile_payload())
    payload["evidence_type"] = "partial_organism"
    payload["review_confidence"] = 0.72
    payload["observation_profile"] = {
        "subject_presence": "partial",
        "subject_visibility": "medium",
        "visible_parts": ["head", "beak", "breast"],
        "view_angle": "mixed",
        "occlusion": "major",
        "context_visible": ["vegetation", "tree"],
    }
    payload["identification_profile"] = {
        "visual_evidence_strength": "medium",
        "diagnostic_feature_visibility": "medium",
        "identification_confidence_from_image": "medium",
        "ambiguity_level": "medium",
        "visible_field_marks": [
            {
                "feature": "bill shape visible despite branches",
                "body_part": "beak",
                "visibility": "medium",
                "importance": "high",
                "confidence": 0.71,
            }
        ],
        "missing_key_features": ["tail", "legs"],
        "identification_limitations": ["heavy vegetation occlusion"],
    }
    payload["group_specific_profile"] = {
        "bird": {
            "bird_visible_parts": ["head", "beak", "breast"],
            "posture": "foraging",
            "behavior_visible": "foraging",
            "plumage_pattern_visible": "medium",
            "bill_shape_visible": "medium",
            "wing_pattern_visible": "low",
            "tail_shape_visible": "none",
        }
    }
    payload["limitations"] = ["tail not visible", "bird partly hidden by branches"]
    return payload


def _feather_profile_payload() -> dict[str, object]:
    payload = copy.deepcopy(_clear_bird_profile_payload())
    payload["evidence_type"] = "feather"
    payload["review_confidence"] = 0.82
    payload["observation_profile"] = {
        "subject_presence": "indirect",
        "subject_visibility": "none",
        "visible_parts": ["feather"],
        "view_angle": "dorsal",
        "occlusion": "none",
        "context_visible": ["ground"],
    }
    payload["biological_profile_visible"] = {
        "sex": {
            "value": "not_applicable",
            "confidence": "low",
            "visible_basis": None,
        },
        "life_stage": {
            "value": "unknown",
            "confidence": "low",
            "visible_basis": None,
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
    }
    payload["identification_profile"] = {
        "visual_evidence_strength": "low",
        "diagnostic_feature_visibility": "medium",
        "identification_confidence_from_image": "low",
        "ambiguity_level": "high",
        "visible_field_marks": [
            {
                "feature": "feather barring pattern",
                "body_part": "feather",
                "visibility": "medium",
                "importance": "medium",
                "confidence": 0.65,
            }
        ],
        "missing_key_features": ["whole_body", "head", "beak"],
        "identification_limitations": [
            "media shows a feather rather than the whole organism"
        ],
    }
    payload["pedagogical_profile"] = {
        "learning_value": "medium",
        "difficulty": "hard",
        "beginner_accessibility": "low",
        "expert_interest": "medium",
        "field_realism": "high",
        "cognitive_load": "high",
        "requires_prior_knowledge": "high",
    }
    payload["group_specific_profile"] = {
        "bird": {
            "bird_visible_parts": ["unknown"],
            "posture": "unknown",
            "behavior_visible": "unknown",
            "plumage_pattern_visible": "medium",
            "bill_shape_visible": "none",
            "wing_pattern_visible": "unknown",
            "tail_shape_visible": "unknown",
        }
    }
    payload["limitations"] = [
        "whole organism is not visible",
        "species-level identification from the media alone is limited",
    ]
    return payload


def _habitat_profile_payload() -> dict[str, object]:
    payload = copy.deepcopy(_clear_bird_profile_payload())
    payload["evidence_type"] = "habitat"
    payload["review_confidence"] = 0.76
    payload["observation_profile"] = {
        "subject_presence": "indirect",
        "subject_visibility": "none",
        "visible_parts": ["habitat"],
        "view_angle": "mixed",
        "occlusion": "none",
        "context_visible": ["water", "vegetation", "reedbed", "sky"],
    }
    payload["identification_profile"] = {
        "visual_evidence_strength": "none",
        "diagnostic_feature_visibility": "low",
        "identification_confidence_from_image": "none",
        "ambiguity_level": "high",
        "visible_field_marks": [],
        "missing_key_features": ["whole_body", "head", "tail"],
        "identification_limitations": [
            "habitat context visible but organism not directly visible"
        ],
    }
    payload["pedagogical_profile"] = {
        "learning_value": "medium",
        "difficulty": "medium",
        "beginner_accessibility": "medium",
        "expert_interest": "medium",
        "field_realism": "high",
        "cognitive_load": "medium",
        "requires_prior_knowledge": "medium",
    }
    payload["group_specific_profile"] = {
        "bird": {
            "bird_visible_parts": ["unknown"],
            "posture": "unknown",
            "behavior_visible": "unknown",
            "plumage_pattern_visible": "none",
            "bill_shape_visible": "none",
            "wing_pattern_visible": "none",
            "tail_shape_visible": "none",
        }
    }
    payload["limitations"] = ["subject is not directly visible"]
    return payload


def _multiple_organisms_profile_payload() -> dict[str, object]:
    payload = copy.deepcopy(_clear_bird_profile_payload())
    payload["evidence_type"] = "multiple_organisms"
    payload["review_confidence"] = 0.79
    payload["observation_profile"] = {
        "subject_presence": "clear",
        "subject_visibility": "medium",
        "visible_parts": ["head", "wing", "tail"],
        "view_angle": "mixed",
        "occlusion": "minor",
        "context_visible": ["tree", "vegetation"],
    }
    payload["identification_profile"] = {
        "visual_evidence_strength": "medium",
        "diagnostic_feature_visibility": "medium",
        "identification_confidence_from_image": "medium",
        "ambiguity_level": "high",
        "visible_field_marks": [
            {
                "feature": "wing bar visible on one individual",
                "body_part": "wing",
                "visibility": "medium",
                "importance": "medium",
                "confidence": 0.63,
            }
        ],
        "missing_key_features": ["clear full-body view per individual"],
        "identification_limitations": [
            "multiple overlapping subjects increase ambiguity"
        ],
    }
    payload["limitations"] = ["overlapping individuals reduce clarity"]
    return payload


def _failed_payload() -> dict[str, object]:
    return build_failed_pedagogical_media_profile_v1(
        failure_reason="schema_validation_failed",
        diagnostics={
            "parsed_json_available": True,
            "schema_error_count": 1,
            "schema_errors": [
                {
                    "path": "technical_profile.technical_quality",
                    "message": "invalid enum value",
                    "cause": "enum_mismatch",
                }
            ],
        },
    )


def _with_scores(payload: Mapping[str, object]) -> dict[str, object]:
    scored = copy.deepcopy(dict(payload))
    scored["scores"] = compute_pedagogical_media_scores_v1(scored)
    return scored


def _build_max_six_field_marks() -> list[dict[str, object]]:
    return [
        {
            "feature": f"feature {index}",
            "body_part": "wing",
            "visibility": "medium",
            "importance": "medium",
            "confidence": 0.51,
        }
        for index in range(6)
    ]


def test_valid_clear_bird_profile_passes_validation() -> None:
    payload = _with_scores(_clear_bird_profile_payload())

    validate_pedagogical_media_profile_v1(payload)


def test_valid_partial_occluded_bird_profile_passes_validation() -> None:
    payload = _with_scores(_partial_occluded_bird_profile_payload())

    validate_pedagogical_media_profile_v1(payload)


def test_valid_feather_profile_passes_validation() -> None:
    payload = _with_scores(_feather_profile_payload())

    validate_pedagogical_media_profile_v1(payload)


def test_valid_habitat_profile_passes_validation() -> None:
    payload = _with_scores(_habitat_profile_payload())

    validate_pedagogical_media_profile_v1(payload)


def test_valid_multiple_organisms_profile_passes_validation() -> None:
    payload = _with_scores(_multiple_organisms_profile_payload())

    validate_pedagogical_media_profile_v1(payload)


def test_low_basic_identification_score_does_not_fail_profile() -> None:
    parsed = parse_pedagogical_media_profile_v1(json.dumps(_feather_profile_payload()))

    assert parsed["review_status"] == "valid"
    usage_scores = parsed["scores"]["usage_scores"]
    assert usage_scores["basic_identification"] <= 25


def test_indirect_evidence_learning_can_be_high_while_basic_is_low() -> None:
    parsed = parse_pedagogical_media_profile_v1(json.dumps(_feather_profile_payload()))

    usage_scores = parsed["scores"]["usage_scores"]
    assert usage_scores["basic_identification"] <= 25
    assert usage_scores["indirect_evidence_learning"] >= 60
    assert usage_scores["indirect_evidence_learning"] > usage_scores["basic_identification"]


def test_invalid_json_fails_closed() -> None:
    parsed = parse_pedagogical_media_profile_v1("{not-valid-json")

    assert parsed["review_status"] == "failed"
    assert parsed["failure_reason"] == "model_output_invalid"


def test_parse_invalid_json_returns_schema_valid_failed_payload() -> None:
    parsed = parse_pedagogical_media_profile_v1("{not-valid-json")

    assert parsed["review_status"] == "failed"
    validate_pedagogical_media_profile_v1(parsed)


def test_non_object_json_fails_closed() -> None:
    parsed = parse_pedagogical_media_profile_v1(json.dumps(["not", "an", "object"]))

    assert parsed["review_status"] == "failed"
    assert parsed["failure_reason"] == "model_output_invalid"


def test_missing_required_field_fails_closed() -> None:
    payload = _clear_bird_profile_payload()
    del payload["technical_profile"]

    parsed = parse_pedagogical_media_profile_v1(json.dumps(payload))

    assert parsed["review_status"] == "failed"
    assert parsed["failure_reason"] == "schema_validation_failed"


def test_parse_schema_error_returns_schema_valid_failed_payload() -> None:
    payload = _clear_bird_profile_payload()
    del payload["technical_profile"]

    parsed = parse_pedagogical_media_profile_v1(json.dumps(payload))

    assert parsed["review_status"] == "failed"
    validate_pedagogical_media_profile_v1(parsed)


def test_wrong_enum_value_fails_validation() -> None:
    payload = _with_scores(_clear_bird_profile_payload())
    payload["technical_profile"]["technical_quality"] = "excellent_plus"

    with pytest.raises(ValueError):
        validate_pedagogical_media_profile_v1(payload)


def test_confidence_out_of_range_fails_validation() -> None:
    payload = _with_scores(_clear_bird_profile_payload())
    payload["review_confidence"] = 1.2

    with pytest.raises(ValueError):
        validate_pedagogical_media_profile_v1(payload)


def test_score_out_of_range_fails_validation() -> None:
    payload = _with_scores(_clear_bird_profile_payload())
    payload["scores"]["usage_scores"]["basic_identification"] = 101

    with pytest.raises(ValueError):
        validate_pedagogical_media_profile_v1(payload)


def test_visible_field_marks_max_5_enforced() -> None:
    payload = _with_scores(_clear_bird_profile_payload())
    payload["identification_profile"]["visible_field_marks"] = _build_max_six_field_marks()

    with pytest.raises(ValueError):
        validate_pedagogical_media_profile_v1(payload)


def test_context_visible_max_5_enforced() -> None:
    payload = _with_scores(_clear_bird_profile_payload())
    payload["observation_profile"]["context_visible"] = [
        "water",
        "vegetation",
        "tree",
        "reedbed",
        "ground",
        "sky",
    ]

    with pytest.raises(ValueError):
        validate_pedagogical_media_profile_v1(payload)


def test_limitations_max_5_enforced() -> None:
    payload = _with_scores(_clear_bird_profile_payload())
    payload["limitations"] = [
        "l1",
        "l2",
        "l3",
        "l4",
        "l5",
        "l6",
    ]

    with pytest.raises(ValueError):
        validate_pedagogical_media_profile_v1(payload)


def test_unknown_biological_value_allows_null_visible_basis() -> None:
    payload = _with_scores(_clear_bird_profile_payload())
    payload["biological_profile_visible"]["life_stage"] = {
        "value": "unknown",
        "confidence": "low",
        "visible_basis": None,
    }

    validate_pedagogical_media_profile_v1(payload)


def test_unknown_biological_value_with_medium_confidence_allows_null_visible_basis() -> None:
    payload = _with_scores(_clear_bird_profile_payload())
    payload["biological_profile_visible"]["life_stage"] = {
        "value": "unknown",
        "confidence": "medium",
        "visible_basis": None,
    }

    validate_pedagogical_media_profile_v1(payload)


def test_unknown_biological_value_with_high_confidence_fails() -> None:
    payload = _with_scores(_clear_bird_profile_payload())
    payload["biological_profile_visible"]["life_stage"] = {
        "value": "unknown",
        "confidence": "high",
        "visible_basis": None,
    }

    with pytest.raises(ValueError, match="confidence"):
        validate_pedagogical_media_profile_v1(payload)


def test_unknown_biological_value_with_unknown_confidence_fails() -> None:
    payload = _with_scores(_clear_bird_profile_payload())
    payload["biological_profile_visible"]["life_stage"] = {
        "value": "unknown",
        "confidence": "unknown",
        "visible_basis": None,
    }

    with pytest.raises(ValueError, match="confidence"):
        validate_pedagogical_media_profile_v1(payload)


def test_not_applicable_biological_value_allows_null_visible_basis() -> None:
    payload = _with_scores(_clear_bird_profile_payload())
    payload["biological_profile_visible"]["sex"] = {
        "value": "not_applicable",
        "confidence": "low",
        "visible_basis": None,
    }

    validate_pedagogical_media_profile_v1(payload)


def test_non_unknown_biological_value_without_visible_basis_fails_validation() -> None:
    payload = _with_scores(_clear_bird_profile_payload())
    payload["biological_profile_visible"]["life_stage"] = {
        "value": "adult",
        "confidence": "medium",
        "visible_basis": None,
    }

    with pytest.raises(ValueError, match="visible_basis"):
        validate_pedagogical_media_profile_v1(payload)


def test_bird_group_requires_bird_group_specific_profile() -> None:
    payload = _with_scores(_clear_bird_profile_payload())
    payload["group_specific_profile"] = {}

    with pytest.raises(ValueError, match="group_specific_profile.bird"):
        validate_pedagogical_media_profile_v1(payload)


def test_indirect_evidence_types_require_indirect_subject_presence() -> None:
    payload = _with_scores(_feather_profile_payload())
    payload["observation_profile"]["subject_presence"] = "clear"

    with pytest.raises(ValueError, match="subject_presence"):
        validate_pedagogical_media_profile_v1(payload)


@pytest.mark.parametrize(
    ("feedback_field", "feedback_value"),
    [
        ("post_answer_feedback", {}),
        ("feedback_profile", {}),
        ("feedback_possible", True),
        ("identification_tips", ["tip"]),
    ],
)
def test_feedback_fields_are_rejected(
    feedback_field: str,
    feedback_value: object,
) -> None:
    payload = _with_scores(_clear_bird_profile_payload())
    payload[feedback_field] = feedback_value

    errors = collect_schema_validation_errors_pmp_v1(payload)

    assert errors
    assert any(error.get("cause") == "additional_property" for error in errors)


@pytest.mark.parametrize(
    ("selection_field", "selection_value"),
    [
        ("selected_for_quiz", True),
        ("palier_1_core_eligible", False),
        ("recommended_use", "field_training"),
        ("runtime_ready", True),
        ("playable", True),
    ],
)
def test_final_selection_fields_are_rejected(
    selection_field: str,
    selection_value: object,
) -> None:
    payload = _with_scores(_clear_bird_profile_payload())
    payload[selection_field] = selection_value

    errors = collect_schema_validation_errors_pmp_v1(payload)

    assert errors
    assert any(error.get("cause") == "additional_property" for error in errors)


def test_failed_payload_with_diagnostics_validates() -> None:
    payload = _failed_payload()

    validate_pedagogical_media_profile_v1(payload)


def test_deterministic_scoring_returns_all_required_scores() -> None:
    payload = _clear_bird_profile_payload()

    score_a = compute_pedagogical_media_scores_v1(payload)
    score_b = compute_pedagogical_media_scores_v1(payload)

    assert score_a == score_b
    assert 0 <= score_a["global_quality_score"] <= 100
    assert set(score_a["usage_scores"]) == {
        "basic_identification",
        "field_observation",
        "confusion_learning",
        "morphology_learning",
        "species_card",
        "indirect_evidence_learning",
    }


def test_failed_payload_score_computation_returns_zero_scores() -> None:
    payload = _failed_payload()

    scores = compute_pedagogical_media_scores_v1(payload)

    assert scores["global_quality_score"] == 0
    assert scores["usage_scores"] == {
        "basic_identification": 0,
        "field_observation": 0,
        "confusion_learning": 0,
        "morphology_learning": 0,
        "species_card": 0,
        "indirect_evidence_learning": 0,
    }
