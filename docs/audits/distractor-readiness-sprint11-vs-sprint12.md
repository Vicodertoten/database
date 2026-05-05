---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/distractor-readiness-sprint11-vs-sprint12.md
scope: audit
---

# Distractor Readiness Comparison: Sprint 11 vs Sprint 12

## Decision

**NEEDS_MORE_TAXON_NAME_ENRICHMENT**

Missing French names still dominate candidate coverage.

## Metric Comparison

| Metric | Sprint 11 | Sprint 12 | Delta |
|---|---:|---:|---:|
| iNat similar count | 0 | 323 | 323 |
| Total candidates | 244 | 407 | 163 |
| Targets ready | 0 | 39 | 39 |
| Targets blocked | 50 | 11 | -39 |
| Targets with >=3 candidates | 26 | 49 | 23 |
| Targets with >=3 FR-usable | 0 | 39 | 39 |
| Missing French names | 43 | 156 | 113 |
| Referenced shells needed | 0 | 0 | 0 |
| No candidates | 3 | 0 | -3 |
| Taxonomic-only dependency | 26 | 1 | -25 |
| Same-order dependency | 17 | 1 | -16 |

## Source Distribution

- Sprint 11:
  {"inaturalist_similar_species": 0, "taxonomic_neighbor_same_genus": 8, "taxonomic_neighbor_same_family": 66, "taxonomic_neighbor_same_order": 170}
- Sprint 12:
  {"inaturalist_similar_species": 323, "taxonomic_neighbor_same_genus": 8, "taxonomic_neighbor_same_family": 66, "taxonomic_neighbor_same_order": 10}

## Guardrail Check

- No emergency diversity fallback generated in Sprint 12: Yes
