---
owner: database
status: stable
last_reviewed: 2026-05-10
source_of_truth: docs/foundation/runtime-consumption-v1.md
scope: foundation
---

# Runtime Consumption V1

Cette note fixe la frontiere de consommation entre `database` et `runtime-app`.

`database` porte la verite des contrats et des artefacts de reference.
`runtime-app` consomme ces surfaces officielles; il ne les redefinit pas.

## Note contract stack active (2026-05-10)

La source canonique du statut des contrats runtime est
`docs/foundation/runtime-contract-stack-v1.md`.
La frontiere entre le compilateur dynamique interne et le contrat produit
`session_snapshot.v2` est documentee dans
`docs/foundation/dynamic-session-compiler-internals-v1.md`.

Etat actif:

- `session_snapshot.v2` est le contrat runtime jouable actif.
- `serving_bundle.v1` est l'input local actif que `runtime-app` peut projeter en
  `session_snapshot.v2` au demarrage d'une session.
- `golden_pack.v1` reste le fallback runtime quand le mode Dynamic Pack est
  desactive ou indisponible.
- `pack_pool.v1` est owner-only.
- `runtime_answer_signals.v1` est le handback batch runtime -> owner.

Les surfaces et transports decrits ci-dessous (`playable_corpus.v1`,
`pack.compiled.v1`, `pack.materialization.v1`, service HTTP owner-side) restent
historiques / strategic-later. Ils ne sont pas la cible runtime actuelle.

## Note Dynamic Pack (2026-05-09)

La cible Dynamic Pack est maintenant verrouillee pour le runtime courant:
`serving_bundle.v1` -> `session_snapshot.v2`. La suite produit reste:
challenges/devoirs figes et batchs de signaux runtime vers `database`.
`session_snapshot.v2` est un contrat produit exporte; les politiques de
selection, de seed, de distracteurs, de locale et de nombre de questions sont
des inputs de materialisation/export, pas le modele domaine interne generique.

La reference de vision est `docs/architecture/DYNAMIC_PACK_PRODUCT_ROADMAP.md`.
Le plan Phase 0 est archive dans
`docs/archive/runbooks/dynamic-pack-phase-0-plan.md`.

## Etat de transport historique

La famille owner-side runtime-read suit l'historique suivant:

- V1: fixtures de reference publiees cote owner et validees cote consumer
- V1.5: API minimale de lecture cote `runtime-app/apps/api`
- Phase 1: service HTTP owner-side minimal de lecture runtime cote `database`

Cette famille est historical / strategic-later. Elle n'est pas le mode nominal
du runtime courant, qui consomme des artefacts locaux `serving_bundle.v1`,
`session_snapshot.v2`, et fallback `golden_pack.v1`.

## Etat courant visible (reference de wording hors MVP Golden Pack)

Pour l'alignement inter-repos de la famille owner-side historique, l'etat
courant
doit etre formule sans ambiguite:

- lecture runtime nominale: owner-side reelle en place (`database`)
- sessions runtime nominales: persistees cote `runtime-app`
- web runtime: minimal pedagogical player
- mobile runtime: surface minimale reelle image-first (rendu image prioritaire en UI)

Aucun texte majeur ne doit presenter cet etat historique comme la cible runtime
courante. Le runtime courant consomme `session_snapshot.v2`, avec
`golden_pack.v1` comme fallback, et ne depend pas du transport HTTP owner-side.

## Phase 1 - read transport owner-side minimal (en place)

Statut: historical / strategic-later. Cette section documente le transport
owner-side existant; elle ne definit pas le contrat runtime courant.

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

## Surfaces owner-side historiques / strategic-later

`runtime-app` peut consommer les surfaces suivantes seulement si cette famille
owner-side est explicitement rouverte dans le scope. Elles restent legacy /
strategic-later et ne sont pas la cible runtime actuelle:

- `playable_corpus.v1`
- `pack.compiled.v1`
- `pack.materialization.v1`

Contrats Phase 3 historiques / strategic-later:

- `pack.compiled.v2`
- `pack.materialization.v2`

Ces surfaces ne doivent pas etre traitees comme le contrat runtime principal.

## Surface interdite pour le runtime

`runtime-app` ne doit jamais utiliser `export.bundle.v4` comme surface live.
Ce bundle peut servir a des usages d'export ou d'inspection, mais pas a la lecture runtime officielle.

## Regle de responsabilite

- `database` possede la verite des contrats, des artefacts et de leur semantique
- `runtime-app` consomme ces artefacts, mais ne les redefinit pas
- toute evolution d'une surface officielle doit d'abord etre verrouillee dans `database`

## Schemas de reference officielle

Les schemas JSON suivants restent la source de verite officielle pour la famille
owner-side / legacy / strategic-later. Ils ne sont pas les schemas du stack
runtime actif.

Tout type consumer (TypeScript ou autre) qui consomme cette famille doit refleter
ces schemas champ par champ, sans renommage local.

- `schemas/playable_corpus_v1.schema.json` — reference pour `playable_corpus.v1`
- `schemas/pack_compiled_v1.schema.json` — reference pour `pack.compiled.v1`
- `schemas/pack_materialization_v1.schema.json` — reference pour `pack.materialization.v1`
- `schemas/pack_compiled_v2.schema.json` — reference historique / strategic-later pour `pack.compiled.v2`
- `schemas/pack_materialization_v2.schema.json` — reference historique / strategic-later pour `pack.materialization.v2`

Regles Phase 3 v2:

- `database` produit les `QuestionOption[]`
- `runtime-app` affiche les options snapshottees sans recalcul
- `runtime-app` ne resout pas les labels de taxons
- `runtime-app` ne score pas les distracteurs
- `selectedOptionId` devient la soumission standard pour v2
- `selectedPlayableItemId` reste legacy pour v1 pendant la transition

Statut historique:

- `pack.compiled.v2` et `pack.materialization.v2` sont legacy / historical /
  non-runtime context
- le runtime courant ne selectionne pas de distracteurs depuis ces surfaces
- le runtime courant ne resout pas de labels depuis ces surfaces
- le runtime courant ne depend pas d'un fetch HTTP owner-side

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
  owner-side non-MVP Golden Pack
- le transport write/editorial owner-side est separe et borne a l'orchestration pack/enrichment
- auth forte, cache distribue et sync avancee restent hors scope
