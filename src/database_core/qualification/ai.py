from __future__ import annotations

import base64
import io
import json
import os
import re
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError

from PIL import Image, UnidentifiedImageError

from database_core.domain.enums import SourceName, TaxonGroup, ViewAngle
from database_core.domain.models import AIQualification, CanonicalTaxon, MediaAsset
from database_core.qualification.bird_image_review_v12 import (
    BIRD_IMAGE_REVIEW_PROMPT_VERSION,
    DEFAULT_BIRD_IMAGE_REVIEW_SCHEMA_PATH,
    build_bird_image_review_prompt_v12,
    compute_bird_image_pedagogical_score_v12,
    parse_bird_image_pedagogical_review_v12,
)
from database_core.qualification.pedagogical_media_profile_prompt_v1 import (
    PEDAGOGICAL_MEDIA_PROFILE_PROMPT_VERSION,
    build_pedagogical_media_profile_prompt_v1,
)
from database_core.qualification.pedagogical_media_profile_v1 import (
    parse_pedagogical_media_profile_v1,
)

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
MIN_AI_IMAGE_WIDTH = 512
MIN_AI_IMAGE_HEIGHT = 512
SOURCE_KEY_SEPARATOR = "::"
AI_REVIEW_CONTRACT_VERSION_ENV = "AI_REVIEW_CONTRACT_VERSION"
AI_REVIEW_CONTRACT_V1_1 = "v1_1"
AI_REVIEW_CONTRACT_V1_2 = "v1_2"
AI_REVIEW_CONTRACT_PMP_V1 = "pedagogical_media_profile_v1"
SUPPORTED_AI_REVIEW_CONTRACT_VERSIONS = (
    AI_REVIEW_CONTRACT_V1_1,
    AI_REVIEW_CONTRACT_V1_2,
    AI_REVIEW_CONTRACT_PMP_V1,
)
DEFAULT_AI_REVIEW_CONTRACT_VERSION = AI_REVIEW_CONTRACT_V1_1
BIRD_IMAGE_REVIEW_FAILED_STATUS = "bird_image_review_failed"

SourceExternalKey = tuple[SourceName, str]

PROMPT_BASE_TEXT = (
    "Return strict JSON only for biodiversity-learning dataset qualification. "
    "Return exactly these keys: technical_quality, pedagogical_quality, life_stage, sex, "
    "visible_parts, view_angle, difficulty_level, media_role, confusion_relevance, "
    "diagnostic_feature_visibility, learning_suitability, uncertainty_reason, confidence, notes. "
    "technical_quality and pedagogical_quality must be one of: unknown, low, medium, high. "
    "sex must be one of: unknown, male, female, mixed. "
    "visible_parts must be a JSON array of short snake_case strings. "
    "view_angle must be one of: unknown, lateral, frontal, dorsal, ventral, oblique, close_up. "
    "difficulty_level must be one of: unknown, easy, medium, hard. "
    "media_role must be one of: primary_id, context, distractor_risk, non_diagnostic. "
    "confusion_relevance must be one of: none, low, medium, high. "
    "diagnostic_feature_visibility must be one of: unknown, low, medium, high. "
    "learning_suitability must be one of: unknown, low, medium, high. "
    "uncertainty_reason must be one of: none, occlusion, angle, distance, motion, "
    "multiple_subjects, model_uncertain, taxonomy_ambiguous. "
    "confidence must be a number between 0.0 and 1.0. "
    "Do not return prose outside the JSON object."
)
PROMPT_TAXON_GROUP_SUPPLEMENTS = {
    TaxonGroup.BIRDS: (
        "The subject is a bird and the assessment should focus on bird identification utility."
    )
}
PROMPT_TASKS = {
    "screening": {
        "version": "phase1.inat.screening.v1",
        "instruction": "Perform a fast screening-style assessment only.",
    },
    "qualification": {
        "version": "phase1.inat.image.v2",
        "instruction": "Classify this bird image for a biodiversity learning dataset.",
    },
    "feature_visibility": {
        "version": "phase1.inat.feature_visibility.v1",
        "instruction": "Focus on visibility of field marks and identification features.",
    },
}
STRICT_GEMINI_RESPONSE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "technical_quality": {
            "type": "string",
            "enum": ["unknown", "low", "medium", "high"],
            "description": "Technical image quality for identification use.",
        },
        "pedagogical_quality": {
            "type": "string",
            "enum": ["unknown", "low", "medium", "high"],
            "description": "Pedagogical usefulness. Descriptive only.",
        },
        "life_stage": {
            "type": "string",
            "description": "Estimated life stage or unknown.",
        },
        "sex": {
            "type": "string",
            "enum": ["unknown", "male", "female", "mixed"],
            "description": "Estimated sex or unknown.",
        },
        "visible_parts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short snake_case names of visible bird parts.",
        },
        "view_angle": {
            "type": "string",
            "enum": ["unknown", "lateral", "frontal", "dorsal", "ventral", "oblique", "close_up"],
            "description": "Primary view angle of the bird.",
        },
        "difficulty_level": {
            "type": "string",
            "enum": ["unknown", "easy", "medium", "hard"],
            "description": "Estimated learning difficulty for species identification.",
        },
        "media_role": {
            "type": "string",
            "enum": ["primary_id", "context", "distractor_risk", "non_diagnostic"],
            "description": "Primary pedagogical role of this media item.",
        },
        "confusion_relevance": {
            "type": "string",
            "enum": ["none", "low", "medium", "high"],
            "description": "How relevant this item is for confusion/differentiation training.",
        },
        "diagnostic_feature_visibility": {
            "type": "string",
            "enum": ["unknown", "low", "medium", "high"],
            "description": "Visibility level of diagnostic features used for identification.",
        },
        "learning_suitability": {
            "type": "string",
            "enum": ["unknown", "low", "medium", "high"],
            "description": "Suitability of this image for learning objectives.",
        },
        "uncertainty_reason": {
            "type": "string",
            "enum": [
                "none",
                "occlusion",
                "angle",
                "distance",
                "motion",
                "multiple_subjects",
                "model_uncertain",
                "taxonomy_ambiguous",
            ],
            "description": "Primary reason for uncertainty, if any.",
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Confidence in the structured assessment.",
        },
        "notes": {
            "type": ["string", "null"],
            "description": "Short justification or uncertainty note.",
        },
    },
    "required": [
        "technical_quality",
        "pedagogical_quality",
        "life_stage",
        "sex",
        "visible_parts",
        "view_angle",
        "difficulty_level",
        "media_role",
        "confusion_relevance",
        "diagnostic_feature_visibility",
        "learning_suitability",
        "uncertainty_reason",
        "confidence",
        "notes",
    ],
    "additionalProperties": False,
}


@lru_cache(maxsize=1)
def _v12_response_json_schema() -> dict[str, object]:
    return json.loads(DEFAULT_BIRD_IMAGE_REVIEW_SCHEMA_PATH.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class PromptBundle:
    task_name: str
    taxon_group: TaxonGroup
    version: str
    text: str


def build_prompt_bundle(
    *,
    task_name: str = "qualification",
    taxon_group: TaxonGroup = TaxonGroup.BIRDS,
) -> PromptBundle:
    task_config = PROMPT_TASKS[task_name]
    supplement = PROMPT_TAXON_GROUP_SUPPLEMENTS[taxon_group]
    return PromptBundle(
        task_name=task_name,
        taxon_group=taxon_group,
        version=str(task_config["version"]),
        text=" ".join([str(task_config["instruction"]), supplement, PROMPT_BASE_TEXT]),
    )


DEFAULT_PROMPT_BUNDLE = build_prompt_bundle()
DEFAULT_GEMINI_PROMPT_VERSION = DEFAULT_PROMPT_BUNDLE.version
STRICT_GEMINI_PROMPT = DEFAULT_PROMPT_BUNDLE.text


@dataclass(frozen=True)
class BirdImageReviewInput:
    scientific_name: str
    common_names: dict[str, str]
    image_url: str | None = None


def resolve_ai_review_contract_version(review_contract_version: str | None = None) -> str:
    raw = review_contract_version or os.environ.get(
        AI_REVIEW_CONTRACT_VERSION_ENV,
        DEFAULT_AI_REVIEW_CONTRACT_VERSION,
    )
    normalized = str(raw).strip().lower().replace(".", "_").replace("-", "_")
    if normalized in {"v1_1", "v11", "1_1", "1.1"}:
        return AI_REVIEW_CONTRACT_V1_1
    if normalized in {"v1_2", "v12", "1_2", "1.2"}:
        return AI_REVIEW_CONTRACT_V1_2
    if normalized in {
        "pedagogical_media_profile_v1",
        "pedagogical_media_profile_1",
        "pmp_v1",
        "pmp1",
    }:
        return AI_REVIEW_CONTRACT_PMP_V1
    raise ValueError(
        "Unsupported AI review contract version: "
        f"{raw!r}. Expected one of {SUPPORTED_AI_REVIEW_CONTRACT_VERSIONS}."
    )


def default_prompt_version_for_review_contract(review_contract_version: str) -> str:
    resolved = resolve_ai_review_contract_version(review_contract_version)
    if resolved == AI_REVIEW_CONTRACT_V1_2:
        return BIRD_IMAGE_REVIEW_PROMPT_VERSION
    if resolved == AI_REVIEW_CONTRACT_PMP_V1:
        from database_core.qualification.pedagogical_media_profile_prompt_v1 import (
            PEDAGOGICAL_MEDIA_PROFILE_PROMPT_VERSION,
        )
        return PEDAGOGICAL_MEDIA_PROFILE_PROMPT_VERSION
    return DEFAULT_GEMINI_PROMPT_VERSION


def source_external_key(*, source_name: SourceName, external_id: str) -> SourceExternalKey:
    return (source_name, external_id.strip())


def source_external_key_for_media(media_asset: MediaAsset) -> SourceExternalKey:
    return source_external_key(
        source_name=media_asset.source_name,
        external_id=media_asset.source_media_id,
    )


def serialize_source_external_key(key: SourceExternalKey) -> str:
    return f"{key[0]}{SOURCE_KEY_SEPARATOR}{key[1]}"


def parse_source_external_key(
    raw_key: str,
    *,
    default_source_name: SourceName | None = None,
) -> SourceExternalKey:
    if SOURCE_KEY_SEPARATOR in raw_key:
        source_raw, external_id = raw_key.split(SOURCE_KEY_SEPARATOR, 1)
        return source_external_key(
            source_name=SourceName(source_raw),
            external_id=external_id,
        )
    if default_source_name is None:
        raise ValueError(f"Missing source segment in source key: {raw_key!r}")
    return source_external_key(source_name=default_source_name, external_id=raw_key)


def build_bird_image_review_inputs_by_source_media_key(
    *,
    media_assets: Sequence[MediaAsset],
    canonical_taxa: Sequence[CanonicalTaxon],
) -> dict[SourceExternalKey, BirdImageReviewInput]:
    canonical_by_id = {item.canonical_taxon_id: item for item in canonical_taxa}
    inputs: dict[SourceExternalKey, BirdImageReviewInput] = {}
    for media_asset in media_assets:
        taxon = canonical_by_id.get(media_asset.canonical_taxon_id or "")
        if taxon is None:
            continue
        inputs[source_external_key_for_media(media_asset)] = BirdImageReviewInput(
            scientific_name=taxon.accepted_scientific_name,
            common_names=_resolve_primary_common_names(taxon),
            image_url=media_asset.source_url,
        )
    return inputs


class GeminiRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        self.retryable = retryable

    @classmethod
    def from_http_error(cls, exc: HTTPError) -> GeminiRequestError:
        retry_after_seconds = _parse_retry_after_seconds(exc)
        return cls(
            _format_gemini_http_error(exc),
            status_code=exc.code,
            retry_after_seconds=retry_after_seconds,
            retryable=exc.code in {408, 429, 500, 502, 503, 504},
        )


class AIQualifier(Protocol):
    def qualify(
        self,
        media_asset: MediaAsset,
        *,
        image_bytes: bytes | None = None,
        bird_image_review_input: BirdImageReviewInput | None = None,
    ) -> AIQualification | AIQualificationOutcome | None: ...


@dataclass(frozen=True)
class AIQualificationOutcome:
    status: str = "ok"
    qualification: AIQualification | None = None
    flags: tuple[str, ...] = ()
    note: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    review_contract_version: str | None = None
    bird_image_pedagogical_review: dict[str, object] | None = None
    bird_image_pedagogical_score: dict[str, object] | None = None
    pedagogical_media_profile: dict[str, object] | None = None
    pedagogical_media_profile_score: dict[str, object] | None = None
    qualified_at: datetime | None = None
    image_width: int | None = None
    image_height: int | None = None

    def to_snapshot_payload(self) -> dict[str, object]:
        return {
            "status": self.status,
            "qualification": (
                self.qualification.model_dump(mode="json")
                if self.qualification is not None
                else None
            ),
            "flags": list(self.flags),
            "note": self.note,
            "model_name": self.model_name,
            "prompt_version": self.prompt_version,
            "review_contract_version": self.review_contract_version,
            "bird_image_pedagogical_review": self.bird_image_pedagogical_review,
            "bird_image_pedagogical_score": self.bird_image_pedagogical_score,
            "pedagogical_media_profile": self.pedagogical_media_profile,
            "pedagogical_media_profile_score": self.pedagogical_media_profile_score,
            "qualified_at": self.qualified_at.isoformat().replace("+00:00", "Z")
            if self.qualified_at
            else None,
            "image_width": self.image_width,
            "image_height": self.image_height,
        }

    @classmethod
    def from_snapshot_payload(cls, payload: Mapping[str, object]) -> AIQualificationOutcome:
        if "status" not in payload and "qualification" not in payload:
            qualification = AIQualification(**payload)
            return cls(
                status="ok",
                qualification=qualification,
                flags=_completeness_flags(qualification),
                model_name=qualification.model_name,
                review_contract_version=AI_REVIEW_CONTRACT_V1_1,
            )

        qualification_payload = payload.get("qualification")
        qualification = AIQualification(**qualification_payload) if qualification_payload else None
        bird_image_review_payload = _mapping(payload.get("bird_image_pedagogical_review"))
        if (
            qualification is None
            and bird_image_review_payload
            and bird_image_review_payload.get("status") == "success"
        ):
            model_name = (
                str(payload["model_name"])
                if payload.get("model_name") is not None
                else "fixture-ai"
            )
            qualification = _ai_qualification_from_bird_image_review_v12(
                bird_image_review_payload,
                model_name=model_name,
            )
        qualified_at_raw = payload.get("qualified_at")
        qualified_at = None
        if qualified_at_raw:
            qualified_at = datetime.fromisoformat(str(qualified_at_raw).replace("Z", "+00:00"))
        review_contract_version = (
            str(payload["review_contract_version"])
            if payload.get("review_contract_version") is not None
            else _infer_review_contract_version(
                prompt_version=(
                    str(payload["prompt_version"])
                    if payload.get("prompt_version") is not None
                    else None
                )
            )
        )
        bird_image_score_payload = _mapping(payload.get("bird_image_pedagogical_score"))
        pmp_payload = _mapping(payload.get("pedagogical_media_profile"))
        pmp_score_payload = _mapping(payload.get("pedagogical_media_profile_score"))
        return cls(
            status=str(payload.get("status") or "ok"),
            qualification=qualification,
            flags=tuple(payload.get("flags", ())),
            note=str(payload["note"]) if payload.get("note") is not None else None,
            model_name=(
                str(payload["model_name"])
                if payload.get("model_name") is not None
                else qualification.model_name
                if qualification is not None
                else None
            ),
            prompt_version=(
                str(payload["prompt_version"])
                if payload.get("prompt_version") is not None
                else None
            ),
            review_contract_version=review_contract_version,
            bird_image_pedagogical_review=(
                dict(bird_image_review_payload) if bird_image_review_payload else None
            ),
            bird_image_pedagogical_score=(
                dict(bird_image_score_payload) if bird_image_score_payload else None
            ),
            pedagogical_media_profile=(
                dict(pmp_payload) if pmp_payload else None
            ),
            pedagogical_media_profile_score=(
                dict(pmp_score_payload) if pmp_score_payload else None
            ),
            qualified_at=qualified_at,
            image_width=int(payload["image_width"])
            if payload.get("image_width") is not None
            else None,
            image_height=int(payload["image_height"])
            if payload.get("image_height") is not None
            else None,
        )


class FixtureAIQualifier:
    def __init__(self, qualifications_by_source_media_id: Mapping[str, AIQualification]) -> None:
        self.qualifications_by_source_media_id = dict(qualifications_by_source_media_id)

    def qualify(
        self,
        media_asset: MediaAsset,
        *,
        image_bytes: bytes | None = None,
        bird_image_review_input: BirdImageReviewInput | None = None,
    ) -> AIQualification | None:
        del image_bytes, bird_image_review_input
        return self.qualifications_by_source_media_id.get(media_asset.source_media_id)


class GeminiVisionQualifier:
    def __init__(
        self,
        api_key: str,
        model_name: str = DEFAULT_GEMINI_MODEL,
        prompt_bundle: PromptBundle | None = None,
        review_contract_version: str | None = DEFAULT_AI_REVIEW_CONTRACT_VERSION,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.prompt_bundle = prompt_bundle or DEFAULT_PROMPT_BUNDLE
        self.review_contract_version = resolve_ai_review_contract_version(review_contract_version)

    def qualify(
        self,
        media_asset: MediaAsset,
        *,
        image_bytes: bytes | None = None,
        bird_image_review_input: BirdImageReviewInput | None = None,
    ) -> AIQualification | AIQualificationOutcome | None:
        if image_bytes is None or media_asset.mime_type is None:
            return None

        if self.review_contract_version == AI_REVIEW_CONTRACT_V1_2:
            return self._qualify_v12(
                media_asset=media_asset,
                image_bytes=image_bytes,
                bird_image_review_input=bird_image_review_input,
            )

        if self.review_contract_version == AI_REVIEW_CONTRACT_PMP_V1:
            return self._qualify_pedagogical_media_profile_v1(
                media_asset=media_asset,
                image_bytes=image_bytes,
                bird_image_review_input=bird_image_review_input,
            )

        return self._qualify_v11(media_asset=media_asset, image_bytes=image_bytes)

    def _qualify_v11(
        self,
        *,
        media_asset: MediaAsset,
        image_bytes: bytes,
    ) -> AIQualification:
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": self.prompt_bundle.text},
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
                "responseMimeType": "application/json",
                "responseJsonSchema": STRICT_GEMINI_RESPONSE_SCHEMA,
                "mediaResolution": "MEDIA_RESOLUTION_HIGH",
            },
        }
        response_payload = _send_gemini_request(
            api_key=self.api_key,
            model_name=self.model_name,
            payload=payload,
        )
        text = response_payload["candidates"][0]["content"]["parts"][0]["text"]
        candidate = _normalize_gemini_candidate(json.loads(text))
        candidate["model_name"] = self.model_name
        return AIQualification(**candidate)

    def _qualify_v12(
        self,
        *,
        media_asset: MediaAsset,
        image_bytes: bytes,
        bird_image_review_input: BirdImageReviewInput | None,
    ) -> AIQualificationOutcome:
        review_input = bird_image_review_input or BirdImageReviewInput(
            scientific_name=(media_asset.canonical_taxon_id or "unknown_bird"),
            common_names={},
            image_url=media_asset.source_url,
        )
        prompt_text = build_bird_image_review_prompt_v12(
            scientific_name=review_input.scientific_name,
            common_names=review_input.common_names,
            image_url=review_input.image_url or media_asset.source_url,
        )
        payload_with_schema = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt_text},
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
                "responseMimeType": "application/json",
                "responseJsonSchema": _v12_response_json_schema(),
                "mediaResolution": "MEDIA_RESOLUTION_HIGH",
            },
        }
        response_payload: Mapping[str, object]
        try:
            response_payload = _send_gemini_request(
                api_key=self.api_key,
                model_name=self.model_name,
                payload=payload_with_schema,
            )
        except (GeminiRequestError, TimeoutError, URLError, OSError):
            # Keep JSON mode even when structured schema support is unstable.
            payload_without_schema = {
                "contents": payload_with_schema["contents"],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "mediaResolution": "MEDIA_RESOLUTION_HIGH",
                },
            }
            response_payload = _send_gemini_request(
                api_key=self.api_key,
                model_name=self.model_name,
                payload=payload_without_schema,
            )
        text = response_payload["candidates"][0]["content"]["parts"][0]["text"]
        review_payload = parse_bird_image_pedagogical_review_v12(
            text,
            gemini_model=self.model_name,
            media_id=media_asset.media_id,
            canonical_taxon_id=media_asset.canonical_taxon_id,
            scientific_name=review_input.scientific_name,
        )
        review_score = compute_bird_image_pedagogical_score_v12(review_payload)

        if review_payload.get("status") != "success":
            failure_reason = str(review_payload.get("failure_reason") or "model_output_invalid")
            return AIQualificationOutcome(
                status=BIRD_IMAGE_REVIEW_FAILED_STATUS,
                qualification=None,
                flags=(
                    BIRD_IMAGE_REVIEW_FAILED_STATUS,
                    f"{BIRD_IMAGE_REVIEW_FAILED_STATUS}_{failure_reason}",
                ),
                note=f"bird image review v1.2 failed: {failure_reason}",
                model_name=self.model_name,
                prompt_version=BIRD_IMAGE_REVIEW_PROMPT_VERSION,
                review_contract_version=AI_REVIEW_CONTRACT_V1_2,
                bird_image_pedagogical_review=dict(review_payload),
                bird_image_pedagogical_score=review_score,
            )

        qualification = _ai_qualification_from_bird_image_review_v12(
            review_payload,
            model_name=self.model_name,
        )
        return AIQualificationOutcome(
            status="ok",
            qualification=qualification,
            flags=_completeness_flags(qualification),
            note=qualification.notes,
            model_name=self.model_name,
            prompt_version=BIRD_IMAGE_REVIEW_PROMPT_VERSION,
            review_contract_version=AI_REVIEW_CONTRACT_V1_2,
            bird_image_pedagogical_review=dict(review_payload),
            bird_image_pedagogical_score=review_score,
        )

    def _qualify_pedagogical_media_profile_v1(
        self,
        *,
        media_asset: MediaAsset,
        image_bytes: bytes,
        bird_image_review_input: BirdImageReviewInput | None,
    ) -> AIQualificationOutcome:
        review_input = bird_image_review_input or BirdImageReviewInput(
            scientific_name=(media_asset.canonical_taxon_id or "unknown"),
            common_names={},
            image_url=media_asset.source_url,
        )
        prompt_text = build_pedagogical_media_profile_prompt_v1(
            expected_scientific_name=review_input.scientific_name,
            common_names=review_input.common_names,
            organism_group="bird",
            media_reference=review_input.image_url or media_asset.source_url or "",
        )
        request_payload: dict[str, object] = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt_text},
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
                "responseMimeType": "application/json",
                "mediaResolution": "MEDIA_RESOLUTION_HIGH",
            },
        }
        response_payload = _send_gemini_request(
            api_key=self.api_key,
            model_name=self.model_name,
            payload=request_payload,
        )
        text = response_payload["candidates"][0]["content"]["parts"][0]["text"]
        profile = parse_pedagogical_media_profile_v1(
            text,
            gemini_model=self.model_name,
            media_id=media_asset.media_id,
            canonical_taxon_id=media_asset.canonical_taxon_id,
            scientific_name=review_input.scientific_name,
        )
        review_status = str(profile.get("review_status") or "failed")
        scores = _mapping(profile.get("scores"))

        if review_status != "valid":
            failure_reason = str(profile.get("failure_reason") or "unknown_failure")
            return AIQualificationOutcome(
                status="pedagogical_media_profile_failed",
                qualification=None,
                flags=(
                    "pedagogical_media_profile_failed",
                    f"pedagogical_media_profile_failed_{failure_reason}",
                ),
                note=f"pedagogical_media_profile_v1 failed: {failure_reason}",
                model_name=self.model_name,
                prompt_version=PEDAGOGICAL_MEDIA_PROFILE_PROMPT_VERSION,
                review_contract_version=AI_REVIEW_CONTRACT_PMP_V1,
                pedagogical_media_profile=dict(profile),
                pedagogical_media_profile_score=dict(scores) if scores else None,
            )

        return AIQualificationOutcome(
            status="ok",
            qualification=None,
            flags=(),
            note=None,
            model_name=self.model_name,
            prompt_version=PEDAGOGICAL_MEDIA_PROFILE_PROMPT_VERSION,
            review_contract_version=AI_REVIEW_CONTRACT_PMP_V1,
            pedagogical_media_profile=dict(profile),
            pedagogical_media_profile_score=dict(scores) if scores else None,
        )


def _send_gemini_request(
    *,
    api_key: str,
    model_name: str,
    payload: Mapping[str, object],
) -> Mapping[str, object]:
        request = urllib.request.Request(
            url=(
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model_name}:generateContent"
            ),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise GeminiRequestError.from_http_error(exc) from exc


def collect_ai_qualification_outcomes(
    media_assets: Sequence[MediaAsset],
    *,
    qualifier_mode: str,
    precomputed_ai_qualifications: Mapping[SourceExternalKey, AIQualification] | None = None,
    precomputed_ai_outcomes: Mapping[SourceExternalKey, AIQualificationOutcome] | None = None,
    cached_image_paths_by_source_media_key: Mapping[SourceExternalKey, Path] | None = None,
    bird_image_review_inputs_by_source_media_key: Mapping[
        SourceExternalKey, BirdImageReviewInput
    ] | None = None,
    gemini_api_key: str | None = None,
    gemini_model: str = DEFAULT_GEMINI_MODEL,
    prompt_version: str | None = None,
    review_contract_version: str | None = None,
    qualifier: AIQualifier | None = None,
    gemini_concurrency: int = 1,
    progress_callback: Callable[[int, int, MediaAsset, AIQualificationOutcome], None] | None = None,
) -> dict[SourceExternalKey, AIQualificationOutcome]:
    resolved_review_contract_version = resolve_ai_review_contract_version(review_contract_version)
    resolved_prompt_version = prompt_version or default_prompt_version_for_review_contract(
        resolved_review_contract_version
    )

    if qualifier_mode == "rules":
        return {}

    if qualifier_mode == "fixture":
        precomputed = dict(precomputed_ai_qualifications or {})
        return {
            source_external_key_for_media(media_asset): (
                AIQualificationOutcome(
                    status="ok",
                    qualification=precomputed[source_external_key_for_media(media_asset)],
                    flags=_completeness_flags(
                        precomputed[source_external_key_for_media(media_asset)]
                    ),
                    model_name=precomputed[source_external_key_for_media(media_asset)].model_name,
                    prompt_version="fixture",
                    review_contract_version=AI_REVIEW_CONTRACT_V1_1,
                )
                if source_external_key_for_media(media_asset) in precomputed
                else AIQualificationOutcome(
                    status="missing_fixture_ai_output",
                    qualification=None,
                    flags=("missing_fixture_ai_output",),
                    note=(
                        "no fixture ai output for "
                        f"{serialize_source_external_key(source_external_key_for_media(media_asset))}"
                    ),
                    prompt_version="fixture",
                    review_contract_version=AI_REVIEW_CONTRACT_V1_1,
                )
            )
            for media_asset in media_assets
        }

    if qualifier_mode == "cached":
        precomputed = dict(precomputed_ai_outcomes or {})
        return {
            source_external_key_for_media(media_asset): _validate_cached_outcome(
                precomputed.get(
                    source_external_key_for_media(media_asset),
                    AIQualificationOutcome(
                        status="missing_cached_ai_output",
                        qualification=None,
                        flags=("missing_cached_ai_output",),
                        note=(
                            "no cached ai output for "
                            f"{serialize_source_external_key(source_external_key_for_media(media_asset))}"
                        ),
                    ),
                ),
                expected_prompt_version=resolved_prompt_version,
            )
            for media_asset in media_assets
        }

    if qualifier_mode != "gemini":
        raise ValueError(f"Unsupported qualifier mode: {qualifier_mode}")

    if qualifier is None:
        if not gemini_api_key:
            raise ValueError("gemini_api_key is required when qualifier_mode='gemini'")
        qualifier = GeminiVisionQualifier(
            api_key=gemini_api_key,
            model_name=gemini_model,
            prompt_bundle=DEFAULT_PROMPT_BUNDLE,
            review_contract_version=resolved_review_contract_version,
        )

    image_paths = dict(cached_image_paths_by_source_media_key or {})
    review_inputs = dict(bird_image_review_inputs_by_source_media_key or {})
    outcomes: dict[SourceExternalKey, AIQualificationOutcome] = {}
    total = len(media_assets)
    resolved_concurrency = max(1, gemini_concurrency)
    if resolved_concurrency == 1 or total <= 1:
        for index, media_asset in enumerate(media_assets, start=1):
            media_key = source_external_key_for_media(media_asset)
            outcome = _collect_single_ai_outcome(
                media_asset=media_asset,
                image_path=image_paths.get(media_key),
                qualifier=qualifier,
                gemini_model=gemini_model,
                prompt_version=resolved_prompt_version,
                review_contract_version=resolved_review_contract_version,
                bird_image_review_input=review_inputs.get(media_key),
            )
            outcomes[media_key] = outcome
            if progress_callback is not None:
                progress_callback(index, total, media_asset, outcome)
        return outcomes

    with ThreadPoolExecutor(max_workers=resolved_concurrency) as executor:
        futures_by_key: dict[SourceExternalKey, Future[AIQualificationOutcome]] = {}
        for media_asset in media_assets:
            media_key = source_external_key_for_media(media_asset)
            futures_by_key[media_key] = executor.submit(
                _collect_single_ai_outcome,
                media_asset=media_asset,
                image_path=image_paths.get(media_key),
                qualifier=qualifier,
                gemini_model=gemini_model,
                prompt_version=resolved_prompt_version,
                review_contract_version=resolved_review_contract_version,
                bird_image_review_input=review_inputs.get(media_key),
            )
        for index, media_asset in enumerate(media_assets, start=1):
            media_key = source_external_key_for_media(media_asset)
            outcome = futures_by_key[media_key].result()
            outcomes[media_key] = outcome
            if progress_callback is not None:
                progress_callback(index, total, media_asset, outcome)
    return outcomes


def build_ai_outputs_payload(
    outcomes_by_source_media_key: Mapping[SourceExternalKey, AIQualificationOutcome],
) -> dict[str, object]:
    return {
        serialize_source_external_key(source_key): outcome.to_snapshot_payload()
        for source_key, outcome in sorted(
            outcomes_by_source_media_key.items(),
            key=lambda item: serialize_source_external_key(item[0]),
        )
    }


def _validate_cached_outcome(
    outcome: AIQualificationOutcome,
    *,
    expected_prompt_version: str,
) -> AIQualificationOutcome:
    if outcome.status != "ok":
        return outcome
    if outcome.prompt_version == expected_prompt_version:
        return outcome
    expected = expected_prompt_version
    actual = outcome.prompt_version or "missing"
    return AIQualificationOutcome(
        status="cached_prompt_version_mismatch",
        qualification=None,
        flags=("cached_prompt_version_mismatch",),
        note=f"cached ai output prompt version mismatch: expected {expected}, got {actual}",
        model_name=outcome.model_name,
        prompt_version=outcome.prompt_version,
        review_contract_version=outcome.review_contract_version,
        bird_image_pedagogical_review=outcome.bird_image_pedagogical_review,
        bird_image_pedagogical_score=outcome.bird_image_pedagogical_score,
        pedagogical_media_profile=outcome.pedagogical_media_profile,
        pedagogical_media_profile_score=outcome.pedagogical_media_profile_score,
        qualified_at=outcome.qualified_at,
        image_width=outcome.image_width,
        image_height=outcome.image_height,
    )


def inspect_image_dimensions(path: Path) -> tuple[int | None, int | None]:
    try:
        with Image.open(path) as image:
            return image.width, image.height
    except (FileNotFoundError, OSError, UnidentifiedImageError):
        return None, None


def _collect_single_ai_outcome(
    *,
    media_asset: MediaAsset,
    image_path: Path | None,
    qualifier: AIQualifier,
    gemini_model: str,
    prompt_version: str,
    review_contract_version: str,
    bird_image_review_input: BirdImageReviewInput | None,
) -> AIQualificationOutcome:
    qualified_at = datetime.now(UTC)

    if image_path is None or not image_path.exists():
        return AIQualificationOutcome(
            status="missing_cached_image",
            qualification=None,
            flags=("missing_cached_image",),
            note=f"missing cached image for {media_asset.source_media_id}",
            model_name=gemini_model,
            prompt_version=prompt_version,
            review_contract_version=review_contract_version,
            qualified_at=qualified_at,
            image_width=media_asset.width,
            image_height=media_asset.height,
        )

    try:
        image_bytes = image_path.read_bytes()
    except OSError as exc:
        return AIQualificationOutcome(
            status="missing_cached_image",
            qualification=None,
            flags=("missing_cached_image",),
            note=f"failed to read cached image for {media_asset.source_media_id}: {exc}",
            model_name=gemini_model,
            prompt_version=prompt_version,
            review_contract_version=review_contract_version,
            qualified_at=qualified_at,
            image_width=media_asset.width,
            image_height=media_asset.height,
        )

    image_width, image_height = _resolve_image_dimensions(media_asset, image_bytes)
    if not _meets_minimum_ai_resolution(image_width=image_width, image_height=image_height):
        return AIQualificationOutcome(
            status="insufficient_resolution",
            qualification=None,
            flags=("insufficient_resolution",),
            note=(
                f"cached image below minimum Gemini resolution for {media_asset.source_media_id}: "
                f"{image_width}x{image_height}"
            ),
            model_name=gemini_model,
            prompt_version=prompt_version,
            review_contract_version=review_contract_version,
            qualified_at=qualified_at,
            image_width=image_width,
            image_height=image_height,
        )

    try:
        qualification_or_outcome = qualifier.qualify(
            media_asset,
            image_bytes=image_bytes,
            bird_image_review_input=bird_image_review_input,
        )
    except json.JSONDecodeError as exc:
        return AIQualificationOutcome(
            status="invalid_gemini_json",
            qualification=None,
            flags=("invalid_gemini_json",),
            note=f"gemini returned invalid json for {media_asset.source_media_id}: {exc}",
            model_name=gemini_model,
            prompt_version=prompt_version,
            review_contract_version=review_contract_version,
            qualified_at=qualified_at,
            image_width=image_width,
            image_height=image_height,
        )
    except (HTTPError, URLError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
        return AIQualificationOutcome(
            status="gemini_error",
            qualification=None,
            flags=("gemini_error",),
            note=f"gemini error for {media_asset.source_media_id}: {type(exc).__name__}: {exc}",
            model_name=gemini_model,
            prompt_version=prompt_version,
            review_contract_version=review_contract_version,
            qualified_at=qualified_at,
            image_width=image_width,
            image_height=image_height,
        )

    if qualification_or_outcome is None:
        return AIQualificationOutcome(
            status="gemini_error",
            qualification=None,
            flags=("gemini_error",),
            note=f"gemini returned no result for {media_asset.source_media_id}",
            model_name=gemini_model,
            prompt_version=prompt_version,
            review_contract_version=review_contract_version,
            qualified_at=qualified_at,
            image_width=image_width,
            image_height=image_height,
        )

    if isinstance(qualification_or_outcome, AIQualificationOutcome):
        return _normalize_qualification_outcome_from_qualifier(
            outcome=qualification_or_outcome,
            media_asset=media_asset,
            gemini_model=gemini_model,
            prompt_version=prompt_version,
            review_contract_version=review_contract_version,
            qualified_at=qualified_at,
            image_width=image_width,
            image_height=image_height,
        )

    qualification = qualification_or_outcome
    return AIQualificationOutcome(
        status="ok",
        qualification=qualification,
        flags=_completeness_flags(qualification),
        note=qualification.notes,
        model_name=qualification.model_name or gemini_model,
        prompt_version=prompt_version,
        review_contract_version=review_contract_version,
        qualified_at=qualified_at,
        image_width=image_width,
        image_height=image_height,
    )


def _resolve_image_dimensions(
    media_asset: MediaAsset,
    image_bytes: bytes,
) -> tuple[int | None, int | None]:
    if media_asset.width is not None and media_asset.height is not None:
        return media_asset.width, media_asset.height
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            return image.width, image.height
    except (OSError, UnidentifiedImageError):
        return media_asset.width, media_asset.height


def _meets_minimum_ai_resolution(*, image_width: int | None, image_height: int | None) -> bool:
    if image_width is None or image_height is None:
        return False
    return image_width >= MIN_AI_IMAGE_WIDTH and image_height >= MIN_AI_IMAGE_HEIGHT


def _completeness_flags(qualification: AIQualification) -> tuple[str, ...]:
    flags: list[str] = []
    if not qualification.visible_parts or qualification.view_angle == ViewAngle.UNKNOWN:
        flags.append("incomplete_required_tags")
    return tuple(flags)


def _normalize_qualification_outcome_from_qualifier(
    *,
    outcome: AIQualificationOutcome,
    media_asset: MediaAsset,
    gemini_model: str,
    prompt_version: str,
    review_contract_version: str,
    qualified_at: datetime,
    image_width: int | None,
    image_height: int | None,
) -> AIQualificationOutcome:
    qualification = outcome.qualification
    review_payload = _mapping(outcome.bird_image_pedagogical_review)
    if qualification is None and review_payload.get("status") == "success":
        qualification = _ai_qualification_from_bird_image_review_v12(
            review_payload,
            model_name=outcome.model_name or gemini_model,
        )

    resolved_flags = tuple(dict.fromkeys(outcome.flags or ()))
    resolved_status = str(outcome.status or "ok")
    if resolved_status != "ok" and not resolved_flags:
        resolved_flags = (resolved_status,)

    resolved_review_contract_version = (
        outcome.review_contract_version
        or _infer_review_contract_version(prompt_version=outcome.prompt_version)
        or review_contract_version
    )

    return AIQualificationOutcome(
        status=resolved_status,
        qualification=qualification,
        flags=resolved_flags,
        note=outcome.note,
        model_name=outcome.model_name or gemini_model,
        prompt_version=outcome.prompt_version or prompt_version,
        review_contract_version=resolved_review_contract_version,
        bird_image_pedagogical_review=(
            dict(review_payload) if review_payload else outcome.bird_image_pedagogical_review
        ),
        bird_image_pedagogical_score=(
            dict(outcome.bird_image_pedagogical_score)
            if isinstance(outcome.bird_image_pedagogical_score, Mapping)
            else outcome.bird_image_pedagogical_score
        ),
        pedagogical_media_profile=(
            dict(outcome.pedagogical_media_profile)
            if isinstance(outcome.pedagogical_media_profile, Mapping)
            else outcome.pedagogical_media_profile
        ),
        pedagogical_media_profile_score=(
            dict(outcome.pedagogical_media_profile_score)
            if isinstance(outcome.pedagogical_media_profile_score, Mapping)
            else outcome.pedagogical_media_profile_score
        ),
        qualified_at=outcome.qualified_at or qualified_at,
        image_width=image_width,
        image_height=image_height,
    )


def _infer_review_contract_version(prompt_version: str | None) -> str | None:
    if prompt_version == BIRD_IMAGE_REVIEW_PROMPT_VERSION:
        return AI_REVIEW_CONTRACT_V1_2
    if prompt_version == PEDAGOGICAL_MEDIA_PROFILE_PROMPT_VERSION:
        return AI_REVIEW_CONTRACT_PMP_V1
    if prompt_version:
        return AI_REVIEW_CONTRACT_V1_1
    return None


def _ai_qualification_from_bird_image_review_v12(
    review_payload: Mapping[str, object],
    *,
    model_name: str,
) -> AIQualification:
    image_assessment = _mapping(review_payload.get("image_assessment"))
    pedagogical_assessment = _mapping(review_payload.get("pedagogical_assessment"))
    limitations = _mapping(review_payload.get("limitations"))
    feature_payload = review_payload.get("identification_features_visible_in_this_image")
    first_feature_explanation = None
    if isinstance(feature_payload, Sequence) and feature_payload:
        first_feature = feature_payload[0]
        if isinstance(first_feature, Mapping):
            explanation = first_feature.get("explanation")
            if explanation is not None:
                first_feature_explanation = str(explanation).strip() or None

    why_not_ideal = limitations.get("why_not_ideal")
    limitation_note = None
    if isinstance(why_not_ideal, Sequence) and not isinstance(why_not_ideal, (str, bytes)):
        for item in why_not_ideal:
            text = str(item).strip()
            if text:
                limitation_note = text
                break

    notes = _join_non_blank(
        [
            first_feature_explanation,
            limitation_note,
        ],
        separator=" | ",
    )

    return AIQualification(
        technical_quality=_map_v12_technical_quality(image_assessment.get("technical_quality")),
        pedagogical_quality=_map_v12_pedagogical_quality(
            pedagogical_assessment.get("pedagogical_quality")
        ),
        life_stage="unknown",
        sex="unknown",
        visible_parts=_normalize_visible_parts(image_assessment.get("visible_parts")),
        view_angle=_map_v12_view_angle(image_assessment.get("view_angle")),
        difficulty_level=_map_v12_difficulty_level(pedagogical_assessment.get("difficulty_level")),
        media_role=_map_v12_media_role(pedagogical_assessment.get("media_role")),
        confusion_relevance=_map_v12_confusion_relevance(
            pedagogical_assessment.get("confusion_relevance")
        ),
        diagnostic_feature_visibility=_map_v12_diagnostic_feature_visibility(
            pedagogical_assessment.get("diagnostic_feature_visibility")
        ),
        learning_suitability=_map_v12_learning_suitability(
            pedagogical_assessment.get("learning_suitability")
        ),
        uncertainty_reason=_normalize_uncertainty_reason(limitations.get("uncertainty_reason")),
        confidence=_normalize_confidence(review_payload.get("overall_confidence")),
        model_name=model_name,
        notes=notes,
    )


def _map_v12_technical_quality(value: object) -> str:
    normalized = _normalize_text(value)
    if normalized in {"high", "medium", "low"}:
        return normalized
    if normalized == "unusable":
        return "low"
    return "unknown"


def _map_v12_pedagogical_quality(value: object) -> str:
    normalized = _normalize_text(value)
    if normalized in {"high", "medium", "low"}:
        return normalized
    return "unknown"


def _map_v12_view_angle(value: object) -> str:
    normalized = _normalize_text(value)
    mapping = {
        "lateral": "lateral",
        "frontal": "frontal",
        "dorsal": "dorsal",
        "ventral": "ventral",
        "rear": "oblique",
        "mixed": "oblique",
    }
    return mapping.get(normalized, "unknown")


def _map_v12_difficulty_level(value: object) -> str:
    normalized = _normalize_text(value)
    if normalized in {"easy", "medium", "hard"}:
        return normalized
    return "unknown"


def _map_v12_media_role(value: object) -> str:
    normalized = _normalize_text(value)
    mapping = {
        "primary_identification": "primary_id",
        "secondary_support": "context",
        "confusion_training": "distractor_risk",
        "not_recommended": "non_diagnostic",
    }
    return mapping.get(normalized, "context")


def _map_v12_confusion_relevance(value: object) -> str:
    normalized = _normalize_text(value)
    if normalized in {"high", "medium", "low"}:
        return normalized
    return "none"


def _map_v12_diagnostic_feature_visibility(value: object) -> str:
    normalized = _normalize_text(value)
    if normalized in {"high", "medium", "low"}:
        return normalized
    return "unknown"


def _map_v12_learning_suitability(value: object) -> str:
    normalized = _normalize_text(value)
    if normalized in {"high", "medium", "low"}:
        return normalized
    return "unknown"


def _normalize_gemini_candidate(candidate: Mapping[str, object]) -> dict[str, object]:
    notes = candidate.get("notes")
    if notes is None and candidate.get("note") is not None:
        notes = candidate.get("note")
    return {
        "technical_quality": _normalize_quality(candidate.get("technical_quality")),
        "pedagogical_quality": _normalize_quality(candidate.get("pedagogical_quality")),
        "life_stage": _normalize_life_stage(candidate.get("life_stage")),
        "sex": _normalize_sex(candidate.get("sex")),
        "visible_parts": _normalize_visible_parts(candidate.get("visible_parts")),
        "view_angle": _normalize_view_angle(candidate.get("view_angle")),
        "difficulty_level": _normalize_difficulty_level(candidate.get("difficulty_level")),
        "media_role": _normalize_media_role(candidate.get("media_role")),
        "confusion_relevance": _normalize_confusion_relevance(candidate.get("confusion_relevance")),
        "diagnostic_feature_visibility": _normalize_diagnostic_feature_visibility(
            candidate.get("diagnostic_feature_visibility")
        ),
        "learning_suitability": _normalize_learning_suitability(
            candidate.get("learning_suitability")
        ),
        "uncertainty_reason": _normalize_uncertainty_reason(candidate.get("uncertainty_reason")),
        "confidence": _normalize_confidence(candidate.get("confidence")),
        "notes": str(notes).strip() if notes not in {None, ""} else None,
    }


def _format_gemini_http_error(exc: HTTPError) -> str:
    detail = None
    try:
        payload = exc.read().decode("utf-8", errors="replace")
    except OSError:
        payload = ""

    if payload:
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            detail = payload.strip()
        else:
            error_payload = parsed.get("error")
            if isinstance(error_payload, Mapping) and error_payload.get("message") is not None:
                detail = str(error_payload["message"]).strip()

    if detail:
        return f"Gemini API request failed with HTTP {exc.code}: {detail}"
    return f"Gemini API request failed with HTTP {exc.code}: {exc.reason}"


def _parse_retry_after_seconds(exc: HTTPError) -> float | None:
    if exc.headers is None:
        return None
    retry_after = exc.headers.get("Retry-After")
    if retry_after is None:
        return None
    try:
        return max(0.0, float(retry_after))
    except ValueError:
        return None


def _normalize_quality(value: object) -> str:
    text = _normalize_text(value)
    if text in {"unknown", "low", "medium", "high"}:
        return text
    if "excellent" in text:
        return "high"
    if re.search(r"\bhigh\b", text):
        return "high"
    if any(token in text for token in ("good", "fair", "adequate", "moderate")):
        return "medium"
    if any(token in text for token in ("poor", "low", "blurry", "obscured")):
        return "low"
    return "unknown"


def _normalize_life_stage(value: object) -> str:
    text = _normalize_text(value)
    if not text:
        return "unknown"
    return text.replace(" ", "_")


def _normalize_sex(value: object) -> str:
    text = _normalize_text(value)
    tokens = set(re.findall(r"[a-z]+", text))
    if {"male", "female"}.issubset(tokens):
        return "mixed"
    if "female" in tokens:
        return "female"
    if "male" in tokens:
        return "male"
    if any(
        token in text for token in ("unknown", "undetermined", "indeterminate", "cannot determine")
    ):
        return "unknown"
    return "unknown"


def _normalize_visible_parts(value: object) -> list[str]:
    raw_items: list[str]
    if value is None:
        return []
    if isinstance(value, Sequence) and not isinstance(value, str):
        raw_items = [str(item) for item in value if str(item).strip()]
    else:
        raw_items = [item.strip() for item in re.split(r"[,;/]", str(value)) if item.strip()]

    normalized_parts: list[str] = []
    for raw_item in raw_items:
        text = _normalize_text(raw_item)
        if any(token in text for token in ("full body", "whole body", "entire body")):
            normalized_parts.append("full_body")
        for keyword in (
            "head",
            "beak",
            "wing",
            "breast",
            "tail",
            "eye",
            "leg",
            "foot",
            "back",
            "body",
        ):
            if keyword in text:
                normalized_parts.append(keyword.replace("foot", "feet").replace("leg", "legs"))
        if not normalized_parts or normalized_parts[-1] != _to_token(text):
            fallback = _to_token(text)
            if fallback and fallback not in normalized_parts:
                normalized_parts.append(fallback)
    return list(dict.fromkeys(part for part in normalized_parts if part))


def _normalize_view_angle(value: object) -> str:
    text = _normalize_text(value)
    if not text:
        return "unknown"
    if any(token in text for token in ("close", "macro", "headshot")):
        return "close_up"
    if "front" in text and "side" in text:
        return "oblique"
    if any(token in text for token in ("profile", "lateral", "side")):
        return "lateral"
    if any(token in text for token in ("frontal", "front")):
        return "frontal"
    if any(token in text for token in ("dorsal", "from above", "top")):
        return "dorsal"
    if any(token in text for token in ("ventral", "underside", "from below")):
        return "ventral"
    if any(token in text for token in ("oblique", "angled", "slightly from")):
        return "oblique"
    return "unknown"


def _normalize_confidence(value: object) -> float:
    if isinstance(value, (int, float)):
        return _scale_confidence(float(value))

    text = _normalize_text(value)
    if not text:
        return 0.0
    try:
        return _scale_confidence(float(text.rstrip("%")))
    except ValueError:
        pass

    if any(token in text for token in ("very high", "high", "excellent", "confident")):
        return 0.9
    if any(token in text for token in ("medium", "moderate", "good")):
        return 0.7
    if any(token in text for token in ("low", "poor")):
        return 0.4
    return 0.0


def _normalize_difficulty_level(value: object) -> str:
    text = _normalize_text(value)
    if text in {"unknown", "easy", "medium", "hard"}:
        return text
    if any(token in text for token in ("beginner", "simple", "easy")):
        return "easy"
    if any(token in text for token in ("advanced", "hard", "difficult")):
        return "hard"
    if any(token in text for token in ("intermediate", "moderate", "medium")):
        return "medium"
    return "unknown"


def _normalize_media_role(value: object) -> str:
    text = _normalize_text(value)
    if text in {"primary_id", "context", "distractor_risk", "non_diagnostic"}:
        return text
    if any(token in text for token in ("primary", "identification", "diagnostic")):
        return "primary_id"
    if any(token in text for token in ("distractor", "confusion", "lookalike")):
        return "distractor_risk"
    if any(token in text for token in ("non", "not diagnostic", "non_diagnostic")):
        return "non_diagnostic"
    if text:
        return "context"
    return "context"


def _normalize_confusion_relevance(value: object) -> str:
    text = _normalize_text(value)
    if text in {"none", "low", "medium", "high"}:
        return text
    if any(token in text for token in ("none", "not relevant", "irrelevant")):
        return "none"
    if any(token in text for token in ("high", "strong", "critical")):
        return "high"
    if any(token in text for token in ("medium", "moderate")):
        return "medium"
    if any(token in text for token in ("low", "slight")):
        return "low"
    return "none"


def _normalize_uncertainty_reason(value: object) -> str:
    text = _normalize_text(value)
    if text in {
        "none",
        "occlusion",
        "angle",
        "distance",
        "motion",
        "multiple_subjects",
        "model_uncertain",
        "taxonomy_ambiguous",
    }:
        return text
    if any(token in text for token in ("occlusion", "occluded", "blocked")):
        return "occlusion"
    if any(token in text for token in ("angle", "view", "perspective")):
        return "angle"
    if any(token in text for token in ("distance", "far", "small in frame")):
        return "distance"
    if any(token in text for token in ("motion", "blur", "moving")):
        return "motion"
    if any(token in text for token in ("multiple", "several", "group")):
        return "multiple_subjects"
    if any(token in text for token in ("taxonomy", "taxonomic")):
        return "taxonomy_ambiguous"
    if any(token in text for token in ("uncertain", "unsure", "low confidence")):
        return "model_uncertain"
    return "none"


def _normalize_diagnostic_feature_visibility(value: object) -> str:
    text = _normalize_text(value)
    if text in {"unknown", "low", "medium", "high"}:
        return text
    if any(token in text for token in ("high", "clear", "very visible", "strong")):
        return "high"
    if any(token in text for token in ("medium", "moderate", "partially visible")):
        return "medium"
    if any(token in text for token in ("low", "weak", "poorly visible", "not visible")):
        return "low"
    return "unknown"


def _normalize_learning_suitability(value: object) -> str:
    text = _normalize_text(value)
    if text in {"unknown", "low", "medium", "high"}:
        return text
    if any(token in text for token in ("high", "excellent", "ideal", "strong")):
        return "high"
    if any(token in text for token in ("medium", "moderate", "good")):
        return "medium"
    if any(token in text for token in ("low", "poor", "weak", "limited")):
        return "low"
    return "unknown"


def _scale_confidence(value: float) -> float:
    if value < 0:
        return 0.0
    if value <= 1:
        return value
    if value <= 5:
        return round(value / 5, 4)
    if value <= 100:
        return round(value / 100, 4)
    return 1.0


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _normalize_text(value: object) -> str:
    if value in {None, ""}:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _to_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


def _resolve_primary_common_names(taxon: CanonicalTaxon) -> dict[str, str]:
    names: dict[str, str] = {}
    multilingual = taxon.common_names_by_language or {}
    for language in ("fr", "en", "nl"):
        language_values = multilingual.get(language, [])
        if language_values:
            first = str(language_values[0]).strip()
            if first:
                names[language] = first
    if "en" not in names and taxon.common_names:
        first_common_name = str(taxon.common_names[0]).strip()
        if first_common_name:
            names["en"] = first_common_name
    return names


def _join_non_blank(
    parts: Sequence[str | None],
    *,
    separator: str = " ",
) -> str | None:
    cleaned = [item.strip() for item in parts if item and item.strip()]
    if not cleaned:
        return None
    return separator.join(cleaned)
