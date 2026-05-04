from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_pedagogical_media_profile_v1_snapshot_outputs import (
    DECISION_BLOCKED_RUN,
    DECISION_READY_CORPUS,
    audit_snapshot_outputs,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _valid_outcome(
    *,
    media_id: str,
    evidence_type: str = "whole_organism",
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
            "evidence_type": evidence_type,
            "identification_profile": {
                "visible_field_marks": [
                    {
                        "feature": "mark",
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


def _failed_outcome(
    *,
    media_id: str,
    error: dict[str, object],
    schema_failure_cause: str = "unknown_schema_failure",
) -> dict[str, object]:
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
            "diagnostics": {
                "schema_error_count": 1,
                "schema_failure_cause": schema_failure_cause,
                "scientific_name": "Ardea cinerea",
                "schema_errors": [error],
                "raw_model_output_excerpt": "{...}",
            },
        },
    }


def _build_metadata_fixture(root: Path, snapshot_id: str) -> Path:
    snapshot_dir = root / snapshot_id
    response_path = snapshot_dir / "responses" / "taxon_1.json"
    _write_json(
        response_path,
        {
            "results": [
                {
                    "id": 501,
                    "species_guess": "Ardea cinerea",
                    "taxon": {"id": 101, "name": "Ardea cinerea"},
                    "photos": [{"id": 1001}],
                },
                {
                    "id": 502,
                    "species_guess": "Fulica atra",
                    "taxon": {"id": 102, "name": "Fulica atra"},
                    "photos": [{"id": 1002}],
                },
            ]
        },
    )
    manifest_path = snapshot_dir / "manifest.json"
    _write_json(
        manifest_path,
        {
            "snapshot_id": snapshot_id,
            "taxon_seeds": [
                {
                    "canonical_taxon_id": "taxon:birds:000001",
                    "source_taxon_id": "101",
                    "accepted_scientific_name": "Ardea cinerea",
                    "response_path": "responses/taxon_1.json",
                }
            ],
            "media_downloads": [
                {"source_media_id": "1001", "source_observation_id": "501"},
                {"source_media_id": "1002", "source_observation_id": "502"},
            ],
        },
    )
    return manifest_path


def test_schema_error_diagnostics_support_type_cause_validator_and_paths(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data/raw/inaturalist"
    ai_outputs_path = snapshot_root / "s1" / "ai_outputs.json"

    payload = {
        "inaturalist::1": _failed_outcome(
            media_id="1",
            error={
                "type": "required",
                "loc": ["scores", "global_quality_score"],
                "message": "missing",
                "expected": ["global_quality_score"],
                "actual": None,
            },
            schema_failure_cause="missing_required_field",
        ),
        "inaturalist::2": _failed_outcome(
            media_id="2",
            error={
                "cause": "enum_mismatch",
                "path": "observation_profile.context_visible.1",
                "validator": "enum",
                "message": "not in enum",
                "expected": ["ground", "tree"],
                "actual": "wall",
            },
        ),
        "inaturalist::3": _failed_outcome(
            media_id="3",
            error={
                "validator": "maxItems",
                "path": "group_specific_profile.bird.bird_visible_parts",
                "message": "too long",
                "expected": 8,
                "actual": "<array len=11>",
            },
        ),
    }
    _write_json(ai_outputs_path, payload)

    report = audit_snapshot_outputs(snapshot_id="s1", snapshot_root=snapshot_root)

    generation = report["generation_metrics"]
    failure_diag = report["failure_diagnostics"]

    assert generation["pmp_failed_count"] == 3
    assert generation["schema_failure_cause_distribution"]["enum_mismatch"] >= 1
    assert generation["schema_failure_cause_distribution"]["required"] >= 1
    assert generation["schema_failure_cause_distribution"]["maxItems"] >= 1

    top_paths = {item["path"]: item["count"] for item in generation["top_schema_error_paths"]}
    assert "scores.global_quality_score" in top_paths
    assert "observation_profile.context_visible.1" in top_paths
    assert "group_specific_profile.bird.bird_visible_parts" in top_paths

    assert "enum_mismatch" in failure_diag["examples_by_failure_cause"]
    assert (
        "group_specific_profile.bird.bird_visible_parts"
        in failure_diag["examples_by_schema_error_path"]
    )


def test_manual_review_sample_recognizes_indirect_and_multiple_types(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data/raw/inaturalist"
    ai_outputs_path = snapshot_root / "s2" / "ai_outputs.json"

    payload = {
        "inaturalist::1001": _valid_outcome(
            media_id="1001",
            evidence_type="whole_organism",
            basic=90,
            indirect=0,
            global_quality=95,
        ),
        "inaturalist::1002": _valid_outcome(
            media_id="1002",
            evidence_type="whole_organism",
            basic=85,
            indirect=0,
            global_quality=92,
        ),
        "inaturalist::1003": _failed_outcome(
            media_id="1003",
            error={
                "cause": "enum_mismatch",
                "path": "x",
                "validator": "enum",
                "message": "bad",
            },
        ),
        "inaturalist::1004": _valid_outcome(
            media_id="1004",
            evidence_type="feather",
            basic=20,
            indirect=90,
            global_quality=88,
        ),
        "inaturalist::1005": _valid_outcome(
            media_id="1005",
            evidence_type="multiple_organisms",
            basic=40,
            indirect=65,
            global_quality=60,
        ),
    }
    _write_json(ai_outputs_path, payload)

    report = audit_snapshot_outputs(snapshot_id="s2", snapshot_root=snapshot_root)

    coverage = report["manual_review_sample_coverage"]
    sample = report["manual_review_sample"]
    sample_types = {item.get("evidence_type") for item in sample}

    assert coverage["has_high_quality_valid"] is True
    assert coverage["has_failed"] is True
    assert coverage["has_indirect_evidence"] is True
    assert coverage["has_partial_or_multiple"] is True
    assert coverage["has_low_basic_identification"] is True
    assert "feather" in sample_types
    assert "multiple_organisms" in sample_types


def test_missing_manual_categories_do_not_fail_audit(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data/raw/inaturalist"
    ai_outputs_path = snapshot_root / "s3" / "ai_outputs.json"

    payload = {
        "inaturalist::1": _valid_outcome(media_id="1", evidence_type="whole_organism"),
        "inaturalist::2": _valid_outcome(media_id="2", evidence_type="whole_organism"),
    }
    _write_json(ai_outputs_path, payload)

    report = audit_snapshot_outputs(snapshot_id="s3", snapshot_root=snapshot_root)

    assert report["generation_metrics"]["pmp_valid_count"] == 2
    assert report["generation_metrics"]["pmp_failed_count"] == 0
    assert len(report["manual_review_sample"]) >= 2


def test_score_metrics_by_evidence_type_are_computed(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data/raw/inaturalist"
    ai_outputs_path = snapshot_root / "s4" / "ai_outputs.json"

    payload = {
        "inaturalist::1": _valid_outcome(
            media_id="1",
            evidence_type="whole_organism",
            basic=90,
            indirect=0,
            global_quality=90,
        ),
        "inaturalist::2": _valid_outcome(
            media_id="2",
            evidence_type="whole_organism",
            basic=80,
            indirect=0,
            global_quality=80,
        ),
        "inaturalist::3": _valid_outcome(
            media_id="3",
            evidence_type="feather",
            basic=20,
            indirect=90,
            global_quality=95,
        ),
        "inaturalist::4": _failed_outcome(
            media_id="4",
            error={
                "cause": "enum_mismatch",
                "path": "x",
                "validator": "enum",
                "message": "bad",
            },
        ),
    }
    _write_json(ai_outputs_path, payload)

    report = audit_snapshot_outputs(snapshot_id="s4", snapshot_root=snapshot_root)

    by_evidence = report["score_metrics"]["score_metrics_by_evidence_type"]
    whole = by_evidence["whole_organism"]
    feather = by_evidence["feather"]

    assert whole["valid_count"] == 2
    assert whole["failed_count"] == 0
    assert whole["valid_rate"] == 1.0
    assert whole["average_global_quality_score"] == 85.0
    assert whole["average_usage_scores"]["indirect_evidence_learning"] == 0.0

    assert feather["valid_count"] == 1
    assert feather["average_usage_scores"]["basic_identification"] == 20.0
    assert feather["average_usage_scores"]["indirect_evidence_learning"] == 90.0


def test_metadata_join_populates_scientific_names_when_manifest_available(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data/raw/inaturalist"
    snapshot_id = "s5"
    _build_metadata_fixture(snapshot_root, snapshot_id)

    ai_outputs_path = snapshot_root / snapshot_id / "ai_outputs.json"
    payload = {
        "inaturalist::1001": _valid_outcome(media_id="1001", evidence_type="whole_organism"),
        "inaturalist::1002": _valid_outcome(media_id="1002", evidence_type="feather"),
    }
    _write_json(ai_outputs_path, payload)

    report = audit_snapshot_outputs(snapshot_id=snapshot_id, snapshot_root=snapshot_root)

    assert report["metadata_join_status"] == "joined_from_manifest"
    sample = report["manual_review_sample"]
    names = {item.get("scientific_name") for item in sample}
    assert "Ardea cinerea" in names
    assert "Fulica atra" in names


def test_missing_or_invalid_ai_outputs_returns_blocked_run_failed(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data/raw/inaturalist"

    missing_report = audit_snapshot_outputs(snapshot_id="missing", snapshot_root=snapshot_root)
    assert missing_report["decision"] == DECISION_BLOCKED_RUN

    invalid_path = snapshot_root / "invalid" / "ai_outputs.json"
    invalid_path.parent.mkdir(parents=True, exist_ok=True)
    invalid_path.write_text("not-json", encoding="utf-8")
    invalid_report = audit_snapshot_outputs(snapshot_id="invalid", snapshot_root=snapshot_root)
    assert invalid_report["decision"] == DECISION_BLOCKED_RUN


def test_audit_can_reach_ready_for_controlled_profiled_corpus_run(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data/raw/inaturalist"
    ai_outputs_path = snapshot_root / "s6" / "ai_outputs.json"
    payload = {
        "inaturalist::1": _valid_outcome(global_quality=90, basic=85, indirect=35, media_id="1"),
        "inaturalist::2": _valid_outcome(global_quality=87, basic=75, indirect=45, media_id="2"),
        "inaturalist::3": _valid_outcome(global_quality=88, basic=70, indirect=75, media_id="3"),
        "inaturalist::4": _valid_outcome(global_quality=84, basic=45, indirect=80, media_id="4"),
        "inaturalist::5": _valid_outcome(global_quality=83, basic=68, indirect=65, media_id="5"),
    }
    payload["inaturalist::4"]["pedagogical_media_profile"]["evidence_type"] = "feather"
    _write_json(ai_outputs_path, payload)

    report = audit_snapshot_outputs(snapshot_id="s6", snapshot_root=snapshot_root)

    assert report["generation_metrics"]["pmp_valid_rate"] == 1.0
    assert report["decision"] == DECISION_READY_CORPUS
    assert len(report["manual_review_sample"]) >= 5
