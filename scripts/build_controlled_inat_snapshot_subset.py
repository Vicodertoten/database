#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from database_core.adapters.inaturalist_snapshot import (
    DEFAULT_INAT_SNAPSHOT_ROOT,
    load_snapshot_manifest,
    write_snapshot_manifest,
)

SUBSET_AUDIT_FILENAME = "subset_audit.json"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a deterministic subset snapshot from an existing iNaturalist snapshot."
    )
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--output-snapshot-id", required=True)
    parser.add_argument("--max-media-count", type=int, required=True)
    parser.add_argument("--max-media-per-taxon", type=int)
    parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_INAT_SNAPSHOT_ROOT)
    return parser.parse_args()


def build_controlled_inat_snapshot_subset(
    *,
    snapshot_id: str,
    output_snapshot_id: str,
    max_media_count: int,
    max_media_per_taxon: int | None = None,
    snapshot_root: Path = DEFAULT_INAT_SNAPSHOT_ROOT,
) -> dict[str, object]:
    if max_media_count <= 0:
        raise ValueError("max_media_count must be > 0")
    if max_media_per_taxon is not None and max_media_per_taxon <= 0:
        raise ValueError("max_media_per_taxon must be > 0 when provided")

    manifest, snapshot_dir = load_snapshot_manifest(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
    )
    output_dir = snapshot_root / output_snapshot_id
    if output_dir.exists():
        raise ValueError(f"Output snapshot already exists: {output_dir}")

    media_download_by_id = {item.source_media_id: item for item in manifest.media_downloads}
    candidate_rows: list[dict[str, object]] = []
    response_payloads: dict[str, dict[str, object]] = {}

    for seed in sorted(manifest.taxon_seeds, key=lambda item: item.canonical_taxon_id):
        response_path = snapshot_dir / seed.response_path
        payload = json.loads(response_path.read_text(encoding="utf-8"))
        response_payloads[seed.response_path] = payload
        for result in payload.get("results", []):
            if not isinstance(result, dict):
                continue
            photos = result.get("photos")
            if not isinstance(photos, list) or not photos:
                continue
            primary = photos[0]
            if not isinstance(primary, dict):
                continue
            media_id = str(primary.get("id") or "").strip()
            if not media_id or media_id not in media_download_by_id:
                continue
            candidate_rows.append(
                {
                    "canonical_taxon_id": seed.canonical_taxon_id,
                    "response_path": seed.response_path,
                    "media_id": media_id,
                    "result": result,
                }
            )

    candidate_rows.sort(
        key=lambda item: (
            str(item["media_id"]),
            str(item["canonical_taxon_id"]),
            str(item["response_path"]),
        )
    )

    selected_media_ids: set[str] = set()
    selected_taxa: set[str] = set()
    per_taxon_counter: Counter[str] = Counter()
    selected_results_by_response: dict[str, list[dict[str, object]]] = {}

    for candidate in candidate_rows:
        if len(selected_media_ids) >= max_media_count:
            break
        canonical_taxon_id = str(candidate["canonical_taxon_id"])
        if (
            max_media_per_taxon is not None
            and per_taxon_counter[canonical_taxon_id] >= max_media_per_taxon
        ):
            continue
        media_id = str(candidate["media_id"])
        if media_id in selected_media_ids:
            continue
        selected_media_ids.add(media_id)
        selected_taxa.add(canonical_taxon_id)
        per_taxon_counter[canonical_taxon_id] += 1
        selected_results_by_response.setdefault(
            str(candidate["response_path"]),
            [],
        ).append(candidate["result"])

    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "responses").mkdir(parents=True, exist_ok=True)
    (output_dir / "taxa").mkdir(parents=True, exist_ok=True)
    (output_dir / "images").mkdir(parents=True, exist_ok=True)

    selected_seeds = [
        seed for seed in manifest.taxon_seeds if seed.canonical_taxon_id in selected_taxa
    ]
    for seed in selected_seeds:
        payload = response_payloads.get(seed.response_path, {"results": []})
        filtered_payload = dict(payload)
        filtered_payload["results"] = selected_results_by_response.get(seed.response_path, [])
        destination_response = output_dir / seed.response_path
        destination_response.parent.mkdir(parents=True, exist_ok=True)
        destination_response.write_text(
            json.dumps(filtered_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if seed.taxon_payload_path:
            source_taxon_path = snapshot_dir / seed.taxon_payload_path
            if source_taxon_path.exists():
                destination_taxon = output_dir / seed.taxon_payload_path
                destination_taxon.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_taxon_path, destination_taxon)

    selected_downloads = [
        item for item in manifest.media_downloads if item.source_media_id in selected_media_ids
    ]
    for item in selected_downloads:
        source_image = snapshot_dir / item.image_path
        if source_image.exists():
            destination_image = output_dir / item.image_path
            destination_image.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_image, destination_image)

    subset_manifest = manifest.model_copy(
        update={
            "snapshot_id": output_snapshot_id,
            "created_at": datetime.now(UTC),
            "taxon_seeds": selected_seeds,
            "media_downloads": selected_downloads,
            "ai_outputs_path": None,
        }
    )
    write_snapshot_manifest(output_dir, subset_manifest)

    audit = {
        "source_snapshot_id": snapshot_id,
        "output_snapshot_id": output_snapshot_id,
        "selection_strategy": "sorted_by_source_media_id_then_taxon",
        "max_media_count": max_media_count,
        "max_media_per_taxon": max_media_per_taxon,
        "selected_media_count": len(selected_downloads),
        "selected_taxon_count": len(selected_taxa),
        "selected_media_count_by_taxon": dict(sorted(per_taxon_counter.items())),
    }
    (output_dir / SUBSET_AUDIT_FILENAME).write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return audit


def main() -> None:
    args = _parse_args()
    audit = build_controlled_inat_snapshot_subset(
        snapshot_id=args.snapshot_id,
        output_snapshot_id=args.output_snapshot_id,
        max_media_count=args.max_media_count,
        max_media_per_taxon=args.max_media_per_taxon,
        snapshot_root=args.snapshot_root,
    )
    print(
        "Built controlled subset"
        f" | source_snapshot_id={audit['source_snapshot_id']}"
        f" | output_snapshot_id={audit['output_snapshot_id']}"
        f" | selected_media_count={audit['selected_media_count']}"
    )


if __name__ == "__main__":
    main()
