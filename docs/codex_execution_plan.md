# Codex Execution Plan — `database`

Statut: plan de travail opératoire pour Codex / VS Code  
Portée: évolution séquentielle du repo `Vicodertoten/database`  
Règle absolue: exécuter **un seul gate à la fois**, sans chevauchement

---

## 1. Mission

Faire évoluer proprement le repo actuel vers une database pédagogique du vivant capable de :

- maintenir un canonique interne stable
- qualifier pédagogiquement des ressources réelles
- produire un **playable corpus** vivant pour le runtime
- supporter des **packs** versionnés et compilables
- supporter une **matérialisation figée** dérivée d’un pack
- supporter une **queue d’enrichissement** asynchrone déclenchée par les besoins
- ingérer des **confusions runtime** en batch pour produire des agrégats globaux

Le runtime ne doit **jamais** lire `export.bundle.v4`.
Le runtime lira uniquement :
- des surfaces dédiées requêtables côté database
- et/ou des artefacts dérivés type playable / compiled pack / materialization

---

## 2. Fichiers à lire obligatoirement avant toute modification

Codex doit lire **réellement** les fichiers suivants avant d’agir :

- `README.md`
- `docs/README.md`
- `docs/00_scope.md`
- `docs/01_domain_model.md`
- `docs/02_pipeline.md`
- `docs/05_audit_reference.md`
- `docs/06_charte_canonique_v1.md`
- `docs/10_program_kpis.md`
- `src/database_core/domain/models.py`
- `src/database_core/domain/enums.py`
- `src/database_core/domain/canonical_governance.py`
- `src/database_core/domain/canonical_reconciliation.py`
- `src/database_core/pipeline/runner.py`
- `src/database_core/export/json_exporter.py`
- `src/database_core/storage/schema.py`
- `src/database_core/storage/sqlite.py`
- `src/database_core/qualification/policy.py`
- `src/database_core/qualification/engine.py`
- tests structurants :
  - `tests/test_pipeline.py`
  - `tests/test_inat_snapshot.py`
  - `tests/test_canonical_rules.py`
  - `tests/test_storage.py`
  - `tests/test_smoke_report.py`

---

## 3. État du repo à respecter

Le repo actuel est déjà :

- un **knowledge core** birds-first / iNaturalist-first / image-only
- un noyau canonique gouverné
- un pipeline séquentiel et reproductible
- un stockage versionné avec history + logs + review queues
- un export versionné `export.bundle.v4`
- une qualification pédagogique minimale déjà structurée
- une discipline documentaire explicite
- une discipline de gates séquentiels explicite

Ce repo **n’est pas** à refondre abstraitement.

---

## 4. Décisions verrouillées

### 4.1 Runtime / export
- `export.bundle.v4` reste un **bundle noyau**, pas un contrat quiz
- le runtime ne lit jamais `export.bundle.v4`
- le runtime lit seulement :
  - la couche playable
  - les compiled packs
  - les materializations figées

### 4.2 Stockage
- la cible principale devient **PostgreSQL / Supabase**
- SQLite devient au mieux un support transitoire/local, pas la cible long terme
- la database doit fournir des surfaces requêtables réelles
- les artefacts JSON restent des dérivés secondaires utiles, pas la source principale

### 4.3 Playable corpus
- le playable corpus est **vivant et incrémental**
- il s’update progressivement
- il ne remplace pas le canonique ni l’export noyau
- il doit supporter les filtres utiles à la compilation des packs

### 4.4 Noms / langues
- les noms communs sont multi-langues dès v1
- langues minimales obligatoires :
  - `fr`
  - `en`
  - `nl`
- utiliser une structure extensible, pas 3 colonnes rigides comme vérité unique

### 4.5 Feedback blocks
- feedback blocks matérialisés dès la couche playable
- blocs minimaux v1 :
  - `what_to_look_at_specific`
  - `what_to_look_at_general`
  - `confusion_hint`
- `what_to_look_at_general` appartient au taxon enrichi, mais peut être dupliqué dans le playable pour simplifier le runtime

### 4.6 Signaux pédagogiques
Les signaux pédagogiques clés à rendre réellement opératoires sont :
- `difficulty_level`
- `media_role`
- `learning_suitability`
- `confusion_relevance`

`diagnostic_feature_visibility` et `learning_suitability` doivent être présents dans la couche playable, mais peuvent rester `unknown` sans bloquer la compilation.

### 4.7 Packs
- le pack est un **objet durable**
- le pack est **révisable par versions immuables**
- modèle retenu :
  - `pack_id` stable
  - `revision` à chaque modification
- le pack n’est pas une partie
- le pack peut être persisté même s’il est non compilable
- le pack peut cibler plusieurs taxons
- le pack peut cibler plusieurs niveaux taxonomiques dans le scope birds
- multi-groupes réels hors birds = backlog `future_scope`

### 4.8 Difficulté pack
Difficultés utilisateur v1 :
- `easy`
- `balanced`
- `hard`
- `mixed`

Interprétation :
- `easy` = privilégier les items faciles
- `balanced` = équilibre easy / medium / hard
- `hard` = privilégier les items difficiles
- `mixed` = aucune préférence forte, on prend ce que l’offre servable permet

Ne pas modifier les enums cœur existants juste pour refléter ces politiques utilisateur.

### 4.9 Géographie / temps
Géographie v1 :
- `country_code`
- `bbox`
- `point + radius`

Ne pas introduire `region` en v1 si cela complique ou fragilise le système.

Temps :
- UTC strict
- bornes inclusives
- toute l’année par défaut si pas de filtre

### 4.10 Compilabilité
Seuils globaux initiaux v1 :
- `min_taxa_served = 10`
- `min_media_per_taxon = 2`
- `min_total_questions = 20`
- objectif indicatif non bloquant : `target_taxa_served = 50`

`questions_possible` signifie :
- **questions réellement servables**
- donc avec distracteurs valides
- si les distracteurs sont insuffisants, la question n’existe pas

### 4.11 Compilation / matérialisation
- le compiled pack dynamique se sert dans la database selon les paramètres du pack
- si de nouveaux éléments compatibles entrent dans la database, ils peuvent apparaître dans le compiled pack dynamique
- seule la **materialization figée** échappe à cette règle
- une materialization figée fige :
  - les items cibles
  - les distracteurs exacts
- valeurs par défaut v1 :
  - `question_count = 20`
  - `daily_challenge_ttl = 24h`

### 4.12 Enrichissement
- si un pack n’est pas compilable, il doit être refusé pour le moment
- il peut proposer une demande d’enrichissement
- l’enrichissement est **asynchrone**
- jamais d’exécution inline pendant la compilation
- fusion logique des demandes similaires :
  - une demande principale
  - les autres comme `interested_requests`
- annulation d’une demande = fin réelle de la demande
- hors birds réel = backlog `future_scope`
- si ambiguïté canonique, blocage local du scope touché
- aucune création canonique sauvage
- toute création canonique automatique reste soumise à la charte canonique existante

### 4.13 Confusions runtime
- contrat d’ingestion des confusions dès ce programme
- ingestion **batch**, pas temps réel
- agrégats v1 :
  - **globaux plateforme seulement**
- pas d’adaptation automatique des distracteurs ou de la compilation à ce stade

### 4.14 Institutionnel léger
Ce repo peut porter :
- `owner_id`
- `org_id`
- `visibility`
- `intended_use`

Ce repo ne doit pas porter :
- auth
- comptes
- classes
- élèves
- essais
- scores
- progression

### 4.15 Sidecar export v3
- le sidecar `v3` doit être retiré dans ce programme
- le retrait se fait **après** stabilisation de :
  - la couche playable
  - le modèle pack
  - la compilation pack

---

## 5. Règles de méthode obligatoires

### 5.1 Discipline documentaire
- mettre à jour les docs existantes avant d’en créer de nouvelles
- toute évolution structurante doit mettre à jour :
  - `README.md`
  - `docs/05_audit_reference.md`
- ne créer un nouveau document que si aucun document existant ne peut raisonnablement porter le sujet
- un seul nouvel ADR structurant est autorisé pour cette chaîne :
  - `docs/adr/0003-playable-corpus-pack-compilation-enrichment-queue.md`

### 5.2 Discipline d’exécution
- un seul gate à la fois
- pas de chevauchement
- toute règle automatique doit avoir un test de non-régression
- toute évolution de contrat doit être versionnée et validée
- ne pas avancer au gate suivant tant que :
  - code
  - tests
  - docs
  - migration éventuelle
  - critères d’acceptation
  sont complets pour le gate courant

### 5.3 Discipline d’architecture
- ne pas tordre `export.bundle.v4`
- ne pas polluer `run_pipeline` avec la logique métier packs/compilation/enrichissement
- préserver le noyau existant
- ajouter la nouvelle chaîne **en aval**, pas en remplacement brutal du noyau actuel

### 5.4 Pas de dérive
Ne pas introduire :
- logique session/scoring/progression
- gameplay profond
- LMS/backoffice complet
- adaptation runtime temps réel
- stratégie offline/mobile comme focus principal
- ouverture multi-groupes immédiate

---

## 6. Boundarys à respecter

### 6.1 Database ↔ Runtime
La database doit porter :
- canonique
- qualification
- playable corpus
- feedback blocks
- packs
- pack revisions
- pack diagnostics
- compiled pack builds
- pack materializations
- enrichment requests / executions
- confusion events / global aggregates

Le runtime doit porter :
- session de quiz
- questions servies en direct
- réponses
- score
- progression
- essais
- UX
- fenêtres d’assignation exécutoires

### 6.2 Pack ↔ Partie
- un pack = définition durable et paramétrique d’un univers de quiz
- une partie = exécution runtime éphémère
- une materialization figée = snapshot stable dérivé d’un pack, sans état utilisateur

### 6.3 Compilation ↔ Enrichissement
- compilation = travaille uniquement sur l’offre existante
- enrichissement = augmente l’offre
- compilation = déterministe, sans appels externes
- enrichissement = asynchrone, traçable, gouverné

---

## 7. Gates séquentiels à exécuter

## Gate 0 — Migration storage vers PostgreSQL / Supabase (+ PostGIS)
Objectif :
- faire de Postgres la cible principale
- préparer le support géographique utile (`country_code`, `bbox`, `point+radius`)
- garder SQLite au mieux comme support transitoire/local

À produire :
- repository Postgres principal
- migrations SQL Postgres versionnées
- adaptation des tests/CI
- docs mises à jour

Ne pas faire :
- ne pas commencer les packs ici
- ne pas profiter de ce gate pour refaire le domaine

### Critères d’acceptation
- Postgres backend principal fonctionnel
- CI exécute le repo sur Postgres
- noyau canonique / qualification / export v4 inchangés fonctionnellement

---

## Gate 1 — Verrou doctrinal + ADR de chaîne
Objectif :
- écrire noir sur blanc les boundarys
- formaliser playable / packs / compilation / enrichissement
- corriger le scope documentaire du repo

À produire :
- mise à jour docs existantes
- ADR `0003`

Ne pas faire :
- pas de nouvelles tables packs ici
- pas de modifications runtime/session

### Critères d’acceptation
- doctrine stable et non ambiguë
- `README.md` et `docs/05_audit_reference.md` à jour

---

## Gate 2 — Playable corpus vivant v1
Objectif :
- créer une couche playable vivante, incrémentale et versionnée
- ajouter les feedback blocks matérialisés
- ajouter les champs nécessaires à la compilation future

À produire :
- modèle `playable item`
- stockage DB/vues/table dérivée
- schéma `playable_corpus_v1`
- tests dédiés

Le playable doit au minimum porter :
- `canonical_taxon_id`
- noms communs multi-langues
- nom scientifique
- signaux pédagogiques clés
- `similar_taxon_ids`
- feedback blocks
- références source discrètes
- facettes géo/date utiles

Ne pas faire :
- ne pas remplacer `export.bundle.v4`
- ne pas mettre de logique de session

### Critères d’acceptation
- surface playable vivante fonctionnelle
- validation contractuelle
- `export.bundle.v4` inchangé

---

## Gate 3 — Modèle de pack + révisions + diagnostic de compilabilité
Objectif :
- introduire `pack_id + revision`
- introduire les paramètres de pack
- introduire un diagnostic formel compilable / non compilable

À produire :
- `pack_specs`
- `pack_revisions`
- `pack_compilation_attempts` / diagnostics
- schémas de contrat pack
- tests

Paramètres v1 :
- multi-taxons birds
- difficulté `easy|balanced|hard|mixed`
- une seule forme géo active
- date UTC
- `owner_id`, `org_id`, `visibility`, `intended_use`

Le diagnostic doit produire :
- liste des déficits mesurés
- `reason_code`
- détail utile par taxon bloquant quand pertinent

Ne pas faire :
- ne pas créer encore des parties
- ne pas implémenter auth/classes/élèves

### Critères d’acceptation
- un pack non compilable peut être persisté
- toute modification crée une nouvelle révision
- diagnostic déterministe sans appels externes

---

## Gate 4 — Compilation dynamique + materialization figée
Objectif :
- compiler un pack contre la database/playable
- distinguer clairement compiled pack dynamique et materialization figée

À produire :
- `compiled_pack_builds`
- `pack_materializations`
- schémas contractuels
- tests compilation et figé

Règles :
- compiled pack dynamique = vit avec la base
- materialization figée = fige items + distracteurs exacts
- valeurs par défaut :
  - `question_count = 20`
  - `ttl = 24h` pour défi du jour

Ne pas faire :
- pas de score
- pas de tentatives utilisateur
- pas de progression

### Critères d’acceptation
- compiled pack dynamique traçable
- release figée stable et rejouable comme base de devoir/défi

---

## Gate 5 — Queue d’enrichissement
Objectif :
- créer la boucle échec compilation → demande enrichissement → exécution → recompilation

À produire :
- `enrichment_requests`
- `enrichment_request_targets`
- `enrichment_executions`
- worker/queue séquentiel v1
- backlog `future_scope`
- fusion logique des demandes similaires

Règles :
- jamais inline
- scope ambigu = blocage local
- respect strict de la charte canonique
- annulation = demande terminée

Ne pas faire :
- ne pas réutiliser la review queue existante pour cette logique
- ne pas appeler de sources externes pendant la compilation

### Critères d’acceptation
- traçabilité bout-en-bout complète
- demandes similaires fusionnées
- recompilation liée possible

---

## Gate 6 — Contrat batch des confusions + agrégats globaux
Objectif :
- recevoir des batches de confusions runtime
- calculer des agrégats globaux plateforme

À produire :
- `confusion_events`
- `confusion_aggregates_global`
- schéma d’ingestion batch
- tests

Ne pas faire :
- pas de temps réel
- pas d’adaptation automatique
- pas de reporting institutionnel détaillé

### Critères d’acceptation
- ingestion batch fiable
- agrégats globaux exploitables

---

## Gate 7 — Inspection / KPIs / smoke / CI
Objectif :
- rendre la nouvelle chaîne pilotable
- ajouter des métriques observatoires
- préserver les KPIs historiques

À produire :
- inspection playable / packs / enrichissement
- métriques observatoires nouvelles
- tests smoke/reporting

Ne pas faire :
- ne pas casser les KPIs verrouillés historiques
- ne pas faire de dashboard produit lourd

### Critères d’acceptation
- inspection opérateur utile
- KPIs historiques toujours valides
- nouvelles métriques visibles

---

## Gate 8 — Retrait du sidecar export v3
Objectif :
- retirer la dette transitoire `v3`

Précondition :
- playable + pack + compilation stabilisés

À produire :
- suppression génération `v3`
- suppression tests/doc associée
- mise à jour docs

### Critères d’acceptation
- `v3` retiré
- `v4` stable
- runtime branché sur playable / compiled pack / materialization

---

## 8. Sortie attendue pour chaque gate

Avant toute modification, Codex doit rendre :
1. un résumé de compréhension du gate
2. la liste des fichiers qu’il prévoit de modifier
3. les risques principaux
4. les tests qu’il prévoit d’ajouter

Après exécution du gate, Codex doit rendre :
1. la liste exacte des fichiers modifiés
2. les décisions prises
3. les migrations ajoutées
4. les schémas/contrats ajoutés ou modifiés
5. les tests ajoutés
6. les commandes à lancer pour vérifier
7. ce qui reste volontairement hors scope du gate

---

## 9. Rappel final pour Codex

Ne pas faire de refonte abstraite.
Ne pas modifier plusieurs gates à la fois.
Ne pas introduire de logique runtime/session.
Ne pas tordre `export.bundle.v4`.
Préserver le noyau existant.
Faire évoluer le repo proprement, séquentiellement, avec docs et tests à chaque étape.
