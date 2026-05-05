---
owner: vicodertoten
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/evidence/pmp_policy_v1_1_broader_400_delta_audit.json
scope: pmp_policy_v1_1_delta_audit
---

# PMP Policy v1.1 Delta Audit — broader_400

## Purpose

Compare broader_400 human review / recorded policy evidence (policy v1.0) against current policy v1.1 behavior. Validate that Sprint 9 Phase 2 calibration patches improve sensitive cases without causing regressions on previously accepted media.

## Inputs

- `docs/audits/human_review/pmp_policy_v1_broader_400_20260504_human_review_labeled.csv` — 60-row human review with recorded policy columns (policy v1.0 era)
- `data/raw/inaturalist/palier1-be-birds-50taxa-run003-pmp-policy-broader-400-20260504/ai_outputs.json` — Gemini PMP outputs for 400 media (re-evaluated with policy v1.1)
- `docs/audits/human_review/pmp_policy_v1_1_optional_signal_annotations.csv` — optional; if present, optional signals (target_taxon_visibility etc.) are injected

## Limitations

- The `before` state is reconstructed from the labeled CSV `policy_status`, `recommended_uses`, and `borderline_uses` columns, which were recorded during the Sprint 9 broader_400 run. This is a faithful approximation of v1.0 behavior but not a recomputed policy run.
- Optional signal annotations (target_taxon_visibility, visible_answer_text, ui_screenshot) are injected if the annotation sheet exists, but these signals were not part of the original policy run. Changes driven by optional signals reflect new capabilities, not policy regressions.
- Rows not matched in ai_outputs.json are excluded from comparison.

## What Changed (Policy v1.0 → v1.1)

Sprint 9 Phase 2 applied the following patches:

1. **Schema normalization**: `body → whole_body`, `sitting → resting`, biological basis null downgrade to `unknown` — fixes 4 schema false negatives.
2. **Species card calibration**: stricter thresholds; severe limitation keywords (distant, silhouette, heavily obscured) now downgrade species_card to not_recommended.
3. **Habitat indirect evidence**: generic habitat with no species-relevant signal now downgrades indirect_evidence_learning.
4. **Optional signals**: target_taxon_visibility, contains_visible_answer_text, contains_ui_screenshot now consumed by policy when present.

## Results

| Metric | Count |
|---|---|
| Total rows | 60 |
| Comparable rows | 60 |
| Not comparable | 0 |
| Fully stable | 49 |
| Calibration downgrades (intentional) | 10 |
| Regressions (unexpected) | 0 |
| Improvements | 0 |
| Changed (neutral) | 1 |
| Schema false negatives fixed | 0 |
| Species card downgraded | 9 |
| Habitat indirect downgraded | 2 |

## Human Judgment Alignment

| Judgment Category | Count |
|---|---|
| Human accept, still valid | 50 |
| Human too_permissive, now downgraded | 1 |
| Human too_strict, now improved | 0 |

## Sensitive Case Summary

- **Schema false negatives**: 4 items (body, sitting, biological basis null) were normalized in Sprint 9 Phase 2. These should now appear as profile_valid instead of profile_failed.
- **Species card**: Items with distance/silhouette/obscured limitations should see species_card downgraded. This is intentional.
- **Habitat**: Generic habitat (e.g. bird feeder with no species signal) should see indirect_evidence_learning downgraded. Intentional.
- **Multiple species target unclear**: 4 items flagged in human review; policy now applies basic_identification/confusion_learning borderline + species_card not_recommended when target_taxon_visibility signal is present.

## Risk of Regressions

- Schema normalization: low risk — fixes clear failures.
- Species card calibration: medium risk — threshold-based; borderline items may shift. Human second review will validate.
- Habitat: low risk for specific habitat; medium for generic habitat (expected downgrade).
- Optional signals: no risk from policy perspective (additive only when signals are present).

## Recommendation for Second Review Sample

Prioritize the following categories in the second broader review sheet:

1. Species_card downgraded items — validate downgrade is appropriate.
2. Schema false negative items — confirm they now pass.
3. Habitat items — validate indirect_evidence_learning behavior.
4. Multiple_organisms items — validate target_taxon_visibility effect.
5. Stable accepted controls — confirm no silent regression.

## Decision

**READY_FOR_SECOND_REVIEW_SHEET**
