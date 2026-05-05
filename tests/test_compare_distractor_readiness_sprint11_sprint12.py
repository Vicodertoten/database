from __future__ import annotations

import json
from pathlib import Path

from scripts.compare_distractor_readiness_sprint11_sprint12 import compare, write_markdown


def _candidates_payload(
    *,
    inat: int,
    total: int,
    fr_ready_targets: int,
    targets_3_plus: int,
    missing_fr: int,
    shells_needed: int,
    no_candidates: int,
    taxonomic_only: int,
    same_order_dep_targets: int,
    emergency_fallback: int = 0,
) -> dict:
    per_target = []
    for i in range(max(1, same_order_dep_targets)):
        per_target.append(
            {
                "target_canonical_taxon_id": f"taxon:birds:{i+1:06d}",
                "scientific_name": f"Species {i+1}",
                "same_order_candidates": 1 if i < same_order_dep_targets else 0,
            }
        )

    return {
        "summary": {
            "target_taxa_count": 50,
            "total_relationships_generated": total,
            "by_source": {
                "inaturalist_similar_species": inat,
                "taxonomic_neighbor_same_genus": 30,
                "taxonomic_neighbor_same_family": 40,
                "taxonomic_neighbor_same_order": 20,
                "emergency_diversity_fallback": emergency_fallback,
            },
            "targets_with_3_plus_candidates": targets_3_plus,
            "targets_with_3_plus_usable_fr_candidates": fr_ready_targets,
            "targets_with_only_taxonomic_candidates": taxonomic_only,
            "targets_with_no_candidates": no_candidates,
            "candidates_missing_french_name": missing_fr,
            "referenced_taxon_shell_needed_count": shells_needed,
        },
        "per_target_summaries": per_target,
    }


def _readiness_payload(*, ready: int, blocked: int) -> dict:
    return {
        "summary": {
            "targets_ready": ready,
            "targets_blocked": blocked,
        }
    }


def test_comparison_detects_improved_inat_count() -> None:
    c11 = _candidates_payload(
        inat=0,
        total=200,
        fr_ready_targets=0,
        targets_3_plus=10,
        missing_fr=40,
        shells_needed=20,
        no_candidates=5,
        taxonomic_only=30,
        same_order_dep_targets=8,
    )
    c12 = _candidates_payload(
        inat=120,
        total=350,
        fr_ready_targets=20,
        targets_3_plus=35,
        missing_fr=8,
        shells_needed=2,
        no_candidates=1,
        taxonomic_only=8,
        same_order_dep_targets=3,
    )
    r11 = _readiness_payload(ready=5, blocked=45)
    r12 = _readiness_payload(ready=20, blocked=30)

    result = compare(
        candidates_s11=c11,
        candidates_s12=c12,
        readiness_s11=r11,
        readiness_s12=r12,
    )
    assert result["metrics"]["inat_similar_count"]["delta"] > 0


def test_comparison_detects_improved_fr_usability() -> None:
    c11 = _candidates_payload(
        inat=5,
        total=210,
        fr_ready_targets=1,
        targets_3_plus=12,
        missing_fr=43,
        shells_needed=10,
        no_candidates=4,
        taxonomic_only=25,
        same_order_dep_targets=8,
    )
    c12 = _candidates_payload(
        inat=100,
        total=340,
        fr_ready_targets=18,
        targets_3_plus=33,
        missing_fr=5,
        shells_needed=3,
        no_candidates=1,
        taxonomic_only=10,
        same_order_dep_targets=2,
    )
    result = compare(
        candidates_s11=c11,
        candidates_s12=c12,
        readiness_s11=_readiness_payload(ready=2, blocked=48),
        readiness_s12=_readiness_payload(ready=18, blocked=32),
    )
    assert result["metrics"]["targets_with_3_plus_fr_usable"]["delta"] > 0


def test_comparison_detects_remaining_blockers() -> None:
    c11 = _candidates_payload(
        inat=0,
        total=240,
        fr_ready_targets=0,
        targets_3_plus=15,
        missing_fr=50,
        shells_needed=30,
        no_candidates=4,
        taxonomic_only=35,
        same_order_dep_targets=9,
    )
    c12 = _candidates_payload(
        inat=20,
        total=260,
        fr_ready_targets=3,
        targets_3_plus=17,
        missing_fr=45,
        shells_needed=18,
        no_candidates=3,
        taxonomic_only=28,
        same_order_dep_targets=8,
    )
    result = compare(
        candidates_s11=c11,
        candidates_s12=c12,
        readiness_s11=_readiness_payload(ready=1, blocked=49),
        readiness_s12=_readiness_payload(ready=3, blocked=47),
    )
    assert result["decision"] in {
        "NEEDS_REFERENCED_TAXON_REVIEW",
        "NEEDS_MORE_TAXON_NAME_ENRICHMENT",
        "NEEDS_MORE_INAT_ENRICHMENT",
        "STILL_BLOCKED",
    }


def test_decision_ready_for_first_corpus_gate_when_enough_targets_ready() -> None:
    c11 = _candidates_payload(
        inat=20,
        total=250,
        fr_ready_targets=8,
        targets_3_plus=20,
        missing_fr=30,
        shells_needed=5,
        no_candidates=2,
        taxonomic_only=14,
        same_order_dep_targets=4,
    )
    c12 = _candidates_payload(
        inat=220,
        total=420,
        fr_ready_targets=32,
        targets_3_plus=45,
        missing_fr=20,
        shells_needed=0,
        no_candidates=0,
        taxonomic_only=5,
        same_order_dep_targets=1,
    )
    result = compare(
        candidates_s11=c11,
        candidates_s12=c12,
        readiness_s11=_readiness_payload(ready=8, blocked=42),
        readiness_s12=_readiness_payload(ready=34, blocked=16),
    )
    assert result["decision"] == "READY_FOR_FIRST_CORPUS_DISTRACTOR_GATE"


def test_decision_still_blocked_when_no_improvement() -> None:
    c11 = _candidates_payload(
        inat=0,
        total=200,
        fr_ready_targets=0,
        targets_3_plus=10,
        missing_fr=45,
        shells_needed=0,
        no_candidates=5,
        taxonomic_only=30,
        same_order_dep_targets=8,
    )
    c12 = _candidates_payload(
        inat=0,
        total=200,
        fr_ready_targets=0,
        targets_3_plus=10,
        missing_fr=45,
        shells_needed=0,
        no_candidates=5,
        taxonomic_only=30,
        same_order_dep_targets=8,
    )
    result = compare(
        candidates_s11=c11,
        candidates_s12=c12,
        readiness_s11=_readiness_payload(ready=0, blocked=50),
        readiness_s12=_readiness_payload(ready=0, blocked=50),
    )
    assert result["decision"] in {"STILL_BLOCKED", "NEEDS_MORE_INAT_ENRICHMENT"}


def test_json_written(tmp_path: Path) -> None:
    result = compare(
        candidates_s11=_candidates_payload(
            inat=0,
            total=200,
            fr_ready_targets=0,
            targets_3_plus=10,
            missing_fr=45,
            shells_needed=10,
            no_candidates=5,
            taxonomic_only=30,
            same_order_dep_targets=8,
        ),
        candidates_s12=_candidates_payload(
            inat=80,
            total=300,
            fr_ready_targets=12,
            targets_3_plus=28,
            missing_fr=18,
            shells_needed=5,
            no_candidates=2,
            taxonomic_only=12,
            same_order_dep_targets=3,
        ),
        readiness_s11=_readiness_payload(ready=3, blocked=47),
        readiness_s12=_readiness_payload(ready=14, blocked=36),
    )
    out = tmp_path / "compare.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["execution_status"] == "complete"


def test_markdown_written(tmp_path: Path) -> None:
    result = compare(
        candidates_s11=_candidates_payload(
            inat=0,
            total=200,
            fr_ready_targets=0,
            targets_3_plus=10,
            missing_fr=45,
            shells_needed=10,
            no_candidates=5,
            taxonomic_only=30,
            same_order_dep_targets=8,
        ),
        candidates_s12=_candidates_payload(
            inat=80,
            total=300,
            fr_ready_targets=12,
            targets_3_plus=28,
            missing_fr=18,
            shells_needed=5,
            no_candidates=2,
            taxonomic_only=12,
            same_order_dep_targets=3,
        ),
        readiness_s11=_readiness_payload(ready=3, blocked=47),
        readiness_s12=_readiness_payload(ready=14, blocked=36),
    )
    out = tmp_path / "compare.md"
    write_markdown(result, out)
    content = out.read_text(encoding="utf-8")
    assert "Sprint 11 vs Sprint 12" in content
    assert "owner: database" in content
