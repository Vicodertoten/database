from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from database_core.adapters.inaturalist_snapshot import (
    DEFAULT_INAT_SNAPSHOT_ROOT,
    DEFAULT_PILOT_TAXA_PATH,
    InaturalistSnapshotManifest,
    SnapshotMediaDownload,
    SnapshotTaxonSeed,
    load_pilot_taxa,
    resolve_snapshot_dir,
)
from database_core.export.json_exporter import write_json

INAT_OBSERVATIONS_API = "https://api.inaturalist.org/v1/observations"
USER_AGENT = "database-core/0.1"


@dataclass(frozen=True)
class HarvestResult:
    snapshot_id: str
    snapshot_dir: Path
    harvested_observation_count: int
    downloaded_image_count: int


def fetch_inat_snapshot(
    *,
    snapshot_id: str,
    snapshot_root: Path = DEFAULT_INAT_SNAPSHOT_ROOT,
    pilot_taxa_path: Path = DEFAULT_PILOT_TAXA_PATH,
    max_observations_per_taxon: int = 5,
    timeout_seconds: int = 30,
) -> HarvestResult:
    snapshot_dir = resolve_snapshot_dir(snapshot_id, snapshot_root)
    responses_dir = snapshot_dir / "responses"
    images_dir = snapshot_dir / "images"
    responses_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)

    manifest_taxa: list[SnapshotTaxonSeed] = []
    media_downloads: list[SnapshotMediaDownload] = []
    harvested_observation_count = 0
    downloaded_image_count = 0

    for seed in load_pilot_taxa(pilot_taxa_path):
        params = {
            "taxon_id": seed.source_taxon_id,
            "quality_grade": "research",
            "photos": "true",
            "per_page": str(max_observations_per_taxon),
            "order_by": "created_at",
            "order": "desc",
        }
        response_payload = _fetch_json(INAT_OBSERVATIONS_API, params=params, timeout_seconds=timeout_seconds)
        candidate_results = [
            item
            for item in response_payload.get("results", [])
            if item.get("quality_grade") == "research" and item.get("photos")
        ][:max_observations_per_taxon]
        response_payload["results"] = candidate_results

        response_path = Path("responses") / f"{_slugify_filename(seed.canonical_taxon_id)}.json"
        write_json(snapshot_dir / response_path, response_payload)
        manifest_taxa.append(
            SnapshotTaxonSeed(
                canonical_taxon_id=seed.canonical_taxon_id,
                scientific_name=seed.scientific_name,
                canonical_rank=seed.canonical_rank,
                common_names=seed.common_names,
                source_taxon_id=seed.source_taxon_id,
                query_params=params,
                response_path=response_path.as_posix(),
            )
        )

        for result in candidate_results:
            harvested_observation_count += 1
            photo = result["photos"][0]
            photo_url = _photo_source_url(photo)
            extension = _guess_extension(photo_url) or "jpg"
            image_path = Path("images") / f"{photo['id']}.{extension}"
            download_status = "downloaded"
            sha256 = None
            try:
                image_bytes = _fetch_bytes(photo_url, timeout_seconds=timeout_seconds)
                (snapshot_dir / image_path).write_bytes(image_bytes)
                sha256 = f"sha256:{hashlib.sha256(image_bytes).hexdigest()}"
                downloaded_image_count += 1
            except Exception as exc:  # noqa: BLE001
                download_status = f"error:{type(exc).__name__}"

            media_downloads.append(
                SnapshotMediaDownload(
                    source_observation_id=str(result["id"]),
                    source_media_id=str(photo["id"]),
                    image_path=image_path.as_posix(),
                    download_status=download_status,
                    source_url=photo_url,
                    mime_type=_guess_mime_type(photo_url),
                    sha256=sha256,
                )
            )

    manifest = InaturalistSnapshotManifest(
        snapshot_id=snapshot_id,
        created_at=datetime.now(timezone.utc),
        taxon_seeds=manifest_taxa,
        media_downloads=media_downloads,
        ai_outputs_path=None,
    )
    write_json(snapshot_dir / "manifest.json", manifest.model_dump(mode="json"))
    return HarvestResult(
        snapshot_id=snapshot_id,
        snapshot_dir=snapshot_dir,
        harvested_observation_count=harvested_observation_count,
        downloaded_image_count=downloaded_image_count,
    )


def _fetch_json(url: str, *, params: dict[str, str], timeout_seconds: int) -> dict[str, object]:
    request = Request(
        url=f"{url}?{urlencode(params)}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_bytes(url: str, *, timeout_seconds: int) -> bytes:
    request = Request(url=url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def _photo_source_url(photo: dict[str, object]) -> str:
    return str(
        photo.get("original_url")
        or photo.get("large_url")
        or photo.get("medium_url")
        or photo.get("url")
        or ""
    )


def _guess_extension(url: str) -> str | None:
    if "." not in url.rsplit("/", 1)[-1]:
        return None
    return url.rsplit(".", 1)[-1].split("?", 1)[0].lower()


def _guess_mime_type(url: str) -> str | None:
    extension = _guess_extension(url)
    if extension in {"jpg", "jpeg"}:
        return "image/jpeg"
    if extension == "png":
        return "image/png"
    if extension == "webp":
        return "image/webp"
    return None


def _slugify_filename(value: str) -> str:
    return value.replace(":", "_").replace("-", "_")
