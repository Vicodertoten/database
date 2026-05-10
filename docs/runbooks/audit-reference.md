---
owner: database
status: stable
last_reviewed: 2026-05-09
source_of_truth: docs/runbooks/audit-reference.md
scope: runbook
---

# Audit De Reference - database

Statut: document vivant (reference d'execution)
Version: v8.2
Date de mise a jour: 2026-05-09
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

Etat de transition confirme:

- le lifecycle playable cumulatif/incremental (`active`/`invalidated`) est implemente et visible en schema + code
- la decomposition storage en stores specialises est deja engagee et operationnelle, avec `storage/services.py` comme point d'orchestration
- `storage/postgres.py` reste une facade de compatibilite encore transitoire (responsabilites reduites, mais simplification a poursuivre)
- la sequence transport owner-side runtime-read est preservee comme contexte
  historique; le runtime courant consomme `session_snapshot.v2` et fallback
  `golden_pack.v1`

Positionnement recommande:

- proteger ce repo comme couche data specialisee
- maintenir la frontiere stricte avec le runtime
- consolider l'operationnel deja implemente (lifecycle playable, decomposition storage) avant extension de scope majeure

## 2. État réel

Le repo fait aujourd'hui, de maniere operationnelle:

- referentiel canonique interne birds-only avec IDs immuables et statuts de cycle de vie
- ingestion fixture et snapshot iNaturalist en cache local
- enrichissement canonique depuis payloads taxes en cache
- qualification image en 4 etapes avec trace IA/rules/licence/provenance
- review queue, overrides snapshot-scoped et gouvernance canonique manuelle
- export `export.bundle.v4` valide par schema
- surface `playable_corpus.v1` exploitable par filtres geo/date/pedagogie
- surface `playable_corpus.v1` etendue avec metadata player-ready minimales owner-side (`taxon_label`, `feedback_short`, `media_render_url`, `media_attribution`, `media_license`)
- packs versionnes, diagnostics, builds compiles, materializations figees
- queue d'enrichissement asynchrone persistante
- ingestion batch de confusions et agregats globaux diriges
- ingestion `runtime_answer_signals.v1` vers confusion events owner et agregats globaux par locale/source
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
- couverture multilingue pedagogique en progression: extraction iNaturalist branchee, gouvernance editoriale encore partielle
- cadrage court terme v0.1 verrouille dans `docs/runbooks/v0.1-scope.md`:
  oiseaux, Belgique, image-only, QCM + reponse directe simple,
  objectif sans appel live iNaturalist et volume cible 50 especes / 1 000 images qualifiees
- backlog explicite hors v0.1: plantes, champignons, insectes, audio,
  offline avance, IA premium, gros dashboard institutionnel,
  multi-pays complexe, marketplace de packs, application parfaite

## 3. Cible

La cible recommandee reste:

- une database specialisee de connaissance et de qualification naturaliste
- un playable corpus cumulatif incremental avec invalidation explicite
- `session_snapshot.v2` comme surface runtime active et `golden_pack.v1` comme fallback
- des surfaces historiques / strategic-later (`playable_corpus.v1`, `pack.compiled.v1`, `pack.materialization.v1`) conservees comme infrastructure utile, mais pas cible runtime actuelle
- une direction produit dynamic pack documentee dans `docs/architecture/DYNAMIC_PACK_PRODUCT_ROADMAP.md`
- une separation stricte entre data/core et runtime/session/scoring
- une extension progressive vers multi-source, multi-taxa, et meilleure qualite editoriale

Le runtime ne doit jamais lire `export.bundle.v4` comme surface de jeu.
Le runtime lit uniquement des surfaces dediees derivees de la database et
explicitement verrouillees pour la phase concernee.

## 4. Forces confirmees

- canonique souverain, governable et traceable
- qualification explicite avec garde-fous juridiques et pedagogiques
- versionnage fort des contrats et artefacts
- historiques run/build/materialization conserves
- discipline documentaire et CI rare pour ce stade
- packs comme objets editoriaux credibles pour la suite produit

## 5. Ecarts structurants et priorites

### E1 - Playable lifecycle implemente, stabilisation operationnelle a poursuivre

Constat:

- lifecycle cumulatif incremental en place: `playable_item_lifecycle` porte `active`/`invalidated`
- `playable_corpus.v1` sert uniquement les items actifs
- invalidations explicites presentes (`qualification_not_exportable`, `canonical_taxon_not_active`, `source_record_removed`, `policy_filtered`)

Impact:

- reduction nette du risque de serving latest-only
- meilleure explicabilite operateur via causes d'invalidation explicites
- point transitoire restant: stabiliser les pratiques d'exploitation et de monitoring sur cette base

Priorite:

- consolidation P0 deja en place, suivi operatoire continu

### E2 - Decomposition storage en place, facade `PostgresRepository` encore transitoire

Constat:

- separation reelle en modules specialises: `pack_store`, `playable_store`, `enrichment_store`, `confusion_store`, `inspection_store`
- orchestration explicite via `storage/services.py`
- `storage/postgres.py` conserve une surface de delegation/facade pour compatibilite

Impact:

- dette d'architecture reduite de maniere tangible
- migration plus lisible pour les consommateurs internes
- residuel: simplification progressive de la facade et clarification finale de la topologie publique

Priorite:

- consolidation transitoire (pas une refonte)

### E3 - Editorialisation et multilingue partiellement consolides

Constat:

- `common_names_i18n` est desormais alimente depuis l'enrichissement multilingue iNaturalist quand les noms langues sont presents
- `key_identification_features_by_language` existe en structure, mais la source amont reste limitee

Impact:

- progression tangible pour le serving pedagogique multilingue, mais couverture/qualite editoriale encore inegales selon taxons

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

- `database.schema.v20`

Contrats observes:

- `inaturalist.snapshot.v3`
- `normalized.snapshot.v3`
- `canonical.enrichment.v2`
- `qualification.staged.v1`
- `export.bundle.v4`
- `review.override.v1`
- `playable_corpus.v1` (owner/internal, pas cible runtime courante)
- `pack.spec.v1`
- `pack.diagnostic.v1`
- `pack.compiled.v1` (historique)
- `pack.materialization.v1` (historique)
- `confusion.event.v1`
- `confusion.aggregate.v1`

References semantiques historiques / transitional:

- `pack.compiled.v2`
- `pack.materialization.v2`

## 7. KPI verrouilles

Les KPI programme verrouilles restent:

- `exportable_unresolved_or_provisional`
- `governance_reason_and_signal_coverage`
- `export_trace_flags_uncertainty_coverage`

Gate 8 a etendu les surfaces inspect, sans changer ni le nom, ni le seuil,
ni le format de ces KPI.

## 8. Recommandation de pilotage

Le chantier Phase 3 taxon-based question options est maintenant un contexte
historique / transitional. Les anciens plans sont archives dans
`docs/archive/superseded-contracts/`.

Le pilotage courant doit suivre `docs/architecture/contract-map.md`:

- `session_snapshot.v2` est le contrat runtime jouable actif;
- `pack_pool.v1` est le pool source owner-side;
- `golden_pack.v1` est le fallback;
- `pack.compiled.v2` et `pack.materialization.v2` restent des references
  semantiques, pas le prochain handoff runtime.

Gate 4.5 closure checklist:

- sequencage correctif applique avant extension
- posture cumulative incremental playable maintenue
- extraction progressive de `PostgresRepository` engagee sans rupture contractuelle

Gate 5 - Politique distracteurs v3

Les prochains travaux ne doivent etre ouverts que si leur cadrage respecte les points suivants:

1. priorite absolue au playable cumulatif incremental
2. cadrage explicite de l'extraction minimale de `PostgresRepository`
3. pas de derive runtime/session/scoring/progression
4. toute extension multi-source ou multi-taxa reste subordonnee aux deux points precedents
5. pas d'auto-creation de taxons canoniques actifs pour des distracteurs seulement references
6. `pack.compiled.v1` et `pack.materialization.v1` restent compatibles pour
   l'historique et l'outillage owner, sans redevenir contrats runtime actifs

## 9. Garde-fous de documentation

- `README.md` et ce document doivent rester alignes sur l'etat reel
- les sections de transition de gates closes ne doivent pas etre conservees si elles n'apportent plus de valeur operative
- tout changement de contrat versionne, CI, KPI, ou doctrine structurante met a jour `README.md`, `docs/runbooks/audit-reference.md`, et `docs/runbooks/execution-plan.md`

## 10. Plan d'execution concret apres implementation des dettes P0

Ordre recommande:

1. P0-1: playable cumulatif incremental (implante)
2. P0-2: extraction minimale de `PostgresRepository` (largement implemente)

Raison d'ordre:

- le repo doit d'abord stabiliser sa surface de serving principale
- la decomposition repository doit ensuite se faire contre une cible de persistance clarifiee
- faire l'inverse risquerait d'extraire des abstractions autour d'un modele playable encore provisoire

### P0-1 - Playable cumulatif incremental

Statut: implemente (base operationnelle en place)

Objectif (atteint):

- remplacer la logique latest-surface reconstruite par un corpus durable avec invalidation explicite

Perimetre recommande:

- formaliser le lifecycle d'un `PlayableItem`
- introduire les metadonnees de validite/invalidation necessaires
- conserver `playable_corpus.v1` comme contrat de lecture owner/internal stable
- separer persistance historique et surface de serving courante sans full reset a chaque run

Criteres d'acceptation:

- aucun `DELETE FROM playable_items` global dans le run nominal
- un item valide au run N reste disponible au run N+1 tant qu'aucune invalidation explicite ne l'exclut
- les invalidations sont traceables par cause explicite (`qualification_not_exportable`, `canonical_taxon_not_active`, `source_record_removed`, `policy_filtered`)
- `playable_corpus.v1` reste compatible pour les consommateurs owner/internal
  explicites, sans redevenir cible runtime courante
- tests d'integration couvrent ajout, maintien, invalidation et non-regression des filtres geo/date/pedagogie

Impacts techniques:

- migration schema `database.schema.v19` sur `distractor_relationships` (Palier A canonical-only + audit DB-first)
- migration schema `database.schema.v20` sur les signaux runtime: enrichissement des batches/evenements de confusion et agregats globaux par locale/source
- ajustement de `save_playable_items` pour raison explicite
- ajout d'une surface inspect dediee aux invalidations playable
- tests de persistance/lifecycle et CLI inspect couverts

### P0-2 - Extraction minimale de `PostgresRepository`

Statut: implemente en grande partie, reste transitoire sur facade

Objectif (largement atteint):

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

Phase 3 — domaine playable corpus (2026-04-12):
- extraction du bloc playable lifecycle write+read vers `src/database_core/storage/playable_store.py` (`PostgresPlayableStore`)
  - methodes migrees: `save_playable_items`, `fetch_playable_corpus`, `fetch_playable_corpus_payload`, `fetch_playable_invalidations`
  - helper prive `_invalidate_missing_playable_items` integre dans le store (non expose)
  - helper module-level `_resolve_playable_run_id` migre dans `playable_store.py` et supprime de `postgres.py`
  - imports devenus inutiles retires de `postgres.py`: `InvalidationReason`, `validate_playable_corpus`, `PLAYABLE_CORPUS_VERSION`
- `PostgresRepository` conserve des facades de delegation strictes pour les 4 methodes — aucun changement de contrat public
- reduction de `storage/postgres.py` sur cette phase: `2422 -> 2034` lignes (`-388`)
- `PostgresPlayableStore` exporte depuis `storage/__init__.py`
- suites `tests/test_storage.py`, `tests/test_pipeline.py`, `tests/test_cli.py` vertes apres extraction

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
- `runtime backend` lit `session_snapshot.v2` comme contrat jouable actif et
  `golden_pack.v1` comme fallback; toute reouverture de
  `playable_corpus.v1`, `pack.compiled.*`, `pack.materialization.*`, ou
  owner-read comme chemin runtime doit faire l'objet d'une decision explicite
- `editorial backend` pilote les operations de packs/review/gouvernance contre la couche database
- `institutional backend` consomme les sorties runtime et certains indicateurs consolides, pas le brut pipeline

## 12. Mode de mise a jour

Regles:

1. toute evolution structurante met a jour `README.md` et ce document
2. tout reordonnancement de priorites met a jour aussi `docs/runbooks/execution-plan.md`
3. toute divergence doc/code est documentee comme ecart explicite
