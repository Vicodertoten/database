# Handoff State

Ce document capture l'etat operationnel reel de passation pour le chantier actif.

## Current active chantier

- ID: INT-024
- Title: Phase 1 instrumentation et baseline KPI
- Status: closed_go_with_gaps

## Repo role in current chantier

- Current repo: database
- Role: owner
- Other repo: runtime-app
- Expected dependency order: protocol lock -> additive smoke instrumentation -> 3-run baseline publication -> consumer nominal validation -> exit decision (completed)

## Last validated state

- Last validated context: INT-024 instrumentation baseline completed.
- What is already validated:
  - owner/consumer boundary remains explicit (`database` owner, `runtime-app` consumer)
  - additive `smoke.report.v1` extension implemented (`extended_kpis`, `compile_deficits_summary`)
  - locked KPI registry and `overall_pass` semantics preserved
  - 3 comparable Phase 1 runs published under `docs/20_execution/phase1/`
  - consumer smoke remains green
  - Phase 1 decision published (`GO_WITH_GAPS`)
- What is not validated yet:
  - none on INT-024 execution scope

## Decisions already locked

- additive compatibility rule on smoke report is mandatory
- locked KPI set remains authoritative for `overall_pass`
- Phase 1 KPI extended set is for baseline/pilotage (non blocking for instrumentation exit)
- P0 historical decision remains unchanged

## Important constraints

- no schema/contract change for this chantier
- no runtime logic in owner repo
- no refactor outside instrumentation scope
- gate doctrine P0 -> P1 remains versioned (`GO` / `GO_WITH_GAPS` / `NO_GO`)

## Next exact step

- Open the next corrective chantier focused on P1 tracked gaps:
  - distractor diversity improvement trajectory
  - country code completeness trajectory
  - consumer latency budget follow-up remains tracked in runtime-app

## Files to read first in this repo

- docs/codex_execution_plan.md
- docs/20_execution/chantiers/INT-024.md
- docs/20_execution/integration_log.md
- docs/10_program_kpis.md
- docs/04_smoke_runbook.md
- scripts/verify_goldset_v1.py
- scripts/generate_smoke_report.py

## Files to read first in the other repo

- runtime-app/docs/20_execution/chantiers/INT-024.md
- runtime-app/docs/20_execution/integration_log.md
- runtime-app/docs/database_integration_v1.md

## Verification commands

- `python scripts/verify_goldset_v1.py`
- `python scripts/generate_smoke_report.py --snapshot-id inaturalist-birds-v2-20260421T210221Z --fail-on-kpi-breach`
- `python -m pytest -q -p no:capture tests/test_smoke_report.py`
- `python scripts/verify_repo.py`
- `corepack pnpm --filter @runtime-app/web run test:smoke`

## Notes for next IA session

- INT-024 closed with `GO_WITH_GAPS` on 2026-04-22
- locked evidence:
  - `docs/20_execution/chantiers/INT-024.md`
  - `docs/20_execution/phase1/baseline_summary.v1.json`
  - `docs/20_execution/phase1/smoke_run1.smoke_report.v1.json`
  - `docs/20_execution/phase1/smoke_run2.smoke_report.v1.json`
  - `docs/20_execution/phase1/smoke_run3.smoke_report.v1.json`
