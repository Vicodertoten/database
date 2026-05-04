---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-04
source_of_truth: docs/audits/pedagogical-media-profile-v1-fixture-dry-run.md
scope: audit
---

# Pedagogical Media Profile v1 Fixture Dry-Run Audit

## 1. Goal

Validate offline model-like fixtures for `pedagogical_media_profile.v1` before any live
Gemini mini-run.

This audit verifies that fixture outputs are parsed, schema-validated, scored, and
classified with deterministic behavior.

## 2. Scope

Included:

- fixture loading from `tests/fixtures/pedagogical_media_profile_v1/raw_model_outputs`
- parser invocation with `parse_pedagogical_media_profile_v1`
- parser output validation with `is_valid_pedagogical_media_profile_v1`
- metric aggregation and deterministic decision
- JSON evidence report generation

Excluded:

- live model calls
- runtime app integration
- pipeline materialization
- datastore writes

## 3. Artifact surfaces

- script: `scripts/audit_pedagogical_media_profile_v1_fixture_dry_run.py`
- evidence JSON: `docs/audits/evidence/pedagogical_media_profile_v1_fixture_dry_run.json`
- fixture corpus: `tests/fixtures/pedagogical_media_profile_v1/`

## 4. Decision policy

Decision is `READY_FOR_LIVE_MINI_RUN` only when all checks pass:

- all intended valid fixtures parse to `review_status=valid`
- all intended invalid fixtures fail with expected failure reasons/causes
- at least one valid fixture keeps low `basic_identification`
- at least one valid fixture keeps high `indirect_evidence_learning`
- forbidden feedback fields are rejected
- no selection field acceptance is detected

Fallback decisions:

- `INVESTIGATE_FIXTURE_FAILURES` for fixture/expectation mismatches or invalid parser outputs
- `ADJUST_PROMPT_OR_SCHEMA` when fixtures parse but quality gates do not pass

## 5. Current dry-run results

Based on `docs/audits/evidence/pedagogical_media_profile_v1_fixture_dry_run.json`:

- `fixture_count`: 10
- `valid_count`: 7
- `failed_count`: 3
- `schema_validation_failed_count`: 2
- `model_output_invalid_count`: 0
- `feedback_rejection_count`: 1
- `biological_basis_rejection_count`: 1
- `average_global_quality_score`: 63.29
- `decision`: `READY_FOR_LIVE_MINI_RUN`

Distribution highlights:

- `evidence_type_distribution` spans direct and indirect evidence
- `organism_group_distribution` is fully bird-scoped for this fixture set
- low-basic-identification valid fixtures remain valid (5 cases)
- high-indirect-evidence valid fixtures remain valid (3 cases)

## 6. Reproduce

Run script and overwrite evidence:

```bash
python scripts/audit_pedagogical_media_profile_v1_fixture_dry_run.py
```

Optional custom paths:

```bash
python scripts/audit_pedagogical_media_profile_v1_fixture_dry_run.py \
  --fixture-root tests/fixtures/pedagogical_media_profile_v1 \
  --raw-fixture-dir tests/fixtures/pedagogical_media_profile_v1/raw_model_outputs \
  --output-path docs/audits/evidence/pedagogical_media_profile_v1_fixture_dry_run.json
```
