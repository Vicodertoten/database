import io
import json

import urllib.request

from database_core.domain.enums import MediaType, SourceName
from database_core.domain.models import AIQualification
from database_core.domain.models import MediaAsset
from database_core.qualification.ai import GeminiVisionQualifier, _normalize_gemini_candidate


def test_normalize_gemini_candidate_recovers_common_schema_drift() -> None:
    normalized = _normalize_gemini_candidate(
        {
            "technical_quality": "Good. The bird is in focus and the head, beak, and eye are sharp.",
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


def test_gemini_vision_qualifier_uses_structured_output_and_high_media_resolution(monkeypatch) -> None:
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
            canonical_taxon_id="bird:turdus-merula",
            raw_payload_ref="fixture.json#/media/1",
        ),
        image_bytes=io.BytesIO(b"fake-image").getvalue(),
    )

    generation_config = captured["payload"]["generationConfig"]
    assert generation_config["responseMimeType"] == "application/json"
    assert generation_config["mediaResolution"] == "MEDIA_RESOLUTION_HIGH"
    assert generation_config["responseJsonSchema"]["type"] == "object"
    assert "technical_quality" in generation_config["responseJsonSchema"]["required"]
    assert qualification.model_name == "gemini-3.1-flash-lite-preview"
