from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from jsonschema import FormatChecker, ValidationError, validate

from database_core.domain.models import (
    CanonicalTaxon,
    MediaAsset,
    QualifiedResource,
    ReviewItem,
    SourceObservation,
)
from database_core.versioning import (
    ENRICHMENT_VERSION,
    NORMALIZED_SNAPSHOT_VERSION,
    SCHEMA_VERSION_LABEL,
)

DEFAULT_EXPORT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "qualified_resources_bundle.schema.json"
)


def build_normalized_snapshot(
    *,
    dataset_id: str,
    captured_at: datetime,
    enrichment_version: str,
    canonical_taxa: list[CanonicalTaxon],
    observations: list[SourceObservation],
    media_assets: list[MediaAsset],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION_LABEL,
        "normalized_snapshot_version": NORMALIZED_SNAPSHOT_VERSION,
        "dataset_id": dataset_id,
        "captured_at": captured_at.isoformat(),
        "enrichment_version": enrichment_version,
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
        "schema_version": SCHEMA_VERSION_LABEL,
        "qualification_version": qualification_version,
        "generated_at": generated_at.isoformat(),
        "qualified_resources": [item.model_dump(mode="json") for item in qualified_resources],
        "review_queue": [item.model_dump(mode="json") for item in review_items],
    }


def build_export_bundle(
    *,
    export_version: str,
    qualification_version: str,
    enrichment_version: str = ENRICHMENT_VERSION,
    generated_at: datetime,
    canonical_taxa: list[CanonicalTaxon],
    qualified_resources: list[QualifiedResource],
) -> dict[str, object]:
    exportable_resources = [item for item in qualified_resources if item.export_eligible]
    canonical_taxon_ids = {item.canonical_taxon_id for item in exportable_resources}
    included_taxa = [
        item for item in canonical_taxa if item.canonical_taxon_id in canonical_taxon_ids
    ]
    return {
        "schema_version": SCHEMA_VERSION_LABEL,
        "export_version": export_version,
        "qualification_version": qualification_version,
        "enrichment_version": enrichment_version,
        "generated_at": generated_at.isoformat(),
        "canonical_taxa": [_serialize_export_taxon(item) for item in included_taxa],
        "qualified_resources": [_serialize_export_resource(item) for item in exportable_resources],
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_export_bundle(
    path: Path,
    payload: dict[str, object],
    *,
    schema_path: Path = DEFAULT_EXPORT_SCHEMA_PATH,
) -> None:
    validate_export_bundle(payload, schema_path=schema_path)
    write_json(path, payload)


def validate_export_bundle(
    payload: dict[str, object],
    *,
    schema_path: Path = DEFAULT_EXPORT_SCHEMA_PATH,
) -> None:
    try:
        validate(
            instance=payload,
            schema=_load_export_schema(schema_path),
            format_checker=FormatChecker(),
        )
    except ValidationError as exc:
        location = ".".join(str(item) for item in exc.absolute_path) or "<root>"
        raise ValueError(f"Export bundle validation failed at {location}: {exc.message}") from exc


def _serialize_export_taxon(taxon: CanonicalTaxon) -> dict[str, object]:
    payload = {
        "canonical_taxon_id": taxon.canonical_taxon_id,
        "scientific_name": taxon.scientific_name,
        "canonical_rank": taxon.canonical_rank,
        "taxon_group": taxon.taxon_group,
    }
    if taxon.common_names:
        payload["common_names"] = list(taxon.common_names)
    if taxon.key_identification_features:
        payload["key_identification_features"] = list(taxon.key_identification_features)
    if taxon.similar_taxon_ids:
        payload["similar_taxon_ids"] = list(taxon.similar_taxon_ids)
    return payload


def _serialize_export_resource(resource: QualifiedResource) -> dict[str, object]:
    return {
        "qualified_resource_id": resource.qualified_resource_id,
        "canonical_taxon_id": resource.canonical_taxon_id,
        "source_observation_id": resource.source_observation_id,
        "media_asset_id": resource.media_asset_id,
        "qualification_status": resource.qualification_status,
        "qualification_version": resource.qualification_version,
        "technical_quality": resource.technical_quality,
        "pedagogical_quality": resource.pedagogical_quality,
        "life_stage": resource.life_stage,
        "sex": resource.sex,
        "visible_parts": list(resource.visible_parts),
        "view_angle": resource.view_angle,
        "license_safety_result": resource.license_safety_result,
        "export_eligible": resource.export_eligible,
    }


@lru_cache(maxsize=1)
def _load_export_schema(schema_path: Path) -> dict[str, object]:
    return json.loads(schema_path.read_text(encoding="utf-8"))
