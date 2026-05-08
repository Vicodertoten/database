from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import export_golden_pack_runtime_handoff as export_handoff
from scripts import verify_golden_pack_runtime_handoff as verify_handoff


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _make_pack_dir(tmp_path: Path) -> Path:
    pack_dir = tmp_path / "pack"
    media_dir = pack_dir / "media"
    media_dir.mkdir(parents=True)
    media_rows = []
    questions = []
    checksum_media = []
    for idx in range(1, 31):
        media_id = f"m{idx:04d}"
        filename = f"img{idx}.jpg"
        media_path = media_dir / filename
        media_path.write_bytes(f"image-{idx}".encode())
        media_rows.append(
            {
                "media_id": media_id,
                "runtime_uri": f"media/{filename}",
                "checksum": f"sha256:{_sha256(media_path)}",
                "source": "inaturalist",
                "source_url": "https://example.org/image.jpg",
                "creator": "Unit Test",
                "license": "cc-by",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "attribution_text": "Unit Test, CC BY",
            }
        )
        checksum_media.append({"path": f"media/{filename}", "sha256": _sha256(media_path)})
        questions.append(
            {
                "question_id": f"q{idx:04d}",
                "prompt": "Quelle espèce est visible sur cette image ?",
                "primary_media_id": media_id,
                "correct_option_id": f"q{idx:04d}_opt1",
                "options": [
                    {
                        "option_id": f"q{idx:04d}_opt1",
                        "display_label": f"Espèce {idx}",
                        "is_correct": True,
                        "taxon_ref": {"type": "canonical_taxon", "id": f"taxon:{idx}"},
                    },
                    *[
                        {
                            "option_id": f"q{idx:04d}_opt{didx}",
                            "display_label": f"Distracteur {idx}-{didx}",
                            "is_correct": False,
                            "taxon_ref": {
                                "type": "referenced_taxon",
                                "id": f"inat:{idx}{didx}",
                            },
                            "referenced_only": True,
                        }
                        for didx in range(2, 5)
                    ],
                ],
                "feedback_short": "Compare les détails visibles.",
            }
        )
    pack = {
        "schema_version": "golden_pack.v1",
        "pack_id": "belgian_birds_mvp_v1",
        "locale": "fr",
        "media": media_rows,
        "questions": questions,
    }
    _write_json(pack_dir / "pack.json", pack)
    validation = {
        "schema_version": "golden_pack_validation_report.v1",
        "status": "passed",
        "schema_validity": {
            "manifest_schema_valid": True,
            "pack_schema_valid": True,
            "validation_report_schema_valid": True,
        },
    }
    _write_json(pack_dir / "validation_report.json", validation)
    manifest = {
        "schema_version": "golden_pack_manifest.v1",
        "checksums": {
            "pack.json": {"sha256": _sha256(pack_dir / "pack.json")},
            "validation_report.json": {
                "sha256": _sha256(pack_dir / "validation_report.json")
            },
            "media_files": checksum_media,
        },
    }
    _write_json(pack_dir / "manifest.json", manifest)
    return pack_dir


def test_verify_runtime_handoff_accepts_valid_pack(tmp_path: Path) -> None:
    result = verify_handoff.verify_runtime_handoff(_make_pack_dir(tmp_path))

    assert result.question_count == 30
    assert result.media_count == 30


def test_verify_runtime_handoff_rejects_missing_media(tmp_path: Path) -> None:
    pack_dir = _make_pack_dir(tmp_path)
    (pack_dir / "media" / "img1.jpg").unlink()

    with pytest.raises(verify_handoff.HandoffVerificationError, match="Missing runtime media"):
        verify_handoff.verify_runtime_handoff(pack_dir)


def test_verify_runtime_handoff_rejects_failed_validation(tmp_path: Path) -> None:
    pack_dir = _make_pack_dir(tmp_path)
    validation_path = pack_dir / "validation_report.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    validation["status"] = "failed"
    _write_json(validation_path, validation)

    with pytest.raises(verify_handoff.HandoffVerificationError, match="status"):
        verify_handoff.verify_runtime_handoff(pack_dir)


def test_verify_runtime_handoff_rejects_partial_pack(tmp_path: Path) -> None:
    pack_dir = _make_pack_dir(tmp_path)
    _write_json(pack_dir / "failed_build" / "partial_pack.json", {"partial": True})

    with pytest.raises(verify_handoff.HandoffVerificationError, match="partial_pack"):
        verify_handoff.verify_runtime_handoff(pack_dir)


def test_verify_runtime_handoff_rejects_remote_runtime_uri(tmp_path: Path) -> None:
    pack_dir = _make_pack_dir(tmp_path)
    pack_path = pack_dir / "pack.json"
    pack = json.loads(pack_path.read_text(encoding="utf-8"))
    pack["media"][0]["runtime_uri"] = "https://example.org/img.jpg"
    _write_json(pack_path, pack)
    manifest = json.loads((pack_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["checksums"]["pack.json"]["sha256"] = _sha256(pack_path)
    _write_json(pack_dir / "manifest.json", manifest)

    with pytest.raises(verify_handoff.HandoffVerificationError, match="Invalid runtime media"):
        verify_handoff.verify_runtime_handoff(pack_dir)


def test_export_runtime_handoff_copies_runtime_payload_only_by_default(tmp_path: Path) -> None:
    pack_dir = _make_pack_dir(tmp_path)
    out = tmp_path / "runtime-pack"

    exported = export_handoff.export_runtime_handoff(pack_dir=pack_dir, output_dir=out)

    assert exported == out
    assert (out / "pack.json").exists()
    assert len(list((out / "media").glob("*"))) == 30
    assert not (out / "audit").exists()


def test_export_runtime_handoff_can_include_audit_files(tmp_path: Path) -> None:
    pack_dir = _make_pack_dir(tmp_path)
    out = tmp_path / "runtime-pack"

    export_handoff.export_runtime_handoff(
        pack_dir=pack_dir,
        output_dir=out,
        include_audit=True,
    )

    assert (out / "audit" / "manifest.json").exists()
    assert (out / "audit" / "validation_report.json").exists()
