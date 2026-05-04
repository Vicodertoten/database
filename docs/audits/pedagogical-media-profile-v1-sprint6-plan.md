---
owner: database
status: planned
last_reviewed: 2026-05-04
source_of_truth: docs/audits/pedagogical-media-profile-v1-sprint6-plan.md
scope: audit
---

# Sprint 6 — Controlled profiled snapshot run

**Sprint:** 6  
**Status:** planned  
**Date:** 2026-05  
**Prerequisite:** pre-Sprint-6 readiness pass complete (see
`docs/audits/pedagogical-media-profile-v1-pre-sprint6-readiness.md`)

---

## Objective

Run `qualify-inat-snapshot` with
`--ai-review-contract-version pedagogical_media_profile_v1` on a controlled
bird-only snapshot. Produce an `ai_outputs.json` file containing PMP outcomes.
Audit validity rates, score distributions, cost/latency (if available), and
decide whether PMP is ready for a controlled profiled corpus run or whether
PMP-specific policy work is needed first.

---

## Scope

| Item | In scope |
|---|---|
| Bird-only snapshot | ✅ |
| Gemini 3.1 Flash-Lite Preview | ✅ |
| PMP opt-in (explicit selector) | ✅ |
| Output: `ai_outputs.json` with PMP outcomes | ✅ |
| Audit of validity / score distributions | ✅ |
| Manual review of a small sample | ✅ |
| Runtime changes | ❌ |
| Materialization | ❌ |
| Supabase/Postgres writes by default | ❌ |
| Default behavior change | ❌ |
| Multi-taxon routing | ❌ |
| PMP-specific qualification policy | ❌ |
| Pack generation | ❌ |

---

## Recommended command

```bash
./.venv/bin/python -m database_core.cli qualify-inat-snapshot \
  --snapshot-id palier1-be-birds-50taxa-run003-v11-baseline \
  --ai-review-contract-version pedagogical_media_profile_v1 \
  --gemini-model gemini-3.1-flash-lite-preview \
  --gemini-concurrency 1 \
  --gemini-api-key-env GEMINI_API_KEY
```

Notes:
- Use `./.venv/bin/python` (not system Python).
- `--gemini-concurrency 1` is conservative; increase if latency is acceptable.
- Model override `--gemini-model` allows fallback to another model without code
  changes; do not silently change the model default.
- No `--database-url` needed; default output is `ai_outputs.json` in the snapshot
  directory.

---

## Metrics to collect

### Generation metrics

| Metric | Description |
|---|---|
| `processed_media_count` | Total media processed |
| `images_sent_to_gemini_count` | Images that reached the Gemini API |
| `status_distribution` | Distribution of `AIQualificationOutcome.status` |
| `pmp_valid_count` | Outcomes with `review_status == "valid"` |
| `pmp_failed_count` | Outcomes with `review_status != "valid"` |
| `pmp_valid_rate` | `pmp_valid_count / images_sent_to_gemini_count` |
| `failure_reason_distribution` | Distribution of `failure_reason` values |
| `schema_failure_cause_distribution` | Distribution of schema-level failure causes |
| `evidence_type_distribution` | Distribution of `evidence_type` |
| `organism_group_distribution` | Distribution of `organism_group` (must be all `bird`) |

### Score metrics

| Metric | Description |
|---|---|
| `average_global_quality_score` | Mean of `scores.global_quality_score` |
| `average_usage_scores` | Mean of each usage score across valid profiles |
| `low_basic_identification_valid_count` | Valid profiles with `basic_identification < 50` |
| `high_indirect_evidence_valid_count` | Valid profiles with `indirect_evidence_learning >= 70` |

### Policy/legacy metrics

| Metric | Description |
|---|---|
| `qualification_none_count` | Count of outcomes with `qualification=None` (expected: all) |
| `legacy_policy_rejection_count` | Resources rejected by legacy qualification policy due to `qualification=None` |

### Operational metrics (if available)

| Metric | Description |
|---|---|
| `cost_estimate` | API cost estimate |
| `latency_estimate` | Mean call latency (ms) |

### Manual review

Select 5–10 sample profiles for manual inspection:
- At least 2 high-quality valid profiles
- At least 1 failed profile, if available
- At least 1 partial-organism or indirect-evidence profile, if available

---

## Critical distinction

Sprint 6 must distinguish:

1. **PMP profile generation success** — did Gemini return a valid PMP structure?
2. **Legacy qualification/export policy effects** — did the resource get rejected
   because `qualification=None` triggered legacy policy?

`qualification=None` is an intentional Sprint 5 design choice. It is **not** a
failure of PMP generation. Do not treat it as such in the audit.

---

## Audit step (required — do not skip)

Sprint 6 does **not** end after producing `ai_outputs.json`. The run must be
followed by a full audit pass:

1. Read `ai_outputs.json` (or the equivalent output artifact).
2. Aggregate the following metrics:
   - PMP validity rate (`pmp_valid_rate`)
   - Score distributions across `overall_score` and sub-scores
   - Evidence type distribution (`evidence_types`)
   - Failure reason breakdown (grouped by `failure_reason`)
   - `qualification_none_count` (profiles where `qualification=None` was returned
     as the intended Sprint 5 behavior)
3. Select a manual review sample (see section above).
4. Write an **evidence JSON** capturing the aggregated metrics and sample pointers.
5. Write a **closure doc** recording the Sprint 6 findings, the decision label
   applied, and next steps.

The closure doc is the official hand-off artifact. Sprint 6 is not complete until
both the evidence JSON and the closure doc exist.

---

## Decision labels

After the run, apply one of:

### `READY_FOR_PMP_POLICY_DESIGN`

Criteria:
- `pmp_valid_rate >= 80%`
- `ai_outputs.json` contains PMP profiles
- No feedback/selection field pollution
- Failures are explainable (schema drift, not_a_bird, etc.)
- Snapshot round-trip works
- `qualification=None` behavior is understood and documented

Meaning: PMP generation is reliable enough to design a PMP-specific qualification
policy as next step.

### `READY_FOR_CONTROLLED_PROFILED_CORPUS_RUN`

Criteria:
- `pmp_valid_rate >= 90%`
- Score and evidence distributions look plausible
- Manual review of sample is acceptable
- Cost/latency acceptable
- No integration regressions

Meaning: PMP is ready to run on the full profiled corpus.

### `ADJUST_PMP_PIPELINE_INTEGRATION`

Criteria:
- `pmp_valid_rate` 60–80%
- Mostly schema/prompt/cache issues
- No doctrine pollution

Meaning: Pipeline integration has fixable issues. Do not proceed to policy design.

### `INVESTIGATE_PMP_PIPELINE_FAILURES`

Criteria (any of):
- `pmp_valid_rate < 60%`
- `model_output_invalid` failure appears frequently
- `ai_outputs.json` is broken or unreadable
- Cached/readback is broken
- Legacy default was accidentally changed
- Feedback/selection field pollution detected

Meaning: There is a systemic issue requiring investigation before re-running.

---

## Non-goals for Sprint 6

- No runtime changes
- No materialization
- No Supabase/Postgres writes by default
- No default behavior change (v1_1 remains default)
- No multi-taxon routing
- No PMP-specific qualification policy (that may follow if decision is
  `READY_FOR_PMP_POLICY_DESIGN`)
- No pack generation
- No feedback fields
- No distractors
