from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_referenced_taxon_shell_needs_for_distractors import (
    _determine_decision,
    prepare_shell_candidates,
    run_audit,
    write_markdown_report,
)


def _canonical_taxa_fixture() -> list[dict[str, object]]:
    return [
        {
            "canonical_taxon_id": "taxon:birds:000001",
            "accepted_scientific_name": "Columba palumbus",
            "common_names_by_language": {"fr": ["Pigeon ramier"], "en": ["Common Wood-Pigeon"]},
            "external_source_mappings": [{"source_name": "inaturalist", "external_id": "3048"}],
        },
        {
            "canonical_taxon_id": "taxon:birds:000002",
            "accepted_scientific_name": "Corvus corone",
            "common_names_by_language": {"fr": ["Corneille noire"], "en": ["Carrion Crow"]},
            "external_source_mappings": [{"source_name": "inaturalist", "external_id": "204496"}],
        },
    ]


def _phase_b_fixture() -> dict[str, object]:
    return {
        "per_target": [
            {
                "canonical_taxon_id": "taxon:birds:000001",
                "hints": [
                    {
                        "source_name": "inaturalist",
                        "external_taxon_id": "204496",
                        "accepted_scientific_name": "Corvus corone",
                        "common_name": "Carrion Crow",
                        "note": "iNat co-identification count: 8; rank: 0",
                    },
                    {
                        "source_name": "inaturalist",
                        "external_taxon_id": "777777",
                        "accepted_scientific_name": "Sturnus vulgaris",
                        "common_name": "Common Starling",
                        "note": "iNat co-identification count: 6; rank: 1",
                    },
                    {
                        "source_name": "inaturalist",
                        "external_taxon_id": "888888",
                        "accepted_scientific_name": "",
                        "common_name": "",
                        "note": "iNat co-identification count: 2; rank: 2",
                    },
                ],
            }
        ]
    }


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_mapped_canonical_candidate_does_not_need_shell(tmp_path: Path) -> None:
    prep = prepare_shell_candidates(
        phase_b_evidence=_phase_b_fixture(),
        canonical_taxa=_canonical_taxa_fixture(),
        localized_taxa=None,
        existing_referenced=None,
        manual_csv_path=tmp_path / "missing.csv",
    )
    items = prep["shell_candidates"]
    mapped = [i for i in items if i["source_taxon_id"] == "204496"][0]
    assert mapped["proposed_mapping_status"] == "mapped"


def test_unmapped_candidate_with_scientific_name_becomes_shell_candidate(tmp_path: Path) -> None:
    prep = prepare_shell_candidates(
        phase_b_evidence=_phase_b_fixture(),
        canonical_taxa=_canonical_taxa_fixture(),
        localized_taxa=None,
        existing_referenced=None,
        manual_csv_path=tmp_path / "missing.csv",
    )
    items = prep["shell_candidates"]
    unmapped = [i for i in items if i["source_taxon_id"] == "777777"][0]
    assert unmapped["proposed_mapping_status"] in {
        "auto_referenced_high_confidence",
        "auto_referenced_low_confidence",
    }


def test_missing_scientific_name_becomes_ignored(tmp_path: Path) -> None:
    prep = prepare_shell_candidates(
        phase_b_evidence=_phase_b_fixture(),
        canonical_taxa=_canonical_taxa_fixture(),
        localized_taxa=None,
        existing_referenced=None,
        manual_csv_path=tmp_path / "missing.csv",
    )
    items = prep["shell_candidates"]
    missing_name = [i for i in items if i["source_taxon_id"] == "888888"][0]
    assert missing_name["proposed_mapping_status"] in {"ignored", "ambiguous"}


def test_existing_referenced_taxon_is_reused(tmp_path: Path) -> None:
    existing = {
        "referenced_taxa": [
            {
                "referenced_taxon_id": "reftaxon:inaturalist:777777",
                "source_taxon_id": "777777",
                "mapping_status": "auto_referenced_high_confidence",
            }
        ]
    }
    prep = prepare_shell_candidates(
        phase_b_evidence=_phase_b_fixture(),
        canonical_taxa=_canonical_taxa_fixture(),
        localized_taxa=None,
        existing_referenced=existing,
        manual_csv_path=tmp_path / "missing.csv",
    )
    items = prep["shell_candidates"]
    reused = [i for i in items if i["source_taxon_id"] == "777777"][0]
    assert reused["existing_referenced_taxon_id"] == "reftaxon:inaturalist:777777"


def test_dry_run_does_not_mutate(tmp_path: Path) -> None:
    phase_b = tmp_path / "phase_b.json"
    canonical = tmp_path / "canonical.json"
    _write_json(phase_b, _phase_b_fixture())
    _write_json(canonical, {"canonical_taxa": _canonical_taxa_fixture()})

    result = run_audit(
        snapshot_id="test",
        phase_b_path=phase_b,
        canonical_path=canonical,
        localized_path=None,
        candidates_path=None,
        existing_referenced_path=None,
        manual_csv_path=tmp_path / "missing.csv",
        apply=False,
    )
    evidence = result["evidence"]
    assert evidence["shell_creation_mode"] == "dry_run"
    assert evidence["apply_result"]["storage_mutated"] is False


def test_shell_candidate_with_fr_name_can_be_distractor_fr(tmp_path: Path) -> None:
    manual_csv = tmp_path / "manual.csv"
    manual_csv.write_text(
        "scientific_name,source_taxon_id,canonical_taxon_id,referenced_taxon_id,"
        "common_name_fr,common_name_en,common_name_nl,source,reviewer,notes\n"
        "Sturnus vulgaris,777777,,,Etourneau sansonnet,Common Starling,Spreeuw,manual,,\n",
        encoding="utf-8",
    )
    prep = prepare_shell_candidates(
        phase_b_evidence=_phase_b_fixture(),
        canonical_taxa=_canonical_taxa_fixture(),
        localized_taxa=None,
        existing_referenced=None,
        manual_csv_path=manual_csv,
    )
    items = prep["shell_candidates"]
    item = [i for i in items if i["source_taxon_id"] == "777777"][0]
    assert item["common_names_i18n"]["fr"]
    if item["proposed_mapping_status"] in {"mapped", "auto_referenced_high_confidence"}:
        assert item["can_be_distractor_fr"] is True


def test_evidence_json_written(tmp_path: Path) -> None:
    phase_b = tmp_path / "phase_b.json"
    canonical = tmp_path / "canonical.json"
    output_json = tmp_path / "audit.json"
    candidates_json = tmp_path / "candidates.json"
    _write_json(phase_b, _phase_b_fixture())
    _write_json(canonical, {"canonical_taxa": _canonical_taxa_fixture()})

    result = run_audit(
        snapshot_id="test",
        phase_b_path=phase_b,
        canonical_path=canonical,
        localized_path=None,
        candidates_path=None,
        existing_referenced_path=None,
        manual_csv_path=tmp_path / "missing.csv",
        apply=False,
    )
    output_json.write_text(json.dumps(result["evidence"], indent=2), encoding="utf-8")
    candidates_json.write_text(json.dumps(result["shell_candidates"], indent=2), encoding="utf-8")

    assert output_json.exists()
    assert candidates_json.exists()


def test_markdown_written(tmp_path: Path) -> None:
    evidence = {
        "run_date": "2026-05-05T00:00:00+00:00",
        "decision": "READY_TO_CREATE_REFERENCED_TAXON_SHELLS",
        "decision_note": "ok",
        "shell_creation_mode": "dry_run",
        "safe_apply_pathway_available": False,
        "required_future_storage_changes": ["item"],
        "metrics": {
            "total_candidate_taxa_from_inat_similar_species": 1,
            "candidates_mapped_to_canonical_taxa": 0,
            "candidates_already_existing_as_referenced_taxa": 0,
            "candidates_needing_new_referenced_shell": 1,
            "candidates_ambiguous": 0,
            "candidates_ignored": 0,
            "candidates_missing_scientific_name": 0,
            "candidates_with_fr_name": 1,
            "candidates_without_fr_name": 0,
        },
    }
    output = tmp_path / "report.md"
    write_markdown_report(evidence, output)
    content = output.read_text(encoding="utf-8")
    assert "owner: database" in content
    assert "Referenced Taxon Shell Needs" in content


def test_decision_label_is_explicit() -> None:
    decision, _ = _determine_decision(
        {
            "total_candidate_taxa_from_inat_similar_species": 2,
            "candidates_needing_new_referenced_shell": 2,
            "candidates_ambiguous": 0,
        },
        apply_requested=False,
        safe_pathway=False,
    )
    assert decision in {
        "READY_FOR_DISTRACTOR_READINESS_RERUN",
        "READY_TO_CREATE_REFERENCED_TAXON_SHELLS",
        "NEEDS_REFERENCED_TAXON_STORAGE_WORK",
        "NO_REFERENCED_SHELLS_NEEDED",
        "BLOCKED_BY_AMBIGUOUS_TAXA",
    }
