# Handoff State

Ce document capture l'etat operationnel reel de passation pour le chantier actif.

## Current active chantier

- ID: INT-019
- Title: Formalisation owner-side des operations editoriales critiques
- Status: closed

## Repo role in current chantier

- Current repo: database
- Role: owner
- Other repo: runtime-app
- Expected dependency order: owner write transport formalisation -> consumer provider integration -> docs sync

## Last validated state

- Last validated context: INT-019 closure sync (2026-04-19)
- What is already validated:
  - service owner-side write minimal en place (`database-editorial-write-owner`)
  - envelopes d'operations versionnes disponibles pour create/diagnose/compile/materialize/enrichment status/enqueue/execute
  - routes write bornees au perimetre editorial pack/enrichment
  - runtime-app route layer `/editorial/*` integree sur transport owner-http (plus de facade semantique mock nominale)
- What is not validated yet:
  - execution CI complete multi-environnements

## Decisions already locked

- separation stricte read vs write owner-side transports
- `apps/api` reste le point d'entree produit
- aucune extension backend produit generaliste dans `database`
- pas d'auth forte/cache distribue/sync avancee dans ce scope

## Important constraints

- garder la frontiere owner/consumer explicite
- conserver la semantique operationnelle cote owner
- ne pas introduire de logique session/runtime UX dans `database`

## Next exact step

- Ouvrir le cadrage institutionnel minimal sur baseline INT-019 closee.

## Files to read first in this repo

- README.md
- docs/runtime_consumption_v1.md
- docs/adr/0005-editorial-write-transport-v1.md
- docs/20_execution/chantiers/INT-019.md
- docs/20_execution/integration_log.md
- src/database_core/editorial_write/service.py
- src/database_core/editorial_write/http_server.py
- tests/test_editorial_write_owner_service.py

## Files to read first in the other repo

- runtime-app/docs/20_execution/chantiers/INT-019.md
- runtime-app/apps/api/src/integrations/database/owner-http-editorial-provider.ts
- runtime-app/apps/api/src/routes/editorial-pack-flows.ts
- runtime-app/docs/20_execution/integration_log.md

## Verification commands

- `ruff check .`
- `python -m compileall -q src tests/test_editorial_write_owner_service.py`

## Notes for next IA session

- INT-018 closed owner-side
- INT-019 closed owner-side + consumer integration mirrored
- baseline prete pour cadrage institutionnel minimal
