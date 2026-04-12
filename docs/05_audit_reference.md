# Audit De Reference - database

Statut: document vivant (reference d'execution)
Version: v7
Date de mise a jour: 2026-04-09
Perimetre: etat reel du repo apres Gate 9 et synthese des constats structurants

---

## 1. Synthese executive

Le repo constitue une base strategiquement pertinente pour la future application,
mais comme database specialisee et noyau de connaissance, pas comme backend produit.

Etat confirme:

- gouvernance canonique v1 implemente et tracee
- pipeline reproductible avec artefacts versionnes
- qualification pedagogique et juridique explicite
- playable v1, packs, diagnostics, compilation, materialization, enrichissement queue, confusions batch en place
- tests structurants + CI + smoke KPI verrouilles

Deux ecarts structurants restent prioritaires:

- la cible playable est cumulative/incrementale, alors que l'implementation reste une surface latest reconstruite a chaque run
- `PostgresRepository` concentre trop de responsabilites et constitue la principale dette d'architecture

Positionnement recommande:

- proteger ce repo comme couche data specialisee
- maintenir la frontiere stricte avec le runtime
- corriger les deux dettes P0 avant toute extension de scope majeure

## 2. État réel

Le repo fait aujourd'hui, de maniere operationnelle:

- referentiel canonique interne birds-only avec IDs immuables et statuts de cycle de vie
- ingestion fixture et snapshot iNaturalist en cache local
- enrichissement canonique depuis payloads taxes en cache
- qualification image en 4 etapes avec trace IA/rules/licence/provenance
- review queue, overrides snapshot-scoped et gouvernance canonique manuelle
- export `export.bundle.v4` valide par schema
- surface `playable_corpus.v1` exploitable par filtres geo/date/pedagogie
- packs versionnes, diagnostics, builds compiles, materializations figees
- queue d'enrichissement asynchrone persistante
- ingestion batch de confusions et agregats globaux diriges
- inspection operateur et historique run-level en PostgreSQL/PostGIS

Le repo ne fait pas:

- runtime quiz, sessions, score, progression, UX
- serving temps reel adapte a l'utilisateur
- backend institutionnel ou gestion d'utilisateurs
- multi-source en implementation effective
- multi-groupe taxonomique
- qualification audio/video

Contraintes volontaires toujours en vigueur:

- birds-only
- iNaturalist-first et seule source active en implementation
- image-only
- pilot seed de 15 taxons
- couverture multilingue pedagogique encore partielle

## 3. Cible

La cible recommandee reste:

- une database specialisee de connaissance et de qualification naturaliste
- un playable corpus cumulatif incremental avec invalidation explicite
- des surfaces stables pour le runtime (`playable_corpus.v1`, `pack.compiled.v1`, `pack.materialization.v1`)
- une separation stricte entre data/core et runtime/session/scoring
- une extension progressive vers multi-source, multi-taxa, et meilleure qualite editoriale

Le runtime ne doit jamais lire `export.bundle.v4` comme surface de jeu.
Le runtime lit des surfaces dediees derivees de la database.

## 4. Forces confirmees

- canonique souverain, governable et traceable
- qualification explicite avec garde-fous juridiques et pedagogiques
- versionnage fort des contrats et artefacts
- historiques run/build/materialization conserves
- discipline documentaire et CI rare pour ce stade
- packs comme objets editoriaux credibles pour la suite produit

## 5. Ecarts structurants et priorites

### E1 - Playable cible vs implementation

Constat:

- cible: corpus cumulatif incremental
- implementation: reset + reconstruction de `playable_items`

Impact:

- surface de serving instable
- difficulte a considerer `playable_items` comme contrat runtime de production

Priorite:

- P0 strategique

### E2 - Concentration de responsabilites dans `PostgresRepository`

Constat:

- persistance, historique, diagnostics, compilation, materialization, metriques et confusions cohabitent dans un meme composant

Impact:

- couplage fort
- surface de regression elevee
- cout d'evolution croissant

Priorite:

- P0 strategique

### E3 - Editorialisation et multilingue encore incompletes

Constat:

- `common_names_i18n` est structurellement pret mais bootstrap `fr`/`nl` incomplet
- `key_identification_features` reste une couche enrichie encore pilote

Impact:

- limite immediate pour un produit grand public ou institutionnel multilingue

Priorite:

- P1 produit/editorial

### E4 - Dependance single-source

Constat:

- iNaturalist reste la seule source active en implementation et la seule autorite de phase 1

Impact:

- risque de dependance de gouvernance et de trajectoire scientifique

Priorite:

- P1 strategique

## 6. Contrats et versions observes

Etat schema applicatif observe:

- `database.schema.v14`

Contrats observes:

- `inaturalist.snapshot.v3`
- `normalized.snapshot.v3`
- `canonical.enrichment.v2`
- `qualification.staged.v1`
- `export.bundle.v4`
- `review.override.v1`
- `playable_corpus.v1`
- `pack.spec.v1`
- `pack.diagnostic.v1`
- `pack.compiled.v1`
- `pack.materialization.v1`
- `confusion.event.v1`
- `confusion.aggregate.v1`

## 7. KPI verrouilles

Les KPI programme verrouilles restent:

- `exportable_unresolved_or_provisional`
- `governance_reason_and_signal_coverage`
- `export_trace_flags_uncertainty_coverage`

Gate 8 a etendu les surfaces inspect, sans changer ni le nom, ni le seuil,
ni le format de ces KPI.

## 8. Recommandation de pilotage

Il n'y a pas de gate actif a ce stade de reference.

Gate 4.5 closure checklist:

- sequencage correctif applique avant extension
- posture cumulative incremental playable maintenue
- extraction progressive de `PostgresRepository` engagee sans rupture contractuelle

Gate 5 - Politique distracteurs v2

Les prochains travaux ne doivent etre ouverts que si leur cadrage respecte les points suivants:

1. priorite absolue au playable cumulatif incremental
2. cadrage explicite de l'extraction minimale de `PostgresRepository`
3. pas de derive runtime/session/scoring/progression
4. toute extension multi-source ou multi-taxa reste subordonnee aux deux points precedents

## 9. Garde-fous de documentation

- `README.md` et ce document doivent rester alignes sur l'etat reel
- les sections de transition de gates closes ne doivent pas etre conservees si elles n'apportent plus de valeur operative
- tout changement de contrat versionne, CI, KPI, ou doctrine structurante met a jour `README.md`, `docs/05_audit_reference.md`, et `docs/codex_execution_plan.md`

## 10. Plan d'execution concret des dettes P0

Ordre recommande:

1. P0-1: playable cumulatif incremental
2. P0-2: extraction minimale de `PostgresRepository`

Raison d'ordre:

- le repo doit d'abord stabiliser sa surface de serving principale
- la decomposition repository doit ensuite se faire contre une cible de persistance clarifiee
- faire l'inverse risquerait d'extraire des abstractions autour d'un modele playable encore provisoire

### P0-1 - Playable cumulatif incremental

Objectif:

- remplacer la logique latest-surface reconstruite par un corpus durable avec invalidation explicite

Perimetre recommande:

- formaliser le lifecycle d'un `PlayableItem`
- introduire les metadonnees de validite/invalidation necessaires
- conserver `playable_corpus.v1` comme contrat de lecture stable
- separer persistance historique et surface de serving courante sans full reset a chaque run

Criteres d'acceptation:

- aucun `DELETE FROM playable_items` global dans le run nominal
- un item valide au run N reste disponible au run N+1 tant qu'aucune invalidation explicite ne l'exclut
- les invalidations sont traceables par cause (qualification, gouvernance canonique, suppression source, autre regle explicite)
- `playable_corpus.v1` reste compatible pour les consommateurs actuels
- tests d'integration couvrent ajout, maintien, invalidation et non-regression des filtres geo/date/pedagogie

Impacts techniques:

- migration schema probable sur `playable_items`
- ajustement de `pipeline/runner.py`
- extraction ou reecriture de la logique `save_playable_items`
- nouveaux tests de persistance et de lineage

### P0-2 - Extraction minimale de `PostgresRepository`

Objectif:

- reduire le couplage sans lancer une refonte abstraite du repo

Perimetre recommande:

- conserver une facade repository stable si utile pour la compatibilite
- extraire d'abord les domaines les moins critiques pour la transaction pipeline centrale
- isoler au minimum:
	- operations pack/compilation/materialization
	- operations enrichment queue
	- operations confusion aggregates
	- lectures d'inspection/metrics

Criteres d'acceptation:

- baisse nette de la taille et du champ de responsabilite de `storage/postgres.py`
- surfaces publiques existantes preservees ou migrees de facon explicite
- aucune regression sur migrations, compilation pack, enrichment queue, confusion metrics, inspect CLI
- architecture cible lisible pour un nouveau contributeur sans reverse engineering du fichier unique

Impacts techniques:

- redistribution du code storage en modules ou services specialises
- mise a jour des imports CLI et pipeline
- renforcement des tests par zone fonctionnelle
- reduction du risque de conflits et regressions futures

Etat d'avancement (2026-04-09):

Phase 1 — domaine pack:
- extraction initiale effective du domaine pack vers `src/database_core/storage/pack_store.py`
- `PostgresRepository` delegue les operations pack principales au store specialise
- CLI `database-pack` et vues inspect pack (`pack-specs`, `pack-revisions`, `pack-diagnostics`, `compiled-pack-builds`, `pack-materializations`) utilisent directement le store pack
- suppression complete du bloc helper pack residuel dans `storage/postgres.py` (pas de duplication morte maintenue)
- reduction mesuree de `storage/postgres.py` sur cette phase pack: `3985 -> 3223` lignes (`-762`)
- test de non-regression ajoute pour valider le point d'entree `PostgresPackStore`
- suites `tests/test_storage.py` et `tests/test_cli.py` vertes apres suppression
- aucun changement de contrat export JSON sur ce lot (`no contract change`)

Phase 2 — domaines enrichment, confusion, inspection:
- extraction de l'ensemble du domaine enrichment queue vers `src/database_core/storage/enrichment_store.py` (`PostgresEnrichmentStore`)
  - methodes: `enqueue_enrichment_for_pack`, `create_or_merge_enrichment_request`, `fetch_enrichment_requests`, `fetch_enrichment_request_targets`, `fetch_enrichment_executions`, `record_enrichment_execution`, `fetch_enrichment_queue_metrics`
  - helpers prives `_normalize_enrichment_targets` et `_fetch_enrichment_target_signature` supprimes de `postgres.py`
- extraction du domaine confusion vers `src/database_core/storage/confusion_store.py` (`PostgresConfusionStore`)
  - methodes: `ingest_confusion_batch`, `fetch_confusion_events`, `recompute_confusion_aggregates_global`, `fetch_confusion_aggregates_global`, `fetch_confusion_metrics`
- extraction de la metrique qualification vers `src/database_core/storage/inspection_store.py` (`PostgresInspectionStore`)
  - methodes: `fetch_qualification_metrics`
- `PostgresRepository` conserve les delegations minces pour compatibilite de surface publique
- reduction totale de `storage/postgres.py`: `3985 -> 2422` lignes (`-1563` depuis le debut du gate P0-2)
- 52 tests storage + CLI verts apres extraction complete (aucune regression)

## 11. Architecture cible autour du repo

### `database`

Responsabilites:

- canonique interne
- ingestion, normalisation, enrichissement, qualification
- surfaces de serving pedagogiques (`playable_corpus.v1`)
- packs, diagnostics, builds compiles, materializations
- review, gouvernance, enrichissement asynchrone, confusions agrégées

### `runtime backend`

Responsabilites:

- sessions utilisateur
- selection et serving live des questions
- reponses, score, progression, personnalisation
- emission de batches de confusions vers `database`

### `editorial backend`

Responsabilites:

- creation et revision des packs
- outillage de revue et de gouvernance operateur
- supervision de la qualite editoriale et multilingue
- lancement des diagnostics, compilations et materializations

### `institutional backend`

Responsabilites:

- organisations, cohortes, assignments, reporting
- exposition B2Edu/B2Institution
- integrations externes et administration produit

### Interfaces recommandees

- `database` expose des contrats de donnees stables, pas une logique de runtime
- `runtime backend` lit `playable_corpus.v1`, `pack.compiled.v1`, `pack.materialization.v1`
- `editorial backend` pilote les operations de packs/review/gouvernance contre la couche database
- `institutional backend` consomme les sorties runtime et certains indicateurs consolides, pas le brut pipeline

## 12. Mode de mise a jour

Regles:

1. toute evolution structurante met a jour `README.md` et ce document
2. tout reordonnancement de priorites met a jour aussi `docs/codex_execution_plan.md`
3. toute divergence doc/code est documentee comme ecart explicite
