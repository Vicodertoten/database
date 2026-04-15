from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

from database_core.adapters.inaturalist_qualification import (
    DEFAULT_INITIAL_BACKOFF_SECONDS,
    DEFAULT_MAX_BACKOFF_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_REQUEST_INTERVAL_SECONDS,
    qualify_inat_snapshot,
)
from database_core.adapters.inaturalist_snapshot import (
    DEFAULT_INAT_SNAPSHOT_ROOT,
    InaturalistSnapshotManifest,
    SnapshotMediaDownload,
    SnapshotTaxonSeed,
    write_snapshot_manifest,
)
from database_core.domain.canonical_ids import next_canonical_taxon_id
from database_core.domain.enums import CanonicalRank, SourceName, TaxonGroup, TaxonStatus
from database_core.pipeline.runner import run_pipeline
from database_core.qualification.ai import (
    DEFAULT_GEMINI_MODEL,
    MIN_AI_IMAGE_HEIGHT,
    MIN_AI_IMAGE_WIDTH,
    inspect_image_dimensions,
)
from database_core.security import redact_database_url
from database_core.storage.postgres import PostgresRepository

DEFAULT_GOLDSET_MANIFEST_PATH = Path("data/goldset/birds_v1/manifest.json")
DEFAULT_PILOT_TAXA_PATH = Path("data/fixtures/inaturalist_pilot_taxa.json")


def main() -> int:
    load_dotenv(dotenv_path=Path(".env"))
    parser = argparse.ArgumentParser(
        description="Run full live pipeline on goldset (Gemini qualification + pipeline export)."
    )
    parser.add_argument("--goldset-manifest", type=Path, default=DEFAULT_GOLDSET_MANIFEST_PATH)
    parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_INAT_SNAPSHOT_ROOT)
    parser.add_argument("--snapshot-id", type=str)
    parser.add_argument("--gemini-api-key-env", default="GEMINI_API_KEY")
    parser.add_argument("--gemini-model", default=DEFAULT_GEMINI_MODEL)
    parser.add_argument(
        "--request-interval-seconds",
        type=float,
        default=DEFAULT_REQUEST_INTERVAL_SECONDS,
    )
    parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    parser.add_argument(
        "--initial-backoff-seconds",
        type=float,
        default=DEFAULT_INITIAL_BACKOFF_SECONDS,
    )
    parser.add_argument("--max-backoff-seconds", type=float, default=DEFAULT_MAX_BACKOFF_SECONDS)
    parser.add_argument("--uncertain-policy", choices=["review", "reject"], default="reject")
    parser.add_argument(
        "--allow-insufficient-resolution",
        action="store_true",
        help="continue even if snapshot contains images below Gemini minimum resolution",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    gemini_api_key = os.environ.get(args.gemini_api_key_env)
    if not gemini_api_key:
        raise SystemExit(f"Missing Gemini API key in env var {args.gemini_api_key_env}")

    snapshot_id = args.snapshot_id or _default_snapshot_id()
    snapshot_dir = args.snapshot_root / snapshot_id
    if snapshot_dir.exists():
        if not args.force:
            raise SystemExit(
                f"Snapshot directory already exists: {snapshot_dir}. "
                "Use --force to recreate."
            )
        shutil.rmtree(snapshot_dir)

    payload = json.loads(args.goldset_manifest.read_text(encoding="utf-8"))
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    (snapshot_dir / "responses").mkdir(parents=True, exist_ok=True)
    (snapshot_dir / "images").mkdir(parents=True, exist_ok=True)
    (snapshot_dir / "taxa").mkdir(parents=True, exist_ok=True)

    canonical_by_source_taxon_id = _resolve_canonical_mapping(payload)

    taxon_seeds: list[SnapshotTaxonSeed] = []
    media_downloads: list[SnapshotMediaDownload] = []

    for taxon in payload.get("taxa", []):
        scientific_name = str(taxon["scientific_name"])
        source_taxon_id = str(taxon["source_taxon_id"])
        canonical_taxon_id = canonical_by_source_taxon_id[source_taxon_id]
        response_path = f"responses/{_slugify_filename(canonical_taxon_id)}.json"
        result_entries: list[dict[str, object]] = []

        for image in taxon.get("images", []):
            observation_id = str(image["source_observation_id"])
            media_id = str(image["source_media_id"])
            source_url = str(image["source_url"])
            source_license = str(image.get("license_code") or "cc-by")
            photo_license = str(image.get("photo_license_code") or source_license)
            observed_on = image.get("observed_on")
            relative_source_image_path = Path(str(image["image_path"]))
            source_image_path = args.goldset_manifest.parent / relative_source_image_path
            extension = source_image_path.suffix.lstrip(".").lower() or _guess_extension(source_url)
            destination_relative = Path("images") / f"{media_id}.{extension}"
            destination_path = snapshot_dir / destination_relative
            _link_or_copy(source_image_path, destination_path)

            media_downloads.append(
                SnapshotMediaDownload(
                    source_observation_id=observation_id,
                    source_media_id=media_id,
                    image_path=destination_relative.as_posix(),
                    download_status="downloaded",
                    source_url=source_url,
                    mime_type=_guess_mime_type(source_url),
                    sha256=str(image.get("sha256")) if image.get("sha256") else None,
                    downloaded_width=(
                        int(image["downloaded_width"])
                        if image.get("downloaded_width") is not None
                        else None
                    ),
                    downloaded_height=(
                        int(image["downloaded_height"])
                        if image.get("downloaded_height") is not None
                        else None
                    ),
                    downloaded_variant=str(image.get("downloaded_variant"))
                    if image.get("downloaded_variant")
                    else None,
                    file_size_bytes=destination_path.stat().st_size,
                )
            )

            result_entries.append(
                {
                    "id": int(observation_id) if observation_id.isdigit() else observation_id,
                    "quality_grade": "research",
                    "license_code": source_license,
                    "captive": None,
                    "observed_on": observed_on,
                    "taxon": {
                        "id": (
                            int(source_taxon_id)
                            if source_taxon_id.isdigit()
                            else source_taxon_id
                        ),
                        "ancestor_ids": [
                            int(source_taxon_id)
                            if source_taxon_id.isdigit()
                            else source_taxon_id
                        ],
                    },
                    "photos": [
                        {
                            "id": int(media_id) if media_id.isdigit() else media_id,
                            "license_code": photo_license,
                            "original_url": source_url,
                            "url": source_url,
                        }
                    ],
                }
            )

        (snapshot_dir / response_path).write_text(
            json.dumps({"results": result_entries}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        taxon_seeds.append(
            SnapshotTaxonSeed(
                canonical_taxon_id=canonical_taxon_id,
                accepted_scientific_name=scientific_name,
                canonical_rank=CanonicalRank.SPECIES,
                taxon_status=TaxonStatus.ACTIVE,
                authority_source=SourceName.INATURALIST,
                display_slug=_scientific_name_slug(scientific_name),
                synonyms=[],
                common_names=[],
                source_taxon_id=source_taxon_id,
                query_params={"source": "goldset.birds.v1", "mode": "live_e2e"},
                response_path=response_path,
                taxon_payload_path=None,
                requested_order_by=str(taxon.get("requested_order_by") or "votes"),
                effective_order_by=str(taxon.get("effective_order_by") or "votes"),
                fallback_applied=bool(
                    taxon.get("requested_order_by")
                    and taxon.get("effective_order_by")
                    and taxon["requested_order_by"] != taxon["effective_order_by"]
                ),
            )
        )

    manifest = InaturalistSnapshotManifest(
        snapshot_id=snapshot_id,
        source_name=SourceName.INATURALIST,
        created_at=datetime.now(UTC),
        taxon_seeds=sorted(taxon_seeds, key=lambda item: item.canonical_taxon_id),
        media_downloads=sorted(media_downloads, key=lambda item: item.source_media_id),
        ai_outputs_path=None,
    )
    write_snapshot_manifest(snapshot_dir, manifest)

    low_resolution_images = _find_low_resolution_images(
        media_downloads=manifest.media_downloads,
        snapshot_dir=snapshot_dir,
    )
    if low_resolution_images and not args.allow_insufficient_resolution:
        preview = ", ".join(low_resolution_images[:5])
        raise SystemExit(
            "Goldset snapshot has images below Gemini minimum resolution "
            f"({MIN_AI_IMAGE_WIDTH}x{MIN_AI_IMAGE_HEIGHT}). "
            f"count={len(low_resolution_images)}; samples={preview}. "
            "Rebuild goldset at higher resolution or rerun with --allow-insufficient-resolution."
        )

    qualification_result = qualify_inat_snapshot(
        snapshot_id=snapshot_id,
        snapshot_root=args.snapshot_root,
        gemini_api_key=gemini_api_key,
        gemini_model=args.gemini_model,
        request_interval_seconds=args.request_interval_seconds,
        max_retries=args.max_retries,
        initial_backoff_seconds=args.initial_backoff_seconds,
        max_backoff_seconds=args.max_backoff_seconds,
    )

    pipeline_result = run_pipeline(
        source_mode="inat_snapshot",
        snapshot_id=snapshot_id,
        snapshot_root=args.snapshot_root,
        qualifier_mode="cached",
        uncertain_policy=args.uncertain_policy,
    )
    repository = PostgresRepository(pipeline_result.database_url)
    repository.initialize()
    summary = repository.fetch_summary()

    print(
        "goldset live pipeline complete | "
        f"snapshot_id={snapshot_id} | "
        f"processed={qualification_result.processed_media_count} | "
        f"ai_ok={qualification_result.ai_valid_output_count} | "
        f"qualified={pipeline_result.qualified_resource_count} | "
        f"exportable={pipeline_result.exportable_resource_count} | "
        f"review={pipeline_result.review_queue_count}"
    )
    print(
        "goldset live artifacts | "
        f"snapshot_dir={snapshot_dir} | "
        f"database_url={redact_database_url(pipeline_result.database_url)} | "
        f"normalized={pipeline_result.normalized_snapshot_path} | "
        f"qualified={pipeline_result.qualification_snapshot_path} | "
        f"export={pipeline_result.export_path}"
    )
    print(
        "goldset live db summary | "
        f"canonical_taxa={summary['canonical_taxa']} | "
        f"source_observations={summary['source_observations']} | "
        f"media_assets={summary['media_assets']} | "
        f"qualified_resources={summary['qualified_resources']} | "
        f"review_queue={summary['review_queue']}"
    )
    return 0


def _default_snapshot_id() -> str:
    return f"goldset-birds-v1-live-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"


def _resolve_canonical_mapping(payload: dict[str, object]) -> dict[str, str]:
    fixtures = json.loads(DEFAULT_PILOT_TAXA_PATH.read_text(encoding="utf-8"))
    mapping: dict[str, str] = {}
    existing_ids: set[str] = set()
    for item in fixtures:
        source_taxon_id = str(item.get("source_taxon_id") or "")
        canonical_taxon_id = str(item.get("canonical_taxon_id") or "")
        if not source_taxon_id or not canonical_taxon_id:
            continue
        mapping[source_taxon_id] = canonical_taxon_id
        existing_ids.add(canonical_taxon_id)

    missing_taxa: list[tuple[str, str]] = []
    for taxon in payload.get("taxa", []):
        source_taxon_id = str(taxon["source_taxon_id"])
        scientific_name = str(taxon["scientific_name"])
        if source_taxon_id not in mapping:
            missing_taxa.append((scientific_name, source_taxon_id))

    for _, source_taxon_id in sorted(missing_taxa):
        canonical_taxon_id = next_canonical_taxon_id(
            existing_ids=existing_ids,
            group=TaxonGroup.BIRDS,
        )
        mapping[source_taxon_id] = canonical_taxon_id
        existing_ids.add(canonical_taxon_id)
    return mapping


def _link_or_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    try:
        os.link(source, destination)
    except OSError:
        shutil.copy2(source, destination)


def _scientific_name_slug(value: str) -> str:
    return "-".join(part for part in value.lower().replace("_", " ").split(" ") if part)


def _guess_extension(url: str) -> str:
    path = urlparse(url).path
    if "." not in path:
        return "jpg"
    return path.rsplit(".", 1)[-1].lower()


def _guess_mime_type(url: str) -> str | None:
    extension = _guess_extension(url)
    if extension in {"jpg", "jpeg"}:
        return "image/jpeg"
    if extension == "png":
        return "image/png"
    if extension == "webp":
        return "image/webp"
    if extension == "gif":
        return "image/gif"
    return None


def _slugify_filename(value: str) -> str:
    return value.replace(":", "_").replace("-", "_")


def _find_low_resolution_images(
    *,
    media_downloads: list[SnapshotMediaDownload],
    snapshot_dir: Path,
) -> list[str]:
    low_resolution_media_ids: list[str] = []
    for item in media_downloads:
        width = item.downloaded_width
        height = item.downloaded_height
        if width is None or height is None:
            width, height = inspect_image_dimensions(snapshot_dir / item.image_path)
        if (
            width is None
            or height is None
            or width < MIN_AI_IMAGE_WIDTH
            or height < MIN_AI_IMAGE_HEIGHT
        ):
            low_resolution_media_ids.append(item.source_media_id)
    return low_resolution_media_ids


if __name__ == "__main__":
    raise SystemExit(main())
