from __future__ import annotations

import base64
import io
import json
import re
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.error import HTTPError, URLError

from PIL import Image, UnidentifiedImageError

from database_core.domain.enums import SourceName, TaxonGroup, ViewAngle
from database_core.domain.models import AIQualification, MediaAsset

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
MIN_AI_IMAGE_WIDTH = 512
MIN_AI_IMAGE_HEIGHT = 512
SOURCE_KEY_SEPARATOR = "::"

SourceExternalKey = tuple[SourceName, str]

PROMPT_BASE_TEXT = (
    "Return strict JSON only for biodiversity-learning dataset qualification. "
    "Return exactly these keys: technical_quality, pedagogical_quality, life_stage, sex, "
    "visible_parts, view_angle, confidence, notes. "
    "technical_quality and pedagogical_quality must be one of: unknown, low, medium, high. "
    "sex must be one of: unknown, male, female, mixed. "
    "visible_parts must be a JSON array of short snake_case strings. "
    "view_angle must be one of: unknown, lateral, frontal, dorsal, ventral, oblique, close_up. "
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
        "confidence",
        "notes",
    ],
    "additionalProperties": False,
}


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
        self, media_asset: MediaAsset, *, image_bytes: bytes | None = None
    ) -> AIQualification | None: ...


@dataclass(frozen=True)
class AIQualificationOutcome:
    status: str = "ok"
    qualification: AIQualification | None = None
    flags: tuple[str, ...] = ()
    note: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
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
            )

        qualification_payload = payload.get("qualification")
        qualification = AIQualification(**qualification_payload) if qualification_payload else None
        qualified_at_raw = payload.get("qualified_at")
        qualified_at = None
        if qualified_at_raw:
            qualified_at = datetime.fromisoformat(str(qualified_at_raw).replace("Z", "+00:00"))
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
        self, media_asset: MediaAsset, *, image_bytes: bytes | None = None
    ) -> AIQualification | None:
        del image_bytes
        return self.qualifications_by_source_media_id.get(media_asset.source_media_id)


class GeminiVisionQualifier:
    def __init__(
        self,
        api_key: str,
        model_name: str = DEFAULT_GEMINI_MODEL,
        prompt_bundle: PromptBundle | None = None,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.prompt_bundle = prompt_bundle or DEFAULT_PROMPT_BUNDLE

    def qualify(
        self, media_asset: MediaAsset, *, image_bytes: bytes | None = None
    ) -> AIQualification | None:
        if image_bytes is None or media_asset.mime_type is None:
            return None

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
        request = urllib.request.Request(
            url=(
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"{self.model_name}:generateContent"
            ),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise GeminiRequestError.from_http_error(exc) from exc

        text = response_payload["candidates"][0]["content"]["parts"][0]["text"]
        candidate = _normalize_gemini_candidate(json.loads(text))
        candidate["model_name"] = self.model_name
        return AIQualification(**candidate)


def collect_ai_qualification_outcomes(
    media_assets: Sequence[MediaAsset],
    *,
    qualifier_mode: str,
    precomputed_ai_qualifications: Mapping[SourceExternalKey, AIQualification] | None = None,
    precomputed_ai_outcomes: Mapping[SourceExternalKey, AIQualificationOutcome] | None = None,
    cached_image_paths_by_source_media_key: Mapping[SourceExternalKey, Path] | None = None,
    gemini_api_key: str | None = None,
    gemini_model: str = DEFAULT_GEMINI_MODEL,
    prompt_version: str = DEFAULT_GEMINI_PROMPT_VERSION,
    qualifier: AIQualifier | None = None,
    progress_callback: Callable[[int, int, MediaAsset, AIQualificationOutcome], None] | None = None,
) -> dict[SourceExternalKey, AIQualificationOutcome]:
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
                expected_prompt_version=prompt_version,
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
        )

    image_paths = dict(cached_image_paths_by_source_media_key or {})
    outcomes: dict[SourceExternalKey, AIQualificationOutcome] = {}
    total = len(media_assets)
    for index, media_asset in enumerate(media_assets, start=1):
        media_key = source_external_key_for_media(media_asset)
        outcome = _collect_single_ai_outcome(
            media_asset=media_asset,
            image_path=image_paths.get(media_key),
            qualifier=qualifier,
            gemini_model=gemini_model,
            prompt_version=prompt_version,
        )
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
            qualified_at=qualified_at,
            image_width=image_width,
            image_height=image_height,
        )

    try:
        qualification = qualifier.qualify(media_asset, image_bytes=image_bytes)
    except json.JSONDecodeError as exc:
        return AIQualificationOutcome(
            status="invalid_gemini_json",
            qualification=None,
            flags=("invalid_gemini_json",),
            note=f"gemini returned invalid json for {media_asset.source_media_id}: {exc}",
            model_name=gemini_model,
            prompt_version=prompt_version,
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
            qualified_at=qualified_at,
            image_width=image_width,
            image_height=image_height,
        )

    if qualification is None:
        return AIQualificationOutcome(
            status="gemini_error",
            qualification=None,
            flags=("gemini_error",),
            note=f"gemini returned no result for {media_asset.source_media_id}",
            model_name=gemini_model,
            prompt_version=prompt_version,
            qualified_at=qualified_at,
            image_width=image_width,
            image_height=image_height,
        )

    return AIQualificationOutcome(
        status="ok",
        qualification=qualification,
        flags=_completeness_flags(qualification),
        note=qualification.notes,
        model_name=qualification.model_name or gemini_model,
        prompt_version=prompt_version,
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


def _normalize_text(value: object) -> str:
    if value in {None, ""}:
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _to_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")
