from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.generate_distractor_relationship_candidates_v1 import (
    _write_markdown,
    run_generation,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_snapshot_dir(tmp_path: Path, taxa: list[dict[str, Any]]) -> Path:
    snap = tmp_path / "test-snapshot"
    taxa_dir = snap / "taxa"
    taxa_dir.mkdir(parents=True)
    (taxa_dir / "taxon_birds_000001.json").write_text(json.dumps({"results": taxa}))
    return snap


def _taxon(
    *,
    name: str,
    taxon_id: int,
    genus_id: int = 100,
    family_id: int = 200,
    order_id: int = 300,
    similar_taxa: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "id": taxon_id,
        "name": name,
        "rank": "species",
        "ancestors": [
            {"rank": "genus", "id": genus_id, "name": "Testgenus"},
            {"rank": "family", "id": family_id, "name": "Testfamily"},
            {"rank": "order", "id": order_id, "name": "Testorder"},
        ],
        "similar_taxa": similar_taxa or [],
    }


def _canonical(name: str, canonical_id: str, fr_name: str | None = None) -> dict[str, Any]:
    cbn: dict[str, list[str]] = {"en": [name.split()[-1]]}
    if fr_name:
        cbn["fr"] = [fr_name]
    return {
        "accepted_scientific_name": name,
        "canonical_taxon_id": canonical_id,
        "common_names_by_language": cbn,
    }


# Shared taxa for most tests
TAXON_A = _taxon(name="Accipiter nisus", taxon_id=1001, genus_id=10, family_id=20, order_id=30)
TAXON_B = _taxon(name="Accipiter gentilis", taxon_id=1002, genus_id=10, family_id=20, order_id=30)
TAXON_C = _taxon(name="Buteo buteo", taxon_id=1003, genus_id=11, family_id=20, order_id=30)
TAXON_D = _taxon(name="Falco tinnunculus", taxon_id=1004, genus_id=12, family_id=21, order_id=30)

CANONICAL_A = _canonical("Accipiter nisus", "taxon:birds:000001")
CANONICAL_B = _canonical("Accipiter gentilis", "taxon:birds:000002")
CANONICAL_C = _canonical("Buteo buteo", "taxon:birds:000003")
CANONICAL_D = _canonical("Falco tinnunculus", "taxon:birds:000004")

CANONICAL_BY_NAME = {
    "Accipiter nisus": CANONICAL_A,
    "Accipiter gentilis": CANONICAL_B,
    "Buteo buteo": CANONICAL_C,
    "Falco tinnunculus": CANONICAL_D,
}


def _run(
    tmp_path: Path,
    taxa: list[dict[str, Any]],
    *,
    canonical_by_name: dict[str, Any] | None = None,
    referenced_by_name: dict[str, Any] | None = None,
    normalized_by_name: dict[str, Any] | None = None,
    include_same_order: bool = False,
    max_neighbors: int = 10,
) -> dict[str, Any]:
    snap = _make_snapshot_dir(tmp_path, taxa)
    return run_generation(
        snapshot_dir=snap,
        canonical_by_name=canonical_by_name or {},
        referenced_by_name=referenced_by_name or {},
        normalized_by_name=normalized_by_name or {},
        snapshot_id="test",
        max_neighbors=max_neighbors,
        include_same_order=include_same_order,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_inat_hint_creates_inaturalist_similar_species_relationship(tmp_path: Path) -> None:
    taxon_with_hint = _taxon(
        name="Accipiter nisus",
        taxon_id=1001,
        genus_id=10,
        family_id=20,
        order_id=30,
        similar_taxa=[{"name": "Accipiter gentilis", "id": 5206}],
    )
    result = _run(tmp_path, [taxon_with_hint], canonical_by_name=CANONICAL_BY_NAME)
    assert result["execution_status"] == "complete"
    rels = result["relationships"]
    inat_rels = [r for r in rels if r["source"] == "inaturalist_similar_species"]
    assert len(inat_rels) == 1
    assert inat_rels[0]["candidate_scientific_name"] == "Accipiter gentilis"
    assert "visual_similarity" in inat_rels[0]["confusion_types"]
    assert inat_rels[0]["pedagogical_value"] == "high"


def test_same_genus_creates_taxonomic_neighbor_same_genus(tmp_path: Path) -> None:
    # A and B share genus 10
    result = _run(tmp_path, [TAXON_A, TAXON_B], canonical_by_name=CANONICAL_BY_NAME)
    rels = result["relationships"]
    genus_rels = [r for r in rels if r["source"] == "taxonomic_neighbor_same_genus"]
    assert len(genus_rels) == 2  # A→B and B→A
    assert all("same_genus" in r["confusion_types"] for r in genus_rels)
    assert all(r["pedagogical_value"] == "medium" for r in genus_rels)


def test_same_family_fallback_works(tmp_path: Path) -> None:
    # C has genus 11 (unique), family 20 (shared with A and B)
    result = _run(tmp_path, [TAXON_A, TAXON_B, TAXON_C], canonical_by_name=CANONICAL_BY_NAME)
    rels = result["relationships"]
    # C should have same_family rels pointing to A and B (different genus, same family)
    c_family = [
        r
        for r in rels
        if r["target_scientific_name"] == "Buteo buteo"
        and r["source"] == "taxonomic_neighbor_same_family"
    ]
    assert len(c_family) == 2
    cnames = {r["candidate_scientific_name"] for r in c_family}
    assert "Accipiter nisus" in cnames
    assert "Accipiter gentilis" in cnames
    assert all("same_family" in r["confusion_types"] for r in c_family)


def test_same_order_not_used_when_stronger_candidates_sufficient(tmp_path: Path) -> None:
    # A has 1 genus neighbor (B) + 1 family neighbor (C) = 2 strong; not >=3
    # Even with include_same_order=False, order rels should not appear
    result = _run(
        tmp_path,
        [TAXON_A, TAXON_B, TAXON_C],
        canonical_by_name=CANONICAL_BY_NAME,
        include_same_order=False,
    )
    rels = result["relationships"]
    order_rels = [r for r in rels if r["source"] == "taxonomic_neighbor_same_order"]
    assert len(order_rels) == 0


def test_same_order_used_when_include_flag_set_and_candidates_insufficient(
    tmp_path: Path,
) -> None:
    # D: unique genus (12) + unique family (21) → 0 strong candidates → needs order fallback
    result = _run(
        tmp_path,
        [TAXON_A, TAXON_B, TAXON_C, TAXON_D],
        canonical_by_name=CANONICAL_BY_NAME,
        include_same_order=True,
    )
    rels = result["relationships"]
    d_order = [
        r
        for r in rels
        if r["target_scientific_name"] == "Falco tinnunculus"
        and r["source"] == "taxonomic_neighbor_same_order"
    ]
    # D has no genus/family neighbors, so order is used
    assert len(d_order) > 0
    assert all("same_order" in r["confusion_types"] for r in d_order)
    assert all(r["pedagogical_value"] == "low" for r in d_order)


def test_no_emergency_diversity_fallback_created(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        [TAXON_A, TAXON_B, TAXON_C, TAXON_D],
        canonical_by_name=CANONICAL_BY_NAME,
        include_same_order=True,
    )
    rels = result["relationships"]
    fallback = [r for r in rels if r["source"] == "emergency_diversity_fallback"]
    assert len(fallback) == 0


def test_unresolved_candidate_is_marked_unresolved_taxon(tmp_path: Path) -> None:
    taxon_with_unknown_hint = _taxon(
        name="Accipiter nisus",
        taxon_id=1001,
        genus_id=10,
        family_id=20,
        order_id=30,
        similar_taxa=[{"name": "UnknownSpecies exotica", "id": 9999}],
    )
    # No canonical or referenced entry for "UnknownSpecies exotica"
    result = _run(
        tmp_path,
        [taxon_with_unknown_hint],
        canonical_by_name={"Accipiter nisus": CANONICAL_A},
    )
    rels = result["relationships"]
    unresolved = [r for r in rels if r["candidate_scientific_name"] == "UnknownSpecies exotica"]
    assert len(unresolved) == 1
    assert unresolved[0]["candidate_taxon_ref_type"] == "unresolved_taxon"
    assert unresolved[0]["candidate_taxon_ref_id"] is None
    # unresolved must have status=needs_review per model constraint
    assert unresolved[0]["status"] == "needs_review"
    assert "unresolved_taxon_ref" in unresolved[0]["usability_blockers"]
    assert result["summary"]["unresolved_candidate_count"] == 1


def test_candidate_with_french_name_is_can_be_used_now_fr(tmp_path: Path) -> None:
    canonical_with_fr = {
        "Accipiter nisus": CANONICAL_A,
        "Accipiter gentilis": _canonical(
            "Accipiter gentilis", "taxon:birds:000002", fr_name="Autour des palombes"
        ),
    }
    result = _run(tmp_path, [TAXON_A, TAXON_B], canonical_by_name=canonical_with_fr)
    rels = result["relationships"]
    # A's candidate B has French name
    b_rels = [
        r
        for r in rels
        if r["target_scientific_name"] == "Accipiter nisus"
        and r["candidate_scientific_name"] == "Accipiter gentilis"
    ]
    assert len(b_rels) >= 1
    assert b_rels[0]["candidate_has_french_name"] is True
    assert b_rels[0]["can_be_used_now_fr"] is True
    assert "missing_french_name" not in b_rels[0]["usability_blockers"]


def test_candidate_without_french_name_is_not_can_be_used_now_fr(tmp_path: Path) -> None:
    # CANONICAL_B has no French name
    result = _run(tmp_path, [TAXON_A, TAXON_B], canonical_by_name=CANONICAL_BY_NAME)
    rels = result["relationships"]
    b_rels = [
        r
        for r in rels
        if r["target_scientific_name"] == "Accipiter nisus"
        and r["candidate_scientific_name"] == "Accipiter gentilis"
    ]
    assert len(b_rels) >= 1
    assert b_rels[0]["candidate_has_french_name"] is False
    assert b_rels[0]["can_be_used_now_fr"] is False
    assert "missing_french_name" in b_rels[0]["usability_blockers"]


def test_duplicate_pair_from_different_sources_keeps_source_specific_records(
    tmp_path: Path,
) -> None:
    # A appears in B's iNat hints AND B is also a same-genus neighbor → two separate rels
    taxon_a_with_hint = _taxon(
        name="Accipiter nisus",
        taxon_id=1001,
        genus_id=10,
        family_id=20,
        order_id=30,
        similar_taxa=[{"name": "Accipiter gentilis", "id": 1002}],
    )
    result = _run(
        tmp_path,
        [taxon_a_with_hint, TAXON_B],
        canonical_by_name=CANONICAL_BY_NAME,
    )
    rels = [
        r
        for r in result["relationships"]
        if r["target_scientific_name"] == "Accipiter nisus"
        and r["candidate_scientific_name"] == "Accipiter gentilis"
    ]
    sources = {r["source"] for r in rels}
    assert "inaturalist_similar_species" in sources
    assert "taxonomic_neighbor_same_genus" in sources


def test_writes_json(tmp_path: Path) -> None:
    result = _run(tmp_path, [TAXON_A, TAXON_B, TAXON_C], canonical_by_name=CANONICAL_BY_NAME)
    out = tmp_path / "out.json"
    out.write_text(json.dumps(result, indent=2))
    loaded = json.loads(out.read_text())
    assert loaded["execution_status"] == "complete"
    assert "relationships" in loaded
    assert "per_target_summaries" in loaded


def test_writes_markdown(tmp_path: Path) -> None:
    result = _run(tmp_path, [TAXON_A, TAXON_B, TAXON_C], canonical_by_name=CANONICAL_BY_NAME)
    out_md = tmp_path / "report.md"
    _write_markdown(result, out_md)
    content = out_md.read_text()
    assert "Distractor Relationship Candidates V1" in content
    assert "---" in content  # front matter
    assert "decision" in content.lower() or result.get("decision", "") in content


def test_handles_missing_snapshot_dir_gracefully(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent"
    result = run_generation(
        snapshot_dir=missing,
        canonical_by_name={},
        referenced_by_name={},
        normalized_by_name={},
        snapshot_id="test",
    )
    assert result["execution_status"] == "blocked"
    assert "block_reason" in result
