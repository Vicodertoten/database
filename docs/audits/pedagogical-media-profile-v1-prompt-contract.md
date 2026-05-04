---
owner: database
status: ready_for_validation
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

The prompt explicitly forbids:

- feedback generation
- post-answer feedback generation
- identification tips
- quiz/pack/runtime final selection fields
- final usage recommendation fields

## 6. Biological and evidence consistency rules in prompt text

Prompt-level consistency guidance includes:

- if biological value is `unknown` or `not_applicable`,
  `visible_basis` may be null and confidence must be low or medium
- if biological value is neither `unknown` nor `not_applicable`,
  `visible_basis` must be non-empty
- for indirect evidence types (`feather`, `egg`, `nest`, `track`, `scat`, `burrow`),
  `observation_profile.subject_presence` must be `indirect`

## 7. Enumerations embedded in prompt

The prompt embeds the controlled vocabularies for:

- `organism_group`
- `evidence_type`

This improves model compliance during fixture dry-runs before any live integration.

## 8. Files introduced for this issue

- `src/database_core/qualification/pedagogical_media_profile_prompt_v1.py`
- `tests/test_pedagogical_media_profile_prompt_v1.py`
