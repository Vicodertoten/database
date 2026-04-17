# Handoff State

Ce document capture l'etat operationnel reel de passation pour le chantier actif.

## Current active chantier

- ID: INT-007
- Title: Runtime Consumption Transport V1 Doctrine
- Status: closed

## Repo role in current chantier

- Current repo: database
- Role: owner
- Other repo: runtime-app
- Expected dependency order: database doctrine -> runtime-app mirror doctrine

## Last validated state

- Last validated commit or tag: working tree with INT-007 doctrinal closure updates
- Validation date: 2026-04-17
- What is already validated:
  - owner ADR added: `docs/adr/0004-runtime-consumption-transport-v1.md`
  - sequence doctrinale verrouillee: V1 fixtures -> V1.5 API minimale -> plus tard operations editoriales plus riches
  - no new runtime surface introduced
  - no owner/consumer boundary change introduced
  - runtime-app mirror ADR expected with same narrative
- What is not validated yet: none in INT-007 scope

## Decisions already locked

- `database` reste owner de la verite des contrats et artefacts runtime.
- `runtime-app` consomme les surfaces officielles et ne les redefinit pas.
- `export.bundle.v4` n'est pas une surface live runtime.
- la doctrine de transport retenue est:
  - V1: artefacts/fixtures publies
  - V1.5: API de lecture minimale (`apps/api` point d'entree produit)
  - plus tard: operations editoriales plus riches, toujours owned par `database`

## Important constraints

- Ne pas toucher aux schemas existants.
- Ne pas modifier la logique pipeline.
- Ne pas redefinir les surfaces runtime officielles.
- Ne pas sur-specifier auth/transport reseau/deploiement/cache/synchronisation.

## Next exact step

- open INT-008 (or next planned chantier) from ADR-0004 baseline

## Files to read first in this repo

- README.md
- docs/runtime_consumption_v1.md
- docs/adr/0003-playable-corpus-pack-compilation-enrichment-queue.md
- docs/adr/0004-runtime-consumption-transport-v1.md
- docs/20_execution/chantiers/INT-007.md
- docs/20_execution/integration_log.md

## Files to read first in the other repo

- runtime-app/docs/adr/0001-runtime-database-transport-v1.md
- runtime-app/docs/20_execution/chantiers/INT-007.md
- runtime-app/docs/20_execution/integration_log.md

## Verification commands

- `python scripts/check_doc_code_coherence.py` (optional for doc consistency)

## Notes for next IA session

- INT-007 is doctrinal and does not add new data surfaces.
- Keep owner/consumer framing unchanged.
- Any future transport evolution must extend ADR-0004, not contradict it.
