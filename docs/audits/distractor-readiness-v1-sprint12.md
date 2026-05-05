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

**INSUFFICIENT_DISTRACTOR_COVERAGE**

Audit input decision: `NEEDS_TAXON_ENRICHMENT_BEFORE_DISTRACTORS`
Candidates input decision: `READY_FOR_AI_RANKING_DESIGN`

---

## Target Readiness Summary

| Readiness status | Count |
|---|---|
| ready_for_first_corpus_distractor_gate | 39 |
| missing_localized_names | 10 |
| ready_with_taxonomic_fallback | 0 |
| needs_inat_enrichment | 0 |
| insufficient_distractors | 1 |
| needs_referenced_taxon_shells | 0 |
| no_candidates | 0 |
| needs_review | 0 |
| **Total** | **50** |

---

## Source Coverage

Total candidate relationships: **407**

| Source | Relationships |
|---|---|
| iNaturalist similar species | 323 |
| Taxonomic neighbor — same genus | 8 |
| Taxonomic neighbor — same family | 66 |
| Taxonomic neighbor — same order | 10 |

---

## iNaturalist Coverage

iNaturalist similar-species hints: **323**

323 iNat hints available.

The iNat enrichment pass must be triggered to unlock higher-quality candidates.

---

## Taxonomic Fallback Coverage

- Targets with ≥3 candidates (taxonomic only): 39
- Targets with insufficient taxonomic candidates: 1
- Targets with no candidates at all: 0

---

## Unresolved / Reference Shell Needs

- Unresolved candidates (no canonical or referenced record): **0**
- Referenced taxon shells needed: **0**

---

## Localization Gaps

- Candidates missing French name: **156**
- Targets missing localized names (blocking FR readiness): **10**

French name is the minimum label requirement for the first Belgian/francophone corpus.

---

## First Corpus Implications

- **39** target(s) are ready for the first corpus distractor gate.
- **11** target(s) are blocked.

Primary blockers:
2. **156 candidates missing French names — blocks FR corpus usability.

---

## Recommended Next Sprint

**Sprint 12 Option B — AI ranking/proposals dry-run.**

Run AI pedagogical proposal dry-run against targets with insufficient candidates.
Validate AI outputs against the schema before any promotion.

---

## Per-Target Readiness (first 20)

| Target | iNat | Genus | Family | Order | Total | FR-usable | Status |
|---|---|---|---|---|---|---|---|
| Columba palumbus | 8 | 1 | — | — | 9 | 4 | ready_for_first_corpus_distractor_gate |
| Corvus corone | 7 | 4 | — | — | 11 | 8 | ready_for_first_corpus_distractor_gate |
| Cyanistes caeruleus | 6 | 1 | — | — | 7 | 3 | ready_for_first_corpus_distractor_gate |
| Erithacus rubecula | 14 | 1 | — | — | 15 | 7 | ready_for_first_corpus_distractor_gate |
| Fringilla coelebs | 12 | 3 | — | — | 15 | 9 | ready_for_first_corpus_distractor_gate |
| Garrulus glandarius | 2 | 4 | — | — | 6 | 5 | ready_for_first_corpus_distractor_gate |
| Motacilla alba | 6 | 0 | — | — | 6 | 0 | missing_localized_names |
| Parus major | 11 | 1 | — | — | 12 | 5 | ready_for_first_corpus_distractor_gate |
| Passer domesticus | 13 | 0 | — | — | 13 | 9 | ready_for_first_corpus_distractor_gate |
| Pica pica | 5 | 4 | — | — | 9 | 6 | ready_for_first_corpus_distractor_gate |
| Sturnus vulgaris | 13 | 0 | — | — | 13 | 4 | ready_for_first_corpus_distractor_gate |
| Sylvia atricapilla | 7 | 0 | — | — | 7 | 3 | ready_for_first_corpus_distractor_gate |
| Troglodytes troglodytes | 5 | 0 | — | — | 5 | 3 | ready_for_first_corpus_distractor_gate |
| Turdus merula | 14 | 1 | — | — | 15 | 9 | ready_for_first_corpus_distractor_gate |
| Turdus philomelos | 8 | 1 | — | — | 9 | 4 | ready_for_first_corpus_distractor_gate |
| Carduelis carduelis | 4 | 3 | — | — | 7 | 5 | ready_for_first_corpus_distractor_gate |
| Chloris chloris | 5 | 3 | — | — | 8 | 5 | ready_for_first_corpus_distractor_gate |
| Acrocephalus scirpaceus | 5 | 0 | — | — | 5 | 0 | missing_localized_names |
| Coccothraustes coccothraustes | 0 | 3 | — | — | 3 | 3 | ready_for_first_corpus_distractor_gate |
| Phoenicurus ochruros | 2 | 1 | — | — | 3 | 2 | missing_localized_names |
| … (30 more) | | | | | | | |

---

*Generated: 2026-05-05 | snapshot: palier1-be-birds-50taxa-run003-v11-baseline*
