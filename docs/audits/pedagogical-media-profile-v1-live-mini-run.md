---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/audits/pedagogical-media-profile-v1-live-mini-run.md
scope: audit
---

# Pedagogical Media Profile v1 — Controlled Live Mini-Run

## 1. Purpose

This document describes the controlled live mini-run audit for `pedagogical_media_profile.v1`.

The mini-run tests the prompt + live model output + parser + schema + scoring on a small
real media sample, without pipeline integration or runtime-app changes.

Central question:

> Do the prompt, parser, schema, and scoring hold against real live model output?

## 2. Script

```
scripts/audit_pedagogical_media_profile_v1_live_mini_run.py
```

## 3. Command

### With an explicit JSON sample file:

```bash
python scripts/audit_pedagogical_media_profile_v1_live_mini_run.py \
  --sample-file path/to/sample.json \
  --sample-size 5 \
  --gemini-model gemini-2.0-flash-lite \
  --gemini-api-key-env GEMINI_API_KEY
```

### With a snapshot:

```bash
python scripts/audit_pedagogical_media_profile_v1_live_mini_run.py \
  --snapshot-id <snapshot_id> \
  --sample-size 5 \
  --gemini-model gemini-2.0-flash-lite \
  --gemini-api-key-env GEMINI_API_KEY
```

## 4. Sample file format

When using `--sample-file`, provide a JSON array of objects:

```json
[
  {
    "media_id": "optional_id",
    "media_url": "https://example.org/photo.jpg",
    "mime_type": "image/jpeg",
    "expected_scientific_name": "Erithacus rubecula",
    "organism_group": "bird",
    "common_names": {"en": "European Robin"},
    "source_metadata": {},
    "observation_context": {},
    "locale_notes": ""
  }
]
```

Required fields: `media_url`, `expected_scientific_name`, `organism_group`.
Optional: `media_id`, `mime_type`, `common_names`, `source_metadata`,
`observation_context`, `locale_notes`.

## 5. Sample policy

- `--sample-size` must be between 5 and 10 (inclusive).
- When using a snapshot, media assets are sorted deterministically by `source_media_id`
  and the first `sample_size` items are taken.
- When using a sample file, items are taken in order up to `sample_size`.

## 6. Safe skip behavior

If the Gemini API key environment variable is missing or empty, the script does **not**
fail hard. It writes a skipped report with:

- `execution_status: "skipped_missing_credentials"`
- `decision: "SKIPPED_MISSING_CREDENTIALS"`
- `summary.skip_reason: "missing_live_credentials"`

This allows CI to run the test suite safely without live credentials.

## 7. Metrics collected

The report includes:

- `valid_count` — items parsed as `review_status=valid`
- `failed_count` — items parsed as `review_status=failed`
- `failure_reason_distribution` — breakdown of failure reasons
- `schema_failure_cause_distribution` — breakdown of schema validation failure causes
- `evidence_type_distribution` — distribution of `evidence_type` values (valid items only)
- `organism_group_distribution` — distribution of `organism_group` values (valid items only)
- `average_global_quality_score` — mean global quality score (valid items only)
- `average_usage_scores` — mean usage scores per category (valid items only)
- `low_basic_identification_valid_count` — valid items with `basic_identification < 50`
- `high_indirect_evidence_valid_count` — valid items with `indirect_evidence_learning >= 80`
- `feedback_rejection_count` — items where a feedback field was detected and rejected
- `selection_field_rejection_count` — items where a selection field was detected and rejected
- `biological_basis_rejection_count` — items with invalid biological basis violations
- `qualitative_examples` — up to 3 valid and 3 failed examples with excerpts
- `per_item_results` — full per-item diagnostic summaries
- `credential_env_name` — name of the env var used (never the secret value itself)

## 8. Decision thresholds

| Decision | Condition |
|---|---|
| `READY_FOR_OPT_IN_PIPELINE_INTEGRATION` | `valid_rate >= 0.8`, `failed_rate <= 0.2`, `feedback_rejection_count == 0`, `selection_field_rejection_count == 0`, `model_output_invalid == 0` |
| `ADJUST_PROMPT_OR_SCHEMA` | `0.4 <= valid_rate < 0.8`, failures are mostly schema/prompt misalignment |
| `INVESTIGATE_LIVE_FAILURES` | `valid_rate < 0.4`, or `model_output_invalid > 0` |
| `SKIPPED_MISSING_CREDENTIALS` | API credentials absent |

## 9. Boundaries preserved

This script preserves all `pedagogical_media_profile.v1` doctrine:

- AI provides qualitative signals only
- System computes all deterministic scores
- No feedback fields accepted
- No quiz/pack/runtime final selection fields accepted
- No taxonomic override
- Live failures fail closed: error paths produce `review_status=failed` results
- No datastore writes, no pipeline integration, no runtime-app changes

## 10. Expected output path

```
docs/audits/evidence/pedagogical_media_profile_v1_live_mini_run.json
```

This file is not committed to the repository (it contains live run evidence
and may contain media excerpts). It is gitignored or treated as a local artifact.
