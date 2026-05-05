from __future__ import annotations

from scripts.audit_database_integrity_for_runtime_handoff import classify_decision, next_phase_for_decision


def test_source_attested_policy_ready_decision() -> None:
    decision = classify_decision(
        hard_integrity=False,
        source_attested_policy_enabled=True,
        runtime_facing_unsafe_labels=False,
        safe_ready_target_count_after_source_attested_policy=30,
        first_corpus_minimum_target_count=30,
        needs_review_conflict_count=0,
        not_displayable_missing_count=10,
    )
    assert decision == "READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS"


def test_non_human_reviewed_is_not_blocker_when_safe_count_ok() -> None:
    decision = classify_decision(
        hard_integrity=False,
        source_attested_policy_enabled=True,
        runtime_facing_unsafe_labels=False,
        safe_ready_target_count_after_source_attested_policy=33,
        first_corpus_minimum_target_count=30,
        needs_review_conflict_count=0,
        not_displayable_missing_count=5,
    )
    assert decision == "READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS"


def test_runtime_unsafe_labels_block() -> None:
    decision = classify_decision(
        hard_integrity=False,
        source_attested_policy_enabled=True,
        runtime_facing_unsafe_labels=True,
        safe_ready_target_count_after_source_attested_policy=40,
        first_corpus_minimum_target_count=30,
        needs_review_conflict_count=0,
        not_displayable_missing_count=0,
    )
    assert decision == "BLOCKED_NEEDS_PLACEHOLDER_EXCLUSION"


def test_conflict_specific_blocker_when_under_minimum() -> None:
    decision = classify_decision(
        hard_integrity=False,
        source_attested_policy_enabled=True,
        runtime_facing_unsafe_labels=False,
        safe_ready_target_count_after_source_attested_policy=10,
        first_corpus_minimum_target_count=30,
        needs_review_conflict_count=3,
        not_displayable_missing_count=0,
    )
    assert decision == "BLOCKED_NEEDS_NAME_CONFLICT_REVIEW"


def test_missing_specific_blocker_when_under_minimum() -> None:
    decision = classify_decision(
        hard_integrity=False,
        source_attested_policy_enabled=True,
        runtime_facing_unsafe_labels=False,
        safe_ready_target_count_after_source_attested_policy=10,
        first_corpus_minimum_target_count=30,
        needs_review_conflict_count=0,
        not_displayable_missing_count=7,
    )
    assert decision == "BLOCKED_NEEDS_NAME_SOURCE_ENRICHMENT"


def test_policy_missing_blocker() -> None:
    decision = classify_decision(
        hard_integrity=False,
        source_attested_policy_enabled=False,
        runtime_facing_unsafe_labels=False,
        safe_ready_target_count_after_source_attested_policy=50,
        first_corpus_minimum_target_count=30,
        needs_review_conflict_count=0,
        not_displayable_missing_count=0,
    )
    assert decision == "BLOCKED_NEEDS_NAME_POLICY"


def test_next_phase_for_ready_is_14c() -> None:
    assert next_phase_for_decision("READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS") == "14C Robustness and regression tests"
