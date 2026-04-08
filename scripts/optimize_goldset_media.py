from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

from PIL import Image, UnidentifiedImageError

DEFAULT_MANIFEST_PATH = Path("data/goldset/birds_v1/manifest.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Optimize Gold set media files in-place.")
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    args = parser.parse_args()

    manifest_path: Path = args.manifest_path
    root = manifest_path.parent
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    converted_count = 0
    bytes_before = 0
    bytes_after = 0

    for taxon in payload.get("taxa", []):
        images = taxon.get("images", [])
        if not isinstance(images, list):
            continue
        for image in images:
            image_path = str(image.get("image_path") or "")
            if not image_path.endswith(".gif"):
                continue
            source = root / image_path
            if not source.exists():
                continue
            original = source.read_bytes()
            bytes_before += len(original)
            converted = _convert_gif_to_jpeg(original)
            target = source.with_suffix(".jpg")
            target.write_bytes(converted)
            source.unlink(missing_ok=True)

            image["image_path"] = target.relative_to(root).as_posix()
            image["sha256"] = f"sha256:{hashlib.sha256(converted).hexdigest()}"
            converted_count += 1
            bytes_after += len(converted)

    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "goldset optimize complete | "
        f"converted={converted_count} | bytes_before={bytes_before} | bytes_after={bytes_after}"
    )
    return 0


def _convert_gif_to_jpeg(raw: bytes) -> bytes:
    try:
        with Image.open(io.BytesIO(raw)) as image:
            first_frame = image.convert("RGB")
            buffer = io.BytesIO()
            first_frame.save(buffer, format="JPEG", quality=82, optimize=True, progressive=True)
            return buffer.getvalue()
    except (OSError, UnidentifiedImageError) as exc:
        raise RuntimeError(f"cannot convert gif to jpeg: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
