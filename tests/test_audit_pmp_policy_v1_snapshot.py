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


def _build_metadata_fixture(root: Path, snapshot_id: str) -> Path:
    snapshot_dir = root / snapshot_id
    response_path = snapshot_dir / "responses" / "taxon_1.json"
    response_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(
        response_path,
        {
            "results": [
                {
                    "id": 501,
                    "species_guess": "Ardea cinerea",
                    "taxon": {
                        "id": 101,
                        "name": "Ardea cinerea",
                        "preferred_common_name": "Grey Heron",
                    },
                    "photos": [{"id": 1001}],
                },
                {
                    "id": 502,
                    "species_guess": "Fulica atra",
                    "taxon": {
                        "id": 102,
                        "name": "Fulica atra",
                        "preferred_common_name": "Eurasian Coot",
                    },
                    "photos": [{"id": 1002}],
                },
            ]
        },
    )
    taxon_path = snapshot_dir / "taxa" / "taxon_birds_000001.json"
    taxon_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(
        taxon_path,
        {
            "id": 101,
            "name": "Ardea cinerea",
            "preferred_common_name": "Grey Heron",
        },
    )
    manifest_path = snapshot_dir / "manifest.json"
    _write_json(
        manifest_path,
        {
            "snapshot_id": snapshot_id,
            "manifest_version": "inaturalist.snapshot.v3",
            "source_name": "inaturalist",
            "created_at": "2026-05-04T00:00:00Z",
            "taxon_seeds": [
                {
                    "canonical_taxon_id": "taxon:birds:000001",
                    "source_taxon_id": "101",
                    "accepted_scientific_name": "Ardea cinerea",
                    "common_names": ["Grey Heron"],
                    "query_params": {},
                    "response_path": "responses/taxon_1.json",
                    "taxon_payload_path": "taxa/taxon_birds_000001.json",
                }
            ],
            "media_downloads": [
                {
                    "source_media_id": "1001",
                    "source_observation_id": "501",
                    "image_path": "images/1001.jpg",
                    "download_status": "downloaded",
                    "source_url": "https://example.test/1001.jpg",
                },
                {
                    "source_media_id": "1002",
                    "source_observation_id": "502",
                    "image_path": "images/1002.jpg",
                    "download_status": "downloaded",
                    "source_url": "https://example.test/1002.jpg",
                },
            ],
        },
    )
    return manifest_path


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


def test_policy_audit_populates_metadata_in_examples_when_manifest_available(
    tmp_path: Path,
) -> None:
    snapshot_root = tmp_path / "data/raw/inaturalist"
    snapshot_id = "s4"
    _build_metadata_fixture(snapshot_root, snapshot_id)
    ai_outputs_path = snapshot_root / snapshot_id / "ai_outputs.json"
    payload = {
        "inaturalist::1001": _valid_outcome(
            media_id="1001", evidence_type="whole_organism", basic=90
        ),
        "inaturalist::1002": _valid_outcome(
            media_id="1002",
            evidence_type="feather",
            basic=20,
            field=75,
            species_card=30,
            indirect=90,
            global_quality=88,
        ),
    }
    _write_json(ai_outputs_path, payload)

    report = audit_pmp_policy_snapshot(snapshot_id=snapshot_id, snapshot_root=snapshot_root)

    assert report["metadata_join_status"] == "joined_from_manifest"
    example = report["examples"]["whole_organism_basic_identification_eligible"]
    assert example["scientific_name"] == "Ardea cinerea"
    assert example["canonical_taxon_id"] == "taxon:birds:000001"


def test_policy_audit_generates_taxon_summaries_when_metadata_available(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data/raw/inaturalist"
    snapshot_id = "s5"
    _build_metadata_fixture(snapshot_root, snapshot_id)
    ai_outputs_path = snapshot_root / snapshot_id / "ai_outputs.json"
    payload = {
        "inaturalist::1001": _valid_outcome(
            media_id="1001", evidence_type="whole_organism", basic=45, species_card=40
        ),
        "inaturalist::1002": _failed_outcome(),
    }
    _write_json(ai_outputs_path, payload)

    report = audit_pmp_policy_snapshot(snapshot_id=snapshot_id, snapshot_root=snapshot_root)

    taxon_summary = report["taxon_policy_summary"]
    assert taxon_summary["taxon_count"] >= 1
    assert taxon_summary["top_taxa_by_media_count"][0]["taxon"] == "taxon:birds:000001"
    assert taxon_summary["count_by_taxon"]["taxon:birds:000001"] == 2
    assert (
        taxon_summary["taxa_without_basic_identification_eligible"][0]["taxon"]
        == "taxon:birds:000001"
    )
    assert taxon_summary["taxa_without_species_card_eligible"][0]["taxon"] == "taxon:birds:000001"
    assert taxon_summary["taxa_with_high_failure_rate"][0]["taxon"] == "taxon:birds:000001"


def test_policy_audit_works_without_metadata_join(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data/raw/inaturalist"
    ai_outputs_path = snapshot_root / "s6" / "ai_outputs.json"
    _write_json(ai_outputs_path, {"inaturalist::1": _valid_outcome(media_id="1")})

    report = audit_pmp_policy_snapshot(snapshot_id="s6", snapshot_root=snapshot_root)

    assert report["metadata_join_status"] == "not_available"


def test_policy_api_exports_available_from_package() -> None:
    from database_core.qualification import (  # noqa: PLC0415
        PMP_POLICY_VERSION,
        classify_usage_score,
        evaluate_pmp_outcome_policy,
        evaluate_pmp_profile_policy,
        is_complex_evidence_type,
        is_indirect_evidence_type,
    )

    assert PMP_POLICY_VERSION == "pmp_qualification_policy.v1"
    assert callable(classify_usage_score)
    assert callable(evaluate_pmp_outcome_policy)
    assert callable(evaluate_pmp_profile_policy)
    assert callable(is_complex_evidence_type)
    assert callable(is_indirect_evidence_type)
