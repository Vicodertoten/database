from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.build_distractor_readiness_v1 import _write_markdown, run_readiness

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _candidate_rel(
    target_id: str,
    target_name: str,
    candidate_name: str,
    source: str,
    ref_type: str = "canonical_taxon",
    has_fr: bool = False,
) -> dict[str, Any]:
    return {
        "relationship_id": f"dr:{target_id}-{candidate_name[:4]}",
        "target_canonical_taxon_id": target_id,
        "target_scientific_name": target_name,
        "candidate_taxon_ref_type": ref_type,
        "candidate_taxon_ref_id": None if ref_type == "unresolved_taxon" else candidate_name,
        "candidate_scientific_name": candidate_name,
        "source": source,
        "source_rank": 1,
        "confusion_types": ["visual_similarity"],
        "pedagogical_value": "medium",
        "difficulty_level": "medium",
        "learner_level": "mixed",
        "status": "needs_review" if ref_type == "unresolved_taxon" else "candidate",
        "created_at": "2026-05-05T10:00:00+00:00",
        "candidate_has_localized_name": has_fr,
        "candidate_has_french_name": has_fr,
        "can_be_used_now_fr": has_fr and ref_type != "unresolved_taxon",
        "can_be_used_now_multilingual": False,
        "usability_blockers": [] if has_fr else ["missing_french_name"],
    }


def _build_candidates_payload(
    rels: list[dict[str, Any]],
    snapshot_id: str = "test",
    include_same_order: bool = False,
) -> dict[str, Any]:
    from collections import Counter

    by_source: Counter = Counter(r["source"] for r in rels)
    targets = {r["target_canonical_taxon_id"] for r in rels}
    per_target = []
    for tid in sorted(targets):
        t_rels = [r for r in rels if r["target_canonical_taxon_id"] == tid]
        name = t_rels[0]["target_scientific_name"]
        inat = sum(1 for r in t_rels if r["source"] == "inaturalist_similar_species")
        genus = sum(1 for r in t_rels if r["source"] == "taxonomic_neighbor_same_genus")
        family = sum(1 for r in t_rels if r["source"] == "taxonomic_neighbor_same_family")
        order = sum(1 for r in t_rels if r["source"] == "taxonomic_neighbor_same_order")
        usable_fr = sum(1 for r in t_rels if r.get("can_be_used_now_fr"))
        per_target.append({
            "target_canonical_taxon_id": tid,
            "scientific_name": name,
            "inat_candidates": inat,
            "same_genus_candidates": genus,
            "same_family_candidates": family,
            "same_order_candidates": order,
            "total_candidates": len(t_rels),
            "usable_fr_candidates": usable_fr,
            "usable_multilingual_candidates": 0,
            "readiness": "ready" if len(t_rels) >= 3 else "insufficient_distractors",
        })

    missing_fr = list({
        r["candidate_scientific_name"]
        for r in rels
        if not r.get("candidate_has_french_name", False)
    })
    unresolved = list({
        r["candidate_scientific_name"]
        for r in rels
        if r.get("candidate_taxon_ref_type") == "unresolved_taxon"
    })
    targets_not_ready = [
        p["scientific_name"] for p in per_target if p["readiness"] != "ready"
    ]

    return {
        "generation_version": "test",
        "run_date": "2026-05-05",
        "execution_status": "complete",
        "input_source": "/test",
        "snapshot_id": snapshot_id,
        "decision": "NEEDS_TAXON_ENRICHMENT_BEFORE_DISTRACTORS",
        "generation_params": {
            "max_taxonomic_neighbors_per_target": 10,
            "include_same_order": include_same_order,
            "ready_threshold": 3,
        },
        "summary": {
            "target_taxa_count": len(targets),
            "total_relationships_generated": len(rels),
            "by_source": dict(by_source),
            "targets_with_3_plus_candidates": sum(
                1 for p in per_target if p["total_candidates"] >= 3
            ),
            "targets_with_3_plus_usable_fr_candidates": sum(
                1 for p in per_target if p["usable_fr_candidates"] >= 3
            ),
            "targets_with_only_taxonomic_candidates": sum(
                1 for p in per_target if p["inat_candidates"] == 0 and p["total_candidates"] > 0
            ),
            "targets_with_insufficient_candidates": sum(
                1 for p in per_target if 0 < p["total_candidates"] < 3
            ),
            "targets_with_no_candidates": sum(1 for p in per_target if p["total_candidates"] == 0),
            "unresolved_candidate_count": len(unresolved),
            "referenced_taxon_shell_needed_count": len(unresolved),
            "candidates_missing_french_name": len(missing_fr),
        },
        "gaps": {
            "unresolved_candidates": unresolved,
            "referenced_taxon_shells_needed": unresolved,
            "candidates_missing_french_name": missing_fr,
            "targets_not_ready": targets_not_ready,
        },
        "per_target_summaries": per_target,
        "relationships": rels,
    }


def _empty_audit(snapshot_id: str = "test") -> dict[str, Any]:
    return {
        "audit_version": "test",
        "run_date": "2026-05-05",
        "execution_status": "complete",
        "snapshot_id": snapshot_id,
        "decision": "NEEDS_TAXON_ENRICHMENT_BEFORE_DISTRACTORS",
        "per_target_summaries": [],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_target_with_3_fr_candidates_and_strong_source_is_ready() -> None:
    tid = "taxon:birds:000001"
    name = "Accipiter nisus"
    rels = [
        _candidate_rel(tid, name, f"Species {i}", "inaturalist_similar_species", has_fr=True)
        for i in range(3)
    ]
    candidates = _build_candidates_payload(rels)
    result = run_readiness(audit=_empty_audit(), candidates=candidates)
    pt = {t["target_canonical_taxon_id"]: t for t in result["per_target_readiness"]}
    assert pt[tid]["readiness_status"] == "ready_for_first_corpus_distractor_gate"
    assert result["summary"]["targets_ready"] == 1


def test_target_with_only_same_order_is_not_fully_ready() -> None:
    tid = "taxon:birds:000002"
    name = "Buteo buteo"
    rels = [
        _candidate_rel(tid, name, f"OrderSp {i}", "taxonomic_neighbor_same_order", has_fr=False)
        for i in range(4)
    ]
    candidates = _build_candidates_payload(rels, include_same_order=True)
    result = run_readiness(audit=_empty_audit(), candidates=candidates)
    pt = {t["target_canonical_taxon_id"]: t for t in result["per_target_readiness"]}
    status = pt[tid]["readiness_status"]
    # same_order is not in STRONG_SOURCES, so it's either
    # missing_localized_names or ready_with_taxonomic_fallback
    assert status in {"ready_with_taxonomic_fallback", "missing_localized_names"}
    assert pt[tid]["readiness_status"] != "ready_for_first_corpus_distractor_gate"


def test_target_with_unresolved_only_candidates_needs_review() -> None:
    tid = "taxon:birds:000003"
    name = "Falco tinnunculus"
    rels = [
        _candidate_rel(
            tid, name, f"Unknown sp {i}",
            "inaturalist_similar_species",
            ref_type="unresolved_taxon",
            has_fr=False,
        )
        for i in range(3)
    ]
    candidates = _build_candidates_payload(rels)
    result = run_readiness(audit=_empty_audit(), candidates=candidates)
    pt = {t["target_canonical_taxon_id"]: t for t in result["per_target_readiness"]}
    assert pt[tid]["readiness_status"] == "needs_review"
    assert pt[tid]["unresolved_candidate_count"] == 3


def test_target_with_candidates_but_missing_french_names() -> None:
    tid = "taxon:birds:000004"
    name = "Columba palumbus"
    rels = [
        _candidate_rel(tid, name, f"NamesLess {i}", "inaturalist_similar_species", has_fr=False)
        for i in range(3)
    ]
    candidates = _build_candidates_payload(rels)
    result = run_readiness(audit=_empty_audit(), candidates=candidates)
    pt = {t["target_canonical_taxon_id"]: t for t in result["per_target_readiness"]}
    assert pt[tid]["readiness_status"] == "missing_localized_names"
    assert pt[tid]["missing_french_name_count"] == 3


def test_target_with_no_candidates_is_no_candidates() -> None:
    # Build a candidates payload with one target but zero relationships
    candidates = _build_candidates_payload([])
    # Force one empty per_target entry
    candidates["per_target_summaries"] = [{
        "target_canonical_taxon_id": "taxon:birds:000005",
        "scientific_name": "Larus fuscus",
        "inat_candidates": 0,
        "same_genus_candidates": 0,
        "same_family_candidates": 0,
        "same_order_candidates": 0,
        "total_candidates": 0,
        "usable_fr_candidates": 0,
        "usable_multilingual_candidates": 0,
        "readiness": "no_candidates",
    }]
    candidates["summary"]["target_taxa_count"] = 1
    result = run_readiness(audit=_empty_audit(), candidates=candidates)
    pt = {t["target_canonical_taxon_id"]: t for t in result["per_target_readiness"]}
    assert pt["taxon:birds:000005"]["readiness_status"] == "no_candidates"
    assert result["summary"]["targets_no_candidates"] == 1


def test_writes_json(tmp_path: Path) -> None:
    tid = "taxon:birds:000006"
    rels = [
        _candidate_rel(tid, "Accipiter brevipes", f"Sp {i}", "taxonomic_neighbor_same_genus")
        for i in range(2)
    ]
    candidates = _build_candidates_payload(rels)
    result = run_readiness(audit=_empty_audit(), candidates=candidates)
    out = tmp_path / "readiness.json"
    out.write_text(json.dumps(result, indent=2))
    loaded = json.loads(out.read_text())
    assert loaded["execution_status"] == "complete"
    assert "per_target_readiness" in loaded
    assert "decision" in loaded


def test_writes_markdown(tmp_path: Path) -> None:
    tid = "taxon:birds:000007"
    rels = [
        _candidate_rel(tid, "Circus aeruginosus", f"Sp {i}", "taxonomic_neighbor_same_family")
        for i in range(3)
    ]
    candidates = _build_candidates_payload(rels)
    result = run_readiness(audit=_empty_audit(), candidates=candidates)
    out_md = tmp_path / "readiness.md"
    _write_markdown(result, out_md)
    content = out_md.read_text()
    assert "Distractor Readiness V1" in content
    assert "---" in content
    assert result.get("decision", "") in content


def test_strongest_source_priority() -> None:
    """iNat candidates rank above taxonomic neighbors."""
    from collections import Counter

    from scripts.build_distractor_readiness_v1 import _strongest_source

    inat = "inaturalist_similar_species"
    genus = "taxonomic_neighbor_same_genus"
    order = "taxonomic_neighbor_same_order"
    assert _strongest_source(Counter([inat, order])) == inat
    assert _strongest_source(Counter([genus, order])) == genus
    assert _strongest_source(Counter([order])) == order
    assert _strongest_source(Counter()) == "none"
