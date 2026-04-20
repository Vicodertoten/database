# Handoff State

Ce document capture l'etat operationnel reel de passation pour le chantier actif.

## Current active chantier

- ID: INT-022
- Title: Phase 6 pilot-prep hardening alignment
- Status: in_progress

## Repo role in current chantier

- Current repo: database
- Role: owner
- Other repo: runtime-app
- Expected dependency order: owner-side readiness evidence -> runtime dry-runs -> cross-repo Go/No-Go dossier

## Last validated state

- Last validated context: runtime-app INT-021 closure + phase 6 kickoff alignment
- What is already validated:
  - owner-side runtime-read and editorial-write services expose health + request observability
  - owner-side boundaries remain unchanged (no runtime session/institutional ownership drift)
  - runtime-app phase 6 baseline is now active (`INT-022`)
- What is not validated yet:
  - staged dry-runs with simulated owner incident and recovery evidence

## Decisions already locked

- keep separation read vs write owner-side transports
- keep `database` as semantic owner for read/editorial contracts
- no auth forte/cache distribue/sync avancee in this phase
- no session/progression/user logic in owner repo

## Important constraints

- preserve contract stability
- preserve strict owner perimeter
- keep errors categorized and actionable

## Next exact step

- Execute dry-run owner readiness checks and publish evidence for runtime-app dry-run #1.

## Files to read first in this repo

- docs/adr/0005-editorial-write-transport-v1.md
- docs/20_execution/chantiers/INT-022.md
- docs/20_execution/phase6_pilot_runbook.md
- docs/20_execution/integration_log.md
- src/database_core/runtime_read/http_server.py
- src/database_core/editorial_write/http_server.py
- tests/test_runtime_read_owner_service.py
- tests/test_editorial_write_owner_service.py

## Files to read first in the other repo

- runtime-app/docs/20_execution/chantiers/INT-022.md
- runtime-app/docs/20_execution/phase6_pilot_runbook.md
- runtime-app/apps/api/src/security/operator-auth.ts
- runtime-app/docs/20_execution/integration_log.md

## Verification commands

- `ruff check .`
- `python -m compileall -q src tests/test_runtime_read_owner_service.py tests/test_editorial_write_owner_service.py`

## Notes for next IA session

- INT-022 in progress
- next strategic step: owner evidence for 2 pilot dry-runs + Go/No-Go contribution
