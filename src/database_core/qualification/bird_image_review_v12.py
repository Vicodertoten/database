from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path

from jsonschema import FormatChecker, ValidationError, validate

BIRD_IMAGE_REVIEW_SCHEMA_VERSION = "bird_image_pedagogical_review.v1.2"
BIRD_IMAGE_REVIEW_PROMPT_VERSION = "bird_image_review_prompt.v1.2"

DEFAULT_BIRD_IMAGE_REVIEW_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "schemas"
    / "bird_image_pedagogical_review_v1_2.schema.json"
)

BIRD_IMAGE_REVIEW_FAILURE_REASONS = (
    "image_not_accessible",
    "non_bird_subject",
    "subject_too_occluded",
    "image_too_blurry",
    "insufficient_information",
    "unsafe_or_invalid_content",
    "model_output_invalid",
    "schema_validation_failed",
)

_LEVEL_SCORE = {
    "high": 1.0,
    "medium": 0.6,
    "low": 0.25,
    "none": 0.0,
    "unusable": 0.0,
}

_SCORE_WEIGHTS = {
    "technical_quality": 20,
    "subject_visibility": 20,
    "diagnostic_feature_visibility": 25,
    "representativeness": 15,
    "feedback_quality": 20,
}

_REQUIRED_SUCCESS_KEYS = {
    "schema_version",
    "prompt_version",
    "status",
    "failure_reason",
    "image_assessment",
    "pedagogical_assessment",
    "identification_features_visible_in_this_image",
    "post_answer_feedback",
    "limitations",
    "overall_confidence",
}


def build_bird_image_review_prompt_v12(
    *,
    scientific_name: str,
    common_names: Mapping[str, str] | None = None,
    image_url: str | None = None,
    app_mode: str = "quiz",
    learner_level: str = "beginner_to_intermediate",
    feedback_moment: str = "after_answer",
) -> str:
    input_payload = {
        "scientific_name": scientific_name.strip(),
        "common_names": dict(common_names or {}),
        "image_url": (image_url or "").strip(),
        "context": {
            "app_mode": app_mode,
            "learner_level": learner_level,
            "feedback_moment": feedback_moment,
        },
    }
    serialized_input = json.dumps(input_payload, ensure_ascii=True, sort_keys=True)
    return (
        "You are an expert bird identification assistant helping build an educational quiz app. "
        "You will receive one bird image, the expected scientific name, optional common names, "
        "and optional iNaturalist metadata. "
        "Return strict JSON only. Do not return markdown, comments, or any text outside JSON. "
        "Do not override the provided species and do not rename the taxon. "
        "Do not compute the final pedagogical score. "
        "Only fail when the image is clearly unusable, inaccessible, non-bird, "
        "too blurry, too occluded, "
        "or has insufficient pedagogical information. "
        "Feedback language must be French and must reference this specific image. "
        "Use formulations such as 'Sur cette image...' and avoid generic advice. "
        "Return the schema "
        "bird_image_pedagogical_review.v1.2 with prompt version bird_image_review_prompt.v1.2. "
        f"Input context JSON: {serialized_input}"
    )


def build_failed_bird_image_review_v12(
    *,
    failure_reason: str,
    consistency_warning: str | None = None,
) -> dict[str, object]:
    normalized_reason = _normalize_failure_reason(failure_reason)
    return {
        "schema_version": BIRD_IMAGE_REVIEW_SCHEMA_VERSION,
        "prompt_version": BIRD_IMAGE_REVIEW_PROMPT_VERSION,
        "status": "failed",
        "failure_reason": normalized_reason,
        "consistency_warning": _normalize_consistency_warning(consistency_warning),
        "overall_confidence": 0,
    }


def parse_bird_image_pedagogical_review_v12(raw_response: str) -> dict[str, object]:
    try:
        candidate = json.loads(raw_response)
    except json.JSONDecodeError:
        return build_failed_bird_image_review_v12(failure_reason="model_output_invalid")

    if not isinstance(candidate, Mapping):
        return build_failed_bird_image_review_v12(failure_reason="model_output_invalid")

    if _normalize_status(candidate.get("status")) == "success":
        missing_success_keys = _REQUIRED_SUCCESS_KEYS.difference(set(candidate))
        if missing_success_keys:
            return build_failed_bird_image_review_v12(failure_reason="schema_validation_failed")

    normalized_payload = normalize_bird_image_pedagogical_review_v12(candidate)

    try:
        validate_bird_image_pedagogical_review_v12(normalized_payload)
    except ValueError:
        return build_failed_bird_image_review_v12(failure_reason="schema_validation_failed")

    if not is_playable_bird_image_review_v12(normalized_payload):
        if normalized_payload.get("status") == "failed":
            return normalized_payload
        return build_failed_bird_image_review_v12(failure_reason="insufficient_information")

    return normalized_payload


def normalize_bird_image_pedagogical_review_v12(
    candidate: Mapping[str, object],
) -> dict[str, object]:
    status = _normalize_status(candidate.get("status"))
    if status == "failed":
        return build_failed_bird_image_review_v12(
            failure_reason=_normalize_failure_reason(candidate.get("failure_reason")),
            consistency_warning=_normalize_consistency_warning(candidate.get("consistency_warning")),
        )

    image_assessment_input = _mapping(candidate.get("image_assessment"))
    pedagogical_assessment_input = _mapping(candidate.get("pedagogical_assessment"))

    image_assessment: dict[str, object] = {
        "technical_quality": _normalize_choice(
            image_assessment_input.get("technical_quality"),
            allowed={"high", "medium", "low", "unusable"},
            fallback="unusable",
            aliases={
                "bad": "low",
                "poor": "low",
                "excellent": "high",
                "none": "unusable",
            },
        ),
        "subject_visibility": _normalize_choice(
            image_assessment_input.get("subject_visibility"),
            allowed={"high", "medium", "low", "none"},
            fallback="none",
            aliases={
                "unseen": "none",
                "hidden": "none",
            },
        ),
        "sharpness": _normalize_choice(
            image_assessment_input.get("sharpness"),
            allowed={"high", "medium", "low"},
            fallback="low",
            aliases={"blurry": "low", "blurred": "low", "soft": "low"},
        ),
        "lighting": _normalize_choice(
            image_assessment_input.get("lighting"),
            allowed={"high", "medium", "low"},
            fallback="low",
            aliases={"poor": "low", "dim": "low", "good": "high"},
        ),
        "background_clutter": _normalize_choice(
            image_assessment_input.get("background_clutter"),
            allowed={"low", "medium", "high"},
            fallback="medium",
            aliases={"clean": "low", "busy": "high"},
        ),
        "occlusion": _normalize_choice(
            image_assessment_input.get("occlusion"),
            allowed={"none", "minor", "major"},
            fallback="major",
            aliases={"partial": "minor", "heavy": "major"},
        ),
        "view_angle": _normalize_view_angle(image_assessment_input.get("view_angle")),
        "visible_parts": _normalize_visible_parts(image_assessment_input.get("visible_parts")),
        "confidence": _normalize_confidence(image_assessment_input.get("confidence"), default=0.0),
    }

    pedagogical_assessment: dict[str, object] = {
        "pedagogical_quality": _normalize_choice(
            pedagogical_assessment_input.get("pedagogical_quality"),
            allowed={"high", "medium", "low"},
            fallback="low",
            aliases={"good": "high", "poor": "low"},
        ),
        "difficulty_level": _normalize_choice(
            pedagogical_assessment_input.get("difficulty_level"),
            allowed={"easy", "medium", "hard"},
            fallback="medium",
            aliases={"beginner": "easy", "advanced": "hard"},
        ),
        "media_role": _normalize_choice(
            pedagogical_assessment_input.get("media_role"),
            allowed={
                "primary_identification",
                "secondary_support",
                "confusion_training",
                "not_recommended",
            },
            fallback="not_recommended",
            aliases={
                "primary_id": "primary_identification",
                "context": "secondary_support",
                "distractor_risk": "confusion_training",
                "non_diagnostic": "not_recommended",
            },
        ),
        "diagnostic_feature_visibility": _normalize_choice(
            pedagogical_assessment_input.get("diagnostic_feature_visibility"),
            allowed={"high", "medium", "low", "none"},
            fallback="none",
            aliases={"unknown": "none"},
        ),
        "representativeness": _normalize_choice(
            pedagogical_assessment_input.get("representativeness"),
            allowed={"high", "medium", "low"},
            fallback="low",
            aliases={"good": "high", "poor": "low"},
        ),
        "learning_suitability": _normalize_choice(
            pedagogical_assessment_input.get("learning_suitability"),
            allowed={"high", "medium", "low"},
            fallback="low",
            aliases={"good": "high", "poor": "low"},
        ),
        "confusion_relevance": _normalize_choice(
            pedagogical_assessment_input.get("confusion_relevance"),
            allowed={"high", "medium", "low"},
            fallback="low",
            aliases={"none": "low"},
        ),
        "confidence": _normalize_confidence(
            pedagogical_assessment_input.get("confidence"),
            default=0.0,
        ),
    }

    features = _normalize_identification_features(
        candidate.get("identification_features_visible_in_this_image"),
        visible_parts=image_assessment["visible_parts"],
    )

    post_answer_feedback = _normalize_post_answer_feedback(candidate)
    limitations = _normalize_limitations(candidate.get("limitations"))

    overall_confidence = _normalize_confidence(
        candidate.get("overall_confidence"),
        default=(
            image_assessment["confidence"]
            + pedagogical_assessment["confidence"]
            + post_answer_feedback["confidence"]
        )
        / 3,
    )

    return {
        "schema_version": BIRD_IMAGE_REVIEW_SCHEMA_VERSION,
        "prompt_version": BIRD_IMAGE_REVIEW_PROMPT_VERSION,
        "status": "success",
        "failure_reason": None,
        "consistency_warning": _normalize_consistency_warning(candidate.get("consistency_warning")),
        "image_assessment": image_assessment,
        "pedagogical_assessment": pedagogical_assessment,
        "identification_features_visible_in_this_image": features,
        "post_answer_feedback": post_answer_feedback,
        "limitations": limitations,
        "overall_confidence": overall_confidence,
    }


def validate_bird_image_pedagogical_review_v12(
    payload: Mapping[str, object],
    *,
    schema_path: Path | None = None,
) -> None:
    resolved_schema_path = schema_path or DEFAULT_BIRD_IMAGE_REVIEW_SCHEMA_PATH
    try:
        validate(
            instance=dict(payload),
            schema=_load_schema(resolved_schema_path),
            format_checker=FormatChecker(),
        )
    except ValidationError as exc:
        location = ".".join(str(item) for item in exc.absolute_path) or "<root>"
        raise ValueError(
            f"Bird image review v1.2 validation failed at {location}: {exc.message}"
        ) from exc

    if payload.get("status") == "failed" and payload.get("overall_confidence") != 0:
        raise ValueError("Failed bird image review payloads must set overall_confidence to 0")


def is_playable_bird_image_review_v12(payload: Mapping[str, object]) -> bool:
    if payload.get("status") != "success":
        return False

    image_assessment = _mapping(payload.get("image_assessment"))
    if image_assessment.get("technical_quality") == "unusable":
        return False
    if image_assessment.get("subject_visibility") == "none":
        return False

    features = payload.get("identification_features_visible_in_this_image")
    if not isinstance(features, Sequence) or len(features) < 1:
        return False

    post_answer_feedback = _mapping(payload.get("post_answer_feedback"))
    correct = _mapping(post_answer_feedback.get("correct"))
    incorrect = _mapping(post_answer_feedback.get("incorrect"))
    tips = _normalize_string_list(post_answer_feedback.get("identification_tips"))

    required_feedback = (
        _non_empty(correct.get("short"))
        and _non_empty(correct.get("long"))
        and _non_empty(incorrect.get("short"))
        and _non_empty(incorrect.get("long"))
    )
    return required_feedback and len(tips) >= 2


def compute_bird_image_pedagogical_score_v12(payload: Mapping[str, object]) -> dict[str, object]:
    if payload.get("status") != "success":
        return {
            "overall": 0,
            "subscores": {
                "technical_quality": 0,
                "subject_visibility": 0,
                "diagnostic_feature_visibility": 0,
                "representativeness": 0,
                "feedback_quality": 0,
            },
        }

    image_assessment = _mapping(payload.get("image_assessment"))
    pedagogical_assessment = _mapping(payload.get("pedagogical_assessment"))
    post_answer_feedback = _mapping(payload.get("post_answer_feedback"))

    technical_score = _weighted_score(
        image_assessment.get("technical_quality"),
        _SCORE_WEIGHTS["technical_quality"],
    )
    subject_visibility_score = _weighted_score(
        image_assessment.get("subject_visibility"),
        _SCORE_WEIGHTS["subject_visibility"],
    )
    diagnostic_visibility_score = _weighted_score(
        pedagogical_assessment.get("diagnostic_feature_visibility"),
        _SCORE_WEIGHTS["diagnostic_feature_visibility"],
    )
    representativeness_score = _weighted_score(
        pedagogical_assessment.get("representativeness"),
        _SCORE_WEIGHTS["representativeness"],
    )
    feedback_quality_score = _weighted_score(
        _feedback_quality_level(post_answer_feedback),
        _SCORE_WEIGHTS["feedback_quality"],
    )

    subscores = {
        "technical_quality": technical_score,
        "subject_visibility": subject_visibility_score,
        "diagnostic_feature_visibility": diagnostic_visibility_score,
        "representativeness": representativeness_score,
        "feedback_quality": feedback_quality_score,
    }
    return {
        "overall": int(sum(subscores.values())),
        "subscores": subscores,
    }


def _normalize_status(value: object) -> str:
    text = _normalize_text(value)
    if text in {"success", "ok", "passed", "valid"}:
        return "success"
    return "failed"


def _normalize_failure_reason(value: object) -> str:
    normalized = _normalize_choice(
        value,
        allowed=set(BIRD_IMAGE_REVIEW_FAILURE_REASONS),
        fallback="schema_validation_failed",
        aliases={
            "image_unavailable": "image_not_accessible",
            "not_accessible": "image_not_accessible",
            "non_bird": "non_bird_subject",
            "not_bird": "non_bird_subject",
            "occluded": "subject_too_occluded",
            "too_blurry": "image_too_blurry",
            "blurry": "image_too_blurry",
            "not_enough_information": "insufficient_information",
            "invalid_json": "model_output_invalid",
            "invalid_output": "model_output_invalid",
            "schema_error": "schema_validation_failed",
        },
    )
    return normalized


def _normalize_consistency_warning(value: object) -> str | None:
    text = _normalize_text(value)
    if text == "obvious_non_bird_subject":
        return text
    return None


def _normalize_view_angle(value: object) -> str:
    text = _normalize_text(value)
    if not text:
        return "unknown"
    if "side" in text or "profile" in text or text == "lateral":
        return "lateral"
    if "front" in text:
        return "frontal"
    if "rear" in text or "back" in text:
        return "rear"
    if "dors" in text or "top" in text:
        return "dorsal"
    if "ventr" in text or "under" in text or "below" in text:
        return "ventral"
    if "mixed" in text or "oblique" in text or "angle" in text:
        return "mixed"
    return "unknown"


def _normalize_visible_parts(value: object) -> list[str]:
    raw_values = _normalize_string_list(value)
    normalized = [_to_token(part) for part in raw_values]
    return [item for item in dict.fromkeys(normalized) if item]


def _normalize_identification_features(
    value: object,
    *,
    visible_parts: object,
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            if not isinstance(item, Mapping):
                continue
            feature = _non_empty(item.get("feature"))
            body_part = _non_empty(item.get("body_part"))
            explanation = _non_empty(item.get("explanation"))
            if feature is None or body_part is None or explanation is None:
                continue
            items.append(
                {
                    "feature": feature,
                    "body_part": body_part,
                    "visibility": _normalize_choice(
                        item.get("visibility"),
                        allowed={"high", "medium", "low"},
                        fallback="low",
                    ),
                    "importance_for_identification": _normalize_choice(
                        item.get("importance_for_identification"),
                        allowed={"high", "medium", "low"},
                        fallback="low",
                    ),
                    "explanation": explanation,
                }
            )

    if items:
        return items

    normalized_visible_parts = _normalize_visible_parts(visible_parts)
    if not normalized_visible_parts:
        return []

    first_part = normalized_visible_parts[0]
    return [
        {
            "feature": first_part.replace("_", " "),
            "body_part": first_part,
            "visibility": "medium",
            "importance_for_identification": "medium",
            "explanation": (
                f"In this image, the {first_part.replace('_', ' ')} is visible and useful."
            ),
        }
    ]


def _normalize_post_answer_feedback(candidate: Mapping[str, object]) -> dict[str, object]:
    post_feedback_input = _mapping(candidate.get("post_answer_feedback"))
    correct_input = _mapping(post_feedback_input.get("correct"))
    incorrect_input = _mapping(post_feedback_input.get("incorrect"))

    legacy_short = _non_empty(candidate.get("feedback_short"))
    legacy_long = _non_empty(candidate.get("feedback_long"))
    legacy_tips = _normalize_string_list(candidate.get("what_to_look_at"))

    correct_short = _non_empty(correct_input.get("short")) or legacy_short
    correct_long = _non_empty(correct_input.get("long")) or legacy_long or correct_short
    incorrect_short = _non_empty(incorrect_input.get("short")) or legacy_short
    incorrect_long = _non_empty(incorrect_input.get("long")) or legacy_long or incorrect_short

    tips = _normalize_string_list(post_feedback_input.get("identification_tips"))
    if not tips:
        tips = legacy_tips

    confidence = _normalize_feedback_confidence(
        post_feedback_input.get("confidence"),
        fallback_raw=candidate.get("feedback_confidence"),
    )

    return {
        "correct": {
            "short": correct_short or "",
            "long": correct_long or "",
        },
        "incorrect": {
            "short": incorrect_short or "",
            "long": incorrect_long or "",
        },
        "identification_tips": tips,
        "confidence": confidence,
    }


def _normalize_limitations(value: object) -> dict[str, object]:
    limitations = _mapping(value)
    why_not_ideal = _normalize_string_list(limitations.get("why_not_ideal"))
    uncertainty_reason = _non_empty(limitations.get("uncertainty_reason"))
    requires_human_review = bool(limitations.get("requires_human_review", False))
    return {
        "why_not_ideal": why_not_ideal,
        "uncertainty_reason": uncertainty_reason,
        "requires_human_review": requires_human_review,
    }


def _normalize_feedback_confidence(value: object, *, fallback_raw: object) -> float:
    if value is not None:
        return _normalize_confidence(value, default=0.0)

    fallback_text = _normalize_text(fallback_raw)
    if fallback_text and re.fullmatch(r"\d+(\.\d+)?", fallback_text):
        fallback = float(fallback_text)
        if fallback > 1:
            fallback = fallback / 100.0
        return _normalize_confidence(fallback, default=0.0)

    return 0.0


def _normalize_choice(
    value: object,
    *,
    allowed: set[str],
    fallback: str,
    aliases: Mapping[str, str] | None = None,
) -> str:
    text = _normalize_text(value)
    if not text:
        return fallback
    alias_map = {k: v for k, v in (aliases or {}).items()}
    text = alias_map.get(text, text)
    if text in allowed:
        return text
    return fallback


def _normalize_confidence(value: object, *, default: float) -> float:
    if value is None:
        return default
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if numeric > 1.0:
        return default
    if numeric < 0.0:
        return default
    return numeric


def _normalize_string_list(value: object) -> list[str]:
    if value is None:
        return []
    raw_values: list[str] = []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        raw_values = [str(item) for item in value]
    else:
        raw_values = re.split(r"[,;|]", str(value))
    normalized = []
    for raw in raw_values:
        item = _non_empty(raw)
        if item is None:
            continue
        normalized.append(item)
    return list(dict.fromkeys(normalized))


def _feedback_quality_level(post_answer_feedback: Mapping[str, object]) -> str:
    correct = _mapping(post_answer_feedback.get("correct"))
    incorrect = _mapping(post_answer_feedback.get("incorrect"))
    tips = _normalize_string_list(post_answer_feedback.get("identification_tips"))
    confidence = _normalize_confidence(post_answer_feedback.get("confidence"), default=0.0)

    has_required_text = (
        _non_empty(correct.get("short"))
        and _non_empty(correct.get("long"))
        and _non_empty(incorrect.get("short"))
        and _non_empty(incorrect.get("long"))
    )
    if not has_required_text or len(tips) < 2:
        return "low"
    if confidence >= 0.75 and len(tips) >= 3:
        return "high"
    if confidence >= 0.40:
        return "medium"
    return "low"


def _weighted_score(level: object, weight: int) -> int:
    normalized = _normalize_text(level)
    ratio = _LEVEL_SCORE.get(normalized, 0.0)
    return int(round(weight * ratio))


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _non_empty(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _to_token(value: object) -> str:
    text = _normalize_text(value)
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


@lru_cache(maxsize=2)
def _load_schema(schema_path: Path) -> dict[str, object]:
    return json.loads(schema_path.read_text(encoding="utf-8"))
