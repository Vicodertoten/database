# Handoff Template

Ce document est un modele operationnel de reprise de travail pour une session IA ou humaine.
Remplir les crochets avant de transmettre le contexte.

## Current active chantier

- ID: [INT-000]
- Title: [Titre court et stable du chantier]
- Status: [not_started | in_progress | blocked | validated | closed]

## Repo role in current chantier

- Current repo: [database]
- Role: [owner | consumer]
- Other repo: [runtime-app]
- Expected dependency order: [database first, runtime-app second]

## Last validated state

- Last validated commit or tag: [abc1234 or none]
- Validation date: [YYYY-MM-DD]
- What is already validated: [contrat confirme, doc mise a jour, integration locale verifiee]
- What is not validated yet: [adaptation runtime, verification inter-repos, revue finale]

## Decisions already locked

- [`database` reste owner des contrats et artefacts data concernes]
- [`runtime-app` consomme les surfaces officielles et ne les redefinit pas]
- [`export.bundle.v4` n'est pas une surface live runtime]
- [Autre decision verrouillee utile a la reprise]

## Important constraints

- [Ne pas toucher aux schemas existants]
- [Ne pas modifier la logique pipeline]
- [Rester strictement sequentiel et traçable]
- [Autre contrainte bloquante]

## Next exact step

- [Exemple: relire docs/runtime_consumption_v1.md puis verifier que runtime-app lit uniquement pack.materialization.v1 pour le cas cible]

## Files to read first in this repo

- [README.md]
- [docs/README.md]
- [docs/codex_execution_plan.md]
- [docs/03_open_questions.md]
- [docs/runtime_consumption_v1.md]
- [docs/20_execution/chantiers/INT-000.md]

## Files to read first in the other repo

- [README.md]
- [docs/integration/runtime_contracts.md]
- [src/runtime/contracts/loaders.ts]
- [docs/handshake_with_database.md]

## Verification commands

- [python scripts/check_doc_code_coherence.py]
- [python -m pytest -q -m "not integration_db" -p no:capture]
- [commandes de verification du repo consumer]

## Notes for next IA session

- [Commencer par verifier si le chantier courant est toujours le seul chantier structurant actif]
- [Ne pas ouvrir un second chantier tant que le statut n'est pas `validated` ou `closed`]
- [Relire les decisions verrouillees avant toute proposition de changement inter-repos]
- [Si un ecart apparait entre owner et consumer, corriger d'abord le repo owner ou la documentation de reference]