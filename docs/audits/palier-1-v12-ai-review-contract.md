---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-02
source_of_truth: docs/audits/palier-1-v12-ai-review-contract.md
scope: audit
---

# Palier 1 v1.2 AI Review Contract

## 1. Goal

Define a strict AI review contract for bird images that improves pedagogical quality
without changing runtime contracts.

Primary decision for v1.2:

- no pre-answer hints
- only post-answer feedback (`correct`, `incorrect`, `identification_tips`)

## 2. AI role in v1.2

The AI analyzes one image tied to a known species and returns structured pedagogical
signals.

The AI does not:

- change canonical taxonomy
- override the provided species
- compute the final pedagogical score

The AI can fail only for obvious non-usable cases (image access, non-bird subject,
strong blur/occlusion, insufficient usable information, invalid output).

## 3. Versioned contract

- prompt version: `bird_image_review_prompt.v1.2`
- schema version: `bird_image_pedagogical_review.v1.2`
- schema path: `schemas/bird_image_pedagogical_review_v1_2.schema.json`
- parser/normalizer/validator: `src/database_core/qualification/bird_image_review_v12.py`

## 4. Output structure

Success payload (strict JSON):

- `status=success`
- `failure_reason=null`
- `image_assessment`
- `pedagogical_assessment`
- `identification_features_visible_in_this_image`
- `post_answer_feedback`
- `limitations`
- `overall_confidence`

Failed payload (strict JSON):

- `status=failed`
- required `failure_reason`
- `overall_confidence=0`

## 5. Failure reasons (controlled enum)

- `image_not_accessible`
- `non_bird_subject`
- `subject_too_occluded`
- `image_too_blurry`
- `insufficient_information`
- `unsafe_or_invalid_content`
- `model_output_invalid`
- `schema_validation_failed`

## 6. Validation rules

Mandatory rules:

- strict JSON object only
- required `schema_version`, `prompt_version`, `status`
- `status in {success, failed}`
- confidence values in `[0,1]`
- success payload requires full assessment sections
- success payload requires post-answer feedback (`correct.short`, `correct.long`,
  `incorrect.short`, `incorrect.long`, `identification_tips>=2`)
- success payload requires `identification_features_visible_in_this_image>=1`
- failed payload requires `failure_reason` and `overall_confidence=0`

Any invalid output must fail closed.

## 7. Fail-closed behavior

Parser behavior in `bird_image_review_v12.py`:

- invalid JSON -> `failed/model_output_invalid`
- schema mismatch -> `failed/schema_validation_failed`
- non-playable success payload -> `failed/insufficient_information`

A failed review is never playable/mature.

## 8. Deterministic score decomposition

The system computes the score deterministically from AI signals:

- technical_quality: 20 points
- subject_visibility: 20 points
- diagnostic_feature_visibility: 25 points
- representativeness: 15 points
- feedback_quality: 20 points

Mapping:

- `high=1.0`
- `medium=0.6`
- `low=0.25`
- `none/unusable=0`

Score helper:

- `compute_bird_image_pedagogical_score_v12` in
  `src/database_core/qualification/bird_image_review_v12.py`

## 9. Compatibility note

This v1.2 contract is additive.

- Runtime contracts remain unchanged.
- Existing playable contracts (`playable_corpus.v1`, `pack.compiled.v1`,
  `pack.materialization.v1`) are unchanged.
- `PedagogicalImageProfile` now prioritizes post-answer feedback while keeping legacy
  fields for backward compatibility.
