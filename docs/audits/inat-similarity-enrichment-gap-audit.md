---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/inat-similarity-enrichment-gap-audit.md
scope: audit
---

# iNat Similarity Enrichment Gap Audit

## Purpose

Diagnose why all 50 target taxa have zero iNaturalist similar-species hints after Sprint 11 distractor candidate generation.

## Sprint 11 Blocker Recap

| Metric | Sprint 11 value |
|---|---|
| Target taxa | 50 |
| iNat similar-species hints | 0 |
| Candidates generated | 244 (all taxonomic) |
| Targets ready for first corpus gate | 0 |
| Final decision | `NEEDS_TAXON_ENRICHMENT_BEFORE_DISTRACTORS` |

---

## Inspected Sources

| Source | Path |
|---|---|
| Normalized taxa | `data/normalized/palier1_be_birds_50taxa_run003_v11_baseline.normalized.json` |
| Raw taxon payloads | `data/raw/inaturalist/palier1-be-birds-50taxa-run003-v11-baseline/taxa` |
| Snapshot manifest | `data/raw/inaturalist/palier1-be-birds-50taxa-run003-v11-baseline/manifest.json` |
| Enrichment source | `src/database_core/enrichment/taxa.py` |
| Harvest source | `src/database_core/adapters/inaturalist_harvest.py` |
| Test fixtures | `tests/fixtures/inaturalist_snapshot_smoke/taxa` |

---

## Findings by Level

### Level A — CanonicalTaxon

- **Total taxa**: 50
- **Taxa with any similarity hints**: 0
- **Taxa with iNat similarity hints**: 0
- **Taxa with resolved `similar_taxa`**: 0
- **Taxa with `similar_taxon_ids`**: 0
- **Enrichment status distribution**: `{'complete': 50}`

> All taxa enriched to completion but with empty similarity hints.

### Level B — Raw Cached Payloads

- **Taxon payload files found**: 50
- **Payloads with `similar_taxa`**: 0
- **Similarity-like keys found**: `{}`
- **API endpoint used**: `GET https://api.inaturalist.org/v1/taxa/{inat_id}`

Keys present in every raw payload result:

```
  ancestor_ids
  ancestors
  ancestry
  atlas_id
  children
  complete_rank
  complete_species_count
  conservation_status
  conservation_statuses
  current_synonymous_taxon_ids
  default_photo
  extinct
  flag_counts
  iconic_taxon_id
  iconic_taxon_name
  id
  is_active
  listed_taxa
  listed_taxa_count
  name
  observations_count
  parent_id
  photos_locked
  preferred_common_name
  provisional
  rank
  rank_level
  taxon_changes_count
  taxon_photos
  taxon_schemes_count
  vision
  wikipedia_summary
  wikipedia_url
```

> Raw payloads from GET /v1/taxa/{id} do not contain a `similar_taxa` field. The iNat taxon-detail endpoint does not expose visual similarity data. A separate endpoint is required: GET /v1/identifications/similar_species.

### Level C — Snapshot / Manifest

- **Snapshot ID**: `palier1-be-birds-50taxa-run003-v11-baseline`
- **Manifest version**: `inaturalist.snapshot.v3`
- **Enrichment version**: `None`
- **Total seeds**: 50
- **Seeds with taxon payload path**: 50
- **Payload files on disk**: 50

> Manifest has no enrichment_version field — snapshot was built before a multi-pass enrichment model was defined. All 50/50 taxon payload files exist on disk.

### Level D — Code Paths

- **Enrichment similarity functions**: `['_extract_similarity_hints', '_resolve_similarity_hints', '_merge_similarity_hints', '_merge_similar_taxa', '_coerce_similarity_relation_type']`
- **Enrichment reads key**: `raw_hints = record.get("similar_taxa") or []`
- **Harvest calls similar_species endpoint**: `False`
- **Test snapshot covers similar_taxa**: `True`
- **Test fixtures with similar_taxa populated**: `['taxon_birds_000009.json', 'taxon_birds_000014.json']`

> The enrichment function `_extract_similarity_hints` reads `record.get('similar_taxa')` from the taxon payload results[0]. Test fixtures confirm this works when the field is manually injected. The harvest adapter calls GET /v1/taxa/{id} which does NOT return `similar_taxa`. The harvest adapter does NOT call GET /v1/identifications/similar_species.

---

## Root Cause Classification

**`SIMILAR_HINTS_REQUIRE_API_REFRESH`**

Raw taxon payloads (from GET /v1/taxa/{id}) do not contain `similar_taxa`. The harvest adapter does not call GET /v1/identifications/similar_species. A separate enrichment pass using the similar_species endpoint is required.

### Evidence chain

1. All 50 raw taxon payload files were fetched via    `GET /v1/taxa/{id}` (iNat taxon-detail endpoint).
2. That endpoint does **not** include a `similar_taxa` field in its response.
3. The enrichment function `_extract_similarity_hints` reads    `record.get('similar_taxa')` from `results[0]` of the payload.
4. Since `similar_taxa` is absent, enrichment produces empty hints    and sets `source_enrichment_status = complete` (0 unresolved = complete).
5. Test fixtures (`tests/fixtures/inaturalist_snapshot_smoke/taxa/`)    manually inject `similar_taxa` — proving the extraction code is correct.
6. iNat exposes visual similarity via a separate endpoint:    `GET /v1/identifications/similar_species?taxon_id={id}&place_id=7008`.
7. The harvest adapter never calls this endpoint.

---

## Recommended Phase B Path

**Decision: `READY_FOR_INAT_TAXON_REFRESH`**

Implement `scripts/fetch_inat_similar_species_v1.py`:

```
GET https://api.inaturalist.org/v1/identifications/similar_species?taxon_id={inat_id}&place_id=7008
```

Steps:

1. Load all 50 `(canonical_taxon_id, inat_id)` pairs from the normalized JSON.
2. For each, call `GET /v1/identifications/similar_species?taxon_id={inat_id}&place_id=7008`.
3. Parse results: each result has `{taxon: {...}, count: N}`.
4. Write enrichment JSON to    `data/enriched/{snapshot_id}.similar_species_v1.json`.
5. Re-run `generate_distractor_relationship_candidates_v1.py`    with `--enrichment-json`.
6. Re-run `build_distractor_readiness_v1.py` and compare Sprint 11 vs Sprint 12.

Rate-limit: 1 request/second. 50 requests total ≈ 50 seconds.
Cache: re-run skips taxa whose enrichment already exists on disk.

---

## Risks

| Risk | Mitigation |
|---|---|
| `similar_species` results are globally scoped, not Belgium-specific | Use `place_id=7008` parameter to filter to Belgian observations |
| Some similar species may not be in the canonical corpus | Phase D creates referenced taxon shells for out-of-corpus candidates |
| iNat API rate limits | 1 req/s polite rate, 50 requests total |
| `similar_species` results may include non-species ranks | Filter to `rank=species` in Phase B script |

---

## Final Decision

**`READY_FOR_INAT_TAXON_REFRESH`**

No data was mutated. No runtime or pack changes were made.
Snapshot `palier1-be-birds-50taxa-run003-v11-baseline` was not modified.
