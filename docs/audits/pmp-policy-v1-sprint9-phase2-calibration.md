---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/pmp-policy-v1-sprint9-phase2-calibration.md
scope: audit
---

# PMP policy v1 Sprint 9 Phase 2 calibration

## Purpose

Apply only the targeted PMP / policy v1.1 calibration patches justified by the
broader_400 human review analysis from Sprint 9 Phase 1.

## Input evidence

- `docs/audits/evidence/pmp_policy_v1_broader_400_20260504_human_review_analysis.json`
- `docs/audits/pmp-policy-v1-broader-400-human-review-analysis.md`
- `docs/audits/human_review/pmp_policy_v1_broader_400_20260504_human_review_labeled.csv`
- `docs/audits/evidence/pmp_policy_v1_sprint9_phase2_schema_false_negative_analysis.json`

## Files changed

- `src/database_core/qualification/pedagogical_media_profile_v1.py`
- `src/database_core/qualification/pedagogical_media_profile_prompt_v1.py`
- `src/database_core/qualification/pmp_policy_v1.py`
- `tests/test_pedagogical_media_profile_v1.py`
- `tests/test_pmp_policy_v1.py`
- `docs/foundation/pmp-qualification-policy-v1.md`
- `docs/foundation/target-taxon-visibility-v1.md`
- `docs/foundation/habitat-evidence-policy-notes-v1.md`
- `docs/audits/evidence/pmp_policy_v1_sprint9_phase2_schema_false_negative_analysis.json`

## Patches applied

1. **Schema false-negative normalization fix**
   - normalize `bird_visible_parts=body` to `whole_body`;
   - normalize bird `posture=sitting` to `resting`;
   - downgrade unsupported biological claims with missing `visible_basis` to
     `unknown` instead of failing the whole PMP payload.

2. **Prompt tightening**
   - explicitly instruct the model not to use `body` or `sitting`;
   - explicitly instruct the model to downgrade unsupported biological claims to
     `unknown` instead of leaving `visible_basis=null`.

3. **Target taxon visibility policy support**
   - add policy-side optional support for `target_taxon_visibility` without PMP
     schema expansion;
   - distinguish `multiple_individuals_same_taxon`,
     `multiple_species_target_unclear`, and `target_not_visible`.

4. **Visible answer text / UI overlay policy support**
   - add policy-side optional support for:
     - `contains_visible_answer_text`
     - `contains_ui_screenshot`
   - when explicit flags are present, block quiz-like and representative uses.

5. **Habitat calibration**
   - generic habitat is downgraded for `indirect_evidence_learning`;
   - species-relevant habitat signs remain eligible when score support is high.

6. **Species-card calibration**
   - `species_card` is kept stricter than `basic_identification`;
   - severe weak-image limitations now downgrade representative-card eligibility.

## Patches explicitly not applied

- no PMP schema expansion for `target_taxon_visibility` yet;
- no OCR or screenshot detection pipeline;
- no runtime changes;
- no pack materialization;
- no Supabase/Postgres writes;
- no default switch to PMP/policy;
- no broader rerun;
- no distractor logic;
- no new complex pre-AI status chain.

## Schema false-negative analysis summary

Broader_400 Phase 1 surfaced 4 false negatives.
They were not broad contract failures.
They were concrete output-shape mismatches:

- `body` instead of `whole_body`;
- `sitting` instead of an allowed bird posture enum;
- two biological assertions with non-unknown values but missing `visible_basis`.

Decision:
- patch normalization + prompt;
- do not weaken schema;
- do not weaken biological rules.

## Pre-AI strictness decision

No code change was applied.

Evidence:
- one borderline item only;
- width was 500 px against current 512 px minimum;
- reviewer explicitly preferred staying strict to avoid future layout/crop issues.

Decision:
- keep pre-AI simple and strict;
- revisit only if broader evidence accumulates.

## Target taxon visibility decision

Decision:
- formalize the concept in documentation now;
- support it as optional policy context now;
- defer PMP schema expansion until recurrence justifies contract growth.

## Visible answer text policy

Decision:
- explicit flags can now block quiz-like and representative uses;
- no OCR or automatic screenshot detection in this phase.

## Habitat policy change

Decision:
- generic habitat is stricter;
- species-relevant ecological signs remain allowed when strongly supported.

## Species-card calibration

Decision:
- keep `species_card` stricter than `basic_identification`;
- downgrade weak, distant, small, silhouette-only, or strongly obscured media.

## Field-observation decision

Decision:
- keep broad by design;
- do not make a broad threshold change from one review item;
- only explicit severe flags trigger policy downgrades in this phase.

## Rare model-subject miss handling

Decision:
- document only;
- keep as rare/second-review note;
- do not add a new policy category yet.

## Tests run

- `./.venv/bin/python -m pytest tests/test_pedagogical_media_profile_v1.py -q`
- `./.venv/bin/python -m pytest tests/test_pmp_policy_v1.py -q`
- full targeted suite run after all edits

## Docs updated

- PMP policy foundation doc updated
- target taxon visibility foundation doc created
- habitat evidence notes created
- schema false-negative evidence JSON created

## Final decision

**READY_FOR_SECOND_BROADER_REVIEW**

Rationale:
- high-priority review issues now have targeted, tested patches;
- no broad contract weakening was introduced;
- no second validation run has happened yet;
- a second review on patched behavior is still required before promoting the
  calibrated policy further.
