# Codex Execution Plan - database

Statut: plan operatoire de reference
Portee: evolution sequentielle du repo Vicodertoten/database apres le baseline Gate 9
Regle absolue: un seul chantier structurant actif a la fois

---

## 1. Mission

Faire evoluer `database` comme noyau de connaissance pedagogique du vivant,
en conservant:

- canonique interne gouverne
- qualification traceable
- surfaces playable/pack/compiled/materialized exploitables
- separation stricte avec le runtime

Le runtime ne lit jamais `export.bundle.v4`.
Le runtime lit des surfaces dediees (`playable_corpus.v1`, builds compiles, materializations).

## 2. Fichiers a lire avant modification

Codex doit lire au minimum:

- `README.md`
- `docs/README.md`
- `docs/00_scope.md`
- `docs/01_domain_model.md`
- `docs/02_pipeline.md`
- `docs/03_open_questions.md`
- `docs/05_audit_reference.md`
- `docs/06_charte_canonique_v1.md`
- `docs/10_program_kpis.md`
- `src/database_core/domain/models.py`
- `src/database_core/domain/enums.py`
- `src/database_core/pipeline/runner.py`
- `src/database_core/export/json_exporter.py`
- `src/database_core/storage/postgres.py`
- `src/database_core/storage/postgres_schema.py`
- `src/database_core/qualification/policy.py`
- `src/database_core/qualification/engine.py`
- tests structurants gates 0 a 9

## 3. Etat reel du repo a respecter

Le repo est deja operationnel jusqu'au Gate 9:

- Gate 0: PostgreSQL/PostGIS
- Gate 1: verrou doctrinal
- Gate 2: playable v1
- Gate 3: pack + revisions + diagnostic
- Gate 4: compilation + materialization
- Gate 4.5: correctif strategique pre-extension
- Gate 5: politique distracteurs v2
- Gate 6: queue d'enrichissement
- Gate 7: confusions batch + agregats globaux
- Gate 8: inspection/KPI/smoke/CI
- Gate 9: retrait sidecar export v3

Ce repo n'est pas a refondre abstraitement.
Il doit etre consolide a partir de son etat reel.

Markers de traçabilite (compatibilite verification):

- Gate 4.5 - Correctif strategique pre-extension
- Gate 5 - Politique distracteurs v2
- Gate 6 - Queue d'enrichissement
- Gate 7 - Contrat batch confusions + agregats globaux
- Gate 8 - Inspection/KPI/smoke/CI etendus

## 4. Decisions verrouillees

### 4.1 Frontiere runtime

- `database` porte canonique, qualification, playable, packs, compilation, materialization, enrichissement asynchrone, confusions batch et agregats
- runtime porte sessions, questions live, reponses, score, progression, UX

### 4.2 Canonique et sources externes

- les sources externes nourrissent le systeme
- elles ne definissent jamais librement l'identite interne
- creation canonique automatique reste soumise a la charte canonique v1

### 4.3 Builds et materializations

- les compiled builds historiques sont conserves
- les materializations figees sont immuables
- le runtime ne doit pas reconstituer ces objets a partir du brut

### 4.4 Dettes structurelles explicites

- playable cumulatif incremental: implemente (`active`/`invalidated`) avec causes explicites
- decomposition storage: largement implementee via stores specialises + `storage/services.py`
- statut restant: facade `PostgresRepository` encore transitoire, a simplifier sans rupture de contrat

## 5. Chantiers prioritaires admissibles

Il n'y a pas de gate actif par defaut dans ce plan.
Si un nouveau chantier structurant est ouvert, il doit appartenir a l'un des axes suivants:

1. consolidation operatoire du playable cumulatif incremental implemente
2. consolidation finale de l'extraction de responsabilites hors `PostgresRepository`
3. qualite editoriale et multilingue des surfaces pedagogiques
4. extension multi-source ou multi-taxa seulement apres 1 et 2

Tout autre chantier doit etre considere comme secondaire ou hors-sequence.

Ordre de consolidation recommande:

1. maintenir la stabilite du modele playable deja migre
2. poursuivre la simplification de la facade `PostgresRepository` sur base des extractions deja en place

Critere de maintien de la phase transitoire:

- pas de retour a une reconstruction latest-only du serving playable
- causes d'invalidation conservees explicites et testees
- `playable_corpus.v1` reste stable pour les consommateurs

Etat d'avancement constate (2026-04-09):

- schema `database.schema.v15` actif pour le lifecycle playable incremental
- `playable_items` n'est plus supprime globalement dans le run nominal PostgreSQL
- lifecycle `active`/`invalidated` persiste en base et `playable_corpus.v1` ne sert que les items actifs
- reactivation automatique couverte en test storage
- causes d'invalidation explicites et testees en P0-1 (`qualification_not_exportable`, `canonical_taxon_not_active`, `source_record_removed`, `policy_filtered`)

Etat d'avancement P0-2 (2026-04-12):

- phase 1 pack (`pack_store.py`): complete
- phase 2 enrichment/confusion/inspection (`enrichment_store.py`, `confusion_store.py`, `inspection_store.py`): complete
- phase 3 playable corpus (`playable_store.py`): complete — bloc playable lifecycle write+read extrait, facades delegation conservees, `-388` lignes de `postgres.py`, total `3985 -> 2034` lignes

Etat d'avancement P3 (2026-04-12):

- extension `CanonicalTaxon` avec surfaces multilingues optionnelles (`common_names_by_language`, `key_identification_features_by_language`) et fallback compatibilite vers `en`
- enrichissement iNaturalist: extraction des noms par langue depuis `names[]` + merge dedup par langue
- serving playable: alimentation `common_names_i18n` depuis les champs multilingues enrichis, avec fallback legacy
- signal pedagogique: `confusion_hint` enrichi avec nom scientifique + nom commun (si disponible)
- non-regression: tests gate dedies + suites structurantes + `verify_repo` verts

## 6. Discipline d'execution

1. Un seul chantier structurant actif a la fois.
2. Pas de logique runtime/session/scoring/progression dans `database`.
3. Ne pas tordre `export.bundle.v4` pour des besoins runtime.
4. Toute evolution structurante met a jour `README.md`, `docs/05_audit_reference.md`, et ce document.
5. Avant ouverture d'un nouveau chantier: code + tests + docs + migration + criteres d'acceptation complets.

## 7. Sortie attendue pour tout chantier

Avant execution:

1. resume de comprehension
2. fichiers prevus
3. risques
4. tests prevus

Apres execution:

1. fichiers modifies
2. decisions prises
3. migrations
4. contrats/schema modifies
5. tests ajoutes/modifies
6. commandes de verification
7. hors-scope volontaire

## 8. Rappel final

Ne pas faire de refonte abstraite.
Ne pas faire plusieurs chantiers structurants a la fois.
Ne pas introduire de logique runtime/session.
Ne pas demarrer un chantier hors priorite sans mise a jour de la doctrine.
Faire evoluer le repo sequentiellement, avec coherence code/docs/tests.
