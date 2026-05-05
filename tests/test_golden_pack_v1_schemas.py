from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
HEX64 = "a" * 64


def _load_schema(file_name: str) -> dict:
    return json.loads((SCHEMAS_DIR / file_name).read_text(encoding="utf-8"))


def _build_valid_manifest() -> dict:
    return {
        "schema_version": "golden_pack_manifest.v1",
        "pack_id": "belgian_birds_mvp_v1",
        "contract_version": "golden_pack.v1",
        "build_timestamp": "2026-05-05T10:00:00Z",
        "scope": "belgian_birds_mvp",
        "runtime_surface": "artifact_only",
        "contract_status": "before_mvp_candidate",
        "gates": [
            {"gate_id": "question_count", "status": "passed"},
            {"gate_id": "media_eligibility", "status": "warning", "message": "license review pending"}
        ],
        "warnings": ["license review pending"],
        "non_actions": ["no_distractor_relationship_persistence"],
        "evidence_links": [
            {"path": "docs/audits/evidence/database_integrity_runtime_handoff_audit.json"}
        ],
        "audit_links": [
            {"path": "docs/audits/database-integrity-runtime-handoff-audit.md"}
        ],
        "checksums": {
            "pack.json": {"sha256": HEX64},
            "validation_report.json": {"sha256": HEX64},
            "media_files": [
                {"path": "media/q0001.jpg", "sha256": HEX64}
            ]
        },
        "PERSIST_DISTRACTOR_RELATIONSHIPS_V1": False,
        "DATABASE_PHASE_CLOSED": False,
    }


def _build_valid_pack() -> dict:
    media = []
    questions = []
    for idx in range(1, 31):
        question_num = f"{idx:04d}"
        media_id = f"m{question_num}"
        question_id = f"gbbmvp1_q{question_num}"
        correct_option_id = f"{question_id}_opt1"
        media.append(
            {
                "media_id": media_id,
                "runtime_uri": f"media/{media_id}.jpg",
                "source_url": f"https://example.org/source/{media_id}",
                "source": "inaturalist",
                "creator": "Jane Doe",
                "license": "CC-BY-4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "attribution_text": f"Photo {media_id} by Jane Doe (CC-BY-4.0)",
                "checksum": HEX64,
            }
        )
        questions.append(
            {
                "question_id": question_id,
                "primary_media_id": media_id,
                "prompt": "Quelle espece est visible sur cette image ?",
                "options": [
                    {
                        "option_id": correct_option_id,
                        "taxon_ref": {"type": "canonical_taxon", "id": f"taxon:birds:{idx:06d}"},
                        "display_label": f"Espece cible {idx}",
                        "is_correct": True,
                    },
                    {
                        "option_id": f"{question_id}_opt2",
                        "taxon_ref": {"type": "canonical_taxon", "id": f"taxon:birds:{idx + 100:06d}"},
                        "display_label": f"Distracteur A {idx}",
                        "is_correct": False,
                    },
                    {
                        "option_id": f"{question_id}_opt3",
                        "taxon_ref": {"type": "canonical_taxon", "id": f"taxon:birds:{idx + 200:06d}"},
                        "display_label": f"Distracteur B {idx}",
                        "is_correct": False,
                    },
                    {
                        "option_id": f"{question_id}_opt4",
                        "taxon_ref": {"type": "referenced_taxon", "id": f"ref:birds:{idx:06d}"},
                        "display_label": f"Distracteur Ref {idx}",
                        "is_correct": False,
                        "referenced_only": True,
                        "provenance": {"source": "inaturalist_similar_species"},
                    },
                ],
                "correct_option_id": correct_option_id,
                "feedback_short": "Regarde le motif de la tete et la forme du bec.",
                "feedback_source": "database_authored",
            }
        )
    return {
        "schema_version": "golden_pack.v1",
        "pack_id": "belgian_birds_mvp_v1",
        "locale": "fr",
        "questions": questions,
        "media": media,
    }


def _build_valid_validation_report() -> dict:
    return {
        "schema_version": "golden_pack_validation_report.v1",
        "pack_id": "belgian_birds_mvp_v1",
        "status": "passed",
        "schema_validity": {
            "manifest_schema_valid": True,
            "pack_schema_valid": True,
            "validation_report_schema_valid": True,
        },
        "count_checks": {
            "expected_questions": 30,
            "actual_questions": 30,
            "expected_options_per_question": 4,
            "expected_correct_options_per_question": 1,
            "expected_distractors_per_question": 3,
            "status": "passed",
        },
        "target_candidates_considered": 45,
        "selected_targets": [f"taxon:birds:{idx:06d}" for idx in range(1, 31)],
        "rejected_targets": [
            {"taxon_ref_id": "taxon:birds:000999", "reason_codes": ["missing_media"]}
        ],
        "label_checks": {
            "all_display_labels_runtime_safe": True,
            "no_placeholder_labels": True,
            "no_empty_labels": True,
            "no_invented_labels": True,
            "no_scientific_fallback_primary_labels": True,
        },
        "distractor_checks": {
            "exactly_three_distractors_per_question": True,
            "options_have_taxon_ref": True,
            "no_generic_canonical_taxon_id_fields": True,
            "referenced_taxon_rules_valid": True,
            "no_emergency_fallback_distractors": True,
        },
        "media_eligibility_checks": {
            "all_primary_media_basic_identification_eligible": True,
            "missing_primary_media_count": 0,
        },
        "media_copy_checksum_checks": {
            "all_runtime_media_copied": True,
            "all_media_checksums_verified": True,
            "missing_runtime_media_paths": [],
        },
        "media_pack_size_check": {
            "total_bytes": 32000000,
            "max_bytes": 50000000,
            "within_limit": True,
        },
        "attribution_checks": {
            "all_attribution_fields_present": True,
            "missing_attribution_entries": [],
        },
        "feedback_checks": {
            "all_questions_have_feedback_short": True,
            "fallback_database_mvp_count": 0,
        },
        "warnings": [],
        "blockers": [],
    }


def _validate(schema_name: str, payload: dict) -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")
    jsonschema.validate(instance=payload, schema=_load_schema(schema_name))


def test_manifest_minimal_valid_passes() -> None:
    _validate("golden_pack_manifest_v1.schema.json", _build_valid_manifest())


def test_pack_minimal_valid_with_30_questions_passes() -> None:
    _validate("golden_pack_v1.schema.json", _build_valid_pack())


def test_validation_report_valid_passes() -> None:
    _validate(
        "golden_pack_validation_report_v1.schema.json",
        _build_valid_validation_report(),
    )


def test_wrong_schema_version_fails() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")
    payload = _build_valid_pack()
    payload["schema_version"] = "golden_pack.v0"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=payload, schema=_load_schema("golden_pack_v1.schema.json"))


def test_additional_property_fails() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")
    payload = _build_valid_manifest()
    payload["unexpected_field"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=payload,
            schema=_load_schema("golden_pack_manifest_v1.schema.json"),
        )


def test_pack_with_less_than_30_questions_fails() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")
    payload = _build_valid_pack()
    payload["questions"] = payload["questions"][:-1]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=payload, schema=_load_schema("golden_pack_v1.schema.json"))


def test_option_without_taxon_ref_fails() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")
    payload = _build_valid_pack()
    del payload["questions"][0]["options"][0]["taxon_ref"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=payload, schema=_load_schema("golden_pack_v1.schema.json"))


def test_option_with_canonical_taxon_id_field_fails() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")
    payload = _build_valid_pack()
    option = deepcopy(payload["questions"][0]["options"][0])
    option["canonical_taxon_id"] = "taxon:birds:000001"
    payload["questions"][0]["options"][0] = option
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=payload, schema=_load_schema("golden_pack_v1.schema.json"))


def test_media_runtime_uri_outside_media_folder_fails() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")
    payload = _build_valid_pack()
    payload["media"][0]["runtime_uri"] = "https://cdn.example.org/m0001.jpg"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=payload, schema=_load_schema("golden_pack_v1.schema.json"))


def test_manifest_with_database_phase_closed_true_fails() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")
    payload = _build_valid_manifest()
    payload["DATABASE_PHASE_CLOSED"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=payload,
            schema=_load_schema("golden_pack_manifest_v1.schema.json"),
        )


def test_manifest_with_persist_distractor_relationships_true_fails() -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")
    payload = _build_valid_manifest()
    payload["PERSIST_DISTRACTOR_RELATIONSHIPS_V1"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=payload,
            schema=_load_schema("golden_pack_manifest_v1.schema.json"),
        )
