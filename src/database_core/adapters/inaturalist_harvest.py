from __future__ import annotations

import hashlib
import io
import json
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from PIL import Image, ImageFilter, ImageStat, UnidentifiedImageError

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
INAT_OBSERVATION_TAXA_API = "https://api.inaturalist.org/v1/observations/taxa"
INAT_TAXA_API = "https://api.inaturalist.org/v1/taxa"
USER_AGENT = "database-core/0.1"
INAT_SAFE_LICENSE_FILTER = "cc0,cc-by,cc-by-sa"
INAT_PRIMARY_LOCALE = "fr"
INAT_LOCALIZED_NAME_LANGUAGES = ("fr", "en", "nl")
RECOVERABLE_HARVEST_ERRORS = (
    HTTPError,
    URLError,
    TimeoutError,
    OSError,
    ValueError,
    json.JSONDecodeError,
)
BLUR_SCORE_DOWNSAMPLED_SIZE = (256, 256)
COUNTRY_CODE_TO_INAT_PLACE_ID = {
    "BE": "7008",
    "FR": "6753",
}


def _bbox_to_inat_params(bbox: str) -> dict[str, str]:
    parts = [part.strip() for part in bbox.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must have four comma-separated values")
    min_lon, min_lat, max_lon, max_lat = parts
    return {
        "swlng": min_lon,
        "swlat": min_lat,
        "nelng": max_lon,
        "nelat": max_lat,
    }


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
    bbox: str | None = None,
    place_id: str | None = None,
    country_code: str | None = None,
    observed_from: str | None = None,
    observed_to: str | None = None,
    order_by: str | None = None,
    order: str | None = None,
    exclude_observation_ids: set[str] | None = None,
    exclude_media_ids: set[str] | None = None,
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
    normalized_country_code, resolved_place_id = _resolve_geo_country_filters(
        country_code=country_code,
        place_id=place_id,
    )

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
            bbox=bbox,
            place_id=resolved_place_id,
            observed_from=observed_from,
            observed_to=observed_to,
            order_by=order_by,
            order=order,
        )
        if normalized_country_code is not None:
            effective_params = {
                **effective_params,
                "country_code": normalized_country_code,
            }
        candidate_results: list[dict[str, object]] = []
        known_observation_ids = exclude_observation_ids or set()
        known_media_ids = exclude_media_ids or set()
        for item in response_payload.get("results", []):
            if not is_supported_observation_result(item, seed.source_taxon_id):
                continue
            observation_id = str(item.get("id", "")).strip()
            photos = item.get("photos") or []
            primary_photo = photos[0] if photos else None
            media_id = str((primary_photo or {}).get("id", "")).strip()
            if observation_id and observation_id in known_observation_ids:
                continue
            if media_id and media_id in known_media_ids:
                continue
            candidate_results.append(item)
            if len(candidate_results) >= max_observations_per_taxon:
                break
        response_payload["results"] = candidate_results
        taxon_payload_path = _write_taxon_payload(
            snapshot_dir=snapshot_dir,
            source_taxon_id=seed.source_taxon_id,
            canonical_taxon_id=seed.canonical_taxon_id,
            timeout_seconds=timeout_seconds,
            preferred_place_id=resolved_place_id,
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
            blur_score = None

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
                blur_score = _compute_blur_score(downloaded.image_bytes)
                downloaded_image_count += 1
            except RECOVERABLE_HARVEST_ERRORS as exc:
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
                    blur_score=blur_score,
                    pre_ai_rejection_reason=None,
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
    preferred_place_id: str | None = None,
) -> Path | None:
    detail_params = {
        "locale": INAT_PRIMARY_LOCALE,
        "all_names": "true",
    }
    if preferred_place_id:
        detail_params["preferred_place_id"] = preferred_place_id
    try:
        payload = _fetch_json(
            f"{INAT_TAXA_API}/{source_taxon_id}",
            params=detail_params,
            timeout_seconds=timeout_seconds,
        )
    except RECOVERABLE_HARVEST_ERRORS:
        return None

    localized_payloads: dict[str, object] = {}
    for locale in INAT_LOCALIZED_NAME_LANGUAGES:
        try:
            localized_payloads[locale] = _fetch_json(
                INAT_TAXA_API,
                params=_taxon_lookup_params(
                    source_taxon_id=source_taxon_id,
                    locale=locale,
                    preferred_place_id=preferred_place_id,
                ),
                timeout_seconds=timeout_seconds,
            )
        except RECOVERABLE_HARVEST_ERRORS as exc:
            localized_payloads[locale] = {
                "error": f"{type(exc).__name__}: {exc}",
                "locale": locale,
            }
    payload["localized_taxa"] = localized_payloads

    payload_path = Path("taxa") / f"{_slugify_filename(canonical_taxon_id)}.json"
    write_json(snapshot_dir / payload_path, payload)
    return payload_path


def _taxon_lookup_params(
    *,
    source_taxon_id: str,
    locale: str,
    preferred_place_id: str | None,
) -> dict[str, str]:
    params = {
        "taxon_id": source_taxon_id,
        "per_page": "1",
        "locale": locale,
        "all_names": "true",
    }
    if preferred_place_id:
        params["preferred_place_id"] = preferred_place_id
    return params


def _fetch_json(url: str, *, params: dict[str, str], timeout_seconds: int) -> dict[str, object]:
    request = Request(
        url=f"{url}?{urlencode(params)}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with _urlopen_with_ssl_fallback(request, timeout_seconds=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi  # type: ignore[import-not-found]

        return ssl.create_default_context(cafile=certifi.where())
    except (ImportError, OSError):
        return ssl.create_default_context()


def _urlopen_with_ssl_fallback(request: Request, *, timeout_seconds: int):
    try:
        return urlopen(request, timeout=timeout_seconds, context=_ssl_context())
    except URLError as exc:
        if not _is_ssl_certificate_error(exc):
            raise
        return urlopen(
            request,
            timeout=timeout_seconds,
            context=ssl._create_unverified_context(),
        )


def _is_ssl_certificate_error(exc: URLError) -> bool:
    reason = getattr(exc, "reason", None)
    if isinstance(reason, ssl.SSLCertVerificationError):
        return True
    return "CERTIFICATE_VERIFY_FAILED" in str(exc)


def _fetch_seed_payload(
    *,
    source_taxon_id: str,
    max_observations_per_taxon: int,
    timeout_seconds: int,
    bbox: str | None = None,
    place_id: str | None = None,
    observed_from: str | None = None,
    observed_to: str | None = None,
    order_by: str | None = None,
    order: str | None = None,
) -> tuple[dict[str, object], str, str, bool, dict[str, str]]:
    base_params = {
        "taxon_id": source_taxon_id,
        "quality_grade": "research",
        "photos": "true",
        "license": INAT_SAFE_LICENSE_FILTER,
        "photo_license": INAT_SAFE_LICENSE_FILTER,
        "captive": "false",
        "per_page": str(max_observations_per_taxon),
        "order": (order or "desc"),
        "locale": INAT_PRIMARY_LOCALE,
    }
    if bbox:
        base_params.update(_bbox_to_inat_params(bbox))
    if place_id:
        base_params["place_id"] = place_id
        base_params["preferred_place_id"] = place_id
    if observed_from:
        base_params["d1"] = observed_from
    if observed_to:
        base_params["d2"] = observed_to
    requested_order_by = order_by or "votes"
    first_params = {**base_params, "order_by": requested_order_by}
    try:
        payload = _fetch_json(
            INAT_OBSERVATIONS_API, params=first_params, timeout_seconds=timeout_seconds
        )
        return payload, requested_order_by, requested_order_by, False, first_params
    except RECOVERABLE_HARVEST_ERRORS:
        fallback_order_by = "observed_on"
        fallback_params = {**base_params, "order_by": fallback_order_by}
        payload = _fetch_json(
            INAT_OBSERVATIONS_API, params=fallback_params, timeout_seconds=timeout_seconds
        )
        return payload, requested_order_by, fallback_order_by, True, fallback_params


def _fetch_bytes(url: str, *, timeout_seconds: int) -> bytes:
    request = Request(url=url, headers={"User-Agent": USER_AGENT})
    with _urlopen_with_ssl_fallback(request, timeout_seconds=timeout_seconds) as response:
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
        except RECOVERABLE_HARVEST_ERRORS as exc:
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


def _compute_blur_score(image_bytes: bytes) -> float | None:
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            grayscale = image.convert("L").resize(BLUR_SCORE_DOWNSAMPLED_SIZE)
            # Lightweight edge-energy proxy using Laplacian kernel variance.
            laplacian = grayscale.filter(
                ImageFilter.Kernel(
                    (3, 3),
                    [-1, -1, -1, -1, 8, -1, -1, -1, -1],
                    scale=1,
                )
            )
            stats = ImageStat.Stat(laplacian)
            return round(float(stats.var[0]), 6)
    except (OSError, UnidentifiedImageError, ValueError):
        return None


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


def _resolve_geo_country_filters(
    *,
    country_code: str | None,
    place_id: str | None,
) -> tuple[str | None, str | None]:
    normalized_country_code = _normalize_country_code(country_code)
    normalized_place_id = str(place_id).strip() if place_id else None

    if normalized_country_code is None:
        return None, normalized_place_id

    mapped_place_id = COUNTRY_CODE_TO_INAT_PLACE_ID.get(normalized_country_code)
    if mapped_place_id is None:
        supported = ", ".join(sorted(COUNTRY_CODE_TO_INAT_PLACE_ID))
        raise ValueError(
            "Unsupported country_code filter "
            f"{normalized_country_code!r}. Supported values: {supported}"
        )

    if normalized_place_id and normalized_place_id != mapped_place_id:
        raise ValueError(
            "Conflicting geo filters: place_id and country_code target different places. "
            f"Expected place_id={mapped_place_id!r} for country_code={normalized_country_code!r}."
        )

    return normalized_country_code, mapped_place_id


def _normalize_country_code(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if len(normalized) != 2:
        raise ValueError("country_code must be an ISO alpha-2 code")
    return normalized


def _slugify_filename(value: str) -> str:
    return value.replace(":", "_").replace("-", "_")
