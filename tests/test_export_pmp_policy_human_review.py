from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.export_pmp_policy_human_review import export_pmp_policy_human_review


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _valid_outcome(
    *,
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
        "review_contract_version": "pedagogical_media_profile_v1",
        "pedagogical_media_profile": {
            "review_status": "valid",
            "organism_group": "bird",
            "evidence_type": evidence_type,
            "technical_profile": {"technical_quality": "medium"},
            "observation_profile": {"subject_visibility": "medium"},
            "identification_profile": {
                "diagnostic_feature_visibility": "medium",
                "visible_field_marks": [
                    {
                        "feature": "white frontal shield",
                        "body_part": "head",
                        "visibility": "high",
                        "importance": "high",
                        "confidence": 0.9,
                    }
                ],
            },
            "biological_profile_visible": {
                "sex": {"value": "unknown"},
                "life_stage": {"value": "adult"},
                "plumage_state": {"value": "unknown"},
                "seasonal_state": {"value": "unknown"},
            },
            "limitations": ["occlusion by reeds"],
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
        "qualification": None,
    }


def _failed_outcome() -> dict[str, object]:
    return {
        "status": "pedagogical_media_profile_failed",
        "review_contract_version": "pedagogical_media_profile_v1",
        "pedagogical_media_profile": {
            "review_status": "failed",
            "failure_reason": "schema_validation_failed",
        },
        "qualification": None,
    }


def _pre_ai_outcome() -> dict[str, object]:
    return {
        "status": "insufficient_resolution_pre_ai",
        "review_contract_version": "pedagogical_media_profile_v1",
        "pedagogical_media_profile": None,
        "qualification": None,
    }


def _build_metadata_fixture(root: Path, snapshot_id: str) -> None:
    snapshot_dir = root / snapshot_id
    _write_json(
        snapshot_dir / "responses" / "taxon_1.json",
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
                {
                    "id": 503,
                    "species_guess": "Gallinula chloropus",
                    "taxon": {
                        "id": 103,
                        "name": "Gallinula chloropus",
                        "preferred_common_name": "Common Moorhen",
                    },
                    "photos": [{"id": 1003}],
                },
            ]
        },
    )
    _write_json(
        snapshot_dir / "taxa" / "taxon_birds_000001.json",
        {"id": 101, "preferred_common_name": "Grey Heron"},
    )
    _write_json(
        snapshot_dir / "manifest.json",
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
                {
                    "source_media_id": "1003",
                    "source_observation_id": "503",
                    "image_path": "images/1003.jpg",
                    "download_status": "downloaded",
                    "source_url": "https://example.test/1003.jpg",
                },
            ],
        },
    )


def test_export_generates_csv_and_jsonl_with_required_columns(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data/raw/inaturalist"
    snapshot_id = "s1"
    _build_metadata_fixture(snapshot_root, snapshot_id)
    ai_outputs_path = snapshot_root / snapshot_id / "ai_outputs.json"
    _write_json(
        ai_outputs_path,
        {
            "inaturalist::1001": _valid_outcome(),
            "inaturalist::1002": _valid_outcome(evidence_type="feather", basic=20, indirect=91),
            "inaturalist::1003": _failed_outcome(),
        },
    )

    output_csv = tmp_path / "review.csv"
    output_jsonl = tmp_path / "review.jsonl"
    summary = export_pmp_policy_human_review(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        output_csv=output_csv,
        output_jsonl=output_jsonl,
        sample_size=3,
        seed=42,
        include_failed=True,
        include_pre_ai=False,
    )

    assert summary["review_item_count"] == 3
    assert output_csv.exists()
    assert output_jsonl.exists()

    with output_csv.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert rows
    required = {
        "review_item_id",
        "scientific_name",
        "common_name_en",
        "basic_identification_policy",
        "human_overall_judgment",
        "human_notes",
    }
    assert required.issubset(reader.fieldnames or [])
    assert rows[0]["metadata_join_status"] == "joined_from_manifest"

    jsonl_rows = [
        json.loads(line)
        for line in output_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(jsonl_rows) == 3


def test_export_is_deterministic_with_seed(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data/raw/inaturalist"
    snapshot_id = "s2"
    _build_metadata_fixture(snapshot_root, snapshot_id)
    ai_outputs_path = snapshot_root / snapshot_id / "ai_outputs.json"
    _write_json(
        ai_outputs_path,
        {
            "inaturalist::1001": _valid_outcome(),
            "inaturalist::1002": _valid_outcome(evidence_type="feather", basic=20, indirect=91),
            "inaturalist::1003": _pre_ai_outcome(),
        },
    )

    output_csv_a = tmp_path / "a.csv"
    output_csv_b = tmp_path / "b.csv"
    export_pmp_policy_human_review(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        output_csv=output_csv_a,
        output_jsonl=None,
        sample_size=3,
        seed=7,
        include_failed=True,
        include_pre_ai=True,
    )
    export_pmp_policy_human_review(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        output_csv=output_csv_b,
        output_jsonl=None,
        sample_size=3,
        seed=7,
        include_failed=True,
        include_pre_ai=True,
    )

    assert output_csv_a.read_text(encoding="utf-8") == output_csv_b.read_text(encoding="utf-8")


def test_export_works_without_metadata_and_records_absence(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data/raw/inaturalist"
    snapshot_id = "s3"
    ai_outputs_path = snapshot_root / snapshot_id / "ai_outputs.json"
    _write_json(ai_outputs_path, {"inaturalist::1": _valid_outcome()})

    output_csv = tmp_path / "review.csv"
    export_pmp_policy_human_review(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        output_csv=output_csv,
        output_jsonl=None,
        sample_size=1,
    )

    with output_csv.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["metadata_join_status"] == "not_available"
    assert row["scientific_name"] == ""


def test_export_includes_indirect_failed_and_pre_ai_when_available(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data/raw/inaturalist"
    snapshot_id = "s4"
    _build_metadata_fixture(snapshot_root, snapshot_id)
    ai_outputs_path = snapshot_root / snapshot_id / "ai_outputs.json"
    _write_json(
        ai_outputs_path,
        {
            "inaturalist::1001": _valid_outcome(evidence_type="whole_organism", basic=85),
            "inaturalist::1002": _valid_outcome(evidence_type="feather", basic=20, indirect=90),
            "inaturalist::1003": _failed_outcome(),
            "inaturalist::9999": _pre_ai_outcome(),
        },
    )

    output_csv = tmp_path / "review.csv"
    export_pmp_policy_human_review(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        output_csv=output_csv,
        output_jsonl=None,
        sample_size=4,
        include_failed=True,
        include_pre_ai=True,
    )

    with output_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    evidence_types = {row["evidence_type"] for row in rows}
    policy_statuses = {row["policy_status"] for row in rows}
    assert "feather" in evidence_types
    assert "profile_failed" in policy_statuses
    assert "pre_ai_rejected" in policy_statuses
