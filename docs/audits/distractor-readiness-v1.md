---
owner: vicodertoten
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/evidence/distractor_readiness_v1.json
scope: distractor_readiness_v1
---

# Distractor Readiness V1

## Purpose

Synthesis of Sprint 11 distractor relationship work.
Combines the current-state audit and candidate generation results into
a per-target readiness assessment for the first corpus distractor gate.

This report does not persist any relationships, modify runtime, packs, or run AI.

---

## Inputs

- `docs/audits/evidence/distractor_v1_current_state_audit.json`
- `docs/audits/evidence/distractor_relationship_candidates_v1.json`
- Snapshot: `palier1-be-birds-50taxa-run003-v11-baseline`

---

## Decision

**NEEDS_TAXON_ENRICHMENT_BEFORE_DISTRACTORS**

Audit input decision: `NEEDS_TAXON_ENRICHMENT_BEFORE_DISTRACTORS`
Candidates input decision: `INSUFFICIENT_DISTRACTOR_COVERAGE`

---

## Target Readiness Summary

| Readiness status | Count |
|---|---|
| ready_for_first_corpus_distractor_gate | 0 |
| missing_localized_names | 18 |
| ready_with_taxonomic_fallback | 8 |
| needs_inat_enrichment | 21 |
| insufficient_distractors | 0 |
| needs_referenced_taxon_shells | 0 |
| no_candidates | 3 |
| needs_review | 0 |
| **Total** | **50** |

---

## Source Coverage

Total candidate relationships: **244**

| Source | Relationships |
|---|---|
| iNaturalist similar species | 0 |
| Taxonomic neighbor — same genus | 8 |
| Taxonomic neighbor — same family | 66 |
| Taxonomic neighbor — same order | 170 |

---

## iNaturalist Coverage

iNaturalist similar-species hints: **0**

No iNat similar-species hints have been populated yet. All existing candidates come from taxonomic neighbors.

The iNat enrichment pass must be triggered to unlock higher-quality candidates.

---

## Taxonomic Fallback Coverage

- Targets with ≥3 candidates (taxonomic only): 8
- Targets with insufficient taxonomic candidates: 21
- Targets with no candidates at all: 3

---

## Unresolved / Reference Shell Needs

- Unresolved candidates (no canonical or referenced record): **0**
- Referenced taxon shells needed: **0**

---

## Localization Gaps

- Candidates missing French name: **43**
- Targets missing localized names (blocking FR readiness): **18**

French name is the minimum label requirement for the first Belgian/francophone corpus.

---

## First Corpus Implications

- **0** target(s) are ready for the first corpus distractor gate.
- **50** target(s) are blocked.

Primary blockers:
1. **No iNaturalist similar-species hints** — highest priority gap.
2. **43 candidates missing French names** — blocks FR corpus usability.
3. **3 targets with no candidates at all** — may need AI proposal.

---

## Recommended Next Sprint

**Sprint 12 Option A — Referenced taxon harvest + iNat enrichment.**

Trigger iNaturalist similar-species enrichment for all 50 targets.
Re-run candidate generation after enrichment.
If referenced taxon shells are needed, harvest them first.

---

## Per-Target Readiness (first 20)

| Target | iNat | Genus | Family | Order | Total | FR-usable | Status |
|---|---|---|---|---|---|---|---|
| Columba palumbus | 0 | 1 | — | — | 1 | 0 | needs_inat_enrichment |
| Corvus corone | 0 | 4 | — | — | 4 | 0 | missing_localized_names |
| Cyanistes caeruleus | 0 | 11 | — | — | 11 | 0 | missing_localized_names |
| Erithacus rubecula | 0 | 11 | — | — | 11 | 0 | missing_localized_names |
| Fringilla coelebs | 0 | 3 | — | — | 3 | 0 | missing_localized_names |
| Garrulus glandarius | 0 | 4 | — | — | 4 | 0 | missing_localized_names |
| Motacilla alba | 0 | 10 | — | — | 10 | 0 | ready_with_taxonomic_fallback |
| Parus major | 0 | 11 | — | — | 11 | 0 | missing_localized_names |
| Passer domesticus | 0 | 10 | — | — | 10 | 0 | ready_with_taxonomic_fallback |
| Pica pica | 0 | 4 | — | — | 4 | 0 | missing_localized_names |
| Sturnus vulgaris | 0 | 10 | — | — | 10 | 0 | ready_with_taxonomic_fallback |
| Sylvia atricapilla | 0 | 10 | — | — | 10 | 0 | ready_with_taxonomic_fallback |
| Troglodytes troglodytes | 0 | 10 | — | — | 10 | 0 | ready_with_taxonomic_fallback |
| Turdus merula | 0 | 11 | — | — | 11 | 0 | missing_localized_names |
| Turdus philomelos | 0 | 11 | — | — | 11 | 0 | missing_localized_names |
| Carduelis carduelis | 0 | 3 | — | — | 3 | 0 | missing_localized_names |
| Chloris chloris | 0 | 3 | — | — | 3 | 0 | missing_localized_names |
| Acrocephalus scirpaceus | 0 | 10 | — | — | 10 | 0 | ready_with_taxonomic_fallback |
| Coccothraustes coccothraustes | 0 | 3 | — | — | 3 | 0 | missing_localized_names |
| Phoenicurus ochruros | 0 | 11 | — | — | 11 | 0 | missing_localized_names |
| … (30 more) | | | | | | | |

---

*Generated: 2026-05-05 | snapshot: palier1-be-birds-50taxa-run003-v11-baseline*
