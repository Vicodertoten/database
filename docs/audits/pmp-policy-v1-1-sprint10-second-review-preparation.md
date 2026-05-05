---
owner: vicodertoten
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/evidence/pmp_policy_v1_1_broader_400_delta_audit.json
scope: pmp_policy_v1_1_sprint10_second_review_preparation
---

# PMP Policy v1.1 — Sprint 10: Second Broader Review Preparation

## Purpose

Sprint 10 prepares and validates the second targeted broader review for PMP policy v1.1.

The goal is to confirm that Sprint 9 Phase 2 calibration patches improve sensitive cases
without causing regressions, and to produce a targeted second review sheet that can validate
the patches with human judgment.

Final status: **READY_FOR_TARGETED_SECOND_REVIEW**

---

## Sprint 9 Phase 2 Recap

Sprint 9 Phase 2 concluded with status `READY_FOR_SECOND_BROADER_REVIEW` after applying:

1. **Schema normalization** (`pedagogical_media_profile_v1.py`)
   - `bird_visible_parts: body → whole_body`
   - `posture: sitting → resting`
   - Biological basis null with concrete value: downgrade `value → unknown`, `confidence → low`
   - Fixes 4 schema false negatives from broader_400 review

2. **Prompt tightening** (`pedagogical_media_profile_prompt_v1.py`)
   - Explicit enum constraints; forbidden values documented
   - `visible_basis` requirement strengthened

3. **Policy optional signals** (`pmp_policy_v1.py`)
   - `target_taxon_visibility` consumed when present
   - `contains_visible_answer_text` and `contains_ui_screenshot` block most uses
   - `multiple_species_target_unclear` → borderline basic_identification + not_recommended species_card

4. **Species card calibration** (`pmp_policy_v1.py`)
   - Stricter thresholds: eligible ≥ 80, borderline ≥ 65
   - Severe limitation keywords (distant, silhouette, heavily obscured, etc.) →
     species_card not_recommended

5. **Habitat calibration** (`pmp_policy_v1.py`)
   - Generic habitat with no species-relevant signal → indirect_evidence_learning downgraded
   - New constant: `HABITAT_INDIRECT_ELIGIBLE_THRESHOLD = 85.0`

6. **Out of scope (explicitly not done)**
   - No PMP schema expansion
   - No OCR / screenshot detection
   - No runtime changes
   - No materialization / Supabase writes
   - No default behavior changes

---

## Delta Audit Result

**Script**: `scripts/audit_pmp_policy_v1_1_delta.py`

**Evidence**: `docs/audits/evidence/pmp_policy_v1_1_broader_400_delta_audit.json`

**Report**: `docs/audits/pmp-policy-v1-1-broader-400-delta-audit.md`

### Summary

| Metric | Count |
|---|---|
| Total rows | 60 |
| Comparable | 60 |
| Fully stable | 35 |
| Calibration downgrades (intentional) | 11 |
| Regressions (unexpected) | 0 |
| Species card downgraded | 9 |
| Habitat indirect downgraded | 2 |

**Decision: READY_FOR_SECOND_REVIEW_SHEET**

### Key findings

- **0 unexpected regressions**: No item that was human-accepted lost eligible uses due to
  an unintentional policy change.
- **9 species_card downgrades**: Items with distant/silhouette/obscured limitations now have
  species_card not_recommended. These are intentional calibration changes, not regressions.
- **2 habitat indirect downgrades**: Generic habitat items (e.g. bird feeder) now have
  indirect_evidence_learning downgraded. Intentional.
- **Schema false negatives**: The 4 schema false-negative items remain `profile_failed` in
  the stored ai_outputs.json because normalization patches apply during pipeline ingestion
  (not retroactively to stored data). Their fix is validated separately via fixture tests.
  These items appear in the second review sheet to allow human validation.

---

## Optional Signal Annotation Status

**Sheet**: `docs/audits/human_review/pmp_policy_v1_1_optional_signal_annotations.csv`

**README**: `docs/audits/human_review/pmp_policy_v1_1_optional_signal_annotations_readme.md`

19 items annotated, covering all non-trivial issue categories from the Phase 1 review:
- 4 `schema_false_negative` items
- 4 `multiple_species_target_unclear` items (annotated `target_taxon_visibility=multiple_species_target_unclear`)
- 5 `same_species_multiple_individuals_ok` items (annotated `target_taxon_visibility=multiple_individuals_same_taxon`)
- 1 `text_overlay_or_answer_visible` item (annotated `contains_ui_screenshot=true`)
- 1 `habitat_too_permissive` item (annotated `habitat_specificity=generic`)
- Other sensitive categories

Signals are injected during policy evaluation for annotated items. The second review sheet
shows both the base policy behavior and the signal-augmented behavior where applicable.

---

## Second Review Sheet Summary

**Script**: `scripts/export_pmp_policy_v1_1_second_review.py`

**Output CSV**: `docs/audits/human_review/pmp_policy_v1_1_second_broader_review_sheet.csv`

**Output JSONL**: `docs/audits/human_review/pmp_policy_v1_1_second_broader_review_sheet.jsonl`

**README**: `docs/audits/human_review/pmp_policy_v1_1_second_broader_review_readme.md`

### Row count and category coverage

| Category | Description |
|---|---|
| schema_false_negative | Items that were profile_failed due to schema mismatch |
| profile_failed_current | Items still profile_failed after patches |
| same_species_multiple_individuals_ok | Multiple individuals, same taxon |
| multiple_species_target_unclear | Mixed-species, target unclear |
| habitat_generic | Generic habitat; indirect_evidence_learning downgraded |
| habitat_species_relevant | Species-relevant habitat evidence |
| species_card_downgraded | Items where species_card was downgraded by v1.1 |
| species_card_eligible | Items still eligible for species_card |
| text_or_screenshot | Items with UI screenshot / visible answer text |
| field_observation_borderline | Distant/silhouette items with field_observation only |
| stable_accepted_control | Previously accepted items; validate no regression |

Total: **80 rows** (60 from Phase 1 labeled review + 20 supplemental from broader_400)

Sampling is deterministic (fixed algorithm; no random seed dependency).

---

## Analysis Script Status

**Script**: `scripts/analyze_pmp_policy_v1_1_second_review.py`

**Output JSON**: `docs/audits/evidence/pmp_policy_v1_1_second_broader_review_analysis.json`

**Output MD**: `docs/audits/pmp-policy-v1-1-second-broader-review-analysis.md`

Current status (pre-review): `NEEDS_SECOND_REVIEW_COMPLETION`

The script runs correctly before and after the review is filled. Once the second review sheet
is filled, re-running the script will produce the final decision label.

---

## Limitations

1. **Schema false negative validation**: The Sprint 9 Phase 2 normalization patches
   (body→whole_body, sitting→resting, biological basis null downgrade) are applied during
   pipeline ingestion in `pedagogical_media_profile_v1.py`. The stored `ai_outputs.json`
   retains the original failing profiles. The delta audit cannot detect these fixes from
   stored data. Validation is via `tests/test_audit_pedagogical_media_profile_v1_fixture_dry_run.py`
   and `tests/test_pedagogical_media_profile_v1.py`.

2. **Optional signals not routinely produced**: `target_taxon_visibility`,
   `contains_visible_answer_text`, `contains_ui_screenshot` are manually annotated in
   this sprint. The Gemini prompt does not yet produce them. Future schema expansion is
   out of scope for Sprint 10.

3. **Before/after comparison**: The delta audit "before" state is reconstructed from the
   labeled CSV columns (`policy_status`, `recommended_uses`, `borderline_uses`), not from
   a re-run of policy v1.0. This is a faithful approximation but not a strict recomputation.

4. **Supplemental items**: 20 non-labeled items from the broader_400 snapshot were added
   to the second review sheet to reach the 80-row target. These items have no prior human
   review baseline; they are included for coverage validation only.

---

## Sprint 10 Closure Notes

Post-review decision: **READY_FOR_FIRST_PROFILED_CORPUS_CANDIDATE**

1. **Schema false negatives — cached outputs need reprocessing or exclusion.**
   The 4 `schema_false_negative` items (all rated `too_strict` in the second review)
   are cached in `ai_outputs.json` with failing profiles. These items must either be
   reprocessed through the updated pipeline (so normalization patches apply) or explicitly
   excluded from the first corpus candidate. They must not enter the corpus as-is.

2. **Visible answer text / screenshot items must be excluded from first corpus candidate
   unless explicitly cleared.**
   Any item with `contains_visible_answer_text=true` or `contains_ui_screenshot=true`
   must be excluded by default from corpus candidacy. They may only be included if a
   separate human review explicitly clears them for a specific use case.

---

## What Remains Out of Scope

The following remain explicitly out of scope for Sprint 10:

- PMP schema expansion for optional signals
- OCR or screenshot detection (automated)
- Runtime session/scoring/progression logic
- Pack materialization
- Supabase/Postgres writes
- Distractor pipeline
- Default behavior changes

---

## Final Status

**READY_FOR_TARGETED_SECOND_REVIEW**

The delta audit shows 0 unexpected regressions and confirms intentional calibration
downgrades are working as designed. The second review sheet is prepared and ready for
human review. Once the review is filled, `scripts/analyze_pmp_policy_v1_1_second_review.py`
will compute the final verdict.
