# Archived Fictitious Integration Log Examples

Purpose:
- keep fictitious examples available as historical templates
- keep `docs/20_execution/integration_log.md` focused on real current/recent entries

Status:
- archived reference only
- not a source of truth for current inter-repo state

Source:
- moved from `docs/20_execution/integration_log.md` on 2026-04-19

---

## Fictitious examples

Les exemples ci-dessous sont fictifs. Ils illustrent la forme attendue du journal et ne decrivent pas un etat reel du repo.

### Chantier ID

INT-001

### Title

Alignement des contrats runtime v1

### Status

closed

### Owner repo

database

### Consumer repo

runtime-app

### Summary

Exemple fictif: clarification des surfaces officielles consommees par le runtime pour eviter tout usage direct d'un bundle d'export comme surface live.

### Decisions

- Exemple fictif: `runtime-app` lit `playable_corpus.v1`, `pack.compiled.v1` et `pack.materialization.v1`.
- Exemple fictif: `export.bundle.v4` est interdit comme surface live.
- Exemple fictif: la documentation de consommation est verrouillee cote `database` avant adaptation du loader runtime.

### Affected files

- Exemple fictif: `database/docs/runtime_consumption_v1.md`
- Exemple fictif: `runtime-app/docs/runtime_data_contracts.md`
- Exemple fictif: `runtime-app/src/data/loadPlayableSurface.ts`

### Linked commits

- Exemple fictif: `database: 12ab34c`
- Exemple fictif: `runtime-app: 56de78f`

### Verification

- Exemple fictif: revue documentaire signee dans `database`
- Exemple fictif: test de chargement runtime passe sur fixture officielle

### Next step

- Exemple fictif: archiver le chantier et reutiliser la meme doctrine pour le prochain chantier runtime data.

### Closed at

2026-04-15

### Chantier ID

INT-002

### Title

Fixtures officielles runtime

### Status

validated

### Owner repo

database

### Consumer repo

runtime-app

### Summary

Exemple fictif: publication d'un jeu de fixtures officielles derivees des surfaces de serving pour stabiliser les tests d'integration du runtime.

### Decisions

- Exemple fictif: les fixtures de reference sont generees a partir d'artefacts `database` deja valides.
- Exemple fictif: `runtime-app` ne reconstruit pas ces fixtures a partir de donnees pipeline brutes.
- Exemple fictif: toute evolution de fixture reste rattachee a un chantier trace.

### Affected files

- Exemple fictif: `database/data/fixtures/runtime_pack_materialization_v1.json`
- Exemple fictif: `runtime-app/tests/fixtures/runtime_pack_materialization_v1.json`
- Exemple fictif: `runtime-app/tests/test_runtime_contract_loading.py`

### Linked commits

- Exemple fictif: `database: aa11bb2`
- Exemple fictif: `runtime-app: cc33dd4`

### Verification

- Exemple fictif: schema `pack.materialization.v1` valide cote owner
- Exemple fictif: tests de consommation runtime verts sur fixture officielle

### Next step

- Exemple fictif: cloturer le chantier apres confirmation que la fixture est devenue la seule reference de test runtime.

### Closed at

open

### Chantier ID

INT-003

### Title

Sequence d'integration materialization quotidienne

### Status

in_progress

### Owner repo

database

### Consumer repo

runtime-app

### Summary

Exemple fictif: definition d'une sequence de publication et de consommation pour une materialization quotidienne sans introduire de logique editoriale dans le runtime.

### Decisions

- Exemple fictif: la materialization quotidienne est publiee comme artefact fige cote `database`.
- Exemple fictif: le runtime selectionne un artefact publie mais ne le recompile pas.
- Exemple fictif: les operations editoriales restent hors du runtime.

### Affected files

- Exemple fictif: `database/docs/20_execution/chantiers/INT-003.md`
- Exemple fictif: `runtime-app/docs/daily_challenge_consumption.md`

### Linked commits

- Exemple fictif: `database: pending`
- Exemple fictif: `runtime-app: pending`

### Verification

- Exemple fictif: verification documentaire en cours cote owner
- Exemple fictif: integration runtime non demarree tant que le handoff owner n'est pas valide

### Next step

- Exemple fictif: finaliser le brief de chantier cote `database` puis ouvrir la tache de consommation cote `runtime-app`.

### Closed at

open
