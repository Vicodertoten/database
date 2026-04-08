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


def render_review_queue(
    repository: SQLiteRepository,
    *,
    review_reason_code: str | None = None,
    stage_name: str | None = None,
    review_status: str | None = None,
    canonical_taxon_id: str | None = None,
    priority: str | None = None,
) -> str:
    rows = repository.fetch_review_queue(
        review_reason_code=review_reason_code,
        stage_name=stage_name,
        review_status=review_status,
        canonical_taxon_id=canonical_taxon_id,
        priority=priority,
    )
    if not rows:
        return "Review queue is empty."
    lines = ["Review queue"]
    for row in rows:
        lines.append(
            f"{row['review_item_id']} | {row['priority']} | {row['stage_name']} | "
            f"{row['review_reason_code']} | "
            f"{row['canonical_taxon_id']} | {row['media_asset_id']} | "
            f"{row['review_status']} | {row['review_note'] or row['review_reason']}"
        )
    return "\n".join(lines)


def render_exportables(repository: SQLiteRepository) -> str:
    rows = repository.fetch_exportable_resources()
    if not rows:
        return "No exportable resources."
    lines = ["Exportable resources"]
    for row in rows:
        lines.append(
            f"{row['qualified_resource_id']} | "
            f"{row['canonical_taxon_id']} | {row['media_asset_id']}"
        )
    return "\n".join(lines)


def render_canonical_governance_review_queue(
    repository: SQLiteRepository,
    *,
    run_id: str | None = None,
    reason_code: str | None = None,
    review_status: str | None = None,
) -> str:
    rows = repository.fetch_canonical_governance_review_queue(
        run_id=run_id,
        reason_code=reason_code,
        review_status=review_status,
    )
    if not rows:
        return "Canonical governance review queue is empty."
    lines = ["Canonical governance review queue"]
    for row in rows:
        lines.append(
            f"{row['governance_review_item_id']} | "
            f"run={row['run_id']} | "
            f"{row['reason_code']} | "
            f"{row['canonical_taxon_id']} | "
            f"{row['review_status']} | "
            f"{row['review_note']}"
        )
    return "\n".join(lines)


def render_canonical_state_events(
    repository: SQLiteRepository,
    *,
    run_id: str | None = None,
    limit: int = 100,
) -> str:
    rows = repository.fetch_canonical_state_events(run_id=run_id, limit=limit)
    if not rows:
        return "Canonical state event log is empty."
    lines = ["Canonical state event log"]
    for row in rows:
        lines.append(
            f"{row['state_event_id']} | run={row['run_id']} | "
            f"{row['event_type']} | {row['canonical_taxon_id']}"
        )
    return "\n".join(lines)


def render_canonical_change_events(
    repository: SQLiteRepository,
    *,
    run_id: str | None = None,
    limit: int = 100,
) -> str:
    rows = repository.fetch_canonical_change_events(run_id=run_id, limit=limit)
    if not rows:
        return "Canonical change event log is empty."
    lines = ["Canonical change event log"]
    for row in rows:
        lines.append(
            f"{row['change_event_id']} | run={row['run_id']} | "
            f"{row['event_type']} | {row['canonical_taxon_id']}"
        )
    return "\n".join(lines)


def render_canonical_governance_events(
    repository: SQLiteRepository,
    *,
    run_id: str | None = None,
    limit: int = 100,
) -> str:
    rows = repository.fetch_canonical_governance_events(run_id=run_id, limit=limit)
    if not rows:
        return "Canonical governance decision log is empty."
    lines = ["Canonical governance decision log"]
    for row in rows:
        lines.append(
            f"{row['governance_event_id']} | run={row['run_id']} | "
            f"{row['decision_status']} | {row['decision_reason']} | "
            f"{row['event_type']} | {row['canonical_taxon_id']}"
        )
    return "\n".join(lines)


def render_run_metrics(repository: SQLiteRepository) -> str:
    metrics = repository.fetch_run_level_metrics()
    return "\n".join(
        [
            "Run metrics",
            f"volume: {metrics['volume']}",
            f"quality: {metrics['quality']}",
            f"governance: {metrics['governance']}",
            f"review_load: {metrics['review_load']}",
            f"cost: {metrics['cost']}",
        ]
    )


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
