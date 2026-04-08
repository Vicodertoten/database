from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from PIL import Image, UnidentifiedImageError

from database_core.adapters.inaturalist_snapshot import (
    DEFAULT_INAT_SNAPSHOT_ROOT,
    DEFAULT_PILOT_TAXA_PATH,
    InaturalistSnapshotManifest,
    SnapshotMediaDownload,
    SnapshotTaxonSeed,
    is_supported_observation_result,
    load_pilot_taxa,
    resolve_snapshot_dir,
    write_snapshot_manifest,
)
from database_core.export.json_exporter import write_json

INAT_OBSERVATIONS_API = "https://api.inaturalist.org/v1/observations"
INAT_TAXA_API = "https://api.inaturalist.org/v1/taxa"
USER_AGENT = "database-core/0.1"
INAT_SAFE_LICENSE_FILTER = "cc0,cc-by,cc-by-sa"


@dataclass(frozen=True)
class HarvestResult:
    snapshot_id: str
    snapshot_dir: Path
    harvested_observation_count: int
    downloaded_image_count: int


@dataclass(frozen=True)
class DownloadedPhoto:
    source_url: str
    variant: str
    image_bytes: bytes
    mime_type: str | None
    width: int | None
    height: int | None


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
    taxa_dir = snapshot_dir / "taxa"
    responses_dir.mkdir(parents=True, exist_ok=True)
    images_dir.mkdir(parents=True, exist_ok=True)
    taxa_dir.mkdir(parents=True, exist_ok=True)

    manifest_taxa: list[SnapshotTaxonSeed] = []
    media_downloads: list[SnapshotMediaDownload] = []
    harvested_observation_count = 0
    downloaded_image_count = 0

    for seed in load_pilot_taxa(pilot_taxa_path):
        (
            response_payload,
            requested_order_by,
            effective_order_by,
            fallback_applied,
            effective_params,
        ) = _fetch_seed_payload(
            source_taxon_id=seed.source_taxon_id,
            max_observations_per_taxon=max_observations_per_taxon,
            timeout_seconds=timeout_seconds,
        )
        candidate_results = [
            item
            for item in response_payload.get("results", [])
            if is_supported_observation_result(item, seed.source_taxon_id)
        ][:max_observations_per_taxon]
        response_payload["results"] = candidate_results
        taxon_payload_path = _write_taxon_payload(
            snapshot_dir=snapshot_dir,
            source_taxon_id=seed.source_taxon_id,
            canonical_taxon_id=seed.canonical_taxon_id,
            timeout_seconds=timeout_seconds,
        )

        response_path = Path("responses") / f"{_slugify_filename(seed.canonical_taxon_id)}.json"
        write_json(snapshot_dir / response_path, response_payload)
        manifest_taxa.append(
            SnapshotTaxonSeed(
                canonical_taxon_id=seed.canonical_taxon_id,
                accepted_scientific_name=seed.accepted_scientific_name,
                canonical_rank=seed.canonical_rank,
                taxon_status=seed.taxon_status,
                authority_source=seed.authority_source,
                display_slug=seed.display_slug,
                synonyms=seed.synonyms,
                common_names=seed.common_names,
                source_taxon_id=seed.source_taxon_id,
                query_params=effective_params,
                response_path=response_path.as_posix(),
                taxon_payload_path=taxon_payload_path.as_posix() if taxon_payload_path else None,
                requested_order_by=requested_order_by,
                effective_order_by=effective_order_by,
                fallback_applied=fallback_applied,
            )
        )

        for result in candidate_results:
            harvested_observation_count += 1
            photo = result["photos"][0]
            candidate_urls = list(_candidate_photo_sources(photo))
            image_url = candidate_urls[0][1] if candidate_urls else ""
            extension = _guess_extension(image_url) or "jpg"
            image_path = Path("images") / f"{photo['id']}.{extension}"
            download_status = "downloaded"
            sha256 = None
            downloaded_width = None
            downloaded_height = None
            downloaded_variant = None
            file_size_bytes = None

            try:
                downloaded = _download_best_candidate(
                    candidate_urls, timeout_seconds=timeout_seconds
                )
                image_path = Path("images") / (
                    f"{photo['id']}.{_guess_extension(downloaded.source_url) or extension}"
                )
                (snapshot_dir / image_path).write_bytes(downloaded.image_bytes)
                sha256 = f"sha256:{hashlib.sha256(downloaded.image_bytes).hexdigest()}"
                downloaded_width = downloaded.width
                downloaded_height = downloaded.height
                downloaded_variant = downloaded.variant
                file_size_bytes = len(downloaded.image_bytes)
                image_url = downloaded.source_url
                downloaded_image_count += 1
            except Exception as exc:  # noqa: BLE001
                download_status = f"error:{type(exc).__name__}"

            media_downloads.append(
                SnapshotMediaDownload(
                    source_observation_id=str(result["id"]),
                    source_media_id=str(photo["id"]),
                    image_path=image_path.as_posix(),
                    download_status=download_status,
                    source_url=image_url,
                    mime_type=_guess_mime_type(image_url),
                    sha256=sha256,
                    downloaded_width=downloaded_width,
                    downloaded_height=downloaded_height,
                    downloaded_variant=downloaded_variant,
                    file_size_bytes=file_size_bytes,
                )
            )

    manifest = InaturalistSnapshotManifest(
        snapshot_id=snapshot_id,
        created_at=datetime.now(UTC),
        taxon_seeds=manifest_taxa,
        media_downloads=media_downloads,
        ai_outputs_path=None,
    )
    write_snapshot_manifest(snapshot_dir, manifest)
    return HarvestResult(
        snapshot_id=snapshot_id,
        snapshot_dir=snapshot_dir,
        harvested_observation_count=harvested_observation_count,
        downloaded_image_count=downloaded_image_count,
    )


def _write_taxon_payload(
    *,
    snapshot_dir: Path,
    source_taxon_id: str,
    canonical_taxon_id: str,
    timeout_seconds: int,
) -> Path | None:
    try:
        payload = _fetch_json(
            f"{INAT_TAXA_API}/{source_taxon_id}",
            params={},
            timeout_seconds=timeout_seconds,
        )
    except Exception:  # noqa: BLE001
        return None

    payload_path = Path("taxa") / f"{_slugify_filename(canonical_taxon_id)}.json"
    write_json(snapshot_dir / payload_path, payload)
    return payload_path


def _fetch_json(url: str, *, params: dict[str, str], timeout_seconds: int) -> dict[str, object]:
    request = Request(
        url=f"{url}?{urlencode(params)}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _fetch_seed_payload(
    *,
    source_taxon_id: str,
    max_observations_per_taxon: int,
    timeout_seconds: int,
) -> tuple[dict[str, object], str, str, bool, dict[str, str]]:
    base_params = {
        "taxon_id": source_taxon_id,
        "quality_grade": "research",
        "photos": "true",
        "license": INAT_SAFE_LICENSE_FILTER,
        "photo_license": INAT_SAFE_LICENSE_FILTER,
        "captive": "false",
        "per_page": str(max_observations_per_taxon),
        "order": "desc",
    }
    requested_order_by = "votes"
    first_params = {**base_params, "order_by": requested_order_by}
    try:
        payload = _fetch_json(
            INAT_OBSERVATIONS_API, params=first_params, timeout_seconds=timeout_seconds
        )
        return payload, requested_order_by, requested_order_by, False, first_params
    except Exception:  # noqa: BLE001
        fallback_order_by = "observed_on"
        fallback_params = {**base_params, "order_by": fallback_order_by}
        payload = _fetch_json(
            INAT_OBSERVATIONS_API, params=fallback_params, timeout_seconds=timeout_seconds
        )
        return payload, requested_order_by, fallback_order_by, True, fallback_params


def _fetch_bytes(url: str, *, timeout_seconds: int) -> bytes:
    request = Request(url=url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def _candidate_photo_sources(photo: dict[str, object]) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()

    for variant in ("original", "large", "medium"):
        key = f"{variant}_url"
        value = str(photo.get(key) or "")
        if value and value not in seen:
            candidates.append((variant, value))
            seen.add(value)

    photo_url = str(photo.get("url") or "")
    if not photo_url:
        return candidates

    derived_urls = _derive_variant_urls(photo_url)
    for variant, value in derived_urls:
        if value not in seen:
            candidates.append((variant, value))
            seen.add(value)

    if "/square." not in photo_url and photo_url not in seen:
        candidates.append(("source", photo_url))
    return candidates


def _derive_variant_urls(photo_url: str) -> list[tuple[str, str]]:
    if "/square." not in photo_url:
        return []
    derived: list[tuple[str, str]] = []
    for variant in ("original", "large", "medium"):
        derived.append((variant, photo_url.replace("/square.", f"/{variant}.", 1)))
    return derived


def _download_best_candidate(
    candidate_urls: list[tuple[str, str]],
    *,
    timeout_seconds: int,
) -> DownloadedPhoto:
    last_error: Exception | None = None
    for variant, url in candidate_urls:
        try:
            image_bytes = _fetch_bytes(url, timeout_seconds=timeout_seconds)
            width, height = _inspect_image_dimensions(image_bytes)
            return DownloadedPhoto(
                source_url=url,
                variant=variant,
                image_bytes=image_bytes,
                mime_type=_guess_mime_type(url),
                width=width,
                height=height,
            )
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    if last_error is not None:
        raise last_error
    raise RuntimeError("no candidate image url available")


def _inspect_image_dimensions(image_bytes: bytes) -> tuple[int | None, int | None]:
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            return image.width, image.height
    except (OSError, UnidentifiedImageError):
        return None, None


def _guess_extension(url: str) -> str | None:
    path = urlparse(url).path
    if "." not in path:
        return None
    return path.rsplit(".", 1)[-1].lower()


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
