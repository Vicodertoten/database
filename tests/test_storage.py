import json
from datetime import UTC, datetime

import pytest

from database_core.domain.enums import SourceName
from database_core.domain.models import (
    CanonicalTaxon,
    ExternalMapping,
    GeoPoint,
    LocationMetadata,
    MediaAsset,
    PlayableItem,
    ProvenanceSummary,
    QualifiedResource,
    SourceObservation,
    SourceQualityMetadata,
)
from database_core.playable import validate_playable_corpus
from database_core.storage.postgres import (
    PostgresRepository,
    RepositorySchemaVersionMismatchError,
)


def test_initialize_rejects_legacy_schema_version_without_explicit_reset(
    database_url: str,
) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()

    with repository.connect() as connection:
        connection.execute("DELETE FROM schema_migrations")
        connection.execute("INSERT INTO schema_migrations (version) VALUES (1)")

    with pytest.raises(RepositorySchemaVersionMismatchError):
        repository.initialize()


def test_initialize_can_reset_legacy_schema_version_with_explicit_flag(
    database_url: str,
) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()

    with repository.connect() as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS legacy_table (id INTEGER PRIMARY KEY)")
        connection.execute("DELETE FROM schema_migrations")
        connection.execute("INSERT INTO schema_migrations (version) VALUES (1)")

    repository.initialize(allow_schema_reset=True)

    with repository.connect() as connection:
        table_names = {
            row["tablename"]
            for row in connection.execute(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = current_schema()
                """
            ).fetchall()
        }
        user_version = int(
            connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations"
            ).fetchone()["version"]
        )

    assert "legacy_table" not in table_names
    assert user_version == 9


def test_migrate_to_latest_initializes_v9_schema(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    applied_versions = repository.migrate_to_latest()
    assert applied_versions == (8, 9)
    assert repository.current_schema_version() == 9


def test_geospatial_queries_support_bbox_and_point_radius(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    repository.save_source_observations(
        [
            SourceObservation(
                observation_uid="obs:inaturalist:geo-1",
                source_name=SourceName.INATURALIST,
                source_observation_id="geo-1",
                source_taxon_id="12716",
                observed_at=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
                location=LocationMetadata(
                    place_name="Brussels",
                    latitude=50.8503,
                    longitude=4.3517,
                    country_code="BE",
                ),
                source_quality=SourceQualityMetadata(
                    quality_grade="research",
                    research_grade=True,
                    observation_license="CC-BY",
                    captive=False,
                ),
                raw_payload_ref="fixture://geo/1",
                canonical_taxon_id=None,
            )
        ]
    )

    bbox_rows = repository.fetch_source_observations_in_bbox(
        min_longitude=4.0,
        min_latitude=50.7,
        max_longitude=4.6,
        max_latitude=51.0,
    )
    radius_rows = repository.fetch_source_observations_within_radius(
        longitude=4.3517,
        latitude=50.8503,
        radius_meters=500.0,
    )

    assert [row["source_observation_id"] for row in bbox_rows] == ["geo-1"]
    assert [row["source_observation_id"] for row in radius_rows] == ["geo-1"]


def test_append_run_history_creates_governance_review_queue_item_for_ambiguous_transition(
    database_url: str,
) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()

    first_run_id = "run:20260408T000000Z:aaaaaaaa"
    second_run_id = "run:20260408T000100Z:bbbbbbbb"
    captured_at = datetime(2026, 4, 8, 0, 0, tzinfo=UTC)

    previous_taxa = [
        _canonical_taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Alauda arvensis",
        )
    ]
    current_taxa = [
        _canonical_taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Alauda arvensis",
            taxon_status="deprecated",
            split_into=["taxon:birds:999999"],
        )
    ]

    with repository.connect() as connection:
        repository.start_pipeline_run(
            run_id=first_run_id,
            source_mode="fixture",
            dataset_id="fixture:baseline",
            snapshot_id=None,
            started_at=captured_at,
            connection=connection,
        )
        repository.append_run_history(
            run_id=first_run_id,
            governance_effective_at=captured_at,
            canonical_taxa=previous_taxa,
            observations=[],
            media_assets=[],
            qualified_resources=[],
            review_items=[],
            connection=connection,
        )
        repository.complete_pipeline_run(
            run_id=first_run_id,
            completed_at=captured_at,
            connection=connection,
        )

        repository.start_pipeline_run(
            run_id=second_run_id,
            source_mode="fixture",
            dataset_id="fixture:changed",
            snapshot_id=None,
            started_at=captured_at,
            connection=connection,
        )
        repository.append_run_history(
            run_id=second_run_id,
            governance_effective_at=captured_at,
            canonical_taxa=current_taxa,
            observations=[],
            media_assets=[],
            qualified_resources=[],
            review_items=[],
            connection=connection,
        )
        repository.complete_pipeline_run(
            run_id=second_run_id,
            completed_at=captured_at,
            connection=connection,
        )

    rows = repository.fetch_canonical_governance_review_queue(run_id=second_run_id)
    assert len(rows) == 1
    assert rows[0]["reason_code"] == "ambiguous_transition_missing_target"
    assert rows[0]["review_status"] == "open"


def test_append_run_history_routes_ambiguous_mapping_conflicts_to_governance_review_queue(
    database_url: str,
) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()

    first_run_id = "run:20260408T000000Z:aaaaaaaa"
    second_run_id = "run:20260408T000100Z:bbbbbbbb"
    captured_at = datetime(2026, 4, 8, 0, 0, tzinfo=UTC)

    previous_taxa = [
        _canonical_taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
            external_source_mappings=[("inaturalist", "12716")],
        )
    ]
    current_taxa = [
        _canonical_taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
            external_source_mappings=[("inaturalist", "12716")],
        ),
        _canonical_taxon(
            canonical_taxon_id="taxon:birds:000002",
            name="Parus major duplicate",
            external_source_mappings=[("inaturalist", "12716")],
        ),
    ]

    with repository.connect() as connection:
        repository.start_pipeline_run(
            run_id=first_run_id,
            source_mode="fixture",
            dataset_id="fixture:baseline",
            snapshot_id=None,
            started_at=captured_at,
            connection=connection,
        )
        repository.append_run_history(
            run_id=first_run_id,
            governance_effective_at=captured_at,
            canonical_taxa=previous_taxa,
            observations=[],
            media_assets=[],
            qualified_resources=[],
            review_items=[],
            connection=connection,
        )
        repository.complete_pipeline_run(
            run_id=first_run_id,
            completed_at=captured_at,
            connection=connection,
        )

        repository.start_pipeline_run(
            run_id=second_run_id,
            source_mode="fixture",
            dataset_id="fixture:changed",
            snapshot_id=None,
            started_at=captured_at,
            connection=connection,
        )
        repository.append_run_history(
            run_id=second_run_id,
            governance_effective_at=captured_at,
            canonical_taxa=current_taxa,
            observations=[],
            media_assets=[],
            qualified_resources=[],
            review_items=[],
            connection=connection,
        )
        repository.complete_pipeline_run(
            run_id=second_run_id,
            completed_at=captured_at,
            connection=connection,
        )

    rows = repository.fetch_canonical_governance_review_queue(run_id=second_run_id)
    assert len(rows) == 2
    assert {row["reason_code"] for row in rows} == {"ambiguous_source_mapping_conflict"}
    assert {row["review_status"] for row in rows} == {"open"}


def test_state_change_and_governance_logs_are_separated(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()

    run_1 = "run:20260408T000000Z:aaaaaaaa"
    run_2 = "run:20260408T000100Z:bbbbbbbb"
    run_3 = "run:20260408T000200Z:cccccccc"
    captured_at = datetime(2026, 4, 8, 0, 0, tzinfo=UTC)
    base_taxa = [
        _canonical_taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
        )
    ]
    changed_taxa = [
        _canonical_taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major updated",
        )
    ]

    with repository.connect() as connection:
        for run_id, taxa in ((run_1, base_taxa), (run_2, base_taxa), (run_3, changed_taxa)):
            repository.start_pipeline_run(
                run_id=run_id,
                source_mode="fixture",
                dataset_id=f"fixture:{run_id}",
                snapshot_id=None,
                started_at=captured_at,
                connection=connection,
            )
            repository.save_canonical_taxa(
                taxa,
                run_id=run_id,
                connection=connection,
            )
            repository.append_run_history(
                run_id=run_id,
                governance_effective_at=captured_at,
                canonical_taxa=taxa,
                observations=[],
                media_assets=[],
                qualified_resources=[],
                review_items=[],
                connection=connection,
            )
            repository.complete_pipeline_run(
                run_id=run_id,
                completed_at=captured_at,
                connection=connection,
            )

    state_run_2 = repository.fetch_canonical_state_events(run_id=run_2, limit=50)
    change_run_2 = repository.fetch_canonical_change_events(run_id=run_2, limit=50)
    governance_run_2 = repository.fetch_canonical_governance_events(run_id=run_2, limit=50)
    assert len(state_run_2) == 1
    assert change_run_2 == []
    assert governance_run_2 == []

    change_run_3 = repository.fetch_canonical_change_events(run_id=run_3, limit=50)
    governance_run_3 = repository.fetch_canonical_governance_events(run_id=run_3, limit=50)
    assert len(change_run_3) >= 1
    assert len(governance_run_3) >= 1
    assert "source_delta" in json.loads(str(change_run_3[0]["payload_json"]))
    assert "source_delta" in json.loads(str(governance_run_3[0]["payload_json"]))


def test_governance_review_item_can_be_resolved_with_audit_metadata(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()

    first_run_id = "run:20260408T000000Z:aaaaaaaa"
    second_run_id = "run:20260408T000100Z:bbbbbbbb"
    captured_at = datetime(2026, 4, 8, 0, 0, tzinfo=UTC)
    previous_taxa = [_canonical_taxon(canonical_taxon_id="taxon:birds:000001", name="Parus major")]
    current_taxa = [
        _canonical_taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
            split_into=["taxon:birds:999999"],
            taxon_status="deprecated",
        )
    ]

    with repository.connect() as connection:
        repository.start_pipeline_run(
            run_id=first_run_id,
            source_mode="fixture",
            dataset_id="fixture:baseline",
            snapshot_id=None,
            started_at=captured_at,
            connection=connection,
        )
        repository.append_run_history(
            run_id=first_run_id,
            governance_effective_at=captured_at,
            canonical_taxa=previous_taxa,
            observations=[],
            media_assets=[],
            qualified_resources=[],
            review_items=[],
            connection=connection,
        )
        repository.complete_pipeline_run(
            run_id=first_run_id,
            completed_at=captured_at,
            connection=connection,
        )

        repository.start_pipeline_run(
            run_id=second_run_id,
            source_mode="fixture",
            dataset_id="fixture:changed",
            snapshot_id=None,
            started_at=captured_at,
            connection=connection,
        )
        repository.append_run_history(
            run_id=second_run_id,
            governance_effective_at=captured_at,
            canonical_taxa=current_taxa,
            observations=[],
            media_assets=[],
            qualified_resources=[],
            review_items=[],
            connection=connection,
        )
        repository.complete_pipeline_run(
            run_id=second_run_id,
            completed_at=captured_at,
            connection=connection,
        )

    queue_rows = repository.fetch_canonical_governance_review_queue(run_id=second_run_id)
    assert len(queue_rows) == 1
    item_id = str(queue_rows[0]["governance_review_item_id"])

    updated = repository.resolve_canonical_governance_review_item(
        governance_review_item_id=item_id,
        resolved_note="Reviewed against source delta and accepted.",
        resolved_by="operator:test",
    )
    assert updated["review_status"] == "closed"
    assert updated["resolved_note"] == "Reviewed against source delta and accepted."
    assert updated["resolved_by"] == "operator:test"
    assert updated["resolved_at"] is not None

    backlog = repository.fetch_canonical_governance_review_backlog(run_id=second_run_id)
    assert backlog["open_count"] == 0
    assert backlog["resolved_count"] == 1
    assert backlog["resolved_by_reason"] == {"ambiguous_transition_missing_target": 1}


def test_governance_review_resolution_requires_non_blank_note(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()

    with pytest.raises(ValueError, match="resolved_note must not be blank"):
        repository.resolve_canonical_governance_review_item(
            governance_review_item_id="cgr:run:demo:event:1",
            resolved_note="  ",
            resolved_by="operator:test",
        )


def test_playable_items_persist_and_support_filters(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    captured_at = datetime(2026, 4, 8, 0, 0, tzinfo=UTC)
    run_id = "run:20260408T000000Z:aaaaaaaa"

    with repository.connect() as connection:
        repository.start_pipeline_run(
            run_id=run_id,
            source_mode="fixture",
            dataset_id="fixture:playable",
            snapshot_id=None,
            started_at=captured_at,
            connection=connection,
        )
        repository.save_canonical_taxa(
            [_canonical_taxon(canonical_taxon_id="taxon:birds:000001", name="Parus major")],
            run_id=run_id,
            connection=connection,
        )
        repository.save_source_observations(
            [
                SourceObservation(
                    observation_uid="obs:inaturalist:playable-1",
                    source_name=SourceName.INATURALIST,
                    source_observation_id="playable-1",
                    source_taxon_id="12716",
                    observed_at=captured_at,
                    location=LocationMetadata(
                        place_name="Brussels",
                        latitude=50.8503,
                        longitude=4.3517,
                        country_code="BE",
                    ),
                    source_quality=SourceQualityMetadata(
                        quality_grade="research",
                        research_grade=True,
                        observation_license="CC-BY",
                        captive=False,
                    ),
                    raw_payload_ref="fixture://playable/1",
                    canonical_taxon_id="taxon:birds:000001",
                )
            ],
            connection=connection,
        )
        repository.save_media_assets(
            [
                _media_asset(
                    media_id="media:inaturalist:playable-1",
                    source_media_id="playable-1",
                    source_observation_uid="obs:inaturalist:playable-1",
                    canonical_taxon_id="taxon:birds:000001",
                )
            ],
            connection=connection,
        )
        repository.save_qualified_resources(
            [
                _qualified_resource(
                    qualified_resource_id="qr:media:inaturalist:playable-1",
                    media_asset_id="media:inaturalist:playable-1",
                    source_observation_uid="obs:inaturalist:playable-1",
                    source_observation_id="playable-1",
                    canonical_taxon_id="taxon:birds:000001",
                )
            ],
            connection=connection,
        )
        playable_item = _playable_item(
            run_id=run_id,
            qualified_resource_id="qr:media:inaturalist:playable-1",
            canonical_taxon_id="taxon:birds:000001",
            media_asset_id="media:inaturalist:playable-1",
            source_observation_uid="obs:inaturalist:playable-1",
            source_observation_id="playable-1",
            source_media_id="playable-1",
        )
        repository.save_playable_items([playable_item], connection=connection)
        repository.append_run_history(
            run_id=run_id,
            governance_effective_at=captured_at,
            canonical_taxa=[],
            observations=[],
            media_assets=[],
            qualified_resources=[],
            review_items=[],
            playable_items=[playable_item],
            connection=connection,
        )
        repository.complete_pipeline_run(
            run_id=run_id,
            completed_at=captured_at,
            connection=connection,
        )

    rows = repository.fetch_playable_corpus(
        canonical_taxon_id="taxon:birds:000001",
        country_code="BE",
        difficulty_level="easy",
        media_role="primary_id",
        learning_suitability="high",
        confusion_relevance="medium",
        observed_from=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
        observed_to=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
        bbox=(4.0, 50.7, 4.6, 51.0),
        point_radius=(4.3517, 50.8503, 500.0),
        limit=10,
    )
    assert len(rows) == 1
    assert rows[0]["playable_item_id"] == "playable:qr:media:inaturalist:playable-1"
    assert rows[0]["common_names_i18n"]["en"] == ["Great Tit"]
    assert rows[0]["common_names_i18n"]["fr"] == []
    assert rows[0]["common_names_i18n"]["nl"] == []

    payload = repository.fetch_playable_corpus_payload(limit=10)
    validate_playable_corpus(payload)
    assert payload["playable_corpus_version"] == "playable_corpus.v1"
    assert len(payload["items"]) == 1


def _canonical_taxon(
    *,
    canonical_taxon_id: str,
    name: str,
    taxon_status: str = "active",
    authority_source: str = "inaturalist",
    external_source_mappings: list[tuple[str, str]] | None = None,
    split_into: list[str] | None = None,
) -> CanonicalTaxon:
    return CanonicalTaxon(
        canonical_taxon_id=canonical_taxon_id,
        accepted_scientific_name=name,
        canonical_rank="species",
        taxon_group="birds",
        taxon_status=taxon_status,
        authority_source=authority_source,
        display_slug=name.lower().replace(" ", "-"),
        synonyms=[],
        common_names=[],
        key_identification_features=[],
        source_enrichment_status="seeded",
        bird_scope_compatible=True,
        external_source_mappings=[
            ExternalMapping(source_name=source_name, external_id=external_id)
            for source_name, external_id in (external_source_mappings or [])
        ],
        external_similarity_hints=[],
        similar_taxa=[],
        similar_taxon_ids=[],
        split_into=split_into or [],
        merged_into=None,
        replaced_by=None,
        derived_from=None,
    )


def _playable_item(
    *,
    run_id: str,
    qualified_resource_id: str,
    canonical_taxon_id: str,
    media_asset_id: str,
    source_observation_uid: str,
    source_observation_id: str,
    source_media_id: str,
) -> PlayableItem:
    return PlayableItem(
        playable_item_id=f"playable:{qualified_resource_id}",
        run_id=run_id,
        qualified_resource_id=qualified_resource_id,
        canonical_taxon_id=canonical_taxon_id,
        media_asset_id=media_asset_id,
        source_observation_uid=source_observation_uid,
        source_name=SourceName.INATURALIST,
        source_observation_id=source_observation_id,
        source_media_id=source_media_id,
        scientific_name="Parus major",
        common_names_i18n={"fr": [], "en": ["Great Tit"], "nl": []},
        difficulty_level="easy",
        media_role="primary_id",
        learning_suitability="high",
        confusion_relevance="medium",
        diagnostic_feature_visibility="high",
        similar_taxon_ids=[],
        what_to_look_at_specific=["head"],
        what_to_look_at_general=["black head", "white cheeks"],
        confusion_hint=None,
        country_code="BE",
        observed_at=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
        location_point=GeoPoint(longitude=4.3517, latitude=50.8503),
        location_bbox=None,
        location_radius_meters=None,
    )


def _media_asset(
    *,
    media_id: str,
    source_media_id: str,
    source_observation_uid: str,
    canonical_taxon_id: str,
):
    return MediaAsset(
        media_id=media_id,
        source_name=SourceName.INATURALIST,
        source_media_id=source_media_id,
        media_type="image",
        source_url="https://example.test/image.jpg",
        attribution="test",
        author="test",
        license="CC-BY",
        mime_type="image/jpeg",
        file_extension="jpg",
        width=1600,
        height=1200,
        checksum=None,
        source_observation_uid=source_observation_uid,
        canonical_taxon_id=canonical_taxon_id,
        raw_payload_ref="fixture://media",
    )


def _qualified_resource(
    *,
    qualified_resource_id: str,
    media_asset_id: str,
    source_observation_uid: str,
    source_observation_id: str,
    canonical_taxon_id: str,
):
    return QualifiedResource(
        qualified_resource_id=qualified_resource_id,
        canonical_taxon_id=canonical_taxon_id,
        source_observation_uid=source_observation_uid,
        source_observation_id=source_observation_id,
        media_asset_id=media_asset_id,
        qualification_status="accepted",
        qualification_version="qualification.staged.v1",
        technical_quality="high",
        pedagogical_quality="high",
        life_stage="adult",
        sex="unknown",
        visible_parts=["head"],
        view_angle="lateral",
        difficulty_level="easy",
        media_role="primary_id",
        confusion_relevance="medium",
        diagnostic_feature_visibility="high",
        learning_suitability="high",
        uncertainty_reason="none",
        qualification_notes=None,
        qualification_flags=[],
        provenance_summary=ProvenanceSummary(
            source_name=SourceName.INATURALIST,
            source_observation_key="inaturalist::playable-1",
            source_media_key="inaturalist::playable-1",
            source_observation_id=source_observation_id,
            source_media_id="playable-1",
            raw_payload_ref="fixture://media",
            run_id="run:fixture",
            observation_license="CC-BY",
            media_license="CC-BY",
            qualification_method="fixture",
            ai_model="fixture-ai",
            ai_prompt_version="phase1.inat.image.v2",
            ai_task_name="expert_qualification",
            ai_status="ok",
        ),
        license_safety_result="safe",
        export_eligible=True,
        ai_confidence=0.95,
    )
