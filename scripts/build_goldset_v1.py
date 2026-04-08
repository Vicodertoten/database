from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from PIL import Image, UnidentifiedImageError

INAT_OBSERVATIONS_API = "https://api.inaturalist.org/v1/observations"
USER_AGENT = "database-core/0.1"
SAFE_LICENSES = {"cc0", "cc-by", "cc-by-sa"}
RECOVERABLE_NETWORK_ERRORS = (HTTPError, URLError, TimeoutError, OSError, ValueError)
DEFAULT_OUTPUT_ROOT = Path("data/goldset/birds_v1")
DEFAULT_TARGET_IMAGES_PER_TAXON = 5
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_API_REQUEST_INTERVAL_SECONDS = 1.1


@dataclass(frozen=True)
class GoldsetTaxonTarget:
    scientific_name: str
    source_taxon_id: str


class APIRateLimiter:
    def __init__(self, *, interval_seconds: float) -> None:
        self.interval_seconds = max(0.0, interval_seconds)
        self._last_request_started_at: float | None = None

    def wait(self) -> None:
        if self.interval_seconds <= 0:
            self._last_request_started_at = time.monotonic()
            return
        now = time.monotonic()
        if self._last_request_started_at is None:
            self._last_request_started_at = now
            return
        elapsed = now - self._last_request_started_at
        remaining = self.interval_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_request_started_at = time.monotonic()


TARGET_TAXA: tuple[GoldsetTaxonTarget, ...] = (
    GoldsetTaxonTarget("Turdus merula", "12716"),
    GoldsetTaxonTarget("Erithacus rubecula", "13094"),
    GoldsetTaxonTarget("Passer domesticus", "13858"),
    GoldsetTaxonTarget("Cyanistes caeruleus", "144849"),
    GoldsetTaxonTarget("Parus major", "203153"),
    GoldsetTaxonTarget("Pica pica", "891696"),
    GoldsetTaxonTarget("Fringilla coelebs", "10070"),
    GoldsetTaxonTarget("Columba palumbus", "3048"),
    GoldsetTaxonTarget("Sturnus vulgaris", "14850"),
    GoldsetTaxonTarget("Turdus philomelos", "12748"),
    GoldsetTaxonTarget("Sylvia atricapilla", "15282"),
    GoldsetTaxonTarget("Motacilla alba", "13695"),
    GoldsetTaxonTarget("Garrulus glandarius", "8088"),
    GoldsetTaxonTarget("Corvus corone", "204496"),
    GoldsetTaxonTarget("Troglodytes troglodytes", "145363"),
    GoldsetTaxonTarget("Carduelis carduelis", "9398"),
    GoldsetTaxonTarget("Chloris chloris", "145360"),
    GoldsetTaxonTarget("Acrocephalus scirpaceus", "204455"),
    GoldsetTaxonTarget("Coccothraustes coccothraustes", "9801"),
    GoldsetTaxonTarget("Phoenicurus ochruros", "13000"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Gold set birds v1 (100 images / 20 taxa).")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--images-per-taxon", type=int, default=DEFAULT_TARGET_IMAGES_PER_TAXON)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument(
        "--api-request-interval-seconds",
        type=float,
        default=DEFAULT_API_REQUEST_INTERVAL_SECONDS,
    )
    args = parser.parse_args()

    if args.images_per_taxon <= 0:
        raise SystemExit("--images-per-taxon must be positive")

    output_root: Path = args.output_root
    images_root = output_root / "images"
    output_root.mkdir(parents=True, exist_ok=True)
    images_root.mkdir(parents=True, exist_ok=True)

    limiter = APIRateLimiter(interval_seconds=args.api_request_interval_seconds)
    selected_media_ids: set[str] = set()
    manifest_taxa: list[dict[str, object]] = []

    for target in TARGET_TAXA:
        taxon_payload = _collect_taxon_examples(
            target=target,
            images_per_taxon=args.images_per_taxon,
            timeout_seconds=args.timeout_seconds,
            images_root=images_root,
            globally_selected_media_ids=selected_media_ids,
            limiter=limiter,
        )
        manifest_taxa.append(taxon_payload)
        print(
            "goldset progress | "
            f"taxon={target.scientific_name} | selected={len(taxon_payload['images'])}"
        )

    total_images = sum(len(item["images"]) for item in manifest_taxa)
    manifest_payload = {
        "goldset_version": "goldset.birds.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "source_name": "inaturalist",
        "target_taxa_count": len(TARGET_TAXA),
        "target_images_per_taxon": args.images_per_taxon,
        "total_images": total_images,
        "safe_licenses": sorted(SAFE_LICENSES),
        "taxa": manifest_taxa,
    }

    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n")

    print(
        "goldset built | "
        f"taxa={len(TARGET_TAXA)} | images={total_images} | manifest={manifest_path}"
    )
    return 0


def _collect_taxon_examples(
    *,
    target: GoldsetTaxonTarget,
    images_per_taxon: int,
    timeout_seconds: int,
    images_root: Path,
    globally_selected_media_ids: set[str],
    limiter: APIRateLimiter,
) -> dict[str, object]:
    payload, requested_order_by, effective_order_by = _fetch_observations_with_fallback(
        source_taxon_id=target.source_taxon_id,
        timeout_seconds=timeout_seconds,
        limiter=limiter,
    )
    results = payload.get("results", [])
    if not isinstance(results, list):
        results = []

    selected_images: list[dict[str, object]] = []
    for observation in results:
        if len(selected_images) >= images_per_taxon:
            break
        if not isinstance(observation, dict):
            continue
        observation_license = str(observation.get("license_code") or "").lower()
        if observation_license not in SAFE_LICENSES:
            continue
        if observation.get("captive") is True:
            continue
        photos = observation.get("photos")
        if not isinstance(photos, list) or not photos:
            continue

        photo = photos[0]
        if not isinstance(photo, dict):
            continue
        source_media_id = str(photo.get("id") or "").strip()
        if not source_media_id or source_media_id in globally_selected_media_ids:
            continue
        photo_license = str(photo.get("license_code") or "").lower()
        if photo_license not in SAFE_LICENSES:
            continue

        candidate_urls = _candidate_photo_urls(photo)
        if not candidate_urls:
            continue

        downloaded = None
        for variant, source_url in candidate_urls:
            try:
                image_bytes = _fetch_bytes(source_url, timeout_seconds=timeout_seconds)
            except RECOVERABLE_NETWORK_ERRORS:
                continue
            image_bytes, extension = _normalize_downloaded_image(
                image_bytes=image_bytes,
                source_url=source_url,
            )
            observation_id = str(observation.get("id") or "").strip()
            image_path = (
                images_root
                / target.source_taxon_id
                / f"{observation_id}_{source_media_id}_{variant}.{extension}"
            )
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(image_bytes)
            downloaded = {
                "source_observation_id": observation_id,
                "source_media_id": source_media_id,
                "image_path": image_path.relative_to(images_root.parent).as_posix(),
                "source_url": source_url,
                "license_code": observation_license,
                "photo_license_code": photo_license,
                "downloaded_variant": variant,
                "downloaded_width": photo.get("width"),
                "downloaded_height": photo.get("height"),
                "observed_on": observation.get("observed_on"),
                "sha256": f"sha256:{hashlib.sha256(image_bytes).hexdigest()}",
            }
            break

        if downloaded is None:
            continue
        selected_images.append(downloaded)
        globally_selected_media_ids.add(source_media_id)

    if len(selected_images) < images_per_taxon:
        raise RuntimeError(
            "Gold set build failed: insufficient images for taxon "
            f"{target.scientific_name} ({target.source_taxon_id}). "
            f"expected={images_per_taxon}, got={len(selected_images)}"
        )

    return {
        "scientific_name": target.scientific_name,
        "source_taxon_id": target.source_taxon_id,
        "requested_order_by": requested_order_by,
        "effective_order_by": effective_order_by,
        "images": selected_images,
    }


def _fetch_observations_with_fallback(
    *,
    source_taxon_id: str,
    timeout_seconds: int,
    limiter: APIRateLimiter,
) -> tuple[dict[str, object], str, str]:
    base_params = {
        "taxon_id": source_taxon_id,
        "quality_grade": "research",
        "photos": "true",
        "license": ",".join(sorted(SAFE_LICENSES)),
        "photo_license": ",".join(sorted(SAFE_LICENSES)),
        "captive": "false",
        "per_page": "40",
        "order": "desc",
    }
    requested_order_by = "votes"
    first_params = {**base_params, "order_by": requested_order_by}
    try:
        return (
            _fetch_json(
                INAT_OBSERVATIONS_API,
                params=first_params,
                timeout_seconds=timeout_seconds,
                limiter=limiter,
            ),
            requested_order_by,
            requested_order_by,
        )
    except RECOVERABLE_NETWORK_ERRORS:
        fallback_order_by = "observed_on"
        fallback_params = {**base_params, "order_by": fallback_order_by}
        return (
            _fetch_json(
                INAT_OBSERVATIONS_API,
                params=fallback_params,
                timeout_seconds=timeout_seconds,
                limiter=limiter,
            ),
            requested_order_by,
            fallback_order_by,
        )


def _fetch_json(
    url: str,
    *,
    params: dict[str, str],
    timeout_seconds: int,
    limiter: APIRateLimiter,
) -> dict[str, object]:
    limiter.wait()
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


def _candidate_photo_urls(photo: dict[str, object]) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    seen: set[str] = set()

    for variant in ("medium", "large", "original"):
        value = str(photo.get(f"{variant}_url") or "").strip()
        if value and value not in seen:
            candidates.append((variant, value))
            seen.add(value)

    square_url = str(photo.get("url") or "").strip()
    if square_url:
        for variant in ("medium", "large", "original"):
            if "/square." not in square_url:
                continue
            value = square_url.replace("/square.", f"/{variant}.", 1)
            if value not in seen:
                candidates.append((variant, value))
                seen.add(value)
    return candidates


def _guess_extension(url: str) -> str | None:
    path = urlparse(url).path
    if "." not in path:
        return None
    return path.rsplit(".", 1)[-1].lower()


def _normalize_downloaded_image(*, image_bytes: bytes, source_url: str) -> tuple[bytes, str]:
    extension = (_guess_extension(source_url) or "jpg").lower()
    if extension != "gif":
        return image_bytes, extension
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            first_frame = image.convert("RGB")
            buffer = io.BytesIO()
            first_frame.save(buffer, format="JPEG", quality=82, optimize=True, progressive=True)
            return buffer.getvalue(), "jpg"
    except (OSError, UnidentifiedImageError):
        return image_bytes, extension


if __name__ == "__main__":
    raise SystemExit(main())
