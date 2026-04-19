# Handoff State

Ce document capture l'etat operationnel reel de passation pour le chantier actif.

## Current active chantier

- ID: INT-016
- Title: Runtime-read owner-side proof hardening (Phase 6)
- Status: closed

## Repo role in current chantier

- Current repo: database
- Role: owner
- Other repo: runtime-app
- Expected dependency order: owner-side proofs -> consumer-side proof log alignment

## Last validated state

- Last validated context: INT-016 closure (2026-04-19)
- What is already validated:
  - owner-side runtime-read tests now cover series behavior on compiled/materialization
  - latest compiled read path is explicitly proven (`/packs/{pack_id}/compiled`)
  - HTTP error matrix is explicit (`400 invalid_limit`, `400 invalid_revision`, `404 not_found`, `500 internal_error`)
  - runtime-read boundary remains unchanged (read-only, 3 official surfaces)
- What is not validated yet:
  - full-suite execution in this pass (only targeted owner-read test run)

## Decisions already locked

- no owner-side contract version bump for Phase 6
- no write/editorial transport introduced here
- runtime consumers still depend only on `playable_corpus.v1`, `pack.compiled.v1`, `pack.materialization.v1`

## Important constraints

- keep owner/consumer boundary strict
- keep runtime-read service minimal and read-only
- do not introduce runtime session/scoring logic in `database`

## Next exact step

- Open phase 7 planning and formalization sequence (editorial write contracts + institutional minimum), after runtime-app closure sync.

## Files to read first in this repo

- README.md
- docs/runtime_consumption_v1.md
- docs/adr/0004-runtime-consumption-transport-v1.md
- docs/20_execution/chantiers/INT-016.md
- docs/20_execution/integration_log.md
- tests/test_runtime_read_owner_service.py

## Files to read first in the other repo

- runtime-app/docs/20_execution/chantiers/INT-015.md
- runtime-app/docs/20_execution/chantiers/INT-016.md
- runtime-app/docs/20_execution/integration_log.md

## Verification commands

- `python -m pytest -q tests/test_runtime_read_owner_service.py -p no:capture`

## Notes for next IA session

- INT-016 closed owner-side
- runtime-app INT-015/016 closed consumer-side
- next structural step is phase 7, not a new read-transport expansion
