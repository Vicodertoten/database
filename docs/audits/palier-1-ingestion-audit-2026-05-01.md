---
owner: database
status: in_progress
last_reviewed: 2026-05-01
source_of_truth: docs/audits/palier-1-ingestion-audit-2026-05-01.md
scope: audit
---

# Palier 1 Ingestion Audit - 2026-05-01

## 1. Executive decision

Decision: `GO_WITH_WARNINGS`

Recommended decision for phase progression:

- `GO` for starting Palier 1 audit operations on the current pipeline as-is.
- `NO_GO` for promotion to Palier 2 before closing evidence gaps listed below.

## 2. Scope

- birds
- Belgium
- image-only
- 50 species target
- 1,000 qualified images target
- source snapshot: `phase2-birds-be-20260429T083143Z-a1`
- run id: `MISSING_EVIDENCE` (DB run metadata not accessible from current local DB URL)
- pack/materialization ids:
  - `data/exports/phase3_pedagogical/pack_compiled_v2_pedagogical_calibrated.json`
  - `data/exports/phase3_pedagogical/pack_materialization_v2_pedagogical_calibrated.json`

## 3. Inputs audited

Evidence available:

- snapshot manifest (`data/raw/inaturalist/phase2-birds-be-20260429T083143Z-a1/manifest.json`)
- normalized outputs (`data/normalized/phase2-birds-be-20260429T083143Z-a1.json`)
- qualification outputs (`data/qualified/phase2-birds-be-20260429T083143Z-a1.json`)
- export bundle (`data/exports/phase2-birds-be-20260429T083143Z-a1.json`)
- phase 3 distractor audit script output (`scripts/audit_phase3_distractors.py`)
- prior phase2 smoke evidence (`docs/archive/evidence/2026-04/phase2_playable_corpus_report.v1.json`)
- prior runtime E2E evidence (`docs/audits/learning-loop-audit-v0.md`)

Evidence missing:

- consolidated fresh smoke report generated on current DB instance
- explicit DB-backed run lineage for this audit execution
- fresh manual pedagogical review log (30-50 questions) for this audit cycle

## 4. Source snapshot health

Metrics:

- snapshot id: `phase2-birds-be-20260429T083143Z-a1`
- manifest version: present (`inaturalist.snapshot.v3`)
- canonical taxa in normalized output: `50`
- media assets in normalized output: `1500`
- source observations in normalized output: `MISSING_EVIDENCE` (`0` in normalized file suggests this artifact is not a full source-observation snapshot)
- missing payloads: `MISSING_EVIDENCE`
- source warnings: `MISSING_EVIDENCE`

Decision: `WARNING`

## 5. Candidate and pre-AI filtering

Metrics:

- media candidates: `1500`
- duplicate_pre_ai: `MISSING_EVIDENCE` (no manifest pre-AI counts in current snapshot manifest)
- insufficient_resolution_pre_ai: `46` (observed in qualification flags)
- decode_error_pre_ai: `MISSING_EVIDENCE` for current run-level count
- blur_pre_ai: `MISSING_EVIDENCE` for current run-level count
- media sent to Gemini: `1453` (last consolidated smoke evidence)
- pre-AI savings rate: `MISSING_EVIDENCE` (depends on complete pre-AI counters)

Decision: `WARNING`

## 6. Qualification distribution

Metrics:

- accepted: `1157`
- rejected: `343`
- review_required: `0`
- top flags:
  - `insufficient_technical_quality`: `266`
  - `insufficient_resolution`: `139`
  - `missing_view_angle`: `60`
  - `missing_visible_parts`: `51`
  - `insufficient_resolution_pre_ai`: `46`
- low confidence count: `12`
- missing visible parts: `51`
- missing view angle: `60`
- insufficient technical quality: `266`

Decision: `PASS`

## 7. Species coverage

Metrics:

- active taxa: `50`
- taxa with >= 1 playable item (accepted proxy): `50`
- taxa with >= 10 playable items (accepted proxy): `50`
- median playable items per taxon (accepted proxy): `24.0`
- under-covered species (<10 items): `0`

Decision: `PASS`

## 8. Licence and attribution coverage

Metrics:

- playable items with licence: `MISSING_EVIDENCE` (fresh DB query not available in this run)
- playable items with attribution: `MISSING_EVIDENCE` (fresh DB query not available in this run)
- playable items with source URL: `MISSING_EVIDENCE`
- unsafe_license count: `0` in top rejection flags view (`unsafe_license` not present in observed top flags)
- missing attribution count: `MISSING_EVIDENCE`
- prior consolidated evidence: attribution completeness `1.0` (phase2 report, 2026-04)

Decision: `WARNING`

## 9. Feedback coverage

Metrics:

- feedback_short coverage: `MISSING_EVIDENCE` (not recomputed on current DB)
- what_to_look_at_general coverage: `MISSING_EVIDENCE` for this audit run
- what_to_look_at_specific coverage: `MISSING_EVIDENCE` for this audit run
- confusion_hint coverage: `MISSING_EVIDENCE` for this audit run
- manual usefulness sample: `MISSING_EVIDENCE`

Decision: `FAIL`

## 10. Distractor and materialization v2 validity

Metrics (50-question materialization sample):

- materialization v2 present: `yes`
- questions audited: `50`
- valid `QuestionOption[]` rate: `100%`
- questions with exactly 4 options: `50/50`
- questions with 1 correct option: `50/50`
- questions with referenced_only: `50/50`
- questions with iNat similar species: `50/50`
- reason_codes coverage on distractors: `150/150`
- distractor plausibility manual score: `MISSING_EVIDENCE`
- diversity_fallback_only distractors: `50/150` (`33.33%`)

Decision: `PASS` (technical), `WARNING` (pedagogical calibration still needed)

## 11. Runtime E2E status

Evidence:

- runtime-app consumes materialization v2: prior cross-repo audit evidence says yes
- `selectedOptionId` submit works: prior cross-repo audit evidence says yes
- `selectedTaxonId` derived correctly: prior cross-repo audit evidence says yes
- learning logs correct: prior cross-repo audit evidence says yes
- Postgres tests status: prior evidence PASS, not rerun in this document cycle

Decision: `WARNING` (evidence exists but not rerun in this audit execution)

## 12. Cost estimate

Metrics:

- Gemini calls (proxy): `1453` AI-qualified images (latest consolidated smoke evidence)
- estimated Gemini cost: `EUR 1.7436` (same evidence source)
- cost per candidate image: `EUR 0.0011624` (1.7436 / 1500)
- cost per qualified image: `EUR 0.0015061` (1.7436 / 1157)
- cost per playable item: `MISSING_EVIDENCE` (needs fresh playable total for audited run)
- cost avoided by pre-AI filtering: `MISSING_EVIDENCE`

Decision: `WARNING`

## 13. Review queue

Metrics:

- total review items: `0` (latest consolidated smoke evidence)
- review items per 1,000 candidates: `0`
- top review reasons: `MISSING_EVIDENCE` (no open review items)
- high-priority review items: `0`

Decision: `PASS`

## 14. Manual pedagogical review

Sample:

- required: `30-50 questions`
- current cycle: `MISSING_EVIDENCE`

Scores:

- image clarity: `MISSING_EVIDENCE`
- species identifiable: `MISSING_EVIDENCE`
- diagnostic trait visible: `MISSING_EVIDENCE`
- distractor plausibility: `MISSING_EVIDENCE`
- feedback usefulness: `MISSING_EVIDENCE`
- difficulty appropriateness: `MISSING_EVIDENCE`
- global pedagogical value: `MISSING_EVIDENCE`

Decision: `FAIL`

## 15. Final decision

Decision: `GO_WITH_WARNINGS`

Rationale:

- Hard technical gates for qualification and v2 option contract are strong enough to audit Palier 1 now.
- Promotion-quality evidence is still incomplete on feedback coverage, manual pedagogical scoring, fresh DB-backed smoke/cost lineage, and rerun runtime E2E trace.

## 16. Required corrections before next phase

- P0:
  - generate a fresh consolidated smoke report with accessible DB credentials and explicit run id lineage
  - execute and document manual pedagogical review (30-50 questions) with scored rubric
  - compute current feedback coverage (`feedback_short`, `what_to_look_at_general`, `what_to_look_at_specific`, `confusion_hint`) from current playable corpus
- P1:
  - produce complete pre-AI rejection counters (`duplicate_pre_ai`, `decode_error_pre_ai`, `blur_pre_ai`) and savings rate in the report
  - rerun runtime-app E2E evidence for `selectedOptionId` and link exact test execution timestamp
- P2:
  - reduce `diversity_fallback_only` share and distractor repetition metrics before Palier 2 stress

## 17. References

- `docs/runbooks/pre-scale-ingestion-roadmap.md`
- `docs/runbooks/ingestion-quality-gates.md`
- `docs/runbooks/ingestion-code-to-gate-map.md`
- `docs/archive/superseded-contracts/phase3-distractor-strategy.md`
- `docs/archive/evidence/2026-04/phase2_playable_corpus_report.v1.json`
- `data/qualified/phase2-birds-be-20260429T083143Z-a1.json`
- `data/normalized/phase2-birds-be-20260429T083143Z-a1.json`
- `data/raw/inaturalist/phase2-birds-be-20260429T083143Z-a1/manifest.json`
- `data/exports/phase3_pedagogical/pack_compiled_v2_pedagogical_calibrated.json`
- `data/exports/phase3_pedagogical/pack_materialization_v2_pedagogical_calibrated.json`
- `docs/audits/learning-loop-audit-v0.md`
