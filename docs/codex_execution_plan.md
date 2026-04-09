# Codex Execution Plan - database

Statut: plan operatoire de reference
Portee: evolution sequentielle du repo Vicodertoten/database
Regle absolue: un seul gate actif a la fois

---

## 1. Mission

Faire evoluer database comme noyau de connaissance pedagogique du vivant, en conservant:

- canonique interne gouverne
- qualification traceable
- surfaces playable/pack/compiled/materialized exploitables
- separation stricte avec le runtime

Le runtime ne lit jamais export.bundle.v4.
Le runtime lit des surfaces dediees (playable, builds compiles, materializations).

---

## 2. Fichiers a lire avant modification

Codex doit lire au minimum:

- README.md
- docs/README.md
- docs/00_scope.md
- docs/01_domain_model.md
- docs/02_pipeline.md
- docs/05_audit_reference.md
- docs/06_charte_canonique_v1.md
- docs/10_program_kpis.md
- src/database_core/domain/models.py
- src/database_core/domain/enums.py
- src/database_core/pipeline/runner.py
- src/database_core/export/json_exporter.py
- src/database_core/storage/postgres.py
- src/database_core/storage/postgres_schema.py
- src/database_core/qualification/policy.py
- src/database_core/qualification/engine.py
- tests structurants gates 0 a 4

---

## 3. Etat reel du repo a respecter

Le repo est deja operationnel jusqu'au Gate 6:

- Gate 0: PostgreSQL/PostGIS
- Gate 1: verrou doctrinal
- Gate 2: playable v1
- Gate 3: pack + revisions + diagnostic
- Gate 4: compilation + materialization
- Gate 4.5: correctif strategique pre-extension
- Gate 5: politique distracteurs v2
- Gate 6: queue d'enrichissement

Ce repo n'est pas a refondre abstraitement.

Point critique explicite:

- cible finale playable: corpus cumulatif incremental reel
- etat actuel: surface latest reconstruite a chaque run
- ce delta doit etre traite avant extension metier

---

## 4. Decisions verrouillees

### 4.1 Frontiere runtime

- database porte canonique, qualification, playable, packs, compilation, materialization, enrichissement asynchrone futur, confusions batch futures
- runtime porte sessions, questions live, reponses, score, progression, UX

### 4.2 Canonique et sources externes

- les sources externes nourrissent le systeme
- elles ne definissent jamais librement l'identite interne
- creation canonique automatique reste soumise a la charte canonique v1

### 4.3 Similarites

- similarites externes (ex: similar species iNaturalist) peuvent etre stockees comme hints
- promotion vers similar_taxon_ids internes est autorisee si le taxon cible existe deja
- si cible absente, toute creation eventuelle reste gouvernee et tracee selon charte

### 4.4 Builds et materializations

- compiled builds historiques sont conserves
- leur generation doit rester traceable (pack/revision/source_run/build metadata)
- materializations figees sont immuables

### 4.5 Dette repository

- PostgresRepository concentre trop de responsabilites
- cette dette devient un chantier dedie
- pas de refactor lance dans la presente remise documentaire

---

## 5. Rappels de discipline

1. Un seul gate actif a la fois.
2. Pas de logique runtime/session/scoring/progression dans database.
3. Ne pas tordre export.bundle.v4 pour des besoins runtime.
4. Toute evolution structurante met a jour README.md et docs/05_audit_reference.md.
5. Avant gate suivant: code + tests + docs + migration + criteres d'acceptation complets.

---

## 6. Sequence de gates retenue

### Gates deja livres

- Gate 0 - Migration PostgreSQL/PostGIS: DONE
- Gate 1 - Verrou doctrinal + ADR de chaine: DONE
- Gate 2 - Playable corpus v1: DONE
- Gate 3 - Pack + revisions + diagnostic: DONE
- Gate 4 - Compilation dynamique + materialization figee: DONE
- Gate 4.5 - Correctif strategique pre-extension: DONE
- Gate 5 - Politique distracteurs v2 (dedie): DONE
- Gate 6 - Queue d'enrichissement: DONE
- Gate 7 - Contrat batch confusions + agregats globaux: DONE
- Gate 8 - Inspection/KPI/smoke/CI etendus: DONE
- Gate 9 - Retrait sidecar export v3: DONE

### Suite reordonnee

- Aucun gate actif dans ce plan de reference

---

## 7. Definition du Gate 4.5

Objectif:

- realigner proprement doctrine, plan et contexte d'execution post-Gate 4

Perimetre:

- clarifier explicitement playable cible cumulatif incremental
- clarifier explicitement etat actuel latest-surface
- clarifier statut historique des compiled builds
- clarifier immutabilite des materializations
- formaliser dette PostgresRepository comme chantier dedie
- preparer gate distracteurs v2 (objectif/perimetre/risques/acceptation)

Hors perimetre:

- aucun code metier nouveau
- aucune implementation Gate 5+
- aucun refactor repository

Criteres d'acceptation:

- documentation coherente inter-docs
- sequence de gates reordonnee sans ambiguite
- ecarts reels explicites, traces, et relies a la suite

---

## 8. Definition du Gate 5 (distracteurs v2)

Objectif:

- augmenter la qualite pedagogique de selection des distracteurs

Perimetre:

- policy distracteurs v2 avec priorisation pedagogique
- exploitation disciplinee des similarites internes
- prise en compte controlee des similar species iNaturalist
- promotion traceable vers similar_taxon_ids si cible interne existe deja

Contraintes:

- aucune source externe ne peut imposer l'identite interne
- creation canonique automatique eventuelle reste strictement sous regles charte
- pas de derive runtime/session/scoring

Criteres d'acceptation:

- selection distracteurs meilleure pedagogiquement et reproductible
- tracabilite des choix et fallbacks
- tests de non-regression explicites

---

## 9. Definition du Gate 6 (queue d'enrichissement)

Objectif:

- boucle asynchrone echec compilation -> demande enrichissement -> execution -> recompilation

Perimetre:

- enrichment_requests
- enrichment_request_targets
- enrichment_executions
- fusion logique de demandes similaires

Contraintes:

- jamais inline pendant compilation
- respect strict charte canonique
- pas de creation sauvage

---

## 10. Definition du Gate 7 (confusions batch)

Objectif:

- ingerer des batches de confusions runtime
- produire des agregats globaux plateforme

Hors perimetre:

- pas de temps reel
- pas d'adaptation automatique des distracteurs en ligne

---

## 11. Definition du Gate 8 (inspection et pilotage)

Objectif:

- etendre l'inspection operateur et la lisibilite des metriques
- conserver les KPI verrouilles existants

---

## 12. Definition du Gate 9 (retrait sidecar v3)

Objectif:

- retirer la dette de transition export.bundle.v3

Precondition:

- playable + pack + compilation + trajectoire enrichissement/confusions stabilises

---

## 13. Sortie attendue par gate

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

---

## 14. Rappel final

Ne pas faire de refonte abstraite.
Ne pas faire plusieurs gates a la fois.
Ne pas introduire de logique runtime/session.
Ne pas demarrer un chantier technique hors gate actif.
Faire evoluer le repo sequentiellement, avec coherence docs/tests.
