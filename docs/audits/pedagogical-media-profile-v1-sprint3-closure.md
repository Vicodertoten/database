---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/audits/pedagogical-media-profile-v1-sprint3-closure.md
scope: audit
---

# Sprint 3 closure — pedagogical_media_profile.v1 controlled live mini-run

## Purpose

Document the outcome of Sprint 3 for `pedagogical_media_profile.v1`.
This sprint hardened the prompt contract, added the live mini-run script, added
tests with safe-skip behavior, executed a controlled live mini-run, and produces
a final decision and next-sprint recommendation.

---

## Scope

- prompt hardening (Issue 1)
- live mini-run script (Issue 2)
- tests and safe-skip behavior (Issue 3)
- live mini-run execution and closure (this issue)

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
| `src/database_core/qualification/pedagogical_media_profile_prompt_v1.py` | updated | Sprint 3 Issue 1: output skeleton, valid/failed examples, forbidden fields list, bird group rule |
| `tests/test_pedagogical_media_profile_prompt_v1.py` | updated | 8 new hardening tests (54 total) |
| `docs/audits/pedagogical-media-profile-v1-prompt-contract.md` | updated | §5 forbidden fields, §6 bird group rule, §8 output skeleton, §9 raw examples |
| `scripts/audit_pedagogical_media_profile_v1_live_mini_run.py` | added | Sprint 3 Issue 2: controlled live mini-run audit script |
| `tests/test_audit_pedagogical_media_profile_v1_live_mini_run.py` | added | Sprint 3 Issues 2–3: 26 tests (safe-skip, mocked runs, doctrine, sample validation) |
| `docs/audits/pedagogical-media-profile-v1-live-mini-run.md` | added | Sprint 3 Issue 2: live mini-run audit documentation |
| `docs/audits/evidence/pedagogical_media_profile_v1_live_mini_run.json` | added | Sprint 3 Issue 4: live evidence JSON |
| `docs/audits/pedagogical-media-profile-v1-sprint3-closure.md` | added | this file |

---

## Validation results

All checks run on 4 May 2026.

```
python -m pytest tests/test_pedagogical_media_profile_v1.py \
    tests/test_pedagogical_media_profile_prompt_v1.py \
    tests/test_audit_pedagogical_media_profile_v1_fixture_dry_run.py \
    tests/test_audit_pedagogical_media_profile_v1_live_mini_run.py
# 83 passed

python -m ruff check <all Sprint 3 files>
# All checks passed

python scripts/check_doc_code_coherence.py
# Doc/code coherence checks passed

python scripts/check_docs_hygiene.py
# Docs hygiene checks passed

python scripts/verify_repo.py
# Repository verification complete
```

---

## Live mini-run execution

### Command

```bash
python scripts/audit_pedagogical_media_profile_v1_live_mini_run.py \
  --snapshot-id palier1-be-birds-50taxa-run003-v11-baseline \
  --sample-size 5 \
  --gemini-api-key-env GEMINI_API_KEY \
  --gemini-model gemini-2.5-flash-lite \
  --gemini-concurrency 1 \
  --output-path docs/audits/evidence/pedagogical_media_profile_v1_live_mini_run.json
```

**Note on model selection:** `gemini-2.0-flash-lite` and `gemini-2.0-flash` returned
HTTP 404 "no longer available to new users". `gemini-2.5-flash-lite` was selected as
the lightest available model confirmed via `ListModels`.

### Evidence path

```
docs/audits/evidence/pedagogical_media_profile_v1_live_mini_run.json
```

---

## Live mini-run summary

| Metric | Value |
|--------|-------|
| `schema_version` | `pedagogical_media_profile_live_mini_run.v1` |
| `execution_status` | `completed` |
| `model` | `gemini-2.5-flash-lite` |
| `sample_size` | 5 |
| `valid_count` | 0 |
| `failed_count` | 5 |
| `valid_rate` | 0 % |
| `failure_reason_distribution` | `schema_validation_failed: 5` |
| `schema_failure_cause_distribution` | `enum_mismatch: 4`, `missing_required_field: 1` |
| `evidence_type_distribution` | (empty — no valid items) |
| `organism_group_distribution` | (empty — no valid items) |
| `average_global_quality_score` | 0.0 |
| `feedback_rejection_count` | 0 |
| `selection_field_rejection_count` | 0 |

---

## Decision

**`INVESTIGATE_LIVE_FAILURES`**

Triggered by: `valid_rate = 0.0 < 0.4` (decision threshold).

---

## Interpretation

The decision threshold `INVESTIGATE` was triggered by a 0 % valid rate.
However, the raw evidence shows a different underlying pattern:

- All 5 items **reached the model** and received a structured JSON response.
- All 5 failures are `schema_validation_failed`, **not** `model_output_invalid`.
- Root cause is **prompt/schema alignment**, not a fundamental model or network issue.

Specific observations:

1. **Enum mismatch (4/5):** The model generates plausible values that are not in the
   schema's allowed enum sets. For example, the prompt skeleton and examples do not
   exhaustively enumerate all allowed values for every field, so the model improvises.

2. **Missing required field (1/5):** One item omits a field the schema requires.

3. **Forbidden field rejections:** 0 — the model correctly omits `scores`,
   `feedback`, and selection fields. Doctrine is preserved.

4. **Structure integrity:** The JSON structure (top-level keys, nested blocks) is
   correct in all 5 outputs. The failures are value-level, not structure-level.

These observations indicate the prompt is close but the schema contract needs
tighter value enumeration in the prompt text, or the schema needs relaxation for
a small number of edge fields.

---

## Known limitations

- Sample size is 5 (minimum valid), which is small for statistical confidence.
- All 5 sampled images are birds from a single snapshot (palier1-be-birds-50taxa-run003).
- Only one model tested (gemini-2.5-flash-lite).
- The `gemini-2.0-flash-lite` default is deprecated; the `DEFAULT_GEMINI_MODEL`
  constant in the script should be updated before the next run.

---

## Next phase recommendation

**Sprint 4: Prompt/schema alignment pass + second live mini-run**

Do not integrate the pipeline yet.

Recommended actions:

1. Inspect the evidence JSON for the exact failing enum paths and values:
   run `collect_schema_validation_errors_pmp_v1` on each raw output to list paths.

2. For each mismatched enum field, either:
   - add the missing allowed value to the schema enum (if semantically valid), or
   - add explicit per-field allowed-value lists to the prompt text.

3. For the missing required field: identify the field and add an explicit prompt
   reminder or default value in the output skeleton.

4. Update `DEFAULT_GEMINI_MODEL` in the live mini-run script to `gemini-2.5-flash-lite`
   or another currently available model.

5. Re-run the live mini-run with `--sample-size 5` (or 10 for more confidence)
   after prompt/schema changes.

6. If `valid_rate >= 0.8` and `feedback_rejection_count == 0` and
   `selection_field_rejection_count == 0`, proceed to Sprint 4 pipeline integration
   under opt-in flag.

**Default behavior, runtime app, and pipeline are unchanged.**
