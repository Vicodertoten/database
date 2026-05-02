---
owner: database
status: in_progress
last_reviewed: 2026-05-02
source_of_truth: docs/audits/palier-1-ingestion-audit-run002.md
scope: audit
---

# Palier 1 Ingestion Audit - Run002

Run name: `palier1_be_birds_50taxa_run002`  
Audit date: `2026-05-02`

## 1. Executive decision

Decision: `NO_GO`

Primary blockers:

- qualification run blocked (`GEMINI_API_KEY` missing)
- cached pipeline blocked by DB FK violation on `referenced_taxa`
- full pack diagnose run002 failed (`insufficient_media_per_taxon`)
- no full-pack v2 compiled/materialized artifacts

## 2. Comparaison run001 vs run002

- run001 blocker: `insufficient_media_per_taxon` with `9` taxa `<2` playable.
- run002 plan executed with same business rules (no threshold/strategy/runtime changes).
- run002 targeted fetch completed (`41` observations) but full closure not reached.
- run002 diagnose is worse at pack level (`taxa_served=19`) because pipeline refresh failed before playable-state update.

## 3. Taxons bloquants run001 et résolution run002

Run001 blocking set (9 taxa):

- `taxon:birds:000026`, `000032`, `000037`, `000041`, `000044`, `000045`, `000046`, `000047`, `000050`

Run002 strategy evidence:

- targeted fetch executed for 7 taxa (`000026`, `000032`, `000037`, `000041`, `000044`, `000045`, `000047`)
- replacements documented and present in final fixture:
  - out: `taxon:birds:000046` (`Galerida cristata`)
  - out: `taxon:birds:000050` (`Corvus cornix`)
  - in: `taxon:birds:000070` (`Podiceps cristatus`)
  - in: `taxon:birds:000079` (`Streptopelia decaocto`)

Remaining fetch under-coverage after 40:

- `taxon:birds:000026` (`Larus michahellis`) -> `1` observation (`unresolved_coverage_after_40`)

## 4. Snapshot health

Evidence:

- `data/raw/inaturalist/palier1-be-birds-blocking-run002/manifest.json`
- `docs/archive/evidence/smoke-reports/palier1-be-birds-blocking-run002.smoke_report.v1.json`

Observed:

- snapshot exists and valid (`manifest_version=inaturalist.snapshot.v3`)
- targeted taxa in snapshot: `7`
- harvested observations: `41`
- downloaded images: `41`
- smoke report generated: `PASS` (`overall_pass=true`)

## 5. Candidate and pre-AI filtering counts

Observed for run002 targeted snapshot:

- candidates downloaded: `41`
- pre-AI rejection counts: `MISSING_EVIDENCE` (run002 qualification did not execute)

## 6. Qualification status distribution

Executed command failed:

- `python scripts/qualify_inat_snapshot.py --snapshot-id palier1-be-birds-blocking-run002`
- error: `Missing Gemini API key in env var GEMINI_API_KEY`

Therefore:

- images sent to Gemini: `MISSING_EVIDENCE`
- valid outputs: `MISSING_EVIDENCE`
- Gemini errors: `MISSING_EVIDENCE`
- rejection distribution: `MISSING_EVIDENCE`

## 7. Species coverage

Fixture integrity checks:

- final fixture taxa count: `50`
- duplicates (`canonical_taxon_id`): `0`
- duplicates (`source_taxon_id`): `0`
- `canonical_rank=species`: `50/50`
- kept non-targeted taxa from run001: `41`
- targeted taxa included: `7`
- replacements included: `2`

Pack diagnose run002:

- `taxa_served=19`
- `min_media_count_per_taxon=0`
- coverage gate `>=2` per taxon: `FAILED`

## 8. Licence and attribution coverage

- blocking state prevented fresh run002-qualified corpus derivation.
- no new run002 license/attribution coverage table from qualified/playable refresh.
- status for run002: `MISSING_EVIDENCE`

## 9. Feedback coverage

- no successful run002 pipeline completion.
- run002 feedback coverage recomputation: `MISSING_EVIDENCE`

## 10. Pack diagnose result

Evidence:

- `manage_packs.py diagnose --pack-id pack:palier1:be:birds:run002`

Observed:

- `compilable=false`
- `reason_code=insufficient_media_per_taxon`
- `taxa_served=19`
- `questions_possible=20`
- `min_media_count_per_taxon=0`
- blocking taxa: `45`

## 11. Compile v2 result

- `NOT_RUN` (diagnose non-compilable)

## 12. Materialization v2 result

- `NOT_RUN` (no successful compile v2)

## 13. Distractor audit

- `NOT_RUN` for full pack run002 (no compiled/materialized v2 artifact available)

## 14. Cost estimate

- run002 incremental Gemini cost: `MISSING_EVIDENCE` (qualification not executed)
- smoke report contains global historical estimate, not a clean run002 incremental cost ledger

## 15. Runtime E2E evidence

Known status carried from prior evidence:

- runtime-app v2 submission with `selectedOptionId`: `PASS` (run001-linked evidence)

Run002-specific runtime E2E:

- no new full-pack v2 artifact to consume, so no run002 runtime E2E replay

## 16. Missing evidence

- `GEMINI_API_KEY` missing for run002 qualification.
- run002 qualification metrics (Gemini I/O/rejections/cost) missing.
- run002 pipeline completion blocked by FK violation on `referenced_taxa`.
- run002 full-pack v2 compile/materialize artifacts missing.
- run002 distractor audit missing (artifact precondition not met).
- runtime Postgres E2E rerun status: `MISSING_EVIDENCE` (`TEST_RUNTIME_DATABASE_URL` not provided/rerun not executed in this run).

## 17. Final decision

Decision: `NO_GO`

Mandatory GO/GO_WITH_WARNINGS criteria not met:

- `50/50` taxa with `>=2` active playable items: `FAIL`
- full pack compile v2: `FAIL` (not compilable)
- full pack materialize v2: `FAIL` (not run)
- QuestionOption validity on full pack: `MISSING_EVIDENCE`
- non-empty labels on full pack: `MISSING_EVIDENCE`
- exactly one correct option on full pack: `MISSING_EVIDENCE`
- distractor reason codes on full pack: `MISSING_EVIDENCE`

## 18. Update after DB FK fix and rerun

### 18.1 FK cause racine (`referenced_taxa`)

- failing path: pipeline `reset_materialized_state` deleted `canonical_taxa` while `referenced_taxa` still referenced them.
- FK involved:
  - `referenced_taxa.mapped_canonical_taxon_id -> canonical_taxa.canonical_taxon_id`
  - `referenced_taxon_events.referenced_taxon_id -> referenced_taxa.referenced_taxon_id`

Applied correction:

- file: `src/database_core/storage/postgres.py`
- function: `PostgresStorageInternal.reset_materialized_state`
- change: add `DELETE FROM referenced_taxa` before `DELETE FROM canonical_taxa`
- rationale: minimal, explicit, compatible with phase-3 referenced-only lifecycle; avoids masking errors.

### 18.2 Qualification rerun status

Command rerun:

- `python scripts/qualify_inat_snapshot.py --snapshot-id palier1-be-birds-blocking-run002`

Observed:

- candidates: `41`
- sent to Gemini: `35`
- valid Gemini outputs (`ok`): `35`
- Gemini errors: `0`
- pre-AI rejections: `6` (`insufficient_resolution_pre_ai`)

### 18.3 Pipeline run002 status after fix

Command rerun:

- `python scripts/run_pipeline.py --source-mode inat_snapshot --snapshot-id palier1-be-birds-blocking-run002 --qualifier-mode cached --uncertain-policy reject --database-url "$DATABASE_URL" --normalized-path data/normalized/palier1_be_birds_50taxa_run002.normalized.json --qualified-path data/qualified/palier1_be_birds_50taxa_run002.qualified.json --export-path data/exports/palier1_be_birds_50taxa_run002.export.json`

Observed:

- `PASS`
- `run_id=run:20260502T102543Z:9bbcb4e7`
- `qualified=41`
- `exportable=3`
- `review=0`

Design behavior observed:

- pipeline replaces active materialized state (not incremental merge of run001 + run002 datasets).
- with a targeted 7-taxa snapshot, this drops 50-taxa pack readiness.

### 18.4 Diagnose/compile/materialize/audit status after fix

Diagnose rerun:

- `compilable=false`
- `reason_code=insufficient_taxa_served`
- `taxa_served=2`
- `questions_possible=0`
- `min_media_count_per_taxon=0`

Consequences:

- compile v2: `NOT_RUN` (as required)
- materialize v2: `NOT_RUN`
- distractor audit: `NOT_RUN` (no v2 artifacts)

### 18.5 Updated final decision

Decision remains `NO_GO`.

Main remaining blocker is now run design, not FK:

- a targeted run002 snapshot alone cannot close a full 50-taxa pack when pipeline overwrite semantics are used.

## 19. Closure snapshot 50 execution update

### 19.1 Snapshot/fetch closure status

- closure snapshot id: `palier1-be-birds-50taxa-run002-closure`
- harvested observations: `1414`
- downloaded images: `1414`
- taxa in fixture: `50`
- taxon still `<2` observations before qualification: `Larus michahellis` (`1`)
- targeted deep fetch `Larus` to `60`: no improvement (`1`) -> `unresolved_coverage_after_60`

### 19.2 Qualification closure status

- candidates/media processed: `1413`
- sent to Gemini: `1333`
- valid outputs (`ok`): `1333`
- Gemini errors: `0`
- pre-AI rejections: `80`
  - `insufficient_resolution_pre_ai: 78`
  - `duplicate_pre_ai: 3`
- estimated AI cost (smoke report): `€1.5996`

### 19.3 Pipeline closure status

- pipeline cached rerun: `PASS`
- `run_id=run:20260502T112940Z:5c268034`
- `qualified=1413`
- `exportable=581`
- `review=0`
- closure artifacts produced:
  - `data/normalized/palier1_be_birds_50taxa_run002_closure.normalized.json`
  - `data/qualified/palier1_be_birds_50taxa_run002_closure.qualified.json`
  - `data/exports/palier1_be_birds_50taxa_run002_closure.export.json`

### 19.4 Diagnose/compile/materialize/audit closure status

Diagnose (`pack:palier1:be:birds:run002`):

- `compilable=false`
- `reason_code=insufficient_media_per_taxon`
- `taxa_served=45`
- `questions_possible=20`
- `min_media_count_per_taxon=0`
- blocking taxa: `8`
  - `taxon:birds:000026`
  - `taxon:birds:000032`
  - `taxon:birds:000037`
  - `taxon:birds:000040`
  - `taxon:birds:000041`
  - `taxon:birds:000044`
  - `taxon:birds:000045`
  - `taxon:birds:000047`

Gate enforcement:

- compile v2: `NOT_RUN`
- materialize v2: `NOT_RUN`
- distractor audit: `NOT_RUN`

### 19.5 Final decision update

Decision remains `NO_GO`.

Reason:

- closure improved to `45/50` taxa served, but mandatory full-pack compile precondition (`>=2` playable for every requested taxon) still fails on 8 taxa.
