---
owner: database
status: stable
last_reviewed: 2026-05-02
source_of_truth: docs/audits/palier-1-v11-baseline-go.md
scope: audit
---

> Historical audit note.
> This audit may reference superseded pack/materialization contracts.
> Current contract source of truth: `docs/architecture/contract-map.md`.
> Do not use this audit as current runtime implementation guidance.


# Palier 1 v1.1 Baseline GO Audit

## Decision

Decision: `GO`

## Scope

- pack baseline: `pack:palier1:be:birds:run003-v11-baseline`
- revision: `1`
- contract family: `pack.compiled.v2` / `pack.materialization.v2`

## Hard gate results

- compile v2: `PASS`
- materialize v2: `PASS`
- `question_count_requested = 50`: `PASS`
- `question_count_built = 50`: `PASS`
- unique `target_canonical_taxon_id = 50`: `PASS`
- materialization `question_count = 50`: `PASS`
- distractor audit report produced with empty `errors`: `PASS`

## Evidence

- `docs/audits/evidence/palier1_v11_baseline/pack_diagnose.json`
- `docs/audits/evidence/palier1_v11_baseline/pack_compiled_v2.json`
- `docs/audits/evidence/palier1_v11_baseline/pack_materialization_v2.json`
- `docs/audits/evidence/palier1_v11_baseline/phase3_distractor_audit_report.json`
- validation gate: `python scripts/check_palier1_v11_baseline.py`

## Notes

- Target selection is stabilized with deterministic round-robin (`one-target-per-taxon-first`) for v2 compilation.
- Baseline fixture is frozen at `50` unique taxa in
  `data/fixtures/inaturalist_pilot_taxa_palier1_be_50_run003_v11_baseline.json`.
