from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from database_core.adapters.common import SourceDataset
from database_core.domain.enums import SourceName
from database_core.domain.models import (
    AIQualification,
    CanonicalTaxon,
    ExternalMapping,
    LocationMetadata,
    MediaAsset,
    SourceObservation,
    SourceQualityMetadata,
)


def load_fixture_dataset(path: Path) -> SourceDataset:
    payload = json.loads(path.read_text(encoding="utf-8"))
    canonical_taxa = [_build_taxon(item) for item in payload["canonical_taxa"]]

    observations: list[SourceObservation] = []
    media_assets: list[MediaAsset] = []
    for observation_index, observation_payload in enumerate(payload["observations"]):
        observation = _build_observation(observation_payload)
        observations.append(observation)
        for media_index, media_payload in enumerate(observation_payload["media"]):
            media_assets.append(
                _build_media_asset(
                    observation=observation,
                    media_payload=media_payload,
                    fallback_raw_payload_ref=(
                        f"{path.as_posix()}#/observations/{observation_index}/media/{media_index}"
                    ),
                )
            )

    ai_qualifications = {
        media_id: AIQualification(**item)
        for media_id, item in payload.get("ai_fixture_outputs", {}).items()
    }

    return SourceDataset(
        dataset_id=payload["dataset_id"],
        captured_at=datetime.fromisoformat(payload["captured_at"].replace("Z", "+00:00")),
        canonical_taxa=sorted(canonical_taxa, key=lambda item: item.canonical_taxon_id),
        observations=sorted(observations, key=lambda item: item.observation_uid),
        media_assets=sorted(media_assets, key=lambda item: item.media_id),
        ai_qualifications=ai_qualifications,
        cached_image_paths_by_source_media_id={},
    )


def _build_taxon(payload: dict[str, object]) -> CanonicalTaxon:
    return CanonicalTaxon(
        canonical_taxon_id=str(payload["canonical_taxon_id"]),
        scientific_name=str(payload["scientific_name"]),
        canonical_rank=payload["canonical_rank"],
        common_names=list(payload.get("common_names", [])),
        bird_scope_compatible=bool(payload.get("bird_scope_compatible", True)),
        external_source_mappings=[
            ExternalMapping(
                source_name=mapping["source_name"],
                external_id=str(mapping["external_id"]),
            )
            for mapping in payload.get("external_source_mappings", [])
        ],
        similar_taxon_ids=list(payload.get("similar_taxon_ids", [])),
    )


def _build_observation(payload: dict[str, object]) -> SourceObservation:
    source_name = SourceName(str(payload["source_name"]))
    source_observation_id = str(payload["source_observation_id"])
    return SourceObservation(
        observation_uid=f"obs:{source_name}:{source_observation_id}",
        source_name=source_name,
        source_observation_id=source_observation_id,
        source_taxon_id=str(payload["source_taxon_id"]),
        observed_at=datetime.fromisoformat(str(payload["observed_at"]).replace("Z", "+00:00")),
        location=LocationMetadata(**payload.get("location", {})),
        source_quality=SourceQualityMetadata(**payload["source_quality"]),
        raw_payload_ref=str(payload["raw_payload_ref"]),
        canonical_taxon_id=str(payload["canonical_taxon_id"]) if payload.get("canonical_taxon_id") else None,
    )


def _build_media_asset(
    *,
    observation: SourceObservation,
    media_payload: dict[str, object],
    fallback_raw_payload_ref: str,
) -> MediaAsset:
    source_media_id = str(media_payload["source_media_id"])
    return MediaAsset(
        media_id=f"media:{observation.source_name}:{source_media_id}",
        source_name=observation.source_name,
        source_media_id=source_media_id,
        media_type=media_payload["media_type"],
        source_url=str(media_payload["source_url"]),
        attribution=str(media_payload["attribution"]),
        author=str(media_payload["author"]) if media_payload.get("author") else None,
        license=str(media_payload["license"]) if media_payload.get("license") else None,
        mime_type=str(media_payload["mime_type"]) if media_payload.get("mime_type") else None,
        file_extension=str(media_payload["file_extension"]) if media_payload.get("file_extension") else None,
        width=int(media_payload["width"]) if media_payload.get("width") is not None else None,
        height=int(media_payload["height"]) if media_payload.get("height") is not None else None,
        checksum=str(media_payload["checksum"]) if media_payload.get("checksum") else None,
        source_observation_uid=observation.observation_uid,
        canonical_taxon_id=observation.canonical_taxon_id,
        raw_payload_ref=str(media_payload.get("raw_payload_ref", fallback_raw_payload_ref)),
    )
