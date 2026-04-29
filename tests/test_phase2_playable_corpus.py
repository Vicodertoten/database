from __future__ import annotations

from database_core.ops.phase2_playable_corpus import (
    Phase2Thresholds,
    evaluate_phase2_gate,
    recommend_phase2_strategy,
)


def _baseline_metrics() -> dict[str, float | int]:
    return {
        "species_count": 50,
        "species_with_min_images": 50,
        "common_name_fr_effective_completeness": 1.0,
        "country_code_completeness": 1.0,
        "question_generation_success_rate": 1.0,
        "attribution_completeness": 1.0,
        "playable_items_total": 1000,
    }


def test_evaluate_phase2_gate_returns_go_when_all_thresholds_are_met() -> None:
    thresholds = Phase2Thresholds()
    gate = evaluate_phase2_gate(metrics=_baseline_metrics(), thresholds=thresholds)

    assert gate["status"] == "GO"
    assert all(item["pass"] for item in gate["checks"].values())


def test_evaluate_phase2_gate_returns_no_go_when_species_density_is_insufficient() -> None:
    thresholds = Phase2Thresholds()
    metrics = _baseline_metrics()
    metrics["species_with_min_images"] = 42

    gate = evaluate_phase2_gate(metrics=metrics, thresholds=thresholds)

    assert gate["status"] == "NO_GO"
    assert gate["checks"]["species_with_min_images"]["pass"] is False


def test_recommend_phase2_strategy_reconstruction_for_empty_corpus() -> None:
    thresholds = Phase2Thresholds()
    metrics = _baseline_metrics()
    metrics["playable_items_total"] = 0
    metrics["species_count"] = 0
    metrics["species_with_min_images"] = 0

    recommendation = recommend_phase2_strategy(metrics=metrics, thresholds=thresholds)

    assert recommendation["strategy"] == "reconstruction"
    assert recommendation["database_posture"] == "clean_start_recommended"


def test_recommend_phase2_strategy_reuse_and_complete_for_partial_density() -> None:
    thresholds = Phase2Thresholds()
    metrics = _baseline_metrics()
    metrics["species_with_min_images"] = 30

    recommendation = recommend_phase2_strategy(metrics=metrics, thresholds=thresholds)

    assert recommendation["strategy"] == "reuse_and_complete"
    assert recommendation["database_posture"] == "reuse_with_remediation"


def test_evaluate_phase2_gate_ignores_country_check_in_global_scope() -> None:
    thresholds = Phase2Thresholds(target_country_code=None)
    metrics = _baseline_metrics()
    metrics["country_code_completeness"] = 0.0

    gate = evaluate_phase2_gate(metrics=metrics, thresholds=thresholds)

    assert gate["status"] == "GO"
    assert gate["checks"]["country_code_completeness"]["pass"] is True