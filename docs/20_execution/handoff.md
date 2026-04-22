# Handoff State

Ce document capture l'etat operationnel reel de passation pour le chantier actif.

## Current active chantier

- ID: INT-023
- Title: Phase 0 segment cible et benchmark prototype
- Status: closed_no_go

## Repo role in current chantier

- Current repo: database
- Role: owner
- Other repo: runtime-app
- Expected dependency order: owner benchmark protocol lock -> prototype baseline freeze -> owner comparative runs -> consumer runtime validation -> Go/No-Go dossier (completed)

## Last validated state

- Last validated context: INT-023 execution completed with locked artifacts and decision.
- What is already validated:
  - owner/consumer boundary remains explicit (`database` owner, `runtime-app` consumer)
  - smoke KPI locked set remains unchanged
  - goldset tooling and smoke reporting commands are available
  - baseline prototype frozen from inaturamouche (`docs/20_execution/phase0/prototype_baseline.v1.json`)
  - 3 comparable owner runs executed on snapshot `inaturalist-birds-v2-20260421T210221Z`
  - consumer p95 evidence published with >= 30 measured requests per run
  - Go/No-Go decision published (`NO_GO`)
- What is not validated yet:
  - doctrine versioning of `P0 before P1` as an explicit codified rule

## Decisions already locked

- segment Phase 0: birds-only, image-only, Europe, difficulty policy mixed, no seasonal filter
- prototype baseline source: inaturamouche only
- runtime-app is validation consumer only (not prototype baseline)
- comparative benchmark is corpus/snapshot comparable; live iNaturalist is optional stability check only
- Go/No-Go is strictly metric-based and diffable

## Important constraints

- no schema/contract change for this chantier
- no runtime logic in owner repo
- no subjective UX criterion in Phase 0 decision
- treat `P0 before P1` as proposed gating rule until explicitly versioned in doctrine

## Next exact step

- Open a focused post-P0 corrective mini-plan (new chantier) to address only the two failed metrics:
  - `distractor_diversity_segment` gap vs prototype baseline
  - `latency_e2e_segment_p95` gap vs prototype baseline

## Files to read first in this repo

- docs/codex_execution_plan.md
- docs/20_execution/chantiers/INT-023.md
- docs/20_execution/integration_log.md
- docs/10_program_kpis.md
- docs/04_smoke_runbook.md
- scripts/verify_goldset_v1.py
- scripts/generate_smoke_report.py

## Files to read first in the other repo

- runtime-app/docs/20_execution/chantiers/INT-023.md
- runtime-app/docs/20_execution/integration_log.md
- runtime-app/docs/database_integration_v1.md

## Verification commands

- `python scripts/verify_goldset_v1.py`
- `python scripts/generate_smoke_report.py --snapshot-id <snapshot_id> --fail-on-kpi-breach`
- `python scripts/verify_repo.py`
- `corepack pnpm --filter @runtime-app/web run test:smoke`
- `python scripts/phase0_owner_benchmark.py --snapshot-id inaturalist-birds-v2-20260421T210221Z --difficulty-policy mixed --runs 3 --attempts-per-run 10 --question-count 20 --output docs/20_execution/phase0/owner_benchmark_summary.v1.json`
- `python scripts/phase0_go_no_go.py --owner-summary docs/20_execution/phase0/owner_benchmark_summary.v1.json --prototype-baseline /Users/ryelandt/Documents/Inaturamouche/docs/20_execution/phase0/prototype_baseline.v1.json --consumer-summary /Users/ryelandt/Documents/runtime-app/docs/20_execution/phase0/consumer_latency_summary.v1.json --output docs/20_execution/phase0/go_no_go_decision.v1.json`

## Notes for next IA session

- INT-023 closed with `NO_GO` on 2026-04-22
- locked evidence:
  - `docs/20_execution/phase0/owner_benchmark_summary.v1.json`
  - `docs/20_execution/phase0/go_no_go_decision.v1.json`
