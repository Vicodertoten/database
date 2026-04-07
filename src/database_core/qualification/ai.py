from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Protocol

from database_core.domain.enums import ViewAngle
from database_core.domain.models import AIQualification, MediaAsset


class AIQualifier(Protocol):
    def qualify(self, media_asset: MediaAsset, *, image_bytes: bytes | None = None) -> AIQualification | None:
        ...


@dataclass(frozen=True)
class AIQualificationOutcome:
    qualification: AIQualification | None
    flags: tuple[str, ...] = ()
    note: str | None = None


class FixtureAIQualifier:
    def __init__(self, qualifications_by_source_media_id: Mapping[str, AIQualification]) -> None:
        self.qualifications_by_source_media_id = dict(qualifications_by_source_media_id)

    def qualify(self, media_asset: MediaAsset, *, image_bytes: bytes | None = None) -> AIQualification | None:
        del image_bytes
        return self.qualifications_by_source_media_id.get(media_asset.source_media_id)


class GeminiVisionQualifier:
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash") -> None:
        self.api_key = api_key
        self.model_name = model_name

    def qualify(self, media_asset: MediaAsset, *, image_bytes: bytes | None = None) -> AIQualification | None:
        if image_bytes is None or media_asset.mime_type is None:
            return None

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                "Classify this bird image for a biodiversity learning dataset. "
                                "Return strict JSON with keys: technical_quality, pedagogical_quality, "
                                "life_stage, sex, visible_parts, view_angle, confidence, notes."
                            )
                        },
                        {
                            "inline_data": {
                                "mime_type": media_asset.mime_type,
                                "data": base64.b64encode(image_bytes).decode("ascii"),
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json"
            },
        }
        request = urllib.request.Request(
            url=(
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.model_name}:generateContent?key={self.api_key}"
            ),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            response_payload = json.loads(response.read().decode("utf-8"))

        text = response_payload["candidates"][0]["content"]["parts"][0]["text"]
        candidate = json.loads(text)
        candidate["model_name"] = self.model_name
        return AIQualification(**candidate)


def collect_ai_qualification_outcomes(
    media_assets: Sequence[MediaAsset],
    *,
    qualifier_mode: str,
    precomputed_ai_qualifications: Mapping[str, AIQualification] | None = None,
    cached_image_paths_by_source_media_id: Mapping[str, Path] | None = None,
    gemini_api_key: str | None = None,
    gemini_model: str = "gemini-2.5-flash",
    qualifier: AIQualifier | None = None,
) -> dict[str, AIQualificationOutcome]:
    if qualifier_mode == "rules":
        return {}

    if qualifier_mode == "fixture":
        precomputed = dict(precomputed_ai_qualifications or {})
        return {
            media_asset.source_media_id: (
                AIQualificationOutcome(
                    qualification=precomputed[media_asset.source_media_id],
                    flags=_completeness_flags(precomputed[media_asset.source_media_id]),
                )
                if media_asset.source_media_id in precomputed
                else AIQualificationOutcome(
                    qualification=None,
                    flags=("missing_fixture_ai_output",),
                    note=f"no fixture ai output for {media_asset.source_media_id}",
                )
            )
            for media_asset in media_assets
        }

    if qualifier_mode != "gemini":
        raise ValueError(f"Unsupported qualifier mode: {qualifier_mode}")

    if qualifier is None:
        if not gemini_api_key:
            raise ValueError("gemini_api_key is required when qualifier_mode='gemini'")
        qualifier = GeminiVisionQualifier(api_key=gemini_api_key, model_name=gemini_model)

    image_paths = dict(cached_image_paths_by_source_media_id or {})
    outcomes: dict[str, AIQualificationOutcome] = {}
    for media_asset in media_assets:
        image_path = image_paths.get(media_asset.source_media_id)
        if image_path is None or not image_path.exists():
            outcomes[media_asset.source_media_id] = AIQualificationOutcome(
                qualification=None,
                flags=("missing_cached_image",),
                note=f"missing cached image for {media_asset.source_media_id}",
            )
            continue
        try:
            image_bytes = image_path.read_bytes()
        except OSError as exc:
            outcomes[media_asset.source_media_id] = AIQualificationOutcome(
                qualification=None,
                flags=("missing_cached_image",),
                note=f"failed to read cached image for {media_asset.source_media_id}: {exc}",
            )
            continue

        try:
            qualification = qualifier.qualify(media_asset, image_bytes=image_bytes)
        except json.JSONDecodeError as exc:
            outcomes[media_asset.source_media_id] = AIQualificationOutcome(
                qualification=None,
                flags=("invalid_gemini_json",),
                note=f"gemini returned invalid json for {media_asset.source_media_id}: {exc}",
            )
            continue
        except Exception as exc:  # noqa: BLE001
            outcomes[media_asset.source_media_id] = AIQualificationOutcome(
                qualification=None,
                flags=("gemini_error",),
                note=f"gemini error for {media_asset.source_media_id}: {type(exc).__name__}: {exc}",
            )
            continue

        if qualification is None:
            outcomes[media_asset.source_media_id] = AIQualificationOutcome(
                qualification=None,
                flags=("gemini_error",),
                note=f"gemini returned no result for {media_asset.source_media_id}",
            )
            continue

        outcomes[media_asset.source_media_id] = AIQualificationOutcome(
            qualification=qualification,
            flags=_completeness_flags(qualification),
        )
    return outcomes


def _completeness_flags(qualification: AIQualification) -> tuple[str, ...]:
    flags: list[str] = []
    if not qualification.visible_parts or qualification.view_angle == ViewAngle.UNKNOWN:
        flags.append("incomplete_required_tags")
    return tuple(flags)
