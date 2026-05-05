from __future__ import annotations

from database_core.qualification.pmp_policy_v1 import (
    PMP_POLICY_STATUS_POLICY_ERROR,
    PMP_POLICY_STATUS_POLICY_NOT_APPLICABLE,
    PMP_POLICY_STATUS_PRE_AI_REJECTED,
    PMP_POLICY_STATUS_PROFILE_FAILED,
    PMP_POLICY_STATUS_PROFILE_VALID,
    evaluate_pmp_outcome_policy,
    evaluate_pmp_profile_policy,
)


def _profile(
    *,
    evidence_type: str,
    global_quality_score: float,
    basic_identification: float,
    field_observation: float,
    confusion_learning: float,
    morphology_learning: float,
    species_card: float,
    indirect_evidence_learning: float,
    review_status: str = "valid",
    target_taxon_visibility: str | None = None,
    contains_visible_answer_text: bool | None = None,
    contains_ui_screenshot: bool | None = None,
    limitations: list[str] | None = None,
    identification_limitations: list[str] | None = None,
    visible_field_marks: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    profile = {
        "review_status": review_status,
        "evidence_type": evidence_type,
        "scores": {
            "global_quality_score": global_quality_score,
            "usage_scores": {
                "basic_identification": basic_identification,
                "field_observation": field_observation,
                "confusion_learning": confusion_learning,
                "morphology_learning": morphology_learning,
                "species_card": species_card,
                "indirect_evidence_learning": indirect_evidence_learning,
            },
        },
        "identification_profile": {
            "identification_limitations": identification_limitations or [],
            "visible_field_marks": visible_field_marks or [],
        },
        "limitations": limitations or [],
    }
    if target_taxon_visibility is not None:
        profile["target_taxon_visibility"] = target_taxon_visibility
    if contains_visible_answer_text is not None:
        profile["contains_visible_answer_text"] = contains_visible_answer_text
    if contains_ui_screenshot is not None:
        profile["contains_ui_screenshot"] = contains_ui_screenshot
    return profile


def _outcome(profile: dict[str, object], *, status: str = "ok") -> dict[str, object]:
    return {
        "status": status,
        "review_contract_version": "pedagogical_media_profile_v1",
        "pedagogical_media_profile": profile,
        "qualification": None,
    }


def test_whole_organism_high_scores_profile_valid() -> None:
    decision = evaluate_pmp_profile_policy(
        _profile(
            evidence_type="whole_organism",
            global_quality_score=90,
            basic_identification=82,
            field_observation=88,
            confusion_learning=71,
            morphology_learning=75,
            species_card=83,
            indirect_evidence_learning=20,
        )
    )

    assert decision["policy_status"] == PMP_POLICY_STATUS_PROFILE_VALID
    assert decision["usage_statuses"]["basic_identification"]["status"] == "eligible"
    assert decision["usage_statuses"]["field_observation"]["status"] == "eligible"
    assert decision["usage_statuses"]["species_card"]["status"] == "eligible"


def test_whole_organism_low_basic_high_field_observation_stays_valid() -> None:
    decision = evaluate_pmp_profile_policy(
        _profile(
            evidence_type="whole_organism",
            global_quality_score=88,
            basic_identification=45,
            field_observation=80,
            confusion_learning=72,
            morphology_learning=71,
            species_card=74,
            indirect_evidence_learning=35,
        )
    )

    assert decision["policy_status"] == PMP_POLICY_STATUS_PROFILE_VALID
    assert decision["usage_statuses"]["basic_identification"]["status"] == "not_recommended"
    assert decision["usage_statuses"]["field_observation"]["status"] == "eligible"


def test_feather_low_basic_high_indirect_is_sensible() -> None:
    decision = evaluate_pmp_profile_policy(
        _profile(
            evidence_type="feather",
            global_quality_score=86,
            basic_identification=30,
            field_observation=74,
            confusion_learning=65,
            morphology_learning=70,
            species_card=40,
            indirect_evidence_learning=91,
        )
    )

    assert decision["policy_status"] == PMP_POLICY_STATUS_PROFILE_VALID
    assert decision["usage_statuses"]["basic_identification"]["status"] in {
        "not_recommended",
        "not_applicable",
    }
    assert decision["usage_statuses"]["indirect_evidence_learning"]["status"] == "eligible"


def test_habitat_indirect_can_be_eligible_species_card_stricter() -> None:
    decision = evaluate_pmp_profile_policy(
        _profile(
            evidence_type="habitat",
            global_quality_score=84,
            basic_identification=20,
            field_observation=78,
            confusion_learning=70,
            morphology_learning=68,
            species_card=72,
            indirect_evidence_learning=88,
        )
    )

    assert decision["policy_status"] == PMP_POLICY_STATUS_PROFILE_VALID
    assert decision["usage_statuses"]["indirect_evidence_learning"]["status"] == "eligible"
    assert decision["usage_statuses"]["species_card"]["status"] in {
        "borderline",
        "not_recommended",
    }


def test_partial_organism_has_stricter_basic_identification() -> None:
    decision = evaluate_pmp_profile_policy(
        _profile(
            evidence_type="partial_organism",
            global_quality_score=81,
            basic_identification=75,
            field_observation=80,
            confusion_learning=71,
            morphology_learning=73,
            species_card=70,
            indirect_evidence_learning=55,
        )
    )

    assert decision["usage_statuses"]["basic_identification"]["status"] == "borderline"
    assert decision["usage_statuses"]["field_observation"]["status"] == "eligible"


def test_multiple_organisms_has_stricter_species_card() -> None:
    decision = evaluate_pmp_profile_policy(
        _profile(
            evidence_type="multiple_organisms",
            global_quality_score=78,
            basic_identification=72,
            field_observation=82,
            confusion_learning=71,
            morphology_learning=72,
            species_card=72,
            indirect_evidence_learning=62,
        )
    )

    assert decision["usage_statuses"]["field_observation"]["status"] == "eligible"
    assert decision["usage_statuses"]["species_card"]["status"] == "borderline"


def test_multiple_same_taxon_can_remain_eligible_for_relevant_uses() -> None:
    decision = evaluate_pmp_profile_policy(
        _profile(
            evidence_type="multiple_organisms",
            global_quality_score=86,
            basic_identification=84,
            field_observation=84,
            confusion_learning=78,
            morphology_learning=82,
            species_card=82,
            indirect_evidence_learning=40,
            target_taxon_visibility="multiple_individuals_same_taxon",
        )
    )

    assert decision["usage_statuses"]["basic_identification"]["status"] == "eligible"
    assert decision["usage_statuses"]["morphology_learning"]["status"] == "eligible"
    assert decision["usage_statuses"]["field_observation"]["status"] == "eligible"
    assert decision["usage_statuses"]["species_card"]["status"] == "eligible"


def test_multiple_species_target_unclear_downgrades_identification_and_blocks_species_card(
) -> None:
    decision = evaluate_pmp_profile_policy(
        _profile(
            evidence_type="multiple_organisms",
            global_quality_score=82,
            basic_identification=76,
            field_observation=83,
            confusion_learning=74,
            morphology_learning=75,
            species_card=86,
            indirect_evidence_learning=45,
            target_taxon_visibility="multiple_species_target_unclear",
        )
    )

    assert decision["usage_statuses"]["basic_identification"]["status"] == "borderline"
    assert decision["usage_statuses"]["confusion_learning"]["status"] == "borderline"
    assert decision["usage_statuses"]["species_card"]["status"] == "not_recommended"
    assert decision["usage_statuses"]["field_observation"]["status"] == "eligible"


def test_visible_answer_text_blocks_quiz_like_and_card_uses() -> None:
    decision = evaluate_pmp_profile_policy(
        _profile(
            evidence_type="whole_organism",
            global_quality_score=88,
            basic_identification=85,
            field_observation=84,
            confusion_learning=82,
            morphology_learning=80,
            species_card=87,
            indirect_evidence_learning=10,
            contains_visible_answer_text=True,
            contains_ui_screenshot=True,
        )
    )

    for usage_name in (
        "basic_identification",
        "field_observation",
        "confusion_learning",
        "morphology_learning",
        "species_card",
    ):
        assert decision["usage_statuses"][usage_name]["status"] == "not_recommended"


def test_generic_habitat_with_score_70_is_not_indirectly_eligible() -> None:
    decision = evaluate_pmp_profile_policy(
        _profile(
            evidence_type="habitat",
            global_quality_score=72,
            basic_identification=10,
            field_observation=76,
            confusion_learning=35,
            morphology_learning=30,
            species_card=20,
            indirect_evidence_learning=70,
            identification_limitations=["environmental context only", "no organism present"],
        )
    )

    assert decision["usage_statuses"]["indirect_evidence_learning"]["status"] == "not_recommended"


def test_generic_habitat_feeder_context_is_not_indirectly_eligible() -> None:
    decision = evaluate_pmp_profile_policy(
        _profile(
            evidence_type="habitat",
            global_quality_score=84,
            basic_identification=15,
            field_observation=74,
            confusion_learning=30,
            morphology_learning=30,
            species_card=22,
            indirect_evidence_learning=92,
            visible_field_marks=[
                {
                    "feature": "bird feeder habitat",
                    "body_part": "habitat",
                }
            ],
            identification_limitations=["feeding station only"],
        )
    )

    assert decision["usage_statuses"]["indirect_evidence_learning"]["status"] == "not_recommended"


def test_species_relevant_habitat_signal_can_be_eligible_at_85_plus() -> None:
    decision = evaluate_pmp_profile_policy(
        _profile(
            evidence_type="habitat",
            global_quality_score=85,
            basic_identification=12,
            field_observation=77,
            confusion_learning=42,
            morphology_learning=45,
            species_card=25,
            indirect_evidence_learning=86,
            visible_field_marks=[
                {
                    "feature": "woodpecker foraging damage",
                    "body_part": "habitat",
                }
            ],
            identification_limitations=[
                "indirect evidence only, typical of large woodpecker activity"
            ],
        )
    )

    assert decision["usage_statuses"]["indirect_evidence_learning"]["status"] == "eligible"


def test_distant_low_detail_whole_organism_is_downgraded_for_species_card() -> None:
    decision = evaluate_pmp_profile_policy(
        _profile(
            evidence_type="whole_organism",
            global_quality_score=78,
            basic_identification=60,
            field_observation=77,
            confusion_learning=58,
            morphology_learning=62,
            species_card=82,
            indirect_evidence_learning=10,
            identification_limitations=[
                "Subject is small in frame",
                "lack of detail for definitive ID",
            ],
        )
    )

    assert decision["usage_statuses"]["species_card"]["status"] == "not_recommended"


def test_failed_profile_maps_to_profile_failed() -> None:
    decision = evaluate_pmp_profile_policy(
        _profile(
            evidence_type="whole_organism",
            global_quality_score=0,
            basic_identification=0,
            field_observation=0,
            confusion_learning=0,
            morphology_learning=0,
            species_card=0,
            indirect_evidence_learning=0,
            review_status="failed",
        )
    )

    assert decision["policy_status"] == PMP_POLICY_STATUS_PROFILE_FAILED
    for usage in decision["usage_statuses"].values():
        assert usage["status"] == "not_applicable"


def test_pre_ai_rejected_maps_to_pre_ai_policy_status() -> None:
    outcome = {
        "status": "insufficient_resolution_pre_ai",
        "review_contract_version": "pedagogical_media_profile_v1",
        "pedagogical_media_profile": None,
    }

    decision = evaluate_pmp_outcome_policy(outcome)

    assert decision["policy_status"] == PMP_POLICY_STATUS_PRE_AI_REJECTED


def test_missing_pmp_profile_maps_to_error_or_not_applicable() -> None:
    non_pmp_outcome = {
        "status": "ok",
        "review_contract_version": "v1_1",
        "pedagogical_media_profile": None,
    }
    pmp_outcome = {
        "status": "ok",
        "review_contract_version": "pedagogical_media_profile_v1",
        "pedagogical_media_profile": None,
    }

    non_pmp_decision = evaluate_pmp_outcome_policy(non_pmp_outcome)
    pmp_decision = evaluate_pmp_outcome_policy(pmp_outcome)

    assert non_pmp_decision["policy_status"] == PMP_POLICY_STATUS_POLICY_NOT_APPLICABLE
    assert pmp_decision["policy_status"] == PMP_POLICY_STATUS_POLICY_ERROR


def test_high_global_score_does_not_force_basic_identification_eligible() -> None:
    decision = evaluate_pmp_profile_policy(
        _profile(
            evidence_type="whole_organism",
            global_quality_score=95,
            basic_identification=40,
            field_observation=82,
            confusion_learning=73,
            morphology_learning=70,
            species_card=75,
            indirect_evidence_learning=15,
        )
    )

    assert decision["global_quality_score"] == 95.0
    assert decision["usage_statuses"]["basic_identification"]["status"] == "not_recommended"


def test_policy_output_contains_no_runtime_fields() -> None:
    decision = evaluate_pmp_outcome_policy(
        _outcome(
            _profile(
                evidence_type="whole_organism",
                global_quality_score=80,
                basic_identification=75,
                field_observation=77,
                confusion_learning=70,
                morphology_learning=71,
                species_card=73,
                indirect_evidence_learning=20,
            )
        )
    )

    assert "playable" not in decision
    assert "selected_for_quiz" not in decision
    assert "runtime_ready" not in decision
    assert "selectedOptionId" not in decision


def test_outcome_failed_status_adds_failed_note() -> None:
    outcome = _outcome(
        _profile(
            evidence_type="whole_organism",
            global_quality_score=0,
            basic_identification=0,
            field_observation=0,
            confusion_learning=0,
            morphology_learning=0,
            species_card=0,
            indirect_evidence_learning=0,
            review_status="failed",
        ),
        status="pedagogical_media_profile_failed",
    )

    decision = evaluate_pmp_outcome_policy(outcome)

    assert decision["policy_status"] == PMP_POLICY_STATUS_PROFILE_FAILED
    assert "outcome_status_pedagogical_media_profile_failed" in decision["policy_notes"]
