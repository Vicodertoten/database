---
owner: database
status: stable
last_reviewed: 2026-05-04
source_of_truth: docs/audits/pmp-policy-v1-human-review-ai-labeling.md
scope: audit
---

# PMP policy v1 human review AI labeling

## Purpose

Create structured calibration labels from human-written review notes in the PMP
human review CSV, while preserving auditability and preserving doctrine
boundaries.

This pass does not change PMP policy thresholds and does not execute broader
corpus runs.

## Input file

- docs/audits/human_review/pmp_policy_v1_human_review_sample.csv

## Output files

- docs/audits/human_review/pmp_policy_v1_human_review_ai_labeled.csv
- docs/audits/human_review/pmp_policy_v1_human_review_ai_labeled.jsonl
- docs/audits/evidence/pmp_policy_v1_human_review_ai_labeling_audit.json

## Labeling schema

Each row receives inferred fields:
- human_overall_judgment_inferred
- human_basic_identification_judgment_inferred
- human_field_observation_judgment_inferred
- human_confusion_learning_judgment_inferred
- human_morphology_learning_judgment_inferred
- human_species_card_judgment_inferred
- human_indirect_evidence_learning_judgment_inferred
- human_evidence_type_judgment_inferred
- human_field_marks_judgment_inferred
- human_issue_categories
- calibration_priority
- ai_inference_confidence
- ai_inference_rationale
- labeling_source (ai, rule, none)

Allowed values are strict and validated in the script:
- overall: accept, too_permissive, too_strict, unclear, reject, blank
- per-usage: agree, too_permissive, too_strict, not_sure, blank
- evidence type: correct, wrong, too_specific, too_generic, not_sure, blank
- field marks: useful, partially_useful, generic, wrong, not_sure, blank

## AI role

AI is optional and text-only.

When enabled with credentials, the script sends compact per-row text context to
Gemini and expects strict JSON output constrained to allowed values.

AI does not inspect images and does not modify taxonomy, PMP profiles, policy
thresholds, runtime, or materialization.

## Rule-based fallback role

Deterministic fallback rules cover obvious note patterns, including:
- schema false negatives for profile_failed rows with strong positive photo notes,
- pre-AI false negatives when note says recognizable,
- target taxon mismatch from explicit mismatch notes,
- habitat too permissive signals,
- too strict or too permissive qualitative notes,
- global score uncertainty and second-review routing.

When no note exists, labels remain blank with conservative low-priority
classification.

## Limitations

- AI labels are inferred interpretations of human notes, not human truth.
- Empty or ambiguous notes produce blank or not_sure style outputs by design.
- This process cannot resolve image-level ambiguity without a separate image-based
  second review task.

## Audit summary (current run)

From docs/audits/evidence/pmp_policy_v1_human_review_ai_labeling_audit.json:
- input_rows: 40
- rows_with_human_notes: 37
- rows_without_human_notes: 3
- rows_ai_labeled: 0
- rows_rule_labeled: 37
- rows_unlabeled: 3
- overall_judgment_distribution: accept=19, too_strict=3, too_permissive=1,
  unclear=14, blank=3
- calibration_priority_distribution: high=3, medium=16, low=21
- high_priority_items: pmp-policy-review-0037, pmp-policy-review-0072,
  pmp-policy-review-0104

Interpretation:
- the workflow executed correctly,
- deterministic rule-based labeling captured obvious note signals,
- the remaining ambiguous rows were routed to unclear/not_sure or left blank.

## Recommended next calibration actions

1. Complete human_notes in the review CSV for rows where calibration signals are
   needed.
2. Re-run the labeling script with the same input/output paths.
3. Review high-priority and needs_second_review subsets before any threshold
   changes.
4. Keep threshold changes as a separate, explicitly reviewed step.

## Doctrine statement

AI-inferred labels are structured interpretations of human notes. They must be
reviewed by humans before any policy threshold or calibration decision is
adopted.
