import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime as real_datetime
from pathlib import Path

import database_core.cli as cli
from database_core.adapters.inaturalist_qualification import SnapshotQualificationResult


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
