from __future__ import annotations

import pytest

from database_core.dynamic_pack import validate_pack_pool, validate_session_snapshot
from database_core.ops.phase2a_dynamic_pack import (
    PHASE2A_DEFAULT_QUESTION_COUNT,
    _build_pool_metrics,
    build_session_snapshot,
)
from database_core.storage.dynamic_pack_store import PostgresDynamicPackStore
from database_core.versioning import (
    PACK_POOL_VERSION,
    SCHEMA_VERSION_LABEL,
    SESSION_SNAPSHOT_VERSION,
)


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


def _pack_pool(*, items: list[dict[str, object]] | None = None) -> dict[str, object]:
    resolved_items = items or [_pool_item(index) for index in range(1, 51)]
    return {
        "schema_version": SCHEMA_VERSION_LABEL,
        "pack_pool_version": PACK_POOL_VERSION,
        "pool_id": "pack-pool:test",
        "generated_at": "2026-05-09T12:00:00+00:00",
        "source_run_id": "run:test",
        "scope": {
            "product_scope": "be_fr_birds_50",
            "country_codes": ["BE", "FR"],
            "locale_policy": "fallback_allowed_internal",
        },
        "metrics": _build_pool_metrics(resolved_items),
        "items": resolved_items,
    }


def test_pack_pool_v1_validates_and_rejects_missing_media_url() -> None:
    pool = _pack_pool()
    validate_pack_pool(pool)

    invalid = _pack_pool()
    invalid["items"][0]["media"]["render_url"] = ""

    with pytest.raises(ValueError, match="render_url"):
        validate_pack_pool(invalid)


def test_session_snapshot_v1_validates_deferred_options() -> None:
    session = build_session_snapshot(
        pool=_pack_pool(),
        locale="fr",
        seed="seed",
        question_count=PHASE2A_DEFAULT_QUESTION_COUNT,
    )

    validate_session_snapshot(session)
    assert session["session_snapshot_version"] == SESSION_SNAPSHOT_VERSION
    assert session["question_count"] == 20
    assert len(session["questions"]) == 20
    assert all(question["options"] == [] for question in session["questions"])
    assert {
        question["option_generation"]["status"] for question in session["questions"]
    } == {"deferred_phase3"}


def test_session_selection_is_deterministic_and_uses_one_question_per_taxon() -> None:
    pool = _pack_pool()

    first = build_session_snapshot(pool=pool, locale="en", seed="same", question_count=20)
    second = build_session_snapshot(pool=pool, locale="en", seed="same", question_count=20)

    assert first["questions"] == second["questions"]
    taxon_ids = [question["canonical_taxon_id"] for question in first["questions"]]
    assert len(taxon_ids) == len(set(taxon_ids))


def test_session_selection_errors_when_pool_has_too_few_taxa() -> None:
    pool = _pack_pool(
        items=[
            _pool_item(index, taxon_id=f"taxon:birds:{(index % 2) + 1:06d}")
            for index in range(1, 8)
        ]
    )

    with pytest.raises(ValueError, match="enough distinct taxa"):
        build_session_snapshot(pool=pool, locale="nl", seed="seed", question_count=3)


def test_locale_fallbacks_are_allowed_in_pack_pool() -> None:
    item = _pool_item(1)
    item["labels"]["fr"] = "Species 1"
    item["label_sources"]["fr"] = "scientific_name"
    pool = _pack_pool(items=[item])

    validate_pack_pool(pool)
    assert pool["metrics"]["locale_label_fallback_counts"]["fr"] == 1


class _FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...] = ()) -> None:
        self.calls.append((query, params))


def test_dynamic_pack_store_saves_pack_pool_and_session_snapshot() -> None:
    connection = _FakeConnection()
    store = PostgresDynamicPackStore(connect=lambda: None)
    pool = _pack_pool()
    session = build_session_snapshot(pool=pool, locale="fr", seed="seed", question_count=20)

    store.save_pack_pool(pool, connection=connection)
    store.save_session_snapshot(session, connection=connection)

    assert "INSERT INTO pack_pools" in connection.calls[0][0]
    assert connection.calls[0][1][0] == "pack-pool:test"
    assert "INSERT INTO session_snapshots" in connection.calls[1][0]
    assert connection.calls[1][1][0] == session["session_snapshot_id"]
