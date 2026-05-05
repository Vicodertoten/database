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

# Explicit enum sets used in prompt text (mirrors schema exactly).
_SIGNAL_LEVEL = "high|medium|low|unknown"
_SIGNAL_LEVEL_WITH_NONE = "high|medium|low|none|unknown"

_TECHNICAL_QUALITY_ENUM = "high|medium|low|unusable|unknown"
_BACKGROUND_CLUTTER_ENUM = "low|medium|high|unknown"
_FRAMING_ENUM = "good|acceptable|poor|unknown"
_DISTANCE_ENUM = "close|medium|far|very_far|unknown"
_VIEW_ANGLE_ENUM = "lateral|frontal|rear|dorsal|ventral|mixed|unknown"
_OCCLUSION_ENUM = "none|minor|major|unknown"
_CONTEXT_VISIBLE_ENUM = (
    "water|vegetation|tree|reedbed|ground|sky|urban|snow|rock|dead_wood|human_structure|unknown"
)

_SEX_VALUE_ENUM = "male|female|unknown|not_applicable"
_LIFE_STAGE_VALUE_ENUM = "egg|juvenile|adult|unknown|not_applicable"
_PLUMAGE_STATE_VALUE_ENUM = (
    "breeding_plumage|non_breeding_plumage|eclipse_plumage|juvenile_plumage"
    "|unknown|not_applicable"
)
_SEASONAL_STATE_VALUE_ENUM = (
    "breeding_season|non_breeding_season|migration_period|wintering|unknown|not_applicable"
)
_BIO_CONFIDENCE_ENUM = "high|medium|low|unknown"

_AMBIGUITY_ENUM = "low|medium|high|unknown"
_FIELD_MARK_BODY_PART_ENUM = (
    "head|beak|eye|neck|breast|belly|back|wing|tail|legs|feet|whole_body"
    "|feather|egg|nest|track|scat|habitat|leaf|flower|stem|cap|gills|stipe|unknown"
)

_DIFFICULTY_ENUM = "easy|medium|hard|unknown"

_BIRD_POSTURE_ENUM = "perched|standing|swimming|flying|foraging|resting|unknown"
_BIRD_BEHAVIOR_ENUM = (
    "foraging|swimming|flying|perched|singing|feeding_young|resting|bathing|unknown"
)
_BIRD_VISIBLE_PARTS_ENUM = (
    "head|beak|eye|neck|breast|belly|back|wing|tail|legs|feet|whole_body|unknown"
)

# Output skeleton — all raw AI signal blocks; scores block is excluded (system-injected).
# Placeholder values show the exact allowed enum values for each field.
_OUTPUT_SKELETON: dict[str, object] = {
    "schema_version": "pedagogical_media_profile.v1",
    "prompt_version": "pedagogical_media_profile_prompt.v1",
    "review_status": "valid|failed",
    "review_confidence": "<float 0.0-1.0>",
    "organism_group": "<see organism_group allowed values>",
    "evidence_type": "<see evidence_type allowed values>",
    "technical_profile": {
        "technical_quality": "high|medium|low|unusable|unknown",
        "sharpness": "high|medium|low|unknown",
        "lighting": "high|medium|low|unknown",
        "contrast": "high|medium|low|unknown",
        "background_clutter": "low|medium|high|unknown",
        "framing": "good|acceptable|poor|unknown",
        "distance_to_subject": "close|medium|far|very_far|unknown",
    },
    "observation_profile": {
        "subject_presence": "clear|partial|indirect|absent|unknown",
        "subject_visibility": "high|medium|low|none|unknown",
        "visible_parts": ["<free-form body part name>"],
        "view_angle": "lateral|frontal|rear|dorsal|ventral|mixed|unknown",
        "occlusion": "none|minor|major|unknown",
        "context_visible": [
            "water|vegetation|tree|reedbed|ground|sky"
            "|urban|snow|rock|dead_wood|human_structure|unknown"
        ],
    },
    "biological_profile_visible": {
        "sex": {
            "value": _SEX_VALUE_ENUM,
            "confidence": _BIO_CONFIDENCE_ENUM,
            "visible_basis": "<string or null>",
        },
        "life_stage": {
            "value": _LIFE_STAGE_VALUE_ENUM,
            "confidence": _BIO_CONFIDENCE_ENUM,
            "visible_basis": "<string or null>",
        },
        "plumage_state": {
            "value": _PLUMAGE_STATE_VALUE_ENUM,
            "confidence": _BIO_CONFIDENCE_ENUM,
            "visible_basis": "<string or null>",
        },
        "seasonal_state": {
            "value": _SEASONAL_STATE_VALUE_ENUM,
            "confidence": _BIO_CONFIDENCE_ENUM,
            "visible_basis": "<string or null>",
        },
    },
    "identification_profile": {
        "visual_evidence_strength": "high|medium|low|none|unknown",
        "diagnostic_feature_visibility": "high|medium|low|none|unknown",
        "identification_confidence_from_image": "high|medium|low|none|unknown",
        "ambiguity_level": "low|medium|high|unknown",
        "visible_field_marks": [
            {
                "feature": "<string>",
                "body_part": (
                    "head|beak|eye|neck|breast|belly|back|wing|tail|legs|feet"
                    "|whole_body|feather|egg|nest|track|scat|habitat"
                    "|leaf|flower|stem|cap|gills|stipe|unknown"
                ),
                "visibility": "high|medium|low|unknown",
                "importance": "high|medium|low|unknown",
                "confidence": "<float 0.0-1.0>",
            }
        ],
        "missing_key_features": ["<string>"],
        "identification_limitations": ["<string>"],
    },
    "pedagogical_profile": {
        "learning_value": "high|medium|low|none|unknown",
        "difficulty": "easy|medium|hard|unknown",
        "beginner_accessibility": "high|medium|low|none|unknown",
        "expert_interest": "high|medium|low|none|unknown",
        "field_realism": "high|medium|low|none|unknown",
        "cognitive_load": "high|medium|low|none|unknown",
        "requires_prior_knowledge": "high|medium|low|none|unknown",
    },
    "group_specific_profile": {
        "bird": {
            "bird_visible_parts": [
                "head|beak|eye|neck|breast|belly|back|wing|tail|legs|feet|whole_body|unknown"
            ],
            "posture": "perched|standing|swimming|flying|foraging|resting|unknown",
            "behavior_visible": (
                "foraging|swimming|flying|perched|singing|feeding_young|resting|bathing|unknown"
            ),
            "plumage_pattern_visible": "high|medium|low|none|unknown",
            "bill_shape_visible": "high|medium|low|none|unknown",
            "wing_pattern_visible": "high|medium|low|none|unknown",
            "tail_shape_visible": "high|medium|low|none|unknown",
        }
    },
    "limitations": ["<string>"],
}

# Compact valid raw output example — bird, no scores, conservative unknowns for uncertain
# biological attributes, group_specific_profile.bird included.
_VALID_RAW_EXAMPLE: dict[str, object] = {
    "schema_version": "pedagogical_media_profile.v1",
    "prompt_version": "pedagogical_media_profile_prompt.v1",
    "review_status": "valid",
    "review_confidence": 0.85,
    "organism_group": "bird",
    "evidence_type": "whole_organism",
    "technical_profile": {
        "technical_quality": "high",
        "sharpness": "high",
        "lighting": "high",
        "contrast": "high",
        "background_clutter": "low",
        "framing": "good",
        "distance_to_subject": "close",
    },
    "observation_profile": {
        "subject_presence": "clear",
        "subject_visibility": "high",
        "visible_parts": ["head", "beak", "breast", "wing"],
        "view_angle": "lateral",
        "occlusion": "none",
        "context_visible": ["vegetation"],
    },
    "biological_profile_visible": {
        "sex": {"value": "unknown", "confidence": "low", "visible_basis": None},
        "life_stage": {
            "value": "adult",
            "confidence": "medium",
            "visible_basis": "adult plumage and body size",
        },
        "plumage_state": {"value": "unknown", "confidence": "low", "visible_basis": None},
        "seasonal_state": {"value": "unknown", "confidence": "low", "visible_basis": None},
    },
    "identification_profile": {
        "visual_evidence_strength": "high",
        "diagnostic_feature_visibility": "high",
        "identification_confidence_from_image": "high",
        "ambiguity_level": "low",
        "visible_field_marks": [
            {
                "feature": "distinctive breast pattern",
                "body_part": "breast",
                "visibility": "high",
                "importance": "high",
                "confidence": 0.90,
            }
        ],
        "missing_key_features": [],
        "identification_limitations": [],
    },
    "pedagogical_profile": {
        "learning_value": "high",
        "difficulty": "easy",
        "beginner_accessibility": "high",
        "expert_interest": "medium",
        "field_realism": "medium",
        "cognitive_load": "low",
        "requires_prior_knowledge": "low",
    },
    "group_specific_profile": {
        "bird": {
            "bird_visible_parts": ["head", "beak", "breast", "wing"],
            "posture": "perched",
            "behavior_visible": "perched",
            "plumage_pattern_visible": "high",
            "bill_shape_visible": "high",
            "wing_pattern_visible": "medium",
            "tail_shape_visible": "none",
        }
    },
    "limitations": [],
}

# Valid raw example for indirect evidence (feather) — bird profile still required.
# Demonstrates: subject_presence=indirect, complete group_specific_profile.bird,
# biological attributes all unknown (bird not directly visible).
_VALID_RAW_EXAMPLE_INDIRECT: dict[str, object] = {
    "schema_version": "pedagogical_media_profile.v1",
    "prompt_version": "pedagogical_media_profile_prompt.v1",
    "review_status": "valid",
    "review_confidence": 0.65,
    "organism_group": "bird",
    "evidence_type": "feather",
    "technical_profile": {
        "technical_quality": "high",
        "sharpness": "high",
        "lighting": "high",
        "contrast": "medium",
        "background_clutter": "low",
        "framing": "good",
        "distance_to_subject": "close",
    },
    "observation_profile": {
        "subject_presence": "indirect",
        "subject_visibility": "low",
        "visible_parts": ["feather"],
        "view_angle": "unknown",
        "occlusion": "none",
        "context_visible": ["ground"],
    },
    "biological_profile_visible": {
        "sex": {"value": "unknown", "confidence": "low", "visible_basis": None},
        "life_stage": {"value": "unknown", "confidence": "low", "visible_basis": None},
        "plumage_state": {"value": "unknown", "confidence": "low", "visible_basis": None},
        "seasonal_state": {"value": "unknown", "confidence": "low", "visible_basis": None},
    },
    "identification_profile": {
        "visual_evidence_strength": "medium",
        "diagnostic_feature_visibility": "medium",
        "identification_confidence_from_image": "medium",
        "ambiguity_level": "medium",
        "visible_field_marks": [
            {
                "feature": "barring pattern on feather",
                "body_part": "feather",
                "visibility": "high",
                "importance": "medium",
                "confidence": 0.65,
            }
        ],
        "missing_key_features": ["bird not directly visible"],
        "identification_limitations": ["indirect evidence only; feather alone"],
    },
    "pedagogical_profile": {
        "learning_value": "high",
        "difficulty": "hard",
        "beginner_accessibility": "low",
        "expert_interest": "high",
        "field_realism": "high",
        "cognitive_load": "high",
        "requires_prior_knowledge": "high",
    },
    "group_specific_profile": {
        "bird": {
            "bird_visible_parts": ["unknown"],
            "posture": "unknown",
            "behavior_visible": "unknown",
            "plumage_pattern_visible": "medium",
            "bill_shape_visible": "none",
            "wing_pattern_visible": "none",
            "tail_shape_visible": "none",
        }
    },
    "limitations": ["indirect evidence; feather only; identification uncertain"],
}

# Compact failed raw output example — media uninspectable, no assessment blocks.
_FAILED_RAW_EXAMPLE: dict[str, object] = {
    "schema_version": "pedagogical_media_profile.v1",
    "prompt_version": "pedagogical_media_profile_prompt.v1",
    "review_status": "failed",
    "failure_reason": "media_uninspectable",
}

_SERIALIZED_OUTPUT_SKELETON = json.dumps(_OUTPUT_SKELETON, ensure_ascii=True)
_SERIALIZED_VALID_RAW_EXAMPLE = json.dumps(_VALID_RAW_EXAMPLE, ensure_ascii=True)
_SERIALIZED_VALID_RAW_EXAMPLE_INDIRECT = json.dumps(_VALID_RAW_EXAMPLE_INDIRECT, ensure_ascii=True)
_SERIALIZED_FAILED_RAW_EXAMPLE = json.dumps(_FAILED_RAW_EXAMPLE, ensure_ascii=True)


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
        # --- Core doctrine ---
        "Database qualifies now; downstream systems select later. "
        "Review validity is separate from media usefulness. "
        "A feather, nest, track, habitat, distant organism, partial organism, or weak "
        "identification evidence can still be valid. "
        "Use review_status=failed only when media cannot be inspected or output cannot "
        "be structured. "
        # --- Raw vs persisted distinction ---
        "Raw AI output may omit scores. "
        "The system parses, normalizes, and injects scores after validation. "
        "Persisted normalized profile must satisfy schema validation including scores. "
        "Do not output a scores block. "
        # --- Forbidden fields (explicit) ---
        "Forbidden fields — do not include any of: "
        "scores, feedback, post_answer_feedback, identification_tips, "
        "selected_for_quiz, palier_1_core_eligible, recommended_use, "
        "runtime_ready, playable. "
        "Do not compute final numeric scores. The system computes global_quality_score "
        "and usage_scores after parsing and validation. "
        "Do not generate feedback, post-answer hints, quiz or pack or runtime selection, "
        "or final usage recommendations. "
        # --- Taxonomic boundary ---
        "Do not rename, override, or correct the provided taxon. "
        # --- Biological attribute rules ---
        "If biological attributes are uncertain, use unknown. "
        "For biological_profile_visible fields, if value is unknown or not_applicable then "
        "visible_basis may be null and confidence must be 'low' or 'medium' — "
        "do NOT use confidence='unknown' for biological attributes. "
        "When value is unknown or not_applicable, prefer confidence='low'. "
        "Do NOT use confidence='high' when value is unknown or not_applicable. "
        "If unsure, set value='unknown', confidence='low', visible_basis=null. "
        "If value is neither unknown nor not_applicable, visible_basis must be non-empty. "
        # --- Indirect evidence rule ---
        "For indirect evidence types feather, egg, nest, track, scat, burrow, set "
        "observation_profile.subject_presence=indirect. "
        # --- Bird group-specific rule ---
        "If organism_group is bird, group_specific_profile.bird is REQUIRED in ALL cases, "
        "including when evidence_type is feather, egg, nest, track, scat, or burrow. "
        "For indirect evidence, use unknown for posture, behavior_visible, and "
        "bird_visible_parts=[unknown]; fill remaining bird profile fields using "
        "whatever can be inferred from the indirect evidence. "
        "bird_visible_parts can list up to 12 visible parts when clearly visible. "
        "Keep visible_field_marks selective (max 5) and focused on key marks. "
        "Normalize context synonyms to allowed enums: brick wall, wall, building, "
        "fence -> human_structure. "
        # --- Enumerations ---
        f"Allowed organism_group values: [{organism_group_enum}]. "
        f"Allowed evidence_type values: [{evidence_type_enum}]. "
        # --- ENUM CONSTRAINTS: use EXACTLY one listed value, no synonyms ---
        "CRITICAL ENUM CONSTRAINTS — use EXACTLY one value from each list below. "
        "Do NOT invent synonyms, free-text descriptions, or unlisted values. "
        "If uncertain, use 'unknown' (when available) or the closest listed value. "
        "Never use: fair, good (except framing), poor (except framing), moderate, "
        "unclear, not_visible, invisible, partly_visible, visible, "
        "excellent, sharp, blurry, close-up, distant, side-on, overhead, partial_visibility. "
        f"technical_profile.sharpness: [{_SIGNAL_LEVEL}]. "
        f"technical_profile.lighting: [{_SIGNAL_LEVEL}]. "
        f"technical_profile.contrast: [{_SIGNAL_LEVEL}]. "
        f"technical_profile.background_clutter: [{_BACKGROUND_CLUTTER_ENUM}]. "
        f"technical_profile.framing: [{_FRAMING_ENUM}]. "
        f"technical_profile.distance_to_subject: [{_DISTANCE_ENUM}]. "
        f"observation_profile.view_angle: [{_VIEW_ANGLE_ENUM}]. "
        f"observation_profile.occlusion: [{_OCCLUSION_ENUM}]. "
        f"observation_profile.context_visible items: [{_CONTEXT_VISIBLE_ENUM}]. "
        f"biological_profile_visible.sex.value: [{_SEX_VALUE_ENUM}]. "
        f"biological_profile_visible.life_stage.value: [{_LIFE_STAGE_VALUE_ENUM}]. "
        f"biological_profile_visible.plumage_state.value: [{_PLUMAGE_STATE_VALUE_ENUM}]. "
        f"biological_profile_visible.seasonal_state.value: [{_SEASONAL_STATE_VALUE_ENUM}]. "
        f"biological_profile_visible.*.confidence: [{_BIO_CONFIDENCE_ENUM}] — "
        f"use 'low' (not 'unknown') when value is unknown or not_applicable. "
        f"identification_profile.ambiguity_level: [{_AMBIGUITY_ENUM}]. "
        f"identification_profile.visible_field_marks[].visibility: [{_SIGNAL_LEVEL}]. "
        f"identification_profile.visible_field_marks[].importance: [{_SIGNAL_LEVEL}]. "
        f"identification_profile.visible_field_marks[].body_part: [{_FIELD_MARK_BODY_PART_ENUM}]. "
        f"pedagogical_profile.difficulty: [{_DIFFICULTY_ENUM}]. "
        f"pedagogical_profile.expert_interest: [{_SIGNAL_LEVEL_WITH_NONE}]. "
        f"pedagogical_profile.cognitive_load: [{_SIGNAL_LEVEL_WITH_NONE}]. "
        f"group_specific_profile.bird.posture: [{_BIRD_POSTURE_ENUM}]. "
        f"group_specific_profile.bird.behavior_visible: [{_BIRD_BEHAVIOR_ENUM}]. "
        f"group_specific_profile.bird.bird_visible_parts items: [{_BIRD_VISIBLE_PARTS_ENUM}]. "
        f"group_specific_profile.bird.plumage_pattern_visible: [{_SIGNAL_LEVEL_WITH_NONE}]. "
        f"group_specific_profile.bird.bill_shape_visible: [{_SIGNAL_LEVEL_WITH_NONE}]. "
        f"group_specific_profile.bird.wing_pattern_visible: [{_SIGNAL_LEVEL_WITH_NONE}]. "
        f"group_specific_profile.bird.tail_shape_visible: [{_SIGNAL_LEVEL_WITH_NONE}]. "
        # --- Output skeleton ---
        "Output skeleton (all raw AI signal blocks; omit scores block): "
        f"{_SERIALIZED_OUTPUT_SKELETON} "
        # --- Valid raw example (whole_organism) ---
        "Valid raw output example — whole_organism bird "
        "(no scores, no feedback, no selection fields): "
        f"{_SERIALIZED_VALID_RAW_EXAMPLE} "
        # --- Valid raw example (indirect evidence feather) ---
        "Valid raw output example — feather indirect evidence "
        "(subject_presence=indirect, group_specific_profile.bird still required): "
        f"{_SERIALIZED_VALID_RAW_EXAMPLE_INDIRECT} "
        # --- Failed raw example ---
        "Failed raw output example (review_status=failed, no assessment blocks): "
        f"{_SERIALIZED_FAILED_RAW_EXAMPLE} "
        # --- Input context ---
        f"Input context JSON: {serialized_input}"
    )
