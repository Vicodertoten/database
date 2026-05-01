---
owner: database
status: stable
last_reviewed: 2026-04-29
source_of_truth: docs/runbooks/execution-plan.md
scope: runbook
---

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

## 1.1 Cadrage court terme verrouille (v0.1)

Source de verite: `docs/runbooks/v0.1-scope.md`.

Roadmap complementaire de robustification ingestion avant montee en volume:
`docs/runbooks/pre-scale-ingestion-roadmap.md`.

Perimetre operationnel court terme:

- oiseaux uniquement
- Belgique uniquement
- images uniquement
- modes QCM + reponse directe simple
- corpus interne issu d'ingestion iNaturalist
- aucune boucle de jeu runtime avec appel live iNaturalist
- volume cible: 50 especes / 1 000 images qualifiees

Ce cadrage court terme ne modifie pas les gates historiques 0 a 9,
ni la frontiere owner/runtime deja verrouillee.

## 2. Fichiers a lire avant modification

Codex doit lire au minimum:

- `README.md`
- `docs/README.md`
- `docs/foundation/scope.md`
- `docs/foundation/domain-model.md`
- `docs/foundation/pipeline.md`
- `docs/runbooks/open-questions.md`
- `docs/runbooks/audit-reference.md`
- `docs/foundation/canonical-charter-v1.md`
- `docs/runbooks/program-kpis.md`
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
- Gate 5: politique distracteurs v3
- Gate 6: queue d'enrichissement
- Gate 7: confusions batch + agregats globaux
- Gate 8: inspection/KPI/smoke/CI
- Gate 9: retrait sidecar export v3

Ce repo n'est pas a refondre abstraitement.
Il doit etre consolide a partir de son etat reel.

Markers de traçabilite (compatibilite verification):

- Gate 4.5 - Correctif strategique pre-extension
- Gate 5 - Politique distracteurs v3
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

Le prochain chantier structurant planifie est Phase 3 taxon-based question options.
Il est documente dans:

- `docs/foundation/adr/0006-taxon-based-question-options.md`
- `docs/runbooks/phase3-distractor-strategy.md`

Ce chantier est database-first et contract-first:

- verrouiller doctrine et invariants avant code lourd
- creer `pack.compiled.v2` et `pack.materialization.v2`
- conserver v1 en compatibilite
- ne pas commencer l'adaptation `runtime-app` avant production owner-side v2

Si un nouveau chantier structurant est ouvert, il doit appartenir a l'un des axes suivants:

1. consolidation operatoire du playable cumulatif incremental implemente
2. consolidation finale de l'extraction de responsabilites hors `PostgresRepository`
3. options de question taxon-based et distracteurs hors pack gouvernes
4. qualite editoriale et multilingue des surfaces pedagogiques
5. extension multi-source ou multi-taxa seulement apres 1 et 2

Tout autre chantier doit etre considere comme secondaire ou hors-sequence.

Ordre de consolidation recommande:

1. maintenir la stabilite du modele playable deja migre
2. poursuivre la simplification de la facade `PostgresRepository` sur base des extractions deja en place

Critere de maintien de la phase transitoire:

- pas de retour a une reconstruction latest-only du serving playable
- causes d'invalidation conservees explicites et testees
- `playable_corpus.v1` reste stable pour les consommateurs
- `pack.compiled.v1` et `pack.materialization.v1` restent disponibles pendant l'introduction de v2

Etat d'avancement constate (2026-04-09):

- schema `database.schema.v16` actif pour le lifecycle playable incremental
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
- extension additive runtime-read `playable_corpus.v1` (phase 3 minimal player-ready):
  - `taxon_label`
  - `feedback_short`
  - `media_render_url`
  - `media_attribution`
  - `media_license`
- non-regression: tests gate dedies + suites structurantes + `verify_repo` verts

## 6. Discipline d'execution

1. Un seul chantier structurant actif a la fois.
2. Pas de logique runtime/session/scoring/progression dans `database`.
3. Ne pas tordre `export.bundle.v4` pour des besoins runtime.
4. Toute evolution structurante met a jour `README.md`, `docs/runbooks/audit-reference.md`, et ce document.
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

## 9. Roadmap detaillee en 8 phases (ordre d'implementation recommande)

Objectif de cette roadmap:

- fournir un plan de travail dev concret et sequentiel
- maximiser la valeur pedagogique sans casser la separation data/runtime
- reduire le risque de rework par un ordre de livraison strict

Regle de pilotage:

- une phase active a la fois
- pas de phase suivante tant que les criteres de sortie de la phase courante ne sont pas atteints

### 9.1 Vue d'ensemble

| Phase | Intitule | Pourquoi maintenant |
|---|---|---|
| 1 | Instrumentation et baseline KPI | mesurer avant de modifier |
| 2 | Pre-filtrage image amont (cout) | reduire le gaspillage IA le plus tot |
| 3 | Remediation data taxons deficitaires | augmenter la couverture utile |
| 4 | Localisation robuste PostGIS | fiabiliser geo-filtres et reporting |
| 5 | Distracteurs v3 confusion-aware | augmenter la qualite pedagogique quiz |
| 6 | Multilingue + nomenclature scientifique | stabiliser la qualite linguistique |
| 7 | Multi-taxon readiness | preparer extension sans dette critique |
| 8 | Hardening operatoire et gouvernance | verrouiller exploitation long terme |

### 9.2 Phase 1 - Instrumentation et baseline KPI

Scope:

- etendre le smoke report avec KPI pedagogiques et couverture
- rendre les deficits compile visibles et comparables run-over-run

Fichiers cibles:

- `src/database_core/ops/smoke_report.py`
- `src/database_core/storage/postgres.py`
- `docs/runbooks/program-kpis.md`
- tests smoke/inspect associes

Backlog technique:

1. ajouter KPI `taxon_playable_coverage_ratio`
2. ajouter KPI `taxon_with_min2_media_ratio`
3. ajouter KPI `country_code_completeness_ratio`
4. ajouter KPI `distractor_diversity_index` (premiere version simple)
5. exposer un resume deficits packs (raison + taxons bloquants)

Criteres d'acceptation:

- smoke report versionne sans rupture de contrat existant
- nouveaux KPI calcules sur 3 runs consecutifs
- tests non-regression verts

Definition of done:

- doc KPI mise a jour
- commande smoke standard conservee
- `overall_pass` documente avec distinction KPI verrouilles vs KPI etendus non bloquants (phase 1)

### 9.3 Phase 2 - Pre-filtrage image amont (reduction cout)

Scope:

- rejeter ou deferer avant IA les images techniquement non exploitables

Fichiers cibles:

- `src/database_core/adapters/inaturalist_harvest.py`
- `src/database_core/adapters/inaturalist_snapshot.py`
- `src/database_core/qualification/ai.py`
- tests qualification/harvest

Backlog technique:

1. hard gate dimensions minimales avant qualification IA
2. detecter corruption decode image
3. ajouter heuristique blur simple
4. dedupliquer media evidemment dupliques (hash perceptuel si possible)
5. tracer `pre_ai_rejection_reason`

Criteres d'acceptation:

- hard gates (obligatoires):
  - compatibilite contractuelle conservee (changement additif uniquement)
  - non-regression qualite/sortie (`overall_pass` verrouille et exportable stable)
  - tracabilite pre-IA exploitable (`pre_ai_rejection_reason` + distribution smoke)
- impact cout (objectif de pilotage, non bloquant si hard gates passes):
  - baisse du volume d'appels IA non utiles
  - cout IA par exportable en baisse

Regle de decision Phase 2:

- `GO`: hard gates passes + impact cout confirme
- `GO_WITH_GAPS`: hard gates passes + impact cout non confirme sur corpus courant
- `NO_GO`: hard gate casse

Definition of done:

- metriques cout publiees dans smoke
- rejets pre-IA auditables
- tests de seuils amont ajoutes

### 9.4 Phase 3 - Remediation data taxons deficitaires

Scope:

- augmenter taxa served et taxons >= 2 medias jouables

Fichiers cibles:

- `src/database_core/adapters/inaturalist_harvest.py`
- `src/database_core/storage/pack_store.py`
- `src/database_core/storage/enrichment_store.py`
- scripts ops associes

Backlog technique:

1. detecter automatiquement taxons deficitaires via diagnostics pack
2. lancer fetch cible multi-pass pour taxons deficitaires
3. augmenter `per_page` uniquement pour taxons deficitaires
4. definir un run remediation dedie, idempotent
5. persister le resultat remediation et son impact KPI

Criteres d'acceptation:

- hausse mesurable de `taxon_with_min2_media_ratio`
- reduction des echec compile pour cause `insufficient_media_per_taxon`

Definition of done:

- playbook remediation taxons documente
- historique remediation consultable
- tests integration sur scenario deficitaires verts

### 9.5 Phase 4 - Localisation robuste avec PostGIS

Scope:

- fiabiliser `country_code` et filtres geo sans couplage runtime

Fichiers cibles:

- `src/database_core/storage/postgres_schema.py`
- `src/database_core/storage/playable_store.py`
- `src/database_core/pipeline/runner.py`
- migrations SQL associees

Backlog technique:

1. definir une strategie d'enrichissement `country_code` depuis `location_point`
2. maintenir trace source vs enrichi (provenance geo)
3. priorite de verite: point -> country_code enrichi -> texte libre
4. exposer KPI de completude geo
5. verifier impact sur filtres pack geo

Criteres d'acceptation:

- hausse significative du taux `country_code` non null
- aucune regression des requetes geo existantes

Definition of done:

- migration schema appliquee et testee
- inspect geo coherent
- documentation runbook maj

### 9.6 Phase 5 - Distracteurs v3 confusion-aware

Scope:

- remplacer la priorisation deterministic-only par une priorisation pedagogique

Fichiers cibles:

- `src/database_core/storage/pack_store.py`
- `src/database_core/storage/confusion_store.py`
- `src/database_core/domain/models.py` (si score explicite persiste)
- tests pack/qualification

Backlog technique:

1. definir un score distracteur composite (confusion + similarite + difficulte)
2. ajouter penalite de repetition intra-pack
3. ajouter contrainte de diversite inter-questions
4. conserver deterministic reproducibility (meme entree -> meme build)
5. exposer metriques de diversite distracteurs

Criteres d'acceptation:

- baisse repetition distracteurs
- hausse indice de diversite
- aucune violation des invariants compile (3 distracteurs distincts)

Definition of done:

- tests property/integration distracteurs v3
- diagnostic pack enrichi avec metriques pedagogiques
- doc domain model maj

### 9.7 Phase 6 - Multilingue + nom scientifique (qualite editoriale)

Scope:

- renforcer la qualite et la completude FR/EN/NL tout en preservant l'identite canonique

Fichiers cibles:

- `src/database_core/enrichment/*`
- `src/database_core/pipeline/runner.py`
- `schemas/playable_corpus_v1.schema.json` (si extension additive necessaire)
- tests multilingue

Backlog technique:

1. durcir pipeline de merge des noms multilingues
2. introduire score de qualite lexicale par langue
3. renforcer fallback deterministic (langue cible -> en -> scientifique)
4. ajouter KPI de completude multilingue
5. preparer queue d'enrichissement linguistique ciblee

Criteres d'acceptation:

- completude FR/EN/NL amelioree
- aucune rupture sur `accepted_scientific_name`

Definition of done:

- tests non-regression multilingue verts
- doc surfaces runtime mise a jour si champ ajoute
- provenance linguistique tracee

### 9.8 Phase 7 - Multi-taxon readiness (beyond birds)

Scope:

- rendre qualification et enrichissement parametrables par `taxon_group`

Fichiers cibles:

- `src/database_core/domain/enums.py`
- `src/database_core/qualification/policy.py`
- `src/database_core/qualification/engine.py`
- `src/database_core/pipeline/runner.py`
- seeds/tests dedies

Backlog technique:

1. separer policies de qualification par groupe taxonomique
2. separer prompts/modeles par groupe quand necessaire
3. introduire fixtures de verification pour un second groupe
4. valider compatibilite canonique et contracts export/playable
5. ajouter KPI couverture multi-taxon

Criteres d'acceptation:

- second groupe taxonomique passe pipeline nominale
- pas de regression birds

Definition of done:

- tests cross-group verts
- doctrine scope mise a jour (`docs/foundation/scope.md`)
- runbook smoke adapte au multi-groupe

### 9.9 Phase 8 - Hardening operatoire et gouvernance long terme

Scope:

- fiabiliser exploitation en conditions pilote/institutionnelles

Fichiers cibles:

- `docs/runbooks/smoke-runbook.md`
- `docs/runbooks/program-kpis.md`
- `docs/runbooks/inter-repo/phase6-pilot-runbook.md`
- CI/tests de verification

Backlog technique:

1. formaliser SLO/SLA pipeline (latence run, taux echec, delai remediation)
2. classifier incidents data/qualification/storage/owner-services
3. verrouiller checklist Go/No-Go institutionnelle
4. renforcer politique anti-secret dans artefacts
5. mettre en place revue mensuelle KPI + debt board

Criteres d'acceptation:

- runbook incident et go/no-go executes en dry-run complet
- criteres de promotion explicites et versionnes

Definition of done:

- documentation operations synchronisee
- evidence dry-run archivee
- revues periodiques planifiees

### 9.10 Dependances inter-phases (obligatoires)

| From | To | Dependance |
|---|---|---|
| 1 | 2 | baseline cout/qualite necessaire pour mesurer gain pre-filtrage |
| 2 | 3 | reduction bruit qualification avant remediation taxons |
| 1 | 4 | KPI geo de reference avant enrichissement PostGIS |
| 3 + 4 | 5 | distracteurs v3 plus utiles avec meilleure couverture + geo fiable |
| 5 | 6 | qualite pedagogique quiz stabilisee avant extension linguistique avancee |
| 6 | 7 | fondations linguistiques/canoniques stables avant multi-groupe |
| 7 | 8 | hardening final sur architecture deja elargie |

### 9.11 Cadence de livraison recommandee

- sprint 1: phase 1
- sprint 2: phase 2
- sprint 3: phase 3
- sprint 4: phase 4
- sprint 5: phase 5
- sprint 6: phase 6
- sprint 7-8: phase 7
- sprint 9: phase 8

### 9.12 KPI de pilotage global roadmap

KPI de resultat:

- augmentation `exportable_resources`
- augmentation `taxa_served` et `taxons >=2 medias`
- reduction repetition distracteurs
- augmentation completude `country_code`
- augmentation completude FR/EN/NL

KPI de cout:

- baisse `estimated_ai_cost_eur / exportable_resource`

KPI de robustesse:

- stabilite `overall_pass`
- baisse incidents operationnels

### 9.13 Contraintes non negociables a conserver pendant toute la roadmap

1. separation stricte data knowledge vs runtime/session/scoring
2. pas de detournement de `export.bundle.v4` en surface runtime
3. contrats versionnes, migrations explicites, tests systematiques
4. aucune rupture non documentee des surfaces `playable_corpus.v1`, `pack.compiled.v1`, `pack.materialization.v1`
5. aucune adaptation runtime v2 avant production owner-side de `pack.materialization.v2`
6. aucun taxon reference-only ne devient automatiquement active/playable/fully qualified

### 9.14 Alignement strategique (audit produit) a appliquer immediatement

Positionnement cible:

- ne pas chercher a battre iNaturalist sur le volume brut
- chercher a surpasser le serving pedagogique via la chaine:
  `requete pedagogique -> corpus jouable fiable -> distracteurs pertinents -> experience quiz stable`

Doctrine operationnelle:

1. iNaturalist est une source d'acquisition, pas une surface runtime
2. runtime consomme uniquement les surfaces versionnees du repo
3. acquisition et compilation restent separees (pas d'appel externe en compile)

### 9.15 Phases strategiques additionnelles (necessaires)

Ces phases completent la roadmap 8 phases sans invalider l'ordre existant.

#### Phase 0 - Segment cible et benchmark prototype

But:

- gagner clairement sur un segment etroit avant toute extension (ex: oiseaux Belgique/Europe)

Scope:

1. definir un perimetre pilote strict (zone, saison, niveau)
2. fixer des objectifs comparatifs vs prototype sur ce segment
3. valider que la boucle compile/materialize est meilleure ou equivalente en experience

Livrables:

- dossier benchmark segment cible
- baseline KPI segment (compilation, diversite, latence)

Criteres de sortie:

- experience quiz au moins equivalente au prototype sur segment cible

Note doctrine (2026-04-22):

- le resultat `NO_GO` de la comparaison stricte prototype reste conserve tel quel dans les artefacts P0
- la promotion P0 -> P1 est evaluee avec un gate doctrine explicite:
  - hard gates de stabilite/reproductibilite/contrats
  - KPI comparatifs prototype suivis en gaps prioritaires de Phase 1
  - statut de decision: `GO`, `GO_WITH_GAPS`, `NO_GO`

Regle de promotion P0 -> P1 (version active):

Hard gates (bloquants):

1. `compile_success_ratio_segment == 1.0` sur les 3 runs retenus
2. `overall_pass == true` sur les 3 runs retenus
3. 3 runs strictement comparables (segment/snapshot/formules/commandes/difficulty policy)
4. contrats runtime owner inchanges et smoke nominal vert
5. latence consumer: aucun run `p95 > 1500ms`

KPI etendus (non bloquants a l'entree P1, obligatoires a corriger en P1):

1. `owner_distractor_diversity_vs_prototype`
2. `consumer_latency_vs_prototype`

Statuts de decision:

1. `GO`: hard gates passes + KPI etendus dans la cible
2. `GO_WITH_GAPS`: hard gates passes + au moins un KPI etendu hors cible non bloquante
3. `NO_GO`: hard gate casse ou seuil bloquant depasse

Budget latence P1 (consumer `latency_e2e_segment_p95`):

1. vert: `p95 <= 900ms`
2. ambre: `900ms < p95 <= 1500ms` (tolere avec gap ouvert)
3. rouge: `p95 > 1500ms` (bloquant)
4. stabilite: au plus 1 run sur 3 au-dessus de `900ms`, aucun run au-dessus de `1500ms`

Objectifs distractor diversity P1:

1. amelioration obligatoire vs baseline P0
2. plancher minimal de sortie P1: `0.15`
3. cible recommandee de sortie P1: `0.25`
4. non bloquant pour l'entree en P1, gap prioritaire de pilotage

#### Phase 3bis - Query-to-pack loop et coverage contracts

But:

- rendre la creation de packs pilotee par la couverture reelle au lieu d'etre aveugle

Scope:

1. introduire un contrat `coverage.query.v1` (filtre pedagogique)
2. introduire un contrat `pack.coverage.v1` (reponse diagnostique exploitable)
3. implementer la boucle:
   - query utilisateur
   - diagnostic couverture locale
   - compile si seuil atteint
   - sinon enqueue remediation/acquisition ciblee

Fichiers cibles:

- `schemas/coverage_query_v1.schema.json` (nouveau)
- `schemas/pack_coverage_v1.schema.json` (nouveau)
- `src/database_core/storage/pack_store.py`
- `src/database_core/storage/services.py`
- `docs/foundation/domain-model.md`
- `docs/foundation/pipeline.md`

Criteres d'acceptation:

- toute demande pack peut etre expliquee par un diagnostic coverage stable
- echec compile accompagne d'une remediation proposee (raison explicite)

### 9.16 Clarification des objets pack (obligatoire)

Le plan doit distinguer explicitement 4 objets differents:

1. `PackIntent` / `PackQuery`: besoin utilisateur (pedagogique + filtres)
2. `PackSpec`: spec versionnee persistee
3. `PackCompiledBuild`: build dynamique depuis corpus courant
4. `PackMaterialization`: snapshot fige servable

Regle:

- ne pas confondre intention utilisateur et objet materialise
- toute transition d'objet doit etre traçable et rejouable

### 9.17 Extensions KPI prioritaires a verrouiller

En plus des KPI deja listes, ajouter prioritairement:

1. `coverage_compile_success_ratio` (query -> compile)
2. `coverage_remediation_resolution_time_hours`
3. `distractor_plausibility_ratio`
4. `intra_pack_distractor_entropy`
5. `inter_session_repetition_rate`
6. `seasonal_coverage_ratio`

Ces KPI restent dans le perimetre data/serving (pas de logique runtime/session).

### 9.18 Dependances mises a jour (avec phases additionnelles)

| From | To | Dependance |
|---|---|---|
| 0 | 1 | baseline segment cible avant extension KPI |
| 1 | 2 | baseline cout/qualite necessaire pour mesurer gain pre-filtrage |
| 2 | 3 | reduction bruit qualification avant remediation taxons |
| 3 | 3bis | remediation minimale necessaire pour diagnostic query-to-pack utile |
| 1 | 4 | KPI geo de reference avant enrichissement PostGIS |
| 3bis + 4 | 5 | distracteurs v3 plus utiles avec coverage pilotee + geo fiable |
| 5 | 6 | qualite pedagogique quiz stabilisee avant extension linguistique avancee |
| 6 | 7 | fondations linguistiques/canoniques stables avant multi-groupe |
| 7 | 8 | hardening final sur architecture deja elargie |

### 9.19 Cadence recommandee (mise a jour)

- sprint 0: phase 0
- sprint 1: phase 1
- sprint 2: phase 2
- sprint 3: phase 3
- sprint 4: phase 3bis
- sprint 5: phase 4
- sprint 6: phase 5
- sprint 7: phase 6
- sprint 8-9: phase 7
- sprint 10: phase 8

### 9.20 Anti-patterns a eviter explicitement

1. ingestion massive "aspirer tout iNaturalist" sans demande produit
2. coupler compile et acquisition live
3. lancer multi-taxon avant robustesse d'un premier domaine
4. repousser le chantier distracteurs apres extension de perimetre
5. introduire une abstraction multi-taxon universelle trop tot
