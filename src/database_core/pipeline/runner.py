from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from database_core.adapters import (
    DEFAULT_INAT_SNAPSHOT_ROOT,
    load_fixture_dataset,
    load_snapshot_dataset,
)
from database_core.export.json_exporter import (
    build_export_bundle,
    build_normalized_snapshot,
    build_qualification_snapshot,
    write_json,
)
from database_core.qualification.ai import (
    AIQualifier,
    DEFAULT_GEMINI_MODEL,
    collect_ai_qualification_outcomes,
)
from database_core.qualification.rules import QUALIFICATION_VERSION, qualify_media_assets
from database_core.storage.sqlite import SQLiteRepository


DEFAULT_FIXTURE_PATH = Path("data/fixtures/birds_pilot.json")
DEFAULT_DB_PATH = Path("data/database.sqlite")
DEFAULT_NORMALIZED_PATH = Path("data/normalized/normalized_snapshot.json")
DEFAULT_QUALIFIED_PATH = Path("data/qualified/qualification_snapshot.json")
DEFAULT_EXPORT_PATH = Path("data/exports/qualified_resources_bundle.json")
DEFAULT_DATABASES_DIR = Path("data/databases")


@dataclass(frozen=True)
class PipelineResult:
    database_path: Path
    normalized_snapshot_path: Path
    qualification_snapshot_path: Path
    export_path: Path
    qualified_resource_count: int
    exportable_resource_count: int
    review_queue_count: int


def run_pipeline(
    *,
    source_mode: str = "fixture",
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    snapshot_id: str | None = None,
    snapshot_root: Path = DEFAULT_INAT_SNAPSHOT_ROOT,
    snapshot_manifest_path: Path | None = None,
    db_path: Path = DEFAULT_DB_PATH,
    normalized_snapshot_path: Path = DEFAULT_NORMALIZED_PATH,
    qualification_snapshot_path: Path = DEFAULT_QUALIFIED_PATH,
    export_path: Path = DEFAULT_EXPORT_PATH,
    qualifier_mode: str | None = None,
    uncertain_policy: str | None = None,
    gemini_api_key: str | None = None,
    gemini_model: str = DEFAULT_GEMINI_MODEL,
    ai_qualifier: AIQualifier | None = None,
) -> PipelineResult:
    dataset = _load_dataset(
        source_mode=source_mode,
        fixture_path=fixture_path,
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        snapshot_manifest_path=snapshot_manifest_path,
    )
    resolved_qualifier_mode = qualifier_mode or _default_qualifier_mode(source_mode)
    resolved_uncertain_policy = uncertain_policy or _default_uncertain_policy(source_mode)
    resolved_paths = _resolve_output_paths(
        source_mode=source_mode,
        snapshot_id=snapshot_id,
        snapshot_manifest_path=snapshot_manifest_path,
        db_path=db_path,
        normalized_snapshot_path=normalized_snapshot_path,
        qualification_snapshot_path=qualification_snapshot_path,
        export_path=export_path,
    )
    db_path = resolved_paths["db_path"]
    normalized_snapshot_path = resolved_paths["normalized_snapshot_path"]
    qualification_snapshot_path = resolved_paths["qualification_snapshot_path"]
    export_path = resolved_paths["export_path"]
    repository = SQLiteRepository(db_path)
    repository.initialize()
    repository.reset()
    repository.save_canonical_taxa(dataset.canonical_taxa)
    repository.save_source_observations(dataset.observations)
    repository.save_media_assets(dataset.media_assets)

    ai_qualifications = collect_ai_qualification_outcomes(
        dataset.media_assets,
        qualifier_mode=resolved_qualifier_mode,
        precomputed_ai_qualifications=dataset.ai_qualifications,
        precomputed_ai_outcomes=dataset.ai_qualification_outcomes,
        cached_image_paths_by_source_media_id=dataset.cached_image_paths_by_source_media_id,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        qualifier=ai_qualifier,
    )
    qualified_resources, review_items = qualify_media_assets(
        observations=dataset.observations,
        media_assets=dataset.media_assets,
        ai_qualifications_by_source_media_id=ai_qualifications,
        created_at=dataset.captured_at,
        uncertain_policy=resolved_uncertain_policy,
    )
    repository.save_qualified_resources(qualified_resources)
    repository.save_review_items(review_items)

    normalized_snapshot = build_normalized_snapshot(
        dataset_id=dataset.dataset_id,
        captured_at=dataset.captured_at,
        canonical_taxa=dataset.canonical_taxa,
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
        export_version=QUALIFICATION_VERSION,
        generated_at=dataset.captured_at,
        canonical_taxa=dataset.canonical_taxa,
        qualified_resources=qualified_resources,
    )

    write_json(normalized_snapshot_path, normalized_snapshot)
    write_json(qualification_snapshot_path, qualification_snapshot)
    write_json(export_path, export_bundle)

    exportable_resource_count = len([item for item in qualified_resources if item.export_eligible])
    return PipelineResult(
        database_path=db_path,
        normalized_snapshot_path=normalized_snapshot_path,
        qualification_snapshot_path=qualification_snapshot_path,
        export_path=export_path,
        qualified_resource_count=len(qualified_resources),
        exportable_resource_count=exportable_resource_count,
        review_queue_count=len(review_items),
    )


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


def _resolve_output_paths(
    *,
    source_mode: str,
    snapshot_id: str | None,
    snapshot_manifest_path: Path | None,
    db_path: Path,
    normalized_snapshot_path: Path,
    qualification_snapshot_path: Path,
    export_path: Path,
) -> dict[str, Path]:
    if source_mode != "inat_snapshot":
        return {
            "db_path": db_path,
            "normalized_snapshot_path": normalized_snapshot_path,
            "qualification_snapshot_path": qualification_snapshot_path,
            "export_path": export_path,
        }

    resolved_snapshot_id = snapshot_id or (
        snapshot_manifest_path.parent.name if snapshot_manifest_path is not None else None
    )
    if not resolved_snapshot_id:
        return {
            "db_path": db_path,
            "normalized_snapshot_path": normalized_snapshot_path,
            "qualification_snapshot_path": qualification_snapshot_path,
            "export_path": export_path,
        }

    return {
        "db_path": (
            DEFAULT_DATABASES_DIR / f"{resolved_snapshot_id}.sqlite"
            if db_path == DEFAULT_DB_PATH
            else db_path
        ),
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
    }
