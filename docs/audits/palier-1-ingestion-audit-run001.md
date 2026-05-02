---
owner: database
status: in_progress
last_reviewed: 2026-05-02
source_of_truth: docs/audits/palier-1-ingestion-audit-run001.md
scope: audit
---

# Palier 1 Ingestion Audit - Run001

Run name: `palier1_be_birds_50taxa_run001`  
Audit date: `2026-05-02`

## 1. Snapshot health

Evidence source:
- `python scripts/inspect_database.py snapshot-health --snapshot-id palier1-be-birds-50taxa-run001`
- `docs/archive/evidence/smoke-reports/palier1_be_birds_50taxa_run001.smoke_report.v1.json`

Observed:
- harvested observations: `778`
- taxa with results: `49/50`
- taxa without results: `1/50` (`taxon:birds:000050`, `Corvus cornix`)
- downloaded images: `778`
- review queue: `0`
- latest successful run id: `run:20260502T091349Z:10e95bc1`
- smoke overall pass: `true`

## 2. Candidate and pre-AI filtering counts

Evidence source:
- `data/exports/palier1_be_birds_50taxa_run001.qualification_metrics.json`
- snapshot health output

Observed:
- candidates downloaded: `778`
- images sent to Gemini: `732`
- pre-AI rejection reason counts:
  - `insufficient_resolution_pre_ai: 43`
  - `duplicate_pre_ai: 3`
- status distribution at qualification I/O level:
  - `ok: 718`
  - `gemini_error: 14`
  - `insufficient_resolution_pre_ai: 43`
  - `duplicate_pre_ai: 2`

## 3. Qualification status distribution

Evidence source:
- snapshot health output
- smoke report (`run_metrics.quality`)

Observed:
- qualified resources: `777`
- accepted resources: `301`
- rejected resources: `476`
- review_required resources: `0`
- top rejection flags:
  - `insufficient_technical_quality: 414`
  - `insufficient_resolution: 126`
  - `missing_view_angle: 90`
  - `missing_visible_parts: 67`
  - `insufficient_resolution_pre_ai: 43`

## 4. Species coverage

Evidence source:
- `data/exports/palier1_be_birds_50taxa_run001.postrun_metrics.json`
- `docs/audits/palier-1-run001-coverage-audit.md`

Observed:
- active taxa in run scope: `50`
- taxa with `>=1` playable item: `43`
- taxa with `>=10` playable items: `10`
- median playable items per taxon: `5.0`
- per-pack compile blocker for 50-taxa v2:
  - taxa meeting min playable threshold for pack compile (`>=2`): `41/50`
  - blocking taxa (`<2`): `9`

## 5. Licence and attribution coverage

Evidence source:
- `data/exports/palier1_be_birds_50taxa_run001.postrun_metrics.json`

Observed (on playable total `301`):
- with license: `301/301` (`100%`)
- with attribution: `301/301` (`100%`)
- with source URL: `301/301` (`100%`)

## 6. Feedback coverage

Evidence source:
- `data/exports/palier1_be_birds_50taxa_run001.postrun_metrics.json`

Observed (on playable total `301`):
- `feedback_short`: `301/301` (`100%`)
- `what_to_look_at_specific`: `301/301` (`100%`)
- `what_to_look_at_general`: `0/301` (`0%`)
- `confusion_hint`: `0/301` (`0%`)

## 7. Distractor/materialization v2 validity

### 7.1 Full 50-taxa pack (`pack:palier1:be:birds:run001`)

Evidence source:
- `docs/runbooks/palier-1-run-001.md` section 11
- `data/exports/palier1_be_birds_50taxa_run001.phase3_distractor_audit_report.json`

Observed:
- compile v2: `FAILED` (`insufficient_media_per_taxon`)
- materialize v2: `FAILED` (no v2 compiled build)
- distractor audit on full pack: `MISSING_EVIDENCE` (no valid v2 artifact to audit)
- parser errors captured when audit was run on inspect-list outputs:
  - `'/tmp/palier1_compiled_builds.json': "'list' object has no attribute 'get'"`
  - `'/tmp/palier1_materializations.json': "'list' object has no attribute 'get'"`

### 7.2 Temporary reduced coverage-pass pack (`pack:palier1:be:birds:run001:coverage-pass`)

Evidence source:
- `data/exports/palier1_be_birds_50taxa_run001.coverage_pass.pack_compiled_v2.json`
- `data/exports/palier1_be_birds_50taxa_run001.coverage_pass.pack_materialization_v2.json`
- `data/exports/palier1_be_birds_50taxa_run001.coverage_pass.phase3_distractor_audit_report.json`

Observed:
- questions: `20`
- options: `80`
- distractors: `60`
- invariants:
  - questions with 4 options: `20/20` (`100%`)
  - questions with exactly 1 correct option: `20/20` (`100%`)
  - options with non-empty labels: `80/80` (`100%`)
  - distractors with reason codes: `60/60` (`100%`)
- distractor characteristics:
  - iNaturalist similar species distractors: `0`
  - out_of_pack distractors: `0`
  - referenced_only distractors: `0`
  - dominant reason code: `diversity_fallback` (`60/60`)

## 8. Review queue volume

Evidence source:
- snapshot health output
- smoke report `run_metrics.review_load`

Observed:
- open review queue items: `0`
- average open review age: `0.0h`

## 9. Cost estimate Gemini

Evidence source:
- smoke report `run_metrics.cost`

Observed:
- ai_qualified_images: `718`
- estimated_ai_cost_eur: `0.8616`

Note:
- model-level billing detail breakdown per request/token: `MISSING_EVIDENCE`

## 10. Runtime E2E selectedOptionId

Evidence source:
- `runtime-app/docs/runbooks/palier1-run001-v2-consumption-check.md`

Observed:
- owner sync/contracts: no drift
- materialization v2 consumed in runtime test harness: `PASS`
- answer submitted with `selectedOptionId`: `PASS`
- derived `selectedTaxonId` check: `PASS` (`taxon:birds:000002`)
- `shown_distractor_taxon_ids` check: `PASS` (`3` ids)
- no dependency on `selectedPlayableItemId` for taxon-only distractor: `PASS`
- Postgres runtime E2E tests:
  - skipped (`TEST_RUNTIME_DATABASE_URL` unavailable): `MISSING_EVIDENCE`

## 11. Manual pedagogical review

Evidence source:
- no dedicated manual pedagogical checklist/run evidence attached for run001

Observed:
- manual review sample (30-100 questions) with pedagogical rubric: `MISSING_EVIDENCE`

## 12. Consolidated evidence matrix

### 12.1 Preuves disponibles
- snapshot health and smoke pass
- candidate/pre-AI counts
- qualification distribution and rejection flags
- species/playable coverage with blocking taxa analysis
- license/attribution coverage
- feedback coverage
- reduced-pack v2 distractor/materialization validity
- review queue volume
- Gemini cost estimate (`estimated_ai_cost_eur`)
- runtime selectedOptionId E2E functional validation

### 12.2 Preuves manquantes
- full 50-taxa v2 distractor audit metrics (no compiled/materialized v2 artifact)
- Postgres-backed runtime E2E evidence (`TEST_RUNTIME_DATABASE_URL` missing)
- manual pedagogical review evidence
- detailed Gemini billing breakdown per request/token

## 13. Issues

### 13.1 Problèmes bloquants
- Full 50-taxa pack v2 does not compile (`insufficient_media_per_taxon`).
- `9` taxa are below compile threshold (`active playable <2`), preventing full run001 v2 materialization.
- No full-pack v2 artifact means no full-pack distractor validity audit.

### 13.2 Problèmes non bloquants
- `what_to_look_at_general` coverage is `0%`.
- `confusion_hint` coverage is `0%`.
- Runtime Postgres tests skipped due to missing env var (does not invalidate functional contract consumption proof, but leaves persistence-path evidence incomplete).
- Manual pedagogical review evidence absent.

## 14. Corrections before run002

### P0 (obligatoires)
- Resolve the 9 blocking taxa coverage gap (more candidates and/or governed taxon replacement decisions) so full 50-taxa pack reaches compile threshold.
- Re-run cached pipeline and then re-run full pack `diagnose -> compile v2 -> materialize v2`.
- Produce full-pack v2 distractor audit report from actual full-pack artifacts (not reduced pack).

### P1 (fortement recommandées)
- Execute runtime Postgres E2E suites with `TEST_RUNTIME_DATABASE_URL` set and archive evidence.
- Execute manual pedagogical review sample and archive outcomes (image clarity, distractor plausibility, feedback usefulness).

### P2 (optionnelles)
- Improve general feedback coverage and confusion hints where pedagogically relevant.
- Improve distractor diversity beyond `diversity_fallback` dominance once full-pack coverage is stabilized.

## 15. Final decision

1. **Décision recommandée:** `NO_GO`
2. **Raisons:**
- The primary Palier 1 full pack objective (50 taxa v2 compile/materialize + full-pack distractor audit) is not met.
- Critical evidence remains missing for full-pack v2 distractor validity and manual pedagogical review.
3. **Corrections obligatoires avant run002:**
- P0 actions listed above.
4. **Corrections optionnelles:**
- P1/P2 actions listed above.
5. **Conditions pour passer au palier 2:**
- Full 50-taxa pack compiles/materializes in v2 with no blocking taxa.
- Full-pack distractor audit report exists with required invariant checks.
- Runtime selectedOptionId flow validated including Postgres-backed persistence evidence.
- Manual pedagogical review evidence produced and accepted for run001 scope.

