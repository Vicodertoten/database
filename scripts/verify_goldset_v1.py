from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_MANIFEST_PATH = Path("data/goldset/birds_v1/manifest.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Gold set birds v1 integrity.")
    parser.add_argument("--manifest-path", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--expected-taxa", type=int, default=20)
    parser.add_argument("--expected-images-per-taxon", type=int, default=5)
    args = parser.parse_args()

    payload = json.loads(args.manifest_path.read_text(encoding="utf-8"))
    expected_total_images = args.expected_taxa * args.expected_images_per_taxon
    errors: list[str] = []

    taxa = payload.get("taxa")
    if not isinstance(taxa, list):
        raise SystemExit("invalid goldset manifest: `taxa` must be a list")
    if len(taxa) != args.expected_taxa:
        errors.append(
            f"expected {args.expected_taxa} taxa but found {len(taxa)} "
            f"(manifest={args.manifest_path})"
        )

    unique_media_ids: set[str] = set()
    image_count = 0
    for taxon in taxa:
        scientific_name = str(taxon.get("scientific_name") or "<unknown>")
        images = taxon.get("images")
        if not isinstance(images, list):
            errors.append(f"{scientific_name}: `images` must be a list")
            continue
        if len(images) != args.expected_images_per_taxon:
            errors.append(
                f"{scientific_name}: expected {args.expected_images_per_taxon} images, got {len(images)}"
            )
        for image in images:
            source_media_id = str(image.get("source_media_id") or "").strip()
            image_path = str(image.get("image_path") or "").strip()
            if not source_media_id:
                errors.append(f"{scientific_name}: missing source_media_id")
                continue
            if source_media_id in unique_media_ids:
                errors.append(f"{scientific_name}: duplicated source_media_id={source_media_id}")
            unique_media_ids.add(source_media_id)
            if not image_path:
                errors.append(f"{scientific_name}: missing image_path for media={source_media_id}")
                continue
            resolved_path = args.manifest_path.parent / image_path
            if not resolved_path.exists():
                errors.append(
                    f"{scientific_name}: missing file {resolved_path} for media={source_media_id}"
                )
            image_count += 1

    declared_total_images = int(payload.get("total_images") or 0)
    if declared_total_images != expected_total_images:
        errors.append(
            f"manifest total_images mismatch: expected {expected_total_images}, got {declared_total_images}"
        )
    if image_count != expected_total_images:
        errors.append(f"materialized image count mismatch: expected {expected_total_images}, got {image_count}")
    if len(unique_media_ids) != expected_total_images:
        errors.append(
            f"unique media count mismatch: expected {expected_total_images}, got {len(unique_media_ids)}"
        )

    if errors:
        for item in errors:
            print(f"- {item}")
        raise SystemExit(1)

    print(
        "goldset verification passed | "
        f"taxa={len(taxa)} | images={image_count} | manifest={args.manifest_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
