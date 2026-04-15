# Handoff State

Ce document capture l'etat operationnel reel de passation pour le chantier actif.

## Current active chantier

- ID: INT-002
- Title: Align runtime-app/packages/contracts with official database schemas
- Status: in_progress

## Repo role in current chantier

- Current repo: database
- Role: owner
- Other repo: runtime-app
- Expected dependency order: database first, runtime-app second

## Last validated state

- Last validated commit or tag: d921a9b (database)
- Validation date: 2026-04-15
- What is already validated: three owner schemas confirmed as official source of truth; no schema changes needed; chantier brief published
- What is not validated yet: consumer contracts aligned; cross-repo closure

## Decisions already locked

- `database` reste owner des contrats et artefacts data concernes.
- `runtime-app` consomme les surfaces officielles et ne les redefinit pas.
- `export.bundle.v4` n'est pas une surface live runtime.
- Les besoins runtime hors surfaces officielles doivent etre formalises d'abord dans `database`.

## Important constraints

- Ne pas toucher aux schemas existants.
- Ne pas modifier la logique pipeline.
- Ne pas sur-specifier transport, auth, session, endpoints, ou UX runtime.
- Rester strictement sequentiel et tracable.

## Next exact step

- align runtime-app consumer contracts with these schemas: schemas/playable_corpus_v1.schema.json, schemas/pack_compiled_v1.schema.json, schemas/pack_materialization_v1.schema.json

## Files to read first in this repo

- README.md
- docs/runtime_consumption_v1.md
- docs/20_execution/handoff.md
- docs/20_execution/chantiers/INT-002.md
- schemas/playable_corpus_v1.schema.json
- schemas/pack_compiled_v1.schema.json
- schemas/pack_materialization_v1.schema.json

## Files to read first in the other repo

- README.md
- packages/contracts/src/ (all contract type files)
- docs/20_execution/chantiers/INT-002.md

## Verification commands

- python scripts/check_doc_code_coherence.py (optional)

## Notes for next IA session

- INT-002 est le seul chantier structurant actif.
- Source de verite = les 3 fichiers schemas/*.json de database. Aucun renommage local autorise.
- Corriger uniquement cote consumer (runtime-app/packages/contracts); ne rien changer dans database.
- Cloturer inter-repos seulement apres alignement confirme et tests consumer verts.