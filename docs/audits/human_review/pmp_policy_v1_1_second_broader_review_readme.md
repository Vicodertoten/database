---
owner: vicodertoten
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/human_review/pmp_policy_v1_1_second_broader_review_sheet.csv
scope: pmp_policy_v1_1_second_broader_review
---

# PMP Policy v1.1 — Second Broader Review Sheet README

## Purpose

This is a targeted human review sheet for Sprint 10, validating the effect of Sprint 9 Phase 2 calibration patches (policy v1.1) on the broader_400 snapshot.

**Do not use this sheet to evaluate media usefulness in general.**
This review is specifically about whether policy v1.1 behavior is correct compared to what a human would expect.

Total items: **80**

## What Changed Since the Previous Review

Sprint 9 Phase 2 applied the following patches:

1. **Schema normalization**: `body→whole_body`, `sitting→resting`, biological basis null downgrade. Fixes 4 schema false negatives.
2. **Species card calibration**: stricter thresholds + severe limitation keyword detection (distant, silhouette, obscured).
3. **Habitat calibration**: generic habitat now downgrades `indirect_evidence_learning`.
4. **Optional signals**: `target_taxon_visibility`, `contains_visible_answer_text`, `contains_ui_screenshot` consumed by policy when present.

## What to Check

For each item, review the image and the current policy outcome. Ask:

- Does the `policy_status_current` make sense for this image?
- Does the `recommended_uses_current` accurately reflect what this image can teach?
- If the item was previously a human-flagged issue, has the issue been resolved?
- Is there an unexpected regression (previously acceptable, now too strict)?
- Is there still a policy permissiveness problem?

## How to Fill Fields

### `second_review_decision`
**Required.** One of:
- `accept` — policy outcome is appropriate
- `too_strict` — policy is stricter than warranted
- `too_permissive` — policy is more permissive than warranted
- `reject` — item should not be used for any learning purpose
- `unclear` — uncertain; leave a note

### `second_review_main_issue`
**Optional but recommended.** One of:
- `none` — no issue
- `still_too_strict` — patch did not fix a too_strict case
- `still_too_permissive` — patch did not fix a too_permissive case
- `fixed` — patch resolved the previous issue
- `regression` — patch introduced a new problem
- `target_taxon_issue` — problem with target visibility
- `habitat_issue` — problem with habitat classification
- `species_card_issue` — problem with species_card eligibility
- `visible_text_issue` — problem with visible answer text detection
- `schema_failure` — still failing at schema level
- `other` — other issue (explain in notes)

### `second_review_notes`
**Optional.** Free text notes about the decision.

## What NOT to Judge

- Do not judge media aesthetic quality beyond what affects learning utility.
- Do not re-assess taxonomy (species name is fixed).
- Do not assess whether runtime should select this item (out of scope).
- Do not assess pack composition (out of scope).

## How Optional Signals Are Evaluated

Some items include pre-filled optional signals in the columns:
- `target_taxon_visibility_if_available`
- `contains_visible_answer_text_if_available`
- `contains_ui_screenshot_if_available`
- `habitat_specificity_if_available`

These signals are annotated from the optional signal sheet and, where present, are injected into policy v1.1 evaluation. The `usage_statuses_current` already reflects these injected signals.

If you disagree with a signal value, note it in `second_review_notes`.

## Decision Criteria After Review

After this review is filled, the analysis script (`scripts/analyze_pmp_policy_v1_1_second_review.py`) will compute:

- Overall accept/too_strict/too_permissive/reject distribution
- Fixed count (previous issues now resolved)
- Regression count (new issues introduced by patch)
- Category-specific outcomes

Decision labels that the analysis will produce:
- `READY_FOR_FIRST_PROFILED_CORPUS_CANDIDATE` — patches validated, no critical regressions
- `NEEDS_POLICY_V1_2_CALIBRATION` — significant issues remain
- `NEEDS_MORE_TARGET_SIGNAL_WORK` — optional signals need more work
- `INVESTIGATE_REGRESSIONS` — unexpected regressions detected

## Category Coverage

| Category | Count |
|---|---|
| schema_false_negative | 4 |
| profile_failed_current | 4 |
| same_species_multiple_individuals_ok | 5 |
| multiple_species_target_unclear | 4 |
| habitat_generic | 2 |
| habitat_species_relevant | 1 |
| species_card_downgraded | 9 |
| species_card_eligible | 22 |
| text_or_screenshot | 1 |
| field_observation_borderline | 8 |
| stable_accepted_control | 37 |