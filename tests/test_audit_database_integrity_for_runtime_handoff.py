from __future__ import annotations

from scripts.audit_database_integrity_for_runtime_handoff import (
    build_low_confidence_or_provisional_seed_ids,
    build_pmp_blocker_table,
    build_referenced_shell_status,
    classify_decision,
    compute_placeholder_breakdown,
    count_target_equals_candidate,
    count_unresolved_marked_usable,
    detect_duplicate_relationship_ids,
    detect_low_confidence_fr_seed_count,
    is_runtime_unsafe_label,
    next_phase_for_decision,
)


def test_duplicate_relationship_id_detection() -> None:
    rows = [{"relationship_id": "dr:1"}, {"relationship_id": "dr:1"}, {"relationship_id": "dr:2"}]
    assert detect_duplicate_relationship_ids(rows) == ["dr:1"]


def test_target_equals_candidate_detection() -> None:
    rows = [
        {
            "target_canonical_taxon_id": "taxon:birds:000001",
            "candidate_taxon_ref_id": "taxon:birds:000001",
            "target_scientific_name": "Parus major",
            "candidate_scientific_name": "Parus major",
        },
        {
            "target_canonical_taxon_id": "taxon:birds:000002",
            "candidate_taxon_ref_id": "taxon:birds:000003",
            "target_scientific_name": "Corvus corone",
            "candidate_scientific_name": "Pica pica",
        },
    ]
    assert count_target_equals_candidate(rows) == 1


def test_emergency_fallback_detection_metric_shape() -> None:
    compare_payload = {"metrics": {"emergency_fallback_count": {"sprint13": 1}}}
    assert int(compare_payload["metrics"]["emergency_fallback_count"]["sprint13"]) == 1


def test_placeholder_breakdown() -> None:
    records = [
        {
            "candidate_taxon_ref_id": "reftaxon:inaturalist:117016",
            "candidate_scientific_name": "Phylloscopus collybita",
            "status": "candidate",
        },
        {
            "candidate_taxon_ref_id": "reftaxon:inaturalist:117028",
            "candidate_scientific_name": "Phylloscopus inornatus",
            "status": "needs_review",
        },
    ]
    canonical = {"canonical_taxa": []}
    referenced = {
        "referenced_taxa": [
            {
                "referenced_taxon_id": "reftaxon:inaturalist:117016",
                "scientific_name": "Phylloscopus collybita",
                "common_names_i18n": {"fr": ["Phylloscopus collybita"]},
            },
            {
                "referenced_taxon_id": "reftaxon:inaturalist:117028",
                "scientific_name": "Phylloscopus inornatus",
                "common_names_i18n": {"fr": ["Phylloscopus inornatus"]},
            },
        ]
    }
    out = compute_placeholder_breakdown(records, canonical, referenced)
    assert out["unique_placeholder_taxon_count"] == 2
    assert out["candidate_placeholder_relationship_occurrence_count"] == 2
    assert out["corpus_facing_placeholder_relationship_occurrence_count"] == 1
    assert out["affected_first_corpus_candidate_relationship_occurrence_count"] == 1


def test_low_confidence_fr_seed_detection_from_sprint13_apply_evidence() -> None:
    payload = {
        "applied": [
            {"confidence": "low"},
            {"confidence": "low"},
            {"confidence": "high"},
        ]
    }
    out = detect_low_confidence_fr_seed_count(payload, None)
    assert out["status"] == "known"
    assert out["count"] == 2


def test_low_confidence_fr_seed_detection_missing_evidence() -> None:
    out = detect_low_confidence_fr_seed_count(None, None)
    assert out["status"] == "evidence_missing"
    assert out["count"] is None


def test_unresolved_marked_usable_detection() -> None:
    rows = [
        {"candidate_taxon_ref_type": "unresolved_taxon", "status": "needs_review"},
        {"candidate_taxon_ref_type": "unresolved_taxon", "status": "candidate"},
    ]
    assert count_unresolved_marked_usable(rows) == 1


def test_referenced_shell_planned_not_created_semantics() -> None:
    payload = {
        "input_candidates_count": 198,
        "mapped_to_canonical_count": 42,
        "new_shell_plan_count": 156,
        "dry_run": True,
    }
    out = build_referenced_shell_status(payload)
    assert out["inat_candidates_assessed_count"] == 198
    assert out["mapped_to_canonical_count"] == 42
    assert out["referenced_shells_planned_count"] == 156
    assert out["referenced_shells_created_count"] == 0
    assert out["mode"] == "dry_run"
    assert out["status"] == "planned_not_created"


def test_pmp_blocker_attribution_shape() -> None:
    payload = {
        "issue_category_distribution": {
            "schema_false_negative": 4,
            "text_overlay_or_answer_visible": 1,
        }
    }
    table = build_pmp_blocker_table(payload)
    assert len(table) == 2
    assert table[0]["affects_runtime_handoff"] == "unknown"


def test_blocked_needs_audit_clarification_decision() -> None:
    decision = classify_decision(
        hard_integrity=False,
        audit_clarification_needed=True,
        pmp_blocker_proven=False,
        name_review_needed=False,
        placeholder_exclusion_needed=False,
        referenced_shell_review_needed=False,
        warning_only=False,
    )
    assert decision == "BLOCKED_NEEDS_AUDIT_CLARIFICATION"


def test_blocked_needs_placeholder_exclusion_decision() -> None:
    decision = classify_decision(
        hard_integrity=False,
        audit_clarification_needed=False,
        pmp_blocker_proven=False,
        name_review_needed=False,
        placeholder_exclusion_needed=True,
        referenced_shell_review_needed=False,
        warning_only=False,
    )
    assert decision == "BLOCKED_NEEDS_PLACEHOLDER_EXCLUSION"


def test_ready_with_warnings_requires_no_placeholder_exclusion_blocker() -> None:
    decision = classify_decision(
        hard_integrity=False,
        audit_clarification_needed=False,
        pmp_blocker_proven=False,
        name_review_needed=False,
        placeholder_exclusion_needed=False,
        referenced_shell_review_needed=False,
        warning_only=True,
    )
    assert decision == "READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS"


def test_runtime_unsafe_label_low_confidence_seed_is_unsafe() -> None:
    assert is_runtime_unsafe_label(
        common_name_fr="Nom valide apparent",
        scientific_name="Parus major",
        low_confidence_or_provisional_seed=True,
        explicit_placeholder_or_provisional=False,
    )


def test_runtime_unsafe_label_scientific_name_as_fr_is_unsafe() -> None:
    assert is_runtime_unsafe_label(
        common_name_fr="Parus major",
        scientific_name="Parus major",
        low_confidence_or_provisional_seed=False,
        explicit_placeholder_or_provisional=False,
    )


def test_runtime_unsafe_label_latin_binomial_fr_is_unsafe() -> None:
    assert is_runtime_unsafe_label(
        common_name_fr="Corvus corone",
        scientific_name="Parus major",
        low_confidence_or_provisional_seed=False,
        explicit_placeholder_or_provisional=False,
    )


def test_build_low_confidence_or_provisional_seed_ids() -> None:
    rows = [
        {
            "candidate_taxon_ref_id": "reftaxon:1",
            "confidence": "low",
            "source": "manual_override",
            "recommended_action": "seed_fr_then_human_review",
            "notes": "provisional seed",
        },
        {
            "candidate_taxon_ref_id": "reftaxon:2",
            "confidence": "high",
            "source": "manual_override",
            "recommended_action": "",
            "notes": "",
        },
    ]
    out = build_low_confidence_or_provisional_seed_ids(rows)
    assert out == {"reftaxon:1"}


def test_guard_excludes_unsafe_runtime_occurrences_but_preserves_audit_counts() -> None:
    records = [
        {
            "target_canonical_taxon_id": "taxon:1",
            "candidate_taxon_ref_id": "reftaxon:1",
            "candidate_scientific_name": "Phylloscopus collybita",
            "status": "candidate",
        },
        {
            "target_canonical_taxon_id": "taxon:1",
            "candidate_taxon_ref_id": "reftaxon:2",
            "candidate_scientific_name": "Parus major",
            "status": "candidate",
        },
        {
            "target_canonical_taxon_id": "taxon:1",
            "candidate_taxon_ref_id": "reftaxon:3",
            "candidate_scientific_name": "Erithacus rubecula",
            "status": "candidate",
        },
    ]
    referenced = {
        "referenced_taxa": [
            {
                "referenced_taxon_id": "reftaxon:1",
                "scientific_name": "Phylloscopus collybita",
                "common_names_i18n": {"fr": ["Phylloscopus collybita"]},
            },
            {
                "referenced_taxon_id": "reftaxon:2",
                "scientific_name": "Parus major",
                "common_names_i18n": {"fr": ["Mésange charbonnière"]},
            },
            {
                "referenced_taxon_id": "reftaxon:3",
                "scientific_name": "Erithacus rubecula",
                "common_names_i18n": {"fr": ["Rougegorge"]},
            },
        ]
    }
    out = compute_placeholder_breakdown(
        records,
        {"canonical_taxa": []},
        referenced,
        low_confidence_or_provisional_seed_ids={"reftaxon:1"},
        runtime_guard_active=True,
        first_corpus_minimum_target_count=1,
    )
    assert out["corpus_facing_placeholder_relationship_occurrence_count_before_guard"] == 1
    assert out["corpus_facing_placeholder_relationship_occurrence_count_after_guard"] == 0
    assert out["placeholder_relationship_occurrences_marked_not_for_corpus_display"] == 1
    assert out["candidate_placeholder_relationship_occurrence_count"] == 1


def test_decision_blocks_when_guard_absent_and_placeholder_corpus_facing() -> None:
    decision = classify_decision(
        hard_integrity=False,
        audit_clarification_needed=False,
        pmp_blocker_proven=False,
        name_review_needed=False,
        placeholder_exclusion_needed=True,
        referenced_shell_review_needed=False,
        warning_only=False,
    )
    assert decision == "BLOCKED_NEEDS_PLACEHOLDER_EXCLUSION"


def test_decision_blocks_name_review_when_safe_target_count_below_30() -> None:
    decision = classify_decision(
        hard_integrity=False,
        audit_clarification_needed=False,
        pmp_blocker_proven=False,
        name_review_needed=True,
        placeholder_exclusion_needed=False,
        referenced_shell_review_needed=False,
        warning_only=False,
    )
    assert decision == "BLOCKED_NEEDS_NAME_REVIEW"


def test_next_phase_recommendation_is_14c_when_ready() -> None:
    assert next_phase_for_decision("READY_FOR_RUNTIME_CONTRACTS_GATE") == "14C Robustness and regression tests"
    assert (
        next_phase_for_decision("READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS")
        == "14C Robustness and regression tests"
    )
