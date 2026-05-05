---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/taxon-localized-names-enrichment-sprint12.md
scope: audit
---

# Taxon Localized Names Enrichment — Sprint 12

## Purpose

Apply localized names (FR, NL, EN) to canonical taxa using the manual CSV `data/manual/taxon_common_names_i18n_sprint12.csv` populated from iNat and manual review.

---

## Results

| Metric | Value |
|---|---|
| Patches applied | 50 |
| FR names added | 50 |
| NL names added | 50 |
| EN names added | 0 |
| Candidates now FR-usable | 43 |
| Candidates still missing FR | 0 |
| Conflicts | 0 |
| Skipped rows | 0 |
| Unresolved rows | 0 |

---

## Safety Guarantees

- Existing names were never overwritten (conflicts reported instead).
- `accepted_scientific_name` and `canonical_taxon_id` were never mutated.
- No `CanonicalTaxon` records were created.
- Source and reviewer fields are preserved in the CSV for traceability.

---

## Next Step Recommendation

**Decision: `READY_FOR_DISTRACTOR_READINESS_RERUN`**

All candidate FR names resolved. Rerun distractor readiness.
