from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_distractor_relationships_v1_current_state import (
    _write_markdown,
    run_audit,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_snapshot_dir(
    tmp_path: Path,
    taxa: list[dict],
) -> Path:
    """Build a minimal snapshot directory with a taxa/ subdir."""
    snap = tmp_path / "test-snapshot"
    taxa_dir = snap / "taxa"
    taxa_dir.mkdir(parents=True)
    (taxa_dir / "taxon_birds_000001.json").write_text(
        json.dumps({"results": taxa})
    )
    return snap


def _taxon(
    *,
    name: str,
    taxon_id: int,
    genus_id: int = 100,
    family_id: int = 200,
    order_id: int = 300,
    similar_taxa: list[dict] | None = None,
) -> dict:
    return {
        "id": taxon_id,
        "name": name,
        "rank": "species",
        "ancestry": "48460/1/2",
        "ancestors": [
            {"rank": "genus", "id": genus_id, "name": "Testgenus"},
            {"rank": "family", "id": family_id, "name": "Testfamily"},
            {"rank": "order", "id": order_id, "name": "Testorder"},
        ],
        "similar_taxa": similar_taxa or [],
    }


TAXON_A = _taxon(name="Accipiter nisus", taxon_id=1001, genus_id=10, family_id=20, order_id=30)
TAXON_B = _taxon(name="Accipiter gentilis", taxon_id=1002, genus_id=10, family_id=20, order_id=30)
TAXON_C = _taxon(name="Buteo buteo", taxon_id=1003, genus_id=11, family_id=20, order_id=30)
TAXON_D = _taxon(name="Falco tinnunculus", taxon_id=1004, genus_id=12, family_id=21, order_id=30)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_audit_handles_minimal_fixture(tmp_path: Path) -> None:
    snap = _make_snapshot_dir(tmp_path, [TAXON_A])
    result = run_audit(snapshot_dir=snap, export_bundle={}, snapshot_id="test")
    assert result["execution_status"] == "complete"
    assert result["target_taxa_count"] == 1


def test_audit_handles_missing_input_gracefully(tmp_path: Path) -> None:
    missing_dir = tmp_path / "nonexistent"
    result = run_audit(snapshot_dir=missing_dir, export_bundle={}, snapshot_id="test")
    assert result["execution_status"] == "blocked"
    assert "block_reason" in result


def test_counts_inat_hints(tmp_path: Path) -> None:
    taxon_with_hints = _taxon(
        name="Accipiter nisus",
        taxon_id=1001,
        genus_id=10,
        family_id=20,
        order_id=30,
        similar_taxa=[
            {"id": 2001, "name": "Accipiter gentilis"},
            {"id": 2002, "name": "Falco peregrinus"},
        ],
    )
    snap = _make_snapshot_dir(tmp_path, [taxon_with_hints])
    result = run_audit(snapshot_dir=snap, export_bundle={}, snapshot_id="test")
    assert result["taxa_with_inat_similarity_hints"] == 1
    assert result["source_coverage"]["inaturalist_hint_count"] == 2


def test_counts_same_genus_neighbors(tmp_path: Path) -> None:
    # A and B share genus_id=10; C has genus_id=11
    snap = _make_snapshot_dir(tmp_path, [TAXON_A, TAXON_B, TAXON_C])
    result = run_audit(snapshot_dir=snap, export_bundle={}, snapshot_id="test")
    # A should have 1 same-genus neighbor (B), and vice versa
    summaries = {s["scientific_name"]: s for s in result["per_target_summaries"]}
    assert summaries["Accipiter nisus"]["same_genus_count"] == 1
    assert summaries["Accipiter gentilis"]["same_genus_count"] == 1
    assert summaries["Buteo buteo"]["same_genus_count"] == 0


def test_computes_ready_for_distractor_v1_when_3_plus_candidates_and_inat(
    tmp_path: Path,
) -> None:
    taxon_with_hints = _taxon(
        name="Accipiter nisus",
        taxon_id=1001,
        genus_id=10,
        family_id=20,
        order_id=30,
        similar_taxa=[
            {"id": 2001, "name": "Accipiter gentilis"},
            {"id": 2002, "name": "Falco peregrinus"},
            {"id": 2003, "name": "Buteo buteo"},
        ],
    )
    snap = _make_snapshot_dir(tmp_path, [taxon_with_hints])
    result = run_audit(snapshot_dir=snap, export_bundle={}, snapshot_id="test")
    summaries = {s["scientific_name"]: s for s in result["per_target_summaries"]}
    assert summaries["Accipiter nisus"]["readiness_status"] == "ready_for_distractor_v1"
    assert result["first_corpus_readiness_preview"]["ready_for_distractor_v1_count"] == 1


def test_computes_insufficient_distractors_when_less_than_3(tmp_path: Path) -> None:
    taxon_lonely = _taxon(
        name="Accipiter nisus",
        taxon_id=1001,
        genus_id=999,  # unique genus — no neighbors
        family_id=998,  # unique family
        order_id=997,  # unique order
        similar_taxa=[{"id": 2001, "name": "Accipiter gentilis"}],
    )
    snap = _make_snapshot_dir(tmp_path, [taxon_lonely])
    result = run_audit(snapshot_dir=snap, export_bundle={}, snapshot_id="test")
    summaries = {s["scientific_name"]: s for s in result["per_target_summaries"]}
    assert summaries["Accipiter nisus"]["total_potential_candidates"] < 3
    assert summaries["Accipiter nisus"]["readiness_status"] == "insufficient_distractors"


def test_handles_no_candidates(tmp_path: Path) -> None:
    taxon_isolated = _taxon(
        name="Accipiter nisus",
        taxon_id=1001,
        genus_id=999,
        family_id=998,
        order_id=997,
        similar_taxa=[],
    )
    snap = _make_snapshot_dir(tmp_path, [taxon_isolated])
    result = run_audit(snapshot_dir=snap, export_bundle={}, snapshot_id="test")
    summaries = {s["scientific_name"]: s for s in result["per_target_summaries"]}
    assert summaries["Accipiter nisus"]["total_potential_candidates"] == 0
    assert result["taxa_without_candidates"] == 1


def test_writes_json(tmp_path: Path) -> None:
    snap = _make_snapshot_dir(tmp_path, [TAXON_A, TAXON_B])
    result = run_audit(snapshot_dir=snap, export_bundle={}, snapshot_id="test")
    out = tmp_path / "out.json"
    out.write_text(json.dumps(result, indent=2))
    loaded = json.loads(out.read_text())
    assert loaded["execution_status"] == "complete"
    assert "per_target_summaries" in loaded


def test_writes_markdown(tmp_path: Path) -> None:
    snap = _make_snapshot_dir(tmp_path, [TAXON_A, TAXON_B, TAXON_C])
    result = run_audit(snapshot_dir=snap, export_bundle={}, snapshot_id="test")
    out_md = tmp_path / "report.md"
    _write_markdown(result, out_md)
    content = out_md.read_text()
    assert "Distractor Relationships V1" in content
    assert (
        "decision" in content.lower()
        or "NEEDS_TAXON_ENRICHMENT" in content
        or "READY" in content
    )
    assert "---" in content  # front matter present


def test_does_not_require_runtime_or_pack_artifacts(tmp_path: Path) -> None:
    # Just verify the audit runs with only snapshot data — no pack, no runtime artifacts
    snap = _make_snapshot_dir(tmp_path, [TAXON_A, TAXON_B, TAXON_C, TAXON_D])
    result = run_audit(snapshot_dir=snap, export_bundle={}, snapshot_id="test")
    assert result["execution_status"] == "complete"
    assert result["target_taxa_count"] == 4
    # All summaries have required fields
    for s in result["per_target_summaries"]:
        assert "readiness_status" in s
        assert "total_potential_candidates" in s


def test_multiple_taxa_same_family_neighbors(tmp_path: Path) -> None:
    # A, B share genus 10; C has genus 11; A, B, C share family 20; D has family 21
    snap = _make_snapshot_dir(tmp_path, [TAXON_A, TAXON_B, TAXON_C, TAXON_D])
    result = run_audit(snapshot_dir=snap, export_bundle={}, snapshot_id="test")
    summaries = {s["scientific_name"]: s for s in result["per_target_summaries"]}
    # A: same_genus=B (1), same_family=C (1 = family20 minus genus10 members)
    assert summaries["Accipiter nisus"]["same_genus_count"] == 1
    assert summaries["Accipiter nisus"]["same_family_count"] == 1
    # D: genus 12 unique, family 21 unique; same_order candidates = A+B+C
    assert summaries["Falco tinnunculus"]["same_genus_count"] == 0
    assert summaries["Falco tinnunculus"]["same_family_count"] == 0
    assert summaries["Falco tinnunculus"]["same_order_count"] == 3
