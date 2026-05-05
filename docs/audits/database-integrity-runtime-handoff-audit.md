---
owner: database
status: ready_for_validation
last_reviewed: 2026-05-05
source_of_truth: docs/audits/database-integrity-runtime-handoff-audit.md
scope: sprint14b_data_integrity_gate
---

# Database Integrity Runtime Handoff Audit (Sprint 14B)

## What Was Audited

- Sprint 13 projected distractor relationships and integrity invariants.
- Referenced shell plan semantics (assessed, mapped, planned, created, mode, status).
- FR quality signals (missing FR, low-confidence seeds, placeholder FR labels breakdown).
- PMP policy artifacts with explicit attribution and impact uncertainty.

## Pass/Warning/Fail

| Check | Status | Value |
|---|---|---|
| projected_relationship_schema_validity | pass | {"schema_validation_error_count": 0, "rejected_records_count": 0} |
| duplicate_relationship_ids | pass | {"duplicate_id_count": 0, "sample": []} |
| orphan_target_taxon_references | pass | 0 |
| orphan_candidate_taxon_references | pass | 0 |
| target_equals_candidate | pass | 0 |
| emergency_fallback_count | pass | 0 |
| unresolved_marked_usable | pass | 0 |
| candidates_missing_french_names | warning | 112 |
| low_confidence_fr_seeds | warning | {"count": 44, "status": "known", "source": "localized_apply.applied"} |
| placeholder_french_labels_breakdown | warning | {"unique_placeholder_taxon_count": 67, "target_placeholder_taxon_count": 0, "candidate_placeholder_relationship_occurrence_count": 206, "referenced_shell_placeholder_taxon_count": 67, "corpus_facing_placeholder_relationship_occurrence_count": 124, "excluded_or_not_for_corpus_display_relationship_occurrence_count": 82, "affected_first_corpus_candidate_relationship_occurrence_count": 124, "unknown_impact_count": 0, "affected_target_taxon_count": 49, "affected_ready_target_count": 40, "safe_ready_target_count_after_placeholder_exclusion": 10, "runtime_contract_placeholder_exclusion_guard": true, "placeholder_labels_runtime_policy": "exclude_or_mark_not_for_corpus_display", "corpus_facing_placeholder_relationship_occurrence_count_before_guard": 124, "corpus_facing_placeholder_relationship_occurrence_count_after_guard": 0, "placeholder_relationship_occurrences_marked_not_for_corpus_display": 124, "first_corpus_minimum_target_count": 30, "first_corpus_target_count_after_guard": 10, "first_corpus_target_count_after_guard_status": "fail"} |
| runtime_contract_placeholder_exclusion_guard | pass | {"documented_in_14d_runtime_contracts": true, "required_condition": "14D runtime contracts must exclude or mark all provisional/placeholder FR labels as not_for_corpus_display.", "placeholder_labels_runtime_policy": "exclude_or_mark_not_for_corpus_display", "active": true} |
| first_corpus_target_count_after_guard | fail | {"first_corpus_minimum_target_count": 30, "first_corpus_target_count_after_guard": 10, "status": "fail"} |
| referenced_shell_plan_status | warning | {"inat_candidates_assessed_count": 198, "mapped_to_canonical_count": 42, "referenced_shells_planned_count": 156, "referenced_shells_created_count": 0, "mode": "dry_run", "status": "planned_not_created"} |
| localized_name_conflicts | pass | 0 |
| invalid_pmp_records | warning | 4 |
| visible_answer_text_or_screenshot_blockers | warning | 1 |
| pmp_policy_blocker_attribution | warning | {"count": 14, "table_rows": 8} |

## Key Counts

- projected_record_count: 407
- duplicate_relationship_id_count: 0
- emergency_fallback_count: 0
- candidates_missing_french_name_count: 112
- low_confidence_fr_seed_count: 44
- placeholder_french_labels: {"unique_placeholder_taxon_count": 67, "target_placeholder_taxon_count": 0, "candidate_placeholder_relationship_occurrence_count": 206, "referenced_shell_placeholder_taxon_count": 67, "corpus_facing_placeholder_relationship_occurrence_count": 124, "excluded_or_not_for_corpus_display_relationship_occurrence_count": 82, "affected_first_corpus_candidate_relationship_occurrence_count": 124, "unknown_impact_count": 0, "affected_target_taxon_count": 49, "affected_ready_target_count": 40, "safe_ready_target_count_after_placeholder_exclusion": 10, "runtime_contract_placeholder_exclusion_guard": true, "placeholder_labels_runtime_policy": "exclude_or_mark_not_for_corpus_display", "corpus_facing_placeholder_relationship_occurrence_count_before_guard": 124, "corpus_facing_placeholder_relationship_occurrence_count_after_guard": 0, "placeholder_relationship_occurrences_marked_not_for_corpus_display": 124, "first_corpus_minimum_target_count": 30, "first_corpus_target_count_after_guard": 10, "first_corpus_target_count_after_guard_status": "fail"}
- referenced_shell_status: {"inat_candidates_assessed_count": 198, "mapped_to_canonical_count": 42, "referenced_shells_planned_count": 156, "referenced_shells_created_count": 0, "mode": "dry_run", "status": "planned_not_created"}

## Placeholder Semantics

- unique_placeholder_taxon_count=67 represents distinct placeholder taxa.
- candidate_placeholder_relationship_occurrence_count=206 represents relationship-level occurrences.
- corpus_facing_placeholder_relationship_occurrence_count_before_guard=124 are unsafe before runtime filtering.
- corpus_facing_placeholder_relationship_occurrence_count_after_guard=0 must be 0 for runtime-facing output.
- placeholder_relationship_occurrences_marked_not_for_corpus_display=124 remain in source/audit data but are excluded from corpus-facing display.
- safe_ready_target_count_after_placeholder_exclusion=10 against minimum=30 (fail).

## Corpus Gate vs Persistence

- READY_FOR_FIRST_CORPUS_DISTRACTOR_GATE remains a corpus-readiness signal only.
- PERSIST_DISTRACTOR_RELATIONSHIPS_V1 remains false in Sprint 14B/14B.1.
- DATABASE_PHASE_CLOSED remains false in Sprint 14B/14B.1.
- It does not authorize DistractorRelationship persistence.
- It does not authorize database-phase closure.
- 14D runtime contracts must exclude or mark all provisional/placeholder FR labels as not_for_corpus_display.
- Placeholder/provisional labels remain preserved in source and audit evidence for traceability.
- Runtime-facing label selection must use only safe localized labels.

## PMP Blocker Attribution

| blocker_category | count | source_artifact | affects_first_corpus_candidate | affects_runtime_handoff | severity | recommended_action |
|---|---:|---|---|---|---|---|
| schema_false_negative | 4 | docs/audits/evidence/pmp_policy_v1_broader_400_20260504_human_review_analysis.json | unknown | unknown | warning | Classify impact on first-corpus candidate set before promoting to hard blocker. |
| multiple_species_target_unclear | 4 | docs/audits/evidence/pmp_policy_v1_broader_400_20260504_human_review_analysis.json | unknown | unknown | warning | Classify impact on first-corpus candidate set before promoting to hard blocker. |
| text_overlay_or_answer_visible | 1 | docs/audits/evidence/pmp_policy_v1_broader_400_20260504_human_review_analysis.json | unknown | unknown | warning | Classify impact on first-corpus candidate set before promoting to hard blocker. |
| field_observation_too_permissive | 1 | docs/audits/evidence/pmp_policy_v1_broader_400_20260504_human_review_analysis.json | unknown | unknown | warning | Classify impact on first-corpus candidate set before promoting to hard blocker. |
| species_card_too_permissive | 1 | docs/audits/evidence/pmp_policy_v1_broader_400_20260504_human_review_analysis.json | unknown | unknown | warning | Classify impact on first-corpus candidate set before promoting to hard blocker. |
| habitat_too_permissive | 1 | docs/audits/evidence/pmp_policy_v1_broader_400_20260504_human_review_analysis.json | unknown | unknown | warning | Classify impact on first-corpus candidate set before promoting to hard blocker. |
| pre_ai_borderline | 1 | docs/audits/evidence/pmp_policy_v1_broader_400_20260504_human_review_analysis.json | unknown | unknown | warning | Classify impact on first-corpus candidate set before promoting to hard blocker. |
| rare_model_subject_miss | 1 | docs/audits/evidence/pmp_policy_v1_broader_400_20260504_human_review_analysis.json | unknown | unknown | warning | Classify impact on first-corpus candidate set before promoting to hard blocker. |

## Exact Blockers

- Safe ready target count after placeholder exclusion is below first-corpus minimum (30).

## Exact Non-Actions

- No DistractorRelationship persistence
- No ReferencedTaxon shell creation
- No localized-name modifications
- No delete/archive/deprecate actions

## Decision

- decision: BLOCKED_NEEDS_NAME_REVIEW
- recommended_next_action: Complete required name review for corpus-facing artifacts, then rerun Sprint 14B.

## Next Phase Recommendation

- Resolve blockers and rerun Sprint 14B data integrity gate
