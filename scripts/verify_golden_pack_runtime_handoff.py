from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import materialize_golden_pack_belgian_birds_mvp_v1 as mat


class HandoffVerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class HandoffVerificationResult:
    pack_dir: Path
    question_count: int
    media_count: int


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise HandoffVerificationError(f"Missing required file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise HandoffVerificationError(f"JSON object expected: {path}")
    return payload


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_label(value: object) -> bool:
    label = str(value or "").strip()
    if not label:
        return False
    normalized = mat.normalize_localized_name_for_compare(label)
    return bool(normalized) and normalized not in {
        "unknown",
        "inconnu",
        "non renseigne",
        "non renseigné",
        "n/a",
        "na",
    }


def _assert_checksum(manifest: dict[str, Any], pack_dir: Path) -> None:
    checksums = manifest.get("checksums")
    if not isinstance(checksums, dict):
        raise HandoffVerificationError("manifest.checksums must be present")
    for rel in ("pack.json", "validation_report.json"):
        expected = (checksums.get(rel) or {}).get("sha256")
        if isinstance(expected, str) and expected:
            actual = _sha256_file(pack_dir / rel)
            if actual != expected:
                raise HandoffVerificationError(
                    f"Checksum mismatch for {rel}: expected={expected} actual={actual}"
                )
    media_entries = checksums.get("media_files")
    if not isinstance(media_entries, list):
        raise HandoffVerificationError("manifest.checksums.media_files must be present")
    for row in media_entries:
        if not isinstance(row, dict):
            continue
        rel = row.get("path")
        expected = row.get("sha256")
        if not isinstance(rel, str) or not isinstance(expected, str):
            continue
        media_path = pack_dir / rel
        if not media_path.exists():
            raise HandoffVerificationError(f"Missing checksummed media file: {rel}")
        actual = _sha256_file(media_path)
        if actual != expected:
            raise HandoffVerificationError(
                f"Checksum mismatch for {rel}: expected={expected} actual={actual}"
            )


def verify_runtime_handoff(pack_dir: Path) -> HandoffVerificationResult:
    pack_path = pack_dir / "pack.json"
    manifest_path = pack_dir / "manifest.json"
    validation_path = pack_dir / "validation_report.json"
    partial_path = pack_dir / "failed_build" / "partial_pack.json"
    media_dir = pack_dir / "media"
    if partial_path.exists():
        raise HandoffVerificationError("failed_build/partial_pack.json must not be present")
    if not media_dir.is_dir():
        raise HandoffVerificationError(f"Missing media directory: {media_dir}")

    pack = _load_json(pack_path)
    manifest = _load_json(manifest_path)
    validation = _load_json(validation_path)
    if validation.get("status") != "passed":
        raise HandoffVerificationError("validation_report.status must be passed")
    schema_validity = validation.get("schema_validity")
    if not isinstance(schema_validity, dict) or not all(schema_validity.values()):
        raise HandoffVerificationError("validation_report.schema_validity must be fully true")
    if pack.get("schema_version") != "golden_pack.v1":
        raise HandoffVerificationError("pack.schema_version must be golden_pack.v1")

    media_rows = pack.get("media")
    questions = pack.get("questions")
    if not isinstance(media_rows, list) or len(media_rows) != 30:
        raise HandoffVerificationError("pack.media must contain exactly 30 rows")
    if not isinstance(questions, list) or len(questions) != 30:
        raise HandoffVerificationError("pack.questions must contain exactly 30 rows")

    media_by_id: dict[str, dict[str, Any]] = {}
    for row in media_rows:
        if not isinstance(row, dict):
            raise HandoffVerificationError("pack.media rows must be objects")
        media_id = str(row.get("media_id") or "")
        runtime_uri = str(row.get("runtime_uri") or "")
        if not media_id or not runtime_uri.startswith("media/"):
            raise HandoffVerificationError(f"Invalid runtime media row: {row}")
        if not (pack_dir / runtime_uri).exists():
            raise HandoffVerificationError(f"Missing runtime media file: {runtime_uri}")
        media_by_id[media_id] = row

    for question in questions:
        if not isinstance(question, dict):
            raise HandoffVerificationError("pack.questions rows must be objects")
        if question.get("primary_media_id") not in media_by_id:
            raise HandoffVerificationError(
                f"Question references missing primary media: {question.get('question_id')}"
            )
        options = question.get("options")
        if not isinstance(options, list) or len(options) != 4:
            raise HandoffVerificationError("Each question must have exactly 4 options")
        correct_count = sum(1 for option in options if isinstance(option, dict) and option.get("is_correct") is True)
        if correct_count != 1:
            raise HandoffVerificationError("Each question must have exactly 1 correct option")
        distractor_count = sum(1 for option in options if isinstance(option, dict) and option.get("is_correct") is False)
        if distractor_count != 3:
            raise HandoffVerificationError("Each question must have exactly 3 distractors")
        for option in options:
            if not isinstance(option, dict) or not _safe_label(option.get("display_label")):
                raise HandoffVerificationError("Every option must have a runtime-safe display_label")

    _assert_checksum(manifest, pack_dir)
    return HandoffVerificationResult(
        pack_dir=pack_dir,
        question_count=len(questions),
        media_count=len(media_rows),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pack-dir",
        type=Path,
        default=Path("data/exports/golden_packs/belgian_birds_mvp_v1"),
    )
    args = parser.parse_args()
    result = verify_runtime_handoff(args.pack_dir)
    print(
        "Runtime handoff verified: "
        f"pack_dir={result.pack_dir} questions={result.question_count} media={result.media_count}"
    )


if __name__ == "__main__":
    main()
