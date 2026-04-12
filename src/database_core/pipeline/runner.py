from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from database_core.adapters import (
    DEFAULT_INAT_SNAPSHOT_ROOT,
    load_fixture_dataset,
    load_snapshot_dataset,
)
from database_core.domain.canonical_reconciliation import (
    reconcile_canonical_taxa_with_previous_state,
)
from database_core.domain.enums import TaxonStatus
from database_core.domain.models import (
    CanonicalTaxon,
    GeoPoint,
    MediaAsset,
    PlayableItem,
    QualifiedResource,
    ReviewItem,
    SourceObservation,
)
from database_core.enrichment import enrich_canonical_taxa
from database_core.export.json_exporter import (
    build_export_bundle,
    build_normalized_snapshot,
    build_qualification_snapshot,
    write_export_bundle,
    write_json,
)
from database_core.qualification.ai import (
    DEFAULT_GEMINI_MODEL,
    AIQualifier,
    collect_ai_qualification_outcomes,
)
from database_core.qualification.rules import (
    QUALIFICATION_VERSION,
    build_review_items,
    qualify_media_assets,
)
from database_core.review.overrides import (
    apply_review_overrides as apply_review_overrides_to_resources,
)
from database_core.review.overrides import (
    load_review_override_file,
    resolve_review_overrides_path,
)
from database_core.storage.postgres import PostgresRepository
from database_core.versioning import ENRICHMENT_VERSION, EXPORT_VERSION

DEFAULT_FIXTURE_PATH = Path("data/fixtures/birds_pilot.json")
DEFAULT_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:5432/postgres",
)
DEFAULT_NORMALIZED_PATH = Path("data/normalized/normalized_snapshot.json")
DEFAULT_QUALIFIED_PATH = Path("data/qualified/qualification_snapshot.json")
DEFAULT_EXPORT_PATH = Path("data/exports/qualified_resources_bundle.json")


@dataclass(frozen=True)
class PipelineResult:
    run_id: str
    database_url: str
    normalized_snapshot_path: Path
    qualification_snapshot_path: Path
    export_path: Path
    qualified_resource_count: int
    exportable_resource_count: int
    review_queue_count: int


@dataclass(frozen=True)
class PreparedPipelineState:
    canonical_taxa: list[CanonicalTaxon]
    observations: list[SourceObservation]
    media_assets: list[MediaAsset]
    qualified_resources: list[QualifiedResource]
    review_items: list[ReviewItem]
    playable_items: list[PlayableItem]
    normalized_snapshot: dict[str, object]
    qualification_snapshot: dict[str, object]
    export_bundle: dict[str, object]


def run_pipeline(
    *,
    source_mode: str = "fixture",
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    snapshot_id: str | None = None,
    snapshot_root: Path = DEFAULT_INAT_SNAPSHOT_ROOT,
    snapshot_manifest_path: Path | None = None,
    database_url: str | None = None,
    normalized_snapshot_path: Path = DEFAULT_NORMALIZED_PATH,
    qualification_snapshot_path: Path = DEFAULT_QUALIFIED_PATH,
    export_path: Path = DEFAULT_EXPORT_PATH,
    review_overrides_path: Path | None = None,
    apply_review_overrides: bool = False,
    qualifier_mode: str | None = None,
    uncertain_policy: str | None = None,
    gemini_api_key: str | None = None,
    gemini_model: str = DEFAULT_GEMINI_MODEL,
    ai_qualifier: AIQualifier | None = None,
    allow_schema_reset: bool = False,
    run_id: str | None = None,
) -> PipelineResult:
    resolved_database_url = database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    dataset = _load_dataset(
        source_mode=source_mode,
        fixture_path=fixture_path,
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        snapshot_manifest_path=snapshot_manifest_path,
    )
    resolved_snapshot_id_input = snapshot_id
    if source_mode == "inat_snapshot" and resolved_snapshot_id_input is None:
        resolved_snapshot_id_input = _infer_snapshot_id_from_dataset(dataset.dataset_id)
    resolved_qualifier_mode = qualifier_mode or _default_qualifier_mode(source_mode)
    resolved_uncertain_policy = uncertain_policy or _default_uncertain_policy(source_mode)
    resolved_paths = _resolve_output_paths(
        source_mode=source_mode,
        snapshot_id=resolved_snapshot_id_input,
        snapshot_manifest_path=snapshot_manifest_path,
        normalized_snapshot_path=normalized_snapshot_path,
        qualification_snapshot_path=qualification_snapshot_path,
        export_path=export_path,
    )
    normalized_snapshot_path = resolved_paths["normalized_snapshot_path"]
    qualification_snapshot_path = resolved_paths["qualification_snapshot_path"]
    export_path = resolved_paths["export_path"]
    resolved_snapshot_id = resolved_paths["snapshot_id"]
    resolved_run_id = run_id or _generate_run_id()
    resolved_review_overrides_path = _resolve_review_overrides_path(
        apply_review_overrides=apply_review_overrides,
        source_mode=source_mode,
        review_overrides_path=review_overrides_path,
        snapshot_id=resolved_snapshot_id,
    )
    repository = PostgresRepository(resolved_database_url)
    repository.initialize(allow_schema_reset=allow_schema_reset)
    previous_canonical_taxa = repository.fetch_latest_completed_canonical_taxa()
    prepared_state = _prepare_pipeline_state(
        dataset=dataset,
        previous_canonical_taxa=previous_canonical_taxa,
        run_id=resolved_run_id,
        qualifier_mode=resolved_qualifier_mode,
        uncertain_policy=resolved_uncertain_policy,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        ai_qualifier=ai_qualifier,
        review_overrides_path=resolved_review_overrides_path,
        snapshot_id=resolved_snapshot_id,
    )

    staged_artifacts = _stage_pipeline_artifacts(
        normalized_snapshot_path=normalized_snapshot_path,
        qualification_snapshot_path=qualification_snapshot_path,
        export_path=export_path,
        normalized_snapshot=prepared_state.normalized_snapshot,
        qualification_snapshot=prepared_state.qualification_snapshot,
        export_bundle=prepared_state.export_bundle,
    )

    repository.start_pipeline_run(
        run_id=resolved_run_id,
        source_mode=source_mode,
        dataset_id=dataset.dataset_id,
        snapshot_id=resolved_snapshot_id,
        started_at=datetime.now(UTC),
    )

    try:
        with repository.connect() as connection:
            repository.reset_materialized_state(connection=connection)
            repository.save_canonical_taxa(
                prepared_state.canonical_taxa,
                run_id=resolved_run_id,
                connection=connection,
            )
            repository.save_source_observations(prepared_state.observations, connection=connection)
            repository.save_media_assets(prepared_state.media_assets, connection=connection)
            repository.save_qualified_resources(
                prepared_state.qualified_resources,
                connection=connection,
            )
            repository.save_review_items(prepared_state.review_items, connection=connection)
            repository.save_playable_items(
                prepared_state.playable_items,
                run_id=resolved_run_id,
                connection=connection,
            )
            repository.append_run_history(
                run_id=resolved_run_id,
                governance_effective_at=dataset.captured_at,
                canonical_taxa=prepared_state.canonical_taxa,
                observations=prepared_state.observations,
                media_assets=prepared_state.media_assets,
                qualified_resources=prepared_state.qualified_resources,
                review_items=prepared_state.review_items,
                playable_items=prepared_state.playable_items,
                connection=connection,
            )
    except Exception:
        _cleanup_staged_pipeline_artifacts(staged_artifacts)
        repository.complete_pipeline_run(
            run_id=resolved_run_id,
            completed_at=datetime.now(UTC),
            run_status="failed",
        )
        raise

    try:
        _promote_staged_pipeline_artifacts(staged_artifacts)
    except Exception:
        _cleanup_staged_pipeline_artifacts(staged_artifacts)
        repository.complete_pipeline_run(
            run_id=resolved_run_id,
            completed_at=datetime.now(UTC),
            run_status="artifact_write_failed",
        )
        raise
    finally:
        _cleanup_staged_pipeline_artifacts(staged_artifacts)

    repository.complete_pipeline_run(
        run_id=resolved_run_id,
        completed_at=datetime.now(UTC),
        run_status="completed",
    )

    exportable_resource_count = len(
        [item for item in prepared_state.qualified_resources if item.export_eligible]
    )
    return PipelineResult(
        run_id=resolved_run_id,
        database_url=resolved_database_url,
        normalized_snapshot_path=normalized_snapshot_path,
        qualification_snapshot_path=qualification_snapshot_path,
        export_path=export_path,
        qualified_resource_count=len(prepared_state.qualified_resources),
        exportable_resource_count=exportable_resource_count,
        review_queue_count=len(prepared_state.review_items),
    )


def _prepare_pipeline_state(
    *,
    dataset,
    previous_canonical_taxa: list[CanonicalTaxon],
    run_id: str,
    qualifier_mode: str,
    uncertain_policy: str,
    gemini_api_key: str | None,
    gemini_model: str,
    ai_qualifier: AIQualifier | None,
    review_overrides_path: Path | None,
    snapshot_id: str | None,
) -> PreparedPipelineState:
    canonical_taxa = enrich_canonical_taxa(
        dataset.canonical_taxa,
        taxon_payloads_by_canonical_taxon_id=dataset.taxon_payloads_by_canonical_taxon_id,
    )
    canonical_taxa = reconcile_canonical_taxa_with_previous_state(
        current_taxa=canonical_taxa,
        previous_taxa=previous_canonical_taxa,
    )
    taxon_status_by_id = {item.canonical_taxon_id: item.taxon_status for item in canonical_taxa}
    deprecated_media_asset_ids = sorted(
        [
            item.media_id
            for item in dataset.media_assets
            if taxon_status_by_id.get(item.canonical_taxon_id or "") == TaxonStatus.DEPRECATED
        ]
    )
    if deprecated_media_asset_ids:
        raise ValueError(
            "Canonical integrity failure: deprecated taxa cannot receive new media assets "
            f"(media_asset_ids={','.join(deprecated_media_asset_ids)})"
        )

    ai_qualifications = collect_ai_qualification_outcomes(
        dataset.media_assets,
        qualifier_mode=qualifier_mode,
        precomputed_ai_qualifications=dataset.ai_qualifications,
        precomputed_ai_outcomes=dataset.ai_qualification_outcomes,
        cached_image_paths_by_source_media_key=dataset.cached_image_paths_by_source_media_key,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        qualifier=ai_qualifier,
    )
    qualified_resources, review_items = qualify_media_assets(
        canonical_taxa=canonical_taxa,
        observations=dataset.observations,
        media_assets=dataset.media_assets,
        ai_qualifications_by_source_media_key=ai_qualifications,
        created_at=dataset.captured_at,
        run_id=run_id,
        uncertain_policy=uncertain_policy,
    )
    override_file = (
        load_review_override_file(review_overrides_path, snapshot_id=snapshot_id)
        if review_overrides_path is not None and snapshot_id is not None
        else None
    )
    qualified_resources = apply_review_overrides_to_resources(
        qualified_resources,
        override_file=override_file,
    )
    review_items = build_review_items(qualified_resources, created_at=dataset.captured_at)
    playable_items = _build_playable_items(
        run_id=run_id,
        canonical_taxa=canonical_taxa,
        observations=dataset.observations,
        media_assets=dataset.media_assets,
        qualified_resources=qualified_resources,
    )

    normalized_snapshot = build_normalized_snapshot(
        dataset_id=dataset.dataset_id,
        captured_at=dataset.captured_at,
        enrichment_version=ENRICHMENT_VERSION,
        canonical_taxa=canonical_taxa,
        observations=dataset.observations,
        media_assets=dataset.media_assets,
    )
    qualification_snapshot = build_qualification_snapshot(
        qualification_version=QUALIFICATION_VERSION,
        generated_at=dataset.captured_at,
        qualified_resources=qualified_resources,
        review_items=review_items,
    )
    export_bundle = build_export_bundle(
        export_version=EXPORT_VERSION,
        qualification_version=QUALIFICATION_VERSION,
        enrichment_version=ENRICHMENT_VERSION,
        generated_at=dataset.captured_at,
        canonical_taxa=canonical_taxa,
        qualified_resources=qualified_resources,
        run_id=run_id,
    )
    return PreparedPipelineState(
        canonical_taxa=canonical_taxa,
        observations=list(dataset.observations),
        media_assets=list(dataset.media_assets),
        qualified_resources=qualified_resources,
        review_items=review_items,
        playable_items=playable_items,
        normalized_snapshot=normalized_snapshot,
        qualification_snapshot=qualification_snapshot,
        export_bundle=export_bundle,
    )


def _build_playable_items(
    *,
    run_id: str,
    canonical_taxa: list[CanonicalTaxon],
    observations: list[SourceObservation],
    media_assets: list[MediaAsset],
    qualified_resources: list[QualifiedResource],
) -> list[PlayableItem]:
    canonical_by_id = {item.canonical_taxon_id: item for item in canonical_taxa}
    observations_by_uid = {item.observation_uid: item for item in observations}
    media_assets_by_id = {item.media_id: item for item in media_assets}
    playable_items: list[PlayableItem] = []

    for resource in qualified_resources:
        if not resource.export_eligible:
            continue
        taxon = canonical_by_id.get(resource.canonical_taxon_id)
        if taxon is None:
            raise ValueError(
                "Playable corpus integrity failure: missing canonical taxon for "
                f"qualified_resource_id={resource.qualified_resource_id}"
            )
        observation = observations_by_uid.get(resource.source_observation_uid)
        if observation is None:
            raise ValueError(
                "Playable corpus integrity failure: missing source observation for "
                f"qualified_resource_id={resource.qualified_resource_id}"
            )
        media_asset = media_assets_by_id.get(resource.media_asset_id)
        if media_asset is None:
            raise ValueError(
                "Playable corpus integrity failure: missing media asset for "
                f"qualified_resource_id={resource.qualified_resource_id}"
            )

        location_point = (
            GeoPoint(
                longitude=observation.location.longitude,
                latitude=observation.location.latitude,
            )
            if (
                observation.location.longitude is not None
                and observation.location.latitude is not None
            )
            else None
        )
        playable_items.append(
            PlayableItem(
                playable_item_id=f"playable:{resource.qualified_resource_id}",
                run_id=run_id,
                qualified_resource_id=resource.qualified_resource_id,
                canonical_taxon_id=resource.canonical_taxon_id,
                media_asset_id=resource.media_asset_id,
                source_observation_uid=resource.source_observation_uid,
                source_name=observation.source_name,
                source_observation_id=observation.source_observation_id,
                source_media_id=media_asset.source_media_id,
                scientific_name=taxon.accepted_scientific_name,
                common_names_i18n=_build_common_names_i18n(taxon),
                difficulty_level=resource.difficulty_level,
                media_role=resource.media_role,
                learning_suitability=resource.learning_suitability,
                confusion_relevance=resource.confusion_relevance,
                diagnostic_feature_visibility=resource.diagnostic_feature_visibility,
                similar_taxon_ids=sorted(set(taxon.similar_taxon_ids)),
                what_to_look_at_specific=_dedupe_non_blank_strings(resource.visible_parts),
                what_to_look_at_general=_dedupe_non_blank_strings(
                    taxon.key_identification_features
                ),
                confusion_hint=_build_confusion_hint(taxon=taxon, canonical_by_id=canonical_by_id),
                country_code=observation.location.country_code,
                observed_at=observation.observed_at,
                location_point=location_point,
                location_bbox=None,
                location_radius_meters=None,
            )
        )
    return sorted(playable_items, key=lambda item: item.playable_item_id)


def _build_common_names_i18n(taxon: CanonicalTaxon) -> dict[str, list[str]]:
    """Build multilingual common names dict for PlayableItem.
    
    Uses common_names_by_language if available (from enrichment),
    otherwise falls back to monolingual common_names populated under 'en'.
    """
    # Start with any multilingual names from enrichment
    if taxon.common_names_by_language:
        base = {lang: list(names) for lang, names in taxon.common_names_by_language.items()}
    else:
        base = {}
    
    # Ensure required keys exist with at minimum English names
    for lang in ("fr", "en", "nl"):
        if lang not in base:
            base[lang] = []
    
    # If English wasn't populated from multilingual data, use monolingual fallback
    if not base["en"] and taxon.common_names:
        base["en"] = _dedupe_non_blank_strings(taxon.common_names)
    
    return base


def _build_confusion_hint(
    *,
    taxon: CanonicalTaxon,
    canonical_by_id: dict[str, CanonicalTaxon],
) -> str | None:
    """Build a pedagogical confusion hint with species names in multiple languages where available.
    
    Enhanced to include both scientific names and common names, prioritizing
    English common names but noting multilingual variants for pedagogical clarity.
    """
    if not taxon.similar_taxon_ids:
        return None
    
    similar_species: list[str] = []
    for taxon_id in sorted(set(taxon.similar_taxon_ids)):
        if taxon_id not in canonical_by_id:
            continue
        similar_taxon = canonical_by_id[taxon_id]
        
        # Build entry with scientific name
        entry_parts = [similar_taxon.accepted_scientific_name]
        
        # Add English common name if available
        if (
            similar_taxon.common_names_by_language
            and "en" in similar_taxon.common_names_by_language
        ):
            en_names = similar_taxon.common_names_by_language["en"]
            if en_names:
                entry_parts.append(f"({en_names[0]})")
        elif similar_taxon.common_names:
            # Fallback to monolingual common name
            entry_parts.append(f"({similar_taxon.common_names[0]})")
        
        similar_species.append(" ".join(entry_parts))
    
    if not similar_species:
        return None
    
    # Format hint: limit to 3 species for clarity
    return f"Compare with: {'; '.join(similar_species[:3])}."


def _dedupe_non_blank_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def _load_dataset(
    *,
    source_mode: str,
    fixture_path: Path,
    snapshot_id: str | None,
    snapshot_root: Path,
    snapshot_manifest_path: Path | None,
):
    if source_mode == "fixture":
        return load_fixture_dataset(fixture_path)
    if source_mode == "inat_snapshot":
        return load_snapshot_dataset(
            snapshot_id=snapshot_id,
            snapshot_root=snapshot_root,
            manifest_path=snapshot_manifest_path,
        )
    raise ValueError(f"Unsupported source mode: {source_mode}")


def _default_qualifier_mode(source_mode: str) -> str:
    if source_mode == "inat_snapshot":
        return "cached"
    return "fixture"


def _default_uncertain_policy(source_mode: str) -> str:
    if source_mode == "inat_snapshot":
        return "reject"
    return "review"


def _infer_snapshot_id_from_dataset(dataset_id: str) -> str | None:
    prefix = "inaturalist:"
    if not dataset_id.startswith(prefix):
        return None
    return dataset_id.removeprefix(prefix)


def _resolve_output_paths(
    *,
    source_mode: str,
    snapshot_id: str | None,
    snapshot_manifest_path: Path | None,
    normalized_snapshot_path: Path,
    qualification_snapshot_path: Path,
    export_path: Path,
) -> dict[str, Path | str | None]:
    if source_mode != "inat_snapshot":
        return {
            "normalized_snapshot_path": normalized_snapshot_path,
            "qualification_snapshot_path": qualification_snapshot_path,
            "export_path": export_path,
            "snapshot_id": None,
        }

    resolved_snapshot_id = snapshot_id or (
        snapshot_manifest_path.parent.name if snapshot_manifest_path is not None else None
    )
    if not resolved_snapshot_id:
        return {
            "normalized_snapshot_path": normalized_snapshot_path,
            "qualification_snapshot_path": qualification_snapshot_path,
            "export_path": export_path,
            "snapshot_id": None,
        }

    return {
        "normalized_snapshot_path": (
            Path("data/normalized") / f"{resolved_snapshot_id}.json"
            if normalized_snapshot_path == DEFAULT_NORMALIZED_PATH
            else normalized_snapshot_path
        ),
        "qualification_snapshot_path": (
            Path("data/qualified") / f"{resolved_snapshot_id}.json"
            if qualification_snapshot_path == DEFAULT_QUALIFIED_PATH
            else qualification_snapshot_path
        ),
        "export_path": (
            Path("data/exports") / f"{resolved_snapshot_id}.json"
            if export_path == DEFAULT_EXPORT_PATH
            else export_path
        ),
        "snapshot_id": resolved_snapshot_id,
    }


def _resolve_review_overrides_path(
    *,
    apply_review_overrides: bool,
    source_mode: str,
    review_overrides_path: Path | None,
    snapshot_id: str | None,
) -> Path | None:
    if not apply_review_overrides:
        return None
    if source_mode != "inat_snapshot" or not snapshot_id:
        raise ValueError(
            "Review overrides are only supported for snapshot-scoped inat_snapshot runs"
        )
    if review_overrides_path is not None:
        return review_overrides_path
    return resolve_review_overrides_path(snapshot_id)


def _stage_pipeline_artifacts(
    *,
    normalized_snapshot_path: Path,
    qualification_snapshot_path: Path,
    export_path: Path,
    normalized_snapshot: dict[str, object],
    qualification_snapshot: dict[str, object],
    export_bundle: dict[str, object],
) -> list[tuple[Path, Path]]:
    temporary_normalized = _temporary_output_path(normalized_snapshot_path)
    temporary_qualification = _temporary_output_path(qualification_snapshot_path)
    temporary_export = _temporary_output_path(export_path)
    write_json(temporary_normalized, normalized_snapshot)
    write_json(temporary_qualification, qualification_snapshot)
    write_export_bundle(temporary_export, export_bundle)
    return [
        (temporary_normalized, normalized_snapshot_path),
        (temporary_qualification, qualification_snapshot_path),
        (temporary_export, export_path),
    ]


def _promote_staged_pipeline_artifacts(staged_artifacts: list[tuple[Path, Path]]) -> None:
    for temporary_path, final_path in staged_artifacts:
        temporary_path.replace(final_path)


def _cleanup_staged_pipeline_artifacts(staged_artifacts: list[tuple[Path, Path]]) -> None:
    for temporary_path, _ in staged_artifacts:
        temporary_path.unlink(missing_ok=True)


def _temporary_output_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.tmp-{uuid4().hex}")


def _generate_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"run:{timestamp}:{uuid4().hex[:8]}"
