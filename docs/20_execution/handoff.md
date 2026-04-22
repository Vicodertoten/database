# Handoff State

Ce document capture l'etat operationnel reel de passation pour le chantier actif.

## Current active chantier

- ID: INT-026
- Title: Phase 3 remediation data taxons deficitaires
- Status: open_in_progress

## Repo role in current chantier

- Current repo: database
- Role: owner
- Other repo: runtime-app
- Expected dependency order: baseline diagnose -> targeted remediation passes -> diagnose/compile delta -> runtime compatibility check

## Last validated state

- Last validated context: INT-026 implementation started owner-side.
- What is already validated:
  - phase3 remediation orchestration is implemented (`scripts/phase3_taxon_remediation.py`)
  - prioritization source uses pack diagnostics (`reason_code`, `deficits`, `blocking_taxa`)
  - idempotence guards implemented in script-level snapshot filtering (`source_observation_id`, `source_media_id`)
  - enrichment queue role preserved (request/execution/recompile trace)
- What is not validated yet:
  - full end-to-end remediation run evidence on target pack(s)
  - runtime compatibility note for INT-026 consumer mirror

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

- execute INT-026 remediation on prioritized pack(s), publish `docs/20_execution/phase3/*.phase3_remediation.v1.json`, then emit Phase 3 decision.

## Files to read first in this repo

- docs/codex_execution_plan.md
- docs/20_execution/chantiers/INT-026.md
- docs/20_execution/integration_log.md
- src/database_core/ops/phase3_taxon_remediation.py
- scripts/phase3_taxon_remediation.py

## Files to read first in the other repo

- runtime-app/docs/20_execution/chantiers/INT-026.md
- runtime-app/docs/20_execution/handoff.md
- runtime-app/docs/20_execution/integration_log.md

## Verification commands

- `python -m pytest -q -p no:capture tests/test_phase3_taxon_remediation.py`
- `python -m pytest -q -p no:capture tests/test_storage.py`
- `python scripts/verify_goldset_v1.py`
- `python scripts/verify_repo.py`
- `corepack pnpm --filter @runtime-app/web run test:smoke`

## Notes for next IA session

- INT-026 implementation is in place and validated by targeted unit tests.
- `verify_repo.py` currently fails on a pre-existing doctrine marker check (`Politique distracteurs v2`) unrelated to this chantier.
- INT-026 decision is pending execution evidence.
