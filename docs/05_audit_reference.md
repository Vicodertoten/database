# Audit De Référence — `database`

Statut: document vivant (référence d’exécution)  
Version: `v1`  
Date d’initialisation: `2026-04-08`  
Périmètre: code + docs + tests + run local du repo

---

## Synthèse Exécutive

`database` est déjà un **excellent pilote de knowledge core**: cadrage stratégique net, modèle de domaine juste, pipeline traçable, qualification IA disciplinée, export versionné, tests solides.

Le point de friction principal n’est pas la structure technique, mais la **gouvernance**:
- gouvernance canonique encore légère pour devenir autorité de vérité interne,
- langage pédagogique encore trop court vs ambition produit,
- contrat d’export encore trop mince pour du multi-usage long terme,
- maturité Ops encore locale/manuelle.

Objectif de ce document: transformer cette base solide en trajectoire opérationnelle mesurable.

## Statut d’exécution des gates

| Gate | Statut | Date | Note |
|---|---|---|---|
| Gate 0 — Migration storage PostgreSQL/PostGIS | DONE | `2026-04-09` | backend principal basculé sur PostgreSQL/PostGIS, CI/tests alignés Postgres |
| Gate 1 — Verrou doctrinal + ADR de chaîne | DONE | `2026-04-09` | clôture documentaire/doctrinale uniquement; aucun changement de contrat technique ni implémentation des gates suivants |
| Gate 2 — Playable corpus vivant v1 | DONE | `2026-04-09` | couche playable versionnée en base (`playable_corpus.v1`) livrée; aucun objet gate 3+ introduit |
| Gate 3 — Modèle pack + révisions + diagnostic | DONE | `2026-04-09` | tables `pack_specs`/`pack_revisions`/`pack_compilation_attempts`, contrats `pack.spec.v1` + `pack.diagnostic.v1`, sans objets Gate 4+ |
| Gate 4 — Compilation dynamique + materialization figée | DONE | `2026-04-09` | tables `compiled_pack_builds`/`pack_materializations`, contrats `pack.compiled.v1` + `pack.materialization.v1`, sans objets Gate 5+ |

### État réel (2026-04-09)

- persistence hybride implémentée: historique append-only (`pipeline_runs` + tables `*_history`) et tables matérialisées `latest`.
- schéma applicatif actuel: `database.schema.v11`.
- backend storage principal: PostgreSQL/PostGIS (`DATABASE_URL`) avec migrations versionnées (`schema_migrations`).
- export principal actuel: `export.bundle.v4`.
- export de transition maintenu en mode opt-in: `export.bundle.v3` (désactivé par défaut).
- version d’overrides opérateur: `review.override.v1` (validation stricte à la lecture).
- contrat playable principal: `playable_corpus.v1` (payload validé par schéma dédié).
- contrat pack principal: `pack.spec.v1` (payload validé par schéma dédié).
- contrat diagnostic pack: `pack.diagnostic.v1` (payload validé par schéma dédié).
- contrat compilation pack: `pack.compiled.v1` (payload validé par schéma dédié).
- contrat materialization pack: `pack.materialization.v1` (payload validé par schéma dédié).
- résiduel Gate 2: i18n `common_names_i18n` initialisé en `en` avec `fr`/`nl` vides tant qu’aucune source locale traduite n’est branchée.
- résiduel Gate 3: seuils de compilabilité v1 (`10/2/20`) stricts et volontairement conservateurs pour le pilotage initial.
- résiduel Gate 4: sélection des distracteurs v1 déterministe et minimale (3 taxons distincts), sans enrichissement asynchrone ni confusions runtime.

### Cible (prochaine étape)

- introduire la queue d’enrichissement (Gate 5), sans dériver runtime.
- conserver la séparation stricte: pas de runtime/session/scoring/progression dans `database`.
- préserver `export.bundle.v4` inchangé pendant la montée des surfaces playable/pack.

### Acté Implémenté Vs Acté Cible (séparation explicite)

| Domaine | Acté implémenté | Acté cible |
|---|---|---|
| Canonique | politique `auto_clear équilibrée` + `reason_code` + `signal_breakdown` + `source_delta` persistés | enrichir la détection amont avec signaux taxonomiques source plus riches |
| Événements | séparation effective `state_event_log` / `canonical_change_log` / `governance_decision_log` | améliorer les vues opérateur avancées et indexation d’inspection |
| Qualification | champs V1+ intégrés (`difficulty_level`, `media_role`, `confusion_relevance`, `diagnostic_feature_visibility`, `learning_suitability`, `uncertainty_reason`) | étendre vers une ontologie pédagogique plus fine (learning sequencing, distractor planning) |
| Export | `export.bundle.v4` principal + sidecar `v3` transition 2 releases | retrait planifié du sidecar `v3` après fenêtre de transition |
| Playable | couche vivante `playable_corpus.v1` persistée en Postgres avec filtres geo/date/signaux | brancher packs/compilation (gates suivants) sans dériver runtime |
| Packs | `pack_id + revision` immuable + diagnostics persistés (`pack.diagnostic.v1`) | brancher la queue d’enrichissement (Gate 5) sans dériver runtime |
| Compilation/Materialization | builds dynamiques `pack.compiled.v1` + snapshots figés `pack.materialization.v1` persistés et inspectables | étendre couverture via enrichissement asynchrone (Gate 5) |
| Ops | métriques run-level standardisées + `smoke.report.v1` | seuils opérationnels avancés (SLA review, alerting automatique) |

## Challenge Consolidé De L’Analyse Externe (2026-04-08)

Cette section challenge explicitement le verdict externe et sert de référence opératoire immédiate.

### Points confirmés

- cadrage produit/scope très discipliné (birds-first, iNaturalist-first, image-only),
- charte canonique v1 effectivement implémentée dans les modèles et le stockage,
- persistance hybride `latest + history` avec rollback transactionnel couvert par tests,
- export versionné `v4` validé par schéma (+ sidecar `v3` transitoire),
- CI minimale réelle (`verify_repo`) et base de tests crédible.

### Points à challenger

- la gouvernance canonique est solide, mais la **détection amont** des transitions taxonomiques reste partielle; le moteur dérive surtout des deltas déjà exprimés sur les taxons courants.
- la couche qualification est robuste en filtrage/réutilisabilité, mais encore peu expressive pédagogiquement (ontologie courte et non contractuelle).
- le contrat export `v4` est désormais riche, mais doit être stabilisé downstream avant retrait du sidecar `v3`.
- la sémantique événementielle est séparée (`state` / `change` / `governance`), et les vues opérateur doivent encore être enrichies.
- ce document contient encore des entrées historiques marquées “acté” qui sont en réalité des cibles (voir rectificatif ci-dessous).

### Rectificatif Doc/Code (obligatoire)

Les éléments `IA4`, `IA6` et le pilotage budget fin de `IA10` restent des objectifs ultérieurs.  
Les éléments `DA12` et l’ontologie pédagogique V1 minimale (`difficulty_level`, `media_role`, `confusion_relevance`, `uncertainty_reason`) sont désormais implémentés.

---

## Décisions Actées (2026-04-08)

Ces décisions sont la baseline d'exécution. Toute déviation doit être documentée.

### Architecture (acté)

| ID | Décision |
|---|---|
| AR1 | `append + purge planifiée` pour les runs/snapshots |
| AR2 | pipeline atomique: transaction DB + écriture JSON temporaire puis renommage |
| AR3 | migrations explicites; reset autorisé uniquement en dev local |
| AR4 | taxons non résolus tolérés en interne mais interdits à l'export |
| AR5 | override vers `accepted` interdit si licence non `safe` |
| AR6 | rétention snapshots bruts: 12 mois; snapshots promus conservés |
| AR7 | PostgreSQL/PostGIS est le storage principal; SQLite n’est plus une cible d’exécution |

### Data (acté)

| ID | Décision |
|---|---|
| DA1 | `canonical_taxon_id` représente un concept interne immuable (pas un nom) |
| DA2 | format ID officiel: `taxon:<group>:<padded_integer>` (généré automatiquement, unique, immuable) |
| DA3 | `display_slug` conservé séparément (lisibilité/URL/debug), non identitaire |
| DA4 | source d’autorité phase 1 birds: `iNaturalist` |
| DA5 | création automatique d’un taxon canonique autorisée uniquement via la source d’autorité |
| DA6 | sources secondaires: mapping/enrichissement uniquement; pas de création canonique automatique |
| DA7 | statuts canoniques officiels: `active`, `deprecated`, `provisional` |
| DA8 | split/merge/replacement explicités (`split_into`, `merged_into`, `replaced_by`, `derived_from`) sans réécriture silencieuse de l’historique |
| DA9 | similarités officielles: `taxonomic_neighbor`, `visual_lookalike`, `educational_confusion` |
| DA10 | l’IA peut enrichir mais ne gouverne jamais le canonique |
| DA11 | `deprecated` ne reçoit plus de nouveaux assets; `provisional` sort de l’export pédagogique par exception explicite uniquement |
| DA12 | export principal `v4` inclut provenance enrichie, trace IA, flags, notes, incertitude typée et review context; sidecar `v3` transitoire |

### IA (acté)

| ID | Décision |
|---|---|
| IA1 | stack modèles par rôle (screening / qualification / enrichissement taxon) |
| IA2 | convention version prompt: `family.task.group.vMAJOR.MINOR.PATCH` |
| IA3 | ontologie pédagogique V1 minimale intégrée (`difficulty_level`, `media_role`, `confusion_relevance`, `uncertainty_reason`) |
| IA4 | double seuil confiance fin (`>=0.80` / `0.65-0.79`) encore cible, non activé dans ce cycle |
| IA5 | seuil résolution acceptance conservé: `1000x750` |
| IA6 | revue humaine adaptative avec plancher de 10%: cible ultérieure |
| IA7 | gold set V1: 100 images, 20 taxons |
| IA8 | maintenance gold set: owner data + owner IA |
| IA9 | rerun ciblé par cache key; rerun complet uniquement sur changement majeur |
| IA10 | coût IA estimé run-level (modèle simple) implémenté; budget piloté fin reste cible |

### Ops (acté)

| ID | Décision |
|---|---|
| OP1 | CI minimale: `verify_repo` sur PR + branche protégée |
| OP2 | merge: 1 review standard; 2 reviews pour canonique/IA/export |
| OP3 | smoke live hebdomadaire |
| OP4 | rapports smoke versionnés dans `docs/smoke_reports/` |
| OP5 | ADR obligatoires pour canonique/qualification/export/IA |

### Roadmap (acté)

| ID | Décision |
|---|---|
| RM1 | ordre P0: doctrine canonique -> robustesse pipeline -> intégrité export -> CI -> gold set |
| RM2 | M1: "le plus vite possible" (pas de date fixe) |
| RM3 | KPI M1: CI active; 0 unresolved exportable; 100% trace IA; 2 smokes complets consécutifs; 0 erreur silencieuse critique |
| RM4 | go multi-taxons seulement après validation P0 + KPI M1 + retrait sidecar `v3` |

---

## Architecture

### État actuel

Points solides:
- séparation claire `CanonicalTaxon` / `SourceObservation` / `MediaAsset` / `QualifiedResource`,
- pipeline explicitement versionné (manifest, normalized, qualification, export),
- séparation canonique vs source déjà matérialisée,
- review queue + overrides snapshot-scopés et rejouables.

Écarts critiques à traiter:
- orchestration encore monolithique dans le runner central (lisibilité/évolutivité limitées),
- vues d’inspection encore limitées malgré la séparation des journaux d’événements,
- gestion d’erreurs encore large sur certains chemins non critiques (`except Exception` infrastructure),
- fallback `"unresolved"` encore possible dans la qualification interne (même si bloqué à l’export).

### Registre des écarts architecture

| ID | Constat | Impact | Priorité |
|---|---|---|---|
| A1 | Orchestrateur pipeline trop centralisé | complexité croissante à chaque nouveau flux | P1 |
| A2 | table legacy `canonical_taxon_events` retirée du flux standard (drop en migration `v7`) | dette résiduelle: compatibilité des DB hors migration contrôlée | P3 |
| A3 | Exceptions larges (`except Exception`) sur couche infrastructure | diagnostic moins précis en incident | P1 |
| A4 | Canonical fallback `"unresolved"` | affaiblit l’autorité canonique | P1 |
| A5 | Indexation Postgres géo/métier à consolider selon charge réelle | dette de performance à l’échelle | P2 |

### Décisions architecture actées (rappel)

1. Politique de persistence: `append + purge planifiée`.
2. Stratégie de migration: migrations explicites; reset limité au dev local.
3. Politique d’intégrité: taxon non résolu toléré en interne, interdit à l’export.

### Critères de sortie Architecture (DoD)

- séparation explicite entre `state event log`, `canonical change log` et `governance decision log`,
- runner allégé par extraction de modules métier (gouvernance/export/qualification),
- aucune exception large non tracée dans les chemins critiques,
- `0` ressource exportée avec taxon non résolu.

---

## Data

### État actuel

Points solides:
- ingestion iNaturalist cadrée (research-grade, licence safe, `captive=false`),
- snapshot cache complet (responses, taxa, images, manifest, ai_outputs),
- usage des dimensions réellement téléchargées pour les décisions qualité,
- artefacts normalisés/qualifiés/exportables reproductibles.

Limites structurantes:
- mono-source (iNaturalist) et birds-only (pilot),
- détection des changements taxonomiques source encore pilot-level (signaux explicites mais couverture limitée),
- contrat export `v4` en phase de stabilisation downstream,
- politique de retrait du sidecar `v3` à exécuter après 2 cycles.

### Registre des écarts data

| ID | Constat | Impact | Priorité |
|---|---|---|---|
| D1 | Signaux opératoires `clear` vs `ambiguous` implémentés mais encore limités à un jeu de signaux pilote | risque de sous-couverture sur cas taxonomiques complexes | P1 |
| D2 | Détection des transitions surtout basée sur l’état canonique déjà enrichi | manque de preuve sur détection amont multi-cas | P0 |
| D3 | Contrat `v4` nouveau: adoption downstream à sécuriser pendant la fenêtre sidecar `v3` | risque de friction de migration | P1 |
| D4 | Maintien transitoire du sidecar `v3` | dette de compatibilité à retirer au terme des 2 cycles | P1 |
| D5 | Similarité encore “pilot-level” | confusion canonique/pédagogique possible | P2 |

### Cible Data (cycle suivant)

1. **Gouvernance canonique**
- règle de vie d’un `canonical_taxon_id`,
- protocole de changement taxonomique (split/merge/synonyme),
- stratégie de conflit inter-sources.

Référence normative stable: `docs/06_charte_canonique_v1.md`.

2. **Contrat export v4+**
- provenance enrichie,
- `qualification_flags` et `qualification_notes`,
- incertitude typée,
- review rationale explicite,
- versioning IA/prompt/task explicite,
- séparation nette `minimum downstream contract` vs `rich internal snapshot`.

3. **Qualité des données mesurable**
- taux de taxons enrichis `complete`,
- taux de ressources `accepted/review/rejected`,
- taux de hints non résolus,
- taux de rerun sans variation inattendue.

### Critères de sortie Data (DoD)

- doctrine canonique documentée et approuvée,
- export schema `v4` validé par tests de compatibilité + retrait contrôlé du sidecar `v3`,
- métriques data standardisées dans `snapshot-health`.

---

## IA

### État actuel

Points solides:
- prompt structuré + schéma JSON strict,
- normalisation des dérives de sortie,
- `prompt_version` gouverné dans les caches,
- qualification rejouable depuis snapshots,
- pacing/retry/backoff pour robustesse API.

Limite principale:
- la qualification est encore orientée **filtrage MVP**, pas encore **langage pédagogique riche**.

### Registre des écarts IA

| ID | Constat | Impact | Priorité |
|---|---|---|---|
| I1 | Ontologie pédagogique insuffisante | faible valeur didactique downstream | P0 |
| I2 | Gold set présent mais encore peu utilisé comme gate de décision | dérive de qualité non contrôlée | P0 |
| I3 | Traçabilité IA partielle dans ressources finales | auditabilité incomplète | P1 |
| I4 | Politiques de rerun/coût non formalisées | surcoût et hétérogénéité | P1 |
| I5 | Multiplication des tâches prompt plus rapide que la consommation downstream | dispersion ontologique | P2 |

### Cible IA V2 (“même école IA”)

Langage interne minimal à ajouter:
- `diagnostic_feature_visibility`
- `learning_suitability`
- `difficulty_level`
- `confusion_relevance`
- `uncertainty_reason`
- `media_role`

Gouvernance IA minimale:
- prompt family versionnée (base + taxon-group + task),
- modèle(s) par rôle explicités,
- gold set figé (images + taxons) avec seuils de non-régression,
- registre de rerun (quand / pourquoi / impact / coût).

### Critères de sortie IA (DoD)

- gold set exécuté comme gate explicite avant tout bump prompt/modèle,
- nouveaux champs pédagogiques intégrés au flux qualification,
- traçabilité complète `model + prompt family + prompt version + task` dans les sorties internes.

---

## Ops

### État actuel

Points solides:
- CLI opérable et cohérente,
- runbook smoke clair,
- script standard de vérification locale (`compileall`, `pytest`, cohérence doc/code, `ruff`),
- tests unitaires/intégration déjà robustes pour un MVP.

Limites:
- processus encore local-first (runbook manuel),
- CI visible mais encore minimale (un seul workflow de vérification),
- observabilité runtime/coût encore peu structurée,
- gouvernance de changement (ADR, conventions) à formaliser.

### Registre des écarts Ops

| ID | Constat | Impact | Priorité |
|---|---|---|---|
| O1 | CI présente mais trop minimale | risque de régression silencieuse | P0 |
| O2 | Smoke majoritairement manuel | faible cadence de validation live | P1 |
| O3 | Pas de tableau de bord coût/volume | pilotage économique incomplet | P1 |
| O4 | Gouvernance doc/changements légère | perte de contexte équipe | P2 |

### Standard Ops minimal (à court terme)

1. CI repository:
- job `verify_repo` automatique sur PR.

2. Rituel smoke:
- cadence hebdomadaire,
- template de rapport standardisé,
- archivage des résultats par snapshot dans `docs/smoke_reports/`.

3. Pilotage:
- suivi des métriques clés (qualité, volume, coût, review load),
- seuils d’alerte simples par métrique.

### Critères de sortie Ops (DoD)

- CI active,
- au moins 3 smokes consécutifs reportés au format standard,
- métriques de suivi visibles et comparables dans le temps.

---

## Roadmap

### Horizon 0–30 jours (P0)

Objectif: sécuriser le noyau (intégrité + gouvernance minimale).

Livrables:
1. Implémentation Charte canonique V1 (IDs, statuts, split/merge, sources, garde-fous IA).
2. Suppression des échecs silencieux critiques et ajout des reason codes.
3. Durcissement intégrité qualification/export (`no unresolved exportable`).
4. CI minimale `verify_repo`.
5. Gold set IA V1 (petit mais stable) + procédure de non-régression.

### Plan d’exécution canonique V1 (nouvelles tâches à réaliser)

| ID | Tâche | Livrable attendu | Priorité | Statut |
|---|---|---|---|---|
| CAN-01 | Introduire les champs canoniques V1 (`accepted_scientific_name`, `synonyms[]`, `taxon_status`, `authority_source`, `display_slug`) | modèle domaine + schémas + stockage alignés charte | P0 | DONE (`2026-04-08`) |
| CAN-02 | Implémenter un générateur d’ID `taxon:<group>:<padded_integer>` | service d’allocation d’ID + tests d’unicité/immutabilité | P0 | DONE (`2026-04-08`) |
| CAN-03 | Migrer les IDs existants vers le format V1 sans perte d’historique | migration SQL + script de backfill + mapping de transition | P0 | DONE (`2026-04-08`) |
| CAN-04 | Appliquer la règle d’autorité: création auto uniquement via iNaturalist | garde-fous dans ingestion/résolution | P0 | DONE (`2026-04-08`) |
| CAN-05 | Bloquer la création canonique automatique depuis sources secondaires | pipeline qui laisse non-résolu si mapping absent | P0 | DONE (`2026-04-08`) |
| CAN-06 | Appliquer les règles de statut (`active`, `deprecated`, `provisional`) | rejet des nouveaux assets sur `deprecated`; exclusion `provisional` à l’export par défaut | P0 | DONE (`2026-04-08`) |
| CAN-07 | Implémenter les relations de changement (`split_into`, `merged_into`, `replaced_by`, `derived_from`) | représentation persistée + lecture API/export interne | P0 | DONE (`2026-04-08`) |
| CAN-08 | Créer un journal de gouvernance canonique (événements de changement) | trail audit explicite pour split/merge/replacement | P1 | DONE (`2026-04-08`) |
| CAN-09 | Migrer la similarité vers les 3 relations officielles V1 | enums + fixtures + compatibilité descendante documentée | P1 | DONE (`2026-04-08`) |
| CAN-10 | Encadrer les enrichissements IA en lecture seule sur l’identité canonique | validation qui interdit mutations identitaires par IA | P0 | DONE (`2026-04-08`) |
| CAN-11 | Couvrir les règles automatiques R1–R12 + règles interdites | tests unitaires/intégration + cas d’échec explicites | P0 | DONE (`2026-04-08`) |
| CAN-12 | Produire l’ADR d’implémentation de la charte | ADR signée + documentation de migration hard cutover | P1 | DONE (`2026-04-08`) |

### Exécution P0 complémentaire (post-canonique)

| ID | Tâche | Livrable attendu | Priorité | Statut |
|---|---|---|---|---|
| RBT-01 | Robustesse pipeline A1+A2+A3 | fin reset implicite, transaction DB sur run, artefacts JSON écrits via temporaires+rename, exceptions critiques resserrées | P0 | DONE (`2026-04-08`) |
| CI-01 | CI minimale GitHub | workflow `.github/workflows/verify-repo.yml` sur PR + push `main` | P0 | DONE (`2026-04-08`) |
| GS-01 | Gold set IA V1 | dataset `data/goldset/birds_v1` avec 20 taxons / 100 images + script de vérification dédié | P0 | DONE (`2026-04-08`) |

### Priorités consolidées (après challenge externe)

| Ordre | Chantier | Livrable minimal |
|---|---|---|
| 1 | Détection canonique amont | spécification explicite des signaux `clear`/`ambiguous` + tests d’intégration associés |
| 2 | Qualification pédagogique | champs `difficulty_level`, `media_role`, `confusion_relevance`, `uncertainty_reason` dans le pipeline |
| 3 | Contrat export enrichi | extension `v4` (ou `v3.1`) avec flags/notes/rationale et validation schéma |
| 4 | Sémantique événementielle | séparation nette entre journal d’état, journal de changement, journal de gouvernance |
| 5 | Pilotage Ops | métriques standardisées (volume, coût, review load) + smoke report comparable |

### Horizon 31–60 jours (P1)

Objectif: enrichir la qualité pédagogique et le contrat de sortie.

Livrables:
1. Ontologie pédagogique V1 intégrée à la qualification.
2. Contrat export `v4` stabilisé downstream + plan de retrait sidecar `v3`.
3. Dashboard smoke standardisé (qualité/volume/coût/review).
4. Politique de rerun IA documentée.

### Horizon 61–90 jours (P2)

Objectif: préparer la montée en échelle contrôlée.

Livrables:
1. Plan migration persistence/migrations (post-reset strategy).
2. Indexation Postgres ciblée et mesure de performance.
3. Extension pilote vers sous-ensemble taxons additionnels (sans casser la doctrine).

### Backlog priorisé (référence)

| Priorité | Sujet | Résultat attendu |
|---|---|---|
| P0 | Gouvernance canonique V1 | référentiel de vérité opérable |
| P0 | Robustesse pipeline (atomicité + erreurs) | runs fiables et auditables |
| P0 | CI minimale | qualité continue sur PR |
| P0 | Gold set IA V1 | stabilité qualitative contrôlée |
| P1 | Ontologie pédagogique V1 | qualification utile pour apprentissage |
| P1 | Stabilisation export contract `v4` | meilleure réutilisabilité downstream |
| P1 | Pilotage coût/volume/review | décisions outillées |
| P2 | Perf + migration DB | readiness montée en charge |

### Jalons de validation

- `M1` (fin P0): noyau sécurisé, gouvernance minimale validée, à atteindre le plus vite possible (pas de date fixe).
- `M2` (fin P1): qualification pédagogiquement plus riche + export `v4` stabilisé.
- `M3` (fin P2): base prête à extension multi-taxons incrémentale.

---

## Mode De Mise À Jour Du Document

Cadence recommandée:
- revue hebdomadaire légère,
- revue mensuelle décisionnelle.

Règles:
1. toute décision de doctrine impactant le canonique, la qualification, l’export ou l’IA doit être reflétée ici;
2. toute clôture d’un item `P0/P1/P2` doit mettre à jour son statut et sa date;
3. toute divergence entre repo et document est une dette explicite à corriger.

Template de mise à jour:

```text
date:
owner:
section_modifiée:
changement:
raison:
impact:
next_step:
```

---

## Statut Initial (Baseline)

- Vérification repo locale: `71 passed`, lint/compile/doc-check OK.
- Pipeline fixture: `qualified=4`, `exportable=2`, `review=1`.
- Ce baseline correspond à l’état observé au `2026-04-08`.
