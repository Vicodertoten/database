from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from database_core.adapters.common import SourceDataset
from database_core.domain.enums import CanonicalRank, SourceName
from database_core.domain.models import (
    AIQualification,
    CanonicalTaxon,
    ExternalMapping,
    LocationMetadata,
    MediaAsset,
    SourceObservation,
    SourceQualityMetadata,
)

DEFAULT_INAT_SNAPSHOT_ROOT = Path("data/raw/inaturalist")
DEFAULT_PILOT_TAXA_PATH = Path("data/fixtures/inaturalist_pilot_taxa.json")


class SnapshotModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())


class PilotTaxonSeed(SnapshotModel):
    canonical_taxon_id: str
    scientific_name: str
    canonical_rank: CanonicalRank = CanonicalRank.SPECIES
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
    scientific_name: str
    canonical_rank: CanonicalRank = CanonicalRank.SPECIES
    common_names: list[str] = Field(default_factory=list)
    source_taxon_id: str
    query_params: dict[str, str]
    response_path: str


class SnapshotMediaDownload(SnapshotModel):
    source_observation_id: str
    source_media_id: str
    image_path: str
    download_status: str
    source_url: str
    mime_type: str | None = None
    sha256: str | None = None


class InaturalistSnapshotManifest(SnapshotModel):
    snapshot_id: str
    source_name: SourceName = SourceName.INATURALIST
    created_at: datetime
    taxon_seeds: list[SnapshotTaxonSeed]
    media_downloads: list[SnapshotMediaDownload]
    ai_outputs_path: str | None = None


def load_pilot_taxa(path: Path = DEFAULT_PILOT_TAXA_PATH) -> list[PilotTaxonSeed]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [PilotTaxonSeed(**item) for item in payload]


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

    manifest = InaturalistSnapshotManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    return manifest, manifest_path.parent


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
    canonical_taxa = sorted(
        [_build_canonical_taxon(seed) for seed in manifest.taxon_seeds],
        key=lambda item: item.canonical_taxon_id,
    )
    observations: list[SourceObservation] = []
    media_assets: list[MediaAsset] = []
    download_by_media_id = {item.source_media_id: item for item in manifest.media_downloads}

    for seed in sorted(manifest.taxon_seeds, key=lambda item: item.canonical_taxon_id):
        payload = json.loads((snapshot_dir / seed.response_path).read_text(encoding="utf-8"))
        for raw_index, result in enumerate(payload.get("results", [])):
            if not _is_supported_observation(result, seed.source_taxon_id):
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
                    download=download_by_media_id.get(str(primary_photo["id"])),
                    response_path=seed.response_path,
                    raw_index=raw_index,
                )
            )

    return SourceDataset(
        dataset_id=f"{manifest.source_name}:{manifest.snapshot_id}",
        captured_at=manifest.created_at,
        canonical_taxa=canonical_taxa,
        observations=sorted(observations, key=lambda item: item.observation_uid),
        media_assets=sorted(media_assets, key=lambda item: item.media_id),
        ai_qualifications=_load_ai_outputs(snapshot_dir, manifest.ai_outputs_path),
        cached_image_paths_by_source_media_id={
            item.source_media_id: snapshot_dir / item.image_path for item in manifest.media_downloads
        },
    )


def summarize_snapshot_manifest(
    *,
    snapshot_id: str | None = None,
    snapshot_root: Path = DEFAULT_INAT_SNAPSHOT_ROOT,
    manifest_path: Path | None = None,
) -> dict[str, int]:
    manifest, snapshot_dir = load_snapshot_manifest(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        manifest_path=manifest_path,
    )
    harvested_observations = 0
    for seed in manifest.taxon_seeds:
        payload = json.loads((snapshot_dir / seed.response_path).read_text(encoding="utf-8"))
        harvested_observations += len(
            [
                item
                for item in payload.get("results", [])
                if _is_supported_observation(item, seed.source_taxon_id)
            ]
        )
    downloaded_images = len(
        [
            item
            for item in manifest.media_downloads
            if item.download_status == "downloaded" and (snapshot_dir / item.image_path).exists()
        ]
    )
    return {
        "harvested_observations": harvested_observations,
        "downloaded_images": downloaded_images,
    }


def _build_canonical_taxon(seed: SnapshotTaxonSeed) -> CanonicalTaxon:
    return CanonicalTaxon(
        canonical_taxon_id=seed.canonical_taxon_id,
        scientific_name=seed.scientific_name,
        canonical_rank=seed.canonical_rank,
        common_names=seed.common_names,
        bird_scope_compatible=True,
        external_source_mappings=[
            ExternalMapping(source_name=SourceName.INATURALIST, external_id=seed.source_taxon_id)
        ],
        similar_taxon_ids=[],
    )


def _is_supported_observation(result: dict[str, object], seed_source_taxon_id: str) -> bool:
    photos = result.get("photos") or []
    if result.get("quality_grade") != "research" or not photos:
        return False
    taxon = result.get("taxon") or {}
    taxon_id = str(taxon.get("id", ""))
    ancestor_ids = {str(item) for item in taxon.get("ancestor_ids", [])}
    return taxon_id == seed_source_taxon_id or seed_source_taxon_id in ancestor_ids


def _build_snapshot_observation(
    *,
    result: dict[str, object],
    seed: SnapshotTaxonSeed,
    response_path: str,
    raw_index: int,
) -> SourceObservation:
    geojson = result.get("geojson") or {}
    coordinates = geojson.get("coordinates") or [None, None]
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
) -> MediaAsset:
    source_url = (
        photo.get("original_url")
        or photo.get("large_url")
        or photo.get("medium_url")
        or photo.get("url")
        or observation.raw_payload_ref
    )
    original_dimensions = photo.get("original_dimensions") or {}
    return MediaAsset(
        media_id=f"media:inaturalist:{photo['id']}",
        source_name=SourceName.INATURALIST,
        source_media_id=str(photo["id"]),
        media_type="image",
        source_url=str(source_url),
        attribution=str(photo.get("attribution") or "unknown attribution"),
        author=str(photo.get("attribution_name")) if photo.get("attribution_name") else None,
        license=str(photo.get("license_code")) if photo.get("license_code") else None,
        mime_type=download.mime_type if download and download.mime_type else _guess_mime_type(str(source_url)),
        file_extension=_guess_extension(str(source_url)),
        width=original_dimensions.get("width"),
        height=original_dimensions.get("height"),
        checksum=download.sha256 if download else None,
        source_observation_uid=observation.observation_uid,
        canonical_taxon_id=observation.canonical_taxon_id,
        raw_payload_ref=f"{response_path}#/results/{raw_index}",
    )


def _load_ai_outputs(snapshot_dir: Path, ai_outputs_path: str | None) -> dict[str, AIQualification]:
    if ai_outputs_path is None:
        return {}
    payload = json.loads((snapshot_dir / ai_outputs_path).read_text(encoding="utf-8"))
    return {media_id: AIQualification(**item) for media_id, item in payload.items()}


def _parse_datetime(value: object) -> datetime | None:
    if value in {None, ""}:
        return None
    text = str(value)
    if len(text) == 10:
        text = f"{text}T00:00:00+00:00"
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


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
