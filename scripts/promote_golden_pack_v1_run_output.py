from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CANONICAL_EXPORT_DIR = REPO_ROOT / "data" / "exports" / "golden_packs" / "belgian_birds_mvp_v1"


class PromotionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromotionConfig:
    run_output_dir: Path
    canonical_export_dir: Path = DEFAULT_CANONICAL_EXPORT_DIR


REQUIRED_FILES = (
    "validation_report.json",
    "manifest.json",
    "pack.json",
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PromotionError(f"Missing required file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PromotionError(f"JSON object expected: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _assert_passed(validation_report: dict[str, Any], run_output_dir: Path) -> None:
    status = str(validation_report.get("status") or "")
    if status != "passed":
        raise PromotionError(
            f"Refusing promotion: validation_report.status={status!r} (expected 'passed') for {run_output_dir}"
        )
    schema_validity = validation_report.get("schema_validity")
    if not isinstance(schema_validity, dict) or not all(
        schema_validity.get(key) is True
        for key in (
            "manifest_schema_valid",
            "pack_schema_valid",
            "validation_report_schema_valid",
        )
    ):
        raise PromotionError("Refusing promotion: schema_validity is not fully true")


def _assert_no_partial_only(run_output_dir: Path) -> None:
    pack_path = run_output_dir / "pack.json"
    partial_path = run_output_dir / "failed_build" / "partial_pack.json"
    if not pack_path.exists() and partial_path.exists():
        raise PromotionError(
            "Refusing promotion: failed_build/partial_pack.json exists without runtime pack.json"
        )


def _assert_required_paths(run_output_dir: Path) -> None:
    for rel in REQUIRED_FILES:
        path = run_output_dir / rel
        if not path.exists():
            raise PromotionError(f"Missing required promotion artifact: {path}")
    media_dir = run_output_dir / "media"
    if not media_dir.exists() or not media_dir.is_dir():
        raise PromotionError(f"Missing required media directory: {media_dir}")


def _assert_manifest_checksums(manifest: dict[str, Any], run_output_dir: Path) -> None:
    checksums = manifest.get("checksums") if isinstance(manifest.get("checksums"), dict) else {}

    def expected_sha(name: str) -> str | None:
        entry = checksums.get(name)
        if isinstance(entry, dict):
            raw = entry.get("sha256")
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
        return None

    for rel in ("pack.json", "validation_report.json"):
        expected = expected_sha(rel)
        if not expected:
            continue
        actual = _sha256_file(run_output_dir / rel)
        if actual != expected:
            raise PromotionError(
                f"Checksum mismatch for {rel}: expected={expected} actual={actual}"
            )

    media_entries = checksums.get("media_files")
    if not isinstance(media_entries, list):
        return
    for row in media_entries:
        if not isinstance(row, dict):
            continue
        rel = row.get("path")
        expected = row.get("sha256")
        if not isinstance(rel, str) or not rel.strip() or not isinstance(expected, str) or not expected.strip():
            continue
        media_path = run_output_dir / rel
        if not media_path.exists():
            raise PromotionError(f"Missing media referenced by manifest checksum: {media_path}")
        actual = _sha256_file(media_path)
        if actual != expected:
            raise PromotionError(
                f"Checksum mismatch for {rel}: expected={expected} actual={actual}"
            )


def _copy_to_staging(run_output_dir: Path, staging_dir: Path) -> None:
    for rel in REQUIRED_FILES:
        src = run_output_dir / rel
        dst = staging_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    src_media = run_output_dir / "media"
    dst_media = staging_dir / "media"
    shutil.copytree(src_media, dst_media)


def promote_run_output(config: PromotionConfig) -> Path:
    run_output_dir = config.run_output_dir
    canonical_export_dir = config.canonical_export_dir

    _assert_no_partial_only(run_output_dir)
    _assert_required_paths(run_output_dir)

    validation_report = _load_json(run_output_dir / "validation_report.json")
    _assert_passed(validation_report, run_output_dir)

    manifest = _load_json(run_output_dir / "manifest.json")
    _assert_manifest_checksums(manifest, run_output_dir)

    canonical_export_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{canonical_export_dir.name}_staging_", dir=str(canonical_export_dir.parent)) as tmp:
        staging_dir = Path(tmp)
        _copy_to_staging(run_output_dir, staging_dir)

        if canonical_export_dir.exists():
            shutil.rmtree(canonical_export_dir)
        shutil.move(str(staging_dir), str(canonical_export_dir))

    return canonical_export_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-output-dir", type=Path, required=True)
    parser.add_argument("--canonical-export-dir", type=Path, default=DEFAULT_CANONICAL_EXPORT_DIR)
    args = parser.parse_args()

    promoted = promote_run_output(
        PromotionConfig(
            run_output_dir=args.run_output_dir,
            canonical_export_dir=args.canonical_export_dir,
        )
    )
    print(f"Promotion successful: {promoted}")


if __name__ == "__main__":
    main()
