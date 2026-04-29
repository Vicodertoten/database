from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from database_core.adapters.common import SourceDataset, source_external_key
from database_core.domain.canonical_ids import next_canonical_taxon_id
from database_core.domain.enums import CanonicalRank, SourceName, TaxonGroup, TaxonStatus
from database_core.domain.models import (
    CanonicalTaxon,
    ExternalMapping,
    LocationMetadata,
    MediaAsset,
    SourceObservation,
    SourceQualityMetadata,
)
from database_core.qualification.ai import (
    AIQualificationOutcome,
    inspect_image_dimensions,
    parse_source_external_key,
)
from database_core.qualification.rules import is_safe_license
from database_core.versioning import SNAPSHOT_MANIFEST_VERSION

DEFAULT_INAT_SNAPSHOT_ROOT = Path("data/raw/inaturalist")
DEFAULT_PILOT_TAXA_PATH = Path("data/fixtures/inaturalist_pilot_taxa.json")
MIN_ACCEPTED_WIDTH = 1000
MIN_ACCEPTED_HEIGHT = 750
INAT_PLACE_ID_TO_COUNTRY_CODE = {
    "7083": "BE",
}


class SnapshotModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())


class PilotTaxonSeed(SnapshotModel):
    canonical_taxon_id: str | None = None
    accepted_scientific_name: str
    canonical_rank: CanonicalRank = CanonicalRank.SPECIES
    taxon_status: TaxonStatus = TaxonStatus.ACTIVE
    authority_source: SourceName = SourceName.INATURALIST
    display_slug: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    common_names: list[str] = Field(default_factory=list)
    source_taxon_id: str

    @field_validator("source_taxon_id")
    @classmethod
    def validate_source_taxon_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_taxon_id must not be blank")
        return value


class SnapshotTaxonSeed(SnapshotModel):
    canonical_taxon_id: str
    accepted_scientific_name: str
    canonical_rank: CanonicalRank = CanonicalRank.SPECIES
    taxon_status: TaxonStatus = TaxonStatus.ACTIVE
    authority_source: SourceName = SourceName.INATURALIST
    display_slug: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    common_names: list[str] = Field(default_factory=list)
    source_taxon_id: str
    query_params: dict[str, str]
    response_path: str
    taxon_payload_path: str | None = None
    requested_order_by: str | None = None
    effective_order_by: str | None = None
    fallback_applied: bool = False


class SnapshotMediaDownload(SnapshotModel):
    source_observation_id: str
    source_media_id: str
    image_path: str
    download_status: str
    source_url: str
    mime_type: str | None = None
    sha256: str | None = None
    downloaded_width: int | None = None
    downloaded_height: int | None = None
    downloaded_variant: str | None = None
    file_size_bytes: int | None = None
    blur_score: float | None = None
    pre_ai_rejection_reason: str | None = None


class InaturalistSnapshotManifest(SnapshotModel):
    manifest_version: str = SNAPSHOT_MANIFEST_VERSION
    snapshot_id: str
    source_name: SourceName = SourceName.INATURALIST
    created_at: datetime
    taxon_seeds: list[SnapshotTaxonSeed]
    media_downloads: list[SnapshotMediaDownload]
    ai_outputs_path: str | None = None


def load_pilot_taxa(path: Path = DEFAULT_PILOT_TAXA_PATH) -> list[PilotTaxonSeed]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    seeds = [
        PilotTaxonSeed(**item)
        for item in payload
    ]
    validated = _assign_missing_canonical_taxon_ids(seeds)
    for seed in validated:
        if seed.authority_source != SourceName.INATURALIST:
            raise ValueError(
                "Pilot taxon seed has unsupported authority_source for phase1 birds."
            )
    return validated


def resolve_snapshot_dir(
    snapshot_id: str,
    snapshot_root: Path = DEFAULT_INAT_SNAPSHOT_ROOT,
) -> Path:
    return snapshot_root / snapshot_id


def load_snapshot_manifest(
    *,
    snapshot_id: str | None = None,
    snapshot_root: Path = DEFAULT_INAT_SNAPSHOT_ROOT,
    manifest_path: Path | None = None,
) -> tuple[InaturalistSnapshotManifest, Path]:
    if manifest_path is None:
        if snapshot_id is None:
            raise ValueError("snapshot_id or manifest_path is required for inat_snapshot mode")
        manifest_path = resolve_snapshot_dir(snapshot_id, snapshot_root) / "manifest.json"

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_version = payload.get("manifest_version")
    if manifest_version != SNAPSHOT_MANIFEST_VERSION:
        raise ValueError(
            "Unsupported snapshot manifest_version "
            f"{manifest_version!r} in {manifest_path}. Expected {SNAPSHOT_MANIFEST_VERSION!r} "
            "for canonical v1 hard-cutover."
        )
    manifest = InaturalistSnapshotManifest.model_validate(payload)
    return manifest, manifest_path.parent


def write_snapshot_manifest(snapshot_dir: Path, manifest: InaturalistSnapshotManifest) -> None:
    path = snapshot_dir / "manifest.json"
    path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_snapshot_dataset(
    *,
    snapshot_id: str | None = None,
    snapshot_root: Path = DEFAULT_INAT_SNAPSHOT_ROOT,
    manifest_path: Path | None = None,
) -> SourceDataset:
    manifest, snapshot_dir = load_snapshot_manifest(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        manifest_path=manifest_path,
    )
    if manifest.source_name != SourceName.INATURALIST:
        raise ValueError(
            "Canonical auto-creation authority for phase1 birds is inaturalist only."
        )
    for seed in manifest.taxon_seeds:
        if seed.authority_source != SourceName.INATURALIST:
            raise ValueError(
                "Snapshot taxon seed has unsupported authority_source for phase1 birds."
            )
    canonical_taxa = sorted(
        [_build_canonical_taxon(seed) for seed in manifest.taxon_seeds],
        key=lambda item: item.canonical_taxon_id,
    )
    observations: list[SourceObservation] = []
    media_assets: list[MediaAsset] = []
    download_by_media_id = {
        source_external_key(
            source_name=manifest.source_name,
            external_id=item.source_media_id,
        ): item
        for item in manifest.media_downloads
    }
    taxon_payloads_by_canonical_taxon_id: dict[str, dict[str, object]] = {}

    for seed in manifest.taxon_seeds:
        if not seed.taxon_payload_path:
            continue
        payload_path = snapshot_dir / seed.taxon_payload_path
        if not payload_path.exists():
            continue
        taxon_payloads_by_canonical_taxon_id[seed.canonical_taxon_id] = json.loads(
            payload_path.read_text(encoding="utf-8")
        )

    for seed in sorted(manifest.taxon_seeds, key=lambda item: item.canonical_taxon_id):
        payload = json.loads((snapshot_dir / seed.response_path).read_text(encoding="utf-8"))
        for raw_index, result in enumerate(payload.get("results", [])):
            if not is_supported_observation_result(result, seed.source_taxon_id):
                continue
            observation = _build_snapshot_observation(
                result=result,
                seed=seed,
                response_path=seed.response_path,
                raw_index=raw_index,
            )
            observations.append(observation)

            primary_photo = (result.get("photos") or [None])[0]
            if primary_photo is None:
                continue

            media_assets.append(
                _build_snapshot_media_asset(
                    observation=observation,
                    photo=primary_photo,
                    download=download_by_media_id.get(
                        source_external_key(
                            source_name=manifest.source_name,
                            external_id=str(primary_photo["id"]),
                        )
                    ),
                    response_path=seed.response_path,
                    raw_index=raw_index,
                    snapshot_dir=snapshot_dir,
                )
            )

    return SourceDataset(
        dataset_id=f"{manifest.source_name}:{manifest.snapshot_id}",
        captured_at=manifest.created_at,
        canonical_taxa=canonical_taxa,
        observations=sorted(observations, key=lambda item: item.observation_uid),
        media_assets=sorted(media_assets, key=lambda item: item.media_id),
        ai_qualifications={},
        cached_image_paths_by_source_media_key={
            source_external_key(
                source_name=manifest.source_name,
                external_id=item.source_media_id,
            ): snapshot_dir
            / item.image_path
            for item in manifest.media_downloads
        },
        ai_qualification_outcomes=_load_ai_outputs(
            snapshot_dir,
            manifest.ai_outputs_path,
            source_name=manifest.source_name,
        ),
        taxon_payloads_by_canonical_taxon_id=taxon_payloads_by_canonical_taxon_id,
    )


def summarize_snapshot_manifest(
    *,
    snapshot_id: str | None = None,
    snapshot_root: Path = DEFAULT_INAT_SNAPSHOT_ROOT,
    manifest_path: Path | None = None,
) -> dict[str, object]:
    manifest, snapshot_dir = load_snapshot_manifest(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        manifest_path=manifest_path,
    )
    harvested_observations = 0
    harvested_per_taxon: dict[str, int] = {}
    for seed in manifest.taxon_seeds:
        payload = json.loads((snapshot_dir / seed.response_path).read_text(encoding="utf-8"))
        supported_observations = [
            item
            for item in payload.get("results", [])
            if is_supported_observation_result(item, seed.source_taxon_id)
        ]
        harvested_per_taxon[seed.canonical_taxon_id] = len(supported_observations)
        harvested_observations += len(supported_observations)

    downloaded_images = 0
    insufficient_resolution_images = 0
    for item in manifest.media_downloads:
        image_path = snapshot_dir / item.image_path
        if item.download_status == "downloaded" and image_path.exists():
            downloaded_images += 1
        width, height = _resolve_download_dimensions(snapshot_dir, item)
        if width is not None and height is not None:
            if width < MIN_ACCEPTED_WIDTH or height < MIN_ACCEPTED_HEIGHT:
                insufficient_resolution_images += 1

    pre_ai_rejection_reason_counts: dict[str, int] = {}
    for item in manifest.media_downloads:
        reason = str(item.pre_ai_rejection_reason or "").strip()
        if not reason:
            continue
        pre_ai_rejection_reason_counts[reason] = pre_ai_rejection_reason_counts.get(reason, 0) + 1

    ai_outputs = _load_ai_outputs(
        snapshot_dir,
        manifest.ai_outputs_path,
        source_name=manifest.source_name,
    )
    pre_ai_statuses = {
        "insufficient_resolution_pre_ai",
        "decode_error_pre_ai",
        "blur_pre_ai",
        "duplicate_pre_ai",
    }
    images_sent_to_gemini = len(
        [
            item
            for item in ai_outputs.values()
            if item.status
            not in {
                "missing_cached_image",
                "insufficient_resolution",
                "missing_cached_ai_output",
                *pre_ai_statuses,
            }
        ]
    )
    ai_valid_outputs = len([item for item in ai_outputs.values() if item.status == "ok"])

    return {
        "harvested_observations": harvested_observations,
        "taxa_with_results": len([count for count in harvested_per_taxon.values() if count > 0]),
        "harvested_per_taxon": harvested_per_taxon,
        "downloaded_images": downloaded_images,
        "images_sent_to_gemini": images_sent_to_gemini,
        "insufficient_resolution_images": insufficient_resolution_images,
        "ai_valid_outputs": ai_valid_outputs,
        "pre_ai_rejection_reason_counts": dict(sorted(pre_ai_rejection_reason_counts.items())),
    }


def _build_canonical_taxon(seed: SnapshotTaxonSeed) -> CanonicalTaxon:
    return CanonicalTaxon(
        canonical_taxon_id=seed.canonical_taxon_id,
        accepted_scientific_name=seed.accepted_scientific_name,
        canonical_rank=seed.canonical_rank,
        taxon_status=seed.taxon_status,
        authority_source=seed.authority_source,
        display_slug=seed.display_slug,
        synonyms=seed.synonyms,
        common_names=seed.common_names,
        bird_scope_compatible=True,
        external_source_mappings=[
            ExternalMapping(source_name=SourceName.INATURALIST, external_id=seed.source_taxon_id)
        ],
        similar_taxon_ids=[],
    )


def is_supported_observation_result(result: dict[str, object], seed_source_taxon_id: str) -> bool:
    photos = result.get("photos") or []
    if result.get("quality_grade") != "research" or not photos:
        return False
    if not is_safe_license(_normalize_license(result.get("license_code"))):
        return False
    if result.get("captive") is True:
        return False
    taxon = result.get("taxon") or {}
    taxon_id = str(taxon.get("id", ""))
    ancestor_ids = {str(item) for item in taxon.get("ancestor_ids", [])}
    if taxon_id != seed_source_taxon_id and seed_source_taxon_id not in ancestor_ids:
        return False
    primary_photo = photos[0]
    return is_safe_license(_normalize_license((primary_photo or {}).get("license_code")))


def _normalize_license(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_snapshot_observation(
    *,
    result: dict[str, object],
    seed: SnapshotTaxonSeed,
    response_path: str,
    raw_index: int,
) -> SourceObservation:
    geojson = result.get("geojson") or {}
    coordinates = geojson.get("coordinates") or [None, None]
    country_code = _infer_country_code(result=result, seed=seed)
    return SourceObservation(
        observation_uid=f"obs:inaturalist:{result['id']}",
        source_name=SourceName.INATURALIST,
        source_observation_id=str(result["id"]),
        source_taxon_id=str((result.get("taxon") or {}).get("id") or seed.source_taxon_id),
        observed_at=_parse_datetime(
            result.get("time_observed_at")
            or result.get("observed_on_string")
            or result.get("observed_on")
        ),
        location=LocationMetadata(
            place_name=result.get("place_guess"),
            latitude=coordinates[1] if len(coordinates) > 1 else None,
            longitude=coordinates[0] if coordinates else None,
            country_code=country_code,
        ),
        source_quality=SourceQualityMetadata(
            quality_grade=str(result.get("quality_grade", "unknown")),
            research_grade=result.get("quality_grade") == "research",
            observation_license=result.get("license_code"),
            captive=result.get("captive"),
        ),
        raw_payload_ref=f"{response_path}#/results/{raw_index}",
        canonical_taxon_id=seed.canonical_taxon_id,
    )


def _build_snapshot_media_asset(
    *,
    observation: SourceObservation,
    photo: dict[str, object],
    download: SnapshotMediaDownload | None,
    response_path: str,
    raw_index: int,
    snapshot_dir: Path,
) -> MediaAsset:
    source_url = (
        download.source_url
        if download and download.source_url
        else photo.get("original_url")
        or photo.get("large_url")
        or photo.get("medium_url")
        or photo.get("url")
        or observation.raw_payload_ref
    )
    width, height = _resolve_download_dimensions(snapshot_dir, download)
    return MediaAsset(
        media_id=f"media:inaturalist:{photo['id']}",
        source_name=SourceName.INATURALIST,
        source_media_id=str(photo["id"]),
        media_type="image",
        source_url=str(source_url),
        attribution=str(photo.get("attribution") or "unknown attribution"),
        author=str(photo.get("attribution_name")) if photo.get("attribution_name") else None,
        license=str(photo.get("license_code")) if photo.get("license_code") else None,
        mime_type=download.mime_type
        if download and download.mime_type
        else _guess_mime_type(str(source_url)),
        file_extension=_guess_extension(str(source_url)),
        width=width,
        height=height,
        checksum=download.sha256 if download else None,
        source_observation_uid=observation.observation_uid,
        canonical_taxon_id=observation.canonical_taxon_id,
        raw_payload_ref=f"{response_path}#/results/{raw_index}",
    )


def _load_ai_outputs(
    snapshot_dir: Path,
    ai_outputs_path: str | None,
    *,
    source_name: SourceName,
) -> dict[tuple[SourceName, str], AIQualificationOutcome]:
    if ai_outputs_path is None:
        return {}
    payload = json.loads((snapshot_dir / ai_outputs_path).read_text(encoding="utf-8"))
    return {
        parse_source_external_key(
            media_id,
            default_source_name=source_name,
        ): AIQualificationOutcome.from_snapshot_payload(item)
        for media_id, item in payload.items()
    }


def _resolve_download_dimensions(
    snapshot_dir: Path,
    download: SnapshotMediaDownload | None,
) -> tuple[int | None, int | None]:
    if download is None:
        return None, None
    if download.downloaded_width is not None and download.downloaded_height is not None:
        return download.downloaded_width, download.downloaded_height
    return inspect_image_dimensions(snapshot_dir / download.image_path)


def _parse_datetime(value: object) -> datetime | None:
    if value in {None, ""}:
        return None
    text = str(value).strip()
    normalized = text
    if len(normalized) >= 10:
        date_part = normalized[:10].replace("/", "-")
        normalized = f"{date_part}{normalized[10:]}"
    if len(normalized) == 10:
        normalized = f"{normalized}T00:00:00+00:00"
    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        # Some iNaturalist payloads ship non-ISO variants such as
        # `2018-07-06 5:40 AM -03` or `3/13/2010`; keep ingestion resilient by
        # preserving date-only information in UTC.
        date_only = normalized[:10]
        for date_format in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                parsed = datetime.strptime(date_only, date_format)
                return datetime.fromisoformat(parsed.strftime("%Y-%m-%dT00:00:00+00:00"))
            except ValueError:
                continue
        # Older payloads may include textual dates, e.g. `May 2, 2008`.
        for date_format in ("%B %d, %Y", "%b %d, %Y", "%B %d %Y", "%b %d %Y"):
            try:
                parsed = datetime.strptime(text, date_format)
                return datetime.fromisoformat(parsed.strftime("%Y-%m-%dT00:00:00+00:00"))
            except ValueError:
                continue
        raise


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


def _infer_country_code(
    *,
    result: dict[str, object],
    seed: SnapshotTaxonSeed,
) -> str | None:
    explicit_value = _normalize_country_code(
        _extract_explicit_country_code(result)
        or seed.query_params.get("country_code")
    )
    if explicit_value is not None:
        return explicit_value

    place_ids = result.get("place_ids")
    if isinstance(place_ids, list):
        for place_id in place_ids:
            mapped = INAT_PLACE_ID_TO_COUNTRY_CODE.get(str(place_id).strip())
            if mapped is not None:
                return mapped

    seed_place_id = str(seed.query_params.get("place_id") or "").strip()
    if seed_place_id:
        mapped = INAT_PLACE_ID_TO_COUNTRY_CODE.get(seed_place_id)
        if mapped is not None:
            return mapped

    place_guess = str(result.get("place_guess") or "").strip().upper()
    if not place_guess:
        return None
    if ", BE" in place_guess or place_guess.endswith(" BE"):
        return "BE"
    if "BELGIUM" in place_guess or "BELGIQUE" in place_guess or "BELGIE" in place_guess:
        return "BE"
    return None


def _extract_explicit_country_code(result: dict[str, object]) -> str | None:
    direct_value = result.get("country_code")
    if isinstance(direct_value, str) and direct_value.strip():
        return direct_value

    place = result.get("place")
    if isinstance(place, dict):
        place_value = place.get("country_code")
        if isinstance(place_value, str) and place_value.strip():
            return place_value
    return None


def _normalize_country_code(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    if not normalized:
        return None
    if len(normalized) != 2:
        return None
    return normalized


def _assign_missing_canonical_taxon_ids(seeds: list[PilotTaxonSeed]) -> list[PilotTaxonSeed]:
    if all(seed.canonical_taxon_id for seed in seeds):
        return seeds

    existing_ids = [seed.canonical_taxon_id for seed in seeds if seed.canonical_taxon_id]
    updated: list[PilotTaxonSeed] = []
    missing = sorted(
        [seed for seed in seeds if not seed.canonical_taxon_id],
        key=lambda item: item.source_taxon_id,
    )
    assigned_by_source_taxon_id: dict[str, str] = {}
    for seed in missing:
        canonical_taxon_id = next_canonical_taxon_id(
            existing_ids=existing_ids,
            group=TaxonGroup.BIRDS,
        )
        assigned_by_source_taxon_id[seed.source_taxon_id] = canonical_taxon_id
        existing_ids.append(canonical_taxon_id)

    for seed in seeds:
        canonical_taxon_id = seed.canonical_taxon_id or assigned_by_source_taxon_id[
            seed.source_taxon_id
        ]
        updated.append(seed.model_copy(update={"canonical_taxon_id": canonical_taxon_id}))
    return updated
