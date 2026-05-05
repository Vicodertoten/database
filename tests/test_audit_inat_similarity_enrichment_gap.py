from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.audit_inat_similarity_enrichment_gap import (
    RC_MAPPING_BUG,
    RC_PRESENT_NOT_EXTRACTED,
    RC_REQUIRE_API_REFRESH,
    RC_UNAVAILABLE,
    _classify_root_cause,
    _inspect_canonical_taxa,
    _inspect_raw_payloads,
    _write_markdown,
    run_audit,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_normalized_json(
    tmp_path: Path,
    *,
    n_taxa: int = 3,
    with_inat_hints: int = 0,
    enrichment_status: str = "complete",
) -> Path:
    taxa = []
    for i in range(n_taxa):
        hints: list[dict[str, Any]] = []
        if i < with_inat_hints:
            hints = [
                {
                    "source_name": "inaturalist",
                    "external_taxon_id": f"inat_{i}",
                    "relation_type": "visual_lookalike",
                }
            ]
        taxa.append(
            {
                "canonical_taxon_id": f"taxon:birds:{i:06d}",
                "accepted_scientific_name": f"Species {i}",
                "external_similarity_hints": hints,
                "similar_taxa": [],
                "similar_taxon_ids": [],
                "source_enrichment_status": enrichment_status,
                "external_source_mappings": [
                    {"source_name": "inaturalist", "external_id": f"{9000 + i}"}
                ],
            }
        )
    path = tmp_path / "normalized.json"
    path.write_text(json.dumps({"canonical_taxa": taxa}), encoding="utf-8")
    return path


def _make_raw_snapshot(
    tmp_path: Path,
    *,
    n_taxa: int = 3,
    include_similar_taxa: bool = False,
) -> Path:
    taxa_dir = tmp_path / "taxa"
    taxa_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n_taxa):
        record: dict[str, Any] = {
            "id": 9000 + i,
            "name": f"Species {i}",
            "vision": True,
            "rank": "species",
            "ancestor_ids": [],
        }
        if include_similar_taxa:
            record["similar_taxa"] = [
                {
                    "id": f"{8000 + i}",
                    "name": f"Lookalike {i}",
                    "preferred_common_name": f"Common Lookalike {i}",
                    "confidence": 0.7,
                }
            ]
        payload = {"page": 1, "per_page": 20, "results": [record], "total_results": 1}
        (taxa_dir / f"taxon_{i:06d}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    return tmp_path


def _make_manifest(
    snapshot_dir: Path,
    *,
    n_taxa: int = 3,
    include_enrichment_version: bool = False,
) -> Path:
    seeds = []
    taxa_dir = snapshot_dir / "taxa"
    for i in range(n_taxa):
        fname = f"taxon_{i:06d}.json"
        payload_path = f"taxa/{fname}"
        seeds.append(
            {
                "canonical_taxon_id": f"taxon:birds:{i:06d}",
                "accepted_scientific_name": f"Species {i}",
                "source_taxon_id": str(9000 + i),
                "taxon_payload_path": payload_path if (taxa_dir / fname).exists() else None,
                "taxon_status": "active",
            }
        )
    manifest: dict[str, Any] = {
        "snapshot_id": "test-snapshot",
        "manifest_version": "1",
        "source_name": "inaturalist",
        "taxon_seeds": seeds,
    }
    if include_enrichment_version:
        manifest["enrichment_version"] = "canonical.enrichment.v2"
    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


# ---------------------------------------------------------------------------
# Level A tests
# ---------------------------------------------------------------------------


def test_inspect_canonical_taxa_detects_hints_present(tmp_path: Path) -> None:
    norm = _make_normalized_json(tmp_path, n_taxa=5, with_inat_hints=3)
    result = _inspect_canonical_taxa(norm)
    assert result["total_taxa"] == 5
    assert result["taxa_with_inat_similarity_hints"] == 3
    assert result["taxa_with_any_similarity_hints"] == 3


def test_inspect_canonical_taxa_all_empty(tmp_path: Path) -> None:
    norm = _make_normalized_json(tmp_path, n_taxa=5, with_inat_hints=0)
    result = _inspect_canonical_taxa(norm)
    assert result["taxa_with_inat_similarity_hints"] == 0
    assert result["enrichment_status_distribution"] == {"complete": 5}


def test_inspect_canonical_taxa_missing_file(tmp_path: Path) -> None:
    result = _inspect_canonical_taxa(tmp_path / "nonexistent.json")
    assert "error" in result


# ---------------------------------------------------------------------------
# Level B tests
# ---------------------------------------------------------------------------


def test_inspect_raw_payloads_detects_hints_in_payloads(tmp_path: Path) -> None:
    snap = _make_raw_snapshot(tmp_path, n_taxa=4, include_similar_taxa=True)
    result = _inspect_raw_payloads(snap)
    assert result["payloads_with_similar_taxa"] == 4
    assert result["similar_taxa_field_absent"] is False


def test_inspect_raw_payloads_detects_empty_payloads(tmp_path: Path) -> None:
    snap = _make_raw_snapshot(tmp_path, n_taxa=4, include_similar_taxa=False)
    result = _inspect_raw_payloads(snap)
    assert result["payloads_with_similar_taxa"] == 0
    assert result["similar_taxa_field_absent"] is True


def test_inspect_raw_payloads_missing_dir(tmp_path: Path) -> None:
    result = _inspect_raw_payloads(tmp_path / "nonexistent")
    assert "error" in result


# ---------------------------------------------------------------------------
# Root cause classification tests
# ---------------------------------------------------------------------------


def _minimal_level_a(inat_hints: int = 0) -> dict[str, Any]:
    return {
        "total_taxa": 3,
        "taxa_with_inat_similarity_hints": inat_hints,
        "taxa_with_similar_taxa": 0,
        "enrichment_status_distribution": {"complete": 3},
    }


def _minimal_level_b(
    payloads: int = 3,
    with_similar: int = 0,
) -> dict[str, Any]:
    return {
        "total_payload_files": payloads,
        "payloads_with_similar_taxa": with_similar,
    }


def _minimal_level_c() -> dict[str, Any]:
    return {"snapshot_id": "test"}


def _minimal_level_d(harvest_calls: bool = False) -> dict[str, Any]:
    return {"harvest_calls_similar_species_endpoint": harvest_calls}


def test_classify_requires_api_refresh_when_no_similar_in_payloads() -> None:
    rc, decision, _ = _classify_root_cause(
        _minimal_level_a(0),
        _minimal_level_b(3, 0),
        _minimal_level_c(),
        _minimal_level_d(False),
    )
    assert rc == RC_REQUIRE_API_REFRESH
    assert "REFRESH" in decision


def test_classify_present_not_extracted_when_payloads_have_hints_canonical_empty() -> None:
    rc, decision, _ = _classify_root_cause(
        _minimal_level_a(0),
        _minimal_level_b(3, 3),  # payloads have hints
        _minimal_level_c(),
        _minimal_level_d(False),
    )
    assert rc == RC_PRESENT_NOT_EXTRACTED
    assert "EXTRACT" in decision


def test_classify_mapping_bug_when_canonical_has_hints_but_payloads_empty() -> None:
    rc, decision, _ = _classify_root_cause(
        _minimal_level_a(inat_hints=2),  # canonical has hints
        _minimal_level_b(3, 0),  # payloads don't
        _minimal_level_c(),
        _minimal_level_d(False),
    )
    assert rc == RC_MAPPING_BUG
    assert "FIX" in decision


def test_classify_unavailable_when_no_payload_files() -> None:
    rc, decision, _ = _classify_root_cause(
        _minimal_level_a(0),
        _minimal_level_b(0, 0),  # no payloads at all
        _minimal_level_c(),
        _minimal_level_d(False),
    )
    assert rc == RC_UNAVAILABLE
    assert "BLOCKED" in decision or "MISSING" in decision


# ---------------------------------------------------------------------------
# run_audit integration tests
# ---------------------------------------------------------------------------


def test_run_audit_with_no_similar_data_classifies_api_refresh(tmp_path: Path) -> None:
    snap = _make_raw_snapshot(tmp_path / "snap", n_taxa=3, include_similar_taxa=False)
    _make_manifest(snap, n_taxa=3)
    norm = _make_normalized_json(tmp_path, n_taxa=3, with_inat_hints=0)
    result = run_audit("test-snapshot", snap, norm)
    assert result["root_cause_classification"] == RC_REQUIRE_API_REFRESH
    assert result["execution_status"] == "complete"
    assert result["evidence_summary"]["taxa_inspected"] == 3


def test_run_audit_handles_missing_snapshot_gracefully(tmp_path: Path) -> None:
    norm = _make_normalized_json(tmp_path, n_taxa=3, with_inat_hints=0)
    result = run_audit("missing-snap", tmp_path / "nonexistent", norm)
    # Should complete but with errors in level B/C
    assert result["execution_status"] == "complete"
    assert "error" in result["levels"]["B_raw_payloads"]


# ---------------------------------------------------------------------------
# Output tests
# ---------------------------------------------------------------------------


def test_run_audit_writes_json(tmp_path: Path) -> None:
    snap = _make_raw_snapshot(tmp_path / "snap", n_taxa=2, include_similar_taxa=False)
    _make_manifest(snap, n_taxa=2)
    norm = _make_normalized_json(tmp_path, n_taxa=2)
    result = run_audit("test", snap, norm)
    out = tmp_path / "out.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    loaded = json.loads(out.read_text())
    assert loaded["root_cause_classification"] == RC_REQUIRE_API_REFRESH
    assert "levels" in loaded
    assert "evidence_summary" in loaded


def test_run_audit_writes_markdown(tmp_path: Path) -> None:
    snap = _make_raw_snapshot(tmp_path / "snap", n_taxa=2, include_similar_taxa=False)
    _make_manifest(snap, n_taxa=2)
    norm = _make_normalized_json(tmp_path, n_taxa=2)
    result = run_audit("test", snap, norm)
    out_md = tmp_path / "report.md"
    _write_markdown(result, out_md)
    content = out_md.read_text()
    assert "iNat Similarity Enrichment Gap Audit" in content
    assert "READY_FOR_INAT_TAXON_REFRESH" in content
    assert "SIMILAR_HINTS_REQUIRE_API_REFRESH" in content
    assert "similar_species" in content
