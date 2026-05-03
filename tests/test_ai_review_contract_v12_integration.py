from __future__ import annotations

import json
import urllib.request
from datetime import datetime
from pathlib import Path

from database_core.domain.enums import (
    MediaType,
    PedagogicalProfileStatus,
    QualificationStatus,
    SourceName,
)
from database_core.domain.models import (
    AIQualification,
    LocationMetadata,
    MediaAsset,
    SourceObservation,
    SourceQualityMetadata,
)
from database_core.qualification.ai import (
    AI_REVIEW_CONTRACT_V1_2,
    AIQualificationOutcome,
    BirdImageReviewInput,
    GeminiVisionQualifier,
    collect_ai_qualification_outcomes,
    source_external_key_for_media,
)
from database_core.qualification.bird_image_review_v12 import BIRD_IMAGE_REVIEW_PROMPT_VERSION
from database_core.qualification.pedagogical_image_profile import build_pedagogical_image_profile
from database_core.qualification.rules import qualify_media_assets

_FIXTURE_IMAGE = Path("tests/fixtures/inaturalist_snapshot_smoke/images/810001.jpg")


def _media_asset() -> MediaAsset:
    return MediaAsset(
        media_id="media:inaturalist:810001",
        source_name=SourceName.INATURALIST,
        source_media_id="810001",
        media_type=MediaType.IMAGE,
        source_url="https://example.org/810001.jpg",
        attribution="(c) observer",
        author="observer",
        license="CC-BY",
        mime_type="image/jpeg",
        file_extension="jpg",
        width=1600,
        height=1200,
        source_observation_uid="obs:inaturalist:910001",
        canonical_taxon_id="taxon:birds:000014",
        raw_payload_ref="responses/taxon_birds_000014.json#/results/0",
    )


def _observation() -> SourceObservation:
    return SourceObservation(
        observation_uid="obs:inaturalist:910001",
        source_name=SourceName.INATURALIST,
        source_observation_id="910001",
        source_taxon_id="12716",
        observed_at=datetime.fromisoformat("2025-04-18T07:31:00+00:00"),
        location=LocationMetadata(place_name="Brussels, BE", country_code="BE"),
        source_quality=SourceQualityMetadata(
            quality_grade="research",
            research_grade=True,
            observation_license="CC-BY",
            captive=False,
        ),
        raw_payload_ref="responses/taxon_birds_000014.json#/results/0",
        canonical_taxon_id="taxon:birds:000014",
    )


def _v12_success_review_payload() -> dict[str, object]:
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
            "visible_parts": ["head", "beak", "breast", "tail"],
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
            "confidence": 0.85,
        },
        "identification_features_visible_in_this_image": [
            {
                "feature": "beak shape",
                "body_part": "beak",
                "visibility": "high",
                "importance_for_identification": "high",
                "explanation": "Sur cette image, le bec est net et distinctif.",
            }
        ],
        "post_answer_feedback": {
            "correct": {
                "short": "Oui. Sur cette image, le bec et la poitrine sont tres nets.",
                "long": (
                    "Sur cette image, observe d'abord le bec puis la poitrine; "
                    "ici la silhouette et la queue confirment l'espece."
                ),
            },
            "incorrect": {
                "short": "Pas encore. Sur cette image, commence par le bec et la poitrine.",
                "long": "Ici, verifie le bec, la poitrine et la queue avant de valider.",
            },
            "identification_tips": [
                "Sur cette image, repere le bec puis la poitrine.",
                "Ici, compare la silhouette et la queue.",
                "Regarde aussi l'oeil pour confirmer.",
            ],
            "confidence": 0.82,
        },
        "limitations": {
            "why_not_ideal": [],
            "uncertainty_reason": None,
            "requires_human_review": False,
        },
        "overall_confidence": 0.87,
    }


class _FakeGeminiResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def _build_gemini_transport_payload(review_text: str) -> dict[str, object]:
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "text": review_text,
                        }
                    ]
                }
            }
        ]
    }


def test_v11_default_path_is_preserved_for_cached_outputs() -> None:
    media_asset = _media_asset()
    media_key = source_external_key_for_media(media_asset)

    outcomes = collect_ai_qualification_outcomes(
        [media_asset],
        qualifier_mode="cached",
        precomputed_ai_outcomes={
            media_key: AIQualificationOutcome(
                status="ok",
                prompt_version="phase1.inat.image.v2",
                qualification=AIQualification(
                    technical_quality="high",
                    pedagogical_quality="high",
                    life_stage="adult",
                    sex="unknown",
                    visible_parts=["head", "beak", "breast"],
                    view_angle="lateral",
                    confidence=0.9,
                    model_name="gemini-test",
                    notes="legacy path",
                ),
            )
        },
    )

    assert outcomes[media_key].status == "ok"
    assert outcomes[media_key].prompt_version == "phase1.inat.image.v2"


def test_v12_gemini_path_reaches_profile_with_post_answer_feedback(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout=30):
        del timeout
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeGeminiResponse(
            _build_gemini_transport_payload(json.dumps(_v12_success_review_payload()))
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    media_asset = _media_asset()
    media_key = source_external_key_for_media(media_asset)
    qualifier = GeminiVisionQualifier(
        api_key="test-key",
        review_contract_version=AI_REVIEW_CONTRACT_V1_2,
    )

    outcomes = collect_ai_qualification_outcomes(
        [media_asset],
        qualifier_mode="gemini",
        cached_image_paths_by_source_media_key={media_key: _FIXTURE_IMAGE},
        bird_image_review_inputs_by_source_media_key={
            media_key: BirdImageReviewInput(
                scientific_name="Turdus merula",
                common_names={"fr": "Merle noir", "en": "Common blackbird"},
                image_url=media_asset.source_url,
            )
        },
        qualifier=qualifier,
        review_contract_version=AI_REVIEW_CONTRACT_V1_2,
    )

    prompt_text = captured["payload"]["contents"][0]["parts"][0]["text"]
    assert "bird_image_pedagogical_review.v1.2" in prompt_text
    generation_config = captured["payload"]["generationConfig"]
    assert generation_config["responseMimeType"] == "application/json"
    assert generation_config["responseJsonSchema"]["type"] == "object"
    assert generation_config["responseJsonSchema"]["oneOf"]

    outcome = outcomes[media_key]
    assert outcome.status == "ok"
    assert outcome.prompt_version == BIRD_IMAGE_REVIEW_PROMPT_VERSION
    assert outcome.review_contract_version == AI_REVIEW_CONTRACT_V1_2
    assert outcome.bird_image_pedagogical_review is not None
    assert outcome.bird_image_pedagogical_review["status"] == "success"

    resources, _ = qualify_media_assets(
        observations=[_observation()],
        media_assets=[media_asset],
        ai_qualifications_by_source_media_key={media_key: outcome},
        created_at=datetime.fromisoformat("2026-05-02T00:00:00+00:00"),
        run_id="run:20260502T000000Z:aaaaaaaa",
        uncertain_policy="reject",
        qualification_policy="v1.1",
    )
    assert resources[0].qualification_status == QualificationStatus.ACCEPTED

    profile = build_pedagogical_image_profile(
        resources[0],
        ai_outcome=outcome,
        media_asset=media_asset,
    )
    assert profile.profile_status in {
        PedagogicalProfileStatus.PROFILED,
        PedagogicalProfileStatus.PROFILED_WITH_WARNINGS,
        PedagogicalProfileStatus.MANUAL_REVIEW_REQUIRED,
    }
    assert profile.feedback.post_answer_feedback is not None
    assert (
        profile.feedback.post_answer_feedback.correct.short
        == "Oui. Sur cette image, le bec et la poitrine sont tres nets."
    )


def test_v12_invalid_output_fails_closed_and_blocks_playable_profile(monkeypatch) -> None:
    def fake_urlopen(request, timeout=30):
        del request, timeout
        return _FakeGeminiResponse(_build_gemini_transport_payload('{"status": "success"}'))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    media_asset = _media_asset()
    media_key = source_external_key_for_media(media_asset)
    qualifier = GeminiVisionQualifier(
        api_key="test-key",
        review_contract_version=AI_REVIEW_CONTRACT_V1_2,
    )

    outcomes = collect_ai_qualification_outcomes(
        [media_asset],
        qualifier_mode="gemini",
        cached_image_paths_by_source_media_key={media_key: _FIXTURE_IMAGE},
        bird_image_review_inputs_by_source_media_key={
            media_key: BirdImageReviewInput(
                scientific_name="Turdus merula",
                common_names={"fr": "Merle noir"},
                image_url=media_asset.source_url,
            )
        },
        qualifier=qualifier,
        review_contract_version=AI_REVIEW_CONTRACT_V1_2,
    )

    outcome = outcomes[media_key]
    assert outcome.status == "bird_image_review_failed"
    assert outcome.bird_image_pedagogical_review is not None
    assert outcome.bird_image_pedagogical_review["failure_reason"] == "schema_validation_failed"

    resources, _ = qualify_media_assets(
        observations=[_observation()],
        media_assets=[media_asset],
        ai_qualifications_by_source_media_key={media_key: outcome},
        created_at=datetime.fromisoformat("2026-05-02T00:00:00+00:00"),
        run_id="run:20260502T000000Z:bbbbbbbb",
        uncertain_policy="reject",
        qualification_policy="v1.1",
    )
    assert resources[0].qualification_status == QualificationStatus.REJECTED

    profile = build_pedagogical_image_profile(
        resources[0],
        ai_outcome=outcome,
        media_asset=media_asset,
    )
    assert profile.profile_status in {
        PedagogicalProfileStatus.PENDING_AI,
        PedagogicalProfileStatus.REJECTED_FOR_PLAYABLE_USE,
    }
    assert profile.recommended_usages == []


def test_v12_non_json_output_fails_closed_with_model_output_invalid(monkeypatch) -> None:
    def fake_urlopen(request, timeout=30):
        del request, timeout
        return _FakeGeminiResponse(_build_gemini_transport_payload("{not-valid-json"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    media_asset = _media_asset()
    media_key = source_external_key_for_media(media_asset)
    qualifier = GeminiVisionQualifier(
        api_key="test-key",
        review_contract_version=AI_REVIEW_CONTRACT_V1_2,
    )

    outcomes = collect_ai_qualification_outcomes(
        [media_asset],
        qualifier_mode="gemini",
        cached_image_paths_by_source_media_key={media_key: _FIXTURE_IMAGE},
        bird_image_review_inputs_by_source_media_key={
            media_key: BirdImageReviewInput(
                scientific_name="Turdus merula",
                common_names={"fr": "Merle noir"},
                image_url=media_asset.source_url,
            )
        },
        qualifier=qualifier,
        review_contract_version=AI_REVIEW_CONTRACT_V1_2,
    )

    outcome = outcomes[media_key]
    assert outcome.status == "bird_image_review_failed"
    assert outcome.bird_image_pedagogical_review is not None
    assert outcome.bird_image_pedagogical_review["failure_reason"] == "model_output_invalid"
