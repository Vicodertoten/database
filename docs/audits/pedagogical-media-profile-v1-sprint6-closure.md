---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/audits/pedagogical-media-profile-v1-sprint6-closure.md
scope: audit
---

# Sprint 6 closure - controlled profiled snapshot run (pedagogical_media_profile_v1)

**Sprint:** 6  
**Status:** closed  
**Date:** 2026-05-04

---

## Purpose

Execute a real `qualify-inat-snapshot` run with
`--ai-review-contract-version pedagogical_media_profile_v1` on a controlled
bird-only snapshot, then audit `ai_outputs.json` and apply an explicit decision
label.

---

## Scope and run profile

- In scope: controlled bird-only run, PMP output generation, structured audit,
  evidence JSON, closure decision.
- Out of scope: runtime changes, materialization, pack generation,
  selectedOptionId changes, Supabase/Postgres writes by default, multi-taxon
  routing, PMP policy implementation.

### Run size adaptation

The baseline snapshot `palier1-be-birds-50taxa-run003-v11-baseline` contains
1493 media items, which is too large for a controlled Sprint 6 validation run.
A deterministic controlled subset snapshot was created:

- snapshot id:
  `palier1-be-birds-50taxa-run003-v11-baseline-sprint6-controlled-120`
- selected media count: 120
- kept taxa with at least one selected media: 36

---

## Commands run

### Pre-run validation

```bash
./.venv/bin/python -m pytest \
  tests/test_pedagogical_media_profile_v1.py \
  tests/test_pedagogical_media_profile_prompt_v1.py \
  tests/test_sprint5_pmp_pipeline.py \
  tests/test_ai.py \
  tests/test_inat_qualification.py \
  tests/test_inat_snapshot.py \
  -q

./.venv/bin/python -m ruff check \
  src/database_core/qualification/pedagogical_media_profile_v1.py \
  src/database_core/qualification/pedagogical_media_profile_prompt_v1.py \
  src/database_core/qualification/ai.py \
  src/database_core/cli.py \
  src/database_core/adapters/inaturalist_qualification.py \
  tests/test_pedagogical_media_profile_v1.py \
  tests/test_pedagogical_media_profile_prompt_v1.py \
  tests/test_sprint5_pmp_pipeline.py

./.venv/bin/python scripts/check_docs_hygiene.py
./.venv/bin/python scripts/check_doc_code_coherence.py
./.venv/bin/python scripts/verify_repo.py
```

Results:
- tests: 127 passed
- ruff: all checks passed
- docs hygiene/coherence: passed
- verify_repo: repository verification complete

### Live run execution

```bash
set -a && source .env && set +a

./.venv/bin/python -m database_core.cli qualify-inat-snapshot \
  --snapshot-id palier1-be-birds-50taxa-run003-v11-baseline-sprint6-controlled-120 \
  --ai-review-contract-version pedagogical_media_profile_v1 \
  --gemini-model gemini-3.1-flash-lite-preview \
  --gemini-concurrency 6 \
  --gemini-api-key-env GEMINI_API_KEY
```

Run result:
- live run executed: yes
- model: `gemini-3.1-flash-lite-preview`
- parallel mode: enabled (`--gemini-concurrency 6`)
- `ai_outputs.json` generated: yes

ai_outputs path:
`data/raw/inaturalist/palier1-be-birds-50taxa-run003-v11-baseline-sprint6-controlled-120/ai_outputs.json`

---

## Evidence artifact

Evidence JSON path:
`docs/audits/evidence/pedagogical_media_profile_v1_sprint6_snapshot_audit.json`

Generated with:

```bash
./.venv/bin/python scripts/audit_pedagogical_media_profile_v1_snapshot_outputs.py \
  --snapshot-id palier1-be-birds-50taxa-run003-v11-baseline-sprint6-controlled-120 \
  --output-path docs/audits/evidence/pedagogical_media_profile_v1_sprint6_snapshot_audit.json
```

---

## Generation metrics summary

- processed_media_count: 120
- images_sent_to_gemini_count: 116
- status_distribution:
  - ok: 106
  - pedagogical_media_profile_failed: 10
  - insufficient_resolution_pre_ai: 4
- pmp_valid_count: 106
- pmp_failed_count: 10
- pmp_valid_rate: 0.9138
- failure_reason_distribution: schema_validation_failed=10
- evidence_type_distribution:
  - whole_organism: 92
  - multiple_organisms: 7
  - nest: 3
  - feather: 2
  - habitat: 1
  - dead_organism: 1
- organism_group_distribution: bird=106

---

## Score metrics summary

- average_global_quality_score: 72.62
- average_usage_scores:
  - basic_identification: 63.66
  - field_observation: 78.97
  - confusion_learning: 63.29
  - morphology_learning: 64.57
  - species_card: 63.63
  - indirect_evidence_learning: 9.51
- score_min_max: min=32, max=100
- low_basic_identification_valid_count: 39
- high_indirect_evidence_valid_count: 7

---

## Policy/legacy metrics summary

- qualification_none_count: 120
- legacy_policy_rejection_count: not computed from `ai_outputs.json` alone

`qualification=None` is expected for PMP outcomes after Sprint 5 and was **not**
treated as a PMP generation failure.

---

## Doctrine pollution checks

- feedback_field_count: 0
- selection_field_count: 0
- bird_image_pollution_count: 0
- unexpected_runtime_field_count: 0
- doctrine_pollution_detected: false

No doctrine pollution detected.

---

## Manual review sample summary

The evidence JSON includes a deterministic 5-item manual sample with:
- high-quality valid profiles
- failed profile (schema validation failure)
- indirect-evidence/partial-like profile coverage when available
- low basic_identification valid profile

Each sample item records media key, status, evidence type, global quality,
usage scores, visible field marks, limitations, failure reason (if any), and a
bounded payload excerpt.

---

## Interpretation

### 1. PMP profile generation success

PMP generation quality is strong on this controlled run:
- `pmp_valid_rate = 0.9138`
- failures are concentrated in explainable schema validation errors
- no feedback/selection/runtime pollution
- expected evidence diversity (whole organism plus feather/nest/habitat/multiple)

### 2. Legacy qualification/export policy effects

`qualification=None` appears for all outcomes and is expected after Sprint 5.
This is a legacy policy compatibility concern, not a PMP generation failure.

---

## Residual risks

- Schema validation failures (10) still require root-cause cleanup before larger
  volume runs.
- Cost/latency estimates were not measured in this audit output.
- This result does not imply runtime or production readiness.

---

## Final decision

**`READY_FOR_CONTROLLED_PROFILED_CORPUS_RUN`**

Criteria matched:
- pmp_valid_rate >= 90%
- plausible score/evidence distributions
- no doctrine pollution
- controlled snapshot round-trip successful
- qualification=None behavior documented correctly

---

## Next step recommendation (Sprint 7)

Primary recommendation:
- run a broader controlled profiled corpus with the same PMP selector and audit
  protocol.

Parallel strategic track (still out of runtime scope):
- start PMP-specific qualification policy design to bridge legacy
  `qualification=None` compatibility.

Do not move to runtime/materialization until PMP policy work is explicitly
defined and validated.
