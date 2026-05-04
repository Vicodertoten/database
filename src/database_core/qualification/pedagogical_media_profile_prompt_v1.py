from __future__ import annotations

import json
from collections.abc import Mapping

from database_core.qualification.pedagogical_media_profile_v1 import (
    PEDAGOGICAL_MEDIA_PROFILE_SCHEMA_VERSION,
)

PEDAGOGICAL_MEDIA_PROFILE_PROMPT_VERSION = "pedagogical_media_profile_prompt.v1"

_ORGANISM_GROUP_ENUM = [
    "bird",
    "mammal",
    "reptile",
    "amphibian",
    "fish",
    "insect",
    "arachnid",
    "mollusk",
    "plant",
    "fungus",
    "lichen",
    "unknown",
]

_EVIDENCE_TYPE_ENUM = [
    "whole_organism",
    "partial_organism",
    "feather",
    "egg",
    "nest",
    "track",
    "scat",
    "burrow",
    "habitat",
    "plant_part",
    "fungus_fruiting_body",
    "dead_organism",
    "multiple_organisms",
    "unknown",
]


def build_pedagogical_media_profile_prompt_v1(
    *,
    expected_scientific_name: str,
    organism_group: str,
    media_reference: str,
    common_names: Mapping[str, str] | None = None,
    source_metadata: Mapping[str, object] | None = None,
    observation_context: Mapping[str, object] | None = None,
    locale_notes: str | None = None,
) -> str:
    input_payload = {
        "expected_scientific_name": expected_scientific_name.strip(),
        "common_names": dict(common_names or {}),
        "organism_group": organism_group.strip(),
        "media_reference": media_reference.strip(),
        "source_metadata": dict(source_metadata or {}),
        "observation_context": dict(observation_context or {}),
        "locale_notes": (locale_notes or "").strip(),
        "contract": {
            "schema_version": PEDAGOGICAL_MEDIA_PROFILE_SCHEMA_VERSION,
            "prompt_version": PEDAGOGICAL_MEDIA_PROFILE_PROMPT_VERSION,
            "output_mode": "raw_ai_signals",
            "persisted_mode": "system_computed_scores",
        },
    }
    serialized_input = json.dumps(input_payload, ensure_ascii=True, sort_keys=True)

    organism_group_enum = ", ".join(_ORGANISM_GROUP_ENUM)
    evidence_type_enum = ", ".join(_EVIDENCE_TYPE_ENUM)

    return (
        "You are an expert naturalist media qualification assistant. "
        "Return exactly one strict JSON object and nothing else. "
        "Do not output markdown, comments, or explanatory prose. "
        "Use schema_version=pedagogical_media_profile.v1 and "
        "prompt_version=pedagogical_media_profile_prompt.v1. "
        "Database qualifies now; downstream systems select later. "
        "Review validity is separate from media usefulness. "
        "A feather, nest, track, habitat, distant organism, partial organism, or weak "
        "identification evidence can still be valid. "
        "Use review_status=failed only when media cannot be inspected or output cannot "
        "be structured. "
        "Do not compute final numeric scores. The system computes global_quality_score "
        "and usage_scores after parsing and validation. "
        "Do not generate feedback, post-answer hints, quiz or pack or runtime selection, "
        "or final usage recommendations. "
        "Forbidden fields and concepts include: feedback, identification tips, selected "
        "for quiz, palier core eligibility, recommended use, runtime readiness, playable. "
        "Do not rename, override, or correct the provided taxon. "
        "If biological attributes are uncertain, use unknown. "
        "For biological_profile_visible fields, if value is unknown or not_applicable then "
        "visible_basis may be null and confidence must be low or medium. "
        "If value is neither unknown nor not_applicable, visible_basis must be non-empty. "
        "For indirect evidence types feather, egg, nest, track, scat, burrow, set "
        "observation_profile.subject_presence=indirect. "
        f"Allowed organism_group values: [{organism_group_enum}]. "
        f"Allowed evidence_type values: [{evidence_type_enum}]. "
        "Produce the raw AI signal structure for pedagogical_media_profile.v1. "
        "Raw AI output may omit scores; persisted normalized profile must include scores "
        "computed by the system. "
        f"Input context JSON: {serialized_input}"
    )
