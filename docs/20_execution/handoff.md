# Handoff State

Ce document capture l'etat operationnel reel de passation pour le chantier actif.

## Current active chantier

- ID: INT-027
- Title: Phase 3 retargeting preflight gate (owner)
- Status: closed_no_go

## Repo role in current chantier

- Current repo: database
- Role: owner
- Other repo: runtime-app
- Expected dependency order: baseline diagnose -> targeted remediation passes -> diagnose/compile delta -> runtime compatibility check

## Last validated state

- Last validated context: INT-027 preflight + gated full run executed.
- What is already validated:
  - preflight ops function implemented (`run_phase3_preflight`)
  - preflight decision function implemented (`evaluate_preflight_gate`)
  - `phase3_1_complete_measurement.py` blocks full campaign when preflight is missing/no-go (`STOP_RETARGET_PRECHECK`)
  - unit/non-regression tests green (`30 passed`) on targeted suites
  - real preflight artifact generated and parsed
  - real full run produced `phase3_1_summary.v1.json` with `decision.status=STOP_RETARGET_PRECHECK`
- What is not validated yet:
  - rerun on a candidate pack with `insufficient_media_before>0` and `preflight_go=true`

## Decisions already locked

- source of truth for targeting: pack diagnose output
- idempotence logic lives in remediation script + snapshot filtering (not enrichment_store core)
- no runtime contract change
- no Phase 4/5 work in this chantier

## Important constraints

- no schema/contract break
- additive-only data surface changes
- no refactor outside pre-filtering scope
- keep owner/consumer boundary explicit

## Next exact step

- select a candidate pack with explicit compile deficit (`insufficient_media_before>0`), rerun preflight, and launch Phase 3.1 full campaign only if `preflight_go=true`.

## Files to read first in this repo

- docs/codex_execution_plan.md
- docs/20_execution/chantiers/INT-027.md
- docs/20_execution/integration_log.md
- scripts/phase3_1_complete_measurement.py
- src/database_core/ops/phase3_taxon_remediation.py
- scripts/phase3_taxon_remediation.py

## Files to read first in the other repo

- runtime-app/docs/20_execution/chantiers/INT-026.md
- runtime-app/docs/20_execution/handoff.md
- runtime-app/docs/20_execution/integration_log.md

## Verification commands

- `python -m pytest -q -p no:capture tests/test_phase3_taxon_remediation.py`
- `python -m pytest -q -p no:capture tests/test_inat_snapshot.py`
- `python -m pytest -q -p no:capture tests/test_storage.py`
- `python scripts/verify_goldset_v1.py`
- `python scripts/verify_repo.py`
- `corepack pnpm --filter @runtime-app/web run test:smoke`

## Notes for next IA session

- INT-026 is closed with final decision `NO_GO`.
- INT-027 introduces a hard preflight gate to avoid wasteful reruns.
- INT-027 is now closed `NO_GO` by strict mapping (`STOP_RETARGET_PRECHECK -> NO_GO`) on real execution.
- `verify_repo.py` currently fails on a pre-existing doctrine marker check (`Politique distracteurs v2`) unrelated to this chantier.
- Phase 3.1 full campaign should not be launched without `docs/20_execution/phase3_1/phase3_1_preflight.v1.json` with `preflight_go=true`.
