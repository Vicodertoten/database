---
owner: database
status: in_progress
last_reviewed: 2026-05-02
source_of_truth: docs/runbooks/palier-1-run-002.md
scope: runbook
---

# Palier 1 Run 002

Run name target: `palier1_be_birds_50taxa_run002`

## 1. Objective

Make the **full 50-taxa pack** compilable/materializable in v2 by fixing coverage only.

Baseline:

- run001 audit and coverage findings
- run001 full pack blocker: `insufficient_media_per_taxon`
- run001 blocking taxa: `9` (active playable `<2`)

## 2. Strict guardrails (run002)

Run002 must not change:

- qualification thresholds;
- distractor strategy;
- feedback model;
- runtime logic;
- canonical governance rules.

Allowed scope:

- targeted source coverage actions only (fetch/replacement/exclusion decisions).

## 3. Taxon strategy

### 3.1 Taxa kept as-is (already compilable for threshold)

- keep the `41` taxa from run001 with `active playable >=2` unchanged in pack scope.

### 3.2 Blocking taxa decision matrix

| Taxon | run001 status | run002 decision | Rationale |
|---|---|---|---|
| `taxon:birds:000026` (`Larus michahellis`) | 1 candidate / 1 playable | `FETCH_TARGETED` | very low source coverage, potentially recoverable with larger fetch |
| `taxon:birds:000032` (`Accipiter nisus`) | 11 candidates / 0 playable | `FETCH_TARGETED` | source exists; likely quality/visibility issue to offset with more candidates |
| `taxon:birds:000037` (`Athene noctua`) | 2 candidates / 0 playable | `FETCH_TARGETED` | undercovered source, increase search depth first |
| `taxon:birds:000041` (`Apus apus`) | 13 candidates / 0 playable | `FETCH_TARGETED` | high rejection likely due to far/difficult imagery; needs larger pool |
| `taxon:birds:000044` (`Riparia riparia`) | 3 candidates / 1 playable | `FETCH_TARGETED` | close to threshold, likely recoverable quickly |
| `taxon:birds:000045` (`Alauda arvensis`) | 4 candidates / 0 playable | `FETCH_TARGETED` | low source volume, try targeted fetch first |
| `taxon:birds:000046` (`Galerida cristata`) | 1 candidate / 0 playable | `REPLACE` (recommended) | structurally weak coverage in run001; low ROI for targeted fetch |
| `taxon:birds:000047` (`Lanius collurio`) | 7 candidates / 0 playable | `FETCH_TARGETED` | recoverable candidate volume path before replacement |
| `taxon:birds:000050` (`Corvus cornix`) | 0 candidate / 0 playable | `REPLACE` (recommended) | no source coverage in run001; replacement is lower risk for palier1 |

### 3.3 Replacement policy (run002)

Replacement candidates must be:

- common in Belgium;
- easy to retrieve on iNaturalist;
- visually identifiable;
- pedagogically useful;
- license/attribution robust.

Operational rule:

- if a `FETCH_TARGETED` taxon remains at `0-1` playable after targeted pass, switch to `REPLACE` for run002 closure.

## 4. Planned fixtures

Two fixture files should be prepared before execution:

1. `data/fixtures/inaturalist_pilot_taxa_palier1_be_run002_targeted.json`
- only blocking taxa selected for targeted fetch (`FETCH_TARGETED` group).

2. `data/fixtures/inaturalist_pilot_taxa_palier1_be_50_run002.json`
- final 50-taxa pack fixture for run002:
  - 41 kept taxa;
  - 7 fetch-targeted taxa;
  - 2 autonomous replacements.

### 4.1 Created fixtures (current)

- `data/fixtures/inaturalist_pilot_taxa_palier1_be_run002_targeted.json` (`7` taxa)
- `data/fixtures/inaturalist_pilot_taxa_palier1_be_50_run002.json` (`50` taxa)

### 4.2 Taxons fetch targeted (7)

- `Larus michahellis` (`taxon:birds:000026`, `source_taxon_id=59202`)
- `Accipiter nisus` (`taxon:birds:000032`, `source_taxon_id=5106`)
- `Athene noctua` (`taxon:birds:000037`, `source_taxon_id=19998`)
- `Apus apus` (`taxon:birds:000041`, `source_taxon_id=6638`)
- `Riparia riparia` (`taxon:birds:000044`, `source_taxon_id=11941`)
- `Alauda arvensis` (`taxon:birds:000045`, `source_taxon_id=7347`)
- `Lanius collurio` (`taxon:birds:000047`, `source_taxon_id=12038`)

### 4.3 Taxons replaced (2)

- replaced out:
  - `Galerida cristata` (`taxon:birds:000046`, `source_taxon_id=578607`)
  - `Corvus cornix` (`taxon:birds:000050`, `source_taxon_id=144757`)
- replaced in:
  - `Podiceps cristatus` (`taxon:birds:000070`, `source_taxon_id=4208`)
  - `Streptopelia decaocto` (`taxon:birds:000079`, `source_taxon_id=2969`)

Canonical id convention used:

- did **not** reuse `taxon:birds:000046` / `taxon:birds:000050` to avoid canonical identity drift;
- reused existing canonical ids already present in local fixtures (`birds_pilot_v2.json`), preserving stable identity semantics.

## 5. Planned commands

### 5.1 Targeted fetch (blocking taxa only)

Primary setting:

- `--place-id 7008`
- `--max-observations-per-taxon 40` (escalate to `60` if still under threshold)

```bash
python scripts/fetch_inat_snapshot.py \
  --snapshot-id palier1-be-birds-blocking-run002 \
  --pilot-taxa-path data/fixtures/inaturalist_pilot_taxa_palier1_be_run002_targeted.json \
  --place-id 7008 \
  --max-observations-per-taxon 40
```

### 5.2 Qualification and pipeline (new data only via cache flow)

```bash
python scripts/qualify_inat_snapshot.py \
  --snapshot-id palier1-be-birds-blocking-run002

python scripts/run_pipeline.py \
  --source-mode inat_snapshot \
  --snapshot-id palier1-be-birds-blocking-run002 \
  --qualifier-mode cached \
  --uncertain-policy reject \
  --database-url "$DATABASE_URL" \
  --normalized-path data/normalized/palier1_be_birds_50taxa_run002.normalized.json \
  --qualified-path data/qualified/palier1_be_birds_50taxa_run002.qualified.json \
  --export-path data/exports/palier1_be_birds_50taxa_run002.export.json
```

### 5.3 Full pack gate for run002

```bash
python scripts/manage_packs.py create \
  --database-url "$DATABASE_URL" \
  --pack-id "pack:palier1:be:birds:run002" \
  --difficulty-policy mixed \
  --country-code BE \
  --visibility private \
  --intended-use training \
  <50 canonical taxon flags from run002 fixture>

python scripts/manage_packs.py diagnose \
  --database-url "$DATABASE_URL" \
  --pack-id "pack:palier1:be:birds:run002"

python scripts/manage_packs.py compile \
  --database-url "$DATABASE_URL" \
  --pack-id "pack:palier1:be:birds:run002" \
  --question-count 50 \
  --contract-version v2

python scripts/manage_packs.py materialize \
  --database-url "$DATABASE_URL" \
  --pack-id "pack:palier1:be:birds:run002" \
  --question-count 50 \
  --contract-version v2 \
  --purpose assignment
```

### 5.4 Full-pack distractor audit

```bash
python scripts/audit_phase3_distractors.py \
  data/exports/palier1_be_birds_50taxa_run002.pack_compiled_v2.json \
  data/exports/palier1_be_birds_50taxa_run002.pack_materialization_v2.json \
  --output-json data/exports/palier1_be_birds_50taxa_run002.phase3_distractor_audit_report.json
```

## 6. Success criteria (run002)

Coverage gate:

- each taxon in final 50-taxa pack has `>=2` active playable items;
- target quality goal: `5-10` playable items for recovered taxa when feasible.

Compilation/materialization gate:

- full pack 50 taxa compile v2: `PASS`;
- full pack 50 taxa materialize v2: `PASS`.

v2 validity gate:

- questions with 4 options: `100%`;
- exactly 1 correct option: `100%`;
- non-empty option labels: `100%`;
- distractors with reason_codes: `100%`.

Documentation gate:

- run002 metrics captured:
  - new candidates;
  - sent to Gemini;
  - accepted;
  - became playable;
  - marginal Gemini cost;
  - blocking taxa resolution outcome.

## 7. Fallback and escalation

If full 50-taxa pack remains blocked after first targeted fetch:

1. escalate target fetch from `40` to `60` for unresolved taxa only;
2. apply replacement on persistent `0-1 playable` taxa;
3. regenerate final run002 50-taxa fixture;
4. rerun diagnose/compile/materialize on full pack.

The temporary reduced pack (`coverage-pass`) remains a validation artifact only and does not replace run002 full-pack closure.

## 8. Autonomous replacement decision

### 8.1 Replacement A

- taxon replaced: `Galerida cristata` (`taxon:birds:000046`)
- taxon chosen: `Podiceps cristatus` (`taxon:birds:000070`)
- justification:
  - widespread and observable in Belgium;
  - typically well represented as waterbird observations;
  - visually distinctive profile (shape/crest) for pedagogy;
  - lower ambiguity risk than structurally undercovered `Galerida cristata` in run001.
- confidence: `medium`
- risks:
  - seasonal/local clustering may still affect candidate density depending on window;
  - water distance shots can reduce qualification yield.
- `source_taxon_id` status: `verified` (`4208`, from local fixture data)

### 8.2 Replacement B

- taxon replaced: `Corvus cornix` (`taxon:birds:000050`)
- taxon chosen: `Streptopelia decaocto` (`taxon:birds:000079`)
- justification:
  - common and urban/peri-urban in Belgium;
  - usually easy to retrieve from iNaturalist observations;
  - visually identifiable and pedagogically useful at species level;
  - avoids run001 zero-candidate dead-end taxon.
- confidence: `high`
- risks:
  - potential confusion with other pigeons/doves in poor-angle photos, mitigated by larger candidate pool.
- `source_taxon_id` status: `verified` (`2969`, from local fixture data)

## 9. Executed run002 (2026-05-02)

### 9.1 Fixture preconditions validation

Executed checks:

- targeted fixture exists: `data/fixtures/inaturalist_pilot_taxa_palier1_be_run002_targeted.json`
- final fixture exists: `data/fixtures/inaturalist_pilot_taxa_palier1_be_50_run002.json`
- targeted taxa exact match: `7/7` expected names
- final fixture size: `50`
- duplicate `canonical_taxon_id`: `0`
- duplicate `source_taxon_id`: `0`
- `canonical_rank=species`: `50/50`
- `source_taxon_id=NEEDS_VERIFICATION`: `0`

Run001 vs run002 fixture composition:

- kept taxa: `48`
- targeted kept taxa: `7`
- kept non-targeted taxa: `41`
- replaced out: `taxon:birds:000046`, `taxon:birds:000050`
- replaced in: `taxon:birds:000070`, `taxon:birds:000079`

### 9.2 Targeted fetch run002

Executed:

```bash
python scripts/fetch_inat_snapshot.py \
  --snapshot-id palier1-be-birds-blocking-run002 \
  --pilot-taxa-path data/fixtures/inaturalist_pilot_taxa_palier1_be_run002_targeted.json \
  --place-id 7008 \
  --max-observations-per-taxon 40
```

Observed:

- snapshot id: `palier1-be-birds-blocking-run002`
- harvested observations: `41`
- downloaded images: `41`
- manifest version: `inaturalist.snapshot.v3`

Per targeted taxon observations:

- `taxon:birds:000026` (`Larus michahellis`): `1`
- `taxon:birds:000032` (`Accipiter nisus`): `11`
- `taxon:birds:000037` (`Athene noctua`): `2`
- `taxon:birds:000041` (`Apus apus`): `13`
- `taxon:birds:000044` (`Riparia riparia`): `3`
- `taxon:birds:000045` (`Alauda arvensis`): `4`
- `taxon:birds:000047` (`Lanius collurio`): `7`

Coverage status after `max=40`:

- unresolved: `taxon:birds:000026` (`unresolved_coverage_after_40`)

Escalation to `max=60` was not run in this pass because no clean partial-append mode was confirmed for the same snapshot artifact without risk of replacing snapshot scope.

### 9.3 Qualification run002

Executed:

```bash
python scripts/qualify_inat_snapshot.py \
  --snapshot-id palier1-be-birds-blocking-run002
```

Observed:

- `FAILED`: `Missing Gemini API key in env var GEMINI_API_KEY`
- no qualification counts produced for run002 snapshot

### 9.4 Pipeline cached run002

Executed:

```bash
python scripts/run_pipeline.py \
  --source-mode inat_snapshot \
  --snapshot-id palier1-be-birds-blocking-run002 \
  --qualifier-mode cached \
  --uncertain-policy reject \
  --database-url "$DATABASE_URL" \
  --normalized-path data/normalized/palier1_be_birds_50taxa_run002.normalized.json \
  --qualified-path data/qualified/palier1_be_birds_50taxa_run002.qualified.json \
  --export-path data/exports/palier1_be_birds_50taxa_run002.export.json
```

Observed:

- `FAILED` with DB FK violation during `reset_materialized_state`
- error: `update or delete on table "canonical_taxa" violates foreign key constraint ... on table "referenced_taxa"`

Behavior note:

- run002 pipeline could not complete, so run001/run002 merge behavior could not be validated in this execution.

### 9.5 Smoke report run002

Executed:

```bash
python scripts/generate_smoke_report.py \
  --snapshot-id palier1-be-birds-blocking-run002
```

Observed:

- generated: `docs/archive/evidence/smoke-reports/palier1-be-birds-blocking-run002.smoke_report.v1.json`
- `overall_pass=true`
- latest run in report: `failed`

### 9.6 Pack run002 diagnose

Executed create:

```bash
python scripts/manage_packs.py create \
  --database-url "$DATABASE_URL" \
  --pack-id "pack:palier1:be:birds:run002" \
  --difficulty-policy mixed \
  --country-code BE \
  --visibility private \
  --intended-use training \
  --canonical-taxon-id <50x from run002 fixture>
```

Executed diagnose:

```bash
python scripts/manage_packs.py diagnose \
  --database-url "$DATABASE_URL" \
  --pack-id "pack:palier1:be:birds:run002"
```

Diagnose result:

- `compilable=false`
- `reason_code=insufficient_media_per_taxon`
- `taxa_served=19`
- `questions_possible=20`
- `min_media_count_per_taxon=0`
- blocking taxa count: `45`

### 9.7 Compile/materialize/audit status

- compile v2: `NOT_RUN` (blocked by diagnose failure)
- materialize v2: `NOT_RUN`
- full-pack distractor audit: `NOT_RUN` (no v2 artifacts)

### 9.8 Decision and next actions

Run002 decision: `NO_GO`

Recommended next actions:

1. Provide `GEMINI_API_KEY` and rerun qualification for snapshot run002.
2. Resolve pipeline DB reset blocker (`referenced_taxa` FK) before rerunning cached pipeline.
3. Rerun diagnose on refreshed playable state and continue compile/materialize/audit only if compilable.

## 10. Run002 update after FK fix (2026-05-02)

### 10.1 FK root cause and fix

Root cause:

- `reset_materialized_state()` deleted `canonical_taxa` but did not clear `referenced_taxa`.
- `referenced_taxa.mapped_canonical_taxon_id -> canonical_taxa.canonical_taxon_id` caused FK violation.

Code location:

- file: `src/database_core/storage/postgres.py`
- function: `PostgresStorageInternal.reset_materialized_state`

Applied fix (minimal):

- added `DELETE FROM referenced_taxa` before `DELETE FROM canonical_taxa`.
- this preserves governance semantics and keeps reset coherent with phase-3 referenced-only data lifecycle.

Test added:

- `tests/test_pipeline.py::test_pipeline_overwrite_clears_referenced_taxa_before_canonical_reset`
- validates second pipeline run no longer fails when referenced taxa exist.

### 10.2 Qualification rerun (with GEMINI_API_KEY)

Executed:

```bash
python scripts/qualify_inat_snapshot.py \
  --snapshot-id palier1-be-birds-blocking-run002
```

Observed:

- candidates/images: `41`
- sent to Gemini: `35`
- valid outputs (`ok`): `35`
- Gemini errors: `0`
- pre-AI rejections: `6` (`insufficient_resolution_pre_ai`)

### 10.3 Pipeline cached rerun

Executed:

```bash
python scripts/run_pipeline.py \
  --source-mode inat_snapshot \
  --snapshot-id palier1-be-birds-blocking-run002 \
  --qualifier-mode cached \
  --uncertain-policy reject \
  --database-url "$DATABASE_URL" \
  --normalized-path data/normalized/palier1_be_birds_50taxa_run002.normalized.json \
  --qualified-path data/qualified/palier1_be_birds_50taxa_run002.qualified.json \
  --export-path data/exports/palier1_be_birds_50taxa_run002.export.json
```

Observed:

- `PASS`
- `run_id=run:20260502T102543Z:9bbcb4e7`
- `qualified=41`
- `exportable=3`
- `review=0`

Behavior confirmed:

- pipeline overwrites current materialized state rather than merging run001 + run002.
- because snapshot run002 is targeted (7 taxa), the full 50-taxa pack loses prior run001 playable coverage.
- this is a design blocker for run002 closure, not a runtime/qualification rule issue.

### 10.4 Diagnose rerun

Executed:

```bash
python scripts/manage_packs.py diagnose \
  --database-url "$DATABASE_URL" \
  --pack-id "pack:palier1:be:birds:run002"
```

Observed:

- `compilable=false`
- `reason_code=insufficient_taxa_served`
- `taxa_served=2`
- `questions_possible=0`
- `min_media_count_per_taxon=0`

Decision impact:

- compile v2/materialize v2/audit distractors not run (blocked by diagnose).

### 10.5 Updated run002 decision

- decision remains: `NO_GO`
- primary remaining blocker: run design (targeted snapshot pipeline overwrite without merge with run001 baseline).

## 11. Closure snapshot 50 run (2026-05-02)

Snapshot id:

- `palier1-be-birds-50taxa-run002-closure`

### 11.1 Fetch closure 50

Executed:

```bash
python scripts/fetch_inat_snapshot.py \
  --snapshot-id palier1-be-birds-50taxa-run002-closure \
  --pilot-taxa-path data/fixtures/inaturalist_pilot_taxa_palier1_be_50_run002.json \
  --place-id 7008 \
  --max-observations-per-taxon 40
```

Observed:

- harvested: `1414`
- downloaded: `1414`
- taxon seeds: `50`
- under-covered `<2` observations before qualification: `1` taxon (`Larus michahellis=1`)

Targeted deep fetch for Larus:

```bash
python scripts/fetch_inat_snapshot.py \
  --snapshot-id palier1-be-birds-50taxa-run002-closure-larus60 \
  --pilot-taxa-path <larus-only fixture> \
  --place-id 7008 \
  --max-observations-per-taxon 60
```

Observed:

- `Larus michahellis` remained at `1` observation (`unresolved_coverage_after_60`)

### 11.2 Qualification closure (single pass)

Executed:

```bash
python scripts/qualify_inat_snapshot.py \
  --snapshot-id palier1-be-birds-50taxa-run002-closure
```

Observed:

- candidates/media: `1413`
- sent to Gemini: `1333`
- valid outputs (`ok`): `1333`
- Gemini errors: `0`
- pre-AI rejections: `80` (`78 insufficient_resolution_pre_ai`, `3 duplicate_pre_ai`)

### 11.3 Pipeline closure (cached)

Executed:

```bash
python scripts/run_pipeline.py \
  --source-mode inat_snapshot \
  --snapshot-id palier1-be-birds-50taxa-run002-closure \
  --qualifier-mode cached \
  --uncertain-policy reject \
  --database-url "$DATABASE_URL" \
  --normalized-path data/normalized/palier1_be_birds_50taxa_run002_closure.normalized.json \
  --qualified-path data/qualified/palier1_be_birds_50taxa_run002_closure.qualified.json \
  --export-path data/exports/palier1_be_birds_50taxa_run002_closure.export.json
```

Observed:

- `PASS`
- `run_id=run:20260502T112940Z:5c268034`
- `qualified=1413`
- `exportable=581`
- `review=0`

Artifacts:

- `data/normalized/palier1_be_birds_50taxa_run002_closure.normalized.json` (`canonical_taxa=50`)
- `data/qualified/palier1_be_birds_50taxa_run002_closure.qualified.json` (`qualified_resources=1413`)
- `data/exports/palier1_be_birds_50taxa_run002_closure.export.json` (`canonical_taxa=45`, `qualified_resources=581`)

### 11.4 Smoke + diagnose gate

Smoke:

```bash
python scripts/generate_smoke_report.py \
  --snapshot-id palier1-be-birds-50taxa-run002-closure
```

- report: `docs/archive/evidence/smoke-reports/palier1-be-birds-50taxa-run002-closure.smoke_report.v1.json`
- overall pass: `true`
- estimated AI cost EUR: `1.5996`

Diagnose:

```bash
python scripts/manage_packs.py diagnose \
  --database-url "$DATABASE_URL" \
  --pack-id "pack:palier1:be:birds:run002"
```

Observed:

- `compilable=false`
- `reason_code=insufficient_media_per_taxon`
- `taxa_served=45`
- `questions_possible=20`
- `min_media_count_per_taxon=0`
- blocking taxa: `8` (`000026`, `000032`, `000037`, `000040`, `000041`, `000044`, `000045`, `000047`)

Gate consequence:

- compile v2: `NOT_RUN`
- materialize v2: `NOT_RUN`
- distractor audit: `NOT_RUN`

### 11.5 Updated decision

- run002 decision remains `NO_GO`.
