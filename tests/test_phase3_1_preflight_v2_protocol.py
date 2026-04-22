from __future__ import annotations

from scripts.phase3_1_preflight_v2_protocol import (
    _is_pack_eligible,
    _map_scale_decision,
    _missing_min_media,
    _probe_has_compile_signal,
)


def test_missing_min_media_extracts_expected_value() -> None:
    deficits = [
        {"code": "min_taxa_served", "missing": 10},
        {"code": "min_media_per_taxon", "missing": 2},
    ]
    assert _missing_min_media(deficits) == 2
    assert _missing_min_media([{"code": "min_total_questions", "missing": 20}]) == 0


def test_pack_eligibility_requires_compile_and_min_media_deficit_and_blocking_taxa() -> None:
    diagnostic = {
        "compilable": False,
        "deficits": [{"code": "min_media_per_taxon", "missing": 1}],
        "blocking_taxa": [{"canonical_taxon_id": "taxon:birds:000001"}],
    }
    assert _is_pack_eligible(diagnostic) is True

    no_deficit = {
        "compilable": False,
        "deficits": [{"code": "min_media_per_taxon", "missing": 0}],
        "blocking_taxa": [{"canonical_taxon_id": "taxon:birds:000001"}],
    }
    assert _is_pack_eligible(no_deficit) is False

    no_blocking = {
        "compilable": False,
        "deficits": [{"code": "min_media_per_taxon", "missing": 2}],
        "blocking_taxa": [],
    }
    assert _is_pack_eligible(no_blocking) is False


def test_probe_signal_requires_compile_movement_within_cost_cap() -> None:
    positive = {
        "delta": {
            "insufficient_media_per_taxon_reason_count": -1,
            "taxon_with_min2_media_ratio": 0.01,
        },
        "final": {"overall_pass": True},
        "passes": [{"images_sent_to_gemini": 10}],
    }
    go, reason = _probe_has_compile_signal(positive, gemini_cap=80)
    assert go is True
    assert reason == "probe_compile_signal_positive"

    expensive = {
        "delta": {
            "insufficient_media_per_taxon_reason_count": -1,
            "taxon_with_min2_media_ratio": 0.02,
        },
        "final": {"overall_pass": True},
        "passes": [{"images_sent_to_gemini": 120}],
    }
    go, reason = _probe_has_compile_signal(expensive, gemini_cap=80)
    assert go is False
    assert reason == "probe_cost_cap_exceeded"


def test_map_scale_decision_strict_mapping() -> None:
    assert _map_scale_decision("CONTINUE_SCALE") == "GO"
    assert _map_scale_decision("GO_WITH_GAPS") == "GO_WITH_GAPS"
    assert _map_scale_decision("STOP_RETARGET") == "NO_GO"
    assert _map_scale_decision("STOP_RETARGET_PRECHECK") == "NO_GO"
