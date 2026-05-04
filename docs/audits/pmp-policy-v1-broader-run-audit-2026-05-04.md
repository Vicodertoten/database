---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/audits/pmp-policy-v1-broader-run-audit-2026-05-04.md
scope: audit
---

# PMP policy v1 broader run audit - 2026-05-04

## Purpose

Record the first real broader PMP run on a deterministic 400-image subset,
compare it against the Sprint 6 controlled sample, and state the calibration
implications.

## Executed run

Source snapshot:
- `palier1-be-birds-50taxa-run003-v11-baseline`

Broader subset:
- `palier1-be-birds-50taxa-run003-pmp-policy-broader-400-20260504`

Subset characteristics:
- selected media: `400`
- selected taxa: `48`
- cap: `10` media per taxon

Qualification execution:
- processed media: `400`
- sent to Gemini: `390`
- pre-AI rejected: `10`
- Gemini `ok`: `383`
- PMP schema/profile failed: `7`

Primary evidence:
- `docs/audits/evidence/pedagogical_media_profile_v1_broader_400_20260504_snapshot_audit.json`
- `docs/audits/evidence/pmp_policy_v1_broader_400_20260504_snapshot_audit.json`

Human review sample:
- `docs/audits/human_review/pmp_policy_v1_broader_400_20260504_human_review_sample.csv`
- `docs/audits/human_review/pmp_policy_v1_broader_400_20260504_human_review_sample.jsonl`

## Success criteria verdict

### 1. `profile_valid >= 85%` on 400+ images

Met with margin.

- broader subset size: `400`
- `profile_valid / processed_media_count = 383 / 400 = 95.75%`
- `pmp_valid_rate` on Gemini-sent media: `98.21%`

### 2. Policy distributions stable enough to calibrate

Met, with an important nuance.

Doctrine and output shape are stable:
- doctrine pollution: `0`
- policy audit decision: `READY_FOR_BROADER_PROFILED_CORPUS_WITH_POLICY`
- PMP audit decision: `READY_FOR_CONTROLLED_PROFILED_CORPUS_RUN`
- global quality guardrail violations: `0`

Distribution levels are not numerically identical to Sprint 6. They shift
upward across most direct uses, which means the broader run is more permissive
in aggregate than the 120-image controlled slice. This does not look like a
policy break; it looks like Sprint 6 was a conservative sample and broader
coverage reduces failure concentration.

## Sprint 6 vs broader comparison

Sprint 6 baseline:
- processed: `120`
- `profile_valid`: `106` (`88.33%` of processed at policy layer)
- `profile_failed`: `10` (`8.33%`)
- `pre_ai_rejected`: `4` (`3.33%`)

Broader run:
- processed: `400`
- `profile_valid`: `383` (`95.75%` of processed)
- `profile_failed`: `7` (`1.75%`)
- `pre_ai_rejected`: `10` (`2.50%`)

Eligible-use ratio deltas versus Sprint 6:
- `basic_identification`: `43.33% -> 57.75%` (`+14.42 pts`)
- `field_observation`: `65.00% -> 79.00%` (`+14.00 pts`)
- `confusion_learning`: `34.17% -> 51.00%` (`+16.83 pts`)
- `morphology_learning`: `38.33% -> 53.50%` (`+15.17 pts`)
- `species_card`: `43.33% -> 57.00%` (`+13.67 pts`)
- `indirect_evidence_learning`: `5.83% -> 6.50%` (`+0.67 pts`)

Interpretation:
- the direct-use surfaces all rise together;
- indirect-evidence behavior remains nearly unchanged;
- the broader subset does not reveal a hidden collapse in PMP validity;
- calibration should now use the broader run as the main evidence base, not the
  Sprint 6 slice.

## Failure analysis

Observed failed PMP outputs: `7`

Failure causes:
- `invalid_biological_basis`: `4`
- `enum_mismatch`: `3`

Top failure paths:
- `biological_profile_visible.plumage_state.visible_basis`: `2`
- `biological_profile_visible.seasonal_state.visible_basis`: `2`
- `group_specific_profile.bird.bird_visible_parts.2`: `1`
- `group_specific_profile.bird.posture`: `1`
- `observation_profile.subject_presence`: `1`

Representative issues:
- model outputs `body` instead of allowed bird part vocabulary;
- model outputs `sitting` instead of allowed posture vocabulary;
- indirect evidence sometimes returns `subject_presence=clear` instead of
  `indirect`;
- biological visible states sometimes omit required `visible_basis` when value
  is specific.

Conclusion:
- these are prompt/schema-hardening issues, not evidence of broad policy drift;
- the failure count is low enough that they do not block calibration;
- they should be closed before any larger-scale PMP expansion.

## Taxon coverage

- broader subset covers `48` taxa versus `36` in the Sprint 6 audited slice;
- many taxa reach the intended `10` media cap;
- a few taxa remain under-filled (`2` to `6` media), which reflects source
  availability rather than subset bias.

Operational consequence:
- calibration conclusions are now substantially more representative than on the
  Sprint 6 controlled sample.

## Human review readiness

Broader human review sample exported:
- size: `60`
- includes failed cases: yes
- includes pre-AI cases: yes
- metadata join status: `joined_from_manifest`
- sample coverage includes indirect evidence, low basic-identification items,
  high-quality valid items, and partial/multiple-organism examples.

This sample is appropriate for the next calibration pass.

## Lessons learned

1. The broader run confirms that PMP is operationally stable on a larger bird
   subset.
2. The main remaining technical debt is schema/prompt hardening, not threshold
   collapse.
3. Sprint 6 was useful as a gate-opening sample, but it is too small to anchor
   threshold calibration by itself.
4. Indirect evidence behavior appears stable enough to keep in scope for policy
   calibration.
5. `field_observation` and `confusion_learning` remain the two usages most in
   need of human review scrutiny because they rose strongly in the broader run.

## Immediate next steps

1. Use the 60-row broader human review sample as the primary calibration input.
2. Prioritize review of:
   - `field_observation eligible` cases with weak basic identification,
   - `confusion_learning eligible` cases,
   - all `profile_failed` and `pre_ai_rejected` items in the sample,
   - indirect evidence cases marked `indirect_evidence_learning eligible`.
3. Open a focused hardening pass on PMP output validity for:
   - bird part enum normalization,
   - bird posture normalization,
   - indirect evidence `subject_presence`,
   - biological visible-state basis completion.
4. Base threshold discussion on broader ratios and human review, not on Sprint 6
   raw counts.

## Final decision

P1 broader corpus run is complete and successful.

The repo is now in the right state to start threshold calibration on a real
broader evidence base.