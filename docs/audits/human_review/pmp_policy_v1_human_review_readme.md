---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/audits/human_review/pmp_policy_v1_human_review_readme.md
scope: audit
---

# PMP policy v1 human review sample

## Purpose

This review file is used to calibrate `pmp_qualification_policy.v1` on real PMP
outputs.

Reviewers are judging whether the PMP profile plus deterministic policy output is
reasonable as a database-level usage signal.

## What reviewers should judge

- whether `evidence_type` looks correct,
- whether visible field marks are useful and specific enough,
- whether the usage scores and policy statuses seem too permissive or too strict,
- whether indirect evidence is handled sensibly,
- whether the policy preserves nuance instead of collapsing into one decision.

## What reviewers should not judge

- runtime readiness,
- pack selection,
- whether a quiz should be generated now,
- distractor set availability,
- selectedOptionId,
- feedback wording.

## PMP profile vs policy

- PMP profile: structured review of the media itself.
- Policy: deterministic database interpretation of PMP outputs for usage-level
  eligibility.

A valid PMP profile may still be weak for some uses.
That is not a failure.

## Usage interpretation reminders

- `basic_identification`: image usefulness for direct species-level
  identification learning.
- `field_observation`: usefulness for observational learning in field context.
- `confusion_learning`: image/profile-level suitability for learning
  discriminative visual criteria.

Important:
`confusion_learning` does **not** mean distractor readiness.
It does not imply that similar-species candidates are already available or that
confusion-training quiz generation is implemented.
That remains a separate future layer.

- `morphology_learning`: usefulness for learning morphology and visible form.
- `species_card`: suitability as a species-card style illustration; this may
  need stricter calibration.
- `indirect_evidence_learning`: usefulness for learning from indirect evidence
  such as feathers, nests, tracks, scat, habitat, or dead organisms.

## global_quality_score reminder

`global_quality_score` is a broad multi-use quality signal.
It is not a final selection score.
High global score alone must not force a usage to be considered eligible.

## Human judgment values

Overall:
- `accept`
- `too_permissive`
- `too_strict`
- `unclear`
- `reject`

Per-usage:
- `agree`
- `too_permissive`
- `too_strict`
- `not_sure`

Evidence type:
- `correct`
- `wrong`
- `too_specific`
- `too_generic`
- `not_sure`

Field marks:
- `useful`
- `partially_useful`
- `generic`
- `wrong`
- `not_sure`

## How to fill the CSV

Review one row at a time:
1. inspect identity and image traceability columns,
2. read PMP evidence type, visible marks, limitations, and scores,
3. inspect policy statuses and eligible/borderline/not-recommended uses,
4. fill overall and per-usage human judgment columns,
5. add concise notes when the policy seems too broad or too strict.

## How results will be used

Human review disagreements will be used to:
- calibrate thresholds,
- tighten or relax evidence-type-specific rules,
- identify whether some policy uses should remain purely descriptive,
- guide Sprint 9 threshold work before any broader policy promotion.

## Attribution and privacy notes

Image URLs may point to iNaturalist assets.
Use them only for calibration and review in repository governance scope.
Respect original source attribution and licensing context.
