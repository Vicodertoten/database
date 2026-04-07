from __future__ import annotations

from pathlib import Path

from database_core.adapters import summarize_snapshot_manifest
from database_core.storage.sqlite import SQLiteRepository


def render_summary(repository: SQLiteRepository) -> str:
    summary = repository.fetch_summary()
    return "\n".join(
        [
            "Summary",
            f"canonical_taxa: {summary['canonical_taxa']}",
            f"source_observations: {summary['source_observations']}",
            f"media_assets: {summary['media_assets']}",
            f"qualified_resources: {summary['qualified_resources']}",
            f"review_queue: {summary['review_queue']}",
        ]
    )


def render_review_queue(repository: SQLiteRepository) -> str:
    rows = repository.fetch_review_queue()
    if not rows:
        return "Review queue is empty."
    lines = ["Review queue"]
    for row in rows:
        lines.append(
            f"{row['review_item_id']} | {row['canonical_taxon_id']} | {row['media_asset_id']} | "
            f"{row['review_status']} | {row['review_reason']}"
        )
    return "\n".join(lines)


def render_exportables(repository: SQLiteRepository) -> str:
    rows = repository.fetch_exportable_resources()
    if not rows:
        return "No exportable resources."
    lines = ["Exportable resources"]
    for row in rows:
        lines.append(
            f"{row['qualified_resource_id']} | {row['canonical_taxon_id']} | {row['media_asset_id']}"
        )
    return "\n".join(lines)


def render_snapshot_health(
    repository: SQLiteRepository,
    *,
    snapshot_id: str | None,
    snapshot_root: Path,
    manifest_path: Path | None = None,
) -> str:
    snapshot_metrics = summarize_snapshot_manifest(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        manifest_path=manifest_path,
    )
    qualification_metrics = repository.fetch_qualification_metrics()
    return "\n".join(
        [
            "Snapshot health",
            f"harvested_observations: {snapshot_metrics['harvested_observations']}",
            f"taxa_with_results: {snapshot_metrics['taxa_with_results']}",
            f"harvested_per_taxon: {snapshot_metrics['harvested_per_taxon']}",
            f"downloaded_images: {snapshot_metrics['downloaded_images']}",
            f"images_sent_to_gemini: {snapshot_metrics['images_sent_to_gemini']}",
            f"insufficient_resolution_images: {snapshot_metrics['insufficient_resolution_images']}",
            f"ai_valid_outputs: {snapshot_metrics['ai_valid_outputs']}",
            f"ai_qualified_images: {qualification_metrics['ai_qualified_images']}",
            f"accepted_resources: {qualification_metrics['accepted_resources']}",
            f"rejected_resources: {qualification_metrics['rejected_resources']}",
            f"review_required_resources: {qualification_metrics['review_required_resources']}",
            f"exportable_resources: {qualification_metrics['exportable_resources']}",
            f"review_queue: {qualification_metrics['review_queue_count']}",
            f"license_distribution: {qualification_metrics['license_distribution']}",
            f"ai_model_distribution: {qualification_metrics['ai_model_distribution']}",
            f"top_rejection_flags: {qualification_metrics['top_rejection_flags']}",
        ]
    )
