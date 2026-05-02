---
owner: database
status: stable
last_reviewed: 2026-05-02
source_of_truth: docs/runbooks/palier-1-v11-baseline.md
scope: runbook
---

# Palier 1 v1.1 Baseline

## Purpose

Freeze an operational baseline for Palier 1 v1.1 with deterministic, reproducible
artifacts and explicit hard gates.

## Baseline contract (hard requirements)

- `pack.compiled.v2`: `question_count_requested = 50`
- `pack.compiled.v2`: `question_count_built = 50`
- `pack.compiled.v2`: exactly `50` unique `target_canonical_taxon_id`
- `pack.materialization.v2`: `question_count = 50`
- distractor audit produced with no report-level errors

## Source snapshot and run lineage

- snapshot id: `palier1-be-birds-50taxa-run003-v11-baseline`
- pipeline run id: `run:20260502T160906Z:7520db76`
- qualification policy: `v1.1`
- qualifier mode: `cached`

## Pack lineage

- pack id: `pack:palier1:be:birds:run003-v11-baseline`
- revision: `1`
- diagnose result: `compilable = true`, `reason_code = compilable`
- compiled build id: `packbuild:pack:palier1:be:birds:run003-v11-baseline:1:v2:3d45ebad`

## Frozen artifacts

- `data/fixtures/inaturalist_pilot_taxa_palier1_be_50_run003_v11_baseline.json`
- `docs/audits/evidence/palier1_v11_baseline/pack_diagnose.json`
- `docs/audits/evidence/palier1_v11_baseline/pack_compiled_v2.json`
- `docs/audits/evidence/palier1_v11_baseline/pack_materialization_v2.json`
- `docs/audits/evidence/palier1_v11_baseline/phase3_distractor_audit_report.json`

## Validation gate (CI/local)

Mandatory gate:

```bash
python scripts/check_palier1_v11_baseline.py
```

This gate fails if any baseline hard requirement regresses.

## Operational note

The v2 compile target ordering uses deterministic round-robin by taxon
(`one-target-per-taxon-first`) so `question_count=50` can preserve
`50` unique target taxa when the pack has at least one playable item per taxon.
