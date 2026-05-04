"""Sprint 5 tests: opt-in PMP v1 pipeline integration.

Phases covered:
  1 – neck body_part enum
  2 – selector / resolver
  3 – AIQualificationOutcome PMP fields serialization
  4 – Gemini PMP path (mocked)
  5 – pipeline routing (cached mode)
"""

from __future__ import annotations

import json
import urllib.request
from unittest.mock import MagicMock

import pytest

from database_core.domain.enums import MediaType, SourceName
from database_core.domain.models import AIQualification, MediaAsset
from database_core.qualification.ai import (
    AI_REVIEW_CONTRACT_PMP_V1,
    AI_REVIEW_CONTRACT_V1_1,
    AI_REVIEW_CONTRACT_V1_2,
    SUPPORTED_AI_REVIEW_CONTRACT_VERSIONS,
    AIQualificationOutcome,
    BirdImageReviewInput,
    GeminiVisionQualifier,
    collect_ai_qualification_outcomes,
    resolve_ai_review_contract_version,
    source_external_key_for_media,
)
from database_core.qualification.bird_image_review_v12 import BIRD_IMAGE_REVIEW_PROMPT_VERSION
from database_core.qualification.pedagogical_media_profile_prompt_v1 import (
    PEDAGOGICAL_MEDIA_PROFILE_PROMPT_VERSION,
)

# ---------------------------------------------------------------------------
# Phase 1 – neck body_part enum
# ---------------------------------------------------------------------------


def test_neck_in_pmp_prompt_guidance() -> None:
    from database_core.qualification.pedagogical_media_profile_prompt_v1 import (
        build_pedagogical_media_profile_prompt_v1,
    )

    prompt = build_pedagogical_media_profile_prompt_v1(
        expected_scientific_name="Ardea cinerea",
        common_names={},
        organism_group="bird",
        media_reference="https://example.com/image.jpg",
    )
    assert "neck" in prompt


def test_neck_is_accepted_by_pmp_body_part_normalizer() -> None:
    """neck must not be stripped by the field_mark body_part normalizer."""
    from database_core.qualification.pedagogical_media_profile_v1 import (
        normalize_pedagogical_media_profile_v1,
    )

    raw = {
        "review_status": "valid",
        "identification_profile": {
            "visible_field_marks": [
                {
                    "feature": "grey neck patch",
                    "body_part": "neck",
                    "visibility": "clear",
                    "importance": "primary",
                    "confidence": "high",
                }
            ]
        },
    }
    normalized = normalize_pedagogical_media_profile_v1(raw)
    marks = normalized.get("identification_profile", {}).get("visible_field_marks", [])
    assert len(marks) == 1, "neck mark should be preserved after normalization"
    assert marks[0]["body_part"] == "neck"


# ---------------------------------------------------------------------------
# Phase 2 – selector / resolver
# ---------------------------------------------------------------------------


def test_pmp_v1_selector_resolves() -> None:
    result = resolve_ai_review_contract_version("pedagogical_media_profile_v1")
    assert result == AI_REVIEW_CONTRACT_PMP_V1


def test_pmp_v1_alias_pmp_v1_resolves() -> None:
    assert resolve_ai_review_contract_version("pmp_v1") == AI_REVIEW_CONTRACT_PMP_V1


def test_default_remains_v1_1_after_pmp_addition() -> None:
    assert resolve_ai_review_contract_version(None) == AI_REVIEW_CONTRACT_V1_1


def test_v1_1_still_resolves() -> None:
    assert resolve_ai_review_contract_version("v1_1") == AI_REVIEW_CONTRACT_V1_1


def test_v1_2_still_resolves() -> None:
    assert resolve_ai_review_contract_version("v1_2") == AI_REVIEW_CONTRACT_V1_2


def test_unsupported_selector_raises() -> None:
    with pytest.raises(ValueError, match="(?i)unsupported"):
        resolve_ai_review_contract_version("completely_unknown_version")


def test_pmp_v1_in_supported_versions() -> None:
    assert AI_REVIEW_CONTRACT_PMP_V1 in SUPPORTED_AI_REVIEW_CONTRACT_VERSIONS


# ---------------------------------------------------------------------------
# Phase 3 – AIQualificationOutcome PMP field serialization round-trip
# ---------------------------------------------------------------------------

_VALID_PMP = {"review_status": "valid", "scores": {"global_quality_score": 82}}
_VALID_SCORE = {"global_quality_score": 82}


def test_pmp_outcome_to_snapshot_payload_includes_pmp_fields() -> None:
    outcome = AIQualificationOutcome(
        status="ok",
        review_contract_version=AI_REVIEW_CONTRACT_PMP_V1,
        prompt_version=PEDAGOGICAL_MEDIA_PROFILE_PROMPT_VERSION,
        pedagogical_media_profile=_VALID_PMP,
        pedagogical_media_profile_score=_VALID_SCORE,
    )
    payload = outcome.to_snapshot_payload()
    assert payload["pedagogical_media_profile"] == _VALID_PMP
    assert payload["pedagogical_media_profile_score"] == _VALID_SCORE


def test_pmp_outcome_from_snapshot_payload_restores_pmp_fields() -> None:
    outcome = AIQualificationOutcome(
        status="ok",
        review_contract_version=AI_REVIEW_CONTRACT_PMP_V1,
        prompt_version=PEDAGOGICAL_MEDIA_PROFILE_PROMPT_VERSION,
        pedagogical_media_profile=_VALID_PMP,
        pedagogical_media_profile_score=_VALID_SCORE,
    )
    restored = AIQualificationOutcome.from_snapshot_payload(outcome.to_snapshot_payload())
    assert restored.pedagogical_media_profile == _VALID_PMP
    assert restored.pedagogical_media_profile_score == _VALID_SCORE


def test_old_payload_without_pmp_fields_loads_with_none() -> None:
    old_payload = {
        "status": "ok",
        "prompt_version": BIRD_IMAGE_REVIEW_PROMPT_VERSION,
        "review_contract_version": AI_REVIEW_CONTRACT_V1_2,
    }
    restored = AIQualificationOutcome.from_snapshot_payload(old_payload)
    assert restored.pedagogical_media_profile is None
    assert restored.pedagogical_media_profile_score is None


def test_failed_pmp_payload_round_trips() -> None:
    failed_pmp = {"review_status": "failed", "failure_reason": "low_confidence"}
    outcome = AIQualificationOutcome(
        status="pedagogical_media_profile_failed",
        flags=("pedagogical_media_profile_failed",),
        review_contract_version=AI_REVIEW_CONTRACT_PMP_V1,
        prompt_version=PEDAGOGICAL_MEDIA_PROFILE_PROMPT_VERSION,
        pedagogical_media_profile=failed_pmp,
        pedagogical_media_profile_score=None,
    )
    restored = AIQualificationOutcome.from_snapshot_payload(outcome.to_snapshot_payload())
    assert restored.status == "pedagogical_media_profile_failed"
    assert restored.pedagogical_media_profile == failed_pmp
    assert restored.pedagogical_media_profile_score is None


def test_v1_2_bird_image_fields_not_broken_by_pmp_addition() -> None:
    review = {"status": "success", "confidence": 5}
    score = {"global_quality_score": 70}
    outcome = AIQualificationOutcome(
        status="ok",
        review_contract_version=AI_REVIEW_CONTRACT_V1_2,
        prompt_version=BIRD_IMAGE_REVIEW_PROMPT_VERSION,
        bird_image_pedagogical_review=review,
        bird_image_pedagogical_score=score,
        pedagogical_media_profile=None,
        pedagogical_media_profile_score=None,
    )
    restored = AIQualificationOutcome.from_snapshot_payload(outcome.to_snapshot_payload())
    assert restored.bird_image_pedagogical_review == review
    assert restored.bird_image_pedagogical_score == score
    assert restored.pedagogical_media_profile is None


# ---------------------------------------------------------------------------
# Phase 4 – Gemini PMP path (mocked)
# ---------------------------------------------------------------------------

_FIXTURE_MEDIA_ASSET = MediaAsset(
    media_id="media:test:pmp-1",
    source_name=SourceName.INATURALIST,
    source_media_id="pmp-1",
    media_type=MediaType.IMAGE,
    source_url="https://example.com/image.jpg",
    attribution="fixture",
    license="CC-BY",
    mime_type="image/jpeg",
    file_extension="jpg",
    width=800,
    height=600,
    source_observation_uid="obs:test:1",
    canonical_taxon_id="taxon:birds:000001",
    raw_payload_ref="fixture.json#/pmp-1",
)

_VALID_GEMINI_PMP_RESPONSE = {
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
        "context_visible": [],
    },
    "biological_profile_visible": {
        "sex": {"value": "unknown", "confidence": "low", "visible_basis": None},
        "life_stage": {"value": "adult", "confidence": "medium", "visible_basis": "plumage"},
        "plumage_state": {"value": "unknown", "confidence": "low", "visible_basis": None},
        "seasonal_state": {"value": "unknown", "confidence": "low", "visible_basis": None},
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
                "confidence": 0.9,
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


def _make_gemini_http_response(body: dict) -> MagicMock:
    raw_bytes = json.dumps(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": json.dumps(body)}],
                        "role": "model",
                    }
                }
            ]
        }
    ).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = raw_bytes
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def test_gemini_pmp_valid_output_returns_ok_outcome(monkeypatch) -> None:
    mock_resp = _make_gemini_http_response(_VALID_GEMINI_PMP_RESPONSE)
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: mock_resp)

    qualifier = GeminiVisionQualifier(
        api_key="test-key",
        model_name="gemini-test",
        review_contract_version=AI_REVIEW_CONTRACT_PMP_V1,
    )
    result = qualifier.qualify(
        _FIXTURE_MEDIA_ASSET,
        image_bytes=b"\xff\xd8\xff\xe0" + b"\x00" * 16,
        bird_image_review_input=BirdImageReviewInput(
            scientific_name="Ardea cinerea",
            common_names={},
            image_url="https://example.com/image.jpg",
        ),
    )
    assert result is not None
    assert result.status == "ok"
    assert result.review_contract_version == AI_REVIEW_CONTRACT_PMP_V1
    assert result.prompt_version == PEDAGOGICAL_MEDIA_PROFILE_PROMPT_VERSION
    assert result.pedagogical_media_profile is not None
    assert result.pedagogical_media_profile_score is not None


def test_gemini_pmp_failed_output_returns_failed_outcome(monkeypatch) -> None:
    failed_response = dict(_VALID_GEMINI_PMP_RESPONSE)
    failed_response["review_status"] = "failed"
    failed_response["failure_reason"] = "not_a_bird"
    failed_response["scores"] = None

    mock_resp = _make_gemini_http_response(failed_response)
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: mock_resp)

    qualifier = GeminiVisionQualifier(
        api_key="test-key",
        model_name="gemini-test",
        review_contract_version=AI_REVIEW_CONTRACT_PMP_V1,
    )
    result = qualifier.qualify(
        _FIXTURE_MEDIA_ASSET,
        image_bytes=b"\xff\xd8\xff\xe0" + b"\x00" * 16,
    )
    assert result is not None
    assert result.status == "pedagogical_media_profile_failed"
    assert "pedagogical_media_profile_failed" in result.flags


def test_gemini_pmp_outcome_has_no_bird_image_review_pollution(monkeypatch) -> None:
    mock_resp = _make_gemini_http_response(_VALID_GEMINI_PMP_RESPONSE)
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: mock_resp)

    qualifier = GeminiVisionQualifier(
        api_key="test-key",
        model_name="gemini-test",
        review_contract_version=AI_REVIEW_CONTRACT_PMP_V1,
    )
    result = qualifier.qualify(
        _FIXTURE_MEDIA_ASSET,
        image_bytes=b"\xff\xd8\xff\xe0" + b"\x00" * 16,
    )
    assert result is not None
    assert result.bird_image_pedagogical_review is None
    assert result.bird_image_pedagogical_score is None


# ---------------------------------------------------------------------------
# Phase 5 – pipeline routing (cached mode)
# ---------------------------------------------------------------------------


def test_cached_pmp_outcome_passes_through_pipeline() -> None:
    media_asset = _FIXTURE_MEDIA_ASSET
    media_key = source_external_key_for_media(media_asset)

    cached = AIQualificationOutcome(
        status="ok",
        prompt_version=PEDAGOGICAL_MEDIA_PROFILE_PROMPT_VERSION,
        review_contract_version=AI_REVIEW_CONTRACT_PMP_V1,
        pedagogical_media_profile=_VALID_PMP,
        pedagogical_media_profile_score=_VALID_SCORE,
    )

    outcomes = collect_ai_qualification_outcomes(
        [media_asset],
        qualifier_mode="cached",
        precomputed_ai_outcomes={media_key: cached},
        review_contract_version=AI_REVIEW_CONTRACT_PMP_V1,
    )

    assert outcomes[media_key].status == "ok"
    assert outcomes[media_key].review_contract_version == AI_REVIEW_CONTRACT_PMP_V1
    assert outcomes[media_key].pedagogical_media_profile == _VALID_PMP


def test_v1_1_default_unaffected_by_pmp_addition() -> None:
    """Adding PMP v1 must not break existing v1_1 cached outcomes."""
    from database_core.qualification.ai import default_prompt_version_for_review_contract

    media_asset = _FIXTURE_MEDIA_ASSET
    media_key = source_external_key_for_media(media_asset)

    v11_prompt = default_prompt_version_for_review_contract(AI_REVIEW_CONTRACT_V1_1)
    v11_outcome = AIQualificationOutcome(
        status="ok",
        prompt_version=v11_prompt,
        review_contract_version=AI_REVIEW_CONTRACT_V1_1,
        qualification=AIQualification(
            technical_quality="high",
            pedagogical_quality="high",
            life_stage="adult",
            sex="unknown",
            visible_parts=["head"],
            view_angle="lateral",
            confidence=0.9,
            model_name="gemini-test",
            notes=None,
        ),
    )

    outcomes = collect_ai_qualification_outcomes(
        [media_asset],
        qualifier_mode="cached",
        precomputed_ai_outcomes={media_key: v11_outcome},
        review_contract_version=AI_REVIEW_CONTRACT_V1_1,
    )

    assert outcomes[media_key].status == "ok"
    assert outcomes[media_key].review_contract_version == AI_REVIEW_CONTRACT_V1_1
    assert outcomes[media_key].pedagogical_media_profile is None
