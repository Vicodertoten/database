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
