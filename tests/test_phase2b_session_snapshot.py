from __future__ import annotations

from datetime import UTC, datetime

import pytest

from database_core.domain.models import DistractorRelationship
from database_core.dynamic_pack import validate_session_snapshot
from database_core.ops.phase2b_session_snapshot import (
    PHASE2B_QUESTION_COUNT,
    build_session_snapshot_v2,
    validate_session_snapshot_v2_invariants,
)
from database_core.versioning import SCHEMA_VERSION_LABEL, SESSION_SNAPSHOT_V2_VERSION


def _pool_item(index: int, *, taxon_id: str | None = None) -> dict[str, object]:
    resolved_taxon_id = taxon_id or f"taxon:birds:{index:06d}"
    return {
        "playable_item_id": f"playable:{index:06d}",
        "qualified_resource_id": f"qualified:{index:06d}",
        "canonical_taxon_id": resolved_taxon_id,
        "media_asset_id": f"media:{index:06d}",
        "scientific_name": f"Species {index}",
        "labels": {
            "fr": f"Nom {index}",
            "en": f"Name {index}",
            "nl": f"Soort {index}",
        },
        "label_sources": {
            "fr": "common_name",
            "en": "common_name",
            "nl": "common_name",
        },
        "difficulty_level": "easy",
        "media_role": "primary_id",
        "learning_suitability": "high",
        "diagnostic_feature_visibility": "high",
        "feedback_short": "Look at the visible field mark.",
        "media": {
            "render_url": f"https://example.test/{index}.jpg",
            "attribution": f"Author {index}",
            "license": "CC-BY",
        },
        "country_code": "BE" if index % 2 else "FR",
    }


def _pool() -> dict[str, object]:
    items = [_pool_item(index) for index in range(1, 51)]
    return {
        "schema_version": SCHEMA_VERSION_LABEL,
        "pack_pool_version": "pack_pool.v1",
        "pool_id": "pack-pool:test",
        "generated_at": "2026-05-09T12:00:00+00:00",
        "source_run_id": "run:test",
        "scope": {
            "product_scope": "be_fr_birds_50",
            "country_codes": ["BE", "FR"],
            "locale_policy": "fallback_allowed_internal",
        },
        "metrics": {
            "item_count": len(items),
            "taxon_count": 50,
            "country_counts": {"BE": 25, "FR": 25},
            "min_items_per_taxon": 1,
            "taxa_with_at_least_20_items": 0,
            "items_per_taxon": {str(item["canonical_taxon_id"]): 1 for item in items},
            "attribution_completeness": 1.0,
            "media_url_completeness": 1.0,
            "locale_label_completeness": {"fr": 1.0, "en": 1.0, "nl": 1.0},
            "locale_label_common_name_counts": {"fr": 50, "en": 50, "nl": 50},
            "locale_label_fallback_counts": {"fr": 0, "en": 0, "nl": 0},
        },
        "items": items,
    }


def _relationship(target: int, candidate: int, *, source_rank: int = 1) -> DistractorRelationship:
    return DistractorRelationship(
        relationship_id=f"dr:{target}:{candidate}",
        target_canonical_taxon_id=f"taxon:birds:{target:06d}",
        target_scientific_name=f"Species {target}",
        candidate_taxon_ref_type="canonical_taxon",
        candidate_taxon_ref_id=f"taxon:birds:{candidate:06d}",
        candidate_scientific_name=f"Species {candidate}",
        source="inaturalist_similar_species",
        source_rank=source_rank,
        confusion_types=["visual_similarity"],
        pedagogical_value="high",
        difficulty_level="medium",
        learner_level="mixed",
        status="validated",
        created_at=datetime(2026, 5, 9, tzinfo=UTC),
    )


def _relationships_by_target() -> dict[str, list[DistractorRelationship]]:
    return {
        f"taxon:birds:{target:06d}": [
            _relationship(target, ((target + offset - 1) % 50) + 1, source_rank=offset)
            for offset in range(1, 4)
        ]
        for target in range(1, 51)
    }


def _taxonomy_profiles() -> dict[str, dict[str, object]]:
    return {
        f"taxon:birds:{index:06d}": {
            "parent_id": str(index // 5),
            "ancestor_ids": ["root", str(index // 10), str(index // 5)],
        }
        for index in range(1, 51)
    }


def test_session_snapshot_v2_validates_and_freezes_options() -> None:
    session = build_session_snapshot_v2(
        pool=_pool(),
        locale="fr",
        seed="seed",
        question_count=PHASE2B_QUESTION_COUNT,
        relationships_by_target=_relationships_by_target(),
        taxonomy_profiles=_taxonomy_profiles(),
    )

    validate_session_snapshot(session)
    validate_session_snapshot_v2_invariants(session)
    assert session["session_snapshot_version"] == SESSION_SNAPSHOT_V2_VERSION
    assert session["question_count"] == 20
    assert len(session["questions"]) == 20
    assert all(len(question["options"]) == 4 for question in session["questions"])
    assert all(
        sum(1 for option in question["options"] if option["is_correct"]) == 1
        for question in session["questions"]
    )
    assert all(
        option["referenced_only"] is False
        for question in session["questions"]
        for option in question["options"]
    )


def test_session_snapshot_v2_is_deterministic_for_same_seed() -> None:
    kwargs = {
        "pool": _pool(),
        "locale": "en",
        "seed": "same",
        "question_count": PHASE2B_QUESTION_COUNT,
        "relationships_by_target": _relationships_by_target(),
        "taxonomy_profiles": _taxonomy_profiles(),
    }
    first = build_session_snapshot_v2(**kwargs)
    second = build_session_snapshot_v2(**kwargs)

    assert first["session_snapshot_id"] == second["session_snapshot_id"]
    assert first["questions"] == second["questions"]


def test_session_snapshot_v2_uses_traced_fallback_when_relationships_are_sparse() -> None:
    session = build_session_snapshot_v2(
        pool=_pool(),
        locale="nl",
        seed="seed",
        question_count=PHASE2B_QUESTION_COUNT,
        relationships_by_target={},
        taxonomy_profiles=_taxonomy_profiles(),
    )

    fallback_options = [
        option
        for question in session["questions"]
        for option in question["options"]
        if option["source"] == "taxonomic_fallback_db"
    ]
    assert fallback_options
    assert all("palier_a_fallback" in option["reason_codes"] for option in fallback_options)
    validate_session_snapshot_v2_invariants(session)


def test_session_snapshot_v2_invariants_reject_referenced_only_option() -> None:
    session = build_session_snapshot_v2(
        pool=_pool(),
        locale="fr",
        seed="seed",
        question_count=PHASE2B_QUESTION_COUNT,
        relationships_by_target=_relationships_by_target(),
        taxonomy_profiles=_taxonomy_profiles(),
    )
    session["questions"][0]["options"][0]["referenced_only"] = True

    with pytest.raises(ValueError, match="referenced_only"):
        validate_session_snapshot_v2_invariants(session)
