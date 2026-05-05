from __future__ import annotations

import json
from pathlib import Path

from scripts.select_priority_taxon_name_patches_for_distractors import (
    build_candidates_payload_with_patched_names,
    build_csv_rows,
    compare_sprint12_vs_sprint13,
    run,
    select_priority_candidates,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _schema_payload() -> dict:
    return json.loads(
        Path("schemas/taxon_localized_name_patch_v1.schema.json").read_text(encoding="utf-8")
    )


def _canonical_payload() -> dict:
    return {
        "canonical_taxa": [
            {
                "canonical_taxon_id": "taxon:birds:000010",
                "accepted_scientific_name": "Cand FR One",
                "common_names_by_language": {"fr": ["Nom FR 1"], "en": ["EN 1"]},
            },
            {
                "canonical_taxon_id": "taxon:birds:000011",
                "accepted_scientific_name": "Cand FR Two",
                "common_names_by_language": {"fr": ["Nom FR 2"], "en": ["EN 2"]},
            },
            {
                "canonical_taxon_id": "taxon:birds:000012",
                "accepted_scientific_name": "Cand FR Three",
                "common_names_by_language": {"fr": ["Nom FR 3"], "en": ["EN 3"]},
            },
            {
                "canonical_taxon_id": "taxon:birds:000013",
                "accepted_scientific_name": "Cand FR Four",
                "common_names_by_language": {"fr": ["Nom FR 4"], "en": ["EN 4"]},
            },
            {
                "canonical_taxon_id": "taxon:birds:000001",
                "accepted_scientific_name": "Target A",
                "common_names_by_language": {"en": ["Target A EN"]},
            },
            {
                "canonical_taxon_id": "taxon:birds:000002",
                "accepted_scientific_name": "Target B",
                "common_names_by_language": {"en": ["Target B EN"]},
            },
        ]
    }


def _referenced_candidates_payload() -> dict:
    return {
        "items": [
            {
                "source_taxon_id": "10001",
                "scientific_name": "Missing Shared",
                "common_names_i18n": {"en": ["Shared EN"]},
            },
            {
                "source_taxon_id": "10002",
                "scientific_name": "Missing Solo",
                "common_names_i18n": {"en": ["Solo EN"]},
            },
        ]
    }


def _shell_plan_payload() -> dict:
    return {
        "apply_records": [
            {
                "scientific_name": "Missing Shared",
                "source_taxon_id": "10001",
                "proposed_referenced_taxon_id": "reftaxon:inaturalist:10001",
                "common_names_i18n": {"en": ["Shared EN"]},
            },
            {
                "scientific_name": "Missing Solo",
                "source_taxon_id": "10002",
                "proposed_referenced_taxon_id": "reftaxon:inaturalist:10002",
                "common_names_i18n": {"en": ["Solo EN"]},
            },
        ]
    }


def _relationship(
    *,
    rid: str,
    target_id: str,
    target_name: str,
    ref_type: str,
    ref_id: str,
    sci: str,
    source_rank: int,
    has_fr: bool,
) -> dict:
    return {
        "relationship_id": rid,
        "target_canonical_taxon_id": target_id,
        "target_scientific_name": target_name,
        "candidate_taxon_ref_type": ref_type,
        "candidate_taxon_ref_id": ref_id,
        "candidate_scientific_name": sci,
        "source": "inaturalist_similar_species",
        "source_rank": source_rank,
        "confusion_types": ["visual_similarity"],
        "pedagogical_value": "high",
        "difficulty_level": "medium",
        "learner_level": "mixed",
        "status": "candidate",
        "created_at": "2026-05-05T12:00:00+00:00",
        "candidate_has_localized_name": has_fr,
        "candidate_has_french_name": has_fr,
        "can_be_used_now_fr": has_fr,
        "can_be_used_now_multilingual": False,
        "usability_blockers": [] if has_fr else ["missing_french_name"],
    }


def _candidates_s12_payload() -> dict:
    relationships = [
        _relationship(
            rid="dr:a1",
            target_id="taxon:birds:000001",
            target_name="Target A",
            ref_type="canonical_taxon",
            ref_id="taxon:birds:000010",
            sci="Cand FR One",
            source_rank=1,
            has_fr=True,
        ),
        _relationship(
            rid="dr:a2",
            target_id="taxon:birds:000001",
            target_name="Target A",
            ref_type="canonical_taxon",
            ref_id="taxon:birds:000011",
            sci="Cand FR Two",
            source_rank=2,
            has_fr=True,
        ),
        _relationship(
            rid="dr:a3",
            target_id="taxon:birds:000001",
            target_name="Target A",
            ref_type="referenced_taxon",
            ref_id="reftaxon:inaturalist:10001",
            sci="Missing Shared",
            source_rank=3,
            has_fr=False,
        ),
        _relationship(
            rid="dr:b1",
            target_id="taxon:birds:000002",
            target_name="Target B",
            ref_type="canonical_taxon",
            ref_id="taxon:birds:000012",
            sci="Cand FR Three",
            source_rank=1,
            has_fr=True,
        ),
        _relationship(
            rid="dr:b2",
            target_id="taxon:birds:000002",
            target_name="Target B",
            ref_type="canonical_taxon",
            ref_id="taxon:birds:000013",
            sci="Cand FR Four",
            source_rank=2,
            has_fr=True,
        ),
        _relationship(
            rid="dr:b3",
            target_id="taxon:birds:000002",
            target_name="Target B",
            ref_type="referenced_taxon",
            ref_id="reftaxon:inaturalist:10001",
            sci="Missing Shared",
            source_rank=3,
            has_fr=False,
        ),
        _relationship(
            rid="dr:b4",
            target_id="taxon:birds:000002",
            target_name="Target B",
            ref_type="referenced_taxon",
            ref_id="reftaxon:inaturalist:10002",
            sci="Missing Solo",
            source_rank=4,
            has_fr=False,
        ),
    ]

    return {
        "generation_version": "test",
        "run_date": "2026-05-05",
        "execution_status": "complete",
        "input_source": "/test",
        "snapshot_id": "test-snapshot",
        "decision": "READY_FOR_AI_RANKING_DESIGN",
        "generation_params": {"ready_threshold": 3},
        "summary": {
            "target_taxa_count": 2,
            "total_relationships_generated": 7,
            "by_source": {
                "inaturalist_similar_species": 7,
                "emergency_diversity_fallback": 0,
            },
            "targets_with_3_plus_candidates": 2,
            "targets_with_3_plus_usable_fr_candidates": 0,
            "targets_with_only_taxonomic_candidates": 0,
            "targets_with_insufficient_candidates": 0,
            "targets_with_no_candidates": 0,
            "unresolved_candidate_count": 0,
            "referenced_taxon_shell_needed_count": 0,
            "referenced_taxon_shell_candidate_count": 2,
            "candidates_missing_french_name": 2,
            "no_emergency_diversity_fallback_generated": True,
        },
        "gaps": {
            "unresolved_candidates": [],
            "referenced_taxon_shells_needed": [],
            "candidates_missing_french_name": ["Missing Shared", "Missing Solo"],
            "targets_not_ready": [],
        },
        "per_target_summaries": [
            {
                "target_canonical_taxon_id": "taxon:birds:000001",
                "scientific_name": "Target A",
                "inat_candidates": 3,
                "same_genus_candidates": 0,
                "same_family_candidates": 0,
                "same_order_candidates": 0,
                "total_candidates": 3,
                "usable_fr_candidates": 2,
                "usable_multilingual_candidates": 0,
                "readiness": "ready",
            },
            {
                "target_canonical_taxon_id": "taxon:birds:000002",
                "scientific_name": "Target B",
                "inat_candidates": 4,
                "same_genus_candidates": 0,
                "same_family_candidates": 0,
                "same_order_candidates": 0,
                "total_candidates": 4,
                "usable_fr_candidates": 2,
                "usable_multilingual_candidates": 0,
                "readiness": "ready",
            },
        ],
        "relationships": relationships,
    }


def _readiness_s12_payload() -> dict:
    return {
        "decision": "INSUFFICIENT_DISTRACTOR_COVERAGE",
        "summary": {
            "targets_ready": 0,
            "targets_blocked": 2,
        },
    }


def test_priority_selection_ranks_high_impact_first() -> None:
    ranked, selected, metrics = select_priority_candidates(
        candidates_s12=_candidates_s12_payload(),
        shell_plan=_shell_plan_payload(),
        canonical_payload=_canonical_payload(),
        min_targets_ready=0,
        missing_ratio_target=0.0,
    )

    assert ranked[0]["scientific_name"] == "Missing Shared"
    assert ranked[0]["targets_unblocked_if_named"] == 2
    assert len(selected) >= 1
    assert metrics["missing_fr_relationships_before"] == 3


def test_patch_template_rows_are_generated_with_blank_fr_nl() -> None:
    ranked, selected, _ = select_priority_candidates(
        candidates_s12=_candidates_s12_payload(),
        shell_plan=_shell_plan_payload(),
        canonical_payload=_canonical_payload(),
        min_targets_ready=0,
        missing_ratio_target=0.0,
    )

    rows = build_csv_rows(selected[:1])
    assert rows
    assert rows[0]["scientific_name"] == ranked[0]["scientific_name"]
    assert rows[0]["common_name_fr"] == ""
    assert rows[0]["common_name_nl"] == ""


def test_applying_patches_improves_fr_usability() -> None:
    candidates_s12 = _candidates_s12_payload()
    canonical_taxa = [
        {
            "canonical_taxon_id": "taxon:birds:000010",
            "scientific_name": "Cand FR One",
            "common_names_i18n": {"fr": ["Nom FR 1"], "en": ["EN 1"]},
        },
        {
            "canonical_taxon_id": "taxon:birds:000011",
            "scientific_name": "Cand FR Two",
            "common_names_i18n": {"fr": ["Nom FR 2"], "en": ["EN 2"]},
        },
        {
            "canonical_taxon_id": "taxon:birds:000012",
            "scientific_name": "Cand FR Three",
            "common_names_i18n": {"fr": ["Nom FR 3"], "en": ["EN 3"]},
        },
        {
            "canonical_taxon_id": "taxon:birds:000013",
            "scientific_name": "Cand FR Four",
            "common_names_i18n": {"fr": ["Nom FR 4"], "en": ["EN 4"]},
        },
    ]
    referenced_taxa = [
        {
            "referenced_taxon_id": "reftaxon:inaturalist:10001",
            "source_taxon_id": "10001",
            "scientific_name": "Missing Shared",
            "common_names_i18n": {"fr": ["Missing Shared"], "en": ["Shared EN"]},
        },
        {
            "referenced_taxon_id": "reftaxon:inaturalist:10002",
            "source_taxon_id": "10002",
            "scientific_name": "Missing Solo",
            "common_names_i18n": {"en": ["Solo EN"]},
        },
    ]

    patched = build_candidates_payload_with_patched_names(
        candidates_s12=candidates_s12,
        canonical_taxa=canonical_taxa,
        referenced_taxa=referenced_taxa,
    )

    assert patched["summary"]["targets_with_3_plus_usable_fr_candidates"] == 2
    assert patched["summary"]["candidates_missing_french_name"] == 1


def test_readiness_comparison_detects_improvement_and_no_emergency_fallback() -> None:
    candidates_s12 = _candidates_s12_payload()
    candidates_s13 = dict(candidates_s12)
    candidates_s13["summary"] = dict(candidates_s12["summary"])
    candidates_s13["summary"]["targets_with_3_plus_usable_fr_candidates"] = 2
    candidates_s13["summary"]["candidates_missing_french_name"] = 1
    candidates_s13["summary"]["by_source"] = {
        "inaturalist_similar_species": 7,
        "emergency_diversity_fallback": 0,
    }

    rels_s13 = []
    for rel in candidates_s12["relationships"]:
        rel_new = dict(rel)
        if rel_new["candidate_scientific_name"] == "Missing Shared":
            rel_new["candidate_has_french_name"] = True
            rel_new["can_be_used_now_fr"] = True
            rel_new["usability_blockers"] = []
        rels_s13.append(rel_new)
    candidates_s13["relationships"] = rels_s13

    readiness_s12 = _readiness_s12_payload()
    readiness_s13 = {
        "summary": {
            "targets_ready": 2,
            "targets_blocked": 0,
        }
    }

    comparison = compare_sprint12_vs_sprint13(
        candidates_s12=candidates_s12,
        candidates_s13=candidates_s13,
        readiness_s12=readiness_s12,
        readiness_s13=readiness_s13,
    )

    assert comparison["metrics"]["targets_ready"]["delta"] > 0
    assert comparison["metrics"]["emergency_fallback_count"]["sprint13"] == 0
    assert comparison["decision"] in {
        "READY_FOR_FIRST_CORPUS_DISTRACTOR_GATE",
        "READY_FOR_AI_RANKING_AND_PROPOSALS",
        "NEEDS_MORE_NAME_COMPLETION",
        "NEEDS_REFERENCED_TAXON_REVIEW",
        "STILL_BLOCKED",
    }


def test_run_writes_json_markdown_and_csv_outputs(tmp_path: Path) -> None:
    candidates_s12_path = tmp_path / "candidates_s12.json"
    readiness_s12_path = tmp_path / "readiness_s12.json"
    shell_plan_path = tmp_path / "shell_plan_s13.json"
    localized_audit_path = tmp_path / "localized_audit_s13.json"
    projected_relationships_path = tmp_path / "projected_relationships_s13.json"
    patch_schema_path = tmp_path / "schema.json"
    canonical_path = tmp_path / "canonical.json"
    referenced_candidates_path = tmp_path / "referenced_candidates.json"
    referenced_snapshot_path = tmp_path / "referenced_snapshot.json"

    patch_csv = tmp_path / "manual" / "patches_s13.csv"
    apply_json = tmp_path / "audits" / "apply.json"
    apply_md = tmp_path / "audits" / "apply.md"
    readiness_s13 = tmp_path / "audits" / "readiness_s13.json"
    compare_json = tmp_path / "audits" / "compare.json"
    compare_md = tmp_path / "audits" / "compare.md"
    output_canonical = tmp_path / "out" / "canonical_patched.json"
    output_referenced = tmp_path / "out" / "referenced_patched.json"

    _write_json(candidates_s12_path, _candidates_s12_payload())
    _write_json(readiness_s12_path, _readiness_s12_payload())
    _write_json(shell_plan_path, _shell_plan_payload())
    _write_json(localized_audit_path, {"decision": "BLOCKED_BY_NAME_SOURCE_GAPS"})
    _write_json(
        projected_relationships_path,
        {"decision": "READY_FOR_REFERENCED_TAXON_SHELL_APPLY_PATH"},
    )
    _write_json(patch_schema_path, _schema_payload())
    _write_json(canonical_path, _canonical_payload())
    _write_json(referenced_candidates_path, _referenced_candidates_payload())
    _write_json(referenced_snapshot_path, {"referenced_taxa": []})

    result = run(
        candidates_s12_path=candidates_s12_path,
        readiness_s12_path=readiness_s12_path,
        shell_plan_s13_path=shell_plan_path,
        localized_audit_s13_path=localized_audit_path,
        projected_relationships_s13_path=projected_relationships_path,
        patch_csv_path=patch_csv,
        apply_evidence_json_path=apply_json,
        apply_evidence_md_path=apply_md,
        readiness_s13_path=readiness_s13,
        comparison_json_path=compare_json,
        comparison_md_path=compare_md,
        patch_schema_path=patch_schema_path,
        canonical_path=canonical_path,
        referenced_candidates_path=referenced_candidates_path,
        referenced_snapshot_path=referenced_snapshot_path,
        output_canonical=output_canonical,
        output_referenced=output_referenced,
        apply=False,
    )

    assert patch_csv.exists()
    assert apply_json.exists()
    assert apply_md.exists()
    assert readiness_s13.exists()
    assert compare_json.exists()
    assert compare_md.exists()

    compare_payload = json.loads(compare_json.read_text(encoding="utf-8"))
    assert compare_payload["metrics"]["emergency_fallback_count"]["sprint13"] == 0
    assert result["selected_count"] > 0
