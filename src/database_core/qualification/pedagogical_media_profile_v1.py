from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

PEDAGOGICAL_MEDIA_PROFILE_SCHEMA_VERSION = "pedagogical_media_profile.v1"

DEFAULT_PEDAGOGICAL_MEDIA_PROFILE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "pedagogical_media_profile_v1.schema.json"
)

PEDAGOGICAL_MEDIA_PROFILE_FAILURE_REASONS = (
    "model_output_invalid",
    "schema_validation_failed",
    "media_not_accessible",
    "unsafe_or_invalid_content",
    "empty_model_output",
    "media_uninspectable",
    "unknown_failure",
)

SIGNAL_SCORE = {
    "high": 100,
    "medium": 70,
    "low": 35,
    "none": 0,
    "unknown": 20,
}

TECHNICAL_QUALITY_SCORE = {
    "high": 100,
    "medium": 70,
    "low": 35,
    "unusable": 0,
    "unknown": 20,
}

SUBJECT_PRESENCE_SCORE = {
    "clear": 100,
    "partial": 70,
    "indirect": 55,
    "absent": 5,
    "unknown": 20,
}

AMBIGUITY_CONFUSION_SCORE = {
    "low": 35,
    "medium": 70,
    "high": 90,
    "unknown": 40,
}

PRIOR_KNOWLEDGE_SCORE = {
    "high": 90,
    "medium": 70,
    "low": 45,
    "none": 20,
    "unknown": 40,
}

EVIDENCE_BASIC_IDENTIFICATION_MULTIPLIER = {
    "whole_organism": 1.0,
    "partial_organism": 0.7,
    "feather": 0.25,
    "egg": 0.25,
    "nest": 0.2,
    "track": 0.2,
    "scat": 0.15,
    "burrow": 0.15,
    "habitat": 0.1,
    "plant_part": 0.35,
    "fungus_fruiting_body": 0.45,
    "dead_organism": 0.65,
    "multiple_organisms": 0.6,
    "unknown": 0.4,
}

EVIDENCE_FIELD_OBSERVATION_MULTIPLIER = {
    "whole_organism": 1.0,
    "partial_organism": 0.95,
    "feather": 0.8,
    "egg": 0.85,
    "nest": 0.95,
    "track": 0.95,
    "scat": 0.85,
    "burrow": 0.9,
    "habitat": 1.0,
    "plant_part": 0.85,
    "fungus_fruiting_body": 0.85,
    "dead_organism": 0.8,
    "multiple_organisms": 0.9,
    "unknown": 0.8,
}

EVIDENCE_CONFUSION_LEARNING_MULTIPLIER = {
    "whole_organism": 1.0,
    "partial_organism": 0.8,
    "feather": 0.45,
    "egg": 0.4,
    "nest": 0.3,
    "track": 0.45,
    "scat": 0.25,
    "burrow": 0.25,
    "habitat": 0.2,
    "plant_part": 0.5,
    "fungus_fruiting_body": 0.55,
    "dead_organism": 0.6,
    "multiple_organisms": 0.75,
    "unknown": 0.4,
}

EVIDENCE_MORPHOLOGY_LEARNING_MULTIPLIER = {
    "whole_organism": 1.0,
    "partial_organism": 0.85,
    "feather": 1.0,
    "egg": 0.85,
    "nest": 0.6,
    "track": 0.75,
    "scat": 0.5,
    "burrow": 0.5,
    "habitat": 0.4,
    "plant_part": 1.0,
    "fungus_fruiting_body": 1.0,
    "dead_organism": 0.8,
    "multiple_organisms": 0.8,
    "unknown": 0.6,
}

EVIDENCE_SPECIES_CARD_MULTIPLIER = {
    "whole_organism": 1.0,
    "partial_organism": 0.65,
    "feather": 0.35,
    "egg": 0.3,
    "nest": 0.25,
    "track": 0.2,
    "scat": 0.15,
    "burrow": 0.15,
    "habitat": 0.2,
    "plant_part": 0.6,
    "fungus_fruiting_body": 0.65,
    "dead_organism": 0.5,
    "multiple_organisms": 0.5,
    "unknown": 0.4,
}

EVIDENCE_INDIRECT_LEARNING_RELEVANCE = {
    "whole_organism": 0,
    "partial_organism": 20,
    "feather": 90,
    "egg": 85,
    "nest": 85,
    "track": 90,
    "scat": 90,
    "burrow": 90,
    "habitat": 80,
    "plant_part": 75,
    "fungus_fruiting_body": 75,
    "dead_organism": 65,
    "multiple_organisms": 40,
    "unknown": 30,
}

_BIOLOGICAL_PROFILE_FIELDS = (
    "sex",
    "life_stage",
    "plumage_state",
    "seasonal_state",
)

_INDIRECT_EVIDENCE_TYPES = {
    "feather",
    "egg",
    "nest",
    "track",
    "scat",
    "burrow",
}

_MAX_RAW_EXCERPT_CHARS = 1200


def build_failed_pedagogical_media_profile_v1(
    *,
    failure_reason: str,
    diagnostics: Mapping[str, object] | None = None,
) -> dict[str, object]:
    normalized_reason = _normalize_failure_reason_for_output(failure_reason)
    payload: dict[str, object] = {
        "schema_version": PEDAGOGICAL_MEDIA_PROFILE_SCHEMA_VERSION,
        "review_status": "failed",
        "failure_reason": normalized_reason,
    }
    if diagnostics:
        payload["diagnostics"] = dict(diagnostics)
    return payload


def parse_pedagogical_media_profile_v1(
    raw_response: str,
    *,
    schema_path: Path | None = None,
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
        return build_failed_pedagogical_media_profile_v1(
            failure_reason="model_output_invalid",
            diagnostics=_build_failure_diagnostics(
                parsed_json_available=False,
                schema_errors=(),
                schema_failure_cause="malformed_valid_failed_shape",
                raw_debug=raw_debug,
                context=context,
            ),
        )

    if not isinstance(candidate, Mapping):
        return build_failed_pedagogical_media_profile_v1(
            failure_reason="model_output_invalid",
            diagnostics=_build_failure_diagnostics(
                parsed_json_available=True,
                schema_errors=(),
                schema_failure_cause="malformed_valid_failed_shape",
                raw_debug=raw_debug,
                context=context,
            ),
        )

    normalized_payload = normalize_pedagogical_media_profile_v1(candidate)
    if _normalize_text(normalized_payload.get("review_status")) == "valid":
        normalized_payload = dict(normalized_payload)
        normalized_payload["scores"] = compute_pedagogical_media_scores_v1(normalized_payload)

    schema_errors = collect_schema_validation_errors_pmp_v1(
        normalized_payload,
        schema_path=schema_path,
    )
    if schema_errors:
        return build_failed_pedagogical_media_profile_v1(
            failure_reason="schema_validation_failed",
            diagnostics=_build_failure_diagnostics(
                parsed_json_available=True,
                schema_errors=schema_errors,
                schema_failure_cause=_dominant_failure_cause(schema_errors),
                raw_debug=raw_debug,
                context=context,
            ),
        )

    return normalized_payload


def normalize_pedagogical_media_profile_v1(
    candidate: Mapping[str, object],
) -> dict[str, object]:
    normalized = _trim_strings(candidate)

    review_status = _normalize_known_token(
        normalized.get("review_status"),
        allowed={"valid", "failed"},
    )
    if review_status is not None:
        normalized["review_status"] = review_status

    failure_reason = _normalize_known_token(
        normalized.get("failure_reason"),
        allowed=set(PEDAGOGICAL_MEDIA_PROFILE_FAILURE_REASONS),
    )
    if failure_reason is not None:
        normalized["failure_reason"] = failure_reason

    _normalize_number_field(normalized, "review_confidence")

    technical_profile = _mapping(normalized.get("technical_profile"))
    _normalize_known_enum_field(
        technical_profile,
        "technical_quality",
        {"high", "medium", "low", "unusable", "unknown"},
    )
    _normalize_known_enum_field(
        technical_profile,
        "sharpness",
        {"high", "medium", "low", "unknown"},
    )
    _normalize_known_enum_field(
        technical_profile,
        "lighting",
        {"high", "medium", "low", "unknown"},
    )
    _normalize_known_enum_field(
        technical_profile,
        "contrast",
        {"high", "medium", "low", "unknown"},
    )
    _normalize_known_enum_field(
        technical_profile,
        "background_clutter",
        {"low", "medium", "high", "unknown"},
    )
    _normalize_known_enum_field(
        technical_profile,
        "framing",
        {"good", "acceptable", "poor", "unknown"},
    )
    _normalize_known_enum_field(
        technical_profile,
        "distance_to_subject",
        {"close", "medium", "far", "very_far", "unknown"},
    )

    observation_profile = _mapping(normalized.get("observation_profile"))
    _normalize_known_enum_field(
        observation_profile,
        "subject_presence",
        {"clear", "partial", "indirect", "absent", "unknown"},
    )
    _normalize_known_enum_field(
        observation_profile,
        "subject_visibility",
        {"high", "medium", "low", "none", "unknown"},
    )
    _normalize_known_enum_field(
        observation_profile,
        "view_angle",
        {"lateral", "frontal", "rear", "dorsal", "ventral", "mixed", "unknown"},
    )
    _normalize_known_enum_field(
        observation_profile,
        "occlusion",
        {"none", "minor", "major", "unknown"},
    )
    _normalize_context_visible_aliases(observation_profile)
    _normalize_string_enum_list(
        observation_profile,
        "context_visible",
        {"water", "vegetation", "tree", "reedbed", "ground", "sky",
         "urban", "snow", "rock", "dead_wood", "human_structure", "unknown"},
    )

    identification_profile = _mapping(normalized.get("identification_profile"))
    _normalize_known_enum_field(
        identification_profile,
        "visual_evidence_strength",
        {"high", "medium", "low", "none", "unknown"},
    )
    _normalize_known_enum_field(
        identification_profile,
        "diagnostic_feature_visibility",
        {"high", "medium", "low", "none", "unknown"},
    )
    _normalize_known_enum_field(
        identification_profile,
        "identification_confidence_from_image",
        {"high", "medium", "low", "none", "unknown"},
    )
    _normalize_known_enum_field(
        identification_profile,
        "ambiguity_level",
        {"low", "medium", "high", "unknown"},
    )

    pedagogical_profile = _mapping(normalized.get("pedagogical_profile"))
    _normalize_known_enum_field(
        pedagogical_profile,
        "learning_value",
        {"high", "medium", "low", "none", "unknown"},
    )
    _normalize_known_enum_field(
        pedagogical_profile,
        "field_realism",
        {"high", "medium", "low", "none", "unknown"},
    )
    _normalize_known_enum_field(
        pedagogical_profile,
        "beginner_accessibility",
        {"high", "medium", "low", "none", "unknown"},
    )
    _normalize_known_enum_field(
        pedagogical_profile,
        "requires_prior_knowledge",
        {"high", "medium", "low", "none", "unknown"},
    )
    _normalize_known_enum_field(
        pedagogical_profile,
        "difficulty",
        {"easy", "medium", "hard", "unknown"},
    )
    _normalize_known_enum_field(
        pedagogical_profile,
        "expert_interest",
        {"high", "medium", "low", "none", "unknown"},
    )
    _normalize_known_enum_field(
        pedagogical_profile,
        "cognitive_load",
        {"high", "medium", "low", "none", "unknown"},
    )

    biological_profile_visible = _mapping(normalized.get("biological_profile_visible"))
    _normalize_biological_attribute(
        biological_profile_visible,
        "sex",
        {"male", "female", "unknown", "not_applicable"},
    )
    _normalize_biological_attribute(
        biological_profile_visible,
        "life_stage",
        {"egg", "juvenile", "adult", "unknown", "not_applicable"},
    )
    _normalize_biological_attribute(
        biological_profile_visible,
        "plumage_state",
        {
            "breeding_plumage", "non_breeding_plumage", "eclipse_plumage",
            "juvenile_plumage", "unknown", "not_applicable",
        },
    )
    _normalize_biological_attribute(
        biological_profile_visible,
        "seasonal_state",
        {
            "breeding_season", "non_breeding_season", "migration_period",
            "wintering", "unknown", "not_applicable",
        },
    )

    group_specific_profile = _mapping(normalized.get("group_specific_profile"))
    bird_profile = _mapping(group_specific_profile.get("bird"))
    if bird_profile:
        _normalize_known_enum_field(
            bird_profile,
            "posture",
            {"perched", "standing", "swimming", "flying", "foraging", "resting", "unknown"},
        )
        _normalize_known_enum_field(
            bird_profile,
            "behavior_visible",
            {"foraging", "swimming", "flying", "perched",
               "singing", "feeding_young", "resting", "bathing", "unknown"},
        )
        _normalize_string_enum_list(
            bird_profile,
            "bird_visible_parts",
            {"head", "beak", "eye", "neck", "breast", "belly", "back",
             "wing", "tail", "legs", "feet", "whole_body", "unknown"},
        )
        for _bird_visibility_field in (
            "plumage_pattern_visible", "bill_shape_visible",
            "wing_pattern_visible", "tail_shape_visible",
        ):
            _normalize_known_enum_field(
                bird_profile,
                _bird_visibility_field,
                {"high", "medium", "low", "none", "unknown"},
            )

    visible_field_marks = identification_profile.get("visible_field_marks")
    if isinstance(visible_field_marks, Sequence) and not isinstance(
        visible_field_marks,
        (str, bytes),
    ):
        for item in visible_field_marks:
            if isinstance(item, Mapping):
                _normalize_number_field(item, "confidence")
                _normalize_known_enum_field(
                    item,  # type: ignore[arg-type]
                    "visibility",
                    {"high", "medium", "low", "unknown"},
                )
                _normalize_known_enum_field(
                    item,  # type: ignore[arg-type]
                    "importance",
                    {"high", "medium", "low", "unknown"},
                )
                _normalize_known_enum_field(
                    item,  # type: ignore[arg-type]
                    "body_part",
                    {
                        "head", "beak", "eye", "neck", "breast", "belly", "back", "wing", "tail",
                        "legs", "feet", "whole_body", "feather", "egg", "nest", "track",
                        "scat", "habitat", "leaf", "flower", "stem", "cap", "gills",
                        "stipe", "unknown",
                    },
                )

    return normalized


def validate_pedagogical_media_profile_v1(
    payload: Mapping[str, object],
    *,
    schema_path: Path | None = None,
) -> None:
    schema_errors = collect_schema_validation_errors_pmp_v1(payload, schema_path=schema_path)
    if schema_errors:
        first_error = schema_errors[0]
        raise ValueError(
            "Pedagogical media profile v1 validation failed at "
            f"{first_error['path']}: {first_error['message']}"
        )


def collect_schema_validation_errors_pmp_v1(
    payload: Mapping[str, object],
    *,
    schema_path: Path | None = None,
) -> tuple[dict[str, object], ...]:
    resolved_schema_path = schema_path or DEFAULT_PEDAGOGICAL_MEDIA_PROFILE_SCHEMA_PATH
    schema = _load_schema(resolved_schema_path)
    schema_variant = _schema_variant_for_review_status(schema, payload.get("review_status"))
    validator = Draft202012Validator(schema_variant, format_checker=FormatChecker())
    root_errors = sorted(
        validator.iter_errors(dict(payload)),
        key=lambda item: [str(path) for path in item.absolute_path],
    )
    flattened_errors: list[ValidationError] = []
    for error in root_errors:
        flattened_errors.extend(_flatten_validation_errors(error))
    ordered_errors = sorted(
        flattened_errors,
        key=lambda item: [str(path) for path in item.absolute_path],
    )
    formatted_errors = [_format_schema_error_details(item) for item in ordered_errors]
    formatted_errors.extend(_collect_biological_consistency_errors(payload))
    formatted_errors.extend(_collect_cross_field_consistency_errors(payload))
    return tuple(formatted_errors)


def compute_pedagogical_media_scores_v1(payload: Mapping[str, object]) -> dict[str, object]:
    # v1 scoring is intentionally heuristic and should be calibrated after fixture audits
    # and controlled live mini-runs.
    if _normalize_text(payload.get("review_status")) != "valid":
        return {
            "global_quality_score": 0,
            "usage_scores": {
                "basic_identification": 0,
                "field_observation": 0,
                "confusion_learning": 0,
                "morphology_learning": 0,
                "species_card": 0,
                "indirect_evidence_learning": 0,
            },
        }

    technical_profile = _mapping(payload.get("technical_profile"))
    observation_profile = _mapping(payload.get("observation_profile"))
    identification_profile = _mapping(payload.get("identification_profile"))
    pedagogical_profile = _mapping(payload.get("pedagogical_profile"))

    evidence_type = _normalize_text(payload.get("evidence_type"))
    review_confidence = _normalize_probability(payload.get("review_confidence"), default=0.0)

    technical_quality = _score_lookup(
        technical_profile.get("technical_quality"),
        TECHNICAL_QUALITY_SCORE,
    )
    subject_visibility = _score_lookup(
        observation_profile.get("subject_visibility"),
        SIGNAL_SCORE,
    )
    subject_presence = _score_lookup(
        observation_profile.get("subject_presence"),
        SUBJECT_PRESENCE_SCORE,
    )
    subject_evidence_visibility = int(round(0.6 * subject_visibility + 0.4 * subject_presence))

    visual_evidence_strength = _score_lookup(
        identification_profile.get("visual_evidence_strength"),
        SIGNAL_SCORE,
    )
    learning_value = _score_lookup(
        pedagogical_profile.get("learning_value"),
        SIGNAL_SCORE,
    )
    field_marks_quality = _field_marks_quality_score(identification_profile)
    identification_confidence = _score_lookup(
        identification_profile.get("identification_confidence_from_image"),
        SIGNAL_SCORE,
    )
    reliability_confidence = int(
        round((review_confidence * 100.0 * 0.7) + (identification_confidence * 0.3))
    )

    global_quality_score = _clamp_score(
        (0.20 * technical_quality)
        + (0.20 * subject_evidence_visibility)
        + (0.25 * visual_evidence_strength)
        + (0.15 * learning_value)
        + (0.10 * field_marks_quality)
        + (0.10 * reliability_confidence)
    )

    diagnostic_visibility = _score_lookup(
        identification_profile.get("diagnostic_feature_visibility"),
        SIGNAL_SCORE,
    )
    field_realism = _score_lookup(pedagogical_profile.get("field_realism"), SIGNAL_SCORE)
    beginner_accessibility = _score_lookup(
        pedagogical_profile.get("beginner_accessibility"),
        SIGNAL_SCORE,
    )
    prior_knowledge = _score_lookup(
        pedagogical_profile.get("requires_prior_knowledge"),
        PRIOR_KNOWLEDGE_SCORE,
    )
    ambiguity = _score_lookup(
        identification_profile.get("ambiguity_level"),
        AMBIGUITY_CONFUSION_SCORE,
    )

    visible_parts = _normalize_string_list(observation_profile.get("visible_parts"))
    group_specific_profile = _mapping(payload.get("group_specific_profile"))
    bird_profile = _mapping(group_specific_profile.get("bird"))
    bird_visible_parts = _normalize_string_list(bird_profile.get("bird_visible_parts"))
    visible_parts_count = min(max(len(visible_parts), len(bird_visible_parts)), 8)
    visible_parts_score = int(round((visible_parts_count / 8) * 100))

    basic_identification_base = (
        (0.30 * visual_evidence_strength)
        + (0.20 * diagnostic_visibility)
        + (0.15 * identification_confidence)
        + (0.15 * field_marks_quality)
        + (0.10 * technical_quality)
        + (0.10 * subject_evidence_visibility)
    )
    basic_identification = _clamp_score(
        basic_identification_base
        * EVIDENCE_BASIC_IDENTIFICATION_MULTIPLIER.get(evidence_type, 0.4)
    )

    field_observation_base = (
        (0.30 * subject_evidence_visibility)
        + (0.25 * field_realism)
        + (0.20 * technical_quality)
        + (0.10 * learning_value)
        + (0.10 * identification_confidence)
        + (0.05 * reliability_confidence)
    )
    field_observation = _clamp_score(
        field_observation_base * EVIDENCE_FIELD_OBSERVATION_MULTIPLIER.get(evidence_type, 0.8)
    )

    confusion_learning_base = (
        (0.30 * diagnostic_visibility)
        + (0.25 * field_marks_quality)
        + (0.20 * visual_evidence_strength)
        + (0.15 * ambiguity)
        + (0.10 * prior_knowledge)
    )
    confusion_learning = _clamp_score(
        confusion_learning_base * EVIDENCE_CONFUSION_LEARNING_MULTIPLIER.get(evidence_type, 0.4)
    )

    morphology_learning_base = (
        (0.25 * subject_evidence_visibility)
        + (0.25 * learning_value)
        + (0.20 * visible_parts_score)
        + (0.15 * field_marks_quality)
        + (0.15 * technical_quality)
    )
    morphology_learning = _clamp_score(
        morphology_learning_base * EVIDENCE_MORPHOLOGY_LEARNING_MULTIPLIER.get(evidence_type, 0.6)
    )

    species_card_base = (
        (0.35 * technical_quality)
        + (0.25 * visual_evidence_strength)
        + (0.20 * subject_evidence_visibility)
        + (0.10 * field_marks_quality)
        + (0.10 * beginner_accessibility)
    )
    species_card = _clamp_score(
        species_card_base * EVIDENCE_SPECIES_CARD_MULTIPLIER.get(evidence_type, 0.4)
    )

    indirect_relevance = EVIDENCE_INDIRECT_LEARNING_RELEVANCE.get(evidence_type, 30)
    if indirect_relevance == 0:
        indirect_evidence_learning = 0
    else:
        indirect_evidence_learning = _clamp_score(
            (0.55 * indirect_relevance)
            + (0.15 * learning_value)
            + (0.10 * field_realism)
            + (0.10 * technical_quality)
            + (0.10 * prior_knowledge)
        )

    return {
        "global_quality_score": global_quality_score,
        "usage_scores": {
            "basic_identification": basic_identification,
            "field_observation": field_observation,
            "confusion_learning": confusion_learning,
            "morphology_learning": morphology_learning,
            "species_card": species_card,
            "indirect_evidence_learning": indirect_evidence_learning,
        },
    }


def is_valid_pedagogical_media_profile_v1(
    payload: Mapping[str, object],
    *,
    schema_path: Path | None = None,
) -> bool:
    try:
        validate_pedagogical_media_profile_v1(payload, schema_path=schema_path)
    except ValueError:
        return False
    return True


def _schema_variant_for_review_status(
    full_schema: Mapping[str, object],
    review_status: object,
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

    normalized_status = _normalize_text(review_status)
    if normalized_status == "valid":
        valid_schema = defs.get("valid_payload")
        if isinstance(valid_schema, Mapping):
            return _with_defs(valid_schema)
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
    if validator_name in {"minimum", "maximum", "minItems", "maxItems", "minLength", "const"}:
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
    normalized_path = path.lower()

    if validator_name == "required":
        return "missing_required_field"
    if validator_name == "enum":
        return "enum_mismatch"
    if validator_name == "type":
        return "wrong_type"
    if validator_name == "additionalProperties":
        return "additional_property"
    if validator_name in {"minimum", "maximum"} and "confidence" in normalized_path:
        return "invalid_confidence_range"
    if validator_name == "const":
        if "schema_version" in normalized_path:
            return "wrong_version"
        if "review_status" in normalized_path:
            return "malformed_valid_failed_shape"
    return "unknown_schema_failure"


def _collect_biological_consistency_errors(
    payload: Mapping[str, object],
) -> tuple[dict[str, object], ...]:
    if _normalize_text(payload.get("review_status")) != "valid":
        return ()

    biological_profile = _mapping(payload.get("biological_profile_visible"))
    errors: list[dict[str, object]] = []
    for field_name in _BIOLOGICAL_PROFILE_FIELDS:
        field_payload = _mapping(biological_profile.get(field_name))
        if not field_payload:
            continue

        value = _normalize_text(field_payload.get("value"))
        confidence = _normalize_text(field_payload.get("confidence"))
        visible_basis = field_payload.get("visible_basis")

        if value in {"unknown", "not_applicable"}:
            if confidence not in {"low", "medium"}:
                errors.append(
                    {
                        "path": f"biological_profile_visible.{field_name}.confidence",
                        "message": (
                            "confidence must be low or medium when value is unknown "
                            "or not_applicable"
                        ),
                        "validator": "biological_rule",
                        "expected": ["low", "medium"],
                        "actual": confidence,
                        "cause": "invalid_confidence_range",
                    }
                )
            continue

        if value:
            if _non_empty(visible_basis) is None:
                errors.append(
                    {
                        "path": f"biological_profile_visible.{field_name}.visible_basis",
                        "message": (
                            "visible_basis must be non-empty when value is neither unknown "
                            "nor not_applicable"
                        ),
                        "validator": "biological_rule",
                        "expected": "non-empty string",
                        "actual": _safe_actual_value(visible_basis),
                        "cause": "invalid_biological_basis",
                    }
                )

    return tuple(errors)


def _collect_cross_field_consistency_errors(
    payload: Mapping[str, object],
) -> tuple[dict[str, object], ...]:
    if _normalize_text(payload.get("review_status")) != "valid":
        return ()

    errors: list[dict[str, object]] = []

    organism_group = _normalize_text(payload.get("organism_group"))
    evidence_type = _normalize_text(payload.get("evidence_type"))
    observation_profile = _mapping(payload.get("observation_profile"))
    subject_presence = _normalize_text(observation_profile.get("subject_presence"))
    group_specific_profile = _mapping(payload.get("group_specific_profile"))

    if organism_group == "bird" and not isinstance(group_specific_profile.get("bird"), Mapping):
        errors.append(
            {
                "path": "group_specific_profile.bird",
                "message": "group_specific_profile.bird is required when organism_group is bird",
                "validator": "consistency_rule",
                "expected": "object",
                "actual": _safe_actual_value(group_specific_profile.get("bird")),
                "cause": "missing_required_field",
            }
        )

    if evidence_type in _INDIRECT_EVIDENCE_TYPES and subject_presence != "indirect":
        errors.append(
            {
                "path": "observation_profile.subject_presence",
                "message": (
                    "subject_presence must be indirect for indirect evidence types "
                    "(feather, egg, nest, track, scat, burrow)"
                ),
                "validator": "consistency_rule",
                "expected": "indirect",
                "actual": subject_presence,
                "cause": "enum_mismatch",
            }
        )

    return tuple(errors)


def _dominant_failure_cause(schema_errors: Sequence[Mapping[str, object]]) -> str:
    if not schema_errors:
        return "unknown_schema_failure"
    counts: dict[str, int] = {}
    for error in schema_errors:
        cause = str(error.get("cause") or "unknown_schema_failure")
        counts[cause] = counts.get(cause, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _build_debug_context(
    *,
    gemini_model: str | None,
    media_id: str | None,
    canonical_taxon_id: str | None,
    scientific_name: str | None,
) -> dict[str, object]:
    context: dict[str, object] = {
        "schema_version": PEDAGOGICAL_MEDIA_PROFILE_SCHEMA_VERSION,
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


def _score_lookup(value: object, mapping: Mapping[str, int], *, default: int = 0) -> int:
    return int(mapping.get(_normalize_text(value), default))


def _field_marks_quality_score(identification_profile: Mapping[str, object]) -> int:
    raw_items = identification_profile.get("visible_field_marks")
    if not isinstance(raw_items, Sequence) or isinstance(raw_items, (str, bytes)):
        return 0

    scores: list[float] = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        visibility_score = _score_lookup(item.get("visibility"), SIGNAL_SCORE)
        importance_score = _score_lookup(item.get("importance"), SIGNAL_SCORE)
        confidence = _normalize_probability(item.get("confidence"), default=0.0)
        scores.append(
            (0.45 * visibility_score)
            + (0.35 * importance_score)
            + (0.20 * confidence * 100)
        )

    if not scores:
        return 0
    return _clamp_score(sum(scores) / len(scores))


def _clamp_score(value: float | int) -> int:
    score = int(round(float(value)))
    if score < 0:
        return 0
    if score > 100:
        return 100
    return score


def _normalize_probability(value: object, *, default: float) -> float:
    if value is None:
        return default
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if numeric < 0 or numeric > 1:
        return default
    return numeric


def _trim_strings(value: Mapping[str, object]) -> dict[str, object]:
    def _normalize(node: object) -> object:
        if isinstance(node, Mapping):
            return {key: _normalize(item) for key, item in node.items()}
        if isinstance(node, Sequence) and not isinstance(node, (str, bytes)):
            return [_normalize(item) for item in node]
        if isinstance(node, str):
            return node.strip()
        return node

    normalized = _normalize(value)
    if isinstance(normalized, Mapping):
        return dict(normalized)
    return {}


def _normalize_known_enum_field(
    mapping: Mapping[str, object],
    key: str,
    allowed: set[str],
) -> None:
    normalized = _normalize_known_token(mapping.get(key), allowed=allowed)
    if normalized is not None:
        try:
            mapping[key] = normalized
        except TypeError:
            # Mapping may be read-only; normalization is best-effort.
            return


def _normalize_number_field(mapping: Mapping[str, object], key: str) -> None:
    value = mapping.get(key)
    if value is None:
        return
    try:
        normalized_value: float | int
        if isinstance(value, int):
            normalized_value = value
        else:
            normalized_value = float(value)
    except (TypeError, ValueError):
        return
    try:
        mapping[key] = normalized_value
    except TypeError:
        return


def _normalize_known_token(value: object, *, allowed: set[str]) -> str | None:
    if value is None:
        return None
    normalized = _normalize_text(value)
    if not normalized:
        return None
    if normalized in allowed:
        return normalized
    return None


def _normalize_failure_reason_for_output(value: object) -> str:
    normalized = _normalize_known_token(
        value,
        allowed=set(PEDAGOGICAL_MEDIA_PROFILE_FAILURE_REASONS),
    )
    if normalized:
        return normalized
    return "unknown_failure"


def _normalize_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        items = [str(item).strip() for item in value]
    else:
        items = [str(value).strip()]
    return [item for item in items if item]


def _normalize_string_enum_list(
    mapping: Mapping[str, object],
    key: str,
    allowed: set[str],
) -> None:
    raw = mapping.get(key)
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return
    normalized: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            normalized.append(item)  # type: ignore[arg-type]
            continue
        lowered = _normalize_text(item)
        normalized.append(lowered if lowered in allowed else item.strip())
    try:
        mapping[key] = normalized  # type: ignore[index]
    except TypeError:
        pass


def _normalize_context_visible_aliases(observation_profile: Mapping[str, object]) -> None:
    raw = observation_profile.get("context_visible")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return
    aliases = {
        "brick_wall": "human_structure",
        "wall": "human_structure",
        "building": "human_structure",
        "fence": "human_structure",
    }
    normalized: list[object] = []
    for item in raw:
        if not isinstance(item, str):
            normalized.append(item)
            continue
        token = _normalize_text(item)
        normalized.append(aliases.get(token, item))
    try:
        observation_profile["context_visible"] = normalized  # type: ignore[index]
    except TypeError:
        pass


def _normalize_biological_attribute(
    biological_profile: Mapping[str, object],
    field_name: str,
    allowed_values: set[str],
) -> None:
    field = _mapping(biological_profile.get(field_name))
    if not field:
        return
    _normalize_known_enum_field(field, "value", allowed_values)
    _normalize_known_enum_field(field, "confidence", {"high", "medium", "low", "unknown"})
    # Micro-patch: value=unknown/not_applicable + confidence=unknown → normalize to "low".
    # The model conservatively sets value="unknown" but then mirrors that with
    # confidence="unknown", which fails the biological consistency rule
    # (confidence must be low or medium when value is unknown/not_applicable).
    # Mapping confidence="unknown" → "low" is safe: it makes the assertion weaker,
    # not stronger, and does not imply a concrete biological claim.
    value_raw = _normalize_text(field.get("value"))
    confidence_raw = _normalize_text(field.get("confidence"))
    if value_raw in {"unknown", "not_applicable"} and confidence_raw == "unknown":
        try:
            field["confidence"] = "low"
        except TypeError:
            pass


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


@lru_cache(maxsize=2)
def _load_schema(schema_path: Path) -> dict[str, object]:
    return json.loads(schema_path.read_text(encoding="utf-8"))
