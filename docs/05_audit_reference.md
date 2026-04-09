# Audit De Reference - database

Statut: document vivant (reference d'execution)
Version: v2
Date de mise a jour: 2026-04-09
Perimetre: etat reel du repo apres Gate 4

---

## 1. Synthese executive

Le repo est sur la bonne trajectoire et a livre une base operationnelle solide jusqu'au Gate 4.

Points forts confirmes:

- storage principal PostgreSQL/PostGIS en place, migrations versionnees
- pipeline reproductible avec artefacts versionnes
- gouvernance canonique v1 active et tracee
- couche playable v1 en base, inspectable via CLI
- couche pack v1, diagnostic v1, compilation v1, materialization v1
- couverture tests structurants et smoke KPI verrouilles

Point critique post-Gate 4:

- la cible finale playable est un corpus cumulatif incremental reel
- l'implementation actuelle reste une surface latest reconstruite a chaque run
- cet ecart est maintenant explicite et doit etre traite avant l'ancien Gate 5

Decision de pilotage:

- inserer un Gate 4.5 de remise a niveau documentaire et strategique
- introduire ensuite un gate dedie distracteurs v2 avant la queue d'enrichissement

---

## 2. Statut des gates (etat reel)

| Gate | Statut | Date | Commentaire |
|---|---|---|---|
| Gate 0 - Migration PostgreSQL/PostGIS | DONE | 2026-04-09 | backend principal bascule Postgres |
| Gate 1 - Verrou doctrinal + ADR de chaine | DONE | 2026-04-09 | cadre documentaire stabilise |
| Gate 2 - Playable corpus vivant v1 | DONE | 2026-04-09 | surface playable v1 livree |
| Gate 3 - Pack + revisions + diagnostic | DONE | 2026-04-09 | pack.spec.v1 + pack.diagnostic.v1 |
| Gate 4 - Compilation + materialization | DONE | 2026-04-09 | pack.compiled.v1 + pack.materialization.v1 |

Etat schema applicatif observe:

- database.schema.v11

Etat contrats observes:

- export.bundle.v4 (principal)
- export.bundle.v3 (sidecar transitoire opt-in)
- playable_corpus.v1
- pack.spec.v1
- pack.diagnostic.v1
- pack.compiled.v1
- pack.materialization.v1

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

### E3 - Politique distracteurs v1 pedagogiquement minimale

Constat:

- Gate 4 valide la forme technique (3 distracteurs taxons distincts)
- la qualite pedagogique des distracteurs reste limitee

Impact:

- limite de valeur didactique
- faible exploitation des similarites canoniques

Priorite:

- P1 immediate (gate dedie distracteurs v2)

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

### Gate 4.5 - Correctif strategique pre-extension

Objectif:

- remettre a plat contexte, doctrine d'execution, et trajectoire technique avant nouveaux gates metier

Perimetre:

- clarification explicite du modele cible playable cumulatif incremental
- reconnaissance explicite de l'etat courant latest-surface
- clarification du statut historique compiled builds + immutabilite materializations
- cadrage de dette PostgresRepository comme chantier dedie
- cadrage du gate distracteurs v2 (sans implementation)

Hors perimetre:

- aucune implementation Gate 5+
- aucune nouvelle logique metier
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

1. Ne pas ouvrir Gate 5 directement.
Raison: playable cible, dette repository, et trajectoire distracteurs doivent etre clarifies avant extension.

2. Garder la charte canonique v1 stable.
Raison: le probleme est d'alignement execution/trajectoire, pas de redefinition normative du canonique.

3. Distinguer cadrage et implementation.
Raison: Gate 4.5 cadre sans lancer refactor ni nouvelle feature metier.

4. Introduire un gate distracteurs v2 dedie.
Raison: la politique actuelle est valide techniquement mais trop faible pedagogiquement.

5. Maintenir discipline de frontieres.
Raison: pas de logique runtime/session/scoring/progression dans database.

---

## 8. Risques pour la suite

- R1: confusion persistante entre surface latest et cible cumulative si Gate 4.5 reste superficiel
- R2: amplification de dette repository si gates metier avancent sans extraction preparee
- R3: distracteurs v2 trop ambitieuse et hors discipline canonique
- R4: derive de perimetre runtime dans les gates 5-7

Mitigations:

- accepter Gate 4.5 uniquement si criteres documentaires sont strictement tenus
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
