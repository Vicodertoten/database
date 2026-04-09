from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from jsonschema import FormatChecker, ValidationError, validate

from database_core.domain.canonical_policy import is_resolved_canonical_taxon_id
from database_core.domain.enums import TaxonStatus
from database_core.domain.models import (
    CanonicalTaxon,
    MediaAsset,
    QualifiedResource,
    ReviewItem,
    SourceObservation,
)
from database_core.versioning import (
    ENRICHMENT_VERSION,
    EXPORT_VERSION,
    NORMALIZED_SNAPSHOT_VERSION,
    SCHEMA_VERSION_LABEL,
)

DEFAULT_EXPORT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "qualified_resources_bundle_v4.schema.json"
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
    run_id: str | None = None,
) -> dict[str, object]:
    exportable_resources = [item for item in qualified_resources if item.export_eligible]
    _validate_exportable_resources_have_canonical_resolution(
        exportable_resources=exportable_resources,
        canonical_taxa=canonical_taxa,
    )
    canonical_taxon_ids = {item.canonical_taxon_id for item in exportable_resources}
    included_taxa = [
        item for item in canonical_taxa if item.canonical_taxon_id in canonical_taxon_ids
    ]
    if export_version != EXPORT_VERSION:
        raise ValueError(f"Unsupported export_version: {export_version}")

    if not run_id:
        raise ValueError("run_id is required when export_version is export.bundle.v4")
    return {
        "schema_version": SCHEMA_VERSION_LABEL,
        "export_version": export_version,
        "qualification_version": qualification_version,
        "enrichment_version": enrichment_version,
        "generated_at": generated_at.isoformat(),
        "canonical_taxa": [_serialize_export_taxon(item) for item in included_taxa],
        "qualified_resources": [
            _serialize_export_resource_v4(item, run_id=run_id) for item in exportable_resources
        ],
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, temp_path_str = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
    temp_path = Path(temp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(serialized)
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def write_export_bundle(
    path: Path,
    payload: dict[str, object],
    *,
    schema_path: Path | None = None,
) -> None:
    validate_export_bundle(payload, schema_path=schema_path)
    write_json(path, payload)


def validate_export_bundle(
    payload: dict[str, object],
    *,
    schema_path: Path | None = None,
) -> None:
    resolved_schema_path = schema_path or _schema_path_for_export_payload(payload)
    try:
        validate(
            instance=payload,
            schema=_load_export_schema(resolved_schema_path),
            format_checker=FormatChecker(),
        )
    except ValidationError as exc:
        location = ".".join(str(item) for item in exc.absolute_path) or "<root>"
        raise ValueError(f"Export bundle validation failed at {location}: {exc.message}") from exc


def _schema_path_for_export_payload(payload: dict[str, object]) -> Path:
    export_version = str(payload.get("export_version") or "")
    if export_version == EXPORT_VERSION:
        return DEFAULT_EXPORT_SCHEMA_PATH
    raise ValueError(f"Cannot resolve schema path for export_version={export_version!r}")


def _serialize_export_taxon(taxon: CanonicalTaxon) -> dict[str, object]:
    payload = {
        "canonical_taxon_id": taxon.canonical_taxon_id,
        "accepted_scientific_name": taxon.accepted_scientific_name,
        "canonical_rank": taxon.canonical_rank,
        "taxon_group": taxon.taxon_group,
        "taxon_status": taxon.taxon_status,
    }
    if taxon.synonyms:
        payload["synonyms"] = list(taxon.synonyms)
    if taxon.common_names:
        payload["common_names"] = list(taxon.common_names)
    if taxon.key_identification_features:
        payload["key_identification_features"] = list(taxon.key_identification_features)
    if taxon.similar_taxon_ids:
        payload["similar_taxon_ids"] = list(taxon.similar_taxon_ids)
    return payload


def _serialize_export_resource_base(
    resource: QualifiedResource,
    *,
    run_id: str,
) -> dict[str, object]:
    provenance = resource.provenance_summary
    return {
        "qualified_resource_id": resource.qualified_resource_id,
        "canonical_taxon_id": resource.canonical_taxon_id,
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
        "provenance": {
            "run_id": run_id,
            "source": {
                "source_name": provenance.source_name,
                "source_observation_key": provenance.source_observation_key,
                "source_media_key": provenance.source_media_key,
                "source_observation_id": provenance.source_observation_id,
                "source_media_id": provenance.source_media_id,
                "raw_payload_ref": provenance.raw_payload_ref,
                "observation_license": provenance.observation_license,
                "media_license": provenance.media_license,
            },
            "qualification_trace": {
                "method": provenance.qualification_method,
                "ai_model": provenance.ai_model,
                "ai_prompt_version": provenance.ai_prompt_version,
                "ai_task_name": provenance.ai_task_name,
                "ai_status": provenance.ai_status,
            },
        },
    }


def _serialize_export_resource_v4(
    resource: QualifiedResource,
    *,
    run_id: str,
) -> dict[str, object]:
    payload = _serialize_export_resource_base(resource, run_id=run_id)
    review_reason_code = (
        resource.qualification_flags[0]
        if resource.qualification_flags
        else None
    )
    payload.update(
        {
            "qualification_flags": list(resource.qualification_flags),
            "qualification_notes": resource.qualification_notes,
            "pedagogy": {
                "difficulty_level": resource.difficulty_level,
                "media_role": resource.media_role,
                "confusion_relevance": resource.confusion_relevance,
                "uncertainty_reason": resource.uncertainty_reason,
            },
            "uncertainty": {
                "type": resource.uncertainty_reason,
                "rationale": resource.qualification_notes,
                "confidence": resource.ai_confidence,
            },
            "review_context": {
                "status": (
                    "overridden"
                    if "human_override" in resource.qualification_flags
                    else "not_required"
                ),
                "reason_code": review_reason_code,
                "override_applied": "human_override" in resource.qualification_flags,
            },
        }
    )
    return payload


@lru_cache(maxsize=4)
def _load_export_schema(schema_path: Path) -> dict[str, object]:
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _validate_exportable_resources_have_canonical_resolution(
    *,
    exportable_resources: list[QualifiedResource],
    canonical_taxa: list[CanonicalTaxon],
) -> None:
    if not exportable_resources:
        return

    canonical_taxa_by_id = {item.canonical_taxon_id: item for item in canonical_taxa}
    unresolved_media_asset_ids = [
        item.media_asset_id
        for item in exportable_resources
        if not is_resolved_canonical_taxon_id(item.canonical_taxon_id)
    ]
    if unresolved_media_asset_ids:
        raise ValueError(
            "Export bundle integrity failure: exportable resources include unresolved "
            "canonical_taxon_id "
            f"(media_asset_ids={','.join(sorted(unresolved_media_asset_ids))})"
        )

    missing_canonical_media_asset_ids = [
        item.media_asset_id
        for item in exportable_resources
        if item.canonical_taxon_id not in canonical_taxa_by_id
    ]
    if missing_canonical_media_asset_ids:
        raise ValueError(
            "Export bundle integrity failure: exportable resources reference missing "
            "canonical taxa "
            f"(media_asset_ids={','.join(sorted(missing_canonical_media_asset_ids))})"
        )

    provisional_media_asset_ids = [
        item.media_asset_id
        for item in exportable_resources
        if canonical_taxa_by_id[item.canonical_taxon_id].taxon_status == TaxonStatus.PROVISIONAL
    ]
    if provisional_media_asset_ids:
        raise ValueError(
            "Export bundle integrity failure: exportable resources reference provisional "
            "canonical taxa "
            f"(media_asset_ids={','.join(sorted(provisional_media_asset_ids))})"
        )
