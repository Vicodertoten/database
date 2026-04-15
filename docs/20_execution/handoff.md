# Handoff State

Ce document capture l'etat operationnel reel de passation pour le chantier actif.

## Current active chantier

- ID: INT-003
- Title: Runtime reference fixtures strategy v1 (owner-side)
- Status: closed

## Repo role in current chantier

- Current repo: database
- Role: owner
- Other repo: runtime-app
- Expected dependency order: database first, runtime-app second

## Last validated state

- Last validated commit or tag: 444188a (database), 1868923 (runtime-app)
- Validation date: 2026-04-15
- What is already validated: INT-003 owner-side closed; official runtime fixture trio published, schema-validated, and cross-checked for ID coherence
- What is not validated yet: consumer-side adoption in INT-004 (`runtime-app`)

## Decisions already locked

- `database` reste owner des contrats et artefacts data concernes.
- `runtime-app` consomme les surfaces officielles et ne les redefinit pas.
- `export.bundle.v4` n'est pas une surface live runtime.
- Les besoins runtime hors surfaces officielles doivent etre formalises d'abord dans `database`.

## Important constraints

- Ne pas toucher aux schemas existants.
- Ne pas modifier la logique pipeline.
- Ne pas sur-specifier transport, auth, session, endpoints, ou UX runtime.
- Ne pas produire de code consumer dans `runtime-app` a ce stade.
- Rester strictement sequentiel et tracable.

## Next exact step

- INT-004 (consumer): integrate `fixtures/runtime/*.sample.json` in runtime-app local tests without field transformation

## Files to read first in this repo

- README.md
- docs/runtime_consumption_v1.md
- docs/20_execution/handoff.md
- docs/20_execution/chantiers/INT-003.md
- schemas/playable_corpus_v1.schema.json
- schemas/pack_compiled_v1.schema.json
- schemas/pack_materialization_v1.schema.json

## Files to read first in the other repo

- README.md
- packages/contracts/src/ (all contract type files)
- docs/20_execution/chantiers/INT-003.md

## Verification commands

- python scripts/check_doc_code_coherence.py (optional)

## Notes for next IA session

- INT-002 and INT-003 are closed owner-side in `database`.
- Keep source of truth anchored in `database/schemas/*.json` for runtime contract surfaces.
- Official runtime fixture strategy is now locked in `docs/20_execution/chantiers/INT-003.md`.
- First official fixture trio is published in `fixtures/runtime/`.
- Next inter-repo step is explicitly INT-004 on `runtime-app` (consumer).
