# Audit De Reference - database

Statut: document vivant (reference d'execution)
Version: v3
Date de mise a jour: 2026-04-09
Perimetre: etat reel du repo apres Gate 5

---

## 1. Synthese executive

Le repo est sur la bonne trajectoire et a livre une base operationnelle solide jusqu'au Gate 5.

Points forts confirmes:

- storage principal PostgreSQL/PostGIS en place, migrations versionnees
- pipeline reproductible avec artefacts versionnes
- gouvernance canonique v1 active et tracee
- couche playable v1 en base, inspectable via CLI
- couche pack v1, diagnostic v1, compilation v1, materialization v1
- policy distracteurs v2 active dans la compilation pack
- couverture tests structurants et smoke KPI verrouilles

Point critique post-Gate 5:

- la cible finale playable est un corpus cumulatif incremental reel
- l'implementation actuelle reste une surface latest reconstruite a chaque run
- cet ecart reste explicite et constitue le chantier strategique avant Gate 6+

Decision de pilotage appliquee:

- Gate 4.5 de remise a niveau documentaire et strategique: ferme
- Gate 5 distracteurs v2: execute sans evolution de contrat export/schema

---

## 2. Statut des gates (etat reel)

| Gate | Statut | Date | Commentaire |
|---|---|---|---|
| Gate 0 - Migration PostgreSQL/PostGIS | DONE | 2026-04-09 | backend principal bascule Postgres |
| Gate 1 - Verrou doctrinal + ADR de chaine | DONE | 2026-04-09 | cadre documentaire stabilise |
| Gate 2 - Playable corpus vivant v1 | DONE | 2026-04-09 | surface playable v1 livree |
| Gate 3 - Pack + revisions + diagnostic | DONE | 2026-04-09 | pack.spec.v1 + pack.diagnostic.v1 |
| Gate 4 - Compilation + materialization | DONE | 2026-04-09 | pack.compiled.v1 + pack.materialization.v1 |
| Gate 4.5 - Correctif strategique pre-extension | DONE | 2026-04-09 | alignement doctrine/docs/garde-fous |
| Gate 5 - Politique distracteurs v2 | DONE | 2026-04-09 | similarites internes prioritaires + fallback deterministe |

Etat schema applicatif observe:

- database.schema.v11

Etat contrats observes:

- export.bundle.v4 (principal)
- export.bundle.v3 (sidecar transitoire opt-in)
- review.override.v1
- playable_corpus.v1
- pack.spec.v1
- pack.diagnostic.v1
- pack.compiled.v1
- pack.materialization.v1

## État réel

Le repo est operationnel jusqu'au Gate 5 avec:

- une surface playable latest reconstruite a chaque run
- un historique run-level conserve pour auditabilite
- des builds compiles conserves de maniere historique
- des materializations figees immuables

Le delta vers la cible finale est explicite; Gate 4.5 est clos et Gate 5 est execute.

## Cible

La cible d'evolution reste:

- un playable corpus cumulatif incremental reel
- des frontieres strictes entre database et runtime
- une trajectoire sequentielle avec Gate 6 enrichissement puis Gate 7 confusions batch
- une reduction de dette PostgresRepository planifiee sans lancer de refactor pendant Gate 5

---

## 3. Ecarts structurants confirmes

### E1 - Playable cible vs implementation

Constat:

- cible produit: corpus cumulatif incremental
- implementation actuelle: reset + reconstruction de la surface latest playable

Impact:

- risque de confusion doctrinale
- risque de dette structurelle si on enchaine les gates sans correction de trajectoire

Priorite:

- P0 strategique (avant l'ancien Gate 5)

### E2 - Concentration de responsabilites dans PostgresRepository

Constat:

- un seul composant concentre persistance, diagnostics, compilation, materialization, metriques

Impact:

- couplage fort
- ralentissement de l'evolution
- surface de regression elevee

Priorite:

- P0 strategique (design d'extraction minimale a cadrer avant implementation)

### E3 - Politique distracteurs v2 active, couverture a etendre

Constat:

- Gate 5 active une priorisation pedagogique: similarites internes d'abord, fallback deterministe ensuite
- le cadre reste strictement hors runtime/session/scoring

Impact:

- amelioration immediate de la qualite des distracteurs en compilation
- exploitation explicite des similar_taxon_ids deja resolus

Priorite:

- P1 continue (durcir les jeux de test et l'observabilite de fallback)

### E4 - Traceabilite historique a clarifier explicitement

Constat:

- les builds compiles historiques sont conserves
- les materializations sont figees
- la doc doit le rendre explicite et non ambigu

Impact:

- lisibilite operateur et gouvernance release

Priorite:

- P0 documentaire

---

## 4. Clarifications doctrinales actees (post-Gate 4)

1. Le playable final vise est cumulatif incremental.
2. L'etat courant est une surface latest reconstruite.
3. Cet ecart est reconnu explicitement et traite avant extension de chaine.
4. Les similarites externes alimentent le systeme, mais ne definissent jamais librement l'identite interne.
5. La promotion des similarites iNaturalist vers similar_taxon_ids internes est autorisee seulement sous controle:
- taxon cible interne deja present: promotion traceable possible
- taxon cible interne absent: pas de creation libre; toute creation reste gouvernee par la charte canonique
6. Les compiled builds historiques sont conserves avec trace de generation.
7. Les materializations figees sont immuables.

---

## 5. Remise a niveau strategique avant la suite

### Gate 4.5 - Correctif strategique pre-extension (clos)

Objectif:

- remettre a plat contexte, doctrine d'execution, et trajectoire technique avant nouveaux gates metier

Perimetre:

- clarification explicite du modele cible playable cumulatif incremental
- reconnaissance explicite de l'etat courant latest-surface
- clarification du statut historique compiled builds + immutabilite materializations
- cadrage de dette PostgresRepository comme chantier dedie
- cadrage du gate distracteurs v2 (sans implementation)

Hors perimetre:

- aucune implementation Gate 6+
- aucun refactor repository lance

Criteres d'acceptation:

- docs alignees entre elles et alignees sur le code reel
- sequence de gates reordonnee explicitement
- dettes majeures formulees en objectifs actionnables

---

## 6. Nouvelle sequence de gates retenue

1. Gate 0 - PostgreSQL/PostGIS (DONE)
2. Gate 1 - Verrou doctrinal (DONE)
3. Gate 2 - Playable v1 (DONE)
4. Gate 3 - Pack + diagnostic (DONE)
5. Gate 4 - Compilation + materialization (DONE)
6. Gate 4.5 - Correctif strategique pre-extension (documentation + trajectoire)
7. Gate 5 - Politique distracteurs v2 (dedie)
8. Gate 6 - Queue d'enrichissement
9. Gate 7 - Ingestion batch confusions + agregats globaux
10. Gate 8 - Inspection/KPI/smoke/CI etendus
11. Gate 9 - Retrait sidecar export v3

---

## 7. Arbitrages documentes

1. Clore Gate 4.5 avant d'ouvrir Gate 5.
Raison: playable cible, dette repository, et trajectoire distracteurs devaient etre clarifies avant implementation.

2. Garder la charte canonique v1 stable.
Raison: le probleme est d'alignement execution/trajectoire, pas de redefinition normative du canonique.

3. Distinguer cadrage et implementation.
Raison: Gate 4.5 a cadre sans lancer refactor; Gate 5 implemente uniquement la policy distracteurs.

4. Introduire un gate distracteurs v2 dedie.
Raison: la politique actuelle est valide techniquement mais trop faible pedagogiquement.

5. Maintenir discipline de frontieres.
Raison: pas de logique runtime/session/scoring/progression dans database.

---

## 8. Risques pour la suite

- R1: confusion persistante entre surface latest et cible cumulative tant que le modele cumulatif n'est pas livre
- R2: amplification de dette repository si Gate 6+ avance sans extraction preparee
- R3: distracteurs v2 trop ambitieuse et hors discipline canonique
- R4: derive de perimetre runtime dans les gates 5-7

Mitigations:

- conserver les garde-fous Gate 6+ dans la couche storage
- conserver des criteres d'acceptation courts et testables par gate
- lier chaque extension a ses frontieres explicites

---

## 9. KPI et verification

Les KPIs verrouilles restent inchanges dans ce cycle:

- exportable_unresolved_or_provisional
- governance_reason_and_signal_coverage
- export_trace_flags_uncertainty_coverage

Aucun changement de seuil KPI n'est acte dans cette remise documentaire.

---

## 10. Mode de mise a jour

Regles:

1. toute evolution structurante met a jour README.md et ce document
2. tout reordonnancement de gates met a jour aussi docs/codex_execution_plan.md
3. toute divergence doc/code est documentee comme ecart explicite

Template de mise a jour:

```text
date:
owner:
section_modifiee:
changement:
raison:
impact:
next_step:
```

---

## 11. Gate 4.5 closure checklist

Gate 4.5 is considered closed only when all items below are true:

- docs alignment complete across README, scope, domain model, pipeline, audit, and execution plan
- playable target vs current latest-surface gap is explicit and non-ambiguous
- gate sequence includes Gate 4.5 and dedicated Gate 5 distractor policy v2
- PostgresRepository debt is tracked as a strategic workstream without launched refactor
- compiled build history and materialization immutability are explicit in docs
- canonical boundary for external similar species hints is explicit and controlled
- no implementation markers for Gate 5+ were introduced during Gate 4.5

Evidence format for closure update:

```text
date:
owner:
checklist_items_passed:
tests_run:
residual_risks:
go_no_go:
```

## 12. Gate 5 closure evidence

date: 2026-04-09
owner: codex
checklist_items_passed:
- distractor selection prioritizes internal similar_taxon_ids when available
- iNaturalist similar species hints (external_similarity_hints) are used when they resolve to existing internal taxa
- deterministic fallback selects remaining taxa when similar pool is insufficient
- pedagogical ordering deprioritizes media_role=distractor_risk when alternatives exist
- exactly three unique distractor taxa remain enforced by compiled question contract
- no Gate 6+ storage markers introduced
tests_run:
- tests/test_storage.py::test_compile_pack_prefers_internal_similar_taxa_for_distractors
- tests/test_storage.py::test_compile_pack_falls_back_when_similar_taxa_are_insufficient
- tests/test_storage.py::test_compile_pack_prioritizes_non_distractor_risk_media_when_available
- tests/test_storage.py::test_compile_pack_uses_inat_similar_species_hints_for_distractors
- tests/test_storage.py::test_compile_pack_persists_validated_payload_and_is_deterministic
- tests/test_verify_repo.py
residual_risks:
- playable persistence model remains latest-surface and not cumulative incremental yet
- fallback observability remains inferred from payload selections (no new contract field added)
go_no_go: GO for Gate 5 closure, Gate 6 remains closed
