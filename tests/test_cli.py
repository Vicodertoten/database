import sys
from pathlib import Path

import database_core.cli as cli
from database_core.adapters.inaturalist_qualification import SnapshotQualificationResult


def test_cli_qualify_inat_snapshot_loads_dotenv(monkeypatch, tmp_path: Path, capsys) -> None:
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

    cli.main()

    assert calls["gemini_api_key"] == "dotenv-key"
    assert calls["gemini_model"] == "gemini-3.1-flash-lite-preview"
    assert calls["request_interval_seconds"] == 4.5
    assert calls["max_retries"] == 4
    assert calls["initial_backoff_seconds"] == 5.0
    assert calls["max_backoff_seconds"] == 60.0
    assert "Snapshot AI qualification complete" in capsys.readouterr().out
