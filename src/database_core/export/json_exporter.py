from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from database_core.domain.models import CanonicalTaxon, MediaAsset, QualifiedResource, ReviewItem, SourceObservation


def build_normalized_snapshot(
    *,
    dataset_id: str,
    captured_at: datetime,
    canonical_taxa: list[CanonicalTaxon],
    observations: list[SourceObservation],
    media_assets: list[MediaAsset],
) -> dict[str, object]:
    return {
        "dataset_id": dataset_id,
        "captured_at": captured_at.isoformat(),
        "canonical_taxa": [item.model_dump(mode="json") for item in canonical_taxa],
        "source_observations": [item.model_dump(mode="json") for item in observations],
        "media_assets": [item.model_dump(mode="json") for item in media_assets],
    }


def build_qualification_snapshot(
    *,
    qualification_version: str,
    generated_at: datetime,
    qualified_resources: list[QualifiedResource],
    review_items: list[ReviewItem],
) -> dict[str, object]:
    return {
        "qualification_version": qualification_version,
        "generated_at": generated_at.isoformat(),
        "qualified_resources": [item.model_dump(mode="json") for item in qualified_resources],
        "review_queue": [item.model_dump(mode="json") for item in review_items],
    }


def build_export_bundle(
    *,
    export_version: str,
    generated_at: datetime,
    canonical_taxa: list[CanonicalTaxon],
    qualified_resources: list[QualifiedResource],
) -> dict[str, object]:
    exportable_resources = [item for item in qualified_resources if item.export_eligible]
    canonical_taxon_ids = {item.canonical_taxon_id for item in exportable_resources}
    included_taxa = [item for item in canonical_taxa if item.canonical_taxon_id in canonical_taxon_ids]
    return {
        "export_version": export_version,
        "generated_at": generated_at.isoformat(),
        "canonical_taxa": [item.model_dump(mode="json") for item in included_taxa],
        "qualified_resources": [item.model_dump(mode="json") for item in exportable_resources],
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

