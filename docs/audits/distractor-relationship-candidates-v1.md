---
owner: vicodertoten
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/evidence/distractor_relationship_candidates_v1.json
scope: distractor_relationship_candidates_v1
---

# Distractor Relationship Candidates V1

## Purpose

Generate candidate `DistractorRelationship` artifacts from iNaturalist similar-species hints and taxonomic neighbors.

This report does not persist any relationships to the database.
It does not modify packs, runtime, or any existing artifact.
Regional filtering is not applied — candidates may be outside the target region.

---

## Inputs

- Snapshot: `palier1-be-birds-50taxa-run003-v11-baseline`
- Max taxonomic neighbors per target: 10
- Include same-order fallback: True
- Ready threshold: 3 candidates

---

## Decision

**INSUFFICIENT_DISTRACTOR_COVERAGE**

---

## Source Distribution

| Source | Relationships |
|---|---|
| iNaturalist similar species | 0 |
| Taxonomic neighbor — same genus | 8 |
| Taxonomic neighbor — same family | 66 |
| Taxonomic neighbor — same order | 170 |
| **Total** | **244** |

---

## Readiness Metrics

| Metric | Count |
|---|---|
| Target taxa | 50 |
| Targets with ≥3 candidates | 26 |
| Targets with ≥3 usable FR candidates | 0 |
| Targets with only taxonomic candidates | 26 |
| Targets with insufficient candidates | 21 |
| Targets with no candidates | 3 |

---

## Unresolved and Referenced Taxon Needs

- Unresolved candidates (no canonical or referenced taxon record): **0**
- Referenced taxon shells needed: **0**
- Candidates missing French name: **43**

---

## Targets Not Ready

- Columba palumbus
- Anas platyrhynchos
- Anser anser
- Cygnus olor
- Fulica atra
- Gallinula chloropus
- Larus michahellis
- Larus argentatus
- Phalacrocorax carbo
- Ardea cinerea
- Egretta garzetta
- Buteo buteo
- Accipiter nisus
- Falco tinnunculus
- Falco peregrinus
- Strix aluco
- Asio otus
- Athene noctua
- Picus viridis
- Dendrocopos major
- … and 4 more

---

## Per-Target Summary (first 20)

| Target | iNat | Genus | Family | Order | Total | FR-usable | Readiness |
|---|---|---|---|---|---|---|---|
| Columba palumbus | 0 | 0 | 1 | 0 | 1 | 0 | insufficient_distractors |
| Corvus corone | 0 | 1 | 3 | 0 | 4 | 0 | ready |
| Cyanistes caeruleus | 0 | 0 | 1 | 10 | 11 | 0 | ready |
| Erithacus rubecula | 0 | 0 | 1 | 10 | 11 | 0 | ready |
| Fringilla coelebs | 0 | 0 | 3 | 0 | 3 | 0 | ready |
| Garrulus glandarius | 0 | 0 | 4 | 0 | 4 | 0 | ready |
| Motacilla alba | 0 | 0 | 0 | 10 | 10 | 0 | ready |
| Parus major | 0 | 0 | 1 | 10 | 11 | 0 | ready |
| Passer domesticus | 0 | 0 | 0 | 10 | 10 | 0 | ready |
| Pica pica | 0 | 0 | 4 | 0 | 4 | 0 | ready |
| Sturnus vulgaris | 0 | 0 | 0 | 10 | 10 | 0 | ready |
| Sylvia atricapilla | 0 | 0 | 0 | 10 | 10 | 0 | ready |
| Troglodytes troglodytes | 0 | 0 | 0 | 10 | 10 | 0 | ready |
| Turdus merula | 0 | 1 | 0 | 10 | 11 | 0 | ready |
| Turdus philomelos | 0 | 1 | 0 | 10 | 11 | 0 | ready |
| Carduelis carduelis | 0 | 0 | 3 | 0 | 3 | 0 | ready |
| Chloris chloris | 0 | 0 | 3 | 0 | 3 | 0 | ready |
| Acrocephalus scirpaceus | 0 | 0 | 0 | 10 | 10 | 0 | ready |
| Coccothraustes coccothraustes | 0 | 0 | 3 | 0 | 3 | 0 | ready |
| Phoenicurus ochruros | 0 | 0 | 1 | 10 | 11 | 0 | ready |
| … (30 more) | | | | | | | |

---

## Recommendation for Next Phase

Distractor coverage is insufficient.
Review targets not ready and address individually.

---

*Generated: 2026-05-05 | snapshot: palier1-be-birds-50taxa-run003-v11-baseline | status: complete*
