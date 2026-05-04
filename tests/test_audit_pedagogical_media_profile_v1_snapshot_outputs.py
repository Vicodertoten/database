from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_pedagogical_media_profile_v1_snapshot_outputs import (
    DECISION_BLOCKED_RUN,
    DECISION_READY_CORPUS,
    audit_snapshot_outputs,
)


def _write_ai_outputs(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _valid_outcome(
    *,
    basic: int = 70,
    indirect: int = 40,
    global_quality: int = 80,
) -> dict[str, object]:
    return {
        "status": "ok",
        "qualification": None,
        "review_contract_version": "pedagogical_media_profile_v1",
        "prompt_version": "pedagogical_media_profile_prompt.v1",
        "model_name": "gemini-3.1-flash-lite-preview",
        "bird_image_pedagogical_review": None,
        "bird_image_pedagogical_score": None,
        "pedagogical_media_profile": {
            "review_status": "valid",
            "organism_group": "bird",
            "evidence_type": "whole_organism",
            "identification_profile": {
                "visible_field_marks": [
                    {
                        "feature": "long neck",
                        "body_part": "neck",
                        "visibility": "high",
                        "importance": "high",
                        "confidence": 0.9,
                    }
                ]
            },
            "limitations": [],
            "scores": {
                "global_quality_score": global_quality,
                "usage_scores": {
                    "basic_identification": basic,
                    "field_observation": 75,
                    "confusion_learning": 70,
                    "morphology_learning": 72,
                    "species_card": 80,
                    "indirect_evidence_learning": indirect,
                },
            },
        },
    }


def _failed_outcome() -> dict[str, object]:
    return {
        "status": "pedagogical_media_profile_failed",
        "qualification": None,
        "review_contract_version": "pedagogical_media_profile_v1",
        "prompt_version": "pedagogical_media_profile_prompt.v1",
        "model_name": "gemini-3.1-flash-lite-preview",
        "bird_image_pedagogical_review": None,
        "bird_image_pedagogical_score": None,
        "pedagogical_media_profile": {
            "review_status": "failed",
            "failure_reason": "schema_validation_failed",
            "organism_group": "bird",
            "evidence_type": "whole_organism",
            "diagnostics": {
                "schema_errors": [
                    {"type": "required", "loc": ["scores", "global_quality_score"]}
                ]
            },
        },
    }


def test_audit_counts_valid_failed_and_qualification_none(tmp_path: Path) -> None:
    ai_outputs_path = tmp_path / "data/raw/inaturalist/s1/ai_outputs.json"
    payload = {
        "inaturalist::1": _valid_outcome(global_quality=90),
        "inaturalist::2": _valid_outcome(global_quality=85),
        "inaturalist::3": _failed_outcome(),
    }
    _write_ai_outputs(ai_outputs_path, payload)

    report = audit_snapshot_outputs(
        snapshot_id="s1",
        snapshot_root=tmp_path / "data/raw/inaturalist",
    )

    generation = report["generation_metrics"]
    policy = report["policy_legacy_metrics"]
    assert generation["pmp_valid_count"] == 2
    assert generation["pmp_failed_count"] == 1
    assert generation["failure_reason_distribution"] == {"schema_validation_failed": 1}
    assert policy["qualification_none_count"] == 3
    assert report["decision"] in {"ADJUST_PMP_PIPELINE_INTEGRATION", "READY_FOR_PMP_POLICY_DESIGN"}


def test_audit_detects_feedback_and_selection_pollution(tmp_path: Path) -> None:
    ai_outputs_path = tmp_path / "data/raw/inaturalist/s2/ai_outputs.json"
    bad = _valid_outcome()
    bad["pedagogical_media_profile"]["feedback"] = "forbidden"
    bad["pedagogical_media_profile"]["selected_option_id"] = "x"
    bad["bird_image_pedagogical_review"] = {"status": "success"}
    _write_ai_outputs(ai_outputs_path, {"inaturalist::1": bad})

    report = audit_snapshot_outputs(
        snapshot_id="s2",
        snapshot_root=tmp_path / "data/raw/inaturalist",
    )

    pollution = report["doctrine_pollution_checks"]
    assert pollution["feedback_field_count"] >= 1
    assert pollution["selection_field_count"] >= 1
    assert pollution["bird_image_pollution_count"] == 1
    assert pollution["doctrine_pollution_detected"] is True
    assert report["decision"] == "INVESTIGATE_PMP_PIPELINE_FAILURES"


def test_audit_can_reach_ready_for_controlled_profiled_corpus_run(tmp_path: Path) -> None:
    ai_outputs_path = tmp_path / "data/raw/inaturalist/s3/ai_outputs.json"
    payload = {
        "inaturalist::1": _valid_outcome(global_quality=90, basic=85, indirect=35),
        "inaturalist::2": _valid_outcome(global_quality=87, basic=75, indirect=45),
        "inaturalist::3": _valid_outcome(global_quality=88, basic=70, indirect=75),
        "inaturalist::4": _valid_outcome(global_quality=84, basic=45, indirect=80),
        "inaturalist::5": _valid_outcome(global_quality=83, basic=68, indirect=65),
    }
    payload["inaturalist::4"]["pedagogical_media_profile"]["evidence_type"] = "indirect_evidence"
    _write_ai_outputs(ai_outputs_path, payload)

    report = audit_snapshot_outputs(
        snapshot_id="s3",
        snapshot_root=tmp_path / "data/raw/inaturalist",
    )

    assert report["generation_metrics"]["pmp_valid_rate"] == 1.0
    assert report["decision"] == DECISION_READY_CORPUS
    assert len(report["manual_review_sample"]) >= 5


def test_missing_or_invalid_ai_outputs_returns_blocked_run_failed(tmp_path: Path) -> None:
    missing_report = audit_snapshot_outputs(
        snapshot_id="missing",
        snapshot_root=tmp_path / "data/raw/inaturalist",
    )
    assert missing_report["decision"] == DECISION_BLOCKED_RUN

    invalid_path = tmp_path / "data/raw/inaturalist/invalid/ai_outputs.json"
    invalid_path.parent.mkdir(parents=True, exist_ok=True)
    invalid_path.write_text("not-json", encoding="utf-8")
    invalid_report = audit_snapshot_outputs(
        snapshot_id="invalid",
        snapshot_root=tmp_path / "data/raw/inaturalist",
    )
    assert invalid_report["decision"] == DECISION_BLOCKED_RUN