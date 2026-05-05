from __future__ import annotations

import json
from pathlib import Path

from scripts.apply_taxon_localized_name_patches_v1 import apply_patches, run_apply
from scripts.audit_taxon_localized_names_v1 import run_audit


def _schema_payload() -> dict:
    schema_path = Path("schemas/taxon_localized_name_patch_v1.schema.json")
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _canonical_payload() -> dict:
    return {
        "canonical_taxa": [
            {
                "canonical_taxon_id": "taxon:birds:1",
                "accepted_scientific_name": "Columba palumbus",
                "common_names_by_language": {"en": ["Common Wood Pigeon"]},
            },
            {
                "canonical_taxon_id": "taxon:birds:2",
                "accepted_scientific_name": "Sturnus vulgaris",
                "common_names_by_language": {"fr": ["Etourneau sansonnet"]},
            },
        ]
    }


def _referenced_candidates_payload() -> dict:
    return {
        "items": [
            {
                "source_taxon_id": "3017",
                "scientific_name": "Streptopelia decaocto",
                "common_names_i18n": {"en": ["Eurasian Collared-Dove"]},
            }
        ]
    }


def _relationships_payload() -> dict:
    return {
        "relationships": [
            {
                "candidate_taxon_ref_type": "canonical_taxon",
                "candidate_taxon_ref_id": "taxon:birds:1",
                "candidate_scientific_name": "Columba palumbus",
            },
            {
                "candidate_taxon_ref_type": "referenced_taxon",
                "candidate_taxon_ref_id": "reftaxon:inaturalist:3017",
                "candidate_scientific_name": "Streptopelia decaocto",
            },
        ]
    }


def _valid_patch_rows() -> list[dict]:
    return [
        {
            "schema_version": "1.0",
            "patch_id": "p1",
            "taxon_ref_type": "canonical_taxon",
            "canonical_taxon_id": "taxon:birds:1",
            "common_name_fr": "Pigeon ramier",
            "source": "manual_override",
            "confidence": "high",
            "reviewer": "qa",
        },
        {
            "schema_version": "1.0",
            "patch_id": "p2",
            "taxon_ref_type": "referenced_taxon",
            "referenced_taxon_id": "reftaxon:inaturalist:3017",
            "common_name_fr": "Tourterelle turque",
            "source": "manual_override",
            "confidence": "high",
            "reviewer": "qa",
        },
    ]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_unresolved_taxon_patch_is_never_applied() -> None:
    patches = [
        {
            "patch_id": "u1",
            "taxon_ref_type": "unresolved_taxon",
            "common_name_fr": "Nom test",
            "source": "manual_override",
            "confidence": "high",
            "reviewer": "qa",
        }
    ]
    canonical = [
        {
            "canonical_taxon_id": "taxon:birds:1",
            "scientific_name": "Columba palumbus",
            "common_names_i18n": {},
        }
    ]

    result = apply_patches(patches, canonical_taxa=canonical, referenced_taxa=[])

    assert result["applied"] == []
    assert result["skipped"][0]["reason"] == "unresolved_taxon_patch_is_audit_only"


def test_conflict_requires_manual_override_with_reviewer() -> None:
    patches = [
        {
            "patch_id": "c1",
            "taxon_ref_type": "canonical_taxon",
            "canonical_taxon_id": "taxon:birds:1",
            "common_name_fr": "Nouveau nom",
            "source": "reference_list",
            "confidence": "high",
        }
    ]
    canonical = [
        {
            "canonical_taxon_id": "taxon:birds:1",
            "scientific_name": "Columba palumbus",
            "common_names_i18n": {"fr": ["Ancien nom"]},
        }
    ]

    result = apply_patches(patches, canonical_taxa=canonical, referenced_taxa=[])

    assert result["applied"] == []
    assert result["conflicts"][0]["resolution"] == "blocked_conflict"


def test_run_apply_dry_run_writes_evidence_only(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.json"
    canonical_path = tmp_path / "canonical.json"
    referenced_candidates_path = tmp_path / "referenced_candidates.json"
    referenced_snapshot_path = tmp_path / "referenced_snapshot.json"
    patch_file = tmp_path / "patches.json"

    _write_json(schema_path, _schema_payload())
    _write_json(canonical_path, _canonical_payload())
    _write_json(referenced_candidates_path, _referenced_candidates_payload())
    _write_json(referenced_snapshot_path, {"referenced_taxa": []})
    _write_json(patch_file, {"patches": _valid_patch_rows()})

    output_canonical = tmp_path / "out" / "canonical.json"
    output_referenced = tmp_path / "out" / "referenced.json"
    output_evidence_json = tmp_path / "evidence" / "apply.json"
    output_evidence_md = tmp_path / "evidence" / "apply.md"

    result = run_apply(
        patch_file=patch_file,
        patch_schema_path=schema_path,
        canonical_path=canonical_path,
        referenced_candidates_path=referenced_candidates_path,
        referenced_snapshot_path=referenced_snapshot_path,
        dry_run=True,
        apply=False,
        output_canonical=output_canonical,
        output_referenced=output_referenced,
        output_evidence_json=output_evidence_json,
        output_evidence_md=output_evidence_md,
    )

    assert result["mode"] == "dry_run"
    assert output_evidence_json.exists()
    assert output_evidence_md.exists()
    assert not output_canonical.exists()
    assert not output_referenced.exists()


def test_run_apply_apply_mode_writes_outputs(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.json"
    canonical_path = tmp_path / "canonical.json"
    referenced_candidates_path = tmp_path / "referenced_candidates.json"
    referenced_snapshot_path = tmp_path / "referenced_snapshot.json"
    patch_file = tmp_path / "patches.json"

    _write_json(schema_path, _schema_payload())
    _write_json(canonical_path, _canonical_payload())
    _write_json(referenced_candidates_path, _referenced_candidates_payload())
    _write_json(referenced_snapshot_path, {"referenced_taxa": []})
    _write_json(patch_file, {"patches": _valid_patch_rows()})

    output_canonical = tmp_path / "out" / "canonical.json"
    output_referenced = tmp_path / "out" / "referenced.json"
    output_evidence_json = tmp_path / "evidence" / "apply.json"
    output_evidence_md = tmp_path / "evidence" / "apply.md"

    result = run_apply(
        patch_file=patch_file,
        patch_schema_path=schema_path,
        canonical_path=canonical_path,
        referenced_candidates_path=referenced_candidates_path,
        referenced_snapshot_path=referenced_snapshot_path,
        dry_run=False,
        apply=True,
        output_canonical=output_canonical,
        output_referenced=output_referenced,
        output_evidence_json=output_evidence_json,
        output_evidence_md=output_evidence_md,
    )

    assert result["mode"] == "apply"
    assert output_canonical.exists()
    assert output_referenced.exists()

    canonical_out = json.loads(output_canonical.read_text(encoding="utf-8"))
    first = canonical_out["canonical_taxa"][0]
    assert first["common_names_i18n"]["fr"] == ["Pigeon ramier"]


def test_run_audit_reports_before_after_candidate_usability(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.json"
    canonical_path = tmp_path / "canonical.json"
    referenced_candidates_path = tmp_path / "referenced_candidates.json"
    referenced_snapshot_path = tmp_path / "referenced_snapshot.json"
    rel_path = tmp_path / "relationships.json"
    patch_file = tmp_path / "patches.json"

    _write_json(schema_path, _schema_payload())
    _write_json(canonical_path, _canonical_payload())
    _write_json(referenced_candidates_path, _referenced_candidates_payload())
    _write_json(referenced_snapshot_path, {"referenced_taxa": []})
    _write_json(rel_path, _relationships_payload())
    _write_json(patch_file, {"patches": _valid_patch_rows()})

    output_json = tmp_path / "evidence" / "audit.json"
    output_md = tmp_path / "evidence" / "audit.md"

    result = run_audit(
        canonical_path=canonical_path,
        referenced_candidates_path=referenced_candidates_path,
        referenced_snapshot_path=referenced_snapshot_path,
        candidate_relationship_path=rel_path,
        patch_schema_path=schema_path,
        patch_file=patch_file,
        output_json=output_json,
        output_md=output_md,
    )

    assert output_json.exists()
    assert output_md.exists()
    assert result["before"]["can_be_used_now_fr"] == 0
    assert result["after"]["can_be_used_now_fr"] == 2
    assert result["manual_patches_available"] == 2


def test_invalid_patch_is_counted_in_audit(tmp_path: Path) -> None:
    schema_path = tmp_path / "schema.json"
    canonical_path = tmp_path / "canonical.json"
    referenced_candidates_path = tmp_path / "referenced_candidates.json"
    referenced_snapshot_path = tmp_path / "referenced_snapshot.json"
    rel_path = tmp_path / "relationships.json"
    patch_file = tmp_path / "patches.json"

    invalid_patch = {
        "schema_version": "1.0",
        "patch_id": "bad1",
        "taxon_ref_type": "canonical_taxon",
        "source": "manual_override",
        "confidence": "high",
        "common_name_fr": "Nom",
    }

    _write_json(schema_path, _schema_payload())
    _write_json(canonical_path, _canonical_payload())
    _write_json(referenced_candidates_path, _referenced_candidates_payload())
    _write_json(referenced_snapshot_path, {"referenced_taxa": []})
    _write_json(rel_path, _relationships_payload())
    _write_json(patch_file, {"patches": [invalid_patch]})

    output_json = tmp_path / "evidence" / "audit.json"
    output_md = tmp_path / "evidence" / "audit.md"

    result = run_audit(
        canonical_path=canonical_path,
        referenced_candidates_path=referenced_candidates_path,
        referenced_snapshot_path=referenced_snapshot_path,
        candidate_relationship_path=rel_path,
        patch_schema_path=schema_path,
        patch_file=patch_file,
        output_json=output_json,
        output_md=output_md,
    )

    assert result["decision"] == "NEEDS_NAME_PATCH_FIXES"
    assert len(result["invalid_patches"]) == 1
