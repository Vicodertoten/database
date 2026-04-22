# Handoff State

Ce document capture l'etat operationnel reel de passation pour le chantier actif.

## Current active chantier

- ID: INT-026
- Title: Phase 3 remediation data taxons deficitaires
- Status: closed_no_go

## Repo role in current chantier

- Current repo: database
- Role: owner
- Other repo: runtime-app
- Expected dependency order: baseline diagnose -> targeted remediation passes -> diagnose/compile delta -> runtime compatibility check

## Last validated state

- Last validated context: INT-026 Phase 3.1 execution completed and closed.
- What is already validated:
  - phase3 remediation orchestration is implemented (`scripts/phase3_taxon_remediation.py`)
  - prioritization source uses pack diagnostics (`reason_code`, `deficits`, `blocking_taxa`)
  - idempotence guards implemented in script-level snapshot filtering (`source_observation_id`, `source_media_id`)
  - enrichment queue role preserved (request/execution/recompile trace)
  - phase3.1 summary generated: `docs/20_execution/phase3_1/phase3_1_summary.v1.json`
  - script verdict: `STOP_RETARGET`
  - strict mapping applied: `STOP_RETARGET -> NO_GO`
  - closure decision published in `INT-026` and `integration_log`
- What is not validated yet:
  - no pending validation in INT-026 scope (chantier closed)

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

- open next owner chantier focused on selection retargeting (maximize compile-impact per Gemini call) before any new Phase 3 scale rerun.

## Files to read first in this repo

- docs/codex_execution_plan.md
- docs/20_execution/chantiers/INT-026.md
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

- INT-026 is closed with final decision `NO_GO` after completed Phase 3.1 run.
- `verify_repo.py` currently fails on a pre-existing doctrine marker check (`Politique distracteurs v2`) unrelated to this chantier.
- Phase 3.1 artifacts and summary are available under `docs/20_execution/phase3_1/`.
- Next work should retarget acquisition logic rather than increase raw run volume.
