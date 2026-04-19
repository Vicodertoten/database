# Handoff State

Ce document capture l'etat operationnel reel de passation pour le chantier actif.

## Current active chantier

- ID: INT-018
- Title: Owner-side runtime-read operational hardening
- Status: closed

## Repo role in current chantier

- Current repo: database
- Role: owner
- Other repo: runtime-app
- Expected dependency order: owner-side proofs -> consumer-side proof log alignment

## Last validated state

- Last validated context: INT-018 closure sync (2026-04-19)
- What is already validated:
  - owner-side runtime-read `/health` now exposes operational diagnostics (`service_version`, `ready`, `limits`)
  - request logs are emitted as JSON with `error_category` and `latency_ms`
  - HTTP error matrix remains explicit and now validates `revision <= 0` as `400 invalid_revision`
  - runtime-read boundary remains unchanged (read-only, 3 official surfaces)
  - runtime-app mirror closure evidence is in place (`INT-018` runtime side closed)
- What is not validated yet:
  - none for INT-018 scope

## Decisions already locked

- no owner-side contract version bump for Phase 6
- no write/editorial transport introduced here
- runtime consumers still depend only on `playable_corpus.v1`, `pack.compiled.v1`, `pack.materialization.v1`

## Important constraints

- keep owner/consumer boundary strict
- keep runtime-read service minimal and read-only
- do not introduce runtime session/scoring logic in `database`

## Next exact step

- Open phase 7 planning and keep INT-018 as closed baseline.

## Files to read first in this repo

- README.md
- docs/runtime_consumption_v1.md
- docs/adr/0004-runtime-consumption-transport-v1.md
- docs/20_execution/chantiers/INT-018.md
- docs/20_execution/integration_log.md
- tests/test_runtime_read_owner_service.py

## Files to read first in the other repo

- runtime-app/docs/20_execution/chantiers/INT-015.md
- runtime-app/docs/20_execution/chantiers/INT-016.md
- runtime-app/docs/20_execution/chantiers/INT-017.md
- runtime-app/docs/20_execution/chantiers/INT-018.md
- runtime-app/docs/20_execution/integration_log.md

## Verification commands

- `python -m pytest -q tests/test_runtime_read_owner_service.py -p no:capture`

## Notes for next IA session

- INT-018 closed owner-side
- phase 7 planning can resume
