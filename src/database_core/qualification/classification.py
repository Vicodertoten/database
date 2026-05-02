from __future__ import annotations

from collections.abc import Mapping, Sequence

from database_core.domain.enums import (
    DiagnosticStrength,
    DifficultyBand,
    DifficultyLevel,
    MediaRole,
    ObservationKind,
    PedagogicalRole,
)
from database_core.domain.models import DerivedClassification


def derive_observation_kind(payload: object) -> ObservationKind:
    media_role = str(_field(payload, "media_role", "context"))
    uncertainty_reason = str(_field(payload, "uncertainty_reason", "none"))
    flags = set(_string_list(_field(payload, "qualification_flags", ())))
    visible_parts = set(_string_list(_field(payload, "visible_parts", ())))
    note_blob = _lower_blob(
        [
            _field(payload, "qualification_notes", ""),
            _field(payload, "life_stage", ""),
        ]
    )

    if _has_any(note_blob, ("nest", "egg", "eggs", "hatchling", "hatchlings")):
        return ObservationKind.NEST_OR_EGGS
    if _has_any(note_blob, ("feather", "dropping", "trace", "track", "footprint")):
        return ObservationKind.TRACE_OR_FEATHER
    if _has_any(note_blob, ("carcass", "dead", "corpse", "roadkill")):
        return ObservationKind.CARCASS
    if media_role in {MediaRole.CONTEXT, MediaRole.NON_DIAGNOSTIC}:
        return ObservationKind.HABITAT_CONTEXT
    if uncertainty_reason == "motion" or _has_any(note_blob, ("flight", "flying", "in_flight")):
        return ObservationKind.IN_FLIGHT
    if "missing_visible_parts" in flags or not visible_parts:
        return ObservationKind.PARTIAL
    if uncertainty_reason in {"occlusion", "distance"}:
        return ObservationKind.PARTIAL
    return ObservationKind.FULL_BIRD


def derive_diagnostic_strength(payload: object) -> DiagnosticStrength:
    visibility = str(_field(payload, "diagnostic_feature_visibility", "unknown"))
    learning_suitability = str(_field(payload, "learning_suitability", "unknown"))
    technical_quality = str(_field(payload, "technical_quality", "unknown"))
    flags = set(_string_list(_field(payload, "qualification_flags", ())))
    ai_confidence = _float_or_none(_field(payload, "ai_confidence", None))

    if visibility == "high":
        strength = DiagnosticStrength.HIGH
    elif visibility == "medium":
        strength = DiagnosticStrength.MEDIUM
    elif visibility == "low":
        strength = DiagnosticStrength.LOW
    else:
        strength = DiagnosticStrength.UNKNOWN

    if learning_suitability == "low":
        strength = _degrade_strength(strength)
    if technical_quality in {"low", "unknown"}:
        strength = _degrade_strength(strength)
    if flags.intersection(
        {"missing_visible_parts", "missing_view_angle", "insufficient_technical_quality"}
    ):
        strength = DiagnosticStrength.LOW
    if "low_ai_confidence_below_floor" in flags:
        strength = DiagnosticStrength.LOW
    if "low_ai_confidence" in flags and (ai_confidence is None or ai_confidence < 0.8):
        strength = _degrade_strength(strength)

    return strength


def derive_pedagogical_role(payload: object) -> PedagogicalRole:
    qualification_status = str(_field(payload, "qualification_status", "rejected"))
    observation_kind = derive_observation_kind(payload)
    diagnostic_strength = derive_diagnostic_strength(payload)
    media_role = str(_field(payload, "media_role", "context"))
    learning_suitability = str(_field(payload, "learning_suitability", "unknown"))
    technical_quality = str(_field(payload, "technical_quality", "unknown"))
    flags = set(_string_list(_field(payload, "qualification_flags", ())))

    if qualification_status != "accepted":
        return PedagogicalRole.EXCLUDED
    if observation_kind in {ObservationKind.CARCASS, ObservationKind.TRACE_OR_FEATHER}:
        return PedagogicalRole.FORENSICS
    if observation_kind == ObservationKind.HABITAT_CONTEXT:
        return PedagogicalRole.CONTEXT
    if media_role in {MediaRole.CONTEXT, MediaRole.NON_DIAGNOSTIC}:
        return PedagogicalRole.CONTEXT

    has_core_blocker = bool(
        flags.intersection(
            {"missing_visible_parts", "missing_view_angle", "insufficient_technical_quality"}
        )
    ) or technical_quality in {"low", "unknown"}
    if (
        diagnostic_strength == DiagnosticStrength.HIGH
        and learning_suitability in {"high", "medium"}
        and not has_core_blocker
    ):
        return PedagogicalRole.CORE_ID
    if diagnostic_strength in {DiagnosticStrength.HIGH, DiagnosticStrength.MEDIUM}:
        return PedagogicalRole.ADVANCED_ID
    if learning_suitability in {"high", "medium"}:
        return PedagogicalRole.ADVANCED_ID
    return PedagogicalRole.CONTEXT


def derive_difficulty_band(payload: object) -> DifficultyBand:
    difficulty_level = str(_field(payload, "difficulty_level", "unknown"))
    if difficulty_level == DifficultyLevel.EASY:
        return DifficultyBand.STARTER
    if difficulty_level == DifficultyLevel.MEDIUM:
        return DifficultyBand.INTERMEDIATE
    if difficulty_level == DifficultyLevel.HARD:
        return DifficultyBand.EXPERT
    return DifficultyBand.UNKNOWN


def derive_minimal_classification(payload: object) -> DerivedClassification:
    return DerivedClassification(
        observation_kind=derive_observation_kind(payload),
        diagnostic_strength=derive_diagnostic_strength(payload),
        pedagogical_role=derive_pedagogical_role(payload),
        difficulty_band=derive_difficulty_band(payload),
    )


def _field(payload: object, key: str, default: object = None) -> object:
    if isinstance(payload, Mapping):
        return payload.get(key, default)
    return getattr(payload, key, default)


def _string_list(value: object) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [str(item).strip().lower() for item in value if str(item).strip()]
    return []


def _lower_blob(values: Sequence[object]) -> str:
    parts = [str(item).strip().lower() for item in values if str(item).strip()]
    return " ".join(parts)


def _has_any(text: str, tokens: Sequence[str]) -> bool:
    return any(token in text for token in tokens)


def _degrade_strength(value: DiagnosticStrength) -> DiagnosticStrength:
    if value == DiagnosticStrength.HIGH:
        return DiagnosticStrength.MEDIUM
    if value == DiagnosticStrength.MEDIUM:
        return DiagnosticStrength.LOW
    return value


def _float_or_none(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
