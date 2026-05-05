"""
tests/test_inat_taxon_similarity_enrichment.py

Sprint 12 Phase B — unit tests for inat_taxon_similarity_enrichment ops module.
All tests use in-memory fixtures to avoid disk/network dependency.
"""
from __future__ import annotations

import json
from pathlib import Path

from database_core.ops.inat_taxon_similarity_enrichment import (
    SimilarSpeciesHint,
    TaxonEnrichmentResult,
    _build_canonical_index,
    _extract_inat_pairs,
    _parse_hints,
    apply_hints_to_normalized,
    build_audit_evidence,
    run_enrichment,
    write_markdown_report,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SAMPLE_API_PAYLOAD = {
    "total_results": 2,
    "page": 1,
    "per_page": 2,
    "results": [
        {
            "taxon": {
                "id": 3017,
                "name": "Columba livia",
                "preferred_common_name": "Rock Pigeon",
                "rank": "species",
            },
            "count": 11,
        },
        {
            "taxon": {
                "id": 5062,
                "name": "Streptopelia decaocto",
                "preferred_common_name": "Eurasian Collared-Dove",
                "rank": "species",
            },
            "count": 4,
        },
    ],
}

_MINIMAL_TAXA = [
    {
        "canonical_taxon_id": "taxon:birds:000001",
        "accepted_scientific_name": "Columba palumbus",
        "external_source_mappings": [
            {"source_name": "inaturalist", "external_id": "3048"}
        ],
        "external_similarity_hints": [],
    },
    {
        "canonical_taxon_id": "taxon:birds:000002",
        "accepted_scientific_name": "Corvus corone",
        "external_source_mappings": [
            {"source_name": "inaturalist", "external_id": "204496"}
        ],
        "external_similarity_hints": [],
    },
]


# ---------------------------------------------------------------------------
# 1. Hint extraction from cached payload fixture
# ---------------------------------------------------------------------------


def test_parse_hints_extracts_similar_species_hints():
    hints = _parse_hints(_SAMPLE_API_PAYLOAD)
    assert len(hints) == 2
    assert hints[0].inat_id == "3017"
    assert hints[0].scientific_name == "Columba livia"
    assert hints[0].preferred_common_name == "Rock Pigeon"
    assert hints[0].count == 11


# ---------------------------------------------------------------------------
# 2. External taxon ID is preserved
# ---------------------------------------------------------------------------


def test_parse_hints_preserves_external_taxon_id():
    hints = _parse_hints(_SAMPLE_API_PAYLOAD)
    ids = [h.inat_id for h in hints]
    assert "3017" in ids
    assert "5062" in ids


# ---------------------------------------------------------------------------
# 3. Source rank/order is preserved
# ---------------------------------------------------------------------------


def test_parse_hints_preserves_source_rank_order():
    hints = _parse_hints(_SAMPLE_API_PAYLOAD)
    assert hints[0].source_rank_order == 0
    assert hints[1].source_rank_order == 1
    assert hints[0].rank == "species"


# ---------------------------------------------------------------------------
# 4. Empty similar_species field is handled gracefully
# ---------------------------------------------------------------------------


def test_parse_hints_handles_missing_results():
    assert _parse_hints({}) == []
    assert _parse_hints({"results": []}) == []


def test_parse_hints_skips_results_without_taxon_id():
    payload = {"results": [{"taxon": {"name": "Unknown"}, "count": 2}]}
    assert _parse_hints(payload) == []


# ---------------------------------------------------------------------------
# 5. to_external_similarity_hint_dict maps correctly
# ---------------------------------------------------------------------------


def test_hint_to_external_similarity_hint_dict():
    hint = SimilarSpeciesHint(
        inat_id="3017",
        scientific_name="Columba livia",
        preferred_common_name="Rock Pigeon",
        rank="species",
        count=11,
        source_rank_order=0,
    )
    d = hint.to_external_similarity_hint_dict()
    assert d["source_name"] == "inaturalist"
    assert d["external_taxon_id"] == "3017"
    assert d["accepted_scientific_name"] == "Columba livia"
    assert d["common_name"] == "Rock Pigeon"
    assert d["relation_type"] == "visual_lookalike"
    assert d["confidence"] is None


# ---------------------------------------------------------------------------
# 6. apply_hints_to_normalized does not create CanonicalTaxon for unresolved hints
# ---------------------------------------------------------------------------


def test_apply_hints_does_not_create_canonical_taxon():
    hints = _parse_hints(_SAMPLE_API_PAYLOAD)
    # Neither 3017 nor 5062 is in _MINIMAL_TAXA — they are unresolved
    result = TaxonEnrichmentResult(
        canonical_taxon_id="taxon:birds:000001",
        scientific_name="Columba palumbus",
        inat_id="3048",
        hints=hints,
        fetch_status="ok",
    )
    enriched = apply_hints_to_normalized(_MINIMAL_TAXA, [result])
    canonical_ids = {t["canonical_taxon_id"] for t in enriched}
    # Only original taxa should exist
    assert "taxon:birds:000001" in canonical_ids
    assert "taxon:birds:000002" in canonical_ids
    assert len(enriched) == len(_MINIMAL_TAXA)
    # Hint iNat IDs must NOT become canonical_taxon_ids
    hint_ids = {"3017", "5062"}
    assert not hint_ids.intersection(canonical_ids)


# ---------------------------------------------------------------------------
# 7. apply_hints_to_normalized only updates external_similarity_hints
# ---------------------------------------------------------------------------


def test_apply_hints_does_not_mutate_identity_fields():
    hints = _parse_hints(_SAMPLE_API_PAYLOAD)
    result = TaxonEnrichmentResult(
        canonical_taxon_id="taxon:birds:000001",
        scientific_name="Columba palumbus",
        inat_id="3048",
        hints=hints,
        fetch_status="ok",
    )
    original_taxa = [dict(t) for t in _MINIMAL_TAXA]
    enriched = apply_hints_to_normalized(original_taxa, [result])
    t = next(t for t in enriched if t["canonical_taxon_id"] == "taxon:birds:000001")
    # Identity fields must not be mutated
    assert t["accepted_scientific_name"] == "Columba palumbus"
    assert t["canonical_taxon_id"] == "taxon:birds:000001"
    # Only external_similarity_hints should be updated
    assert len(t["external_similarity_hints"]) == 2


# ---------------------------------------------------------------------------
# 8. build_audit_evidence writes correct keys
# ---------------------------------------------------------------------------


def test_build_audit_evidence_keys():
    hints = _parse_hints(_SAMPLE_API_PAYLOAD)
    results = [
        TaxonEnrichmentResult(
            canonical_taxon_id="taxon:birds:000001",
            scientific_name="Columba palumbus",
            inat_id="3048",
            hints=hints,
            fetch_status="ok",
        )
    ]
    canonical_index: dict[str, str] = {"3048": "taxon:birds:000001"}
    evidence = build_audit_evidence(
        snapshot_id="test-snapshot",
        results=results,
        canonical_index=canonical_index,
        dry_run=False,
        refresh_live=True,
    )
    required_keys = {
        "execution_status",
        "enrichment_mode",
        "targets_attempted",
        "targets_enriched",
        "targets_with_inat_similarity_hints",
        "total_similarity_hints",
        "hints_with_external_taxon_id",
        "hints_with_scientific_name",
        "hints_with_common_name",
        "hints_mapped_to_existing_canonical_taxon",
        "hints_unmapped",
        "raw_payloads_read",
        "raw_payloads_fetched_live",
        "cache_paths_written",
        "errors",
        "skipped_taxa",
    }
    assert required_keys.issubset(set(evidence.keys()))
    assert evidence["targets_attempted"] == 1
    assert evidence["total_similarity_hints"] == 2


# ---------------------------------------------------------------------------
# 9. write_markdown_report produces valid front matter
# ---------------------------------------------------------------------------


def test_write_markdown_report_front_matter(tmp_path: Path):
    hints = _parse_hints(_SAMPLE_API_PAYLOAD)
    results = [
        TaxonEnrichmentResult(
            canonical_taxon_id="taxon:birds:000001",
            scientific_name="Columba palumbus",
            inat_id="3048",
            hints=hints,
            fetch_status="ok",
        )
    ]
    evidence = build_audit_evidence(
        snapshot_id="test-snapshot",
        results=results,
        canonical_index={},
        dry_run=False,
        refresh_live=True,
    )
    output = tmp_path / "report.md"
    write_markdown_report(evidence, output)
    content = output.read_text()
    assert "owner: database" in content
    assert "status: ready_for_validation" in content
    assert "scope: audit" in content
    assert "last_reviewed:" in content


# ---------------------------------------------------------------------------
# 10. dry_run does not write to data/enriched
# ---------------------------------------------------------------------------


def test_dry_run_does_not_write_cache(tmp_path: Path):
    normalized_path = tmp_path / "test.normalized.json"
    normalized_path.write_text(
        json.dumps({"canonical_taxa": _MINIMAL_TAXA}), encoding="utf-8"
    )
    enriched_dir = tmp_path / "enriched"

    evidence = run_enrichment(
        snapshot_id="test-snapshot",
        normalized_path=normalized_path,
        enriched_dir=enriched_dir,
        dry_run=True,
        refresh_live=True,
    )

    # No cache directory should have been created
    assert not enriched_dir.exists() or not any(enriched_dir.rglob("*.json"))
    # All taxa should be skipped
    assert all(
        r["fetch_status"] == "skipped" for r in evidence["per_target"]
    )


# ---------------------------------------------------------------------------
# 11. live refresh disabled by default (refresh_live=False → skip without cache)
# ---------------------------------------------------------------------------


def test_live_refresh_disabled_by_default_skips_without_cache(tmp_path: Path):
    normalized_path = tmp_path / "test.normalized.json"
    normalized_path.write_text(
        json.dumps({"canonical_taxa": _MINIMAL_TAXA[:1]}), encoding="utf-8"
    )
    enriched_dir = tmp_path / "enriched"

    evidence = run_enrichment(
        snapshot_id="test-snapshot",
        normalized_path=normalized_path,
        enriched_dir=enriched_dir,
        dry_run=False,
        refresh_live=False,  # default
    )

    assert all(
        r["fetch_status"] in ("cached", "skipped") for r in evidence["per_target"]
    )
    assert evidence["raw_payloads_fetched_live"] == 0


# ---------------------------------------------------------------------------
# 12. cache is read without live fetch when refresh_live=False and cache exists
# ---------------------------------------------------------------------------


def test_cache_read_avoids_live_fetch(tmp_path: Path):
    normalized_path = tmp_path / "test.normalized.json"
    normalized_path.write_text(
        json.dumps({"canonical_taxa": _MINIMAL_TAXA[:1]}), encoding="utf-8"
    )
    enriched_dir = tmp_path / "enriched"

    # Pre-populate cache
    cache_file = (
        enriched_dir / "test-snapshot" / "similar_species" / "taxon_birds_000001.json"
    )
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(
            {
                "inat_id": "3048",
                "scientific_name": "Columba palumbus",
                "fetched_at": "2025-01-01T00:00:00+00:00",
                "raw_payload": _SAMPLE_API_PAYLOAD,
            }
        ),
        encoding="utf-8",
    )

    evidence = run_enrichment(
        snapshot_id="test-snapshot",
        normalized_path=normalized_path,
        enriched_dir=enriched_dir,
        dry_run=False,
        refresh_live=False,
    )

    assert evidence["per_target"][0]["fetch_status"] == "cached"
    assert evidence["per_target"][0]["hint_count"] == 2
    assert evidence["raw_payloads_fetched_live"] == 0


# ---------------------------------------------------------------------------
# 13. _build_canonical_index covers all taxa
# ---------------------------------------------------------------------------


def test_build_canonical_index():
    index = _build_canonical_index(_MINIMAL_TAXA)
    assert index["3048"] == "taxon:birds:000001"
    assert index["204496"] == "taxon:birds:000002"


# ---------------------------------------------------------------------------
# 14. _extract_inat_pairs returns sorted pairs
# ---------------------------------------------------------------------------


def test_extract_inat_pairs_sorted():
    pairs = _extract_inat_pairs(_MINIMAL_TAXA)
    assert len(pairs) == 2
    assert pairs[0][0] == "taxon:birds:000001"
    assert pairs[0][1] == "3048"
    assert pairs[1][0] == "taxon:birds:000002"
