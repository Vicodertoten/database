from __future__ import annotations

import json
from pathlib import Path

from scripts.project_distractor_candidates_to_relationships_v1 import (
    project_candidates,
    run_projection,
)


def _load_schema() -> dict:
    schema_path = Path("schemas/distractor_relationship_v1.schema.json")
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _valid_candidate_record() -> dict:
    return {
        "relationship_id": "dr:test001",
        "target_canonical_taxon_id": "taxon:birds:000001",
        "target_scientific_name": "Columba palumbus",
        "candidate_taxon_ref_type": "canonical_taxon",
        "candidate_taxon_ref_id": "taxon:birds:000079",
        "candidate_scientific_name": "Streptopelia decaocto",
        "source": "inaturalist_similar_species",
        "source_rank": 1,
        "confusion_types": ["visual_similarity"],
        "pedagogical_value": "high",
        "difficulty_level": "medium",
        "learner_level": "mixed",
        "reason": "strong similar hint",
        "status": "candidate",
        "created_at": "2026-05-05T11:54:53.572537+00:00",
        # Audit-only fields that must be removed by projection.
        "candidate_has_french_name": True,
        "can_be_used_now_fr": True,
        "usability_blockers": [],
    }


def test_valid_candidate_projects_to_schema_compliant_relationship() -> None:
    schema = _load_schema()
    payload = {"relationships": [_valid_candidate_record()]}

    result = project_candidates(payload, schema, stable_referenced_ids=set())

    assert result["projected_records_count"] == 1
    assert result["rejected_records_count"] == 0
    assert result["schema_validation_error_count"] == 0


def test_audit_only_fields_are_removed() -> None:
    schema = _load_schema()
    payload = {"relationships": [_valid_candidate_record()]}

    result = project_candidates(payload, schema, stable_referenced_ids=set())
    projected = result["projected_records"][0]

    assert "candidate_has_french_name" not in projected
    assert "can_be_used_now_fr" not in projected
    assert "usability_blockers" not in projected


def test_invalid_candidate_is_rejected_with_reason() -> None:
    schema = _load_schema()
    invalid = _valid_candidate_record()
    invalid["target_canonical_taxon_id"] = ""
    payload = {"relationships": [invalid]}

    result = project_candidates(payload, schema, stable_referenced_ids=set())

    assert result["projected_records_count"] == 0
    assert result["rejected_records_count"] == 1
    assert "missing_target_canonical_taxon_id" in result["rejected_records"][0]["reasons"]


def test_extra_properties_are_not_present() -> None:
    schema = _load_schema()
    payload = {"relationships": [_valid_candidate_record()]}

    result = project_candidates(payload, schema, stable_referenced_ids=set())
    projected = result["projected_records"][0]
    allowed = set(schema["properties"].keys())

    assert set(projected.keys()).issubset(allowed)


def test_referenced_virtual_candidate_handling_is_explicit() -> None:
    schema = _load_schema()
    rec = _valid_candidate_record()
    rec["candidate_taxon_ref_type"] = "referenced_taxon"
    rec["candidate_taxon_ref_id"] = "reftaxon:inaturalist:3017"
    rec["status"] = "candidate"
    payload = {"relationships": [rec]}

    result = project_candidates(payload, schema, stable_referenced_ids=set())
    projected = result["projected_records"][0]

    assert projected["candidate_taxon_ref_type"] == "unresolved_taxon"
    assert projected["candidate_taxon_ref_id"] is None
    assert projected["status"] == "needs_review"


def test_projected_json_validates_against_schema() -> None:
    schema = _load_schema()
    payload = {"relationships": [_valid_candidate_record()]}

    result = project_candidates(payload, schema, stable_referenced_ids=set())
    assert result["schema_validation_error_count"] == 0


def test_json_and_markdown_outputs_are_written(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(_load_schema()), encoding="utf-8")

    input_path = tmp_path / "candidates.json"
    input_path.write_text(
        json.dumps({"relationships": [_valid_candidate_record()]}),
        encoding="utf-8",
    )

    output_json = tmp_path / "projected.json"
    output_md = tmp_path / "projected.md"

    result = run_projection(
        input_path=input_path,
        schema_path=schema_path,
        output_json_path=output_json,
        output_md_path=output_md,
        referenced_snapshot_path=None,
    )

    assert output_json.exists()
    assert output_md.exists()
    assert result["projected_records_count"] == 1
