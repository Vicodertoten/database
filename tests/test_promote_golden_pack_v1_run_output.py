from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import promote_golden_pack_v1_run_output as promote


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _make_run_output(root: Path, status: str = "passed", with_pack: bool = True) -> Path:
    run_output = root / "run" / "golden_pack"
    media_dir = run_output / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    media_file = media_dir / "img1.jpg"
    media_file.write_bytes(b"fake-jpg")

    if with_pack:
        pack = {"schema_version": "golden_pack.v1", "pack_id": "belgian_birds_mvp_v1", "questions": [], "media": []}
        _write_json(run_output / "pack.json", pack)

    validation_report = {"schema_version": "golden_pack_validation_report.v1", "status": status}
    _write_json(run_output / "validation_report.json", validation_report)

    checksums = {
        "validation_report.json": {"sha256": _sha256(run_output / "validation_report.json")},
        "media_files": [{"path": "media/img1.jpg", "sha256": _sha256(media_file)}],
    }
    if with_pack:
        checksums["pack.json"] = {"sha256": _sha256(run_output / "pack.json")}

    manifest = {
        "schema_version": "golden_pack_manifest.v1",
        "pack_id": "belgian_birds_mvp_v1",
        "checksums": checksums,
    }
    _write_json(run_output / "manifest.json", manifest)

    return run_output


def test_rejects_failed_validation_report(tmp_path: Path) -> None:
    run_output = _make_run_output(tmp_path, status="failed", with_pack=True)
    dest = tmp_path / "canonical"

    with pytest.raises(promote.PromotionError, match="validation_report.status"):
        promote.promote_run_output(
            promote.PromotionConfig(
                run_output_dir=run_output,
                canonical_export_dir=dest,
            )
        )

    assert not dest.exists()


def test_rejects_missing_pack_json(tmp_path: Path) -> None:
    run_output = _make_run_output(tmp_path, status="passed", with_pack=False)
    dest = tmp_path / "canonical"

    with pytest.raises(promote.PromotionError, match="Missing required promotion artifact"):
        promote.promote_run_output(
            promote.PromotionConfig(
                run_output_dir=run_output,
                canonical_export_dir=dest,
            )
        )

    assert not dest.exists()


def test_rejects_partial_only_build(tmp_path: Path) -> None:
    run_output = _make_run_output(tmp_path, status="passed", with_pack=False)
    partial = run_output / "failed_build" / "partial_pack.json"
    _write_json(partial, {"schema_version": "golden_pack.v1"})
    dest = tmp_path / "canonical"

    with pytest.raises(promote.PromotionError, match="partial_pack"):
        promote.promote_run_output(
            promote.PromotionConfig(
                run_output_dir=run_output,
                canonical_export_dir=dest,
            )
        )

    assert not dest.exists()


def test_promotes_passed_run_and_overwrites_destination(tmp_path: Path) -> None:
    run_output = _make_run_output(tmp_path, status="passed", with_pack=True)
    dest = tmp_path / "canonical"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "obsolete.txt").write_text("old", encoding="utf-8")

    promoted = promote.promote_run_output(
        promote.PromotionConfig(
            run_output_dir=run_output,
            canonical_export_dir=dest,
        )
    )

    assert promoted == dest
    assert (dest / "pack.json").exists()
    assert (dest / "manifest.json").exists()
    assert (dest / "validation_report.json").exists()
    assert (dest / "media" / "img1.jpg").exists()
    assert not (dest / "obsolete.txt").exists()


def test_rejects_checksum_mismatch(tmp_path: Path) -> None:
    run_output = _make_run_output(tmp_path, status="passed", with_pack=True)
    manifest = json.loads((run_output / "manifest.json").read_text(encoding="utf-8"))
    manifest["checksums"]["pack.json"]["sha256"] = "deadbeef"
    _write_json(run_output / "manifest.json", manifest)

    dest = tmp_path / "canonical"
    with pytest.raises(promote.PromotionError, match="Checksum mismatch"):
        promote.promote_run_output(
            promote.PromotionConfig(
                run_output_dir=run_output,
                canonical_export_dir=dest,
            )
        )

    assert not dest.exists()
