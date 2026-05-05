---
owner: database
status: stable
last_reviewed: 2026-04-29
source_of_truth: docs/foundation/runtime-consumption-v1.md
scope: foundation
---

# Runtime Consumption V1

Cette note fixe la frontiere de consommation entre `database` et `runtime-app`.

`database` porte la verite des contrats et des artefacts de reference.
`runtime-app` consomme ces surfaces officielles; il ne les redefinit pas.

## Note MVP Golden Pack (2026-05-05)

Pour le MVP Golden Pack, la surface runtime prioritaire est
`golden_pack.v1`, produite comme artefact local versionne sous
`data/exports/golden_packs/belgian_birds_mvp_v1/`.

`golden_pack.v1` est un artefact pedagogique exporte contenant un contrat
runtime strict. Le runtime MVP le consomme en mode artifact-only, sans transport
HTTP owner-side obligatoire.

Les surfaces et transports decrits ci-dessous (`playable_corpus.v1`,
`pack.compiled.v1`, `pack.materialization.v1`, service HTTP owner-side) restent
des surfaces existantes ou strategiques, mais ne sont pas le contrat MVP Golden
Pack. Pour les decisions Golden Pack et runtime artifact-only, la reference
canonique est `docs/architecture/MASTER_REFERENCE.md`.

## Etat de transport actuel

Hors MVP Golden Pack, le transport inter-repos existant suit la sequence
suivante:

- V1: fixtures de reference publiees cote owner et validees cote consumer
- V1.5: API minimale de lecture cote `runtime-app/apps/api`
- Phase 1: service HTTP owner-side minimal de lecture runtime cote `database`

Pour cette famille de surfaces, le mode nominal de lecture runtime n'est plus fixture-only.
Le provider owner-side est maintenant la jonction nominale; les fixtures restent un fallback explicite dev/test.

## Etat courant visible (reference de wording)

Pour l'alignement inter-repos, l'etat courant doit etre formule sans ambiguite:

- lecture runtime nominale: owner-side reelle en place (`database`)
- sessions runtime nominales: persistees cote `runtime-app`
- web runtime: minimal pedagogical player
- mobile runtime: surface minimale reelle image-first (rendu image prioritaire en UI)

Aucun texte majeur ne doit presenter cet etat courant comme un simple demonstrateur technique d'IDs.

## Phase 1 - read transport owner-side minimal (en place)

Un service owner-side de lecture runtime est maintenant en place dans `database`,
borne strictement aux 3 surfaces officielles:

- `GET /playable-corpus` -> `playable_corpus.v1`
- `GET /packs/{pack_id}/compiled/{revision?}` -> `pack.compiled.v1`
- `GET /materializations/{materialization_id}` -> `pack.materialization.v1`

Implementation owner-side:

- facade de lecture: `src/database_core/runtime_read/service.py`
- serveur HTTP minimal: `src/database_core/runtime_read/http_server.py`
- entree script: `database-runtime-read-owner`

Write/editorial owner-side transport (separe du runtime-read):

- facade write: `src/database_core/editorial_write/service.py`
- serveur HTTP write: `src/database_core/editorial_write/http_server.py`
- entree script: `database-editorial-write-owner`

Ces implementations restent volontairement minimales:

- read runtime: borne aux 3 surfaces officielles
- write/editorial: borne aux operations pack/enrichment owner-side formalisees
- aucune logique session/scoring/progression
- aucune exposition du brut pipeline
- observabilite operationnelle minimale incluse:
  - runtime-read `/health` enrichi (`service_version`, `ready`, `limits`)
  - logs requete JSON (`method`, `path`, `status`, `error_category`, `latency_ms`)

## Hypothese reseau owner-side (R4)

Pour le deploiement cible Fly.io:

- les services owner-side (`database-runtime-read-owner`, `database-editorial-write-owner`) ne sont exposes qu'en reseau prive interne (`.internal`)
- toute exposition publique de ces services est une violation de securite
- un secret inter-service optionnel peut etre active:
  - header attendu: `X-Owner-Service-Token`
  - variable owner-side: `OWNER_SERVICE_TOKEN`
  - variable consumer-side (`runtime-api`): `DATABASE_OWNER_SERVICE_TOKEN`

## Surfaces officiellement consommables

Hors MVP Golden Pack artifact-only, `runtime-app` peut consommer les surfaces
suivantes comme surfaces runtime officielles:

- `playable_corpus.v1`
- `pack.compiled.v1`
- `pack.materialization.v1`

Contrats Phase 3 planifies, a consommer seulement apres production cote `database`:

- `pack.compiled.v2`
- `pack.materialization.v2`

Pour le MVP Golden Pack, ces surfaces ne doivent pas etre traitees comme le
contrat runtime principal.

## Surface interdite pour le runtime

`runtime-app` ne doit jamais utiliser `export.bundle.v4` comme surface live.
Ce bundle peut servir a des usages d'export ou d'inspection, mais pas a la lecture runtime officielle.

## Regle de responsabilite

- `database` possede la verite des contrats, des artefacts et de leur semantique
- `runtime-app` consomme ces artefacts, mais ne les redefinit pas
- toute evolution d'une surface officielle doit d'abord etre verrouillee dans `database`

## Schemas de reference officielle

Les schemas JSON suivants sont la source de verite officielle pour les types de consommation runtime.
Tout type consumer (TypeScript ou autre) doit refleter ces schemas champ par champ, sans renommage local.

- `schemas/playable_corpus_v1.schema.json` — reference pour `playable_corpus.v1`
- `schemas/pack_compiled_v1.schema.json` — reference pour `pack.compiled.v1`
- `schemas/pack_materialization_v1.schema.json` — reference pour `pack.materialization.v1`
- `schemas/pack_compiled_v2.schema.json` — reference planifiee pour `pack.compiled.v2`
- `schemas/pack_materialization_v2.schema.json` — reference planifiee pour `pack.materialization.v2`

Regles Phase 3 v2:

- `database` produit les `QuestionOption[]`
- `runtime-app` affiche les options snapshottees sans recalcul
- `runtime-app` ne resout pas les labels de taxons
- `runtime-app` ne score pas les distracteurs
- `selectedOptionId` devient la soumission standard pour v2
- `selectedPlayableItemId` reste legacy pour v1 pendant la transition

Extension additive historique sur `playable_corpus.v1` (sans changement de version de contrat):

- `playable_corpus.v1` expose maintenant un minimum player-ready owner-side:
  - `taxon_label`
  - `feedback_short`
  - `media_render_url`
  - `media_attribution`
  - `media_license`

Ces champs restent prepares owner-side dans `database`; `runtime-app` les consomme sans redefinition semantique.

Etat Phase 4 (runtime-side, sans changement owner-side additionnel):

- `runtime-app/apps/api` projette maintenant ces champs dans des DTOs player-ready pour:
  - `GET /sessions/:sessionId/question`
  - `POST /sessions/:sessionId/answers`
- cette phase ne change pas la frontiere owner/consumer:
  - `database` reste owner des surfaces et de leur semantique
  - `runtime-app` reste assembleur de session/UX a partir des surfaces officielles

## Regle de non-renommage

Aucun consommateur n'est autorise a renommer, abrevger ou simplifier les champs de ces schemas.
Les noms de champs definis dans `database` sont les noms officiels.
Toute deviation locale constitue une derive qui doit etre corrigee du cote consumer.

## Consequence pratique

Les futures operations editoriales ou institutionnelles doivent respecter cette frontiere.
Elles peuvent s'appuyer sur les artefacts publies par `database`, mais ne doivent pas deplacer la source de verite hors du knowledge core.
Tout besoin runtime non couvert par ces surfaces doit d'abord etre formalise et verrouille dans `database`.

Rappel de perimetre:

- le runtime-read couvre uniquement la lecture des 3 surfaces officielles
- le transport write/editorial owner-side est separe et borne a l'orchestration pack/enrichment
- auth forte, cache distribue et sync avancee restent hors scope
