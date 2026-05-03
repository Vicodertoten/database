import io
import json
import urllib.request
from datetime import UTC, datetime
from urllib.error import HTTPError

from database_core.domain.enums import MediaType, SourceName
from database_core.domain.models import AIQualification, MediaAsset
from database_core.qualification.ai import (
    AI_REVIEW_CONTRACT_V1_2,
    AI_REVIEW_CONTRACT_VERSION_ENV,
    AIQualificationOutcome,
    GeminiVisionQualifier,
    _normalize_gemini_candidate,
    build_prompt_bundle,
    collect_ai_qualification_outcomes,
    resolve_ai_review_contract_version,
    source_external_key_for_media,
)
from database_core.qualification.bird_image_review_v12 import BIRD_IMAGE_REVIEW_PROMPT_VERSION


def test_normalize_gemini_candidate_recovers_common_schema_drift() -> None:
    normalized = _normalize_gemini_candidate(
        {
            "technical_quality": (
                "Good. The bird is in focus and the head, beak, and eye are sharp."
            ),
            "pedagogical_quality": "Excellent. The image clearly shows the key field marks.",
            "life_stage": "Adult",
            "sex": "Male",
            "visible_parts": "Full body (profile), head, beak, eye",
            "view_angle": "Profile, slightly from below",
            "confidence": 5,
            "notes": "Real Gemini output normalized for test coverage.",
        }
    )

    qualification = AIQualification(**normalized)

    assert qualification.technical_quality == "medium"
    assert qualification.pedagogical_quality == "high"
    assert qualification.sex == "male"
    assert qualification.view_angle == "lateral"
    assert qualification.confidence == 1.0
    assert "full_body" in qualification.visible_parts
    assert "head" in qualification.visible_parts
    assert qualification.difficulty_level == "unknown"
    assert qualification.media_role == "context"
    assert qualification.confusion_relevance == "none"
    assert qualification.diagnostic_feature_visibility == "unknown"
    assert qualification.learning_suitability == "unknown"
    assert qualification.uncertainty_reason == "none"


def test_gemini_vision_qualifier_uses_structured_output_and_high_media_resolution(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": json.dumps(
                                            {
                                                "technical_quality": "high",
                                                "pedagogical_quality": "medium",
                                                "life_stage": "adult",
                                                "sex": "unknown",
                                                "visible_parts": ["full_body", "head", "beak"],
                                                "view_angle": "lateral",
                                                "confidence": 0.92,
                                                "notes": "Structured response.",
                                            }
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                }
            ).encode("utf-8")

    def fake_urlopen(request, timeout=30):
        del timeout
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    qualifier = GeminiVisionQualifier(api_key="test-key")
    qualification = qualifier.qualify(
        MediaAsset(
            media_id="media:fixture:1",
            source_name=SourceName.INATURALIST,
            source_media_id="fixture-1",
            media_type=MediaType.IMAGE,
            source_url="fixture://media/1",
            attribution="fixture",
            author="observer",
            license="CC-BY",
            mime_type="image/jpeg",
            file_extension="jpg",
            width=1600,
            height=1200,
            source_observation_uid="obs:fixture:1",
            canonical_taxon_id="taxon:birds:000014",
            raw_payload_ref="fixture.json#/media/1",
        ),
        image_bytes=io.BytesIO(b"fake-image").getvalue(),
    )

    generation_config = captured["payload"]["generationConfig"]
    assert generation_config["responseMimeType"] == "application/json"
    assert generation_config["mediaResolution"] == "MEDIA_RESOLUTION_HIGH"
    assert generation_config["responseJsonSchema"]["type"] == "object"
    assert "technical_quality" in generation_config["responseJsonSchema"]["required"]
    assert "The subject is a bird" in captured["payload"]["contents"][0]["parts"][0]["text"]
    assert captured["headers"]["X-goog-api-key"] == "test-key"
    assert qualification.model_name == "gemini-3.1-flash-lite-preview"


def test_gemini_vision_qualifier_surfaces_http_error_details(monkeypatch) -> None:
    error_body = json.dumps(
        {
            "error": {
                "code": 400,
                "message": "API key not valid. Please pass a valid API key.",
                "status": "INVALID_ARGUMENT",
            }
        }
    ).encode("utf-8")

    def fake_urlopen(request, timeout=30):
        del request, timeout
        raise HTTPError(
            url="https://generativelanguage.googleapis.com",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=io.BytesIO(error_body),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    qualifier = GeminiVisionQualifier(api_key="test-key")

    try:
        qualifier.qualify(
            MediaAsset(
                media_id="media:fixture:1",
                source_name=SourceName.INATURALIST,
                source_media_id="fixture-1",
                media_type=MediaType.IMAGE,
                source_url="fixture://media/1",
                attribution="fixture",
                author="observer",
                license="CC-BY",
                mime_type="image/jpeg",
                file_extension="jpg",
                width=1600,
                height=1200,
                source_observation_uid="obs:fixture:1",
                canonical_taxon_id="taxon:birds:000014",
                raw_payload_ref="fixture.json#/media/1",
            ),
            image_bytes=io.BytesIO(b"fake-image").getvalue(),
        )
    except RuntimeError as exc:
        assert str(exc) == (
            "Gemini API request failed with HTTP 400: "
            "API key not valid. Please pass a valid API key."
        )
    else:
        raise AssertionError("Expected RuntimeError")


def test_cached_ai_outputs_require_matching_prompt_version() -> None:
    media_asset = MediaAsset(
        media_id="media:fixture:cached-1",
        source_name=SourceName.INATURALIST,
        source_media_id="cached-1",
        media_type=MediaType.IMAGE,
        source_url="fixture://media/cached-1",
        attribution="fixture",
        license="CC-BY",
        mime_type="image/jpeg",
        file_extension="jpg",
        width=1600,
        height=1200,
        source_observation_uid="obs:fixture:1",
        canonical_taxon_id="taxon:birds:000014",
        raw_payload_ref="fixture.json#/media/cached-1",
    )

    outcomes = collect_ai_qualification_outcomes(
        [media_asset],
        qualifier_mode="cached",
        precomputed_ai_outcomes={
            source_external_key_for_media(media_asset): AIQualificationOutcome(
                status="ok",
                prompt_version="legacy.prompt.v1",
                qualified_at=datetime.now(UTC),
                qualification=AIQualification(
                    technical_quality="high",
                    pedagogical_quality="high",
                    life_stage="adult",
                    sex="unknown",
                    visible_parts=["full_body"],
                    view_angle="lateral",
                    confidence=0.91,
                    model_name="gemini-test",
                    notes=None,
                ),
            )
        },
    )

    media_key = source_external_key_for_media(media_asset)
    assert outcomes[media_key].status == "cached_prompt_version_mismatch"
    assert "cached_prompt_version_mismatch" in outcomes[media_key].flags


def test_normalize_gemini_candidate_does_not_map_female_to_mixed() -> None:
    normalized = _normalize_gemini_candidate(
        {
            "technical_quality": "high",
            "pedagogical_quality": "high",
            "life_stage": "adult",
            "sex": "female",
            "visible_parts": ["full_body"],
            "view_angle": "lateral",
            "confidence": 0.8,
            "notes": None,
        }
    )

    assert normalized["sex"] == "female"


def test_prompt_bundle_supports_multiple_tasks() -> None:
    screening_bundle = build_prompt_bundle(task_name="screening")
    feature_bundle = build_prompt_bundle(task_name="feature_visibility")

    assert screening_bundle.version == "phase1.inat.screening.v1"
    assert feature_bundle.version == "phase1.inat.feature_visibility.v1"


def test_review_contract_version_defaults_to_v1_1(monkeypatch) -> None:
    monkeypatch.delenv(AI_REVIEW_CONTRACT_VERSION_ENV, raising=False)
    assert resolve_ai_review_contract_version(None) == "v1_1"


def test_cached_ai_defaults_to_v1_1_when_no_selector_is_provided() -> None:
    media_asset = MediaAsset(
        media_id="media:fixture:cached-v12-default",
        source_name=SourceName.INATURALIST,
        source_media_id="cached-v12-default",
        media_type=MediaType.IMAGE,
        source_url="fixture://media/cached-v12-default",
        attribution="fixture",
        license="CC-BY",
        mime_type="image/jpeg",
        file_extension="jpg",
        width=1600,
        height=1200,
        source_observation_uid="obs:fixture:2",
        canonical_taxon_id="taxon:birds:000014",
        raw_payload_ref="fixture.json#/media/cached-v12-default",
    )
    media_key = source_external_key_for_media(media_asset)

    outcomes = collect_ai_qualification_outcomes(
        [media_asset],
        qualifier_mode="cached",
        precomputed_ai_outcomes={
            media_key: AIQualificationOutcome(
                status="ok",
                prompt_version=BIRD_IMAGE_REVIEW_PROMPT_VERSION,
                qualification=AIQualification(
                    technical_quality="high",
                    pedagogical_quality="high",
                    life_stage="adult",
                    sex="unknown",
                    visible_parts=["head", "beak"],
                    view_angle="lateral",
                    confidence=0.9,
                    model_name="gemini-test",
                    notes="v1.2 payload",
                ),
            )
        },
    )

    assert outcomes[media_key].status == "cached_prompt_version_mismatch"


def test_cached_ai_uses_v1_2_only_when_explicitly_selected() -> None:
    media_asset = MediaAsset(
        media_id="media:fixture:cached-v12-explicit",
        source_name=SourceName.INATURALIST,
        source_media_id="cached-v12-explicit",
        media_type=MediaType.IMAGE,
        source_url="fixture://media/cached-v12-explicit",
        attribution="fixture",
        license="CC-BY",
        mime_type="image/jpeg",
        file_extension="jpg",
        width=1600,
        height=1200,
        source_observation_uid="obs:fixture:3",
        canonical_taxon_id="taxon:birds:000014",
        raw_payload_ref="fixture.json#/media/cached-v12-explicit",
    )
    media_key = source_external_key_for_media(media_asset)

    outcomes = collect_ai_qualification_outcomes(
        [media_asset],
        qualifier_mode="cached",
        precomputed_ai_outcomes={
            media_key: AIQualificationOutcome(
                status="ok",
                prompt_version=BIRD_IMAGE_REVIEW_PROMPT_VERSION,
                review_contract_version=AI_REVIEW_CONTRACT_V1_2,
                qualification=AIQualification(
                    technical_quality="high",
                    pedagogical_quality="high",
                    life_stage="adult",
                    sex="unknown",
                    visible_parts=["head", "beak"],
                    view_angle="lateral",
                    confidence=0.9,
                    model_name="gemini-test",
                    notes="v1.2 payload",
                ),
            )
        },
        review_contract_version=AI_REVIEW_CONTRACT_V1_2,
    )

    assert outcomes[media_key].status == "ok"
    assert outcomes[media_key].prompt_version == BIRD_IMAGE_REVIEW_PROMPT_VERSION
