from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.prepare_referenced_taxon_shell_apply_plan_v1 import run_prepare


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _shell_candidates_fixture() -> dict:
    return {
        "items": [
            {
                "source": "inaturalist",
                "source_taxon_id": "1001",
                "scientific_name": "Mapped taxon",
                "mapped_canonical_taxon_id": "taxon:birds:000001",
                "existing_referenced_taxon_id": None,
                "common_names_i18n": {"en": ["Mapped"]},
                "proposed_mapping_status": "mapped",
                "confidence": 1.0,
                "reason_codes": ["mapped"],
                "notes": [],
            },
            {
                "source": "inaturalist",
                "source_taxon_id": "2002",
                "scientific_name": "Existing referenced",
                "mapped_canonical_taxon_id": None,
                "existing_referenced_taxon_id": "reftaxon:inaturalist:2002",
                "common_names_i18n": {"fr": ["Nom FR"], "en": ["Name EN"]},
                "proposed_mapping_status": "auto_referenced_high_confidence",
                "confidence": 0.9,
                "reason_codes": ["existing"],
                "notes": [],
            },
            {
                "source": "inaturalist",
                "source_taxon_id": "3003",
                "scientific_name": "Needs shell FR",
                "mapped_canonical_taxon_id": None,
                "existing_referenced_taxon_id": None,
                "common_names_i18n": {"fr": ["Nom FR shell"], "en": ["Name EN shell"]},
                "proposed_mapping_status": "auto_referenced_high_confidence",
                "confidence": 0.8,
                "reason_codes": ["candidate_for_referenced_shell"],
                "notes": [],
            },
            {
                "source": "inaturalist",
                "source_taxon_id": "4004",
                "scientific_name": "Needs shell no FR",
                "mapped_canonical_taxon_id": None,
                "existing_referenced_taxon_id": None,
                "common_names_i18n": {"en": ["Only EN"]},
                "proposed_mapping_status": "auto_referenced_low_confidence",
                "confidence": 0.6,
                "reason_codes": ["candidate_for_referenced_shell"],
                "notes": [],
            },
            {
                "source": "inaturalist",
                "source_taxon_id": "5005",
                "scientific_name": "",
                "mapped_canonical_taxon_id": None,
                "existing_referenced_taxon_id": None,
                "common_names_i18n": {"en": ["No sci"]},
                "proposed_mapping_status": "ambiguous",
                "confidence": 0.4,
                "reason_codes": ["missing_scientific_name"],
                "notes": [],
            },
        ]
    }


def _canonical_fixture() -> dict:
    return {
        "canonical_taxa": [
            {
                "canonical_taxon_id": "taxon:birds:000001",
                "accepted_scientific_name": "Mapped taxon",
                "external_source_mappings": [
                    {"source_name": "inaturalist", "external_id": "1001"}
                ],
            }
        ]
    }


def _relationship_fixture() -> dict:
    return {
        "relationships": [
            {
                "candidate_taxon_ref_type": "referenced_taxon",
                "candidate_taxon_ref_id": "reftaxon:inaturalist:3003",
                "candidate_scientific_name": "Needs shell FR",
            },
            {
                "candidate_taxon_ref_type": "referenced_taxon",
                "candidate_taxon_ref_id": "reftaxon:inaturalist:4004",
                "candidate_scientific_name": "Needs shell no FR",
            },
        ]
    }


def _existing_referenced_fixture() -> dict:
    return {
        "referenced_taxa": [
            {
                "referenced_taxon_id": "reftaxon:inaturalist:2002",
                "source_taxon_id": "2002",
                "scientific_name": "Existing referenced",
                "common_names_i18n": {"fr": ["Nom FR"], "en": ["Name EN"]},
            }
        ]
    }


def _localized_audit_fixture() -> dict:
    return {
        "decision": "BLOCKED_BY_NAME_SOURCE_GAPS",
        "distractor_candidate_taxa_missing_fr": 202,
    }


def _run_default(tmp_path: Path, *, apply: bool = False, confirm: str | None = None) -> dict:
    shell = tmp_path / "shell.json"
    rel = tmp_path / "rel.json"
    canonical = tmp_path / "canonical.json"
    existing_ref = tmp_path / "existing_ref.json"
    local_audit = tmp_path / "local_audit.json"
    local_patch = tmp_path / "local_patch.json"
    output_json = tmp_path / "out" / "plan.json"
    output_md = tmp_path / "out" / "plan.md"
    apply_output_ref = tmp_path / "out" / "referenced_snapshot.json"

    _write_json(shell, _shell_candidates_fixture())
    _write_json(rel, _relationship_fixture())
    _write_json(canonical, _canonical_fixture())
    _write_json(existing_ref, _existing_referenced_fixture())
    _write_json(local_audit, _localized_audit_fixture())
    _write_json(local_patch, {"patches": []})

    return run_prepare(
        shell_candidates_path=shell,
        relationship_candidates_path=rel,
        canonical_path=canonical,
        existing_referenced_path=existing_ref,
        localized_audit_path=local_audit,
        localized_patch_file=local_patch,
        output_json=output_json,
        output_md=output_md,
        apply_output_referenced_path=apply_output_ref,
        apply=apply,
        confirm_apply=confirm,
    )


def test_mapped_canonical_candidate_does_not_create_shell(tmp_path: Path) -> None:
    result = _run_default(tmp_path)
    reasons = [row["reason"] for row in result["skipped_records"]]
    assert "mapped_to_existing_canonical_taxon" in reasons


def test_existing_referenced_taxon_is_reused(tmp_path: Path) -> None:
    result = _run_default(tmp_path)
    reasons = [row["reason"] for row in result["skipped_records"]]
    assert "existing_referenced_taxon_reused" in reasons


def test_unmapped_clean_candidate_creates_shell_plan(tmp_path: Path) -> None:
    result = _run_default(tmp_path)
    source_ids = {row["source_taxon_id"] for row in result["apply_records"]}
    assert "3003" in source_ids


def test_missing_scientific_name_becomes_ambiguous_or_ignored(tmp_path: Path) -> None:
    result = _run_default(tmp_path)
    reasons = [row["reason"] for row in result["skipped_records"]]
    assert any("missing_scientific_name" in reason for reason in reasons)


def test_dry_run_does_not_mutate(tmp_path: Path) -> None:
    result = _run_default(tmp_path)
    assert result["dry_run"] is True
    assert result["apply_result"]["storage_mutated"] is False


def test_apply_path_is_guarded(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _run_default(tmp_path, apply=True, confirm=None)


def test_shell_with_fr_name_sets_can_be_distractor_fr_true(tmp_path: Path) -> None:
    result = _run_default(tmp_path)
    record = next(row for row in result["apply_records"] if row["source_taxon_id"] == "3003")
    assert record["can_be_distractor_fr"] is True


def test_shell_without_fr_name_sets_can_be_distractor_fr_false(tmp_path: Path) -> None:
    result = _run_default(tmp_path)
    record = next(row for row in result["apply_records"] if row["source_taxon_id"] == "4004")
    assert record["can_be_distractor_fr"] is False


def test_json_and_markdown_outputs_are_written(tmp_path: Path) -> None:
    _run_default(tmp_path)
    assert (tmp_path / "out" / "plan.json").exists()
    assert (tmp_path / "out" / "plan.md").exists()
