from __future__ import annotations

import pytest

from database_core.dynamic_pack import validate_serving_bundle
from database_core.ops.phase2b_serving_bundle import (
    audit_serving_bundle_v1,
    build_serving_bundle_v1,
)
from database_core.versioning import SERVING_BUNDLE_VERSION
from tests.test_phase2b_session_snapshot import (
    _pool,
    _relationships_by_target,
    _taxonomy_profiles,
)


def test_serving_bundle_v1_validates_synthetic_pool() -> None:
    bundle = build_serving_bundle_v1(
        pool=_pool(),
        relationships_by_target=_relationships_by_target(),
        taxonomy_profiles=_taxonomy_profiles(),
    )

    validate_serving_bundle(bundle)
    assert bundle["serving_bundle_version"] == SERVING_BUNDLE_VERSION
    assert bundle["pool_id"] == "pack-pool:test"
    assert bundle["metrics"]["item_count"] == 50
    assert bundle["metrics"]["taxon_count"] == 50
    assert bundle["metrics"]["fallback_ready_taxon_count"] == 50
    assert all(
        relationship["status"] == "validated"
        and relationship["candidate_taxon_ref_type"] == "canonical_taxon"
        for relationship in bundle["relationships"]
    )


def test_serving_bundle_audit_warns_when_relationships_need_fallback() -> None:
    bundle = build_serving_bundle_v1(
        pool=_pool(),
        relationships_by_target={},
        taxonomy_profiles=_taxonomy_profiles(),
    )
    report = audit_serving_bundle_v1(bundle)

    assert report["status"] == "GO_WITH_WARNINGS"
    assert report["blockers"] == []
    assert report["warnings"] == ["taxonomic_fallback_db_required"]


def test_serving_bundle_contract_rejects_missing_locale_label() -> None:
    pool = _pool()
    pool["items"][0]["labels"]["nl"] = ""

    with pytest.raises(ValueError, match="Serving bundle validation failed"):
        build_serving_bundle_v1(
            pool=pool,
            relationships_by_target=_relationships_by_target(),
            taxonomy_profiles=_taxonomy_profiles(),
        )
