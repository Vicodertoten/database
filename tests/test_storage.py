import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from database_core.domain.enums import SourceName
from database_core.domain.models import (
    CanonicalTaxon,
    ExternalMapping,
    GeoPoint,
    LocationMetadata,
    MediaAsset,
    PackRevisionParameters,
    PlayableItem,
    ProvenanceSummary,
    QualifiedResource,
    SourceObservation,
    SourceQualityMetadata,
)
from database_core.pack import (
    validate_compiled_pack,
    validate_pack_diagnostic,
    validate_pack_materialization,
    validate_pack_spec,
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
    assert user_version == 13


def test_migrate_to_latest_initializes_v13_schema(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    applied_versions = repository.migrate_to_latest()
    assert applied_versions == (8, 9, 10, 11, 12, 13)
    assert repository.current_schema_version() == 13


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


def test_pack_creation_persists_non_compilable_pack_with_diagnostic(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()

    payload = repository.create_pack(
        parameters={
            "canonical_taxon_ids": ["taxon:birds:000001", "taxon:birds:000002"],
            "difficulty_policy": "balanced",
            "country_code": "BE",
            "location_bbox": None,
            "location_point": None,
            "location_radius_meters": None,
            "observed_from": None,
            "observed_to": None,
            "owner_id": "owner:demo",
            "org_id": "org:demo",
            "visibility": "private",
            "intended_use": "quiz",
        }
    )
    validate_pack_spec(payload)
    assert payload["revision"] == 1
    assert payload["latest_revision"] == 1

    diagnostic = repository.diagnose_pack(pack_id=str(payload["pack_id"]))
    validate_pack_diagnostic(diagnostic)
    assert diagnostic["compilable"] is False
    assert diagnostic["reason_code"] == "no_playable_items"
    assert diagnostic["measured"]["requested_taxa_count"] == 2
    assert diagnostic["measured"]["total_playable_items"] == 0
    assert len(diagnostic["blocking_taxa"]) == 2
    assert {item["code"] for item in diagnostic["deficits"]} == {
        "min_taxa_served",
        "min_media_per_taxon",
        "min_total_questions",
    }

    specs = repository.fetch_pack_specs(pack_id=str(payload["pack_id"]))
    diagnostics = repository.fetch_pack_diagnostics(pack_id=str(payload["pack_id"]))
    assert len(specs) == 1
    assert len(diagnostics) == 1


def test_pack_revision_increments_monotonically(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()

    initial = repository.create_pack(
        parameters={
            "canonical_taxon_ids": ["taxon:birds:000001"],
            "difficulty_policy": "easy",
            "country_code": None,
            "location_bbox": None,
            "location_point": {"longitude": 4.35, "latitude": 50.85},
            "location_radius_meters": 5000.0,
            "observed_from": None,
            "observed_to": None,
            "owner_id": "owner:demo",
            "org_id": None,
            "visibility": "org",
            "intended_use": "practice",
        }
    )
    revised = repository.revise_pack(
        pack_id=str(initial["pack_id"]),
        parameters={
            "canonical_taxon_ids": ["taxon:birds:000001", "taxon:birds:000002"],
            "difficulty_policy": "mixed",
            "country_code": None,
            "location_bbox": None,
            "location_point": {"longitude": 4.35, "latitude": 50.85},
            "location_radius_meters": 5000.0,
            "observed_from": None,
            "observed_to": None,
            "owner_id": "owner:demo",
            "org_id": "org:demo",
            "visibility": "public",
            "intended_use": "assessment",
        },
    )

    assert initial["revision"] == 1
    assert revised["revision"] == 2
    assert revised["latest_revision"] == 2
    revisions = repository.fetch_pack_revisions(pack_id=str(initial["pack_id"]))
    assert [item["revision"] for item in revisions] == [2, 1]


def test_pack_revision_parameters_validate_geo_and_date_constraints() -> None:
    with pytest.raises(ValueError, match="at most one geo filter form can be active"):
        PackRevisionParameters(
            canonical_taxon_ids=["taxon:birds:000001"],
            difficulty_policy="easy",
            country_code="BE",
            location_bbox={
                "min_longitude": 4.0,
                "min_latitude": 50.7,
                "max_longitude": 4.6,
                "max_latitude": 51.0,
            },
            location_point=None,
            location_radius_meters=None,
            observed_from=None,
            observed_to=None,
            owner_id=None,
            org_id=None,
            visibility="private",
            intended_use="training",
        )

    with pytest.raises(ValueError, match="location_point requires location_radius_meters"):
        PackRevisionParameters(
            canonical_taxon_ids=["taxon:birds:000001"],
            difficulty_policy="easy",
            location_point={"longitude": 4.35, "latitude": 50.85},
            location_radius_meters=None,
            observed_from=None,
            observed_to=None,
            owner_id=None,
            org_id=None,
            visibility="private",
            intended_use="training",
        )

    with pytest.raises(ValueError, match="observed_from must be <= observed_to"):
        PackRevisionParameters(
            canonical_taxon_ids=["taxon:birds:000001"],
            difficulty_policy="easy",
            observed_from=datetime(2026, 4, 9, 0, 0, tzinfo=UTC),
            observed_to=datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
            owner_id=None,
            org_id=None,
            visibility="private",
            intended_use="training",
        )


def test_pack_diagnostic_is_deterministic_for_same_revision(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    payload = repository.create_pack(
        pack_id="pack:deterministic:test",
        parameters={
            "canonical_taxon_ids": ["taxon:birds:000001", "taxon:birds:000002"],
            "difficulty_policy": "hard",
            "country_code": None,
            "location_bbox": None,
            "location_point": None,
            "location_radius_meters": None,
            "observed_from": None,
            "observed_to": None,
            "owner_id": "owner:deterministic",
            "org_id": None,
            "visibility": "private",
            "intended_use": "training",
        },
    )

    first = repository.diagnose_pack(pack_id=str(payload["pack_id"]))
    second = repository.diagnose_pack(pack_id=str(payload["pack_id"]))

    assert first["reason_code"] == second["reason_code"] == "no_playable_items"
    assert first["thresholds"] == second["thresholds"]
    assert first["measured"] == second["measured"]
    assert first["deficits"] == second["deficits"]
    assert first["blocking_taxa"] == second["blocking_taxa"]


def test_pack_diagnostic_questions_possible_requires_three_distinct_distractors(
    database_url: str,
) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    canonical_taxon_ids = _seed_pack_ready_playable_items(
        repository,
        run_id="run:20260408T001000Z:qqqqqqqq",
        taxon_count=3,
        media_per_taxon=2,
    )
    payload = repository.create_pack(
        pack_id="pack:diagnostic:distractors",
        parameters={
            "canonical_taxon_ids": canonical_taxon_ids,
            "difficulty_policy": "mixed",
            "country_code": None,
            "location_bbox": None,
            "location_point": None,
            "location_radius_meters": None,
            "observed_from": None,
            "observed_to": None,
            "owner_id": "owner:diagnostic",
            "org_id": None,
            "visibility": "private",
            "intended_use": "training",
        },
    )

    diagnostic = repository.diagnose_pack(pack_id=str(payload["pack_id"]))
    assert diagnostic["measured"]["questions_possible"] == 0
    assert diagnostic["compilable"] is False


def test_compile_pack_persists_validated_payload_and_is_deterministic(
    database_url: str,
) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    canonical_taxon_ids = _seed_pack_ready_playable_items(
        repository,
        run_id="run:20260408T001100Z:rrrrrrrr",
        taxon_count=10,
        media_per_taxon=2,
    )
    payload = repository.create_pack(
        pack_id="pack:compile:deterministic",
        parameters={
            "canonical_taxon_ids": canonical_taxon_ids,
            "difficulty_policy": "easy",
            "country_code": None,
            "location_bbox": None,
            "location_point": None,
            "location_radius_meters": None,
            "observed_from": None,
            "observed_to": None,
            "owner_id": "owner:compile",
            "org_id": None,
            "visibility": "private",
            "intended_use": "training",
        },
    )

    first_build = repository.compile_pack(
        pack_id=str(payload["pack_id"]),
        question_count=20,
    )
    second_build = repository.compile_pack(
        pack_id=str(payload["pack_id"]),
        question_count=20,
    )
    validate_compiled_pack(first_build)
    validate_compiled_pack(second_build)
    assert first_build["question_count_built"] == 20
    assert second_build["question_count_built"] == 20
    assert first_build["questions"] == second_build["questions"]
    assert first_build["build_id"] != second_build["build_id"]

    builds = repository.fetch_compiled_pack_builds(
        pack_id=str(payload["pack_id"]),
        revision=1,
    )
    assert len(builds) == 2
    for build in builds:
        validate_compiled_pack(build)


def test_compile_pack_rejects_non_compilable_pack_without_persisting_build(
    database_url: str,
) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    payload = repository.create_pack(
        pack_id="pack:compile:reject",
        parameters={
            "canonical_taxon_ids": ["taxon:birds:000001", "taxon:birds:000002"],
            "difficulty_policy": "balanced",
            "country_code": "BE",
            "location_bbox": None,
            "location_point": None,
            "location_radius_meters": None,
            "observed_from": None,
            "observed_to": None,
            "owner_id": "owner:compile",
            "org_id": None,
            "visibility": "private",
            "intended_use": "training",
        },
    )

    with pytest.raises(ValueError, match="not compilable"):
        repository.compile_pack(pack_id=str(payload["pack_id"]), question_count=20)

    assert repository.fetch_compiled_pack_builds(pack_id=str(payload["pack_id"])) == []


def test_enqueue_enrichment_for_pack_creates_request_and_targets(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    payload = repository.create_pack(
        pack_id="pack:enrichment:queue-create",
        parameters={
            "canonical_taxon_ids": ["taxon:birds:000001", "taxon:birds:000002"],
            "difficulty_policy": "balanced",
            "country_code": None,
            "location_bbox": None,
            "location_point": None,
            "location_radius_meters": None,
            "observed_from": None,
            "observed_to": None,
            "owner_id": "owner:enrichment",
            "org_id": None,
            "visibility": "private",
            "intended_use": "training",
        },
    )

    result = repository.enqueue_enrichment_for_pack(pack_id=str(payload["pack_id"]))
    assert result["enqueued"] is True
    assert result["request"]["merged"] is False
    request = result["request"]["request"]
    assert request["reason_code"] == "no_playable_items"
    assert request["request_status"] == "pending"
    assert len(result["request"]["targets"]) == 2


def test_enqueue_enrichment_for_pack_merges_same_request_signature(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    payload = repository.create_pack(
        pack_id="pack:enrichment:queue-merge",
        parameters={
            "canonical_taxon_ids": ["taxon:birds:000001", "taxon:birds:000002"],
            "difficulty_policy": "balanced",
            "country_code": None,
            "location_bbox": None,
            "location_point": None,
            "location_radius_meters": None,
            "observed_from": None,
            "observed_to": None,
            "owner_id": "owner:enrichment",
            "org_id": None,
            "visibility": "private",
            "intended_use": "training",
        },
    )

    first = repository.enqueue_enrichment_for_pack(pack_id=str(payload["pack_id"]))
    second = repository.enqueue_enrichment_for_pack(pack_id=str(payload["pack_id"]))

    assert first["request"]["merged"] is False
    assert second["request"]["merged"] is True
    requests = repository.fetch_enrichment_requests(pack_id=str(payload["pack_id"]))
    assert len(requests) == 1


def test_record_enrichment_execution_updates_status_and_attempt_count(
    database_url: str,
) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    payload = repository.create_pack(
        pack_id="pack:enrichment:execution-status",
        parameters={
            "canonical_taxon_ids": ["taxon:birds:000001", "taxon:birds:000002"],
            "difficulty_policy": "balanced",
            "country_code": None,
            "location_bbox": None,
            "location_point": None,
            "location_radius_meters": None,
            "observed_from": None,
            "observed_to": None,
            "owner_id": "owner:enrichment",
            "org_id": None,
            "visibility": "private",
            "intended_use": "training",
        },
    )
    enqueue = repository.enqueue_enrichment_for_pack(pack_id=str(payload["pack_id"]))
    request_id = enqueue["request"]["request"]["enrichment_request_id"]

    execution = repository.record_enrichment_execution(
        enrichment_request_id=request_id,
        execution_status="success",
        execution_context={"step": "manual"},
        trigger_recompile=True,
    )
    assert execution["execution_status"] == "success"
    assert execution["request_status"] == "completed"
    assert execution["recompilation"]["attempted"] is True

    requests = repository.fetch_enrichment_requests(enrichment_request_id=request_id)
    assert requests[0]["execution_attempt_count"] == 1
    assert requests[0]["request_status"] == "completed"
    executions = repository.fetch_enrichment_executions(enrichment_request_id=request_id)
    assert len(executions) == 1


def test_record_enrichment_execution_failed_requires_error_info(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    payload = repository.create_pack(
        pack_id="pack:enrichment:execution-failed",
        parameters={
            "canonical_taxon_ids": ["taxon:birds:000001", "taxon:birds:000002"],
            "difficulty_policy": "balanced",
            "country_code": None,
            "location_bbox": None,
            "location_point": None,
            "location_radius_meters": None,
            "observed_from": None,
            "observed_to": None,
            "owner_id": "owner:enrichment",
            "org_id": None,
            "visibility": "private",
            "intended_use": "training",
        },
    )
    enqueue = repository.enqueue_enrichment_for_pack(pack_id=str(payload["pack_id"]))
    request_id = enqueue["request"]["request"]["enrichment_request_id"]

    with pytest.raises(ValueError, match="error_info is required"):
        repository.record_enrichment_execution(
            enrichment_request_id=request_id,
            execution_status="failed",
            execution_context={"step": "manual"},
        )


def test_ingest_confusion_batch_creates_events(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()

    payload = repository.ingest_confusion_batch(
        batch_id="batch:confusions:001",
        events=[
            {
                "taxon_confused_for_id": "taxon:birds:000001",
                "taxon_correct_id": "taxon:birds:000002",
                "occurred_at": datetime(2026, 4, 9, 12, 0, tzinfo=UTC).isoformat(),
            },
            {
                "taxon_confused_for_id": "taxon:birds:000003",
                "taxon_correct_id": "taxon:birds:000004",
                "occurred_at": datetime(2026, 4, 9, 12, 1, tzinfo=UTC).isoformat(),
            },
        ],
    )
    assert payload["ingested"] is True
    assert payload["event_count"] == 2

    events = repository.fetch_confusion_events(batch_id="batch:confusions:001")
    assert len(events) == 2


def test_ingest_confusion_batch_duplicate_batch_rejected(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    events = [
        {
            "taxon_confused_for_id": "taxon:birds:000001",
            "taxon_correct_id": "taxon:birds:000002",
            "occurred_at": datetime(2026, 4, 9, 12, 0, tzinfo=UTC).isoformat(),
        }
    ]

    first = repository.ingest_confusion_batch(batch_id="batch:confusions:dupe", events=events)
    second = repository.ingest_confusion_batch(batch_id="batch:confusions:dupe", events=events)

    assert first["ingested"] is True
    assert second == {
        "ingested": False,
        "reason": "duplicate_batch",
        "batch_id": "batch:confusions:dupe",
    }
    stored = repository.fetch_confusion_events(batch_id="batch:confusions:dupe")
    assert len(stored) == 1


def test_ingest_confusion_batch_assigns_deterministic_event_ids(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()

    repository.ingest_confusion_batch(
        batch_id="batch:confusions:deterministic",
        events=[
            {
                "taxon_confused_for_id": "taxon:birds:000001",
                "taxon_correct_id": "taxon:birds:000002",
                "occurred_at": datetime(2026, 4, 9, 12, 0, tzinfo=UTC).isoformat(),
            },
            {
                "taxon_confused_for_id": "taxon:birds:000003",
                "taxon_correct_id": "taxon:birds:000004",
                "occurred_at": datetime(2026, 4, 9, 12, 1, tzinfo=UTC).isoformat(),
            },
        ],
    )
    events = repository.fetch_confusion_events(batch_id="batch:confusions:deterministic")
    ids = sorted(item["confusion_event_id"] for item in events)
    assert ids == [
        "batch:confusions:deterministic:1",
        "batch:confusions:deterministic:2",
    ]


def test_recompute_confusion_aggregates_global_counts_directed_pairs(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    repository.ingest_confusion_batch(
        batch_id="batch:confusions:agg",
        events=[
            {
                "taxon_confused_for_id": "taxon:birds:000001",
                "taxon_correct_id": "taxon:birds:000002",
                "occurred_at": datetime(2026, 4, 9, 12, 0, tzinfo=UTC).isoformat(),
            },
            {
                "taxon_confused_for_id": "taxon:birds:000001",
                "taxon_correct_id": "taxon:birds:000002",
                "occurred_at": datetime(2026, 4, 9, 12, 5, tzinfo=UTC).isoformat(),
            },
            {
                "taxon_confused_for_id": "taxon:birds:000002",
                "taxon_correct_id": "taxon:birds:000001",
                "occurred_at": datetime(2026, 4, 9, 12, 7, tzinfo=UTC).isoformat(),
            },
        ],
    )

    recomputed = repository.recompute_confusion_aggregates_global()
    assert recomputed["recomputed"] is True
    assert recomputed["pair_count"] == 2

    aggregates = repository.fetch_confusion_aggregates_global(limit=10)
    by_pair = {
        (item["taxon_confused_for_id"], item["taxon_correct_id"]): item["event_count"]
        for item in aggregates
    }
    assert by_pair[("taxon:birds:000001", "taxon:birds:000002")] == 2
    assert by_pair[("taxon:birds:000002", "taxon:birds:000001")] == 1


def test_recompute_confusion_aggregates_global_is_idempotent(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    repository.ingest_confusion_batch(
        batch_id="batch:confusions:idempotent",
        events=[
            {
                "taxon_confused_for_id": "taxon:birds:000011",
                "taxon_correct_id": "taxon:birds:000012",
                "occurred_at": datetime(2026, 4, 9, 13, 0, tzinfo=UTC).isoformat(),
            }
        ],
    )

    first = repository.recompute_confusion_aggregates_global()
    second = repository.recompute_confusion_aggregates_global()
    assert first["pair_count"] == second["pair_count"] == 1
    aggregates = repository.fetch_confusion_aggregates_global(limit=10)
    assert len(aggregates) == 1
    assert aggregates[0]["event_count"] == 1


def test_ingest_confusion_batch_rejects_same_taxon_pair(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()

    with pytest.raises(ValidationError, match="must differ"):
        repository.ingest_confusion_batch(
            batch_id="batch:confusions:invalid",
            events=[
                {
                    "taxon_confused_for_id": "taxon:birds:000001",
                    "taxon_correct_id": "taxon:birds:000001",
                    "occurred_at": datetime(2026, 4, 9, 12, 0, tzinfo=UTC).isoformat(),
                }
            ],
        )


def test_fetch_summary_confusion_counts_only_global_mode(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    repository.ingest_confusion_batch(
        batch_id="batch:confusions:summary",
        events=[
            {
                "taxon_confused_for_id": "taxon:birds:000001",
                "taxon_correct_id": "taxon:birds:000002",
                "occurred_at": datetime(2026, 4, 9, 12, 0, tzinfo=UTC).isoformat(),
            }
        ],
    )
    repository.recompute_confusion_aggregates_global()

    global_summary = repository.fetch_summary()
    assert global_summary["confusion_events"] == 1
    assert global_summary["confusion_aggregates_global"] == 1

    run_summary = repository.fetch_summary(run_id="run:nonexistent")
    assert "confusion_events" not in run_summary
    assert "confusion_aggregates_global" not in run_summary


def test_fetch_enrichment_queue_metrics_includes_status_distribution(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    payload = repository.create_pack(
        pack_id="pack:enrichment:metrics",
        parameters={
            "canonical_taxon_ids": ["taxon:birds:000001", "taxon:birds:000002"],
            "difficulty_policy": "balanced",
            "country_code": None,
            "location_bbox": None,
            "location_point": None,
            "location_radius_meters": None,
            "observed_from": None,
            "observed_to": None,
            "owner_id": "owner:metrics",
            "org_id": None,
            "visibility": "private",
            "intended_use": "training",
        },
    )
    enqueue = repository.enqueue_enrichment_for_pack(pack_id=str(payload["pack_id"]))
    request_id = enqueue["request"]["request"]["enrichment_request_id"]
    repository.record_enrichment_execution(
        enrichment_request_id=request_id,
        execution_status="failed",
        execution_context={"step": "metrics"},
        error_info="synthetic failure",
    )

    metrics = repository.fetch_enrichment_queue_metrics()
    assert metrics["requests_total"] == 1
    assert metrics["executions_total"] == 1
    assert metrics["attempts_total"] == 1
    assert metrics["status_counts"]["failed"] == 1
    assert metrics["status_counts"]["pending"] == 0


def test_fetch_confusion_metrics_reports_top_pairs(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    repository.ingest_confusion_batch(
        batch_id="batch:confusions:metrics",
        events=[
            {
                "taxon_confused_for_id": "taxon:birds:000031",
                "taxon_correct_id": "taxon:birds:000032",
                "occurred_at": datetime(2026, 4, 9, 14, 0, tzinfo=UTC).isoformat(),
            },
            {
                "taxon_confused_for_id": "taxon:birds:000031",
                "taxon_correct_id": "taxon:birds:000032",
                "occurred_at": datetime(2026, 4, 9, 14, 1, tzinfo=UTC).isoformat(),
            },
            {
                "taxon_confused_for_id": "taxon:birds:000033",
                "taxon_correct_id": "taxon:birds:000034",
                "occurred_at": datetime(2026, 4, 9, 14, 2, tzinfo=UTC).isoformat(),
            },
        ],
    )
    repository.recompute_confusion_aggregates_global()

    metrics = repository.fetch_confusion_metrics(top_pair_limit=1)
    assert metrics["batches_total"] == 1
    assert metrics["events_total"] == 3
    assert metrics["aggregates_total"] == 2
    assert metrics["last_aggregated_at"] is not None
    assert len(metrics["top_pairs"]) == 1
    assert metrics["top_pairs"][0] == {
        "taxon_confused_for_id": "taxon:birds:000031",
        "taxon_correct_id": "taxon:birds:000032",
        "event_count": 2,
    }


def test_compile_pack_prefers_internal_similar_taxa_for_distractors(
    database_url: str,
) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    canonical_taxon_ids = _seed_pack_ready_playable_items(
        repository,
        run_id="run:20260408T001150Z:gate5a01",
        taxon_count=10,
        media_per_taxon=2,
    )
    target_taxon_id = canonical_taxon_ids[0]
    similar_taxon_ids = canonical_taxon_ids[1:4]
    _configure_gate5_similarity(
        repository,
        target_taxon_id=target_taxon_id,
        similar_taxon_ids=similar_taxon_ids,
    )
    payload = repository.create_pack(
        pack_id="pack:compile:gate5:similarity-priority",
        parameters={
            "canonical_taxon_ids": canonical_taxon_ids,
            "difficulty_policy": "easy",
            "country_code": None,
            "location_bbox": None,
            "location_point": None,
            "location_radius_meters": None,
            "observed_from": None,
            "observed_to": None,
            "owner_id": "owner:compile",
            "org_id": None,
            "visibility": "private",
            "intended_use": "training",
        },
    )

    build = repository.compile_pack(pack_id=str(payload["pack_id"]), question_count=1)
    first_question = build["questions"][0]

    assert first_question["target_canonical_taxon_id"] == target_taxon_id
    assert first_question["distractor_canonical_taxon_ids"] == similar_taxon_ids


def test_compile_pack_falls_back_when_similar_taxa_are_insufficient(
    database_url: str,
) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    canonical_taxon_ids = _seed_pack_ready_playable_items(
        repository,
        run_id="run:20260408T001151Z:gate5a02",
        taxon_count=10,
        media_per_taxon=2,
    )
    target_taxon_id = canonical_taxon_ids[0]
    similar_taxon_ids = canonical_taxon_ids[1:3]
    _configure_gate5_similarity(
        repository,
        target_taxon_id=target_taxon_id,
        similar_taxon_ids=similar_taxon_ids,
    )
    payload = repository.create_pack(
        pack_id="pack:compile:gate5:fallback",
        parameters={
            "canonical_taxon_ids": canonical_taxon_ids,
            "difficulty_policy": "easy",
            "country_code": None,
            "location_bbox": None,
            "location_point": None,
            "location_radius_meters": None,
            "observed_from": None,
            "observed_to": None,
            "owner_id": "owner:compile",
            "org_id": None,
            "visibility": "private",
            "intended_use": "training",
        },
    )

    build = repository.compile_pack(pack_id=str(payload["pack_id"]), question_count=1)
    first_question = build["questions"][0]
    selected_taxa = first_question["distractor_canonical_taxon_ids"]

    assert first_question["target_canonical_taxon_id"] == target_taxon_id
    assert len(selected_taxa) == 3
    assert selected_taxa[:2] == similar_taxon_ids
    assert selected_taxa[2] not in similar_taxon_ids
    assert selected_taxa[2] != target_taxon_id


def test_compile_pack_prioritizes_non_distractor_risk_media_when_available(
    database_url: str,
) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    canonical_taxon_ids = _seed_pack_ready_playable_items(
        repository,
        run_id="run:20260408T001152Z:gate5a03",
        taxon_count=10,
        media_per_taxon=2,
    )
    target_taxon_id = canonical_taxon_ids[0]
    similar_taxon_ids = canonical_taxon_ids[1:4]
    _configure_gate5_similarity(
        repository,
        target_taxon_id=target_taxon_id,
        similar_taxon_ids=similar_taxon_ids,
    )
    risk_taxon_id = similar_taxon_ids[0]

    with repository.connect() as connection:
        connection.execute(
            """
            UPDATE playable_items
            SET media_role = 'distractor_risk', confusion_relevance = 'high'
            WHERE canonical_taxon_id = %s
              AND playable_item_id LIKE %s
            """,
            (risk_taxon_id, "%:1"),
        )
        connection.execute(
            """
            UPDATE playable_items
            SET media_role = 'primary_id', confusion_relevance = 'high'
            WHERE canonical_taxon_id = %s
              AND playable_item_id LIKE %s
            """,
            (risk_taxon_id, "%:2"),
        )

    payload = repository.create_pack(
        pack_id="pack:compile:gate5:media-role-priority",
        parameters={
            "canonical_taxon_ids": canonical_taxon_ids,
            "difficulty_policy": "easy",
            "country_code": None,
            "location_bbox": None,
            "location_point": None,
            "location_radius_meters": None,
            "observed_from": None,
            "observed_to": None,
            "owner_id": "owner:compile",
            "org_id": None,
            "visibility": "private",
            "intended_use": "training",
        },
    )

    build = repository.compile_pack(pack_id=str(payload["pack_id"]), question_count=1)
    first_question = build["questions"][0]
    risk_item_id = f"playable:qr:media:inaturalist:{risk_taxon_id}:1"
    preferred_item_id = f"playable:qr:media:inaturalist:{risk_taxon_id}:2"

    assert first_question["target_canonical_taxon_id"] == target_taxon_id
    assert preferred_item_id in first_question["distractor_playable_item_ids"]
    assert risk_item_id not in first_question["distractor_playable_item_ids"]


def test_compile_pack_uses_inat_similar_species_hints_for_distractors(
    database_url: str,
) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    canonical_taxon_ids = _seed_pack_ready_playable_items(
        repository,
        run_id="run:20260408T001153Z:gate5a04",
        taxon_count=10,
        media_per_taxon=2,
    )
    target_taxon_id = canonical_taxon_ids[0]
    similar_taxon_ids = canonical_taxon_ids[1:4]
    _configure_inat_similarity_hints(
        repository,
        canonical_taxon_ids=canonical_taxon_ids,
        target_taxon_id=target_taxon_id,
        hinted_taxon_ids=similar_taxon_ids,
    )
    payload = repository.create_pack(
        pack_id="pack:compile:gate5:inat-similar-species",
        parameters={
            "canonical_taxon_ids": canonical_taxon_ids,
            "difficulty_policy": "easy",
            "country_code": None,
            "location_bbox": None,
            "location_point": None,
            "location_radius_meters": None,
            "observed_from": None,
            "observed_to": None,
            "owner_id": "owner:compile",
            "org_id": None,
            "visibility": "private",
            "intended_use": "training",
        },
    )

    build = repository.compile_pack(pack_id=str(payload["pack_id"]), question_count=1)
    first_question = build["questions"][0]

    assert first_question["target_canonical_taxon_id"] == target_taxon_id
    assert first_question["distractor_canonical_taxon_ids"] == similar_taxon_ids


def test_materialize_pack_daily_challenge_is_frozen_after_playable_change(
    database_url: str,
) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    canonical_taxon_ids = _seed_pack_ready_playable_items(
        repository,
        run_id="run:20260408T001200Z:ssssssss",
        taxon_count=10,
        media_per_taxon=2,
    )
    payload = repository.create_pack(
        pack_id="pack:materialize:freeze",
        parameters={
            "canonical_taxon_ids": canonical_taxon_ids,
            "difficulty_policy": "easy",
            "country_code": None,
            "location_bbox": None,
            "location_point": None,
            "location_radius_meters": None,
            "observed_from": None,
            "observed_to": None,
            "owner_id": "owner:materialize",
            "org_id": None,
            "visibility": "private",
            "intended_use": "training",
        },
    )

    first_build = repository.compile_pack(pack_id=str(payload["pack_id"]), question_count=20)
    materialization = repository.materialize_pack(
        pack_id=str(payload["pack_id"]),
        question_count=20,
        purpose="daily_challenge",
    )
    validate_pack_materialization(materialization)
    assert materialization["purpose"] == "daily_challenge"
    assert materialization["ttl_hours"] == 24
    assert materialization["expires_at"] is not None

    first_target = first_build["questions"][0]["target_playable_item_id"]
    with repository.connect() as connection:
        connection.execute(
            """
            UPDATE playable_items
            SET difficulty_level = 'hard'
            WHERE playable_item_id = %s
            """,
            (first_target,),
        )

    second_build = repository.compile_pack(pack_id=str(payload["pack_id"]), question_count=20)
    assert second_build["questions"] != first_build["questions"]
    assert materialization["questions"] == first_build["questions"]


def test_materialize_pack_assignment_rejects_ttl(database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    canonical_taxon_ids = _seed_pack_ready_playable_items(
        repository,
        run_id="run:20260408T001300Z:tttttttt",
        taxon_count=10,
        media_per_taxon=2,
    )
    payload = repository.create_pack(
        pack_id="pack:materialize:assignment",
        parameters={
            "canonical_taxon_ids": canonical_taxon_ids,
            "difficulty_policy": "balanced",
            "country_code": None,
            "location_bbox": None,
            "location_point": None,
            "location_radius_meters": None,
            "observed_from": None,
            "observed_to": None,
            "owner_id": "owner:materialize",
            "org_id": None,
            "visibility": "private",
            "intended_use": "training",
        },
    )
    repository.compile_pack(pack_id=str(payload["pack_id"]), question_count=20)
    with pytest.raises(ValueError, match="assignment materialization cannot define ttl_hours"):
        repository.materialize_pack(
            pack_id=str(payload["pack_id"]),
            question_count=20,
            purpose="assignment",
            ttl_hours=4,
        )

def _seed_pack_ready_playable_items(
    repository: PostgresRepository,
    *,
    run_id: str,
    taxon_count: int,
    media_per_taxon: int,
) -> list[str]:
    captured_at = datetime(2026, 4, 8, 0, 0, tzinfo=UTC)
    canonical_taxon_ids = [f"taxon:birds:{index + 1:06d}" for index in range(taxon_count)]
    with repository.connect() as connection:
        repository.start_pipeline_run(
            run_id=run_id,
            source_mode="fixture",
            dataset_id=f"fixture:{run_id}",
            snapshot_id=None,
            started_at=captured_at,
            connection=connection,
        )
        repository.save_canonical_taxa(
            [
                _canonical_taxon(canonical_taxon_id=canonical_taxon_id, name=canonical_taxon_id)
                for canonical_taxon_id in canonical_taxon_ids
            ],
            run_id=run_id,
            connection=connection,
        )

        observations: list[SourceObservation] = []
        media_assets: list[MediaAsset] = []
        qualified_resources: list[QualifiedResource] = []
        playable_items: list[PlayableItem] = []
        for canonical_taxon_id in canonical_taxon_ids:
            for offset in range(media_per_taxon):
                suffix = f"{canonical_taxon_id}:{offset + 1}"
                observation_uid = f"obs:inaturalist:{suffix}"
                source_observation_id = f"obs-{suffix}"
                media_id = f"media:inaturalist:{suffix}"
                qualified_resource_id = f"qr:{media_id}"
                observations.append(
                    SourceObservation(
                        observation_uid=observation_uid,
                        source_name=SourceName.INATURALIST,
                        source_observation_id=source_observation_id,
                        source_taxon_id=canonical_taxon_id,
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
                        raw_payload_ref=f"fixture://{suffix}",
                        canonical_taxon_id=canonical_taxon_id,
                    )
                )
                media_assets.append(
                    _media_asset(
                        media_id=media_id,
                        source_media_id=source_observation_id,
                        source_observation_uid=observation_uid,
                        canonical_taxon_id=canonical_taxon_id,
                    )
                )
                qualified_resources.append(
                    _qualified_resource(
                        qualified_resource_id=qualified_resource_id,
                        media_asset_id=media_id,
                        source_observation_uid=observation_uid,
                        source_observation_id=source_observation_id,
                        canonical_taxon_id=canonical_taxon_id,
                    )
                )
                playable_items.append(
                    _playable_item(
                        run_id=run_id,
                        qualified_resource_id=qualified_resource_id,
                        canonical_taxon_id=canonical_taxon_id,
                        media_asset_id=media_id,
                        source_observation_uid=observation_uid,
                        source_observation_id=source_observation_id,
                        source_media_id=source_observation_id,
                        difficulty_level="easy",
                    )
                )

        repository.save_source_observations(observations, connection=connection)
        repository.save_media_assets(media_assets, connection=connection)
        repository.save_qualified_resources(qualified_resources, connection=connection)
        repository.save_playable_items(playable_items, connection=connection)
        repository.complete_pipeline_run(
            run_id=run_id,
            completed_at=captured_at,
            connection=connection,
        )
    return canonical_taxon_ids


def _configure_gate5_similarity(
    repository: PostgresRepository,
    *,
    target_taxon_id: str,
    similar_taxon_ids: list[str],
) -> None:
    with repository.connect() as connection:
        connection.execute(
            """
            UPDATE playable_items
            SET similar_taxon_ids_json = %s
            WHERE canonical_taxon_id = %s
            """,
            (json.dumps(similar_taxon_ids), target_taxon_id),
        )
        for taxon_id in similar_taxon_ids:
            connection.execute(
                """
                UPDATE playable_items
                SET media_role = 'primary_id', confusion_relevance = 'high'
                WHERE canonical_taxon_id = %s
                """,
                (taxon_id,),
            )


def _configure_inat_similarity_hints(
    repository: PostgresRepository,
    *,
    canonical_taxon_ids: list[str],
    target_taxon_id: str,
    hinted_taxon_ids: list[str],
) -> None:
    with repository.connect() as connection:
        for canonical_taxon_id in canonical_taxon_ids:
            source_taxon_id = f"inat-{canonical_taxon_id}"
            connection.execute(
                """
                UPDATE canonical_taxa
                SET external_source_mappings_json = %s
                WHERE canonical_taxon_id = %s
                """,
                (
                    json.dumps(
                        [{"source_name": "inaturalist", "external_id": source_taxon_id}]
                    ),
                    canonical_taxon_id,
                ),
            )

        hint_payload = [
            {
                "source_name": "inaturalist",
                "external_taxon_id": f"inat-{taxon_id}",
                "relation_type": "visual_lookalike",
            }
            for taxon_id in hinted_taxon_ids
        ]
        connection.execute(
            """
            UPDATE canonical_taxa
            SET external_similarity_hints_json = %s
            WHERE canonical_taxon_id = %s
            """,
            (json.dumps(hint_payload), target_taxon_id),
        )
        connection.execute(
            """
            UPDATE playable_items
            SET similar_taxon_ids_json = '[]'
            WHERE canonical_taxon_id = %s
            """,
            (target_taxon_id,),
        )


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
    difficulty_level: str = "easy",
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
        difficulty_level=difficulty_level,
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
