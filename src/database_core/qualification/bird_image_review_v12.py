from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

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

_IMAGE_CONTEXT_MARKERS = (
    "sur cette image",
    "ici",
    "dans cette image",
)

_FEATURE_KEYWORDS = {
    "bec",
    "beak",
    "tete",
    "head",
    "poitrine",
    "breast",
    "aile",
    "wing",
    "queue",
    "tail",
    "oeil",
    "eye",
    "silhouette",
    "profil",
    "posture",
    "plumage",
    "gorge",
    "dos",
    "ventre",
    "nuque",
    "pattes",
}

_MAX_RAW_EXCERPT_CHARS = 1200


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
    enum_reference = (
        "Enum reference (choose exactly one value per field): "
        "image_assessment.technical_quality=[high, medium, low, unusable]; "
        "image_assessment.subject_visibility=[high, medium, low, none]; "
        "image_assessment.sharpness=[high, medium, low]; "
        "image_assessment.lighting=[high, medium, low]; "
        "image_assessment.background_clutter=[low, medium, high]; "
        "image_assessment.occlusion=[none, minor, major]; "
        "image_assessment.view_angle=[lateral, frontal, rear, dorsal, ventral, mixed, unknown]; "
        "pedagogical_assessment.pedagogical_quality=[high, medium, low]; "
        "pedagogical_assessment.difficulty_level=[easy, medium, hard]; "
        "pedagogical_assessment.media_role=[primary_identification, secondary_support, "
        "confusion_training, not_recommended]; "
        "pedagogical_assessment.diagnostic_feature_visibility=[high, medium, low, none]; "
        "pedagogical_assessment.representativeness=[high, medium, low]; "
        "pedagogical_assessment.learning_suitability=[high, medium, low]; "
        "pedagogical_assessment.confusion_relevance=[high, medium, low]; "
        "identification_features_visible_in_this_image[].visibility=[high, medium, low]; "
        "identification_features_visible_in_this_image[].importance_for_identification="
        "[high, medium, low]."
    )
    concrete_example = (
        "{\"schema_version\":\"bird_image_pedagogical_review.v1.2\","
        "\"prompt_version\":\"bird_image_review_prompt.v1.2\","
        "\"status\":\"success\","
        "\"failure_reason\":null,"
        "\"consistency_warning\":null,"
        "\"image_assessment\":{"
        "\"technical_quality\":\"high\","
        "\"subject_visibility\":\"high\","
        "\"sharpness\":\"medium\","
        "\"lighting\":\"medium\","
        "\"background_clutter\":\"low\","
        "\"occlusion\":\"minor\","
        "\"view_angle\":\"lateral\","
        "\"visible_parts\":[\"head\",\"beak\",\"breast\",\"tail\"],"
        "\"confidence\":0.86},"
        "\"pedagogical_assessment\":{"
        "\"pedagogical_quality\":\"high\","
        "\"difficulty_level\":\"easy\","
        "\"media_role\":\"primary_identification\","
        "\"diagnostic_feature_visibility\":\"high\","
        "\"representativeness\":\"high\","
        "\"learning_suitability\":\"high\","
        "\"confusion_relevance\":\"medium\","
        "\"confidence\":0.83},"
        "\"identification_features_visible_in_this_image\":[{"
        "\"feature\":\"thin pointed beak\","
        "\"body_part\":\"beak\","
        "\"visibility\":\"high\","
        "\"importance_for_identification\":\"high\","
        "\"explanation\":\"Sur cette image, le bec fin et pointu est nettement visible.\"}],"
        "\"post_answer_feedback\":{"
        "\"correct\":{\"short\":\"Oui. Sur cette image, le bec et la poitrine correspondent.\","
        "\"long\":\"Sur cette image, commence par le bec fin puis confirme avec la poitrine "
        "et la silhouette.\"},"
        "\"incorrect\":{\"short\":\"Pas encore. Sur cette image, verifie d'abord le bec "
        "et la poitrine.\","
        "\"long\":\"Ici, compare la forme du bec, la poitrine et la queue avant de conclure.\"},"
        "\"identification_tips\":["
        "\"Sur cette image, repere d'abord la forme du bec.\","
        "\"Ici, confirme ensuite la poitrine et la silhouette.\","
        "\"Observe aussi la queue pour valider l'identification.\"],"
        "\"confidence\":0.81},"
        "\"limitations\":{\"why_not_ideal\":[],\"uncertainty_reason\":null,\"requires_human_review\":false},"
        "\"overall_confidence\":0.84}"
    )
    return (
        "You are an expert bird identification assistant helping build an educational quiz app. "
        "You will receive one bird image, the expected scientific name, optional common names, "
        "and optional iNaturalist metadata. "
        "Return one strict JSON object only. Do not return markdown, comments, or any text "
        "outside JSON. "
        "Never output pipe-separated placeholders such as 'high | medium | low'. "
        "For each enum field, choose exactly one concrete value from the enum reference. "
        "Do not override the provided species and do not rename the taxon. "
        "Do not compute the final pedagogical score. "
        "Only fail when the image is clearly unusable, inaccessible, non-bird, "
        "too blurry, too occluded, "
        "or has insufficient pedagogical information. "
        "Feedback language must be French and must reference this specific image. "
        "Use formulations such as 'Sur cette image...' and avoid generic advice. "
        "Return the schema "
        "bird_image_pedagogical_review.v1.2 with prompt version bird_image_review_prompt.v1.2. "
        f"{enum_reference} "
        "Concrete JSON success example (values are examples, not placeholders): "
        f"{concrete_example} "
        f"Input context JSON: {serialized_input}"
    )


def build_failed_bird_image_review_v12(
    *,
    failure_reason: str,
    consistency_warning: str | None = None,
    diagnostics: Mapping[str, object] | None = None,
) -> dict[str, object]:
    normalized_reason = _normalize_failure_reason(failure_reason)
    payload: dict[str, object] = {
        "schema_version": BIRD_IMAGE_REVIEW_SCHEMA_VERSION,
        "prompt_version": BIRD_IMAGE_REVIEW_PROMPT_VERSION,
        "status": "failed",
        "failure_reason": normalized_reason,
        "consistency_warning": _normalize_consistency_warning(consistency_warning),
        "overall_confidence": 0,
    }
    if diagnostics:
        payload["diagnostics"] = dict(diagnostics)
    return payload


def parse_bird_image_pedagogical_review_v12(
    raw_response: str,
    *,
    gemini_model: str | None = None,
    media_id: str | None = None,
    canonical_taxon_id: str | None = None,
    scientific_name: str | None = None,
) -> dict[str, object]:
    context = _build_debug_context(
        gemini_model=gemini_model,
        media_id=media_id,
        canonical_taxon_id=canonical_taxon_id,
        scientific_name=scientific_name,
    )
    raw_debug = _raw_output_debug(raw_response)
    try:
        candidate = json.loads(raw_response)
    except json.JSONDecodeError:
        return build_failed_bird_image_review_v12(
            failure_reason="model_output_invalid",
            diagnostics=_build_failure_diagnostics(
                parsed_json_available=False,
                schema_errors=(),
                schema_failure_cause="malformed_success_failed_shape",
                raw_debug=raw_debug,
                context=context,
            ),
        )

    if not isinstance(candidate, Mapping):
        return build_failed_bird_image_review_v12(
            failure_reason="model_output_invalid",
            diagnostics=_build_failure_diagnostics(
                parsed_json_available=True,
                schema_errors=(),
                schema_failure_cause="malformed_success_failed_shape",
                raw_debug=raw_debug,
                context=context,
            ),
        )

    if _normalize_status(candidate.get("status")) == "success":
        missing_success_keys = _REQUIRED_SUCCESS_KEYS.difference(set(candidate))
        if missing_success_keys:
            schema_errors = tuple(
                {
                    "path": "<root>",
                    "message": f"Missing required field '{key}' in success payload.",
                    "validator": "required",
                    "expected": "field present",
                    "actual": "missing",
                    "cause": (
                        "missing_feedback"
                        if key == "post_answer_feedback"
                        else "missing_identification_features"
                        if key == "identification_features_visible_in_this_image"
                        else "missing_required_field"
                    ),
                }
                for key in sorted(missing_success_keys)
            )
            return build_failed_bird_image_review_v12(
                failure_reason="schema_validation_failed",
                diagnostics=_build_failure_diagnostics(
                    parsed_json_available=True,
                    schema_errors=schema_errors,
                    schema_failure_cause=_dominant_failure_cause(schema_errors),
                    raw_debug=raw_debug,
                    context=context,
                ),
            )

    normalized_payload = normalize_bird_image_pedagogical_review_v12(candidate)
    if normalized_payload.get("status") == "failed":
        existing_diagnostics = _mapping(normalized_payload.get("diagnostics"))
        if not existing_diagnostics:
            raw_status = _normalize_text(candidate.get("status"))
            if raw_status in {"failed", "fail", "error", "invalid"}:
                inferred_cause = "unknown_schema_failure"
            elif raw_status in {"success", "ok", "passed", "valid"}:
                inferred_cause = "unknown_schema_failure"
            else:
                inferred_cause = "malformed_success_failed_shape"
            normalized_payload = dict(normalized_payload)
            normalized_payload["diagnostics"] = _build_failure_diagnostics(
                parsed_json_available=True,
                schema_errors=(),
                schema_failure_cause=inferred_cause,
                raw_debug=raw_debug,
                context=context,
            )
    schema_errors = collect_schema_validation_errors_v12(normalized_payload)
    if schema_errors:
        return build_failed_bird_image_review_v12(
            failure_reason="schema_validation_failed",
            diagnostics=_build_failure_diagnostics(
                parsed_json_available=True,
                schema_errors=schema_errors,
                schema_failure_cause=_dominant_failure_cause(schema_errors),
                raw_debug=raw_debug,
                context=context,
            ),
        )

    if not is_playable_bird_image_review_v12(normalized_payload):
        if normalized_payload.get("status") == "failed":
            return normalized_payload
        return build_failed_bird_image_review_v12(
            failure_reason="insufficient_information",
            diagnostics=_build_failure_diagnostics(
                parsed_json_available=True,
                schema_errors=(),
                schema_failure_cause="missing_feedback",
                raw_debug=raw_debug,
                context=context,
            ),
        )

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
            fallback="",
            aliases={
                "bad": "low",
                "poor": "low",
                "good": "high",
                "excellent": "high",
                "none": "unusable",
            },
            strict=True,
        ),
        "subject_visibility": _normalize_choice(
            image_assessment_input.get("subject_visibility"),
            allowed={"high", "medium", "low", "none"},
            fallback="",
            aliases={
                "unseen": "none",
                "hidden": "none",
                "not_visible": "none",
            },
            strict=True,
        ),
        "sharpness": _normalize_choice(
            image_assessment_input.get("sharpness"),
            allowed={"high", "medium", "low"},
            fallback="",
            aliases={"blurry": "low", "blurred": "low", "soft": "low"},
            strict=True,
        ),
        "lighting": _normalize_choice(
            image_assessment_input.get("lighting"),
            allowed={"high", "medium", "low"},
            fallback="",
            aliases={"poor": "low", "dim": "low", "good": "high"},
            strict=True,
        ),
        "background_clutter": _normalize_choice(
            image_assessment_input.get("background_clutter"),
            allowed={"low", "medium", "high"},
            fallback="",
            aliases={"clean": "low", "busy": "high"},
            strict=True,
        ),
        "occlusion": _normalize_choice(
            image_assessment_input.get("occlusion"),
            allowed={"none", "minor", "major"},
            fallback="",
            aliases={
                "partial": "minor",
                "partially_occluded": "minor",
                "heavy": "major",
            },
            strict=True,
        ),
        "view_angle": _normalize_view_angle(image_assessment_input.get("view_angle")),
        "visible_parts": _normalize_visible_parts(image_assessment_input.get("visible_parts")),
        "confidence": _normalize_confidence(image_assessment_input.get("confidence"), default=-1.0),
    }

    pedagogical_assessment: dict[str, object] = {
        "pedagogical_quality": _normalize_choice(
            pedagogical_assessment_input.get("pedagogical_quality"),
            allowed={"high", "medium", "low"},
            fallback="",
            aliases={"good": "high", "poor": "low"},
            strict=True,
        ),
        "difficulty_level": _normalize_choice(
            pedagogical_assessment_input.get("difficulty_level"),
            allowed={"easy", "medium", "hard"},
            fallback="",
            aliases={"beginner": "easy", "advanced": "hard"},
            strict=True,
        ),
        "media_role": _normalize_choice(
            pedagogical_assessment_input.get("media_role"),
            allowed={
                "primary_identification",
                "secondary_support",
                "confusion_training",
                "not_recommended",
            },
            fallback="",
            aliases={
                "primary_id": "primary_identification",
                "context": "secondary_support",
                "distractor_risk": "confusion_training",
                "non_diagnostic": "not_recommended",
            },
            strict=True,
        ),
        "diagnostic_feature_visibility": _normalize_choice(
            pedagogical_assessment_input.get("diagnostic_feature_visibility"),
            allowed={"high", "medium", "low", "none"},
            fallback="",
            aliases={
                "unknown": "none",
                "not_visible": "none",
            },
            strict=True,
        ),
        "representativeness": _normalize_choice(
            pedagogical_assessment_input.get("representativeness"),
            allowed={"high", "medium", "low"},
            fallback="",
            aliases={"good": "high", "poor": "low"},
            strict=True,
        ),
        "learning_suitability": _normalize_choice(
            pedagogical_assessment_input.get("learning_suitability"),
            allowed={"high", "medium", "low"},
            fallback="",
            aliases={"good": "high", "poor": "low"},
            strict=True,
        ),
        "confusion_relevance": _normalize_choice(
            pedagogical_assessment_input.get("confusion_relevance"),
            allowed={"high", "medium", "low"},
            fallback="",
            aliases={
                "none": "low",
                "not_visible": "low",
            },
            strict=True,
        ),
        "confidence": _normalize_confidence(
            pedagogical_assessment_input.get("confidence"),
            default=-1.0,
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
        default=-1.0,
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
    schema_errors = collect_schema_validation_errors_v12(payload, schema_path=schema_path)
    if schema_errors:
        first_error = schema_errors[0]
        raise ValueError(
            "Bird image review v1.2 validation failed at "
            f"{first_error['path']}: {first_error['message']}"
        )

    if payload.get("status") == "failed" and payload.get("overall_confidence") != 0:
        raise ValueError("Failed bird image review payloads must set overall_confidence to 0")


def collect_schema_validation_errors_v12(
    payload: Mapping[str, object],
    *,
    schema_path: Path | None = None,
) -> tuple[dict[str, object], ...]:
    resolved_schema_path = schema_path or DEFAULT_BIRD_IMAGE_REVIEW_SCHEMA_PATH
    schema = _load_schema(resolved_schema_path)
    schema_variant = _schema_variant_for_status(schema, payload.get("status"))
    validator = Draft202012Validator(schema_variant, format_checker=FormatChecker())
    root_errors = sorted(
        validator.iter_errors(dict(payload)),
        key=lambda item: [str(path) for path in item.absolute_path],
    )
    flattened_errors: list[ValidationError] = []
    for error in root_errors:
        flattened_errors.extend(_flatten_validation_errors(error))
    ordered = sorted(
        flattened_errors,
        key=lambda item: [str(path) for path in item.absolute_path],
    )
    return tuple(_format_schema_error_details(item) for item in ordered)


def _schema_variant_for_status(
    full_schema: Mapping[str, object],
    status: object,
) -> Mapping[str, object]:
    defs = full_schema.get("$defs")
    if not isinstance(defs, Mapping):
        return full_schema

    def _with_defs(sub_schema: Mapping[str, object]) -> Mapping[str, object]:
        return {
            "$schema": full_schema.get("$schema"),
            "$defs": defs,
            **dict(sub_schema),
        }

    normalized_status = str(status or "").strip().lower()
    if normalized_status == "success":
        success_schema = defs.get("success_payload")
        if isinstance(success_schema, Mapping):
            return _with_defs(success_schema)
    if normalized_status == "failed":
        failed_schema = defs.get("failed_payload")
        if isinstance(failed_schema, Mapping):
            return _with_defs(failed_schema)
    return full_schema


def _flatten_validation_errors(error: ValidationError) -> list[ValidationError]:
    if error.context:
        flattened: list[ValidationError] = []
        for sub_error in error.context:
            flattened.extend(_flatten_validation_errors(sub_error))
        if flattened:
            return flattened
    return [error]


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
    correct_short = _non_empty(correct.get("short"))
    correct_long = _non_empty(correct.get("long"))
    incorrect_short = _non_empty(incorrect.get("short"))
    incorrect_long = _non_empty(incorrect.get("long"))

    required_feedback = (
        correct_short
        and correct_long
        and incorrect_short
        and incorrect_long
    )
    if not required_feedback or len(tips) < 2:
        return False

    if _normalize_feedback_text(correct_short) == _normalize_feedback_text(incorrect_short):
        return False
    if _normalize_feedback_text(correct_long) == _normalize_feedback_text(incorrect_long):
        return False

    feedback_texts = [correct_short, correct_long, incorrect_short, incorrect_long, *tips]
    if not _has_image_context_reference(feedback_texts):
        return False
    if not _feedback_lengths_are_acceptable(feedback_texts):
        return False
    if _count_feature_keyword_mentions(" ".join(feedback_texts)) < 2:
        return False
    if _count_concrete_tips(tips) < 2:
        return False

    return True


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


def _build_debug_context(
    *,
    gemini_model: str | None,
    media_id: str | None,
    canonical_taxon_id: str | None,
    scientific_name: str | None,
) -> dict[str, object]:
    context: dict[str, object] = {
        "prompt_version": BIRD_IMAGE_REVIEW_PROMPT_VERSION,
        "schema_version": BIRD_IMAGE_REVIEW_SCHEMA_VERSION,
    }
    if gemini_model:
        context["gemini_model"] = gemini_model
    if media_id:
        context["media_id"] = media_id
    if canonical_taxon_id:
        context["canonical_taxon_id"] = canonical_taxon_id
    if scientific_name:
        context["scientific_name"] = scientific_name
    return context


def _raw_output_debug(raw_response: str) -> dict[str, object]:
    excerpt = raw_response.strip().replace("\r", " ")
    excerpt = re.sub(r"\s+", " ", excerpt)
    excerpt = excerpt[:_MAX_RAW_EXCERPT_CHARS]
    return {
        "raw_model_output_sha256": hashlib.sha256(
            raw_response.encode("utf-8", errors="ignore")
        ).hexdigest(),
        "raw_model_output_excerpt": excerpt,
    }


def _build_failure_diagnostics(
    *,
    parsed_json_available: bool,
    schema_errors: Sequence[Mapping[str, object]],
    schema_failure_cause: str,
    raw_debug: Mapping[str, object],
    context: Mapping[str, object],
) -> dict[str, object]:
    diagnostics: dict[str, object] = {
        "parsed_json_available": bool(parsed_json_available),
        "schema_error_count": len(schema_errors),
        "schema_errors": [dict(item) for item in schema_errors],
        "schema_failure_cause": schema_failure_cause,
    }
    diagnostics.update(raw_debug)
    diagnostics.update(context)
    return diagnostics


def _format_schema_error_details(error: ValidationError) -> dict[str, object]:
    path = ".".join(str(item) for item in error.absolute_path) or "<root>"
    validator_name = str(error.validator) if error.validator is not None else None
    details: dict[str, object] = {
        "path": path,
        "message": error.message,
        "validator": validator_name,
        "cause": _classify_schema_error(error=error, path=path),
    }
    expected = _schema_expected_value(error)
    if expected is not None:
        details["expected"] = expected
    actual = _safe_actual_value(error.instance)
    if actual is not None:
        details["actual"] = actual
    return details


def _schema_expected_value(error: ValidationError) -> object:
    validator_name = str(error.validator or "")
    if validator_name == "enum":
        return list(error.validator_value)
    if validator_name == "type":
        return error.validator_value
    if validator_name == "required":
        return list(error.validator_value)
    if validator_name in {"minimum", "maximum", "minItems", "minLength", "const"}:
        return error.validator_value
    if validator_name == "additionalProperties":
        return "no additional properties"
    return None


def _safe_actual_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        text = value.strip().replace("\r", " ")
        text = re.sub(r"\s+", " ", text)
        return text[:180]
    if isinstance(value, Mapping):
        return f"<object keys={sorted(value.keys())[:10]}>"
    if isinstance(value, Sequence):
        return f"<array len={len(value)}>"
    return str(value)[:180]


def _classify_schema_error(*, error: ValidationError, path: str) -> str:
    validator_name = str(error.validator or "")
    message = str(error.message).lower()
    normalized_path = path.lower()

    if validator_name == "required":
        if "post_answer_feedback" in message or normalized_path.startswith("post_answer_feedback"):
            return "missing_feedback"
        if (
            "identification_features_visible_in_this_image" in message
            or normalized_path.startswith("identification_features_visible_in_this_image")
        ):
            return "missing_identification_features"
        return "missing_required_field"
    if validator_name == "enum":
        return "enum_mismatch"
    if validator_name == "type":
        return "wrong_type"
    if validator_name == "additionalProperties":
        return "additional_property"
    if validator_name in {"minimum", "maximum"} and "confidence" in normalized_path:
        return "invalid_confidence_range"
    if validator_name == "minItems":
        if "identification_tips" in normalized_path:
            return "missing_feedback"
        if "identification_features_visible_in_this_image" in normalized_path:
            return "missing_identification_features"
    if validator_name == "const":
        if "schema_version" in normalized_path or "prompt_version" in normalized_path:
            return "wrong_version"
        if normalized_path == "status":
            return "malformed_success_failed_shape"
    return "unknown_schema_failure"


def _dominant_failure_cause(schema_errors: Sequence[Mapping[str, object]]) -> str:
    if not schema_errors:
        return "unknown_schema_failure"
    counts: dict[str, int] = {}
    for error in schema_errors:
        cause = str(error.get("cause") or "unknown_schema_failure")
        counts[cause] = counts.get(cause, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


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
        return ""
    if text in {"side_view", "side"}:
        return "lateral"
    if "side" in text or "profile" in text or text == "lateral":
        return "lateral"
    if text in {"front_view", "front"}:
        return "frontal"
    if "front" in text:
        return "frontal"
    if text in {"back_view", "back"}:
        return "rear"
    if "rear" in text or "back" in text:
        return "rear"
    if "dors" in text or "top" in text:
        return "dorsal"
    if "ventr" in text or "under" in text or "below" in text:
        return "ventral"
    if "mixed" in text or "oblique" in text or "angle" in text:
        return "mixed"
    return text


def _normalize_visible_parts(value: object) -> list[str]:
    raw_values = _normalize_string_list(value)
    normalized = [_to_token(part) for part in raw_values]
    return [item for item in dict.fromkeys(normalized) if item]


def _normalize_identification_features(
    value: object,
    *,
    visible_parts: object,
) -> list[dict[str, object]]:
    del visible_parts
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

    return items


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
    strict: bool = False,
) -> str:
    text = _normalize_text(value)
    if not text:
        return fallback
    alias_map = {k: v for k, v in (aliases or {}).items()}
    text = alias_map.get(text, text)
    if text in allowed:
        return text
    if strict:
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
    correct_short = _non_empty(correct.get("short"))
    correct_long = _non_empty(correct.get("long"))
    incorrect_short = _non_empty(incorrect.get("short"))
    incorrect_long = _non_empty(incorrect.get("long"))

    has_required_text = (
        correct_short
        and correct_long
        and incorrect_short
        and incorrect_long
    )
    if not has_required_text or len(tips) < 2:
        return "low"

    feedback_texts = [correct_short, correct_long, incorrect_short, incorrect_long, *tips]
    if (
        not _has_image_context_reference(feedback_texts)
        or not _feedback_lengths_are_acceptable(feedback_texts)
        or _count_feature_keyword_mentions(" ".join(feedback_texts)) < 2
        or _count_concrete_tips(tips) < 2
    ):
        return "low"
    if confidence >= 0.75 and len(tips) >= 3:
        return "high"
    if confidence >= 0.40:
        return "medium"
    return "low"


def _normalize_feedback_text(value: str) -> str:
    text = value.lower()
    text = text.replace("'", " ")
    text = text.replace("-", " ")
    text = text.replace("é", "e").replace("è", "e").replace("ê", "e")
    text = text.replace("à", "a").replace("â", "a")
    text = text.replace("î", "i").replace("ï", "i")
    text = text.replace("ô", "o")
    text = text.replace("ù", "u").replace("û", "u")
    text = text.replace("ç", "c")
    return re.sub(r"\s+", " ", text).strip()


def _has_image_context_reference(texts: Sequence[str]) -> bool:
    normalized = " ".join(_normalize_feedback_text(item) for item in texts)
    return any(marker in normalized for marker in _IMAGE_CONTEXT_MARKERS)


def _feedback_lengths_are_acceptable(texts: Sequence[str]) -> bool:
    for text in texts:
        length = len(text.strip())
        if length < 8 or length > 480:
            return False
    return True


def _count_feature_keyword_mentions(text: str) -> int:
    normalized = _normalize_feedback_text(text)
    return sum(1 for keyword in _FEATURE_KEYWORDS if keyword in normalized)


def _count_concrete_tips(tips: Sequence[str]) -> int:
    return sum(
        1
        for tip in tips
        if len(tip.split()) >= 4 and _count_feature_keyword_mentions(tip) >= 1
    )


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
