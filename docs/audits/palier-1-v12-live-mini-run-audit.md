---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-03
source_of_truth: docs/audits/palier-1-v12-live-mini-run-audit.md
scope: audit
---

# Palier 1 v1.2 Live Mini Run Audit

## 1. Purpose

This audit validates the newly wired live Gemini path for bird image review contract
`v1_2` under controlled conditions.

It is intentionally limited:

- not a full Palier-1 v1.2 materialization run
- not distractor v1.2 implementation
- not a runtime-app task

It compares `v1_1` vs `v1_2` on the same mini sample and produces an evidence report.

## 2. Script

- Script: `scripts/audit_bird_image_review_v12_live_mini_run.py`
- Evidence output (default):
  `docs/audits/evidence/bird_image_review_v12_live_mini_run.json`

## 3. Command

```bash
python scripts/audit_bird_image_review_v12_live_mini_run.py \
  --snapshot-id <snapshot_id> \
  --sample-size 5 \
  --gemini-api-key-env GEMINI_API_KEY \
  --gemini-model gemini-3.1-flash-lite-preview \
  --output-path docs/audits/evidence/bird_image_review_v12_live_mini_run.json
```

Optional alternatives:

- use `--snapshot-manifest-path <path/to/manifest.json>`
- use `--gemini-concurrency <n>` for controlled parallelism

## 4. Required Environment Variables

- `GEMINI_API_KEY` (or custom env var via `--gemini-api-key-env`)

No secret value is written to the report.

## 5. Safe Skip Behavior

If live credentials are missing, the script does not fail hard.
It produces a structured skipped report:

- `execution_status=skipped_missing_credentials`
- `decision=INVESTIGATE_LIVE_FAILURES`
- `summary.skip_reason=missing_live_credentials`

This keeps CI deterministic while preserving fixture-based dry-run coverage.

## 6. Sample Policy

- controlled sample size in range `[5,10]` (`--sample-size`)
- deterministic selection from pre-AI eligible media in snapshot order
- same sample used for both `v1_1` and `v1_2`

## 7. Metrics Collected

Summary fields include:

- `sample_size`
- `v1_1_success_count`
- `v1_2_success_count`
- `v1_2_fail_closed_count`
- `v1_2_failure_reason_distribution`
- `v1_1_average_score_if_available`
- `v1_2_average_score`
- `v1_2_score_decomposition_average`
- `feedback_completeness_rate`
- `feedback_image_specificity_rate`
- `generic_feedback_rate`
- `profiles_mature_playable_count`
- `profiles_blocked_by_v1_2_policy_count`
- `qualitative_v1_2_feedback_examples`

Per-image evidence includes:

- status and flags for `v1_1` and `v1_2`
- normalized `v1_2` review payload
- `v1_2` deterministic score payload
- `post_answer_feedback`
- profile/export eligibility summaries

## 8. Interpretation Guide

- High `v1_2_success_count` + low `v1_2_fail_closed_count` indicates stable live parsing.
- High `feedback_completeness_rate` and high `feedback_image_specificity_rate` indicate
  usable pedagogical feedback.
- High `generic_feedback_rate` indicates prompt/validation quality issues to correct.
- `profiles_blocked_by_v1_2_policy_count` should track fail-closed behavior.

## 9. Decision Field

The report writes one final decision:

- `READY_FOR_DISTRACTORS_V1_2`
- `ADJUST_PROMPT_OR_VALIDATION`
- `INVESTIGATE_LIVE_FAILURES`

Current thresholds for `READY_FOR_DISTRACTORS_V1_2`:

- v1.2 parse/validation success rate `>= 80%`
- v1.2 fail-closed rate `<= 20%`
- feedback completeness rate `>= 80%`
- generic feedback rate `<= 30%`
- no runtime contract regression

## 10. Boundaries Preserved

This audit keeps all active program constraints:

- `v1_1` remains default behavior
- `v1_2` remains opt-in
- no change to `selectedOptionId`
- no runtime contract changes
- no playable question contract changes
- no distractor v1.2 implementation

## 11. Latest Evidence (Controlled Live Mini-Run)

Evidence file:

- `docs/audits/evidence/bird_image_review_v12_live_mini_run.json`

Latest recorded run summary:

- snapshot: `palier1-be-birds-50taxa-run003-v11-baseline`
- sample_size: `5`
- v1.1 success: `5/5`
- v1.2 success: `0/5`
- v1.2 fail-closed: `5/5`
- v1.2 failure reasons: `schema_validation_failed=5`
- v1.1 average score (if available): `51.2`
- v1.2 average score: `0.0`
- profiles mature/playable (v1.2 path): `0`
- profiles blocked by v1.2 policy: `5`
- decision: `INVESTIGATE_LIVE_FAILURES`

Interpretation:

- live v1.2 prompt/parser wiring is active and fail-closed behavior is enforced
- runtime contract regression was not detected
- next step is prompt/schema alignment hardening before distractor v1.2 work
