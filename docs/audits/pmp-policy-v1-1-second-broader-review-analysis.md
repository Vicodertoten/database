---
owner: vicodertoten
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/evidence/pmp_policy_v1_1_second_broader_review_analysis.json
scope: pmp_policy_v1_1_second_review_analysis
---

# PMP Policy v1.1 — Second Broader Review Analysis

## Purpose

Analyze results of the targeted second broader review (Sprint 10).
Validate whether Sprint 9 Phase 2 calibration patches (policy v1.1) improve sensitive cases without regressions.

## Review Status: READY_FOR_FIRST_PROFILED_CORPUS_CANDIDATE

- Total rows: 80
- Reviewed rows: 79
- Fill rate: 98.8%

## Decision Distribution

| Decision | Count | % |
|---|---|---|
| accept | 74 | 93.7% |
| too_strict | 4 | 5.1% |
| too_permissive | 1 | 1.3% |
| reject | 0 | 0.0% |
| unclear | 0 | 0.0% |

## Patch Effectiveness

| Metric | Count |
|---|---|
| Fixed | 1 |
| Still too strict | 0 |
| Still too permissive | 0 |
| Regression | 0 |

## Category Outcomes

| Category | accept | too_strict | too_permissive | reject | unclear |
|---|---|---|---|---|---|
| field_observation_borderline | 8 | 0 | 0 | 0 | 0 |
| habitat_generic | 2 | 0 | 0 | 0 | 0 |
| habitat_species_relevant | 1 | 0 | 0 | 0 | 0 |
| multiple_species_target_unclear | 4 | 0 | 0 | 0 | 0 |
| profile_failed_current | 0 | 4 | 0 | 0 | 0 |
| same_species_multiple_individuals_ok | 5 | 0 | 0 | 0 | 0 |
| schema_false_negative | 0 | 4 | 0 | 0 | 0 |
| species_card_downgraded | 8 | 0 | 1 | 0 | 0 |
| species_card_eligible | 21 | 0 | 0 | 0 | 0 |
| stable_accepted_control | 36 | 0 | 0 | 0 | 0 |
| text_or_screenshot | 0 | 0 | 1 | 0 | 0 |

## Target Taxon Visibility Outcomes

Outcomes for items with target_taxon_visibility annotations: {'accept': 4}

## Habitat Outcomes

Outcomes for habitat evidence items: {'accept': 3}

## Species Card Outcomes

Outcomes for species_card items: {'accept': 29, 'too_permissive': 1}

## Schema/Profile Outcomes

Outcomes for schema_false_negative / profile_failed items: {'too_strict': 4}

## Control Case Stability

Stable accepted control outcomes: {'accept': 36}

## Decision Rationale

Calibration patches validated; acceptable distribution of accept/edge cases.

## Final Decision: **READY_FOR_FIRST_PROFILED_CORPUS_CANDIDATE**
