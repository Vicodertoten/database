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

**READY_FOR_AI_RANKING_DESIGN**

---

## Source Distribution

| Source | Relationships |
|---|---|
| iNaturalist similar species | 323 |
| Taxonomic — same genus | 8 |
| Taxonomic — same family | 66 |
| Taxonomic — same order | 10 |
| **Total** | **407** |

---

## Readiness Metrics

| Metric | Count |
|---|---|
| Target taxa | 50 |
| Targets with ≥3 candidates | 49 |
| Targets with ≥3 usable FR candidates | 39 |
| Targets with only taxonomic candidates | 1 |
| Targets with insufficient candidates | 1 |
| Targets with no candidates | 0 |

---

## Unresolved and Referenced Taxon Needs

- Unresolved candidates (no canonical or referenced taxon record): **0**
- Referenced taxon shells needed: **0**
- Referenced taxon shell candidates (Phase D): **156**
- Candidates missing French name: **156**
- Emergency diversity fallback generated: **No**

---

## Targets Not Ready

- Apus apus

---

## Per-Target Summary (first 20)

| Target | iNat | Genus | Family | Order | Total | FR-usable | Readiness |
|---|---|---|---|---|---|---|---|
| Columba palumbus | 8 | 0 | 1 | 0 | 9 | 4 | ready |
| Corvus corone | 7 | 1 | 3 | 0 | 11 | 8 | ready |
| Cyanistes caeruleus | 6 | 0 | 1 | 0 | 7 | 3 | ready |
| Erithacus rubecula | 14 | 0 | 1 | 0 | 15 | 7 | ready |
| Fringilla coelebs | 12 | 0 | 3 | 0 | 15 | 9 | ready |
| Garrulus glandarius | 2 | 0 | 4 | 0 | 6 | 5 | ready |
| Motacilla alba | 6 | 0 | 0 | 0 | 6 | 0 | ready |
| Parus major | 11 | 0 | 1 | 0 | 12 | 5 | ready |
| Passer domesticus | 13 | 0 | 0 | 0 | 13 | 9 | ready |
| Pica pica | 5 | 0 | 4 | 0 | 9 | 6 | ready |
| Sturnus vulgaris | 13 | 0 | 0 | 0 | 13 | 4 | ready |
| Sylvia atricapilla | 7 | 0 | 0 | 0 | 7 | 3 | ready |
| Troglodytes troglodytes | 5 | 0 | 0 | 0 | 5 | 3 | ready |
| Turdus merula | 14 | 1 | 0 | 0 | 15 | 9 | ready |
| Turdus philomelos | 8 | 1 | 0 | 0 | 9 | 4 | ready |
| Carduelis carduelis | 4 | 0 | 3 | 0 | 7 | 5 | ready |
| Chloris chloris | 5 | 0 | 3 | 0 | 8 | 5 | ready |
| Acrocephalus scirpaceus | 5 | 0 | 0 | 0 | 5 | 0 | ready |
| Coccothraustes coccothraustes | 0 | 0 | 3 | 0 | 3 | 3 | ready |
| Phoenicurus ochruros | 2 | 0 | 1 | 0 | 3 | 2 | ready |
| … (30 more) | | | | | | | |

---

## Recommendation for Next Phase

The candidate set is sufficient to proceed with AI ranking design.
Next: design AI pedagogical ranking pass over existing candidates.

---

*Generated: 2026-05-05 | snapshot: palier1-be-birds-50taxa-run003-v11-baseline | status: complete*
