# Handoff State

Ce document capture l'etat operationnel reel de passation pour le chantier actif.

## Current active chantier

- ID: INT-001
- Title: Lock runtime consumption doctrine v1
- Status: validated_by_owner

## Repo role in current chantier

- Current repo: database
- Role: owner
- Other repo: runtime-app
- Expected dependency order: database first, runtime-app second

## Last validated state

- Last validated commit or tag: 1f03803
- Validation date: 2026-04-15
- What is already validated: official runtime-consumable surfaces confirmed; prohibition on export.bundle.v4 confirmed; ownership boundary confirmed
- What is not validated yet: consumer-side mirrored wording; cross-repo closure

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

- Open runtime-app and align docs/database_integration_v1.md with the locked owner wording.

## Files to read first in this repo

- README.md
- docs/README.md
- docs/codex_execution_plan.md
- docs/runtime_consumption_v1.md
- docs/20_execution/handoff.md
- docs/20_execution/chantiers/INT-001.md

## Files to read first in the other repo

- README.md
- docs/database_integration_v1.md

## Verification commands

- python scripts/check_doc_code_coherence.py (optional)

## Notes for next IA session

- Commencer par INT-001 uniquement; ne pas ouvrir de second chantier structurant.
- Relire d'abord la doctrine owner dans docs/runtime_consumption_v1.md.
- Aligner ensuite runtime-app sans redefinir ownership.
- Cloturer inter-repos seulement apres validation explicite des deux cotes.