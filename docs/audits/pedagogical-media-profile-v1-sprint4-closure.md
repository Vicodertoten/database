---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/audits/pedagogical-media-profile-v1-sprint4-closure.md
scope: audit
---

# Sprint 4 closure — pedagogical_media_profile.v1 prompt/schema alignment pass + second live mini-run

## Purpose

Document the outcome of Sprint 4 for `pedagogical_media_profile.v1`.
This sprint diagnosed Sprint 3 live failures, hardened prompt/schema alignment,
added deeper diagnostics, and executed a second controlled live mini-run.

---

## Scope

- Task 1: Deepen live failure diagnostics
- Task 2: Analyze Sprint 3 raw outputs
- Task 3: Harden prompt enum guidance
- Task 4: Handle missing required fields (feather / indirect evidence bird profile)
- Task 5: Evidence-based schema fixes (`prompt_version`, `neck` in bird parts)
- Task 6: Conservative normalization — case normalization for all uncovered enum fields
- Task 7: Update preferred Gemini model (gemini-3.1-flash-lite-preview)
- Task 8: Re-run fixture dry-run
- Task 9: Run second controlled live mini-run

**Out of scope (unchanged):**
- runtime application
- pipeline integration
- materialization
- feedback / distractors
- default behavior

---

## Files added / updated

| File | Status | Purpose |
|------|--------|---------|
| `src/database_core/qualification/pedagogical_media_profile_v1.py` | updated | Sprint 4: extend normalization to all uncovered enum fields; add `_normalize_biological_attribute`, `_normalize_string_enum_list` helpers; add `neck` to bird_visible_parts normalizer |
| `src/database_core/qualification/pedagogical_media_profile_prompt_v1.py` | updated | Sprint 4: add explicit enum constants for all constrained fields; update output skeleton with inline enum hints; add indirect evidence (feather) valid example; add comprehensive ENUM CONSTRAINTS section; add no-synonyms warning; explicit bird profile rule for indirect evidence; add `neck` to bird_visible_parts |
| `scripts/audit_pedagogical_media_profile_v1_live_mini_run.py` | updated | Sprint 4: add `schema_errors` list to per-item results; add `top_schema_error_paths`, `examples_by_schema_error_path`, `examples_by_failure_cause` to summary; update DEFAULT_GEMINI_MODEL comment for Sprint 4 model |
| `schemas/pedagogical_media_profile_v1.schema.json` | updated | Sprint 4: add `prompt_version` as optional string to `valid_payload` and `failed_payload`; add `neck` to `bird_visible_parts` enum |
| `tests/test_audit_pedagogical_media_profile_v1_live_mini_run.py` | updated | Sprint 4: add `schema_errors` to fixture helpers; add 9 new diagnostic tests for `top_schema_error_paths`, `examples_by_schema_error_path`, `examples_by_failure_cause`, per-item enum/missing-field details, determinism, skipped report diagnostics |
| `docs/audits/evidence/pedagogical_media_profile_v1_live_mini_run.json` | updated | Sprint 4 second live mini-run evidence |
| `docs/audits/pedagogical-media-profile-v1-sprint4-closure.md` | added | this file |

---

## Sprint 3 baseline summary

| Metric | Value |
|--------|-------|
| `execution_status` | `completed` |
| `model` | `gemini-2.5-flash-lite` |
| `sample_size` | 5 |
| `valid_count` | 0 |
| `failed_count` | 5 |
| `valid_rate` | 0 % |
| `failure_reason_distribution` | `schema_validation_failed: 5` |
| `schema_failure_cause_distribution` | `enum_mismatch: 4`, `missing_required_field: 1` |
| `feedback_rejection_count` | 0 |
| `selection_field_rejection_count` | 0 |
| Sprint 3 decision | `INVESTIGATE_LIVE_FAILURES` |

Sprint 3 interpretation (confirmed by Sprint 4 diagnostics):
- All 5 items reached the model and returned structured JSON.
- Failures were prompt/schema alignment issues, not model failures.
- Sprint 4 deeper diagnostics revealed `prompt_version` was also a root cause
  (additional_property error) masked in Sprint 3 by the more-frequent enum mismatches.

---

## Model selection

**Sprint 4 model used: `gemini-3.1-flash-lite-preview`**

**Discovery:** `ListModels` was called against the Gemini API (`v1beta/models`).
`models/gemini-3.1-flash-lite-preview` was confirmed available as of 4 May 2026.

Available Flash-Lite models (as of Sprint 4 execution):
- `models/gemini-2.0-flash-lite`, `models/gemini-2.0-flash-lite-001`
- `models/gemini-2.5-flash-lite`
- `models/gemini-3.1-flash-lite-preview` ← **Sprint 4 model** (preferred)
- `models/gemini-3.1-flash-image-preview`, `models/gemini-3-flash-preview`

Sprint 3 had used `gemini-2.5-flash-lite` (gemini-2.0-flash-lite not available to new users).

---

## Diagnosis of Sprint 3 failures (Task 2)

The Sprint 3 evidence did not include per-item `schema_errors` lists (added in Sprint 4).
After running Sprint 4 with deeper diagnostics enabled, the root causes became clear:

### First live run in Sprint 4 (before schema fix)

Sprint 4 first run (`gemini-3.1-flash-lite-preview`, no schema fix yet):
- `additional_property: 5` — dominant cause
- All 5 items rejected because `prompt_version` is present in model output but was
  not in the `valid_payload` schema's allowed properties.
- `enum_mismatch: 1` — `bird_visible_parts` item "neck" not in enum.

Conclusion: Sprint 3 enum mismatches masked the `prompt_version` additional_property issue.
After enum normalization fixed enum mismatches, `prompt_version` became the dominant failure.

### Root causes addressed

| Cause | Sprint 3 count | Fix applied |
|-------|---------------|-------------|
| `enum_mismatch` | 4/5 dominant | Prompt hardening (explicit enum lists for all fields) + extended normalization |
| `missing_required_field` | 1/5 dominant | Prompt explicit requirement for `group_specific_profile.bird` even with indirect evidence; feather example added |
| `additional_property` (prompt_version) | masked in Sprint 3 | Schema fix: added `prompt_version` as optional to `valid_payload` and `failed_payload` |
| `enum_mismatch` (neck in bird_visible_parts) | 1 occurrence | Schema fix: added "neck" to bird_visible_parts enum |

---

## Prompt changes (Task 3 + 4)

### Enum constants

Added module-level enum constant strings for all constrained fields:
`_SIGNAL_LEVEL`, `_SIGNAL_LEVEL_WITH_NONE`, `_TECHNICAL_QUALITY_ENUM`,
`_BACKGROUND_CLUTTER_ENUM`, `_FRAMING_ENUM`, `_DISTANCE_ENUM`,
`_VIEW_ANGLE_ENUM`, `_OCCLUSION_ENUM`, `_CONTEXT_VISIBLE_ENUM`,
`_SEX_VALUE_ENUM`, `_LIFE_STAGE_VALUE_ENUM`, `_PLUMAGE_STATE_VALUE_ENUM`,
`_SEASONAL_STATE_VALUE_ENUM`, `_BIO_CONFIDENCE_ENUM`,
`_AMBIGUITY_ENUM`, `_FIELD_MARK_BODY_PART_ENUM`, `_DIFFICULTY_ENUM`,
`_BIRD_POSTURE_ENUM`, `_BIRD_BEHAVIOR_ENUM`, `_BIRD_VISIBLE_PARTS_ENUM`.

### Output skeleton

Updated all `"..."` placeholder values with explicit enum hint strings
(e.g., `"high|medium|low|unknown"`, `"good|acceptable|poor|unknown"`).
Biological profile visible entries now show exact value/confidence/visible_basis hints.

### Indirect evidence valid example

Added `_VALID_RAW_EXAMPLE_INDIRECT`: a complete valid feather example showing:
- `subject_presence: "indirect"` (required for feather)
- `group_specific_profile.bird` present with all required fields
- `posture: "unknown"`, `behavior_visible: "unknown"` (bird not directly visible)
- All biological attributes `unknown` with `confidence: "low"` and `visible_basis: null`

### ENUM CONSTRAINTS prompt section

Added a dedicated ENUM CONSTRAINTS section to the prompt text explicitly listing
allowed values for all ~30 constrained fields. Includes:
- No-synonyms warning: explicit list of forbidden words (fair, moderate, unclear,
  not_visible, excellent, sharp, blurry, close-up, side-on, etc.)
- Instruction: "use exactly one listed value; if uncertain use unknown"

### Bird profile for indirect evidence

Made the requirement more explicit: "group_specific_profile.bird is REQUIRED in ALL
cases, including when evidence_type is feather, egg, nest, track, scat, or burrow.
For indirect evidence, use unknown for posture, behavior_visible, and bird_visible_parts."

---

## Schema changes (Task 5)

Two evidence-based schema additions in `schemas/pedagogical_media_profile_v1.schema.json`:

### 1. `prompt_version` (optional string) in both `valid_payload` and `failed_payload`

**Evidence:** All 5 Sprint 4 items failed with `additional_property: prompt_version`.
The prompt skeleton always includes `prompt_version`, and the model correctly outputs it.
This was a schema oversight — the field belongs in the contract.

**Change:** Added `"prompt_version": {"type": "string", "minLength": 1}` as an optional
property to both `valid_payload` and `failed_payload` (within `additionalProperties: false`).

**Doctrine impact:** None. `prompt_version` is a contract identifier, not a feedback
or selection field. The change preserves all doctrine boundaries.

### 2. `neck` added to `bird_visible_parts` enum

**Evidence:** 1 item in first Sprint 4 run failed with `enum_mismatch` on
`bird_visible_parts.*.item = "neck"`. Neck is a legitimate visible bird body part.

**Change:** Added `"neck"` to the `bird_visible_parts` items enum, the Python
normalization allowed set, and the prompt enum constant `_BIRD_VISIBLE_PARTS_ENUM`.

---

## Normalization changes (Task 6)

Extended `normalize_pedagogical_media_profile_v1` to call `_normalize_known_enum_field`
for all previously uncovered constrained fields:

**Technical profile:** `sharpness`, `lighting`, `contrast` (signal_level),
`background_clutter`, `framing`, `distance_to_subject`.

**Observation profile:** `view_angle`, `occlusion`.
Added `_normalize_string_enum_list` for `context_visible` list items.

**Identification profile:** `ambiguity_level`.

**Pedagogical profile:** `difficulty`, `expert_interest`, `cognitive_load`.

**Biological profile:** Added `_normalize_biological_attribute` helper to normalize
`sex`, `life_stage`, `plumage_state`, `seasonal_state` value and confidence fields.

**Bird profile:** `posture`, `behavior_visible`, `bird_visible_parts` list items,
`plumage_pattern_visible`, `bill_shape_visible`, `wing_pattern_visible`, `tail_shape_visible`.

**Field marks:** `visibility`, `importance`, `body_part` for each visible_field_marks item.

**Doctrine:** All normalization is case/underscore normalization only (e.g., "HIGH" → "high").
No synonym mapping is applied. Unknown values are left unchanged and rejected by the schema.

---

## Deeper diagnostics (Task 1)

### Per-item results

Added `schema_errors` list to each per-item result:
each entry contains `path`, `message`, `validator`, `expected`, `actual`, `cause`.

### Summary

Added to `_compute_summary`:
- `top_schema_error_paths`: ranked list of most-frequent error paths with counts and causes
- `examples_by_schema_error_path`: up to 2 examples per unique error path
- `examples_by_failure_cause`: up to 3 examples per failure cause category

These fields also appear in skipped reports (empty).

---

## Validation commands and results

All checks run on 4 May 2026.

```
python -m pytest tests/test_pedagogical_media_profile_v1.py \
    tests/test_pedagogical_media_profile_prompt_v1.py \
    tests/test_audit_pedagogical_media_profile_v1_fixture_dry_run.py \
    tests/test_audit_pedagogical_media_profile_v1_live_mini_run.py
# 92 passed (83 from Sprint 3 + 9 new Sprint 4 diagnostic tests)

python -m ruff check src/database_core/qualification/pedagogical_media_profile_v1.py \
    src/database_core/qualification/pedagogical_media_profile_prompt_v1.py \
    scripts/audit_pedagogical_media_profile_v1_live_mini_run.py \
    tests/test_audit_pedagogical_media_profile_v1_live_mini_run.py
# All checks passed

python scripts/check_doc_code_coherence.py
# Doc/code coherence checks passed

python scripts/check_docs_hygiene.py
# Docs hygiene checks passed
```

---

## Fixture dry-run result

Run twice during Sprint 4 (before and after schema changes).

```
python scripts/audit_pedagogical_media_profile_v1_fixture_dry_run.py
# decision: READY_FOR_LIVE_MINI_RUN
# valid_count: 7 (unchanged from Sprint 3)
# intended valid fixtures still pass
# intended invalid fixtures still fail
# feedback fields still rejected
# selection fields still rejected
```

---

## Second live mini-run command

```bash
python scripts/audit_pedagogical_media_profile_v1_live_mini_run.py \
  --snapshot-id palier1-be-birds-50taxa-run003-v11-baseline \
  --sample-size 5 \
  --gemini-api-key-env GEMINI_API_KEY \
  --gemini-model gemini-3.1-flash-lite-preview \
  --gemini-concurrency 1 \
  --output-path docs/audits/evidence/pedagogical_media_profile_v1_live_mini_run.json
```

**Model:** `gemini-3.1-flash-lite-preview` — confirmed available via `ListModels` as of
4 May 2026. This is the `gemini-3.1-flash-lite` preview API.

---

## Second live mini-run summary

| Metric | Value |
|--------|-------|
| `schema_version` | `pedagogical_media_profile_live_mini_run.v1` |
| `execution_status` | `completed` |
| `model` | `gemini-3.1-flash-lite-preview` |
| `sample_size` | 5 |
| `valid_count` | 4 |
| `failed_count` | 1 |
| `valid_rate` | 80 % |
| `failure_reason_distribution` | `schema_validation_failed: 1` |
| `schema_failure_cause_distribution` | `invalid_confidence_range: 1` |
| `evidence_type_distribution` | `whole_organism: 4` |
| `organism_group_distribution` | `bird: 4` |
| `average_global_quality_score` | 62.0 |
| `feedback_rejection_count` | 0 |
| `selection_field_rejection_count` | 0 |
| `biological_basis_rejection_count` | 0 |
| `low_basic_identification_valid_count` | 2 |
| `high_indirect_evidence_valid_count` | 0 |

### Remaining failure analysis

The 1 failed item has `schema_failure_cause: invalid_confidence_range`.
Error paths: `biological_profile_visible.sex.confidence`,
`biological_profile_visible.life_stage.confidence`,
`biological_profile_visible.plumage_state.confidence`,
`biological_profile_visible.seasonal_state.confidence`.

**Cause:** The model set `confidence: "high"` for biological attributes with `value:
"unknown"`. The biological consistency rule requires `confidence in {low, medium}` when
value is `unknown` or `not_applicable`.

**Interpretation:** The prompt now explicitly states "confidence must be low or medium
when value is unknown or not_applicable". The model still violated this for 1 out of 5
items. This is a minor residual misalignment. It does not affect the 4 valid items or
the READY decision.

---

## Sprint 3 vs Sprint 4 comparison

| Metric | Sprint 3 | Sprint 4 |
|--------|---------|---------|
| Model | `gemini-2.5-flash-lite` | `gemini-3.1-flash-lite-preview` |
| `sample_size` | 5 | 5 |
| `valid_count` | 0 | **4** |
| `failed_count` | 5 | **1** |
| `valid_rate` | 0 % | **80 %** |
| Dominant failure cause | `enum_mismatch` (4), `missing_required_field` (1) | `invalid_confidence_range` (1) |
| `feedback_rejection_count` | 0 | 0 |
| `selection_field_rejection_count` | 0 | 0 |
| `top_schema_error_paths` | (not captured) | `biological_profile_visible.*.confidence` (1) |
| Sprint decision | `INVESTIGATE_LIVE_FAILURES` | **`READY_FOR_OPT_IN_PIPELINE_INTEGRATION`** |

---

## Final decision

**`READY_FOR_OPT_IN_PIPELINE_INTEGRATION`**

Triggered by:
- `sample_size = 5 >= 5` ✓
- `valid_rate = 0.8 >= 0.8` ✓
- `failed_rate = 0.2 <= 0.2` ✓
- `model_output_invalid_count = 0` ✓
- `feedback_rejection_count = 0` ✓
- `selection_field_rejection_count = 0` ✓
- `doctrine preserved` ✓
- `fixture dry-run still passes` ✓

---

## Next steps — Sprint 5 recommendation

**Recommended Sprint 5 objective:** opt-in pipeline integration for `pedagogical_media_profile.v1`.

Scope for Sprint 5:
- Integrate `pedagogical_media_profile.v1` into the qualification pipeline as an opt-in step
- `v1_1` remains the default pipeline behavior (no runtime changes)
- No runtime-app changes unless explicitly scoped
- No Supabase/Postgres writes until integration is validated
- Consider adding explicit prompt rule for biological confidence (`confidence must be low
  or medium when value is unknown/not_applicable`) to address the 1 residual failure type

Residual risk from Sprint 4:
- 1/5 items fail on `invalid_confidence_range` for biological attributes — minor
  prompt alignment issue; does not affect doctrine; addressable in Sprint 5 or a
  prompt micro-patch before integration.
- `gemini-3.1-flash-lite-preview` is a preview model; monitor for API stability.
