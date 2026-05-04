---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/audits/pedagogical-media-profile-v1-post-sprint6-corrective-changes.md
scope: audit
---

# Post-Sprint-6 corrective changes before Sprint 7

## Purpose

Apply final small corrective hardening updates identified after Sprint 6
stabilization, without widening scope to Sprint 7 policy design.

## Scope

In scope:
- raise `bird_visible_parts` cap to reduce avoidable schema failures,
- add missing bird behavior enum value `bathing`,
- normalize common context synonyms to `human_structure`,
- preserve strict biological consistency rules,
- harden failed-item audit fallback for `schema_failure_cause`,
- regenerate deterministic Sprint 6 audit evidence from existing `ai_outputs`.

Out of scope:
- runtime/materialization behavior,
- Supabase/Postgres writes,
- rerunning Gemini generation,
- Sprint 7 policy thresholds.

## Corrective changes applied

1. Schema updates
- File: `schemas/pedagogical_media_profile_v1.schema.json`
- `group_specific_profile.bird.bird_visible_parts.maxItems`: `8 -> 12`
- `group_specific_profile.bird.behavior_visible` enum: added `bathing`
- `identification_profile.visible_field_marks.maxItems` unchanged.

2. Prompt contract updates
- File: `src/database_core/qualification/pedagogical_media_profile_prompt_v1.py`
- Added `bathing` in bird behavior enum guidance.
- Added explicit note that `bird_visible_parts` may include up to 12 parts.
- Added explicit context synonym normalization guidance:
  `brick wall|wall|building|fence -> human_structure`.

3. Normalization updates
- File: `src/database_core/qualification/pedagogical_media_profile_v1.py`
- Added `bathing` to normalized `behavior_visible` bird enum.
- Added safe context alias normalization before enum validation:
  `brick wall|wall|building|fence -> human_structure`.
- No schema widening for context enums.

4. Audit fallback hardening
- File: `scripts/audit_pedagogical_media_profile_v1_snapshot_outputs.py`
- For failed items, if diagnostics `schema_failure_cause` is missing/empty or
  `unknown_schema_failure`, fallback now uses first extracted schema error cause.

5. Tests added/updated
- `tests/test_pedagogical_media_profile_v1.py`
  - `bird_visible_parts`: 11 items valid, 13 items invalid,
  - `bathing` valid, invented behavior invalid,
  - context synonym normalization to `human_structure`,
  - unmapped context values still fail validation,
  - biological strictness rules remain enforced.
- `tests/test_pedagogical_media_profile_prompt_v1.py`
  - prompt includes `bathing`,
  - prompt includes context synonym normalization guidance.
- `tests/test_audit_pedagogical_media_profile_v1_snapshot_outputs.py`
  - explicit regression test for `failed_items_summary` fallback from
    `unknown_schema_failure` to extracted first error cause.

## Deterministic evidence regeneration

Regenerated from existing `ai_outputs` only (no model rerun):
- output: `docs/audits/evidence/pedagogical_media_profile_v1_sprint6_snapshot_audit.json`
- snapshot id:
  `palier1-be-birds-50taxa-run003-v11-baseline-sprint6-controlled-120`

## Validation

Executed:

```bash
PYTHONPATH=src /usr/local/bin/python3 -m pytest \
  tests/test_pedagogical_media_profile_v1.py \
  tests/test_pedagogical_media_profile_prompt_v1.py \
  tests/test_audit_pedagogical_media_profile_v1_snapshot_outputs.py

/usr/local/bin/python3 -m ruff check \
  src/database_core/qualification/pedagogical_media_profile_v1.py \
  src/database_core/qualification/pedagogical_media_profile_prompt_v1.py \
  scripts/audit_pedagogical_media_profile_v1_snapshot_outputs.py \
  tests/test_pedagogical_media_profile_v1.py \
  tests/test_pedagogical_media_profile_prompt_v1.py \
  tests/test_audit_pedagogical_media_profile_v1_snapshot_outputs.py

/usr/local/bin/python3 scripts/check_doc_code_coherence.py
/usr/local/bin/python3 scripts/check_docs_hygiene.py
```

Result: pass.

## Final status

**`READY_FOR_SPRINT_7_PMP_POLICY_DESIGN`**

Rationale:
- corrective failures addressed at schema/prompt/normalizer level,
- diagnostics fallback made deterministic and actionable,
- tests and quality gates pass,
- governance and scope boundaries preserved.
