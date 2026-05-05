"""
tests/test_taxon_localized_names_for_distractors.py

Sprint 12 Phase C — tests for audit and apply localized names scripts.
All tests use in-memory fixtures; no network or disk dependencies.
"""
from __future__ import annotations

import csv
from pathlib import Path

from scripts.apply_taxon_localized_names_sprint12 import (
    apply_names,
)
from scripts.apply_taxon_localized_names_sprint12 import (
    build_evidence as build_apply_evidence,
)
from scripts.apply_taxon_localized_names_sprint12 import (
    write_markdown_report as write_apply_md,
)
from scripts.audit_taxon_localized_names_for_distractors import (
    _extract_preferred_names_from_all_names,
    analyze_names_gap,
    build_evidence,
    write_proposed_csv,
)
from scripts.audit_taxon_localized_names_for_distractors import (
    write_markdown_report as write_audit_md,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_TAXA_NO_FR = [
    {
        "canonical_taxon_id": "taxon:birds:000001",
        "accepted_scientific_name": "Columba palumbus",
        "common_names_by_language": {"en": ["Common Wood-Pigeon"]},
        "external_source_mappings": [{"source_name": "inaturalist", "external_id": "3048"}],
    },
    {
        "canonical_taxon_id": "taxon:birds:000002",
        "accepted_scientific_name": "Corvus corone",
        "common_names_by_language": {"en": ["Carrion Crow"]},
        "external_source_mappings": [{"source_name": "inaturalist", "external_id": "204496"}],
    },
]

_TAXA_WITH_FR = [
    {
        "canonical_taxon_id": "taxon:birds:000001",
        "accepted_scientific_name": "Columba palumbus",
        "common_names_by_language": {"en": ["Common Wood-Pigeon"], "fr": ["Pigeon ramier"]},
        "external_source_mappings": [{"source_name": "inaturalist", "external_id": "3048"}],
    },
]

_CANDIDATE_RELS = [
    {
        "candidate_taxon_ref_id": "taxon:birds:000001",
        "candidate_has_french_name": False,
        "can_be_used_now_fr": False,
    },
    {
        "candidate_taxon_ref_id": "taxon:birds:000002",
        "candidate_has_french_name": False,
        "can_be_used_now_fr": False,
    },
]

_INAT_ALL_NAMES_PAYLOAD = {
    "results": [
        {
            "id": 3048,
            "name": "Columba palumbus",
            "preferred_common_name": "Common Wood-Pigeon",
            "names": [
                {"locale": "en", "name": "Common Wood-Pigeon", "is_valid": True},
                {"locale": "fr", "name": "Pigeon ramier", "is_valid": True},
                {"locale": "nl", "name": "Houtduif", "is_valid": True},
            ],
        }
    ]
}

_CSV_ROWS_GOOD = [
    {
        "scientific_name": "Columba palumbus",
        "source_taxon_id": "3048",
        "canonical_taxon_id": "taxon:birds:000001",
        "referenced_taxon_id": "",
        "common_name_fr": "Pigeon ramier",
        "common_name_en": "",
        "common_name_nl": "Houtduif",
        "source": "inat_all_names_live",
        "reviewer": "",
        "notes": "",
    },
    {
        "scientific_name": "Corvus corone",
        "source_taxon_id": "204496",
        "canonical_taxon_id": "taxon:birds:000002",
        "referenced_taxon_id": "",
        "common_name_fr": "Corneille noire",
        "common_name_en": "",
        "common_name_nl": "Zwarte kraai",
        "source": "inat_all_names_live",
        "reviewer": "",
        "notes": "",
    },
]


# ---------------------------------------------------------------------------
# 1. audit: missing French names are detected
# ---------------------------------------------------------------------------


def test_analyze_names_gap_detects_missing_fr(tmp_path: Path):
    gap = analyze_names_gap(
        _TAXA_NO_FR,
        _CANDIDATE_RELS,
        enriched_dir=tmp_path,
        snapshot_id="test",
        fetch_live=False,
    )
    missing_fr = [t for t in gap["per_taxon"] if not t["existing_fr"]]
    assert len(missing_fr) == 2


# ---------------------------------------------------------------------------
# 2. iNat all_names extraction returns correct FR name
# ---------------------------------------------------------------------------


def test_extract_preferred_names_returns_fr():
    names = _extract_preferred_names_from_all_names(_INAT_ALL_NAMES_PAYLOAD)
    assert names.get("fr") == "Pigeon ramier"
    assert names.get("nl") == "Houtduif"
    assert names.get("en") == "Common Wood-Pigeon"


# ---------------------------------------------------------------------------
# 3. apply_names: French name added from CSV
# ---------------------------------------------------------------------------


def test_apply_names_adds_french_name():
    result = apply_names(_TAXA_NO_FR, _CSV_ROWS_GOOD)
    patched = {t["canonical_taxon_id"]: t for t in result["patched_taxa"]}
    cbn_1 = patched["taxon:birds:000001"].get("common_names_by_language", {})
    assert "fr" in cbn_1
    assert "Pigeon ramier" in cbn_1["fr"]
    assert result["fr_added_count"] == 2


# ---------------------------------------------------------------------------
# 4. apply_names: existing French name is not overwritten silently
# ---------------------------------------------------------------------------


def test_apply_names_does_not_overwrite_existing_fr():
    # taxon:birds:000001 already has fr = "Pigeon ramier"
    csv_rows_overwrite = [
        {
            "scientific_name": "Columba palumbus",
            "source_taxon_id": "3048",
            "canonical_taxon_id": "taxon:birds:000001",
            "referenced_taxon_id": "",
            "common_name_fr": "Colombe du bois",  # different — should conflict
            "common_name_en": "",
            "common_name_nl": "",
            "source": "manual",
            "reviewer": "",
            "notes": "",
        }
    ]
    result = apply_names(_TAXA_WITH_FR, csv_rows_overwrite)
    patched = {t["canonical_taxon_id"]: t for t in result["patched_taxa"]}
    cbn = patched["taxon:birds:000001"].get("common_names_by_language", {})
    # Original name preserved
    assert "Pigeon ramier" in cbn.get("fr", [])
    # New name NOT added silently
    assert "Colombe du bois" not in cbn.get("fr", [])
    # Conflict reported
    assert len(result["conflicts"]) == 1


# ---------------------------------------------------------------------------
# 5. conflict is reported in evidence
# ---------------------------------------------------------------------------


def test_apply_names_conflict_in_evidence():
    csv_conflict = [
        {
            "scientific_name": "Columba palumbus",
            "source_taxon_id": "",
            "canonical_taxon_id": "taxon:birds:000001",
            "referenced_taxon_id": "",
            "common_name_fr": "Pigeon des bois",
            "common_name_en": "",
            "common_name_nl": "",
            "source": "manual",
            "reviewer": "",
            "notes": "",
        }
    ]
    apply_result = apply_names(_TAXA_WITH_FR, csv_conflict)
    evidence = build_apply_evidence("test", apply_result, [])
    assert len(evidence["conflicts"]) == 1
    assert evidence["conflicts"][0]["lang"] == "fr"


# ---------------------------------------------------------------------------
# 6. unknown scientific name → unresolved row
# ---------------------------------------------------------------------------


def test_apply_names_unknown_name_is_unresolved():
    csv_unknown = [
        {
            "scientific_name": "Nonexistent species",
            "source_taxon_id": "",
            "canonical_taxon_id": "",
            "referenced_taxon_id": "",
            "common_name_fr": "Oiseau inconnu",
            "common_name_en": "",
            "common_name_nl": "",
            "source": "manual",
            "reviewer": "",
            "notes": "",
        }
    ]
    result = apply_names(_TAXA_NO_FR, csv_unknown)
    assert len(result["unresolved_rows"]) == 1
    assert result["fr_added_count"] == 0


# ---------------------------------------------------------------------------
# 7. audit evidence JSON has correct keys
# ---------------------------------------------------------------------------


def test_build_audit_evidence_keys():
    gap = analyze_names_gap(
        _TAXA_NO_FR,
        _CANDIDATE_RELS,
        enriched_dir=Path("/tmp/nonexistent_test_enriched"),
        snapshot_id="test",
        fetch_live=False,
    )
    evidence = build_evidence(
        snapshot_id="test",
        normalized_taxa=_TAXA_NO_FR,
        candidate_relationships=_CANDIDATE_RELS,
        gap_analysis=gap,
        fetch_live=False,
    )
    required = {
        "targets_missing_fr",
        "candidate_taxa_missing_fr",
        "fr_resolvable_from_inat",
        "names_requiring_manual",
        "candidates_fr_usable_now",
        "candidates_fr_usable_projected",
        "decision",
    }
    assert required.issubset(set(evidence.keys()))
    assert evidence["targets_missing_fr"] == 2
    assert evidence["candidate_taxa_missing_fr"] == 2


# ---------------------------------------------------------------------------
# 8. audit Markdown has correct front matter
# ---------------------------------------------------------------------------


def test_audit_markdown_front_matter(tmp_path: Path):
    gap = analyze_names_gap(
        _TAXA_NO_FR,
        _CANDIDATE_RELS,
        enriched_dir=tmp_path / "enriched",
        snapshot_id="test",
        fetch_live=False,
    )
    evidence = build_evidence(
        snapshot_id="test",
        normalized_taxa=_TAXA_NO_FR,
        candidate_relationships=_CANDIDATE_RELS,
        gap_analysis=gap,
        fetch_live=False,
    )
    out = tmp_path / "audit.md"
    write_audit_md(evidence, out)
    content = out.read_text()
    assert "owner: database" in content
    assert "status: ready_for_validation" in content
    assert "scope: audit" in content


# ---------------------------------------------------------------------------
# 9. apply Markdown has correct front matter
# ---------------------------------------------------------------------------


def test_apply_markdown_front_matter(tmp_path: Path):
    apply_result = apply_names(_TAXA_NO_FR, _CSV_ROWS_GOOD)
    evidence = build_apply_evidence("test", apply_result, _CANDIDATE_RELS)
    out = tmp_path / "enrichment.md"
    write_apply_md(evidence, out)
    content = out.read_text()
    assert "owner: database" in content
    assert "status: ready_for_validation" in content
    assert "scope: audit" in content


# ---------------------------------------------------------------------------
# 10. FR usability improves after names applied
# ---------------------------------------------------------------------------


def test_fr_usability_improves_after_apply():
    # Before: no FR names → 0 FR-usable candidates
    apply_result = apply_names(_TAXA_NO_FR, _CSV_ROWS_GOOD)
    evidence = build_apply_evidence("test", apply_result, _CANDIDATE_RELS)
    assert evidence["candidates_now_fr_usable"] == 2
    assert evidence["candidates_still_missing_fr"] == 0
    assert evidence["fr_added_count"] == 2


# ---------------------------------------------------------------------------
# 11. propose CSV write includes FR names
# ---------------------------------------------------------------------------


def test_write_proposed_csv(tmp_path: Path):
    gap = analyze_names_gap(
        _TAXA_NO_FR,
        _CANDIDATE_RELS,
        enriched_dir=tmp_path / "enriched",
        snapshot_id="test",
        fetch_live=False,
    )
    evidence = build_evidence(
        snapshot_id="test",
        normalized_taxa=_TAXA_NO_FR,
        candidate_relationships=_CANDIDATE_RELS,
        gap_analysis=gap,
        fetch_live=False,
    )
    # Manually inject proposed names to simulate fetch
    for t in evidence["per_taxon"]:
        if t["canonical_taxon_id"] == "taxon:birds:000001":
            t["proposed_names"] = {"fr": "Pigeon ramier", "nl": "Houtduif"}
            t["name_source"] = "inat_all_names_live"
            t["fr_resolvable"] = True
            t["nl_resolvable"] = True

    csv_path = tmp_path / "names.csv"
    write_proposed_csv(evidence, csv_path)
    assert csv_path.exists()
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    assert any(r.get("common_name_fr") for r in rows)


# ---------------------------------------------------------------------------
# 12. apply_names: same name not duplicated when re-applied
# ---------------------------------------------------------------------------


def test_apply_names_no_duplicate_on_same_name():
    """Applying same FR name twice: no duplicate added, no conflict (exact match)."""
    # First apply
    result1 = apply_names(_TAXA_NO_FR, _CSV_ROWS_GOOD)
    patched = result1["patched_taxa"]
    # Second apply on already-patched taxa
    result2 = apply_names(patched, _CSV_ROWS_GOOD)
    # All existing, so 0 added, but same name → no conflict either (exact match skipped)
    assert result2["fr_added_count"] == 0
    assert len(result2["conflicts"]) == 0
