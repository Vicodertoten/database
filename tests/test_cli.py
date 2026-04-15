import io
import json
import sys
from contextlib import redirect_stdout
from datetime import UTC
from datetime import datetime as real_datetime
from pathlib import Path

import pytest

import database_core.cli as cli
from database_core.adapters.inaturalist_qualification import SnapshotQualificationResult
from database_core.domain.enums import SourceName
from database_core.domain.models import (
    CanonicalTaxon,
    GeoPoint,
    LocationMetadata,
    MediaAsset,
    PlayableItem,
    ProvenanceSummary,
    QualifiedResource,
    SourceObservation,
    SourceQualityMetadata,
)
from database_core.pipeline.runner import run_pipeline
from database_core.security import redact_database_url
from database_core.storage.postgres import PostgresRepository
from database_core.versioning import SCHEMA_VERSION


def test_cli_qualify_inat_snapshot_loads_dotenv(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("GEMINI_API_KEY=dotenv-key\n", encoding="utf-8")
    calls: dict[str, object] = {}

    def fake_qualify_inat_snapshot(**kwargs):
        calls.update(kwargs)
        return SnapshotQualificationResult(
            snapshot_id="smoke-snapshot",
            snapshot_dir=tmp_path / "raw" / "smoke-snapshot",
            ai_outputs_path=tmp_path / "raw" / "smoke-snapshot" / "ai_outputs.json",
            processed_media_count=3,
            images_sent_to_gemini_count=3,
            ai_valid_output_count=3,
            insufficient_resolution_count=0,
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(cli, "qualify_inat_snapshot", fake_qualify_inat_snapshot)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "qualify-inat-snapshot",
            "--snapshot-id",
            "smoke-snapshot",
            "--snapshot-root",
            str(tmp_path / "raw"),
        ],
    )

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        cli.main()

    assert calls["gemini_api_key"] == "dotenv-key"
    assert calls["gemini_model"] == "gemini-3.1-flash-lite-preview"
    assert calls["request_interval_seconds"] == 0.5
    assert calls["max_retries"] == 2
    assert calls["initial_backoff_seconds"] == 1.0
    assert calls["max_backoff_seconds"] == 8.0
    assert "Snapshot AI qualification complete" in buffer.getvalue()


def test_default_snapshot_id_uses_strict_inaturalist_prefix(monkeypatch) -> None:
    class FixedDatetime:
        @classmethod
        def now(cls, tz=None):
            del tz
            return real_datetime.fromisoformat("2026-04-08T12:34:56+00:00")

    monkeypatch.setattr(cli, "datetime", FixedDatetime)

    assert cli.default_snapshot_id() == "inaturalist-birds-20260408T123456Z"


def test_review_overrides_cli_init_creates_versioned_file(monkeypatch, tmp_path: Path) -> None:
    override_path = tmp_path / "review_overrides.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "review-overrides",
            "init",
            "--snapshot-id",
            "smoke-snapshot",
            "--path",
            str(override_path),
        ],
    )

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        cli.main()

    payload = json.loads(override_path.read_text(encoding="utf-8"))
    assert payload == {
        "override_version": "review.override.v1",
        "overrides": [],
        "snapshot_id": "smoke-snapshot",
    }
    assert "Review overrides initialized" in buffer.getvalue()


def test_review_overrides_cli_upsert_and_list(monkeypatch, tmp_path: Path) -> None:
    override_path = tmp_path / "review_overrides.json"
    override_path.write_text(
        json.dumps(
            {
                "override_version": "review.override.v1",
                "snapshot_id": "smoke-snapshot",
                "overrides": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "review-overrides",
            "upsert",
            "--snapshot-id",
            "smoke-snapshot",
            "--path",
            str(override_path),
            "--media-asset-id",
            "media:inaturalist:810001",
            "--status",
            "review_required",
            "--note",
            "manual spot-check requested",
        ],
    )
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        cli.main()

    payload = json.loads(override_path.read_text(encoding="utf-8"))
    assert payload["overrides"] == [
        {
            "media_asset_id": "media:inaturalist:810001",
            "qualification_status": "review_required",
            "note": "manual spot-check requested",
        }
    ]

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "review-overrides",
            "list",
            "--snapshot-id",
            "smoke-snapshot",
            "--path",
            str(override_path),
        ],
    )
    with redirect_stdout(buffer):
        cli.main()

    output = buffer.getvalue()
    assert "Review override upserted" in output
    assert "media_asset_id=media:inaturalist:810001" in output


def test_review_overrides_cli_rejects_wrong_override_version(monkeypatch, tmp_path: Path) -> None:
    override_path = tmp_path / "review_overrides.json"
    override_path.write_text(
        json.dumps(
            {
                "override_version": "review.override.v0",
                "snapshot_id": "smoke-snapshot",
                "overrides": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "review-overrides",
            "list",
            "--snapshot-id",
            "smoke-snapshot",
            "--path",
            str(override_path),
        ],
    )

    with pytest.raises(ValueError, match="Review overrides version mismatch"):
        cli.main()


def test_migrate_cli_applies_pending_schema_migration(monkeypatch, database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    with repository.connect() as connection:
        connection.execute("DELETE FROM schema_migrations")
        connection.execute("INSERT INTO schema_migrations (version) VALUES (1)")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "migrate",
            "--database-url",
            database_url,
        ],
    )

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        cli.main()

    output = buffer.getvalue()
    assert "Database migrated" in output
    assert f"database_url={redact_database_url(database_url)}" in output
    assert f"database_url={database_url}" not in output
    assert repository.current_schema_version() == SCHEMA_VERSION


def test_confusion_cli_ingest_and_recompute(monkeypatch, tmp_path: Path, database_url: str) -> None:
    events_file = tmp_path / "confusions.json"
    events_file.write_text(
        json.dumps(
            [
                {
                    "taxon_confused_for_id": "taxon:birds:000001",
                    "taxon_correct_id": "taxon:birds:000002",
                    "occurred_at": "2026-04-09T12:00:00+00:00",
                },
                {
                    "taxon_confused_for_id": "taxon:birds:000001",
                    "taxon_correct_id": "taxon:birds:000003",
                    "occurred_at": "2026-04-09T12:01:00+00:00",
                },
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "confusion",
            "ingest-batch",
            "--database-url",
            database_url,
            "--batch-id",
            "batch:cli:001",
            "--events-file",
            str(events_file),
        ],
    )
    ingest_buffer = io.StringIO()
    with redirect_stdout(ingest_buffer):
        cli.main()
    ingested = json.loads(ingest_buffer.getvalue())
    assert ingested["ingested"] is True
    assert ingested["event_count"] == 2

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "confusion",
            "aggregate-recompute",
            "--database-url",
            database_url,
        ],
    )
    recompute_buffer = io.StringIO()
    with redirect_stdout(recompute_buffer):
        cli.main()
    recomputed = json.loads(recompute_buffer.getvalue())
    assert recomputed["recomputed"] is True
    assert recomputed["pair_count"] == 2


def test_governance_review_cli_resolves_item(monkeypatch, database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()

    run_id = "run:20260408T000000Z:aaaaaaaa"
    governance_event_id = f"{run_id}:event:taxon:birds:000001:split:demo"
    review_item_id = f"cgr:{governance_event_id}"
    started_at = real_datetime.fromisoformat("2026-04-08T00:00:00+00:00")

    with repository.connect() as connection:
        repository.start_pipeline_run(
            run_id=run_id,
            source_mode="fixture",
            dataset_id="fixture:governance-review",
            snapshot_id=None,
            started_at=started_at,
            connection=connection,
        )
        repository.complete_pipeline_run(
            run_id=run_id,
            completed_at=started_at,
            connection=connection,
        )
        connection.execute(
            """
            INSERT INTO canonical_governance_events (
                governance_event_id,
                run_id,
                canonical_taxon_id,
                event_type,
                source_name,
                effective_at,
                decision_status,
                decision_reason,
                payload_json,
                created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                governance_event_id,
                run_id,
                "taxon:birds:000001",
                "split",
                "inaturalist",
                started_at.isoformat(),
                "manual_reviewed",
                "ambiguous_transition_missing_target",
                "{}",
                started_at.isoformat(),
            ),
        )
        connection.execute(
            """
            INSERT INTO canonical_governance_review_queue (
                governance_review_item_id,
                run_id,
                governance_event_id,
                canonical_taxon_id,
                reason_code,
                review_note,
                review_status,
                created_at,
                resolved_at,
                resolved_note,
                resolved_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, NULL)
            """,
            (
                review_item_id,
                run_id,
                governance_event_id,
                "taxon:birds:000001",
                "ambiguous_transition_missing_target",
                "requires operator validation",
                "open",
                started_at.isoformat(),
            ),
        )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "governance-review",
            "resolve",
            "--database-url",
            database_url,
            "--governance-review-item-id",
            review_item_id,
            "--note",
            "validated against source taxonomy delta",
            "--resolved-by",
            "operator:test",
        ],
    )

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        cli.main()

    output = buffer.getvalue()
    assert "Canonical governance review item resolved" in output

    rows = repository.fetch_canonical_governance_review_queue(run_id=run_id)
    assert rows[0]["review_status"] == "closed"
    assert rows[0]["resolved_note"] == "validated against source taxonomy delta"
    assert rows[0]["resolved_by"] == "operator:test"


def test_inspect_cli_playable_corpus_outputs_payload(
    monkeypatch, tmp_path: Path, database_url: str
) -> None:
    run_pipeline(
        fixture_path=Path("data/fixtures/birds_pilot.json"),
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "playable.normalized.json",
        qualification_snapshot_path=tmp_path / "playable.qualified.json",
        export_path=tmp_path / "playable.export.json",
        run_id="run:20260408T000000Z:aaaaaaaa",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "inspect",
            "playable-corpus",
            "--database-url",
            database_url,
            "--limit",
            "10",
        ],
    )
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        cli.main()
    payload = json.loads(buffer.getvalue())
    assert payload["playable_corpus_version"] == "playable_corpus.v1"
    assert len(payload["items"]) == 2


def test_inspect_cli_playable_corpus_supports_filters(
    monkeypatch, tmp_path: Path, database_url: str
) -> None:
    run_pipeline(
        fixture_path=Path("data/fixtures/birds_pilot.json"),
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "playable_filter.normalized.json",
        qualification_snapshot_path=tmp_path / "playable_filter.qualified.json",
        export_path=tmp_path / "playable_filter.export.json",
        run_id="run:20260408T000000Z:aaaaaaaa",
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "inspect",
            "playable-corpus",
            "--database-url",
            database_url,
                "--canonical-taxon-id",
                "taxon:birds:000014",
                "--difficulty-level",
                "unknown",
                "--limit",
                "10",
            ],
    )
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        cli.main()
    payload = json.loads(buffer.getvalue())
    assert len(payload["items"]) == 1
    assert payload["items"][0]["canonical_taxon_id"] == "taxon:birds:000014"


def test_inspect_cli_playable_invalidations_outputs_lifecycle_lines(
    monkeypatch,
    database_url: str,
) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    _seed_pack_ready_data(
        repository,
        run_id="run:20260408T003000Z:inv001aa",
        taxon_count=1,
        media_per_taxon=1,
    )

    with repository.connect() as connection:
        repository.start_pipeline_run(
            run_id="run:20260408T003100Z:inv002bb",
            source_mode="fixture",
            dataset_id="fixture:cli:invalidations",
            snapshot_id=None,
            started_at=real_datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
            connection=connection,
        )
        connection.execute("UPDATE qualified_resources SET export_eligible = FALSE")
        repository.save_playable_items(
            [],
            run_id="run:20260408T003100Z:inv002bb",
            connection=connection,
        )
        repository.complete_pipeline_run(
            run_id="run:20260408T003100Z:inv002bb",
            completed_at=real_datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
            connection=connection,
        )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "inspect",
            "playable-invalidations",
            "--database-url",
            database_url,
            "--run-id",
            "run:20260408T003100Z:inv002bb",
            "--limit",
            "10",
        ],
    )
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        cli.main()

    output = buffer.getvalue()
    assert "Playable lifecycle invalidations" in output
    assert "reason=qualification_not_exportable" in output


def test_pack_cli_create_revise_diagnose_and_inspect(monkeypatch, database_url: str) -> None:
    create_buffer = io.StringIO()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "pack",
            "create",
            "--database-url",
            database_url,
            "--pack-id",
            "pack:test:cli",
            "--canonical-taxon-id",
            "taxon:birds:000001",
            "--canonical-taxon-id",
            "taxon:birds:000002",
            "--difficulty-policy",
            "balanced",
            "--country-code",
            "BE",
            "--owner-id",
            "owner:cli",
            "--org-id",
            "org:cli",
            "--visibility",
            "private",
            "--intended-use",
            "quiz",
        ],
    )
    with redirect_stdout(create_buffer):
        cli.main()
    created = json.loads(create_buffer.getvalue())
    assert created["pack_id"] == "pack:test:cli"
    assert created["revision"] == 1

    revise_buffer = io.StringIO()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "pack",
            "revise",
            "--database-url",
            database_url,
            "--pack-id",
            "pack:test:cli",
            "--canonical-taxon-id",
            "taxon:birds:000001",
            "--difficulty-policy",
            "hard",
            "--point-radius",
            "4.35,50.85,5000",
            "--visibility",
            "org",
            "--intended-use",
            "practice",
        ],
    )
    with redirect_stdout(revise_buffer):
        cli.main()
    revised = json.loads(revise_buffer.getvalue())
    assert revised["revision"] == 2
    assert revised["latest_revision"] == 2

    diagnose_buffer = io.StringIO()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "pack",
            "diagnose",
            "--database-url",
            database_url,
            "--pack-id",
            "pack:test:cli",
        ],
    )
    with redirect_stdout(diagnose_buffer):
        cli.main()
    diagnostic = json.loads(diagnose_buffer.getvalue())
    assert diagnostic["pack_id"] == "pack:test:cli"
    assert diagnostic["reason_code"] == "no_playable_items"

    specs_buffer = io.StringIO()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "inspect",
            "pack-specs",
            "--database-url",
            database_url,
            "--pack-id",
            "pack:test:cli",
        ],
    )
    with redirect_stdout(specs_buffer):
        cli.main()
    specs = json.loads(specs_buffer.getvalue())
    assert len(specs) == 1
    assert specs[0]["latest_revision"] == 2

    revisions_buffer = io.StringIO()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "inspect",
            "pack-revisions",
            "--database-url",
            database_url,
            "--pack-id",
            "pack:test:cli",
        ],
    )
    with redirect_stdout(revisions_buffer):
        cli.main()
    revisions = json.loads(revisions_buffer.getvalue())
    assert [item["revision"] for item in revisions] == [2, 1]

    diagnostics_buffer = io.StringIO()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "inspect",
            "pack-diagnostics",
            "--database-url",
            database_url,
            "--pack-id",
            "pack:test:cli",
        ],
    )
    with redirect_stdout(diagnostics_buffer):
        cli.main()
    diagnostics = json.loads(diagnostics_buffer.getvalue())
    assert len(diagnostics) == 1
    assert diagnostics[0]["reason_code"] == "no_playable_items"


def test_pack_cli_compile_materialize_and_inspect(monkeypatch, database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()
    canonical_taxon_ids = _seed_pack_ready_data(
        repository,
        run_id="run:20260408T002000Z:uuuuuuuu",
        taxon_count=10,
        media_per_taxon=2,
    )

    create_args = [
        "database-core",
        "pack",
        "create",
        "--database-url",
        database_url,
        "--pack-id",
        "pack:test:gate4",
        "--difficulty-policy",
        "easy",
        "--visibility",
        "private",
        "--intended-use",
        "quiz",
    ]
    for canonical_taxon_id in canonical_taxon_ids:
        create_args.extend(["--canonical-taxon-id", canonical_taxon_id])

    create_buffer = io.StringIO()
    monkeypatch.setattr(sys, "argv", create_args)
    with redirect_stdout(create_buffer):
        cli.main()
    created = json.loads(create_buffer.getvalue())
    assert created["pack_id"] == "pack:test:gate4"

    compile_buffer = io.StringIO()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "pack",
            "compile",
            "--database-url",
            database_url,
            "--pack-id",
            "pack:test:gate4",
            "--question-count",
            "20",
        ],
    )
    with redirect_stdout(compile_buffer):
        cli.main()
    compiled_payload = json.loads(compile_buffer.getvalue())
    assert compiled_payload["pack_compiled_version"] == "pack.compiled.v1"
    assert compiled_payload["question_count_built"] == 20

    materialize_buffer = io.StringIO()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "pack",
            "materialize",
            "--database-url",
            database_url,
            "--pack-id",
            "pack:test:gate4",
            "--question-count",
            "20",
            "--purpose",
            "daily_challenge",
        ],
    )
    with redirect_stdout(materialize_buffer):
        cli.main()
    materialized_payload = json.loads(materialize_buffer.getvalue())
    assert materialized_payload["pack_materialization_version"] == "pack.materialization.v1"
    assert materialized_payload["purpose"] == "daily_challenge"
    assert materialized_payload["ttl_hours"] == 24

    builds_buffer = io.StringIO()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "inspect",
            "compiled-pack-builds",
            "--database-url",
            database_url,
            "--pack-id",
            "pack:test:gate4",
        ],
    )
    with redirect_stdout(builds_buffer):
        cli.main()
    builds = json.loads(builds_buffer.getvalue())
    assert len(builds) == 1
    assert builds[0]["pack_compiled_version"] == "pack.compiled.v1"

    materializations_buffer = io.StringIO()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "inspect",
            "pack-materializations",
            "--database-url",
            database_url,
            "--pack-id",
            "pack:test:gate4",
            "--purpose",
            "daily_challenge",
        ],
    )
    with redirect_stdout(materializations_buffer):
        cli.main()
    materializations = json.loads(materializations_buffer.getvalue())
    assert len(materializations) == 1
    assert materializations[0]["pack_materialization_version"] == "pack.materialization.v1"


def test_inspect_cli_enrichment_metrics_outputs_text(monkeypatch, database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()

    buffer = io.StringIO()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "inspect",
            "enrichment-metrics",
            "--database-url",
            database_url,
        ],
    )
    with redirect_stdout(buffer):
        cli.main()
    output = buffer.getvalue()
    assert "Enrichment metrics" in output
    assert "requests_total:" in output
    assert "status_counts" not in output


def test_inspect_cli_confusion_metrics_outputs_text(monkeypatch, database_url: str) -> None:
    repository = PostgresRepository(database_url)
    repository.initialize()

    buffer = io.StringIO()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "inspect",
            "confusion-metrics",
            "--database-url",
            database_url,
        ],
    )
    with redirect_stdout(buffer):
        cli.main()
    output = buffer.getvalue()
    assert "Confusion metrics" in output
    assert "batches_total:" in output


def _seed_pack_ready_data(
    repository: PostgresRepository,
    *,
    run_id: str,
    taxon_count: int,
    media_per_taxon: int,
) -> list[str]:
    captured_at = real_datetime(2026, 4, 8, 0, 0, tzinfo=UTC)
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


def _canonical_taxon(
    *,
    canonical_taxon_id: str,
    name: str,
) -> CanonicalTaxon:
    return CanonicalTaxon(
        canonical_taxon_id=canonical_taxon_id,
        accepted_scientific_name=name,
        canonical_rank="species",
        taxon_group="birds",
        taxon_status="active",
        authority_source="inaturalist",
        display_slug=name.lower().replace(" ", "-"),
        synonyms=[],
        common_names=[],
        key_identification_features=[],
        source_enrichment_status="seeded",
        bird_scope_compatible=True,
        external_source_mappings=[],
        external_similarity_hints=[],
        similar_taxa=[],
        similar_taxon_ids=[],
        split_into=[],
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
    difficulty_level: str,
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
        scientific_name=canonical_taxon_id,
        common_names_i18n={"fr": [], "en": [canonical_taxon_id], "nl": []},
        difficulty_level=difficulty_level,
        media_role="primary_id",
        learning_suitability="high",
        confusion_relevance="medium",
        diagnostic_feature_visibility="high",
        similar_taxon_ids=[],
        what_to_look_at_specific=["head"],
        what_to_look_at_general=["head"],
        confusion_hint=None,
        country_code="BE",
        observed_at=real_datetime(2026, 4, 8, 0, 0, tzinfo=UTC),
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
) -> MediaAsset:
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
) -> QualifiedResource:
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
            source_observation_key=f"inaturalist::{source_observation_id}",
            source_media_key=f"inaturalist::{source_observation_id}",
            source_observation_id=source_observation_id,
            source_media_id=source_observation_id,
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
