---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/inat-similarity-enrichment-sprint12.md
scope: audit
---

# iNat Similarity Enrichment — Sprint 12

## Purpose

Populate `external_similarity_hints` for all 50 target taxa using the iNaturalist `GET /v1/identifications/similar_species` endpoint (Phase B).

## Phase A Root Cause

**`SIMILAR_HINTS_REQUIRE_API_REFRESH`** — The snapshot was built using `GET /v1/taxa/{id}` which does not include `similar_taxa`. A dedicated similar-species endpoint is required.

## Chosen Enrichment Mode

**`live_api_fetch_with_cache`**

Endpoint: `GET https://api.inaturalist.org/v1/identifications/similar_species?taxon_id={{inat_id}}&place_id=7008`

Cache: `data/enriched/{snapshot_id}/similar_species/{canonical_taxon_id}.json`

Rate-limit: 1 request/second. Cached results re-used on repeat runs.

---

## Results

| Metric | Value |
|---|---|
| Snapshot | `palier1-be-birds-50taxa-run003-v11-baseline` |
| Targets attempted | 50 |
| Targets enriched | 49 |
| Total similarity hints | 323 |
| Hints with scientific name | 323 |
| Hints with common name | 323 |
| Hints mapped to canonical | 119 |
| Hints unmapped (out-of-corpus) | 204 |
| Payloads fetched live | 50 |
| Payloads loaded from cache | 0 |
| Errors | 0 |
| Skipped taxa | 0 |

Fetch status distribution:

- `ok`: 49
- `empty`: 1

---

## Cache Behavior

Each fetched response is written to:
```
data/enriched/palier1-be-birds-50taxa-run003-v11-baseline/similar_species/<canonical_taxon_id>.json
```
Re-running the script reads from cache and does not re-fetch.

---

## Doctrine: No Canonical Identity Mutation

- `ExternalSimilarityHint` records are source-side only.
- No `CanonicalTaxon` records are created for unresolved hints.
- `similar_taxa` and `similar_taxon_ids` are populated only by   the governed enrichment pipeline when canonical mapping is resolved.
- `accepted_scientific_name`, `canonical_taxon_id`, and   `external_source_mappings` are never mutated.

---

## Limitations

- `place_id=7008` (Belgium) scopes co-identification counts to Belgian   observations. Some globally common confusion species may be absent.
- Out-of-corpus similar species (unmapped hints) require Phase D   (referenced taxon shell prep) before use in distractor candidate generation.
- `similar_species` endpoint does not return localized names (fr/nl).   Phase C handles localized name enrichment via `GET /v1/taxa/{id}?all_names=true`.

---

## Next Phase Recommendation

**Decision: `NEEDS_REFERENCED_TAXON_SHELL_PREP`**

204 out-of-corpus hints found. Run Phase D (referenced taxon shell prep) before re-running distractor candidate generation.

Parallel path: Run Phase C (localized names enrichment) for the already-mapped canonical candidates.
