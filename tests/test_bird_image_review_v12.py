from __future__ import annotations

import json

import pytest

from database_core.qualification.bird_image_review_v12 import (
    build_failed_bird_image_review_v12,
    compute_bird_image_pedagogical_score_v12,
    is_playable_bird_image_review_v12,
    parse_bird_image_pedagogical_review_v12,
    validate_bird_image_pedagogical_review_v12,
)


def _success_payload() -> dict[str, object]:
    return {
        "schema_version": "bird_image_pedagogical_review.v1.2",
        "prompt_version": "bird_image_review_prompt.v1.2",
        "status": "success",
        "failure_reason": None,
        "consistency_warning": None,
        "image_assessment": {
            "technical_quality": "high",
            "subject_visibility": "high",
            "sharpness": "high",
            "lighting": "medium",
            "background_clutter": "low",
            "occlusion": "none",
            "view_angle": "lateral",
            "visible_parts": ["head", "beak", "breast", "wing"],
            "confidence": 0.9,
        },
        "pedagogical_assessment": {
            "pedagogical_quality": "high",
            "difficulty_level": "easy",
            "media_role": "primary_identification",
            "diagnostic_feature_visibility": "high",
            "representativeness": "high",
            "learning_suitability": "high",
            "confusion_relevance": "medium",
            "confidence": 0.86,
        },
        "identification_features_visible_in_this_image": [
            {
                "feature": "orange breast",
                "body_part": "breast",
                "visibility": "high",
                "importance_for_identification": "high",
                "explanation": "The breast pattern is clearly visible in this image.",
            }
        ],
        "post_answer_feedback": {
            "correct": {
                "short": (
                    "Oui, sur cette image les meilleurs indices sont la poitrine "
                    "et la silhouette."
                ),
                "long": (
                    "Sur cette image, la poitrine et la silhouette compacte "
                    "confirment l'identification."
                ),
            },
            "incorrect": {
                "short": "Pas tout a fait, commence par la poitrine puis la silhouette.",
                "long": "Sur cette image, verifie d'abord la poitrine puis la silhouette globale.",
            },
            "identification_tips": [
                "Regarder d'abord la poitrine.",
                "Verifier la silhouette compacte.",
                "Confirmer avec la forme du bec.",
            ],
            "confidence": 0.84,
        },
        "limitations": {
            "why_not_ideal": [],
            "uncertainty_reason": None,
            "requires_human_review": False,
        },
        "overall_confidence": 0.88,
    }


def test_valid_success_output_passes_validation_and_is_playable() -> None:
    payload = _success_payload()

    validate_bird_image_pedagogical_review_v12(payload)

    parsed = parse_bird_image_pedagogical_review_v12(json.dumps(payload))
    assert parsed["status"] == "success"
    assert is_playable_bird_image_review_v12(parsed)

    score = compute_bird_image_pedagogical_score_v12(parsed)
    assert score["overall"] >= 80
    assert score["subscores"]["technical_quality"] == 20


def test_valid_failed_output_passes_validation() -> None:
    payload = build_failed_bird_image_review_v12(failure_reason="image_too_blurry")

    validate_bird_image_pedagogical_review_v12(payload)

    parsed = parse_bird_image_pedagogical_review_v12(json.dumps(payload))
    assert parsed["status"] == "failed"
    assert parsed["failure_reason"] == "image_too_blurry"


def test_invalid_json_fails_closed() -> None:
    parsed = parse_bird_image_pedagogical_review_v12("{not-valid-json")

    assert parsed["status"] == "failed"
    assert parsed["failure_reason"] == "model_output_invalid"


def test_missing_required_fields_fails_closed() -> None:
    payload = _success_payload()
    del payload["image_assessment"]

    parsed = parse_bird_image_pedagogical_review_v12(json.dumps(payload))

    assert parsed["status"] == "failed"
    assert parsed["failure_reason"] == "schema_validation_failed"


def test_wrong_enum_values_are_rejected_by_schema() -> None:
    payload = _success_payload()
    payload["image_assessment"]["technical_quality"] = "excellent_plus"

    with pytest.raises(ValueError):
        validate_bird_image_pedagogical_review_v12(payload)


def test_out_of_range_confidence_is_rejected_by_schema() -> None:
    payload = _success_payload()
    payload["overall_confidence"] = 1.2

    with pytest.raises(ValueError):
        validate_bird_image_pedagogical_review_v12(payload)


def test_missing_feedback_fails_closed_for_playable_use() -> None:
    payload = _success_payload()
    payload["post_answer_feedback"]["identification_tips"] = ["Only one tip"]

    parsed = parse_bird_image_pedagogical_review_v12(json.dumps(payload))

    assert parsed["status"] == "failed"
    assert parsed["failure_reason"] == "schema_validation_failed"


def test_failed_review_cannot_be_playable_or_mature() -> None:
    payload = build_failed_bird_image_review_v12(failure_reason="non_bird_subject")
    parsed = parse_bird_image_pedagogical_review_v12(json.dumps(payload))

    assert not is_playable_bird_image_review_v12(parsed)
    score = compute_bird_image_pedagogical_score_v12(parsed)
    assert score["overall"] == 0
