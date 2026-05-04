---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/audits/pedagogical-media-profile-v1-prompt-contract.md
scope: audit
---

# Pedagogical Media Profile v1 Prompt Contract

## 1. Goal

Define the versioned AI prompt contract for generating raw qualitative signals
compatible with `pedagogical_media_profile.v1`.

Prompt version:

- `pedagogical_media_profile_prompt.v1`

## 2. Doctrine alignment

The prompt must preserve core doctrine:

- database qualifies now
- downstream systems select later
- review validity is separate from media usefulness
- weak usefulness is not failure
- AI provides qualitative signals
- system computes deterministic scores

## 3. Raw AI output vs persisted normalized profile

The prompt targets raw AI output.

- raw AI output contains structured qualitative profile signals
- raw AI output may omit `scores`
- parser/normalizer computes and injects deterministic `scores`
- persisted normalized profile must satisfy full schema validation

## 4. Prompt inputs

The prompt builder supports:

- expected scientific name
- optional common names
- organism group
- media/image URL or media reference
- optional source metadata (e.g., iNaturalist)
- optional observation context
- optional locale/context notes

## 5. Mandatory prompt constraints

The prompt explicitly requires:

- strict JSON-only output
- `schema_version=pedagogical_media_profile.v1`
- `prompt_version=pedagogical_media_profile_prompt.v1`
- no taxonomic override or renaming
- no final score computation by AI

The prompt explicitly forbids the following fields from AI output:

- `scores`
- `feedback`
- `post_answer_feedback`
- `identification_tips`
- `selected_for_quiz`
- `palier_1_core_eligible`
- `recommended_use`
- `runtime_ready`
- `playable`

The prompt states explicitly: "Do not output a scores block."

## 6. Biological and evidence consistency rules in prompt text

Prompt-level consistency guidance includes:

- if biological value is `unknown` or `not_applicable`,
  `visible_basis` may be null and confidence must be low or medium
- if biological value is neither `unknown` nor `not_applicable`,
  `visible_basis` must be non-empty
- for indirect evidence types (`feather`, `egg`, `nest`, `track`, `scat`, `burrow`),
  `observation_profile.subject_presence` must be `indirect`
- if `organism_group` is `bird`, `group_specific_profile.bird` is required

## 7. Enumerations embedded in prompt

The prompt embeds the controlled vocabularies for:

- `organism_group`
- `evidence_type`

This improves model compliance during fixture dry-runs before any live integration.

## 8. Output skeleton (Sprint 3 hardening)

The prompt includes an explicit JSON output skeleton listing all expected raw AI signal
blocks in order. Blocks included:

- `schema_version`
- `prompt_version`
- `review_status`
- `review_confidence`
- `organism_group`
- `evidence_type`
- `technical_profile`
- `observation_profile`
- `biological_profile_visible`
- `identification_profile`
- `pedagogical_profile`
- `group_specific_profile`
- `limitations`

The `scores` block is absent from the skeleton. The system injects scores after parsing
and validation.

## 9. Inline raw output examples (Sprint 3 hardening)

The prompt includes two compact raw output examples:

**Valid raw output example:**

- `review_status: "valid"`, `review_confidence: 0.85` (float)
- `organism_group: "bird"` with `group_specific_profile.bird`
- Conservative `unknown` values for uncertain biological attributes
  (`sex`, `plumage_state`, `seasonal_state`)
- No `scores` block
- No feedback or selection fields

**Failed raw output example:**

- `review_status: "failed"`, `failure_reason: "media_uninspectable"`
- No assessment blocks

## 10. Files introduced for this issue

- `src/database_core/qualification/pedagogical_media_profile_prompt_v1.py`
- `tests/test_pedagogical_media_profile_prompt_v1.py`

