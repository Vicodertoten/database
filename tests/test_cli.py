import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime as real_datetime
from pathlib import Path

import pytest

import database_core.cli as cli
from database_core.adapters.inaturalist_qualification import SnapshotQualificationResult
from database_core.storage.sqlite import SQLiteRepository


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


def test_migrate_cli_applies_pending_schema_migration(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "migrate.sqlite"
    repository = SQLiteRepository(db_path)
    repository.initialize()
    with repository.connect() as connection:
        connection.execute("PRAGMA user_version = 3")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "database-core",
            "migrate",
            "--db-path",
            str(db_path),
        ],
    )

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        cli.main()

    assert "Database migrated" in buffer.getvalue()
    assert repository.current_schema_version() == 7


def test_governance_review_cli_resolves_item(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "governance-review.sqlite"
    repository = SQLiteRepository(db_path)
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
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
            "--db-path",
            str(db_path),
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
