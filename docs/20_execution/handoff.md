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
  - none on INT-023 execution scope

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
- gate doctrine P0 -> P1 is now versioned (`GO` / `GO_WITH_GAPS` / `NO_GO`)

## Next exact step

- Open Phase 1 under status `GO_WITH_GAPS` and keep scope locked to:
  - instrumentation/baseline KPI work (Phase 1)
  - tracked corrective gaps inherited from P0:
    - `distractor_diversity_segment` (priority 1)
    - `latency_e2e_segment_p95` against product budget (`X=900ms`, `Y=1500ms`)

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
- doctrine decision after closure:
  - promotion decision model versioned: `GO` / `GO_WITH_GAPS` / `NO_GO`
  - P0->P1 status: `GO_WITH_GAPS` (historical `NO_GO` artifact unchanged)
