---
owner: database
status: stable
last_reviewed: 2026-05-05
source_of_truth: docs/foundation/pmp-qualification-policy-v1.md
scope: foundation
---

# PMP qualification policy v1

## Purpose

Define the first PMP-native qualification policy layer that converts
`pedagogical_media_profile_v1` outcomes into deterministic database policy
statuses.

This policy layer is separate from runtime or pack selection.

Core doctrine:
- database qualifies now,
- downstream systems select later,
- review validity is separate from media usefulness,
- weak usefulness is not failure,
- evidence type matters,
- usage scores are primary for usage decisions,
- `global_quality_score` is a broad signal, not a final selection score.

## Scope

In scope:
- PMP review validity interpretation,
- PMP usage-level policy interpretation,
- PMP policy status generation,
- evidence-type-aware usage policy statuses,
- database-only recommendation outputs.

Out of scope:
- runtime readiness,
- selectedOptionId,
- pack materialization,
- final quiz selection,
- feedback generation,
- distractors,
- runtime fields in PMP contract.

## Policy layers

1. PMP review validity (`pmp_review_status`)
- `valid`
- `failed`

This is inherited from PMP output (`review_status`).

2. PMP usage profile usability (`pmp_usage_statuses`)
For each usage:
- `basic_identification`
- `field_observation`
- `confusion_learning`
- `morphology_learning`
- `species_card`
- `indirect_evidence_learning`

Status per usage:
- `eligible`
- `borderline`
- `not_recommended`
- `not_applicable`

Meaning clarification:
- `confusion_learning` is an image/profile-level signal.
- It indicates that the media may be useful for learning discriminative visual
  criteria.
- It does not imply distractor readiness.
- It does not imply similar-species candidate availability.
- It does not imply that a confusion-training quiz can already be generated.
- Confusion-set generation remains a separate future layer.

3. PMP policy status (`pmp_policy_status`)
- `profile_valid`
- `profile_failed`
- `pre_ai_rejected`
- `policy_not_applicable`
- `policy_error`

4. Downstream selection
Out of scope for this policy and not encoded in PMP contract.

## v1 heuristic thresholds

These are provisional Sprint 7 heuristic thresholds to calibrate with broader
profiled corpus evidence.

Base thresholds (usage score):
- `eligible`: score >= 70
- `borderline`: 50 <= score <= 69
- `not_recommended`: score < 50
- `not_applicable`: usage not meaningful for evidence type or score missing

Stricter rules by evidence type may override base thresholds.

## Threshold calibration warnings

These thresholds are heuristic v1 defaults, not final truth.

Warnings:
- `eligible >= 70` is a calibration starting point, not a permanent rule.
- `field_observation` may currently be permissive and needs human review.
- `species_card` may currently be permissive and likely needs stricter review.
- broader corpus audit may reveal taxon-specific or evidence-type-specific bias.
- human review must check whether usage eligibility is too broad or too strict.

Open calibration questions are tracked in:
`docs/audits/pmp-policy-v1-open-questions.md`

## Status mapping rules

- PMP `review_status=failed` -> `pmp_policy_status=profile_failed`
- pre-AI source statuses (`insufficient_resolution_pre_ai`, `blur_pre_ai`, etc.)
  -> `pmp_policy_status=pre_ai_rejected`
- Missing PMP profile with non-PMP contract -> `policy_not_applicable`
- Missing PMP profile where PMP contract is expected -> `policy_error`
- PMP `review_status=valid` -> `profile_valid`

## Evidence-type-aware interpretation

### whole_organism
- `basic_identification`, `field_observation`, `morphology_learning` can be
  `eligible` at score >= 70.
- `indirect_evidence_learning` is not primary; usually `not_applicable` or
  `borderline` unless high score.

### multiple_organisms
- `field_observation` often useful.
- `species_card` is stricter than base thresholds.
- `basic_identification` can still be `borderline`/`eligible` when score supports it.

Phase 2 calibration note:
- same-species multiple individuals are often acceptable and should not be
  automatically penalized when target identity remains clear;
- mixed-species frames with unclear target should downgrade
  `basic_identification` / `confusion_learning` and block `species_card`;
- this uses `target_taxon_visibility` as a policy-side concept, not a taxonomic
  override and not a runtime selection field.

### feather / nest / track / scat / burrow / habitat / dead_organism / egg
- `basic_identification` usually `not_recommended`.
- `indirect_evidence_learning` can be `eligible` at score >= 70.
- `field_observation` can be `eligible` at score >= 70.
- `species_card` is stricter and usually not recommended unless score strongly
  supports it.

Phase 2 calibration note for `habitat`:
- generic habitat or feeder/garden context is weak species-level evidence and
  should not be over-promoted;
- `habitat` indirect evidence is stricter than `feather` / `nest` /
  `dead_organism`;
- species-relevant ecological signs such as woodpecker foraging damage can still
  support `indirect_evidence_learning` when score is high enough.

### partial_organism
- score-driven interpretation is retained,
- stricter for `basic_identification` and `species_card`.

## global_quality_score interpretation

`global_quality_score` remains a broad multi-use signal.

Policy guardrail:
- high `global_quality_score` alone must not force
  `basic_identification=eligible`.
- usage-specific eligibility is driven by usage scores and evidence type.

## visible_answer_text_or_ui_overlay

Meaning:
- the media contains visible text or UI that reveals the species answer, or is a
  screenshot/app artifact.

Policy effect:
- unsuitable for `basic_identification`, `confusion_learning`, and
  `species_card`;
- in v1.1 policy calibration, explicit flags can also downgrade
  `field_observation` and `morphology_learning` because the artifact itself is
  pedagogically contaminating.

Implementation boundary:
- no OCR is implemented in v1.1;
- no filename heuristics are used;
- policy only reacts when explicit optional context flags are present.

Optional context flags accepted by policy:
- `contains_visible_answer_text`
- `contains_ui_screenshot`

These are policy-side hints only. They are not runtime fields and are not part
of quiz selection logic.

## target_taxon_visibility

Policy may consume an optional `target_taxon_visibility` hint.

Current policy-side interpretations:
- `multiple_individuals_same_taxon`: same-species groups can remain useful for
  `basic_identification`, `morphology_learning`, and `field_observation` when
  scores support them;
- `multiple_species_target_unclear`: downgrade identification-oriented uses and
  block `species_card`;
- `target_not_visible`: identification-oriented uses are not recommended; field
  observation may remain only as limited context.

This concept:
- does not rename the taxon,
- does not override canonical identity,
- does not introduce `selectedOptionId`,
- does not add runtime coupling.

## species_card calibration

`species_card` is intentionally stricter than `basic_identification`.

Phase 2 v1.1 guidance:
- representative whole-organism media can remain eligible;
- same-species multiple-individual media can remain borderline/eligible when the
  target remains clear and the image is representative;
- severe limitations should downgrade `species_card`, including:
  `subject too small`, `small in frame`, `low resolution`, `silhouette only`,
  `heavily obscured`, `lack of detail`, explicit target ambiguity, or visible
  answer/UI contamination.

This does not require perfect media.
It requires that `species_card` remain more representative than a merely usable
field observation.

## field_observation clarification

`field_observation` is intentionally broader than `basic_identification`.

It can be useful for:
- real-world context,
- posture,
- distance and viewing difficulty,
- habitat or behavior context,
- realistic field conditions.

It does **not** mean:
- quiz-ready,
- species-card ready,
- clean identification,
- generally high quality.

Phase 2 decision:
- no broad threshold change was applied;
- field observation remains broad by design;
- only explicit severe flags (for example visible answer text / UI artifact or
  target not visible) justify policy downgrades in v1.1.

## Policy output contract (separate from PMP contract)

Policy output is an adjacent layer and must not mutate PMP payload fields.

Example shape:

```json
{
  "policy_version": "pmp_qualification_policy.v1",
  "policy_status": "profile_valid",
  "review_status": "valid",
  "evidence_type": "whole_organism",
  "global_quality_score": 84,
  "usage_statuses": {
    "basic_identification": {
      "status": "eligible",
      "score": 82,
      "reason": "score_above_threshold"
    }
  },
  "eligible_database_uses": ["basic_identification", "field_observation"],
  "not_recommended_database_uses": ["indirect_evidence_learning"],
  "policy_notes": []
}
```

Forbidden in policy output and PMP contract:
- `playable`
- `selected_for_quiz`
- `runtime_ready`
- `selectedOptionId`
- any feedback fields

## Sprint 6 grounding

Sprint 6 controlled run established:
- PMP generation validity (`pmp_valid_rate = 91.38%`),
- no doctrine pollution,
- evidence-type score distribution requiring usage-aware interpretation.

This policy v1 intentionally uses usage-centric eligibility and avoids a single
collapsed "playable" decision.

## Known limitations

- v1 thresholds are heuristic and need broader corpus calibration.
- current policy is still bird-first in observed data, even though contract is
  multi-taxon oriented.
- policy outputs are recommendations for database usage, not final selection.
- rare model-subject misses can still occur for extremely distant subjects;
  these remain second-review notes rather than a new policy category in v1.1.
