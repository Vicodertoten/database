from __future__ import annotations

from scripts.phase2b_distractor_relationships import build_palier_a_relationships


def test_build_palier_a_relationships_imports_only_safe_canonical_records() -> None:
    records = [
        {
            "relationship_id": "dr:canonical",
            "target_canonical_taxon_id": "taxon:birds:000001",
            "target_scientific_name": "Columba palumbus",
            "candidate_taxon_ref_type": "canonical_taxon",
            "candidate_taxon_ref_id": "taxon:birds:000079",
            "candidate_scientific_name": "Streptopelia decaocto",
            "source": "inaturalist_similar_species",
            "source_rank": 1,
            "confusion_types": ["visual_similarity"],
            "pedagogical_value": "high",
            "difficulty_level": "medium",
            "learner_level": "mixed",
            "status": "candidate",
            "created_at": "2026-05-05T11:54:53.572537+00:00",
        },
        {
            "relationship_id": "dr:unresolved",
            "target_canonical_taxon_id": "taxon:birds:000001",
            "target_scientific_name": "Columba palumbus",
            "candidate_taxon_ref_type": "unresolved_taxon",
            "candidate_taxon_ref_id": None,
            "candidate_scientific_name": "Columba livia",
            "source": "inaturalist_similar_species",
            "source_rank": 2,
            "confusion_types": ["visual_similarity"],
            "pedagogical_value": "high",
            "difficulty_level": "medium",
            "learner_level": "mixed",
            "status": "needs_review",
            "created_at": "2026-05-05T11:54:53.572537+00:00",
        },
    ]

    relationships, summary = build_palier_a_relationships(
        records=records,
        canonical_taxon_ids={"taxon:birds:000001", "taxon:birds:000079"},
    )

    assert len(relationships) == 1
    assert relationships[0].status == "validated"
    assert summary["non_canonical_records"] == 1
    assert summary["skipped_counts"] == {"skipped_unresolved_taxon": 1}


def test_build_palier_a_relationships_rejects_unsafe_canonical_records() -> None:
    records = [
        {
            "relationship_id": "dr:missing-candidate",
            "target_canonical_taxon_id": "taxon:birds:000001",
            "target_scientific_name": "Columba palumbus",
            "candidate_taxon_ref_type": "canonical_taxon",
            "candidate_taxon_ref_id": "taxon:birds:999999",
            "candidate_scientific_name": "Missing species",
            "source": "taxonomic_neighbor_same_family",
            "source_rank": 1,
            "confusion_types": ["same_family"],
            "pedagogical_value": "medium",
            "difficulty_level": "medium",
            "learner_level": "mixed",
            "status": "candidate",
            "created_at": "2026-05-05T11:54:53.572537+00:00",
        },
        {
            "relationship_id": "dr:no-confusion",
            "target_canonical_taxon_id": "taxon:birds:000001",
            "target_scientific_name": "Columba palumbus",
            "candidate_taxon_ref_type": "canonical_taxon",
            "candidate_taxon_ref_id": "taxon:birds:000079",
            "candidate_scientific_name": "Streptopelia decaocto",
            "source": "inaturalist_similar_species",
            "source_rank": 1,
            "confusion_types": [],
            "pedagogical_value": "high",
            "difficulty_level": "medium",
            "learner_level": "mixed",
            "status": "candidate",
            "created_at": "2026-05-05T11:54:53.572537+00:00",
        },
    ]

    relationships, summary = build_palier_a_relationships(
        records=records,
        canonical_taxon_ids={"taxon:birds:000001", "taxon:birds:000079"},
    )

    assert relationships == []
    assert summary["skipped_counts"] == {
        "missing_candidate_canonical_taxon": 1,
        "missing_confusion_types": 1,
    }
