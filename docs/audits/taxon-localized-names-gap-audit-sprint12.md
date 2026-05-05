---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/taxon-localized-names-gap-audit-sprint12.md
scope: audit
---

# Taxon Localized Names Gap Audit — Sprint 12

## Purpose

Identify missing French, Dutch, and English localized names for target taxa and distractor candidate taxa. Determine which gaps can be resolved from iNaturalist, and which require manual CSV entry.

## Context

Sprint 11 showed 43 candidate taxa missing French names, resulting in 0/50 targets ready for the FR distractor gate. Phase C resolves this gap.

---

## Gap Summary

| Metric | Value |
|---|---|
| Target taxa | 50 |
| Targets missing FR | 50 |
| Targets missing NL | 50 |
| Targets missing EN | 0 |
| Candidate taxa | 43 |
| Candidates missing FR | 43 |
| Candidates missing NL | 43 |
| Candidates missing EN | 0 |
| FR resolvable from iNat | 43 |
| NL resolvable from iNat | 43 |
| Names requiring manual entry | 0 |
| Candidates FR-usable now | 0 |
| Candidates FR-usable after applying | 244 |

---

## Name Sources

Priority order:

1. Existing `common_names_by_language` in canonical records
2. iNaturalist `GET /v1/taxa/{id}?all_names=true` → `names[]` with locale/is_valid
3. Manual CSV: `data/manual/taxon_common_names_i18n_sprint12.csv`

---

## Next Step Recommendation

**Decision: `READY_FOR_DISTRACTOR_READINESS_RERUN`**

After applying names, 244 candidates will be FR-usable. Proceed to apply, then rerun readiness.

---

## Doctrine

- iNat names are source-side hints; they do not define canonical identity.
- `accepted_scientific_name` is never derived from vernacular names.
- Existing names are never silently overwritten; conflicts are reported.
- `similar_taxa` and `similar_taxon_ids` are not modified by this phase.
