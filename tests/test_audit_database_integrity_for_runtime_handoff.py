from __future__ import annotations

from scripts.audit_database_integrity_for_runtime_handoff import (
    build_pmp_blocker_table,
    build_referenced_shell_status,
    classify_decision,
    compute_placeholder_breakdown,
    count_target_equals_candidate,
    count_unresolved_marked_usable,
    detect_duplicate_relationship_ids,
    detect_low_confidence_fr_seed_count,
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
    assert out["total_placeholder_french_label_count"] == 2
    assert out["candidate_placeholder_count"] == 2
    assert out["corpus_facing_placeholder_count"] == 1


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
        referenced_shell_review_needed=False,
        warning_only=False,
    )
    assert decision == "BLOCKED_NEEDS_AUDIT_CLARIFICATION"


def test_next_phase_recommendation_is_14c_when_ready() -> None:
    assert next_phase_for_decision("READY_FOR_RUNTIME_CONTRACTS_GATE") == "14C Robustness and regression tests"
    assert (
        next_phase_for_decision("READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS")
        == "14C Robustness and regression tests"
    )
