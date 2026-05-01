---
owner: database
status: in_progress
last_reviewed: 2026-05-01
source_of_truth: docs/runbooks/pre-scale-ingestion-roadmap.md
scope: runbook
---

# Pre-Scale Ingestion Roadmap

Statut fonctionnel: draft  
Statut front-matter: `in_progress`, car les statuts actifs acceptés par `check_docs_hygiene.py` n'incluent pas `draft`.  
Périmètre immédiat: oiseaux, Belgique, image-only, 50 espèces, 1 000 images qualifiées  
Rôle du document: runbook stratégique et opérationnel pour robustifier la pipeline avant montée en volume.

Ce document ne remplace pas `docs/runbooks/execution-plan.md`.

- `execution-plan.md` reste le plan opératoire général du repo.
- `pre-scale-ingestion-roadmap.md` pilote spécifiquement la robustification ingestion, qualification, feedback, distracteurs, audit, coûts et passage à l'échelle.

## Current active chantier

Active chantier: Phase A - Verrouiller les gates  
Status: in_progress  
Next concrete output: palier 1 audit preparation  

Do not start as structural implementation work before Phase A exit criteria:

- Phase B - Pré-IA déduplication et coût;
- Phase C - Feedback minimal utile;
- Phase D - Distracteurs auditables;
- Phase F - Recherche sources batch;
- paliers 2 à 5.

Phase A exit criteria:

- gates documentés avec statuts, reason codes, décision bloquante ou review;
- reason codes existants inventoriés;
- gaps entre code actuel et roadmap explicités;
- mapping code actuel -> gate -> reason_code produit;
- gates bloquants palier 1 identifiés;
- premier audit palier 1 préparé;
- aucun déplacement de logique runtime dans `database`.

## Phase Delivery Map

| Phase | Livrable principal | Type | Repo | Statut |
|---|---|---|---|---|
| A | quality gates + code-to-gate map | doc/runbook | `database` | in_progress |
| B | audit dedup pré-IA | script/report | `database` | todo |
| C | feedback minimal utile | data/model/report | `database` | todo |
| D | audit distracteurs `QuestionOption[]` | report | `database` + `runtime-app` | partial |
| E | audit palier 1 | report | `database` | todo |
| F | recherche sources batch | research note | `database` | todo |
| G | stress test palier 2 | run report | `database` | blocked |
| H | pré-scale paliers 3/4 | run plan/report | `database` | blocked |

## 1. Décision stratégique

Objectif:

Transformer des données naturalistes brutes en ressources jouables fiables, traçables, pédagogiquement utiles et économiquement soutenables.

Principe central:

> Une observation valide n'est pas encore une ressource pédagogique. Elle ne le devient qu'après canonicalisation, filtrage, dédoublonnage, qualification, traçabilité, feedback exploitable, distracteurs valides et audit final.

Conséquence opérationnelle:

- ne pas scaler les ingestions tant que la qualité, le coût, les doublons, le feedback, les distracteurs et les audits ne sont pas mesurés;
- ne pas utiliser le runtime comme lieu de correction de la donnée;
- ne pas lancer de génération IA lourde avant les gates pré-IA;
- ne pas confondre volume ingéré et corpus jouable.

## 2. Positionnement dans l'architecture

`database` possède:

- vérité canonique;
- ingestion snapshot et traçabilité source;
- qualification juridique, technique et pédagogique;
- playable items;
- packs, compiled builds et materializations;
- feedback préparé;
- distracteurs gouvernés;
- review queue;
- audit de corpus et signaux de qualité;
- ingestion batch des signaux utilisateurs utiles à l'amélioration du corpus.

`runtime-app` possède:

- sessions;
- présentation des questions;
- réponses utilisateur;
- score;
- progression;
- UX;
- collecte de signaux d'usage.

Frontière non négociable:

- aucun appel live iNaturalist ou GBIF dans la boucle de jeu;
- aucune génération live de feedback dans le runtime;
- le runtime ne lit jamais `export.bundle.v4`;
- le runtime consomme les surfaces officielles owner-side;
- toute amélioration issue des signaux runtime repasse par `database`, review queue et pipeline.

## 3. Périmètre immédiat et trajectoire

### 3.1 Périmètre d'exécution immédiat

Le palier actif reste strictement le périmètre v0.1:

- taxons: oiseaux uniquement;
- zone: Belgique uniquement;
- média: images uniquement;
- source active: iNaturalist snapshot/cache;
- objectif: 50 espèces, 1 000 images qualifiées;
- usage: QCM + réponse directe simple;
- runtime: consommation sans appel live source externe.

### 3.2 Trajectoire de montée en volume

| Palier | Périmètre | Volume cible | Objectif | Statut |
|---|---:|---:|---|---|
| 1 | oiseaux Belgique | 50 espèces / 1 000 images qualifiées | corpus pilote solide | actif |
| 2 | oiseaux communs Europe occidentale | 150 espèces / 5 000 à 10 000 images candidates | stress test coût, temps, review, qualité | bloqué par audit palier 1 |
| 3 | oiseaux Europe | 300 espèces / 20 000 images candidates | pré-scale reproductible | bloqué par recherche sources + coûts |
| 4 | oiseaux communs Europe large | 50 000+ images candidates | ingestion large contrôlée | bloqué par paliers 1 à 3 |
| 5 | multi-taxons | plantes, champignons, insectes, mammifères, etc. | extension du modèle | bloqué par stabilité oiseaux/image-only |

## 4. Conditions bloquantes

Ne pas passer au palier 2 tant que:

- le palier 1 n'a pas reçu une décision `GO` ou `GO_WITH_WARNINGS`;
- les coûts IA par image candidate et par image jouable ne sont pas mesurés;
- le taux d'acceptation, le taux d'incertitude et le volume de review ne sont pas connus;
- les doublons exacts ne sont pas filtrés avant Gemini;
- les audits feedback, distracteurs et traçabilité ne sont pas exploitables.

Ne pas passer aux paliers 3 ou 4 tant que:

- la stratégie GBIF/iNaturalist batch/download n'est pas étudiée et documentée;
- les rate limits, licences, métadonnées média, batch exports et contraintes de traçabilité ne sont pas clarifiés;
- la stratégie de stockage média long terme n'est pas cadrée;
- les seuils de qualification pédagogique ne sont pas stabilisés;
- le coût Gemini par palier n'est pas prévisible.

Ne pas lancer le multi-taxon tant que:

- oiseaux/image-only n'est pas stable;
- les gates et reason codes ne sont pas robustes;
- la review queue est exploitable par un opérateur seul;
- les audits finaux décident clairement `GO`, `GO_WITH_WARNINGS` ou `NO_GO`.

Ne pas généraliser `referenced_only` tant que:

- son usage est visible dans les audits;
- les mappings ambigus ou low confidence sont exclus;
- le contexte institutionnel garde `referenced_only` désactivé par défaut;
- une validation humaine a confirmé l'absence de distracteurs injustes.

## 5. Pipeline cible pré-scale

Séquence cible:

1. Sélection source.
2. Ingestion snapshot.
3. Canonicalisation.
4. Filtrage licence/source.
5. Dédoublonnage et filtrage technique pré-IA.
6. Qualification pédagogique IA/humaine.
7. Feedback préparé.
8. Création playable items.
9. Construction des distracteurs.
10. Compilation packs.
11. Materialization.
12. Audit final.
13. Runtime quiz/révision.
14. Signaux utilisateurs.
15. Review et amélioration `database`.

Règle:

- les étapes 1 à 5 doivent réduire le volume avant qualification IA lourde;
- les étapes 6 à 12 doivent produire des artefacts jouables, auditables et reproductibles;
- les étapes 13 à 15 doivent améliorer le corpus sans déplacer la vérité vers le runtime.

## 6. Quality gates

Chaque gate produit:

- `accepted`;
- `rejected`;
- `uncertain`;
- `needs_review`.

Chaque décision doit porter un `reason_code` explicite.

| Gate | Nom | Exemples de critères | Reason codes initiaux |
|---|---|---|---|
| 1 | Source OK | source fiable, snapshot reproductible, payload traçable | `source_not_allowed`, `snapshot_incomplete`, `source_payload_missing` |
| 2 | Licence OK | licence acceptée, auteur présent, source URL présente | `license_not_allowed`, `missing_author`, `missing_attribution`, `missing_source_url` |
| 3 | Taxon canonique OK | taxon actif ou review explicite | `taxon_unmapped`, `taxon_provisional`, `taxon_deprecated`, `mapping_ambiguous` |
| 4 | Anti-doublons OK | source media ID, file hash, déjà vu entre runs | `duplicate_source_media`, `duplicate_file_hash`, `already_seen_media` |
| 5 | Média techniquement exploitable | résolution, format, ratio, image lisible | `image_too_small`, `image_broken`, `unsupported_format`, `image_too_blurry`, `subject_too_small` |
| 6 | Média pédagogiquement utile | sujet visible, traits diagnostiques visibles, valeur d'apprentissage | `diagnostic_features_not_visible`, `pedagogical_value_low`, `subject_visibility_low`, `ai_confidence_low` |
| 7 | Feedback minimal OK | feedback général et photo-spécifique présents, utiles, courts | `feedback_missing`, `feedback_too_generic`, `feedback_too_long`, `feedback_confidence_low` |
| 8 | Distracteurs disponibles | 3 distracteurs valides, labels présents, sources traçables | `no_valid_distractors`, `distractor_label_missing`, `distractor_mapping_ambiguous`, `distractor_unfair` |
| 9 | Traçabilité complète | run, source, licence, qualification, feedback, options | `trace_missing`, `source_lineage_missing`, `qualification_trace_missing` |
| 10 | Export jouable OK | playable item actif et compatible surfaces runtime | `not_exportable`, `materialization_invalid`, `runtime_contract_invalid` |

Critère de réussite:

Pour chaque image candidate, un opérateur doit pouvoir expliquer:

- pourquoi elle est acceptée;
- pourquoi elle est rejetée;
- pourquoi elle est incertaine;
- qui doit la revoir;
- quel gate bloque sa promotion.

## 7. Dédoublonnage et pré-filtrage IA

Le dédoublonnage est prioritaire avant Gemini.

### 7.1 Court terme obligatoire

À couvrir avant qualification IA lourde:

- doublon exact par `source_media_id`;
- doublon exact par `media_url` canonisée si disponible;
- doublon exact par `file_hash`;
- média déjà vu dans le même snapshot;
- média déjà ingéré entre runs;
- observation ou média réingéré sans changement utile.

Sortie attendue:

- nombre de médias candidats avant déduplication;
- nombre de doublons exacts supprimés;
- nombre de médias envoyés à Gemini;
- coût évité estimé;
- reason codes par type de doublon.

### 7.2 À cadrer avant implémentation lourde

Le quasi-doublon visuel est stratégique mais pas encore assez défini.

Sujets à cadrer:

- perceptual hash;
- embeddings visuels;
- crops;
- redimensionnements;
- reposts entre sources;
- mêmes photos sur iNaturalist et GBIF;
- seuils de similarité;
- conservation du meilleur média;
- impact légal et attribution si deux sources exposent le même média.

Décision provisoire:

- ne pas bloquer le palier 1 sur les quasi-doublons;
- ne pas lancer de gros volume sans stratégie documentée pour les quasi-doublons.

## 8. Modèle de qualification pédagogique

La qualification ne répond pas seulement à:

> L'image est-elle correcte?

Elle répond à:

> Cette image aide-t-elle vraiment à apprendre à reconnaître l'espèce?

Scores recommandés:

| Score | Sens | Échelle |
|---|---|---|
| `technical_quality_score` | netteté, résolution, exploitabilité | 0 à 4 |
| `subject_visibility_score` | sujet visible, taille, cadrage | 0 à 4 |
| `diagnostic_visibility_score` | traits utiles visibles | 0 à 4 |
| `pedagogical_value_score` | valeur d'apprentissage | 0 à 4 |
| `confusion_relevance_score` | aide à distinguer des espèces proches | 0 à 4 |
| `difficulty_score` | difficulté estimée | 0 à 4 |
| `confidence_score` | confiance IA/humaine globale | 0 à 4 |

Interprétation:

- `0`: inutilisable;
- `1`: faible;
- `2`: acceptable;
- `3`: bon;
- `4`: excellent.

Règle de passage initiale à valider:

Playable si:

- `technical_quality_score >= 2`;
- `subject_visibility_score >= 2`;
- `diagnostic_visibility_score >= 2`;
- `pedagogical_value_score >= 2`;
- licence OK;
- taxon canonique `active`;
- feedback minimal présent;
- traçabilité complète.

Cette règle reste une hypothèse de pilotage tant que le palier 1 n'a pas été audité.

## 9. Feedback pédagogique

Le feedback préparé appartient à `database`.

Le runtime peut l'afficher et collecter des signaux, mais il ne le génère pas en live.

### 9.1 Couches de feedback

| Couche | Définition | Statut roadmap |
|---|---|---|
| `feedback_taxon_general` | aide générale pour identifier l'espèce | court terme |
| `feedback_photo_specific` | aide liée à l'image affichée | court terme |
| `feedback_after_error` / `feedback_confusion` | comparaison entre bonne réponse et mauvaise réponse choisie | à approfondir |

### 9.2 Court terme

Le palier 1 doit assurer:

- feedback général minimal par taxon;
- feedback photo-spécifique minimal par playable item;
- texte court, utile, compatible mobile;
- pas d'hallucination taxonomique évidente;
- traçabilité de provenance ou génération;
- reason code si feedback faible ou manquant.

### 9.3 Signaux runtime à réintégrer

Signaux utiles:

- feedback ignoré;
- feedback signalé inutile;
- confusion persistante malgré feedback;
- question signalée;
- mauvaise image;
- taux d'erreur anormal par question;
- taux d'erreur anormal par paire de taxons.

Règle:

- ces signaux créent des entrées de review ou des agrégats dans `database`;
- ils ne modifient pas directement les playable items;
- ils ne déclenchent pas de génération live dans le runtime.

## 10. Distracteurs

Le système de distracteurs est critique avant la montée en volume.

Référence existante:

- `docs/runbooks/phase3-distractor-strategy.md`;
- `docs/foundation/adr/0006-taxon-based-question-options.md`.

### 10.1 Objectif

Produire des distracteurs:

- plausibles;
- traçables;
- non absurdes;
- non injustes;
- compatibles avec `QuestionOption[]`;
- auditables après materialization.

### 10.2 Sources de signaux

Signaux utilisables:

- `similar_taxon_ids` internes;
- iNaturalist similar species quand disponible;
- taxonomie proche: même genre, famille, ordre;
- agrégats globaux de confusion;
- review humaine;
- signaux runtime batch;
- référencés externes gouvernés.

### 10.3 `referenced_only`

Pour le palier 1:

- autorisé seulement avec garde-fous forts;
- maximum recommandé: 1 `referenced_only` par question;
- jamais si `mapping_status` est `ambiguous`;
- jamais si `mapping_status` est low confidence;
- visible en audit;
- prioritaire en review si utilisé dans un pack important.

Pour contexte institutionnel:

- `referenced_only` désactivé par défaut tant que non validé humainement.

### 10.4 Questions ouvertes

À approfondir avant paliers 3 ou 4:

- comment obtenir des signaux type `similar_species` sans spammer l'API iNaturalist;
- possibilité et limites via GBIF ou jeux de données téléchargés;
- couverture réelle des similarités par taxon;
- coût et fraîcheur des snapshots;
- règles de promotion vers similarité interne;
- seuils de validation pédagogique des distracteurs.

## 11. Gemini, coût et parallélisme

Priorité nominale:

- réduire le coût par image jouable;
- augmenter la qualité;
- limiter les appels IA aux médias qui ont déjà passé les gates pré-IA.

Deux modes sont autorisés:

| Mode | Usage | Règles |
|---|---|---|
| nominal cost-efficient | ingestion réelle, pilotage qualité | batch contrôlé, gates pré-IA, déduplication obligatoire, métriques coût |
| dev accéléré | petits corpus, développement ponctuel | parallélisme x4/x8 autorisé, coût borné, pas mode de production |

KPIs coût:

- coût par image candidate;
- coût par image envoyée à Gemini;
- coût par image qualifiée;
- coût par playable item;
- coût évité par déduplication;
- coût évité par filtrage licence/source;
- coût évité par filtrage technique pré-IA.

Condition bloquante:

- ne pas généraliser Gemini à gros volume sans rapport coût/acceptation sur palier 1.

## 12. Sources externes et stratégie batch

Le palier 1 peut continuer avec iNaturalist snapshot/cache.

Avant paliers 3 ou 4, une recherche source officielle est obligatoire.

À étudier:

- options de batch download iNaturalist;
- options de download GBIF;
- licences observation vs média;
- présence et qualité des métadonnées média;
- attribution et source URL;
- rate limits;
- reproductibilité des snapshots;
- différences iNaturalist direct vs GBIF;
- disponibilité des taxon concepts et mappings;
- disponibilité de similarités ou alternatives à `similar_species`;
- stratégie de stockage média long terme.

Décision provisoire:

- ne pas ingérer "tout GBIF";
- construire des lots pédagogiques ciblés;
- ne pas laisser une source externe redéfinir librement l'identité canonique;
- ne pas créer automatiquement de taxons actifs depuis des sources secondaires.

Exemples de lots:

- oiseaux communs Belgique;
- oiseaux jardins Europe occidentale;
- oiseaux forestiers Europe;
- oiseaux d'eau Europe;
- rapaces Europe.

## 13. Review queue

Objectif:

Automatiser les cas évidents et isoler les cas incertains.

À envoyer en review:

- taxon mapping incertain;
- licence ambiguë;
- image techniquement correcte mais pédagogiquement douteuse;
- confiance IA faible;
- désaccord entre signaux;
- feedback généré mais faible;
- distracteur potentiellement injuste;
- `referenced_only` utilisé dans un pack sensible;
- question avec erreurs utilisateur anormales;
- question signalée.

Champs attendus:

- `review_item_id`;
- `stage`;
- `reason_code`;
- `review_priority`;
- `review_status`;
- `target_type`;
- `target_id`;
- `resolved_by`;
- `resolved_at`;
- `resolved_note`.

Priorisation:

1. espèces très jouées;
2. espèces avec peu d'images qualifiées;
3. images proches du seuil d'acceptation;
4. packs institutionnels;
5. questions avec beaucoup d'erreurs utilisateur;
6. questions signalées;
7. distracteurs `referenced_only`.

Critère de réussite:

L'opérateur ne doit pas revoir 10 000 images. Il doit revoir les quelques centaines de cas qui bloquent réellement la qualité du corpus.

Court terme:

- reviewer principal: opérateur projet;
- workflow exploitable sans expert externe obligatoire;
- escalade future possible vers expert naturaliste, enseignant, utilisateur test ou reviewer institutionnel.

## 14. Audit final et décision de run

Chaque run significatif doit finir par:

- `GO`;
- `GO_WITH_WARNINGS`;
- `NO_GO`.

Un script qui "a tourné" n'est pas une décision qualité.

### 14.1 Rapport attendu

Le rapport de run doit inclure:

- observations ingérées;
- médias candidats;
- médias rejetés par doublon;
- médias licence OK;
- médias envoyés à Gemini;
- taxons mappés;
- ressources qualifiées;
- playable items actifs;
- playable items invalidés;
- couverture par espèce;
- moyenne et médiane d'images par espèce;
- taux de feedback général présent;
- taux de feedback photo-spécifique présent;
- taux de distracteurs valides;
- taux de questions compilables;
- taux de materializations valides;
- volume de review;
- coût total IA;
- coût par playable item;
- temps pipeline.

### 14.2 KPIs essentiels

| KPI | Sens |
|---|---|
| `playable_acceptance_rate` | playable items / médias candidats |
| `qualification_rejection_rate` | ressources rejetées / ressources évaluées |
| `uncertain_review_rate` | cas review ou uncertain / ressources évaluées |
| `playable_items_per_taxon` | couverture exploitable par taxon |
| `median_images_per_taxon` | robustesse de couverture |
| `pack_compilability_rate` | packs compilables / packs testés |
| `valid_distractor_rate` | questions avec distracteurs valides / questions |
| `feedback_coverage_rate` | playable items avec feedback utile / playable items |
| `traceability_completion_rate` | items avec trace complète / items |
| `cost_per_candidate_image` | coût IA + ingestion / image candidate |
| `cost_per_playable_item` | coût total / playable item |
| `pipeline_time_per_1000_images` | temps opérationnel normalisé |
| `dedup_rejection_rate` | doublons exacts / médias candidats |
| `pre_ai_filter_savings_rate` | médias évités avant Gemini / médias candidats |

### 14.3 Décision

`GO`:

- hard gates passent;
- artefacts runtime valides;
- feedback et distracteurs au-dessus des seuils;
- coût et temps acceptables;
- review queue exploitable.

`GO_WITH_WARNINGS`:

- hard gates passent;
- quelques KPIs restent faibles mais non bloquants;
- plan de correction explicite avant palier suivant.

`NO_GO`:

- hard gate cassé;
- licence ou attribution douteuse;
- coût non mesuré;
- taux de review ingérable;
- distracteurs ou feedback trop faibles;
- materialization invalide;
- runtime E2E non validé pour les artefacts attendus.

## 15. Paliers de validation

### 15.1 Palier 1 - Corpus pilote solide

Périmètre:

- 50 espèces;
- 1 000 images qualifiées;
- Belgique;
- oiseaux;
- image-only;
- packs v2;
- distracteurs auditables;
- feedback minimal;
- runtime jouable sans appel live iNaturalist.

Critères:

- >= 80% espèces avec au moins 10 images jouables;
- >= 90% playable items avec attribution complète;
- >= 80% questions avec distracteurs plausibles;
- >= 70% playable items avec feedback utile;
- pack v2 compilable sans bricolage;
- materialization v2 inspectable;
- test E2E runtime avec `selectedOptionId`;
- Postgres runtime tests verts;
- aucun appel live source externe dans la boucle de jeu.

Audit humain:

- minimum 50 questions;
- idéalement 100 questions;
- reviewer principal: opérateur projet.

### 15.2 Palier 2 - Stress test modéré

Périmètre:

- 150 espèces;
- 5 000 à 10 000 images candidates;
- Europe occidentale;
- oiseaux communs.

Mesurer:

- temps total pipeline;
- coût IA total;
- coût par image candidate;
- coût par image jouable;
- taux d'acceptation;
- taux d'incertitude;
- taille stockage média;
- couverture par espèce;
- espèces sous-couvertes;
- volume de review;
- qualité des distracteurs;
- qualité du feedback.

Critère:

- pipeline terminée sans intervention manuelle lourde;
- review queue exploitable;
- coût par playable item acceptable;
- pas d'explosion des erreurs de mapping;
- packs compilables sur la majorité des espèces.

### 15.3 Palier 3 - Pré-scale

Périmètre:

- 300 espèces;
- 20 000 images candidates;
- Europe oiseaux.

Critères:

- run reproductible;
- métriques stables;
- coût prévisible;
- stratégie source batch documentée;
- stratégie stockage média cadrée;
- pas de dette documentaire bloquante;
- audit automatique fiable.

### 15.4 Palier 4 - Large Europe oiseaux

Périmètre:

- 50 000+ images candidates;
- oiseaux communs européens.

Condition:

- uniquement si les paliers 1 à 3 sont maîtrisés.

### 15.5 Palier 5 - Multi-taxons

Périmètre futur:

- plantes;
- champignons;
- insectes;
- mammifères;
- autres groupes.

Condition:

- ne pas lancer tant que le modèle oiseaux/image-only n'est pas stable.

## 16. Audit pédagogique humain

À chaque palier, échantillonner:

- 50 questions minimum;
- 100 questions idéalement.

Grille:

| Axe | Score |
|---|---|
| image claire | 0 à 4 |
| espèce identifiable | 0 à 4 |
| trait diagnostique visible | 0 à 4 |
| distracteurs plausibles | 0 à 4 |
| feedback utile | 0 à 4 |
| niveau de difficulté approprié | 0 à 4 |
| intérêt pédagogique global | 0 à 4 |

Interprétation:

- `0`: inutilisable;
- `1`: faible;
- `2`: acceptable;
- `3`: bon;
- `4`: excellent.

Seuils recommandés:

- >= 80% questions notées 2 ou plus;
- >= 60% questions notées 3 ou plus;
- <= 5% questions notées 0;
- 0 question avec image juridiquement douteuse;
- 0 question sans attribution.

Après palier 1 solide:

- test utilisateur avec 5 à 10 personnes;
- 10 à 20 questions chacun;
- retour qualitatif sur compréhension image, plausibilité distracteurs, apprentissage, feedback et envie de rejouer.

## 17. Roadmap d'exécution recommandée

### Phase A - Verrouiller les gates

Objectif:

- formaliser gates, statuses, reason codes, seuils initiaux et décision `GO` / `GO_WITH_WARNINGS` / `NO_GO`.

Livrables:

- `docs/runbooks/ingestion-quality-gates.md`;
- ADR léger si changement doctrinal;
- première taxonomie de reason codes;
- critères de passage palier 1.

Vérification:

- chaque gate a statut, reason codes et propriétaire de décision;
- aucun gate ne pousse de logique runtime dans `database`.

### Phase B - Pré-IA déduplication et coût

Objectif:

- éviter de payer Gemini pour des médias qui ne devraient jamais être qualifiés.

Livrables:

- audit exact dedup;
- métriques coût évité;
- rapport médias avant/après pré-filtrage;
- décision sur seuils minimaux avant Gemini.

Vérification:

- doublons exacts filtrés avant IA;
- coûts par image envoyée à Gemini mesurés;
- quasi-doublons listés comme sujet à cadrer, non mélangés au scope court terme.

### Phase C - Feedback minimal utile

Objectif:

- fournir un feedback général taxon et un feedback photo-spécifique exploitables.

Livrables:

- règle de génération ou qualification du feedback;
- couverture feedback dans l'audit;
- reason codes pour feedback faible.

Vérification:

- >= 70% playable items palier 1 avec feedback utile;
- feedback compatible mobile;
- pas de génération live runtime.

### Phase D - Distracteurs auditables

Objectif:

- améliorer la plausibilité des options et tracer chaque choix.

Livrables:

- audit des `QuestionOption[]`;
- scoring/reason codes distracteurs;
- politique `referenced_only`;
- validation E2E `selectedOptionId`.

Vérification:

- >= 80% questions avec distracteurs plausibles;
- maximum 1 `referenced_only` par question au palier 1;
- `referenced_only` désactivé par défaut en institutionnel.

### Phase E - Palier 1 audit complet

Objectif:

- transformer le corpus pilote en base mesurée.

Livrables:

- rapport automatique de run;
- audit humain 50 à 100 questions;
- décision `GO`, `GO_WITH_WARNINGS` ou `NO_GO`;
- liste de corrections avant palier 2.

Vérification:

- critères palier 1 atteints ou écarts documentés;
- review queue exploitable par l'opérateur projet.

### Phase F - Recherche sources batch

Objectif:

- préparer les paliers 3 et 4 sans spam API et sans dette juridique.

Livrables:

- note GBIF/iNaturalist batch/download;
- comparaison iNaturalist direct vs GBIF;
- stratégie licences et attribution;
- stratégie similarités alternatives;
- stratégie stockage média long terme.

Vérification:

- aucun passage palier 3/4 sans cette recherche;
- aucune source secondaire ne crée librement un taxon actif.

### Phase G - Palier 2 stress test

Objectif:

- tester coût, temps, qualité et review à volume modéré.

Livrables:

- run 5 000 à 10 000 images candidates;
- rapport coût/temps/qualité;
- audit de couverture;
- review queue priorisée.

Vérification:

- coût par playable item acceptable;
- pipeline sans intervention manuelle lourde;
- pas d'explosion des erreurs de mapping.

### Phase H - Pré-scale et ingestion large

Objectif:

- préparer puis lancer les paliers 3 et 4 seulement si les métriques sont stables.

Livrables:

- stratégie batch validée;
- budget IA par palier;
- stratégie stockage;
- audit automatique fiable;
- run reproductible.

Vérification:

- paliers 1 et 2 validés;
- coûts prévisibles;
- review queue maîtrisée;
- décision `GO` explicite.

## 18. Livrables prioritaires

Court terme:

- `docs/runbooks/ingestion-quality-gates.md`;
- rapport automatique de run;
- audit exact dedup pré-IA;
- audit playable corpus quality;
- audit pack/materialization quality;
- grille d'audit humain palier 1.

Moyen terme:

- review queue améliorée;
- rapport coût IA;
- stress test palier 2;
- dashboard opérateur simple;
- gold set de validation pédagogique;
- stratégie source batch GBIF/iNaturalist.

Long terme:

- ingestion par lots GBIF/iNaturalist;
- multi-taxons;
- validation experte;
- corpus institution-ready.

## 19. Immediate next actions

1. Valider ce document comme draft fonctionnel.
2. Créer et maintenir `docs/runbooks/ingestion-quality-gates.md`.
3. Mapper le code actuel aux gates.
4. Inventorier les reason codes existants et les gaps.
5. Définir les gates bloquants du palier 1.
6. Auditer le palier 1 actuel.
7. Produire un premier rapport `GO`, `GO_WITH_WARNINGS` ou `NO_GO`.

## 20. Questions ouvertes à clarifier avant implémentation lourde

Ces sujets ne doivent pas être traités comme de simples détails d'implémentation:

1. Anti-doublons avancé et quasi-doublons visuels.
2. Stratégie GBIF batch/download.
3. Alternatives à iNaturalist `similar_species`.
4. Feedback de confusion après erreur.
5. Politique `referenced_only` en contexte institutionnel.
6. Stratégie de stockage média long terme.
7. Coûts Gemini par palier.
8. Seuils définitifs de qualification pédagogique.
9. Règles de conservation du meilleur média entre doublons.
10. Seuils de review humaine par 1 000 images.

## 21. Références

- `README.md`
- `docs/README.md`
- `docs/runbooks/execution-plan.md`
- `docs/runbooks/ingestion-quality-gates.md`
- `docs/runbooks/ingestion-code-to-gate-map.md`
- `docs/runbooks/v0.1-scope.md`
- `docs/runbooks/program-kpis.md`
- `docs/runbooks/phase3-distractor-strategy.md`
- `docs/foundation/domain-model.md`
- `docs/foundation/pipeline.md`
- `docs/foundation/runtime-consumption-v1.md`
- `docs/foundation/adr/0006-taxon-based-question-options.md`
