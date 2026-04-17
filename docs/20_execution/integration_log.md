# Inter-Repo Integration Log

Ce journal suit les synchronisations entre `database` et `runtime-app`.
Chaque entree correspond a un chantier identifie, avec un resume des decisions, des validations et de la prochaine etape.

Utilisation:

- ajouter une entree a l'ouverture d'un chantier inter-repos
- completer l'entree a chaque validation importante
- cloturer explicitement l'entree quand le chantier est termine dans les deux repos
- garder les exemples fictifs clairement marques comme fictifs

---

## Entry Template

### Chantier ID

[INT-000]

### Title

[Titre court du chantier]

### Status

[not_started | in_progress | blocked | validated | closed]

### Owner repo

[database]

### Consumer repo

[runtime-app]

### Summary

[Resume court de ce qui est aligne ou en cours d'alignement entre les deux repos]

### Decisions

- [Decision 1]
- [Decision 2]
- [Decision 3]

### Affected files

- [database: docs/...]
- [runtime-app: docs/...]
- [runtime-app: src/...]

### Linked commits

- [database: abc1234]
- [runtime-app: def5678]

### Verification

- [Commande ou preuve de verification cote owner]
- [Commande ou preuve de verification cote consumer]

### Next step

- [Prochaine etape exacte et sequentielle]

### Closed at

[YYYY-MM-DD or open]

---

## Active entries

### Chantier ID

INT-001

### Title

Lock runtime consumption doctrine v1

### Status

closed

### Owner repo

database

### Consumer repo

runtime-app

### Summary

runtime consumption boundary locked owner-side and consumer-side verified as aligned.

### Decisions

- `runtime-app` runtime surfaces are limited to `playable_corpus.v1`, `pack.compiled.v1`, and `pack.materialization.v1`.
- `export.bundle.v4` remains prohibited as a live runtime surface.
- `database` owns contract and artifact truth; `runtime-app` consumes without redefining ownership.

### Affected files

- database: docs/runtime_consumption_v1.md
- database: docs/20_execution/chantiers/INT-001.md
- database: docs/20_execution/handoff.md

### Linked commits

- database: 20da705
- database: 1f03803
- runtime-app: f9f556a

### Verification

- owner-side doctrinal coherence review completed against README.md and docs/runtime_consumption_v1.md
- consumer-side: `runtime-app/docs/database_integration_v1.md` verified as aligned with locked owner wording; no modification required

### Next step

INT-002

### Closed at

2026-04-15

---

### Chantier ID

INT-002

### Title

Align runtime-app/packages/contracts with official database schemas

### Status

closed

### Owner repo

database

### Consumer repo

runtime-app

### Summary

Owner and consumer steps complete: runtime-app contracts are aligned 1:1 with owner schemas and the cross-repo closure criteria are met.

### Decisions

- `schemas/playable_corpus_v1.schema.json` is the authoritative contract for `playable_corpus.v1`.
- `schemas/pack_compiled_v1.schema.json` is the authoritative contract for `pack.compiled.v1`.
- `schemas/pack_materialization_v1.schema.json` is the authoritative contract for `pack.materialization.v1`.
- No local field renaming is permitted in `runtime-app/packages/contracts`.

### Affected files

- database: docs/runtime_consumption_v1.md
- database: docs/20_execution/chantiers/INT-002.md
- database: docs/20_execution/handoff.md
- runtime-app: packages/contracts/src/index.ts
- runtime-app: packages/contracts/src/guards.ts
- runtime-app: packages/contracts/src/examples.ts
- runtime-app: packages/contracts/README.md
- runtime-app: docs/20_execution/chantiers/INT-002.md
- runtime-app: docs/20_execution/handoff.md
- runtime-app: docs/20_execution/integration_log.md

### Linked commits

- database: d921a9b
- database: 17f8349
- runtime-app: 1868923

### Verification

- owner-side: schemas verified as stable and complete on 2026-04-15
- consumer-side: field-level alignment verified against owner schemas; no local renaming or semantic transformation
- consumer-side command: `npx -y pnpm run check` passed (exit 0)

### Next step

INT-003

### Closed at

2026-04-15

---

### Chantier ID

INT-003

### Title

Runtime reference fixtures strategy v1 (owner-side)

### Status

closed

### Owner repo

database

### Consumer repo

runtime-app

### Summary

Owner-side fixture strategy is now explicit and first official minimal fixtures are published from real runtime surfaces (`playable_corpus.v1`, `pack.compiled.v1`, `pack.materialization.v1`) for local runtime consumption.

### Decisions

- Only `playable_corpus.v1`, `pack.compiled.v1`, and `pack.materialization.v1` are eligible as official runtime fixtures.
- `export.bundle.v4` is forbidden as a live runtime fixture source.
- Official fixture publication starts in `database`; `runtime-app` mirrors without semantic transformation.
- Published minimal fixture policy: playable subset of 4 coherent items + compiled(1 question) + materialization daily_challenge(1 question).
- No schema change and no runtime consumer code change in this owner step.

### Affected files

- database: docs/20_execution/chantiers/INT-003.md
- database: docs/20_execution/handoff.md
- database: docs/20_execution/integration_log.md
- database: fixtures/runtime/playable_corpus.sample.json
- database: fixtures/runtime/pack_compiled.sample.json
- database: fixtures/runtime/pack_materialization.sample.json
- runtime-app: docs/20_execution/chantiers/INT-003.md

### Linked commits

- database: 444188a
- runtime-app: open (INT-004 not started)

### Verification

- owner-side doctrinal consistency reviewed against `README.md`, `docs/runtime_consumption_v1.md`, and the three runtime schemas on 2026-04-15
- real DB state reused after schema migration to v15; pack compiled with `question_count=1`; materialized with `purpose=daily_challenge`; playable sample subset count verified at 4 items
- all three fixture files validated against official schemas (`playable_corpus_v1`, `pack_compiled_v1`, `pack_materialization_v1`)
- cross-ID coherence verified (`playable_item_id` and `canonical_taxon_id` references aligned across playable/compiled/materialization)

### Next step

- INT-004 (runtime-app consumer): adopt the published fixture trio in local integration tests, keeping strict field-level mirror semantics

### Closed at

2026-04-15

---

### Chantier ID

INT-004

### Title

Consumer integration closure on owner fixtures

### Status

closed

### Owner repo

database

### Consumer repo

runtime-app

### Summary

`runtime-app` consumed the official fixture trio published by `database` in INT-003 and validated runtime surface ingestion through consumer integration tests, with no new owner-side data surface required.

### Decisions

- INT-004 execution stayed consumer-side in `runtime-app`.
- `database` remained source of truth for runtime fixture payloads and contracts.
- No new runtime surface was introduced.
- No owner-side fixture/schema/pipeline/business logic change was required.

### Affected files

- database: docs/20_execution/chantiers/INT-004.md
- database: docs/20_execution/handoff.md
- database: docs/20_execution/integration_log.md
- runtime-app: apps/api/fixtures/playable_corpus.sample.json
- runtime-app: apps/api/fixtures/pack_compiled.sample.json
- runtime-app: apps/api/fixtures/pack_materialization.sample.json
- runtime-app: apps/api/src/tests/contracts.integration.test.ts
- runtime-app: docs/20_execution/chantiers/INT-004.md
- runtime-app: docs/20_execution/handoff.md
- runtime-app: docs/20_execution/integration_log.md

### Linked commits

- database: 444188a (owner fixture publication baseline, from INT-003)
- runtime-app: 36a8741

### Verification

- owner-side baseline confirmed: official fixtures from INT-003 remained unchanged
- consumer-side evidence (`runtime-app` 36a8741): fixture import completed, contract integration test added, checks passed
- inter-repo boundary preserved: runtime consumed official surfaces (`playable_corpus.v1`, `pack.compiled.v1`, `pack.materialization.v1`) with no owner contract drift

### Next step

- INT-005

### Closed at

2026-04-17

---

### Chantier ID

INT-007

### Title

Runtime consumption transport V1 doctrine

### Status

closed

### Owner repo

database

### Consumer repo

runtime-app

### Summary

Owner-side ADR now locks the shared transport narrative between repos without redefining existing runtime surfaces.

### Decisions

- Sequence is explicitly locked: V1 artifacts/fixtures, V1.5 minimal read API, later richer editorial operations.
- `apps/api` is the product entry point for runtime reads; web/mobile stay blind to data origin.
- `export.bundle.v4` remains excluded from live runtime surfaces.
- No schema, pipeline, or owner/consumer boundary change is introduced by INT-007.

### Affected files

- database: docs/adr/0004-runtime-consumption-transport-v1.md
- database: docs/20_execution/chantiers/INT-007.md
- database: docs/20_execution/handoff.md
- database: docs/20_execution/integration_log.md
- runtime-app: docs/adr/0001-runtime-database-transport-v1.md
- runtime-app: docs/20_execution/chantiers/INT-007.md
- runtime-app: docs/20_execution/handoff.md
- runtime-app: docs/20_execution/integration_log.md

### Linked commits

- database: this INT-007 closure commit (`[INT-007][database] add runtime consumption transport v1 ADR`)
- runtime-app: mirror closure commit (`[INT-007][runtime] add runtime-database transport v1 ADR`)

### Verification

- owner-side ADR text reviewed for strict non-regression vs existing runtime surface doctrine
- runtime mirror ADR aligned phrase-by-phrase on sequence and normative reminders
- no code or schema changes introduced

### Next step

- INT-008 or next planned inter-repo chantier from the ADR-0004 baseline

### Closed at

2026-04-17

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
