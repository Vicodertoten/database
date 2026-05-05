---
owner: vicodertoten
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/evidence/distractor_v1_current_state_audit.json
scope: distractor_relationships_v1_current_state_audit
---

# Distractor Relationships V1 — Current State Audit

## Purpose

Audit existing data to determine how much potential distractor coverage exists
before implementing harvest/persistence of `DistractorRelationship` records.

This audit does not persist any relationships.
It does not modify runtime, packs, or any existing artifact.

---

## Input Data

- **Snapshot**: `palier1-be-birds-50taxa-run003-v11-baseline`
- **Execution status**: `complete`
- **Run date**: 2026-05-05

---

## Current Coverage

| Metric | Count |
|---|---|
| Target taxa in snapshot | 50 |
| Active target taxa | 50 |
| Taxa with iNat similarity hints | 0 |
| Taxa with ≥3 iNat hints | 0 |
| Taxa with internal similar_taxa | 0 |
| Taxa with taxonomy profile | 0 |
| Taxa with ≥1 same-genus neighbor | 8 |
| Taxa with ≥1 same-family neighbor | 33 |
| Taxa with ≥3 total candidates | 26 |
| Taxa with no candidates | 3 |

---

## iNaturalist Hint Coverage

Total iNat similarity hints available: **0**

iNaturalist `similar_taxa` data is the first-priority source for distractor
candidates. These hints are populated during taxon enrichment from the iNat API.

**Current state**: No iNat similarity hints found in snapshot taxa.
These hints are fetched during the enrichment pipeline run.
The taxa files in the snapshot may predate the enrichment step.

---

## Taxonomic Fallback Coverage

Taxonomic neighbors are inferred from the ancestry chain within the snapshot.
They are the second and third priority sources (same genus → family → order).

| Source | Total candidates across all targets |
|---|---|
| Same genus | 8 |
| Same family (not same genus) | 66 |
| Same order (not same family) | 606 |

Taxa with ≥1 same-genus neighbor: **8/50**

---

## Referenced Taxon Shell Needs

Unresolved candidate taxa (no canonical or referenced taxon): **0**

Referenced taxon shells needed: **0**

Candidates that are not yet canonical taxa in this repository need
a `ReferencedTaxon` shell to be usable in compiled question options.

---

## Localization Gaps

Candidate taxa missing localized names (no canonical or referenced taxon entry): **0**

Localized names are required for displaying question options to learners.
Missing names must be resolved before a relationship can be `validated`.

---

## Diversity Fallback Risk

Taxa with no candidates at all: **3/50**

Per Sprint 11 Phase 1 policy, `emergency_diversity_fallback` relationships
**must not** be used for the first corpus candidate.
If a taxon has no real pedagogical distractor candidates, it must either be
enriched first (iNat hints + taxonomy profile) or excluded from playable corpus.

---

## Target Readiness Preview

| Readiness status | Count |
|---|---|
| `inat_missing_but_taxonomic_ok` | 26 |
| `insufficient_distractors` | 21 |
| `needs_taxon_enrichment` | 3 |

### Per-target details

| Scientific name | iNat | Genus | Family | Order | Total | Status |
|---|---|---|---|---|---|---|
| Accipiter nisus | 0 | 0 | 1 | 0 | 1 | `insufficient_distractors` |
| Acrocephalus scirpaceus | 0 | 0 | 0 | 25 | 25 | `inat_missing_but_taxonomic_ok` |
| Alauda arvensis | 0 | 0 | 0 | 25 | 25 | `inat_missing_but_taxonomic_ok` |
| Anas platyrhynchos | 0 | 0 | 2 | 0 | 2 | `insufficient_distractors` |
| Anser anser | 0 | 0 | 2 | 0 | 2 | `insufficient_distractors` |
| Apus apus | 0 | 0 | 0 | 0 | 0 | `needs_taxon_enrichment` |
| Ardea cinerea | 0 | 0 | 1 | 0 | 1 | `insufficient_distractors` |
| Asio otus | 0 | 0 | 2 | 0 | 2 | `insufficient_distractors` |
| Athene noctua | 0 | 0 | 2 | 0 | 2 | `insufficient_distractors` |
| Buteo buteo | 0 | 0 | 1 | 0 | 1 | `insufficient_distractors` |
| Carduelis carduelis | 0 | 0 | 3 | 22 | 25 | `inat_missing_but_taxonomic_ok` |
| Chloris chloris | 0 | 0 | 3 | 22 | 25 | `inat_missing_but_taxonomic_ok` |
| Coccothraustes coccothraustes | 0 | 0 | 3 | 22 | 25 | `inat_missing_but_taxonomic_ok` |
| Coloeus monedula | 0 | 0 | 4 | 21 | 25 | `inat_missing_but_taxonomic_ok` |
| Columba palumbus | 0 | 0 | 1 | 0 | 1 | `insufficient_distractors` |
| Corvus corone | 0 | 1 | 3 | 21 | 25 | `inat_missing_but_taxonomic_ok` |
| Corvus frugilegus | 0 | 1 | 3 | 21 | 25 | `inat_missing_but_taxonomic_ok` |
| Cyanistes caeruleus | 0 | 0 | 1 | 24 | 25 | `inat_missing_but_taxonomic_ok` |
| Cygnus olor | 0 | 0 | 2 | 0 | 2 | `insufficient_distractors` |
| Delichon urbicum | 0 | 0 | 2 | 23 | 25 | `inat_missing_but_taxonomic_ok` |
| Dendrocopos major | 0 | 0 | 2 | 0 | 2 | `insufficient_distractors` |
| Dryocopus martius | 0 | 0 | 2 | 0 | 2 | `insufficient_distractors` |
| Egretta garzetta | 0 | 0 | 1 | 0 | 1 | `insufficient_distractors` |
| Erithacus rubecula | 0 | 0 | 1 | 24 | 25 | `inat_missing_but_taxonomic_ok` |
| Falco peregrinus | 0 | 1 | 0 | 0 | 1 | `insufficient_distractors` |
| Falco tinnunculus | 0 | 1 | 0 | 0 | 1 | `insufficient_distractors` |
| Fringilla coelebs | 0 | 0 | 3 | 22 | 25 | `inat_missing_but_taxonomic_ok` |
| Fulica atra | 0 | 0 | 1 | 0 | 1 | `insufficient_distractors` |
| Gallinula chloropus | 0 | 0 | 1 | 0 | 1 | `insufficient_distractors` |
| Garrulus glandarius | 0 | 0 | 4 | 21 | 25 | `inat_missing_but_taxonomic_ok` |
| Hirundo rustica | 0 | 0 | 2 | 23 | 25 | `inat_missing_but_taxonomic_ok` |
| Lanius collurio | 0 | 0 | 0 | 25 | 25 | `inat_missing_but_taxonomic_ok` |
| Larus argentatus | 0 | 1 | 0 | 0 | 1 | `insufficient_distractors` |
| Larus michahellis | 0 | 1 | 0 | 0 | 1 | `insufficient_distractors` |
| Motacilla alba | 0 | 0 | 0 | 25 | 25 | `inat_missing_but_taxonomic_ok` |
| Parus major | 0 | 0 | 1 | 24 | 25 | `inat_missing_but_taxonomic_ok` |
| Passer domesticus | 0 | 0 | 0 | 25 | 25 | `inat_missing_but_taxonomic_ok` |
| Phalacrocorax carbo | 0 | 0 | 0 | 0 | 0 | `needs_taxon_enrichment` |
| Phoenicurus ochruros | 0 | 0 | 1 | 24 | 25 | `inat_missing_but_taxonomic_ok` |
| Pica pica | 0 | 0 | 4 | 21 | 25 | `inat_missing_but_taxonomic_ok` |
| Picus viridis | 0 | 0 | 2 | 0 | 2 | `insufficient_distractors` |
| Podiceps cristatus | 0 | 0 | 0 | 0 | 0 | `needs_taxon_enrichment` |
| Riparia riparia | 0 | 0 | 2 | 23 | 25 | `inat_missing_but_taxonomic_ok` |
| Streptopelia decaocto | 0 | 0 | 1 | 0 | 1 | `insufficient_distractors` |
| Strix aluco | 0 | 0 | 2 | 0 | 2 | `insufficient_distractors` |
| Sturnus vulgaris | 0 | 0 | 0 | 25 | 25 | `inat_missing_but_taxonomic_ok` |
| Sylvia atricapilla | 0 | 0 | 0 | 25 | 25 | `inat_missing_but_taxonomic_ok` |
| Troglodytes troglodytes | 0 | 0 | 0 | 25 | 25 | `inat_missing_but_taxonomic_ok` |
| Turdus merula | 0 | 1 | 0 | 24 | 25 | `inat_missing_but_taxonomic_ok` |
| Turdus philomelos | 0 | 1 | 0 | 24 | 25 | `inat_missing_but_taxonomic_ok` |

---

## Top Blockers

2. **0 iNat similarity hints** — enrichment pipeline has not yet populated external_similarity_hints for snapshot taxa.
3. **0 taxa with taxonomy profile** — authority_taxonomy_profile not yet populated in export bundle.

---

## Recommendation for Next Phase

**Decision: `NEEDS_TAXON_ENRICHMENT_BEFORE_DISTRACTORS`**

The snapshot taxa are not yet enriched with iNat similarity hints or
authority taxonomy profiles. Before Phase 3 candidate generation:

1. Re-run the enrichment pipeline on the target snapshot to populate
   `external_similarity_hints` from the iNat API.
2. Ensure `authority_taxonomy_profile` is populated for ancestry-based
   genus/family/order inference.
3. Create `ReferencedTaxon` shells for candidate taxa that are not yet
   canonicalized.
4. Re-run this audit to confirm readiness.

Taxonomy-based neighbors are already computable from ancestry chains.
**26/50 taxa** have ≥3 taxonomic candidates.
Taxonomy-based candidate generation can proceed without iNat hints,
but iNat hints should be the primary source.
