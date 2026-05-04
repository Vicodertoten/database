---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/audits/pedagogical-media-profile-v1-post-sprint6-stabilization.md
scope: audit
---

# Post-Sprint-6 stabilization - pedagogical_media_profile_v1

## Purpose

Stabilize Sprint 6 evidence quality before Sprint 7 planning, with explicit
focus on schema validation failures, audit diagnostic depth, and interpretation
clarity.

This is not Sprint 7 policy implementation.

## Scope

In scope:
- deep analysis of Sprint 6 failed PMP outcomes,
- hardened audit diagnostics,
- better manual review sample representativeness,
- score metrics by evidence type,
- scientific-name metadata join for manual samples,
- controlled subset documentation,
- global_quality_score interpretation clarification.

Out of scope:
- runtime changes,
- materialization,
- Supabase/Postgres writes by default,
- PMP-specific qualification policy implementation,
- pack generation,
- default behavior change.

## Sprint 6 recap

- Controlled snapshot id:
  `palier1-be-birds-50taxa-run003-v11-baseline-sprint6-controlled-120`
- Processed media: 120
- Sent to Gemini: 116
- `ok`: 106
- `pedagogical_media_profile_failed`: 10
- pre-AI filtered: 4 (`insufficient_resolution_pre_ai`)
- `pmp_valid_rate`: 0.9138
- decision at Sprint 6 close: `READY_FOR_CONTROLLED_PROFILED_CORPUS_RUN`

## What was validated in stabilization

- `ai_outputs.json` remained available and readable.
- Failure diagnostics are now actionable and aggregated.
- Schema failure causes and top paths are now populated.
- Failure examples are grouped by cause and path.
- Manual review sample now recognizes indirect/complex evidence categories.
- score metrics by evidence_type are now available.
- scientific_name is now populated in manual sample when metadata is available.
- Doctrine guardrails are preserved (no feedback/selection/runtime pollution).

## What was not validated

- runtime readiness was not validated,
- materialization readiness was not validated,
- PMP-specific qualification policy was not implemented,
- cost/latency were not measured in Sprint 6 artifacts (explicitly documented as
  not measured).

## Changes made in this stabilization pass

- Hardened audit script:
  `scripts/audit_pedagogical_media_profile_v1_snapshot_outputs.py`
  - robust schema error cause extraction from `cause`, `type`, `validator`,
    `schema_failure_cause`, `error_type`,
  - robust schema path extraction from `path`, `loc`, `instance_path`,
    `json_path`,
  - added `top_schema_error_paths`, `examples_by_failure_cause`,
    `examples_by_schema_error_path`, `failed_items_summary`,
  - added `score_metrics_by_evidence_type`,
  - improved manual sample selection and coverage reporting,
  - added metadata join from snapshot manifest/response files for
    `scientific_name`, `canonical_taxon_id`, `source_taxon_id`.

- Expanded tests:
  `tests/test_audit_pedagogical_media_profile_v1_snapshot_outputs.py`
  - diagnostic key variants and path variants,
  - top path aggregation,
  - examples by cause/path,
  - indirect and multiple evidence sampling,
  - no-failure behavior when categories are missing,
  - per-evidence score metrics,
  - metadata join behavior.

- Added failure analysis evidence:
  `docs/audits/evidence/pedagogical_media_profile_v1_sprint6_failure_analysis.json`

- Updated Sprint 6 evidence JSON with hardened diagnostics:
  `docs/audits/evidence/pedagogical_media_profile_v1_sprint6_snapshot_audit.json`

- Added subset documentation:
  `docs/audits/pedagogical-media-profile-v1-sprint6-controlled-subset.md`

- Clarified score interpretation in foundation contract doc:
  `docs/foundation/pedagogical-media-profile-v1.md`

## Failure analysis summary

From Sprint 6 controlled run:
- failed PMP outcomes: 10
- failure_reason distribution: `schema_validation_failed = 10`

Schema failure causes (after stabilization extraction):
- `maxItems`: 6
- `enum_mismatch`: 2
- `invalid_biological_basis`: 1
- `invalid_confidence_range`: 1

Top schema error paths:
- `group_specific_profile.bird.bird_visible_parts` (6)
- `biological_profile_visible.seasonal_state.visible_basis` (1)
- `biological_profile_visible.sex.confidence` (1)

Interpretation:
- most failures are concentrated and explainable,
- dominant issue is an overlong `bird_visible_parts` list,
- remaining issues are biological consistency and enum/value conformance.

## Manual review sample improvements

Sampling now attempts (if available):
- at least 2 high-quality valid whole-organism profiles,
- at least 1 failed profile,
- at least 1 indirect evidence profile,
- at least 1 partial or multiple-organisms profile,
- at least 1 low basic_identification valid profile,
- optional low global-quality valid profile.

Coverage is now reported explicitly in
`manual_review_sample_coverage`.

## Evidence-type metrics improvements

`score_metrics.score_metrics_by_evidence_type` now reports for each evidence type:
- count / valid_count / failed_count / valid_rate,
- average global score,
- average usage scores,
- score min/max,
- low basic-identification valid count,
- high indirect-evidence-learning valid count.

## Scientific name metadata status

`metadata_join_status` is now explicit.
For Sprint 6 controlled snapshot:
- status: `joined_from_manifest`
- manual sample scientific names are populated from snapshot metadata.

## Controlled subset documentation status

Subset creation method and limitations are now documented in:
`docs/audits/pedagogical-media-profile-v1-sprint6-controlled-subset.md`

## global_quality_score clarification

`global_quality_score` is explicitly documented as:
- broad multi-use quality signal,
- not a final selection score,
- insufficient alone for pack/quiz selection,
- must be interpreted with usage_scores,
- compatible with high-quality indirect evidence profiles that still have low
  basic_identification.

## Validation commands and results

```bash
./.venv/bin/python -m pytest \
  tests/test_pedagogical_media_profile_v1.py \
  tests/test_pedagogical_media_profile_prompt_v1.py \
  tests/test_sprint5_pmp_pipeline.py \
  tests/test_ai.py \
  tests/test_inat_qualification.py \
  tests/test_inat_snapshot.py \
  tests/test_audit_pedagogical_media_profile_v1_snapshot_outputs.py \
  -q

./.venv/bin/python -m ruff check \
  src/database_core/qualification/pedagogical_media_profile_v1.py \
  src/database_core/qualification/pedagogical_media_profile_prompt_v1.py \
  src/database_core/qualification/ai.py \
  src/database_core/cli.py \
  src/database_core/adapters/inaturalist_qualification.py \
  scripts/audit_pedagogical_media_profile_v1_snapshot_outputs.py \
  tests/test_audit_pedagogical_media_profile_v1_snapshot_outputs.py \
  tests/test_sprint5_pmp_pipeline.py

./.venv/bin/python scripts/check_docs_hygiene.py
./.venv/bin/python scripts/check_doc_code_coherence.py
./.venv/bin/python scripts/verify_repo.py
```

Result: pass (reported in this stabilization pass).

## Final decision

**`READY_FOR_SPRINT_7_PMP_POLICY_DESIGN`**

Rationale:
- failures are now diagnosable and actionable,
- schema diagnostics are populated and structured,
- manual review sample is more representative,
- score-by-evidence-type metrics are present,
- no doctrine regression detected,
- tests and documentation checks pass.

## Recommended Sprint 7 scope

Primary scope:
- design PMP-specific qualification policy thresholds and routing, grounded in
  usage_scores and evidence_type-aware interpretation.

Guardrails for Sprint 7:
- keep runtime/materialization out of scope,
- keep v1_1/v1_2 as legacy references only,
- do not reintroduce feedback or selection/runtime fields into PMP contract.
