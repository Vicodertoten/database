---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/foundation/pedagogical-media-profile-v1.md
scope: foundation
---

# Pedagogical Media Profile v1

## 1. Purpose

`pedagogical_media_profile.v1` defines a modular qualification contract for naturalist media.

Its purpose is to transform raw naturalist media into structured, inspectable, scored and reusable pedagogical data.

This contract does **not** decide whether a media item belongs in a specific quiz, pack, runtime surface, level, or learning mode.

Instead, it describes the media item as precisely and consistently as possible so that downstream systems can later select, filter, rank, audit and reuse it according to their own needs.

The central doctrine is:

```txt
database qualifies now
downstream systems select later
```

The contract should help answer:

- What kind of media/evidence is this?
- Which organism group is concerned?
- What is visible?
- What is not visible?
- How technically usable is the media?
- Which biological traits are visible, if any?
- Which visual field marks are visible?
- How strong is the visual evidence for the provided taxon?
- What are the limitations of this media?
- What is its pedagogical value?
- Which future learning uses could it support?

The contract should not answer:

- Should this media item be in Palier-1?
- Should this media item be in a beginner quiz?
- Should this media item be exported to runtime?
- Should this media item generate feedback now?
- Should this media item be selected for a specific pack?
- Is this media item “good” or “bad” in general?

A difficult media item is not necessarily bad.

A feather is not necessarily useless.

A low basic_identification score does not mean the profile failed.

A valid profile can describe a media item as weak for one future use and strong for another.

## 2. Strategic shift

Earlier image-review work, especially bird_image_review.v1.2, focused on bird images, post-answer feedback and playable-readiness signals.

That direction was useful experimentally, but it mixed several concerns:

- image review
- pedagogical quality
- playability
- post-answer feedback
- final usage readiness.

pedagogical_media_profile.v1 deliberately separates those concerns.

The new model is:

media
→ structured qualification
→ deterministic scores
→ downstream selection

Not:

media
→ accepted/rejected for quiz

The database must preserve nuance.

A media item may be:

- poor for direct species identification
- good for field observation
- useful for indirect evidence learning
- useful for morphology
- weak as a species-card illustration
- valid as a profile even if not selected for any current pack.
## 3. Relationship with biodiversity metadata

pedagogical_media_profile.v1 does not replace taxonomic, occurrence, observation or media-source metadata.

It is a complementary pedagogical qualification layer.

Conceptually:

taxon / observation / media source
→ pedagogical_media_profile.v1
→ future learning systems, packs, filters, audits, feedback generation

This means:

- canonical taxonomy remains outside this contract
- the source observation remains outside this contract
- source media IDs remain outside this contract
- this contract qualifies what is visible and pedagogically useful in the media.

The AI must not override or rename the provided taxon.

The profile may describe the visual evidence strength of the media, but this must not be interpreted as a taxonomic correction.

Example:

```json
{
  "provided_taxon": "Columba palumbus",
  "evidence_type": "feather",
  "visual_evidence_strength": "low"
}
```

This means:

The image itself provides limited visual evidence for the provided taxon.

It does not mean:

The provided taxon is wrong.
## 4. Contract identity and versioning

Canonical contract name:

pedagogical_media_profile.v1

Implementation selector value:

pedagogical_media_profile_v1

Future selector shape:

AI_REVIEW_CONTRACT_VERSION =
  v1_1
  v1_2
  pedagogical_media_profile_v1

Rules:

v1_1 remains the default baseline until explicitly changed.
v1_2 remains available for historical comparison.
pedagogical_media_profile_v1 is opt-in.
This contract is additive.
It must not modify runtime contracts.
It must not modify selectedOptionId.
It must not modify existing playable corpus contracts.
It must not remove legacy compatibility fields.
## 5. Core principles
### 5.1 The profile is not a selector

The profile must not encode final product decisions.

Do not add central fields such as:

```json
{
  "selected_for_quiz": true,
  "palier_1_core_eligible": false,
  "recommended_use": "field_training"
}
```

Future systems may derive those decisions from scores and signals.

The profile itself stores:

- structured observations
- quality signals
- identification signals
- pedagogical signals
- deterministic scores
- limitations.
### 5.2 Review validity is separate from media usefulness

review_status describes whether the profile output is structurally valid.

It does not describe whether the media item is useful for a specific learning use.

A valid profile may have low usage scores.

A media item can be valid with:

```json
{
  "usage_scores": {
    "basic_identification": 0,
    "indirect_evidence_learning": 80
  }
}
```
### 5.3 Weak usefulness is not failure

failed must never mean:

- difficult image
- partial organism
- feather
- nest
- egg
- track
- habitat
- weak basic identification potential
- no feedback
- low visual evidence strength
- low global score.

failed is reserved for invalid or impossible reviews.

### 5.4 Feedback is out of scope for v1

pedagogical_media_profile.v1 does not generate feedback.

It does not include:

- post_answer_feedback
- feedback_profile
- feedback_possible
- identification_tips.

A future contract may be introduced later:

pedagogical_feedback_profile.v1

That future contract should use the structured media profile as input.

### 5.5 AI provides signals; system computes scores

The AI may produce normalized qualitative signals such as:

```json
{
  "technical_quality": "medium",
  "subject_visibility": "high",
  "diagnostic_feature_visibility": "medium",
  "visual_evidence_strength": "medium",
  "learning_value": "high"
}
```

The system computes final numeric scores:

```json
{
  "global_quality_score": 74,
  "usage_scores": {
    "basic_identification": 68,
    "field_observation": 82
  }
}
```

The model must not be treated as the final scoring authority.

## 6. Top-level structure

Canonical conceptual shape:

```json
{
  "schema_version": "pedagogical_media_profile.v1",
  "review_status": "valid",
  "review_confidence": 0.86,

  "organism_group": "bird",
  "evidence_type": "whole_organism",

  "technical_profile": {},
  "observation_profile": {},
  "biological_profile_visible": {},
  "identification_profile": {},
  "pedagogical_profile": {},
  "group_specific_profile": {},
  "scores": {},
  "limitations": []
}
```

Top-level blocks:

schema_version
review_status
review_confidence
organism_group
evidence_type
technical_profile
observation_profile
biological_profile_visible
identification_profile
pedagogical_profile
group_specific_profile
scores
limitations
## 7. review_status
Purpose

Indicates whether the review/profile output itself is valid.

It must not be used as a proxy for media usefulness.

Values
valid
failed
valid

Use valid when the media has been structurally qualified.

A valid profile may still describe the media as:

- difficult
- weak for basic identification
- indirect evidence
- visually ambiguous
- poor for some uses
- strong for other uses.

failed

Use failed only for cases where a structured profile cannot be trusted or produced.

Examples:

- invalid JSON
- schema validation failure
- empty model output
- model output impossible to normalize
- media inaccessible
- unsafe media
- media impossible to inspect
- technical failure.
Non-failure examples

The following are not failures by themselves:

- feather
- egg
- nest
- track
- scat
- burrow
- habitat
- dead organism
- multiple organisms
- distant organism
- partial organism
- low basic_identification
- low visual_evidence_strength
- low global_quality_score.
## 8. organism_group
Purpose

Describes the broad biological group associated with the media.

This is not a taxonomic rank. It is a practical profiling group used to choose the appropriate group-specific profile.

Initial enum
bird
mammal
reptile
amphibian
fish
insect
arachnid
mollusk
plant
fungus
lichen
unknown
v1 implementation rule

bird is the first implemented group-specific profile.

The other values are included for forward compatibility.

Future work

Future versions may define additional group-specific profiles for:

- plants
- fungi
- mammals
- insects
- fish
- lichens
- other groups.

The exact future granularity is not fixed.

## 9. evidence_type
Purpose

Describes what kind of biological or ecological evidence the media shows.

This field is central.

A bird image and a bird feather image are not the same type of evidence, even if linked to the same taxon.

Initial enum
whole_organism
partial_organism
feather
egg
nest
track
scat
burrow
habitat
plant_part
fungus_fruiting_body
dead_organism
multiple_organisms
unknown
Excluded from v1

sound_context is intentionally excluded from v1.

The contract is currently focused on visual media qualification.

Human-made context

Human-made elements are not represented as an evidence_type.

They may be represented in context_visible.

Example:

```json
{
  "evidence_type": "habitat",
  "observation_profile": {
    "context_visible": ["human_structure", "vegetation"]
  }
}
```
Evidence examples
Whole organism
```json
{
  "organism_group": "bird",
  "evidence_type": "whole_organism"
}
```
Feather
```json
{
  "organism_group": "bird",
  "evidence_type": "feather"
}
```
Multiple organisms
```json
{
  "organism_group": "bird",
  "evidence_type": "multiple_organisms"
}
```
Habitat
```json
{
  "organism_group": "bird",
  "evidence_type": "habitat"
}
```
Interpretation rule

A non-whole-organism media item is not invalid.

It should receive scores that reflect its actual learning potential.

## 10. technical_profile
Purpose

Describes the technical quality of the media.

This is part of the objective media description.

Structure
```json
{
  "technical_quality": "medium",
  "sharpness": "medium",
  "lighting": "high",
  "contrast": "medium",
  "background_clutter": "medium",
  "framing": "good",
  "distance_to_subject": "medium"
}
```
Enums
technical_quality
high
medium
low
unusable
unknown
sharpness
high
medium
low
unknown
lighting
high
medium
low
unknown
contrast
high
medium
low
unknown
background_clutter
low
medium
high
unknown
framing
good
acceptable
poor
unknown
distance_to_subject
close
medium
far
very_far
unknown
Rule

Use unknown when a field is not applicable or cannot be reliably assessed.

Examples:

distance_to_subject may be unknown for habitat images.
background_clutter may be unknown for non-photographic or atypical media.
technical_quality = unusable should not automatically mean review_status = failed if the media can still be profiled structurally, but it should strongly reduce scores.
## 11. observation_profile
Purpose

Describes what is visible in the media.

Structure
```json
{
  "subject_presence": "clear",
  "subject_visibility": "high",
  "visible_parts": ["head", "beak", "breast", "wing"],
  "view_angle": "lateral",
  "occlusion": "minor",
  "context_visible": ["water", "vegetation"]
}
```
Enums
subject_presence
clear
partial
indirect
absent
unknown
subject_visibility
high
medium
low
none
unknown
view_angle
lateral
frontal
rear
dorsal
ventral
mixed
unknown
occlusion
none
minor
major
unknown
context_visible

Controlled list, max 5 items.

Initial values:

water
vegetation
tree
reedbed
ground
sky
urban
snow
rock
dead_wood
human_structure
unknown
Rules

For indirect evidence types such as:

feather
egg
nest
track
scat
burrow

use:

```json
{
  "subject_presence": "indirect"
}
```

For a feather image, the whole organism is not visible. This does not make the profile invalid.

visible_parts

visible_parts exists in the core profile.

For birds, it may overlap with group_specific_profile.bird.bird_visible_parts.

This temporary redundancy is accepted in v1 because:

- core visible_parts supports cross-group inspection
- bird-specific parts support better bird-focused normalization.
## 12. biological_profile_visible
Purpose

Describes biological attributes visible in the media, when they can be inferred visually.

This block must be conservative.

The model must not invent biological attributes.

Structure
```json
{
  "sex": {
    "value": "unknown",
    "confidence": "low",
    "visible_basis": null
  },
  "life_stage": {
    "value": "adult",
    "confidence": "medium",
    "visible_basis": "adult-like plumage and body size"
  },
  "plumage_state": {
    "value": "unknown",
    "confidence": "low",
    "visible_basis": null
  },
  "seasonal_state": {
    "value": "unknown",
    "confidence": "low",
    "visible_basis": null
  }
}
```
Core fields
sex
life_stage
plumage_state
seasonal_state
Excluded from v1

age is excluded from v1.

Reason:

age overlaps with life_stage and risks creating fragile distinctions too early.

Future versions may reintroduce a more detailed age model if needed.

General rule

If:

value = unknown or not_applicable

then:

visible_basis may be null
- confidence must be low or medium

If:

value != unknown and value != not_applicable

then:

- visible_basis is required and must be non-empty
Recommended confidence behavior

Prefer unknown over fragile inference.

If no visible basis exists, do not infer.

Initial values
sex.value
male
female
unknown
not_applicable
life_stage.value
egg
juvenile
adult
unknown
not_applicable
plumage_state.value
breeding_plumage
non_breeding_plumage
eclipse_plumage
juvenile_plumage
unknown
not_applicable
seasonal_state.value
breeding_season
non_breeding_season
migration_period
wintering
unknown
not_applicable
Notes

seasonal_state is included in v1 but should be treated cautiously.

It should only be asserted when visible evidence supports it or when media metadata makes the inference safe in a future pipeline.

For v1 AI-only profiling, prefer unknown unless visual evidence is clear.

## 13. identification_profile
Purpose

Describes how strongly the visible media supports visual identification of the provided taxon.

This is not a taxonomic override.

The AI must not rename the taxon, challenge the canonical taxon, or propose another species.

Structure
```json
{
  "visual_evidence_strength": "high",
  "diagnostic_feature_visibility": "high",
  "identification_confidence_from_image": "medium",
  "ambiguity_level": "medium",
  "visible_field_marks": [
    {
      "feature": "white frontal shield",
      "body_part": "head",
      "visibility": "high",
      "importance": "high",
      "confidence": 0.91
    }
  ],
  "missing_key_features": ["tail"],
  "identification_limitations": [
    "body partly hidden by vegetation"
  ]
}
```
Enums
visual_evidence_strength
high
medium
low
none
unknown

Meaning:

How strongly the visible media supports the provided taxon.

This does not judge whether the taxon is correct.

diagnostic_feature_visibility
high
medium
low
none
unknown
identification_confidence_from_image
high
medium
low
none
unknown

Meaning:

How confidently the taxon could be identified from the media alone.

ambiguity_level
low
medium
high
unknown
visible_field_marks

Max 5 items.

Structure:

```json
{
  "feature": "white frontal shield",
  "body_part": "head",
  "visibility": "high",
  "importance": "high",
  "confidence": 0.91
}
```

Rules:

feature is a short English free-text string.
body_part should be normalized.
visibility uses high | medium | low | unknown.
importance uses high | medium | low | unknown.
confidence is a number between 0 and 1.
Do not invent field marks that are not visible.
Initial body_part vocabulary

For v1, allow a pragmatic controlled vocabulary:

head
beak
eye
breast
belly
back
wing
tail
legs
feet
whole_body
feather
egg
nest
track
scat
habitat
leaf
flower
stem
cap
gills
stipe
unknown

This list may evolve with future organism-group profiles.

missing_key_features

List of short English strings.

Example:

["tail", "legs"]
identification_limitations

List of short English strings.

Example:

[
  "tail not visible",
  "lighting reduces color reliability"
]
## 14. pedagogical_profile
Purpose

Describes the media’s learning value and difficulty without selecting a final use.

Structure
```json
{
  "learning_value": "high",
  "difficulty": "medium",
  "beginner_accessibility": "medium",
  "expert_interest": "medium",
  "field_realism": "high",
  "cognitive_load": "medium",
  "requires_prior_knowledge": "low"
}
```
Enums

For most fields:

high
medium
low
none
unknown

For difficulty:

easy
medium
hard
unknown
Interpretation

A media item can be both hard and valuable.

Example:

```json
{
  "difficulty": "hard",
  "learning_value": "high",
  "beginner_accessibility": "low",
  "expert_interest": "high"
}
```

This is a valid profile, not a failure.

Fields
learning_value

General pedagogical value of the media.

difficulty

How difficult the media is to interpret visually.

beginner_accessibility

How accessible the media is to a beginner.

expert_interest

How interesting or useful the media may be for advanced learners or expert review.

field_realism

How representative the media is of real-world field-observation conditions.

cognitive_load

How much visual or interpretive effort is required.

requires_prior_knowledge

How much prior knowledge is needed to use the media effectively.

## 15. group_specific_profile
Purpose

Stores organism-group-specific observations.

For v1, only bird is required.

Other groups may be added later.

Bird profile structure
```json
{
  "bird": {
    "bird_visible_parts": ["head", "beak", "breast", "wing"],
    "posture": "swimming",
    "behavior_visible": "foraging",
    "plumage_pattern_visible": "medium",
    "bill_shape_visible": "high",
    "wing_pattern_visible": "low",
    "tail_shape_visible": "low"
  }
}
```
bird_visible_parts

Max 8 items.

Initial values:

head
beak
eye
breast
belly
back
wing
tail
legs
feet
whole_body
unknown
posture

Single value.

Initial values:

perched
standing
swimming
flying
foraging
resting
unknown
behavior_visible

Single value.

Initial values:

foraging
swimming
flying
perched
singing
feeding_young
resting
unknown

If several behaviors appear possible, use the dominant visible behavior.

If uncertain, use unknown.

Visibility fields

The following use:

high
medium
low
none
unknown

Fields:

plumage_pattern_visible
bill_shape_visible
wing_pattern_visible
tail_shape_visible
Habitat

Habitat or background context must remain in:

observation_profile.context_visible

Do not duplicate habitat in the bird-specific profile for v1.

## 16. scores
Purpose

Provide deterministic, system-computed numeric scores.

The AI provides qualitative signals.

The system computes numeric scores.

Structure
```json
{
  "global_quality_score": 78,
  "usage_scores": {
    "basic_identification": 76,
    "field_observation": 84,
    "confusion_learning": 62,
    "morphology_learning": 71,
    "species_card": 65,
    "indirect_evidence_learning": 0
  }
}
```

All scores are integers from 0 to 100.

global_quality_score

A general-purpose quality score used for:

- simple sorting
- audit
- pack generation without advanced filtering
- quick comparison between media items.

It is not a final usage decision.

Provisional global score formula
20% technical_quality
20% subject/evidence visibility
25% visual_evidence_strength
15% learning_value
10% field marks quality
10% reliability/confidence

This formula is provisional and should be calibrated after fixtures and mini-runs.

Usage scores
basic_identification

Potential for direct species identification learning.

field_observation

Potential for realistic field-observation learning.

confusion_learning

Potential for learning distinctions between similar taxa.

morphology_learning

Potential for learning visible morphology or organism parts.

species_card

Potential as illustrative media for a species page or card.

indirect_evidence_learning

Potential for learning from indirect evidence such as feather, egg, nest, track, scat, burrow or habitat.

Important scoring rule

A media item can have:

```json
{
  "basic_identification": 0,
  "indirect_evidence_learning": 80
}
```

and still be valid.

A feather may have a correct or even good global_quality_score if technically clear and pedagogically useful, even if it is poor for direct identification.

## 17. limitations
Purpose

List concise limitations of the media.

Structure

Max 5 short English strings.

Example:

[
  "tail not visible",
  "bird partly hidden by branches",
  "lighting reduces color reliability"
]

Limitations explain profile signals and scores.

They do not automatically reject the media.

## 18. Diagnostics

Diagnostics are only required for failed reviews.

Failed payload example
```json
{
  "schema_version": "pedagogical_media_profile.v1",
  "review_status": "failed",
  "failure_reason": "schema_validation_failed",
  "diagnostics": {
    "parsed_json_available": true,
    "schema_error_count": 2,
    "schema_errors": []
  }
}
```
Failure reasons

Initial enum:

model_output_invalid
schema_validation_failed
media_not_accessible
unsafe_or_invalid_content
empty_model_output
media_uninspectable
unknown_failure

Diagnostics should not be required for valid profiles.

## 19. Language policy

All short free-text fields should use English in v1.

Examples:

"limitations": ["tail not visible"]

not:

"limitations": ["la queue n'est pas visible"]

Rationale:

- easier normalization
- easier testing
- simpler multilingual support later
- consistency with field-mark and biological terminology.

Future user-facing translations belong to UI or localization layers, not this profile contract.

## 20. Feedback policy

Feedback is not part of pedagogical_media_profile.v1.

The contract must not include:

- post_answer_feedback
- feedback_profile
- feedback_possible
- identification_tips
- pre-answer hints.

Future feedback can be built later from this structured profile.

Potential future contract:

pedagogical_feedback_profile.v1
## 21. AI role

The AI should act as a structured media annotator.

It should produce:

- qualitative signals
- visible evidence descriptions
- field marks
- limitations
- confidence values
- conservative biological attributes.

It should not produce:

- final scores
- quiz selection decisions
- pack selection decisions
- runtime decisions
- feedback
- taxonomic corrections.
AI rules

The AI must:

- return strict JSON
- follow the schema
- use controlled enums
- prefer unknown over weak inference
- not invent invisible traits
- not rename the provided taxon
- not challenge canonical taxonomy.
## 22. Structured output and model strategy

pedagogical_media_profile.v1 should remain simple enough for structured-output generation.

Design constraints:

- avoid excessive nesting
- avoid complex polymorphism
- avoid heavy oneOf or conditional schema logic in v1
- use clear enums
- limit arrays
- keep free text short
- validate outputs in application code.

The model choice is not fixed in this foundation.

A future benchmark should compare candidate models on:

- schema pass rate
- enum stability
- field-mark relevance
- prudence on biological attributes
- latency
- cost
- consistency across difficult media
- usefulness of generated limitations.

Testing must not depend on live model access.

## 23. Examples
### 23.1 Clear bird image
```json
{
  "schema_version": "pedagogical_media_profile.v1",
  "review_status": "valid",
  "review_confidence": 0.9,
  "organism_group": "bird",
  "evidence_type": "whole_organism",
  "technical_profile": {
    "technical_quality": "high",
    "sharpness": "high",
    "lighting": "high",
    "contrast": "high",
    "background_clutter": "low",
    "framing": "good",
    "distance_to_subject": "close"
  },
  "observation_profile": {
    "subject_presence": "clear",
    "subject_visibility": "high",
    "visible_parts": ["head", "beak", "breast", "wing", "tail"],
    "view_angle": "lateral",
    "occlusion": "none",
    "context_visible": ["vegetation"]
  },
  "biological_profile_visible": {
    "sex": {
      "value": "unknown",
      "confidence": "low",
      "visible_basis": null
    },
    "life_stage": {
      "value": "adult",
      "confidence": "medium",
      "visible_basis": "adult-like plumage and body size"
    },
    "plumage_state": {
      "value": "unknown",
      "confidence": "low",
      "visible_basis": null
    },
    "seasonal_state": {
      "value": "unknown",
      "confidence": "low",
      "visible_basis": null
    }
  },
  "identification_profile": {
    "visual_evidence_strength": "high",
    "diagnostic_feature_visibility": "high",
    "identification_confidence_from_image": "high",
    "ambiguity_level": "low",
    "visible_field_marks": [
      {
        "feature": "orange breast",
        "body_part": "breast",
        "visibility": "high",
        "importance": "high",
        "confidence": 0.93
      }
    ],
    "missing_key_features": [],
    "identification_limitations": []
  },
  "pedagogical_profile": {
    "learning_value": "high",
    "difficulty": "easy",
    "beginner_accessibility": "high",
    "expert_interest": "medium",
    "field_realism": "medium",
    "cognitive_load": "low",
    "requires_prior_knowledge": "low"
  },
  "group_specific_profile": {
    "bird": {
      "bird_visible_parts": ["head", "beak", "breast", "wing", "tail"],
      "posture": "perched",
      "behavior_visible": "perched",
      "plumage_pattern_visible": "high",
      "bill_shape_visible": "high",
      "wing_pattern_visible": "medium",
      "tail_shape_visible": "medium"
    }
  },
  "scores": {
    "global_quality_score": 88,
    "usage_scores": {
      "basic_identification": 92,
      "field_observation": 70,
      "confusion_learning": 65,
      "morphology_learning": 80,
      "species_card": 85,
      "indirect_evidence_learning": 0
    }
  },
  "limitations": []
}
```
### 23.2 Feather media
```json
{
  "schema_version": "pedagogical_media_profile.v1",
  "review_status": "valid",
  "review_confidence": 0.82,
  "organism_group": "bird",
  "evidence_type": "feather",
  "technical_profile": {
    "technical_quality": "high",
    "sharpness": "high",
    "lighting": "high",
    "contrast": "medium",
    "background_clutter": "low",
    "framing": "good",
    "distance_to_subject": "close"
  },
  "observation_profile": {
    "subject_presence": "indirect",
    "subject_visibility": "none",
    "visible_parts": ["feather"],
    "view_angle": "dorsal",
    "occlusion": "none",
    "context_visible": ["ground"]
  },
  "biological_profile_visible": {
    "sex": {
      "value": "not_applicable",
      "confidence": "low",
      "visible_basis": null
    },
    "life_stage": {
      "value": "unknown",
      "confidence": "low",
      "visible_basis": null
    },
    "plumage_state": {
      "value": "unknown",
      "confidence": "low",
      "visible_basis": null
    },
    "seasonal_state": {
      "value": "unknown",
      "confidence": "low",
      "visible_basis": null
    }
  },
  "identification_profile": {
    "visual_evidence_strength": "low",
    "diagnostic_feature_visibility": "medium",
    "identification_confidence_from_image": "low",
    "ambiguity_level": "high",
    "visible_field_marks": [
      {
        "feature": "feather pattern",
        "body_part": "feather",
        "visibility": "medium",
        "importance": "medium",
        "confidence": 0.65
      }
    ],
    "missing_key_features": ["whole_body", "head", "beak"],
    "identification_limitations": [
      "media shows a feather rather than the whole organism"
    ]
  },
  "pedagogical_profile": {
    "learning_value": "medium",
    "difficulty": "hard",
    "beginner_accessibility": "low",
    "expert_interest": "medium",
    "field_realism": "high",
    "cognitive_load": "high",
    "requires_prior_knowledge": "high"
  },
  "group_specific_profile": {
    "bird": {
      "bird_visible_parts": ["unknown"],
      "posture": "unknown",
      "behavior_visible": "unknown",
      "plumage_pattern_visible": "medium",
      "bill_shape_visible": "none",
      "wing_pattern_visible": "unknown",
      "tail_shape_visible": "unknown"
    }
  },
  "scores": {
    "global_quality_score": 48,
    "usage_scores": {
      "basic_identification": 5,
      "field_observation": 35,
      "confusion_learning": 10,
      "morphology_learning": 45,
      "species_card": 30,
      "indirect_evidence_learning": 80
    }
  },
  "limitations": [
    "whole organism is not visible",
    "species-level identification from the media alone is limited"
  ]
}
```
## 24. Compatibility with existing layers

This contract is additive.

It does not replace:

- AIQualification
- PedagogicalImageProfile
- bird_image_review.v1.2
- playable corpus contracts
- runtime consumption contracts.

It introduces a broader media qualification layer.

Positioning:

AIQualification / source metadata
→ pedagogical_media_profile.v1
→ future scoring, filtering, pack selection, feedback generation

Existing runtime surfaces remain unchanged.

## 25. Implementation roadmap
Phase 0 — Foundation documentation

Create this document and validate the contract doctrine.

No functional code changes.

Phase 1 — Schema, parser, validator, fixtures

Add:

schemas/pedagogical_media_profile_v1.schema.json
src/database_core/qualification/pedagogical_media_profile_v1.py
tests/test_pedagogical_media_profile_v1.py

Include:

- strict JSON schema
- valid payload fixture
- failed payload fixture
- parser
- normalizer
- validator
- enum validation
- confidence validation
- array length validation
- diagnostics for failed payloads.
Phase 2 — Deterministic scoring

Add deterministic score computation.

The AI provides qualitative signals.

The system computes:

- global_quality_score
- usage_scores.
Phase 3 — Prompt and fixture-based dry run

Add prompt builder and fixture-based dry-run.

No live model access required in CI.

Phase 4 — Opt-in integration

Add selector support:

AI_REVIEW_CONTRACT_VERSION=pedagogical_media_profile_v1

Default remains v1_1.

Phase 5 — Controlled live mini-run

Run on a small sample and audit:

- valid profile count
- failed profile count
- evidence type distribution
- organism group distribution
- global score distribution
- usage score averages
- field mark quality
- biological profile prudence
- schema failures
- model latency
- model cost.
Phase 6 — Model benchmark

Compare candidate model/configurations.

Do not choose the long-term model before benchmark evidence exists.

## 26. Acceptance criteria for the foundation

The foundation is valid when:

pedagogical_media_profile.v1 is clearly defined.
It is positioned as a new parallel contract.
It does not replace v1_1 or v1_2.
It clearly separates review validity from media usefulness.
It avoids final usage selection.
It supports broad organism groups.
It supports indirect evidence types.
It removes feedback from v1 scope.
It defines core profile blocks.
It defines the initial bird-specific profile.
It defines global and modular usage scores.
It states that AI provides signals and the system computes scores.
It preserves runtime compatibility.
It documents open future work.
## 27. Open future work

The following are intentionally not fully fixed in v1 foundation:

Exact scoring formulas and weights.
Future plant profile.
Future fungus profile.
Future mammal profile.
Future insect profile.
Model choice and model pricing.
Live structured-output settings.
Manual correction workflow.
Future feedback contract.
Future multilingual display layer.
Future selection policies for packs and runtime experiences.
Future audio-specific profile if sound media becomes first-class.
## 28. Final design statement

pedagogical_media_profile.v1 is a modular naturalist media qualification contract.

It exists to turn raw media into structured, scored, inspectable and reusable pedagogical data.

It does not decide how the media will be used.

The database qualifies now.

Downstream systems select later.
