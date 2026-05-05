---
owner: database
status: in_progress
last_reviewed: 2026-05-05
source_of_truth: docs/runbooks/distractor-enrichment-sprint12.md
scope: runbook
---

# Distractor Enrichment — Sprint 12

## Objective

Unblock the distractor pipeline by enriching the 50 target taxa with:

1. iNaturalist similar-species hints (Phase B)
2. Localized names fr/en/nl (Phase C)
3. Referenced taxon shells for out-of-corpus similar species (Phase D)

Then re-run readiness synthesis to verify gate unlock (Phase E), and take the
persistence decision (Phase F).

---

## Phase A — Similar-species gap audit (diagnosis)

### Root cause

The current snapshot (`palier1-be-birds-50taxa-run003-v11-baseline`) was built
using `GET /v1/taxa/{id}` — the iNat taxon-detail endpoint. That endpoint **does
not include a `similar_taxa` field** in its response. The `similar_taxa` key is
absent from all 50 raw taxon files.

The `ExternalSimilarityHint` model and `_extract_similarity_hints()` in
`src/database_core/enrichment/taxa.py` correctly read from a `similar_taxa` key
in the raw record — but the raw data was never populated with it.

### Correct iNat endpoint

iNaturalist exposes visually similar species via:

```
GET https://api.inaturalist.org/v1/identifications/similar_species
  ?taxon_id={inat_id}
  &place_id=7008       # Belgium
```

Response format (per result):
```json
{ "taxon": { "id": ..., "name": "...", "preferred_common_name": "...", "rank": "species", ... }, "count": N }
```

- `count` = number of co-observations / identifications where both taxa appeared
  in the same session. Higher = more likely to be confused.
- `place_id=7008` scopes results to Belgium (confirmed: place 7008 = Belgium).

### Gap evidence

| Metric | Value |
|---|---|
| Taxa with `external_similarity_hints` | 0 / 50 |
| Taxa with `similar_taxa` | 0 / 50 |
| Total candidates generated (Sprint 11) | 244 |
| iNaturalist candidates | 0 |
| All candidates are taxonomic (genus/family/order) | 100% |

### Constraints

- The `/v1/identifications/similar_species` endpoint does not require authentication.
- The `names` field (all localized names including `fr`/`nl`) is only returned on
  `/v1/taxa/{id}?all_names=true`, **not** on the similar_species endpoint.
- A separate per-candidate name fetch is therefore needed for Phase C.

---

## Phase B — iNat similar_species enrichment

### Script

`scripts/fetch_inat_similar_species_v1.py`

### Logic

1. Load normalized JSON (`data/normalized/*.normalized.json`) to extract all
   `(canonical_taxon_id, inat_id)` pairs.
2. For each target taxon, call
   `GET /v1/identifications/similar_species?taxon_id={inat_id}&place_id=7008`.
3. Parse results into `ExternalSimilarityHint` records.
4. Write a snapshot-scoped enrichment output:
   `data/enriched/palier1_be_birds_50taxa_run003_v11_baseline.similar_species_v1.json`

### Output schema (per taxon)

```json
{
  "canonical_taxon_id": "taxon:birds:000001",
  "scientific_name": "Columba palumbus",
  "inat_id": "3048",
  "similar_species": [
    {
      "inat_id": "3017",
      "scientific_name": "Columba livia",
      "preferred_common_name_en": "Rock Pigeon",
      "count": 11,
      "rank": "species"
    }
  ],
  "fetch_status": "ok" | "empty" | "error",
  "fetched_at": "<ISO-8601>"
}
```

### Rate-limit / politeness

- 1 request per second (50 requests total).
- User-Agent: `BioLearnDatabaseBot/1.0`.
- Cached: re-running the script skips taxa whose output already exists.

---

## Phase C — Localized names enrichment

### Script

`scripts/fetch_localized_names_v1.py`

### Logic

1. Read the similar_species enrichment output from Phase B.
2. Collect the union of all candidate `inat_id`s across all targets.
3. Deduplicate — each unique iNat ID is fetched once.
4. For each candidate iNat ID, call
   `GET /v1/taxa/{inat_id}?all_names=true`.
5. Extract `fr`, `nl`, and `en` names from the `names` array.
6. Write:
   `data/enriched/palier1_be_birds_50taxa_run003_v11_baseline.localized_names_v1.json`

### Output schema

```json
{
  "inat_id": "3017",
  "scientific_name": "Columba livia",
  "names_fr": ["Pigeon biset"],
  "names_nl": ["Rotsduif"],
  "names_en": ["Rock Pigeon"],
  "fetch_status": "ok" | "empty" | "error",
  "fetched_at": "<ISO-8601>"
}
```

### Decision rule

A candidate is FR-usable if `names_fr` is non-empty.

---

## Phase D — Referenced taxon shell prep

### Script

`scripts/prepare_referenced_taxon_shells_v1.py`

### Logic

1. Read Phase B similar_species output.
2. Read the export bundle to identify which candidate iNat IDs are already
   in the canonical corpus (have a `canonical_taxon_id`).
3. For candidates **not** in the corpus, create shell records:
   ```json
   {
     "inat_id": "...",
     "scientific_name": "...",
     "shell_status": "proposed",
     "reason": "similar_species_candidate",
     "canonical_taxon_id": null
   }
   ```
4. Write:
   `data/enriched/palier1_be_birds_50taxa_run003_v11_baseline.referenced_shells_v1.json`

### Note

Phase D **does not persist** any new canonical taxa. It produces a proposal list
for human review. Actual canonical creation follows canonical governance rules.

---

## Phase E — Re-run candidates and readiness

### Steps

1. Re-run `generate_distractor_relationship_candidates_v1.py` with the
   Phase B+C enrichment outputs injected (via `--enrichment-json`).
2. Re-run `build_distractor_readiness_v1.py` on the new candidate set.
3. Write Sprint 12 evidence files:
   - `docs/audits/evidence/distractor_relationship_candidates_v2.json`
   - `docs/audits/evidence/distractor_readiness_v2.json`
4. Compare Sprint 11 vs Sprint 12:
   - iNat candidates: 0 → ?
   - FR-usable candidates: 0 → ?
   - Targets ready: 0 → ?

### Target gate criterion (unchanged)

A target is `ready_for_first_corpus_distractor_gate` iff:
- ≥3 FR-usable candidates
- At least one from a strong source (`inaturalist_similar_species`,
  `taxonomic_neighbor_same_genus`, or `taxonomic_neighbor_same_family`)
- No unresolved-only block

---

## Phase F — Persistence decision

### Decision criteria

Persist `DistractorRelationship` records if and only if:

1. **Data quality gate**: ≥20 of 50 targets are `ready_for_first_corpus_distractor_gate`
   OR ≥40 of 50 are at least `ready_with_taxonomic_fallback`.
2. **Name completeness gate**: All persisted candidates have `names_fr` non-empty.
3. **Source gate**: At least 50% of persisted candidates come from a strong source.

If gate passes: run `persist_distractor_relationships_v1.py` (Phase F script).

If gate fails: document the residual gap and plan Sprint 13 (AI proposal pass
or manual name entry before persistence).

### Scope boundary

Persistence is **owner-side only** (`database` repo).

- Writes to `distractor_relationships` table in the owner Postgres.
- Does **not** modify the export bundle or any runtime-facing surface.
- Runtime consumers must not read `distractor_relationships` directly.
- The serving contract for distractors (pack compilation) reads from
  `pack_store._fetch_inat_similar_taxa_by_target` — that path is unchanged.

---

## Success Criteria

| Criterion | Phase | Status |
|---|---|---|
| Root cause of similar=0 documented | A | ✓ |
| `fetch_inat_similar_species_v1.py` written and run | B | pending |
| `fetch_localized_names_v1.py` written and run | C | pending |
| `prepare_referenced_taxon_shells_v1.py` written and run | D | pending |
| Sprint 12 readiness JSON generated | E | pending |
| Sprint 11 vs Sprint 12 delta documented | E | pending |
| Persistence decision made | F | pending |
| All scripts ruff-clean | — | pending |
| All new tests pass | — | pending |

---

## Open Questions

1. Should `place_id=7008` be configurable, or hard-coded for the Belgian-birds scope?
   → Hard-coded for Sprint 12; parameterize in Sprint 13 if needed.

2. For candidates already in the canonical corpus (e.g. `Streptopelia decaocto`
   appears in both the corpus and as similar species of `Columba palumbus`):
   should the `candidate_taxon_ref_type` be promoted from `taxonomic_neighbor` to
   `inaturalist_similar_species`? → Yes; iNat source takes priority over taxonomic fallback.

3. Rate-limit mitigation: 50 taxa × 1 req (Phase B) + ~40 candidates × 1 req (Phase C)
   ≈ 90 requests at 1 req/s ≈ 90 seconds total. Acceptable.
