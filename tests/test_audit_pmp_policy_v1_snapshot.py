from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_pmp_policy_v1_snapshot import (
    DECISION_BLOCKED,
    audit_pmp_policy_snapshot,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _valid_outcome(
    *,
    media_id: str,
    evidence_type: str = "whole_organism",
    basic: int = 70,
    field: int = 75,
    confusion: int = 70,
    morphology: int = 72,
    species_card: int = 80,
    indirect: int = 40,
    global_quality: int = 80,
) -> dict[str, object]:
    return {
        "status": "ok",
        "qualification": None,
        "review_contract_version": "pedagogical_media_profile_v1",
        "prompt_version": "pedagogical_media_profile_prompt.v1",
        "model_name": "gemini-3.1-flash-lite-preview",
        "pedagogical_media_profile": {
            "review_status": "valid",
            "organism_group": "bird",
            "evidence_type": evidence_type,
            "scores": {
                "global_quality_score": global_quality,
                "usage_scores": {
                    "basic_identification": basic,
                    "field_observation": field,
                    "confusion_learning": confusion,
                    "morphology_learning": morphology,
                    "species_card": species_card,
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
        "pedagogical_media_profile": {
            "review_status": "failed",
            "failure_reason": "schema_validation_failed",
        },
    }


def _pre_ai_outcome() -> dict[str, object]:
    return {
        "status": "insufficient_resolution_pre_ai",
        "qualification": None,
        "review_contract_version": "pedagogical_media_profile_v1",
        "pedagogical_media_profile": None,
    }


def test_missing_ai_outputs_is_blocked(tmp_path: Path) -> None:
    report = audit_pmp_policy_snapshot(snapshot_id="missing", snapshot_root=tmp_path)

    assert report["decision"] == DECISION_BLOCKED


def test_policy_audit_counts_and_usage_statuses(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data/raw/inaturalist"
    ai_outputs_path = snapshot_root / "s1" / "ai_outputs.json"

    payload = {
        "inaturalist::1": _valid_outcome(media_id="1", evidence_type="whole_organism", basic=85),
        "inaturalist::2": _valid_outcome(
            media_id="2",
            evidence_type="feather",
            basic=20,
            field=75,
            species_card=40,
            indirect=90,
            global_quality=88,
        ),
        "inaturalist::3": _failed_outcome(),
        "inaturalist::4": _pre_ai_outcome(),
    }
    _write_json(ai_outputs_path, payload)

    report = audit_pmp_policy_snapshot(snapshot_id="s1", snapshot_root=snapshot_root)

    generation = report["generation_metrics"]
    assert generation["processed_media_count"] == 4
    assert generation["pmp_profile_valid_count"] == 2
    assert generation["pmp_profile_failed_count"] == 1
    assert generation["pre_ai_rejected_count"] == 1

    basic_counts = report["usage_eligibility_counts"]["basic_identification"]
    assert basic_counts["eligible"] >= 1
    assert basic_counts["not_recommended"] >= 1

    indirect_counts = report["usage_eligibility_counts"]["indirect_evidence_learning"]
    assert indirect_counts["eligible"] >= 1


def test_policy_audit_handles_failed_and_pre_ai_and_qualification_none(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data/raw/inaturalist"
    ai_outputs_path = snapshot_root / "s2" / "ai_outputs.json"

    payload = {
        "inaturalist::1": _valid_outcome(media_id="1"),
        "inaturalist::2": _failed_outcome(),
        "inaturalist::3": _pre_ai_outcome(),
    }
    _write_json(ai_outputs_path, payload)

    report = audit_pmp_policy_snapshot(snapshot_id="s2", snapshot_root=snapshot_root)

    assert report["generation_metrics"]["pmp_profile_valid_count"] == 1
    assert report["generation_metrics"]["pmp_profile_failed_count"] == 1
    assert report["generation_metrics"]["pre_ai_rejected_count"] == 1
    assert report["ai_outputs_broken"] is False


def test_policy_audit_emits_no_runtime_fields(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data/raw/inaturalist"
    ai_outputs_path = snapshot_root / "s3" / "ai_outputs.json"

    payload = {
        "inaturalist::1": _valid_outcome(media_id="1", evidence_type="whole_organism", basic=90)
    }
    _write_json(ai_outputs_path, payload)

    report = audit_pmp_policy_snapshot(snapshot_id="s3", snapshot_root=snapshot_root)

    shape = report["policy_summary"]["policy_output_shape"]
    assert shape["contains_playable"] is False
    assert shape["contains_selected_for_quiz"] is False
    assert shape["contains_runtime_ready"] is False
    assert shape["contains_selectedOptionId"] is False
