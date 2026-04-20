# Audit Complet — Plateforme Pédagogique du Vivant
**Repos audités :** `database` + `runtime-app`  
**Date :** 19 avril 2026  
**Périmètre :** audit complet, transversal, professionnel — architecture, domaine, code, tests, sécurité, qualité, vision, cohérence

---

## Table des matières

1. [Synthèse exécutive](#1-synthèse-exécutive)
2. [Architecture globale et séparation des responsabilités](#2-architecture-globale-et-séparation-des-responsabilités)
3. [Repo `database` — analyse complète](#3-repo-database--analyse-complète)
4. [Repo `runtime-app` — analyse complète](#4-repo-runtime-app--analyse-complète)
5. [Analyse transversale](#5-analyse-transversale)
6. [Cohérence vision ↔ implémentation](#6-cohérence-vision--implémentation)
7. [Sécurité](#7-sécurité)
8. [Dettes techniques et risques](#8-dettes-techniques-et-risques)
9. [Recommandations prioritaires](#9-recommandations-prioritaires)
10. [Verdict final](#10-verdict-final)

---

## 1. Synthèse exécutive

### État général

Le projet se trouve à un stade **remarquablement avancé** pour son âge et son contexte de développement solo ou petit noyau. La majorité des fondations architecturales décrites dans le document de vision sont présentes, opérationnelles, et défendables techniquement. Les deux repos forment un système cohérent avec une frontière claire.

**Le `database` repo** est une base de données spécialisée de connaissance naturaliste avec qualification pédagogique, gouvernance canonique, pipeline reproductible, et surfaces serving dédiées. Il opère bien au-delà d'un prototype.

**Le `runtime-app` repo** est un monorepo produit qui consomme proprement les surfaces publiées par `database`, avec une API backend fonctionnelle (Fastify/Node.js), une application mobile (Expo/React Native), et une application web (Next.js). La session, le serving de questions, le scoring, et le feedback pédagogique de base sont opérationnels.

### Verdict global

| Dimension | Notation | Commentaire |
|---|---|---|
| Architecture | ★★★★☆ | Frontières bien posées, quelques résidus transitoires |
| Domaine & modèles | ★★★★★ | Exceptionnel pour ce stade |
| Pipeline data | ★★★★☆ | Robuste et versionné, mono-source en implémentation |
| Gouvernance canonique | ★★★★★ | Rare à ce niveau, traçabilité exemplaire |
| Qualité du code | ★★★★☆ | Bonne discipline, quelques zones de concentration |
| Tests | ★★★☆☆ | Solide sur le domaine, couverture intégration partielle |
| Sécurité | ★★★☆☆ | Aucune faille critique, mais posture défensive encore légère |
| Documentation | ★★★★★ | Exceptionnelle pour ce stade |
| Cohérence vision/code | ★★★★☆ | Très bonne, quelques gaps explicitement identifiés |
| Maturité produit | ★★★☆☆ | MVP technique solide, UX quasi inexistante |

---

## 2. Architecture globale et séparation des responsabilités

### 2.1 Topologie du système

```
┌─────────────────────────────────────────────────────────────┐
│                         database repo                        │
│                                                             │
│  iNaturalist/GBIF → ingest → normalize → qualify →         │
│  export.bundle.v4 (vérité riche)                           │
│                           ↓                                 │
│  playable_corpus.v1  ←── playable build (Gate 2)          │
│  pack.compiled.v1    ←── pack compile  (Gate 4)            │
│  pack.materialization.v1 ← materialize (Gate 4)            │
│                           ↓                                 │
│  HTTP owner-side:                                          │
│    /playable-corpus          (runtime_read)                │
│    /packs/:id/compiled       (runtime_read)                │
│    /materializations/:id     (runtime_read)                │
│    /editorial/packs/*        (editorial_write)             │
└────────────────────────────┬────────────────────────────────┘
                             │ HTTP (owner-side)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                       runtime-app repo                       │
│                                                             │
│  apps/api (Fastify)                                        │
│    ├── GET  /playable-corpus     → from database           │
│    ├── GET  /packs/*             → from database           │
│    ├── POST /sessions/...        → session store           │
│    ├── GET  /sessions/:id/question → PlayableCorpusIndex   │
│    └── POST /sessions/:id/answers  → scoring + feedback    │
│                                                             │
│  packages/contracts  ← consumer-only mirror des schemas    │
│                                                             │
│  apps/web  (Next.js)  ← web player + editorial             │
│  apps/mobile (Expo)   ← mobile player                     │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Jugement sur la séparation

La séparation est **correctement posée et tenue**. Le runtime ne relit jamais `export.bundle.v4`. Il consomme des surfaces serving dédiées (`playable_corpus.v1`, `pack.compiled.v1`, `pack.materialization.v1`). Le `database` repo ne contient pas de logique de session, de scoring, ou de progression.

**Points forts de la séparation :**
- `packages/contracts/src/index.ts` est explicitement annoté comme un miroir consommateur, avec interdiction d'ajouter des champs absents des schémas sources
- `AGENTS.md` du runtime-app définit clairement les hard boundaries
- Le transport inter-repo passe par HTTP owner-side avec validation de contrat des deux côtés
- Les deux repos ont leurs propres systèmes de versioning indépendants

**Résidus et tensions :**
- La surface `editorial_write` du `database` est exposée via HTTP mais le runtime-app agit comme proxy editorial (les routes `/editorial/*` de l'API proxient vers le `database`). Ceci est **logique** à court terme mais crée un couplage opérationnel non documenté comme tel dans les ADRs
- Le `playable_corpus.v1` est chargé en mémoire entier à chaque question demandée (`readPlayableCorpus()` appelé à chaque `GET /sessions/:id/question` et `POST /sessions/:id/answers`). Ceci est un choix de simplicité valide en dev/MVP mais devient un problème de performance dès que le corpus grossit

---

## 3. Repo `database` — analyse complète

### 3.1 Positionnement et vision

Le repo se positionne explicitement comme **knowledge core** du produit, pas comme backend produit. Cette frontière est respectée dans le code. L'`audit_reference.md` (v8, Gate 9) constitue une documentation de bord rare et précieuse : il liste ce que le repo fait, ce qu'il ne fait pas, et les écarts structurants restants. C'est du pilotage de projet discipliné.

### 3.2 Domaine — models.py

**C'est le point le plus fort du repo.** Le fichier `src/database_core/domain/models.py` est un modèle de rigueur :

- Tous les modèles héritent de `DomainModel(BaseModel)` avec `extra="forbid"`, `frozen=True` — immutabilité et étanchéité garanties
- Les validateurs `@field_validator` et `@model_validator` encodent la logique métier (ex : `QualifiedResource.validate_exportability` — un resource exportable doit être `ACCEPTED` et `SAFE`, sinon ValueError immédiate)
- `CanonicalTaxon` auto-normalise ses champs dans `normalize_canonical_fields` (slug, `similar_taxon_ids` dérivés, status auto-déprécié si split/merge, fallback multilingual)
- `GeoBBox` valide l'ordre des coordonnées
- `PackRevisionParameters` interdit les conflits de filtres géographiques et les incohérences point/rayon
- `PlayableItem.validate_common_names_i18n` impose fr/en/nl comme langues obligatoires

**Observations :**
- La gestion multilingual est présente et correcte (`common_names_i18n`, `common_names_by_language`, `key_identification_features_by_language`) mais la couverture éditoriale est encore inégale selon les taxons — c'est documenté (E3 dans `05_audit_reference.md`)
- `AIQualification` et `QualifiedResource` ont des validateurs de confiance (0.0–1.0) bien posés
- La cohérence entre `canonical_taxon_id`, `taxon_group` et le pattern regex est vérifiée en model validator — c'est du bon travail

**Lacune identifiée :**
- Pas de validation de l'URL dans `MediaAsset.source_url` (format, schéma autorisé, injection potentielle de schémas non-HTTPS). À surveiller quand les données viennent d'iNaturalist en prod.

### 3.3 Gouvernance canonique

Le module `domain/canonical_governance.py` est **exceptionnellement structuré** pour ce stade. Il implémente un système complet de gouvernance des transitions canoniques avec :

- `CanonicalTransitionSignal` : 5 signaux booléens + score agrégé
- `CanonicalAuthorityDelta` : delta complet entre version précédente et actuelle des données sources
- `SOURCE_PRIORITY` : hiérarchie de confiance explicite (iNaturalist > GBIF > Wikimedia)
- Catégorisation des décisions en `auto_clear` vs `manual_reviewed` avec raison précise (10 codes de raison)

Les transitions split/merge/replace/derived sont toutes explicitement modélisées, tracées, et ne réécrivent jamais l'histoire — c'est le principe fondateur du système canonical souverain.

**C'est un avantage concurrentiel réel.** Très peu de systèmes naturalistes à ce stade ont une gouvernance canonique aussi rigoureuse.

**Lacune identifiée :**
- `canonical_reconciliation.py` existe mais son intégration dans le pipeline n'est pas visible dans les tests non-intégration. Les chemins de réconciliation sont des surfaces à fort risque de régression qu'il faudra couvrir plus largement quand le multi-source sera activé.

### 3.4 Pipeline de qualification

Le pipeline (`pipeline/runner.py`) est un orchestrateur bien structuré avec :
- 13 gates numérotées, toutes documentées dans `02_pipeline.md`
- Staging des artefacts avant promotion atomique
- Versioning explicite de tous les artefacts (`schema_version`, `qualification_version`, etc.)
- Mode multi-source (fixture / inat_snapshot) avec résolution des chemins de sortie
- Gestion des overrides de review snapshot-scoped (non-destructifs sur les artefacts bruts)

**Le moteur de qualification (`qualification/engine.py`) est propre :**
- 4 stages indépendants : compliance screening, fast semantic screening, expert qualification, review queue assembly
- Combinaison de flags sans chevauchement (`list(dict.fromkeys(...))`)
- Propagation de la provenance complète (run_id, modèle IA, prompt version, task name, statut IA)
- Flag automatique `deprecated_canonical_taxon` et rejet automatique

**Lacunes identifiées :**
1. La gestion des exceptions dans `runner.py` est absente à plusieurs endroits : si `_stage_pipeline_artifacts` réussit mais que `save_*` échoue à mi-chemin, les artefacts stagés sont orphelins. Il y a une `ArtifactPromotionError` mais le `try/except` du bloc de persistence n'est pas complet.
2. Le pipeline recrée son `run_id` par défaut mais le garde stable si fourni. La génération est `uuid4()` — correct. Mais les `run_id` ne sont pas vérifiés pour unicité dans le store avant insertion.
3. `_default_qualifier_mode` et `_default_uncertain_policy` sont des fonctions internes à `runner.py` — leur logique est opaque depuis l'extérieur sans lire le code. Un commentaire ou une doc de référence dans `02_pipeline.md` serait utile.

### 3.5 Stockage et persistence

**Architecture du stockage :**
- `PostgresStorageInternal` est une **façade transitoire** qui délègue aux stores spécialisés : `PostgresPackStore`, `PostgresPlayableStore`, `PostgresEnrichmentStore`, `PostgresConfusionStore`, `PostgresInspectionStore`
- `storage/services.py` est le point d'orchestration
- Migrations versionnées (`postgres_migrations.py`) avec vérification de version avant initialisation

**Points forts :**
- La gestion du PostGIS search_path dans `_ensure_postgis_schema_in_search_path` est correcte et portable
- La vérification de version de schéma avant initialisation avec l'option `allow_schema_reset` évite les accidents
- Les transactions sont gérées proprement via `contextmanager` — commit/rollback/close explicites

**Points de vigilance :**
1. `PostgresStorageInternal` reste une grande façade avec encore beaucoup de méthodes. La décomposition est engagée (E2 dans l'audit_reference) mais **le fichier postgres.py est encore long** (~600+ lignes) et contient de la logique SQL directe en plus de la délégation. La séparation finale doit être complétée.
2. Le `delete from ... canonical_taxa` en début de `save_canonical_taxa` est un **reset complet** de la table à chaque run. C'est cohérent avec le design du pipeline mais dangereux si exécuté hors contexte d'un run complet. Il n'y a pas de garde-fou explicite contre un appel accidentel en dehors d'un contexte de pipeline.
3. L'absence de pool de connexions (`psycopg.connect()` à chaque `contextmanager`) est correcte pour un pipeline batch mais sera problématique dans un contexte de serving HTTP à charge — le `runtime_read/http_server.py` devra utiliser un pool.

### 3.6 Services owner-side HTTP

**`runtime_read/http_server.py` et `service.py` :**
- `RuntimeReadOwnerService` est un `@dataclass(frozen=True)` minimal et correct
- Il ne fait que déléguer aux stores spécialisés
- `read_playable_corpus` respecte un limit configuré (défaut 1000)
- `find_compiled_pack` et `find_pack_materialization` encapsulent proprement les appels stores

**`editorial_write/http_server.py` et `service.py` :**
- `EditorialWriteOwnerService` encapsule toutes les opérations éditoriales
- Double validation : schéma JSON + contrat envelope à chaque opération
- Enveloppes versionnées (`pack.create.v1`, `pack.diagnose.v1`, etc.)

**Lacune identifiée :**
- Le `runtime_read/http_server.py` ne fait pas encore partie des tests non-intégration de manière directe — la couverture du serveur HTTP owner-side est couverte dans les tests d'intégration du runtime-app (via `owner-http-provider.integration.test.ts`) mais pas dans les tests unitaires database. Une simulation de scénarios d'erreur HTTP en tests unitaires serait utile.

### 3.7 Contrats et schémas

Les schémas JSON dans `schemas/` sont la source de vérité du contrat inter-repos :
- `playable_corpus_v1.schema.json`
- `pack_compiled_v1.schema.json`
- `pack_materialization_v1.schema.json`
- `pack_spec_v1.schema.json`
- `pack_diagnostic_v1.schema.json`
- Schémas d'opérations éditoriales versionnés

**Points forts :**
- Les schémas sont chargés avec `@lru_cache(maxsize=4)` — pas de relecture disque à chaque validation
- Validation avec `FormatChecker` pour les formats standard (datetime, etc.)
- Les erreurs de validation exposent le chemin (`location`) et le message — bon débogage

**Lacune identifiée :**
- Il n'existe pas de test qui vérifie que les schémas Python (`contracts/src/index.ts` côté runtime) sont strictement alignés avec les schémas JSON source. C'est une surface de désynchronisation silencieuse à fort risque. Un test de compatibilité bidirectionnel (ex: valider les exemples TypeScript contre les schémas JSON) devrait exister.

### 3.8 Tests — `database`

**Couverture :**
- 144 tests au total, 71 s'exécutent sans intégration DB (49%), les 73 restants nécessitent PostgreSQL
- Tests de domaine, de qualification, de gouvernance canonique, de CLI, d'enrichissement
- Tests `verify_repo` qui vériffient que la documentation elle-même est cohérente (ex: `test_gate_9_storage_layers_keep_gate_7_markers`) — approche rare et excellente

**Points forts :**
- `test_verify_repo.py` est une idée ingénieuse : des tests qui valident la documentation comme partie du contrat
- Les tests de qualification couvrent des cas spécifiques (exportabilité, politique uncertain, qualité pédagogique, file de review)
- Les tests de modèle de domaine couvrent les validateurs métier

**Lacunes identifiées :**
1. **Ratio intégration/unitaire inversé** : 49% des tests requièrent PostgreSQL. En CI sans DB, 51% seulement des tests tournent. Cela fragilise la boucle de développement locale et la CI rapide.
2. **Absence de tests de mutation** : le moteur de qualification est une surface critique où un bug subtil (ex: mauvais flag → mauvais status) aurait un impact pédagogique direct. Des tests de mutation ou au moins des tests de snapshot auraient de la valeur ici.
3. **`test_inat_harvest.py` est exclu** (dans le `.gitignore` ou nécessite des fixtures réseau) — la couverture du harvest est donc absente en CI standard.
4. **Pas de test de régression sur les schémas JSON** : si un schéma évolue, aucun test ne détecte que les exemples de fixtures sont devenus invalides.

### 3.9 Documentation — `database`

**Exceptionnel pour ce stade.** La documentation est vivante, versionnée et cohérente avec le code :
- `01_domain_model.md` → structure du domaine
- `02_pipeline.md` → toutes les gates documentées avec Gate X clairement référencées
- `05_audit_reference.md` (v8) → état réel, cible, forces, écarts prioritisés, KPI verrouillés
- `06_charte_canonique_v1.md` → constitution de la gouvernance canonique
- `07_canonical_id_migration_v1.md` → règles de migration
- `08_goldset_v1.md` → goldset de validation pédagogique
- `adr/` → décisions architecturales tracées

**Seule lacune :** il n'y a pas de document de "runbook de déploiement" de la surface HTTP owner-side (comment configurer, sécuriser, et monitorer les deux serveurs HTTP owner-side en prod). La section security/auth n'est pas documentée.

---

## 4. Repo `runtime-app` — analyse complète

### 4.1 Architecture monorepo

**Stack :**
- Turborepo + pnpm workspaces
- TypeScript strict sur toutes les surfaces
- Node.js 22.x, ESM (type: module)
- `apps/api` : Fastify 5
- `apps/web` : Next.js (App Router)
- `apps/mobile` : Expo / React Native
- `packages/contracts` : contrats consommateurs
- `packages/shared` : logique client partagée
- `packages/config` : configs ESLint/TSConfig/Prettier partagées

**Jugement :**
La structure monorepo est correcte et proportionnée. Le choix Turborepo est justifié pour la parallélisation des builds. L'utilisation de pnpm workspaces garantit l'intégrité des dépendances inter-packages.

**Points de vigilance :**
- Le fichier `turbo.json` n'est pas lu dans cet audit mais la bonne pratique est de s'assurer que les pipelines `type-check → lint → build` sont correctement ordonnés et que les caches sont invalidés sur les changements de contrats.
- `node_modules` à la racine (pnpm hoisting) : vérifier que les dépendances peer sont bien résolues, notamment pour React Native qui a des exigences strictes.

### 4.2 API backend — `apps/api`

#### `app.ts` — wiring

Le wiring dans `app.ts` est **propre et testable** :
- Injection de dépendances explicite via `BuildServerOptions` (databaseClient, editorialClient, sessionService)
- Fallback en-mémoire pour la session store si `RUNTIME_DATABASE_URL` absent (dev/test only) avec warning explicite au logger
- Le `runtimePool` est proprement fermé dans le hook `onClose` — pas de fuite de connexion
- CORS configuré avec `origin: true` — voir section sécurité

#### Routes — `sessions.ts`

**Points forts :**
- Input sanitization systématique : `parseRequiredId()`, `parseSubmittedAnswer()` avec validation de type, integer check, et trim()
- Les codes d'erreur sont typés (`SubmitAnswerPersistenceErrorCode`) et propagés correctement
- Les métriques sont incrémentées sur tous les chemins (ok, not_found, error, conflict)
- Les logs structurés (objet `{ materializationId, errorCode, requestId }`) sont présents sur les erreurs

**Lacunes identifiées :**
1. **Pas d'authentification** sur aucune route. Toutes les routes sont publiques. C'est un choix volontaire pour le MVP mais doit être documenté comme décision temporaire avec une issue ouverte.
2. **Pas de rate limiting** sur `POST /sessions/...` — une attaque de création massive de sessions est possible sans contrainte.
3. **`readPlayableCorpus()` appelé à chaque GET question et POST answer** : le corpus entier est chargé depuis la DB à chaque appel. À cette échelle, c'est acceptable. Avec 10K items jouables et charge réelle, c'est un goulot d'étranglement immédiat. Un cache applicatif en mémoire avec TTL serait nécessaire.
4. **Body parsing non schématé** : Fastify 5 parse le body en `unknown`, et la validation est faite manuellement dans `parseSubmittedAnswer`. C'est correct mais Fastify supporte la validation de schema JSON intégrée (`schema: { body: { ... } }`) qui est plus performante et plus déclarative.

#### Domain — `session.ts`, `question-serving.ts`, `scoring.ts`

**C'est la zone la mieux écrite du runtime-app.** Les trois modules sont clairs, bien séparés, et respectent la séparation des responsabilités.

- `session.ts` : `StoredSessionService` implémente `SessionService` — abstraction correct, injectable
- `question-serving.ts` : `projectSessionQuestions` est une pure fonction, facilement testable
- `scoring.ts` : `scoreSubmittedAnswer` est une pure fonction de 15 lignes — excellent
- `playable-corpus-index.ts` : `PlayableCorpusIndex` est une Map en mémoire avec O(1) lookup — correct

**Lacune :**
- `scoring.ts` ne valide pas que `question.targetPlayableItemId` est non-vide avant comparaison. Si un `PlayableItem` avait un ID vide (corruption de données), la session serait silencieusement incorrecte.
- `getCurrentSessionQuestion` dans `question-serving.ts` retourne `session.questions[session.currentQuestionIndex] ?? null` — si `currentQuestionIndex` est out-of-bounds, on retourne null silencieusement, ce qui est correct mais mériterait un log d'avertissement.

#### `storage/session-store.ts`

La séparation entre `InMemorySessionStore` et `PostgresSessionStore` est correcte. L'interface `SessionStore` est bien définie.

**Points forts :**
- `submitAnswerAtomically` est une opération atomique en Postgres — c'est la bonne approche pour éviter les race conditions en environnement concurrent
- Les types de lignes DB sont explicitement définis (`RuntimeSessionRow`, etc.)
- `asThreeItemStringTuple` valide le format JSON stocké à la désérialisation

**Lacunes :**
1. **Pas de pool de connexions explicite** dans `PostgresSessionStore` : il dépend d'un `Pool` injecté depuis `createRuntimePostgresPoolFromEnv`. Vérifier que le pool est correctement dimensionné (taille max, timeout) dans les options.
2. **Migration de la DB runtime** : il y a un seul fichier de migration (`0001_runtime_sessions.sql`). Le mécanisme de migration est une séquence linéaire simple — acceptable pour l'instant, mais il faudra un vrai système de migration (ex: Flyway, Liquibase, ou au minimum un script séquentiel numéroté avec vérification de version).

#### Observabilité — `metrics.ts`

**Points forts :**
- Métriques Prometheus correctement structurées en compteurs labelisés
- Échappement des labels (`\\"`) — correct
- Mode provider exposé comme gauge — bonne pratique pour les dashboards

**Lacunes :**
- Les métriques sont **en mémoire uniquement** (pas de persistence entre redémarrages). En prod, il faudra un backend Prometheus réel ou un push gateway.
- Aucune métrique de latence (histogramme). Les compteurs seuls ne permettent pas de détecter des dégradations de performance.
- Le `/metrics` endpoint est **public** — en production, il devrait être derrière un middleware d'authentification interne.

### 4.3 `packages/contracts/src/index.ts`

**Excellent.** Le fichier est annoté avec des règles explicites :
- "Do not add fields absent from source schemas"
- "Do not rename or transform field semantics"
- "If a schema changes, the change must originate in database first"

La structure des types TypeScript est fidèle aux schémas JSON : `PlayableCorpusItemV1`, `PackCompiledV1`, `PackMaterializationV1`, enveloppes éditoriales, etc.

**Point de vigilance identifié :**
`packages/contracts/src/guards.ts` exporte des guards de validation (`isPlayableCorpusV1`, `isPackCompiledV1`, `isPackMaterializationV1`). Ces guards sont utilisés dans `owner-http-provider.ts` pour valider les réponses owner-side. C'est la bonne approche — mais il faudra vérifier que les guards sont générés ou écrits de manière à rester en sync avec les types. Si les guards sont écrits à la main, ils peuvent diverger silencieusement.

### 4.4 `apps/web` — Next.js

**État actuel : surface minimale volontaire, correcte en tant que baseline.**

- `page.tsx` : formulaire de démarrage de session par `materializationId` — fonctionnel mais clairement interne/opérateur
- `components/play-client.tsx` : non lu en détail mais présent
- `lib/api.ts` : client API côté web
- Tests smoke avec Playwright : `player-smoke.spec.ts`, `editorial-smoke.spec.ts`

**Jugement :**
Le web player est actuellement une surface de développement/opérateur, pas un produit. C'est cohérent avec la vision qui positionne le mobile comme la surface joueur principale.

**Point de vigilance :**
- La page d'accueil expose `Materialization ID` directement à l'utilisateur. En production, l'utilisateur ne devrait jamais manipuler cet identifiant technique — il doit choisir un pack et lancer une session, le reste doit être transparent.

### 4.5 `apps/mobile` — Expo / React Native

**État actuel : MVP fonctionnel, flux complet question/réponse/feedback.**

`App.tsx` contient l'intégralité du flux de jeu : démarrage de session, chargement de question, affichage image, sélection de réponse, soumission, feedback de correction, progression vers la question suivante, fin de session.

**Points forts :**
- Gestion des états d'image (`idle/loading/loaded/error`) — correct
- Gestion de la fin de session (`isCompleted`)
- Utilisation de `@runtime-app/shared` pour le client API — bon partage
- Feedback structuré : `whatToLookAt`, `dontConfuseWith` déjà présents dans la réponse API

**Lacunes importantes :**
1. **Tout est dans `App.tsx` (monolithique)** : c'est un anti-pattern React Native classique. La navigation, les écrans, les composants (ImageDisplay, ProgressBar, AnswerOption, FeedbackCard) doivent être extraits. Ce n'est pas un problème fonctionnel aujourd'hui, mais c'est une dette de structure UX qui bloque toute vraie expérience joueur.
2. **Pas de navigation** : il n'y a ni React Navigation ni Expo Router. Il est impossible de naviguer entre un écran d'accueil, un écran de sélection de pack, et un écran de jeu. C'est la lacune UX la plus bloquante pour un lancement.
3. **Pas de gestion des droits/attribution** : `media_attribution` et `media_license` sont dans les DTOs mais ne sont pas affichés dans `App.tsx`.
4. **Pas de mode offline** : aucune logique de cache local (AsyncStorage, etc.). C'est volontairement déprioritisé dans la vision mais à noter.
5. **Accessibilité** : aucune propriété `accessibilityLabel` sur les composants interactifs (`Pressable`, `Image`).

### 4.6 Tests — `runtime-app`

**Tests API (intégration)** :
- 9 fichiers de tests d'intégration dans `apps/api/src/tests/`
- Couvrent : sessions (in-memory + Postgres), runtime-read endpoints, editorial pack flows, contracts, owner-http provider, playable corpus index, observability/errors
- Les tests sont des **programmes exécutables** avec `assert` natif Node (pas de framework de test) — inhabituellement bas-niveau mais fonctionnel

**Points forts :**
- `sessions.integration.test.ts` couvre le flux complet create → get question → submit answer × N → session completed
- `contracts.integration.test.ts` valide les fixtures contre les contrats
- Les tests utilisent le `InMemorySessionStore` pour l'isolation

**Lacunes identifiées :**
1. **Pas de framework de test** (pas de Vitest, Jest, etc.) → pas de runner de test unifié, pas de reporting, pas de parallélisme configuré, pas de coverage. C'est un choix minimaliste mais qui va devenir un frein à mesure que la base de tests grandit.
2. **Pas de tests unitaires** sur les fonctions de domaine (`scoreSubmittedAnswer`, `projectSessionQuestions`, `projectPlayerQuestionResponse`). Ce sont des pure functions facilement testables unitairement.
3. **Pas de tests sur `apps/web`** sauf les smokes Playwright.
4. **Pas de tests sur `apps/mobile`** sauf `App.smoke.test.tsx` (smoke uniquement).

---

## 5. Analyse transversale

### 5.1 Contrat d'interface inter-repos

Le contrat inter-repos est **clairement défini et bien maintenu**. Les 3 surfaces de consommation (`playable_corpus.v1`, `pack.compiled.v1`, `pack.materialization.v1`) sont :
- Définies en JSON Schema côté `database`
- Validées à l'émission (Python, jsonschema)
- Mirrorées en TypeScript côté `runtime-app` (packages/contracts)
- Validées à la réception (guards TypeScript côté provider HTTP)

**Risque résiduel — désynchronisation silencieuse :**
Il n'existe pas de test automatique qui :
1. Prend un exemple de payload `database`
2. Le valide contre le JSON Schema `database`
3. Le valide aussi contre le guard TypeScript `runtime-app`

Si l'un des deux évolue sans l'autre, le système peut diverger silencieusement jusqu'à ce qu'une erreur runtime survienne. Un test de contrat bidirectionnel (Pact, ou un test maison) serait la défense idéale.

### 5.2 Transport HTTP owner-side

Le transport HTTP est actuellement local (127.0.0.1, port 8081). Les timeouts (`DEFAULT_TIMEOUT_MS = 5000`) sont raisonnables pour un usage local mais devront être configurables en prod.

**Lacune de résilience :**
- Pas de retry sur les appels HTTP owner-side côté runtime-app
- Pas de circuit breaker
- Si le serveur database owner-side est temporairement indisponible, toutes les sessions échouent immédiatement

### 5.3 Versioning des contrats

Le versioning est **excellent** : toutes les surfaces ont un numéro de version dans leur payload. La détection de désynchronisation est possible. Mais :
- Il n'y a pas de négociation de version au niveau HTTP (pas de `Accept: application/vnd.playable-corpus.v1+json`)
- Si le `database` passe à `playable_corpus.v2`, le runtime-app ne le saura que par un crash de guard, pas par un code d'erreur HTTP explicite

### 5.4 Enrichissement et boucle de valeur

La boucle enrichissement est **partiellement implémentée** :
- Côté `database` : `EnrichmentRequest`, `EnrichmentRequestTarget`, `enrichment_store`, `enqueue_enrichment_for_pack`
- Côté `runtime-app` : les routes `/editorial/packs/:id/enrich` et `/editorial/enrichments/:id` existent
- **Ce qui manque** : le worker d'exécution asynchrone de l'enrichissement. Les requêtes sont enqueued mais rien ne les exécute automatiquement. C'est documenté dans la vision comme un état intentionnel (enrichissement géré manuellement pour l'instant).

### 5.5 Packs dynamiques vs parties figées

La vision distingue pack (univers dynamique) et partie figée (materialization). L'implémentation est correcte :
- `pack.compiled.v1` : build déterministe depuis les playable_items
- `pack.materialization.v1` : snapshot figé d'un build avec `purpose` (assignment / daily_challenge) et `ttl_hours`

**Ce qui manque pour la vision complète :**
- Logique de sélection adaptative des items (le build est déterministe mais pas adaptatif à l'historique utilisateur)
- Politique de recompilation automatique quand les playable_items évoluent
- Expiration effective des materializations (le `ttl_hours` et `expires_at` sont dans le modèle mais la logique d'expiration n'est pas appliquée côté runtime)

### 5.6 Feedback pédagogique

Le feedback pédagogique de base est en place :
- `what_to_look_at_specific` (depuis les visible_parts qualifiés)
- `what_to_look_at_general` (depuis les key_identification_features canoniques)
- `confusion_hint` (depuis les similar_taxa résolus)
- `feedback_short` (champ présent dans `PlayableCorpusItemV1`)

**Ce qui manque pour la vision complète :**
- `feedback_short` est souvent `null` dans les fixtures — c'est une lacune éditoriale, pas technique
- Le feedback post-réponse est structuré en blocs mais l'UX mobile ne l'affiche pas encore distinctement (tout dans un TextInput flat)
- L'IA post-réponse (explication enrichie pour premium) n'est pas encore intégrée côté runtime

---

## 6. Cohérence vision ↔ implémentation

### Ce qui est conforme à la vision

| Principe vision | Implémentation |
|---|---|
| Référentiel canonique interne souverain | ✅ Entièrement en place, IDs immuables, mappings externes séparés |
| Runtime consomme corpus jouable dérivé, pas le brut | ✅ Strictement respecté |
| Packs comme objets éditoriaux versionnés | ✅ pack.spec.v1, revisions, compiled, materialization |
| Pipeline reproductible et versionné | ✅ 13 gates, artefacts versionnés |
| Qualité pédagogique explicite | ✅ 4 stages de qualification, signaux pedagogy/confusion/diagnostic |
| Traçabilité source/licence | ✅ ProvenanceSummary complet sur chaque resource |
| Mobile prioritaire | ✅ Expo/React Native en place |
| Documentation-first | ✅ Documentation exceptionnelle |
| Séparation database/runtime | ✅ Frontière bien tenue |
| Multilingue (fr/en/nl) | ✅ Présent dans le modèle, couverture éditoriale partielle |
| Enrichissement piloté par les packs | ✅ Modèle en place, worker absent |

### Ce qui n'est pas encore implémenté (volontairement ou non)

| Vision | État | Nature |
|---|---|---|
| Moteur adaptatif (historique utilisateur) | ❌ Absent | Architecture non posée |
| Progression utilisateur | ❌ Absent | Volontaire MVP |
| Gamification (streaks, badges, collection) | ❌ Absent | Volontaire MVP |
| Institutionnel (classes, assignations, reporting) | ❌ Absent | Volontaire MVP |
| Audio | ❌ Absent | Volontaire déprioritisé |
| Offline (pack download) | ❌ Absent | Volontaire déprioritisé |
| Multi-taxon (au-delà des oiseaux) | ❌ Birds-only | Volontaire phase 1 |
| Multi-source (GBIF, Wikimedia) | ❌ iNaturalist-only | Volontaire phase 1 |
| Partage de packs | ❌ Absent | Volontaire déprioritisé |
| Authentification utilisateur | ❌ Absente | Non commencée |
| Worker d'enrichissement asynchrone | ❌ Absent | Architecture partiellement posée |
| Pack non compilable → blocage + enrichissement automatique | ❌ Manuel | Architecture posée |
| Expiration materializations (TTL) | ⚠️ Modèle ok, logique absente | Partiel |
| UX de jeu complète (navigation, écrans) | ⚠️ Monolithique App.tsx | Partiel |

### Tension vision / implémentation la plus notable

La vision décrit un **moteur de quiz adaptatif** piloté par l'historique d'usage, les signaux pédagogiques, et les performances de l'utilisateur. L'implémentation actuelle sert les questions d'un pack compilé **déterministement**, sans aucune adaptation à l'histoire de l'utilisateur. C'est un écart fondamental entre la promesse produit et la réalité technique, qui n'est ni documenté comme un écart, ni comme une décision ADR temporaire.

Il faudra une décision architecturale explicite sur où vit l'adaptation : dans le `database` (modification de la compilation), dans le `runtime-app` (logique de serving adaptative), ou dans un service tiers (moteur de répétition espacée). Cet écart est aujourd'hui le plus large entre la vision et l'implémentation.

---

## 7. Sécurité

### 7.1 `database` repo

**Positif :**
- `security/redaction.py` masque correctement le mot de passe dans les URLs de connexion
- Les IDs canoniques sont validés par regex (`CANONICAL_TAXON_ID_PATTERN`) — pas d'injection via les IDs
- Les modèles Pydantic avec `extra="forbid"` rejettent tout champ non attendu — protection contre les surcharges de payload
- Pas de concaténation directe de chaînes SQL — psycopg avec paramètres (`%s`) protège contre l'injection SQL

**Lacunes :**
1. **URL source des médias non validée** : `MediaAsset.source_url` est stockée sans validation de schéma (`https://` uniquement). Une URL `file://`, `javascript:`, ou `data:` pourrait être injectée depuis iNaturalist si les données sources sont corrompues.
2. **Pas d'authentification sur les serveurs HTTP owner-side** : les routes `/playable-corpus`, `/packs/...`, `/editorial/...` sont publiquement accessibles sur le port configuré. En déploiement local c'est acceptable, mais en déploiement réseau même interne, il faut un mécanisme d'authentification (token API ou réseau privé strict).
3. **`allow_schema_reset=True`** dans le runner de pipeline : cette option permet de vider et recréer le schéma DB. Si exposée via une route (même non intentionnelle), c'est une surface de destruction. Elle est actuellement dans le code Python mais doit rester derrière une vérification explicite de contexte (ex: env == "local_dev" uniquement).
4. **Injection GEMINI_API_KEY** : la clé API Gemini est lue depuis l'environnement ou passée en paramètre. Si loggée accidentellement (ex: dans un traceback), elle serait exposée. Il faut s'assurer que la clé n'est jamais loggée.

### 7.2 `runtime-app` repo

**Positif :**
- `parseRequiredId()` et `parseSubmittedAnswer()` font du sanitization explicite
- `encodeURIComponent()` utilisé sur les paramètres d'URL dans `owner-http-provider.ts` — protection contre l'injection de path
- Les erreurs d'API retournent des messages structurés sans exposer d'informations internes (pas de stacktraces dans les réponses)
- Fastify rejette les payloads malformés avant d'atteindre le code applicatif

**Lacunes :**
1. **CORS `origin: true`** : autorise toutes les origines. En production, il faut une whitelist explicite des origines autorisées.
2. **Pas d'authentification** : toutes les routes API sont publiques. La création de sessions, la lecture du corpus jouable, et toutes les opérations éditoriales sont non protégées. C'est un risque critique dès que l'API est exposée au-delà du réseau local.
3. **Pas de rate limiting** : `POST /sessions/materializations/:id` est vulnerable à une création massive de sessions vides.
4. **`/metrics` public** : l'endpoint Prometheus expose des informations sur le comportement interne du système. Il doit être protégé ou restreint au réseau interne.
5. **Session ID généré par `randomUUID()`** : c'est correct cryptographiquement. Les IDs de session ne sont pas prédictibles.
6. **Pas de headers de sécurité HTTP** : pas de `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options` sur l'API. Fastify supporte `@fastify/helmet` pour ça.

### 7.3 Résumé sécurité

Aucune faille critique évidente pour un système local/internal dev. Les risques principaux concernent le déploiement réseau (auth, CORS, rate limiting) et seront à adresser avant tout déploiement public, même bêta.

---

## 8. Dettes techniques et risques

### 8.1 Dettes confirmées (non critiques, documentées)

| Dette | Repo | Priorité | Commentaire |
|---|---|---|---|
| `PostgresStorageInternal` encore grande façade | database | P1 | Décomposition engagée, à finaliser |
| `readPlayableCorpus()` appelé à chaque request | runtime-app | P1 | Cache TTL nécessaire |
| `App.tsx` monolithique | runtime-app/mobile | P0 produit | Bloque l'expérience utilisateur |
| Pas de navigation mobile | runtime-app/mobile | P0 produit | Bloque le vrai flow UX |
| Pas d'authentification | runtime-app | P0 sécurité préprod | Avant tout déploiement |
| Pas de framework de test runtime | runtime-app | P1 | Frein à mesure que la base grandit |
| Tests intégration DB : 51% du total | database | P1 | Ralentit la boucle dev |
| Contrat bidirectionnel non testé | cross-repo | P1 | Risque de désynchronisation silencieuse |

### 8.2 Risques produit

| Risque | Impact | Probabilité | Mitigation |
|---|---|---|---|
| Désynchronisation schémas database/runtime | Crash runtime, expérience cassée | Moyenne | Test de contrat bidirectionnel |
| Corpus jouable trop petit pour packs non-triviaux | Quiz répétitif, expérience pauvre | Haute (actuel ~15 taxons pilotes) | Pipeline harvest + enrichissement |
| Mono-source iNaturalist | Dépendance forte, risque API changes | Haute | Plan multi-source documenté |
| Moteur adaptatif absent | Promesse produit non tenue | Haute | ADR + décision architecturale urgente |
| Données multilingues partielles | Expérience dégradée pour NL/EN | Moyenne | Pipeline éditorial |
| Owner-side HTTP sans auth | Exposition en déploiement réseau | Haute | Token API ou réseau privé |

### 8.3 Risques techniques

| Risque | Impact | Probabilité | Mitigation |
|---|---|---|---|
| `readPlayableCorpus()` à chaque requête | Latence, surcharge DB | Haute à scale | Cache mémoire TTL |
| Pas de retry ni circuit breaker sur HTTP owner-side | Indisponibilité cascade | Moyenne | Retry + backoff + fallback |
| Expiration materializations non appliquée | Sessions sur données périmées | Basse à court terme | Logique d'expiration côté runtime |
| Pipeline reset_materialized_state sans contexte | Perte de données accidentelle | Basse | Guard contextuel strict |

---

## 9. Recommandations prioritaires

### Priorité 0 — Avant tout déploiement public ou bêta

1. **Authentification API** : implémenter un mécanisme d'authentification (token Bearer statique minimum) sur toutes les routes API, en commençant par les routes éditoriales et sessions.
2. **CORS restreint** : passer de `origin: true` à une whitelist explicite des origines autorisées.
3. **Navigation mobile** : intégrer Expo Router ou React Navigation dans `apps/mobile`, extraire les écrans de `App.tsx`.
4. **Cache `playableCorpus`** : implémenter un cache in-process avec TTL de quelques minutes pour éviter le chargement répété depuis la DB owner-side.

### Priorité 1 — Avant un usage institutionnel

5. **ADR sur le moteur adaptatif** : décider explicitement où vit la logique adaptative (database side, runtime side, service séparé) et documenter cette décision architecturale. C'est l'écart le plus structurant entre la vision et l'implémentation.
6. **Test de contrat bidirectionnel** : créer un test qui valide un payload database contre les guards TypeScript du runtime-app et vice versa.
7. **Rate limiting** : ajouter `@fastify/rate-limit` sur les routes sensibles (création de session).
8. **Framework de test runtime** : migrer vers Vitest ou Jest pour avoir un runner unifié, le coverage, et des tests unitaires sur les pure functions de domaine.
9. **Worker d'enrichissement** : implémenter le worker asynchrone qui traite la queue `enrichment_requests`. C'est la boucle de valeur la plus stratégique.

### Priorité 2 — Vers la qualité production

10. **Headers de sécurité HTTP** : ajouter `@fastify/helmet` sur l'API.
11. **Métriques de latence** : ajouter des histogrammes Prometheus pour la latence des requêtes owner-side et des réponses API.
12. **Validation URL source_url** : valider que `MediaAsset.source_url` est un HTTPS URL valide à l'ingestion.
13. **Authentification des serveurs HTTP owner-side** : token API ou réseau privé strict avant tout déploiement non-local.
14. **Runbook de déploiement** : documenter comment déployer, configurer, et monitorer les deux serveurs HTTP owner-side (`runtime_read` + `editorial_write`).

### Priorité 3 — Enrichissement produit

15. **Expiration des materializations** : implémenter la logique de vérification du `expires_at` côté runtime avant de servir une session.
16. **Attribution et droits dans l'UI** : afficher `media_attribution` et `media_license` dans l'app mobile, au moins post-réponse.
17. **Feedback riche** : connecter `feedback_short` dans le flow mobile (il est dans le DTO mais affiché de façon rudimentaire).
18. **Couverture éditoriale multilingue** : pipeline éditorial pour enrichir `key_identification_features_by_language` et `feedback_short` sur les taxons pilotes.

---

## 10. Verdict final

### Ce qui est vraiment fort

1. **Le noyau canonique** est une fondation scientifique rare à ce stade. La gouvernance, la traçabilité, l'immuabilité des IDs, la gestion des transitions taxonomiques — c'est du niveau d'un produit mature.

2. **La séparation database / runtime** est correctement posée et tenue. Le contrat inter-repos est explicite, versionné, et validé des deux côtés. C'est une décision architecturale difficile que beaucoup de projets ratent.

3. **La qualification pédagogique** est explicite, multi-dimensionnelle, et tracée. Les signaux `difficulty_level`, `media_role`, `confusion_relevance`, `diagnostic_feature_visibility`, `learning_suitability` sont directement utiles pour la pédagogie différenciée — et ils sont présents dans les DTOs de serving.

4. **La documentation** est exceptionnelle. `AGENTS.md`, `05_audit_reference.md`, `02_pipeline.md`, les ADRs — c'est le niveau d'un produit qui a décidé de construire sur des fondations solides plutôt que de prototyper à tout prix.

5. **Le domaine Python** (`models.py`, `enums.py`, `canonical_governance.py`) est du code professionnel. La rigueur des validateurs Pydantic encode la logique métier dans le code lui-même.

6. **La discipline de séparation des rôles** dans le runtime-app (`scoring.ts` = 15 lignes, `question-serving.ts` = pure function, `session.ts` = service injectable) montre une maîtrise des principes de design.

### Ce qui est encore fragile

1. **L'expérience utilisateur mobile** est à l'état de prototype interne. `App.tsx` monolithique sans navigation. Pour un produit qui se positionne comme "mobile-first", c'est la lacune la plus visible.

2. **L'adaptivité est absente**. Le moteur de quiz "adaptatif" de la vision n'a aucune fondation dans le code actuel. C'est une promesse produit sans implémentation, sans même une décision architecturale documentée.

3. **La sécurité est en mode dev/local**. Zéro authentification, CORS ouvert, metrics publiques. C'est acceptable aujourd'hui et dangereux demain.

4. **Le corpus est minimal** (15 taxons pilotes, ~birds-only, iNaturalist uniquement). La valeur pédagogique du produit est directement proportionnelle à la richesse du corpus. C'est le plus grand risque produit à court terme.

5. **Les tests du runtime-app sont artisanaux**. Pas de framework, pas de tests unitaires sur les fonctions de domaine, pas de coverage. Correct pour un MVP, limitant pour la suite.

### Formule de conclusion

Ce projet a fait les bons choix difficiles tôt : séparation des responsabilités, canonique souverain, qualification explicite, documentation vivante. Ces choix paient maintenant en clarté architecturale et en capacité à raisonner proprement sur l'évolution.

Les lacunes actuelles (UX mobile, adaptivité, sécurité, corpus) ne sont pas des erreurs de conception — ce sont des niveaux de priorité cohérents avec un MVP technique d'abord. Elles deviennent critiques dès qu'un premier utilisateur réel (étudiant UCLouvain, enseignant) entre dans le système.

Le projet est prêt pour un beta institutionnel fermé à la condition que les priorités 0 soient adressées (auth + navigation mobile + cache corpus). Il n'est pas encore prêt pour un lancement public.

**La fondation est saine. Le produit reste à construire au-dessus.**

---

*Audit réalisé sur la base d'une analyse complète des repos `database` (Python/PostgreSQL, ~150 fichiers source) et `runtime-app` (TypeScript/Node.js/React Native/Next.js, ~40 fichiers source) en date du 19 avril 2026.*
