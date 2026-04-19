# Handoff State

Ce document capture l'etat operationnel reel de passation pour le chantier actif.

## Current active chantier

- ID: INT-020
- Title: Support owner-side pour surface editoriale legere runtime (Phase 4)
- Status: closed

## Repo role in current chantier

- Current repo: database
- Role: owner
- Other repo: runtime-app
- Expected dependency order: owner-side hardening -> consumer web operator surface -> docs sync

## Last validated state

- Last validated context: INT-020 closure sync (2026-04-19)
- What is already validated:
  - service owner-side write remains bounded to editorial pack/enrichment operations
  - invalid input refusals are explicit and covered by owner-side tests
  - runtime-app `/editorial` surface is connected through `apps/api` without direct owner access
- What is not validated yet:
  - full CI matrix across environments

## Decisions already locked

- keep separation read vs write owner-side transports
- keep `database` as semantic owner for editorial operations
- no auth forte/cache distribue/sync avancee in this phase
- no session/progression/user logic in owner repo

## Important constraints

- preserve contract stability
- preserve strict owner perimeter
- keep errors categorized and actionable

## Next exact step

- Ouvrir le cadrage institutionnel minimal sur baseline INT-019/INT-020 closee.

## Files to read first in this repo

- docs/adr/0005-editorial-write-transport-v1.md
- docs/20_execution/chantiers/INT-020.md
- docs/20_execution/chantiers/INT-019.md
- docs/20_execution/integration_log.md
- src/database_core/editorial_write/http_server.py
- tests/test_editorial_write_owner_service.py

## Files to read first in the other repo

- runtime-app/docs/20_execution/chantiers/INT-020.md
- runtime-app/apps/web/app/editorial/page.tsx
- runtime-app/apps/api/src/routes/editorial-pack-flows.ts
- runtime-app/docs/20_execution/integration_log.md

## Verification commands

- `ruff check .`
- `python -m compileall -q src tests/test_editorial_write_owner_service.py`

## Notes for next IA session

- INT-019 closed
- INT-020 closed
- baseline prete pour institutionnel minimal
