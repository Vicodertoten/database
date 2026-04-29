from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from database_core.adapters import (
    DEFAULT_INAT_SNAPSHOT_ROOT,
    DEFAULT_INITIAL_BACKOFF_SECONDS,
    DEFAULT_MAX_BACKOFF_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_PILOT_TAXA_PATH,
    DEFAULT_REQUEST_INTERVAL_SECONDS,
    fetch_inat_snapshot,
    qualify_inat_snapshot,
)
from database_core.domain.models import ConfusionEventInput, PackRevisionParameters
from database_core.inspect.summary import (
    render_canonical_change_events,
    render_canonical_governance_events,
    render_canonical_governance_review_queue,
    render_canonical_state_events,
    render_confusion_aggregates_global,
    render_confusion_events,
    render_confusion_metrics,
    render_enrichment_executions,
    render_enrichment_metrics,
    render_enrichment_requests,
    render_exportables,
    render_playable_invalidations,
    render_review_queue,
    render_run_metrics,
    render_snapshot_health,
    render_summary,
)
from database_core.pipeline.runner import (
    DEFAULT_DATABASE_URL,
    DEFAULT_EXPORT_PATH,
    DEFAULT_FIXTURE_PATH,
    DEFAULT_NORMALIZED_PATH,
    DEFAULT_QUALIFIED_PATH,
    run_pipeline,
)
from database_core.qualification.ai import DEFAULT_GEMINI_MODEL
from database_core.review.overrides import (
    initialize_review_override_file,
    load_review_override_file,
    resolve_review_overrides_path,
    upsert_review_override,
)
from database_core.security import redact_database_url
from database_core.storage.services import build_storage_services


def default_snapshot_id(*, prefix: str = "inaturalist-birds") -> str:
    return f"{prefix}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"


def main() -> None:
    load_dotenv(dotenv_path=Path(".env"))
    parser = argparse.ArgumentParser(prog="database-core")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pipeline_parser = subparsers.add_parser("run-pipeline")
    pipeline_parser.add_argument("--fixture-path", type=Path, default=DEFAULT_FIXTURE_PATH)
    pipeline_parser.add_argument(
        "--source-mode", choices=["fixture", "inat_snapshot"], default="fixture"
    )
    pipeline_parser.add_argument("--snapshot-id", type=str)
    pipeline_parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_INAT_SNAPSHOT_ROOT)
    pipeline_parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    pipeline_parser.add_argument("--normalized-path", type=Path, default=DEFAULT_NORMALIZED_PATH)
    pipeline_parser.add_argument("--qualified-path", type=Path, default=DEFAULT_QUALIFIED_PATH)
    pipeline_parser.add_argument("--export-path", type=Path, default=DEFAULT_EXPORT_PATH)
    pipeline_parser.add_argument(
        "--allow-schema-reset",
        action="store_true",
        help="local-dev only: recreate DB file when schema version mismatches",
    )
    pipeline_parser.add_argument("--apply-review-overrides", action="store_true")
    pipeline_parser.add_argument("--review-overrides-path", type=Path)
    pipeline_parser.add_argument(
        "--qualifier-mode", choices=["fixture", "rules", "cached", "gemini"]
    )
    pipeline_parser.add_argument("--uncertain-policy", choices=["review", "reject"])
    pipeline_parser.add_argument("--gemini-api-key-env", default="GEMINI_API_KEY")
    pipeline_parser.add_argument("--gemini-model", default=DEFAULT_GEMINI_MODEL)

    fetch_parser = subparsers.add_parser("fetch-inat-snapshot")
    fetch_parser.add_argument("--snapshot-id", type=str)
    fetch_parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_INAT_SNAPSHOT_ROOT)
    fetch_parser.add_argument("--pilot-taxa-path", type=Path, default=DEFAULT_PILOT_TAXA_PATH)
    fetch_parser.add_argument("--max-observations-per-taxon", type=int, default=5)
    fetch_parser.add_argument("--timeout-seconds", type=int, default=30)
    fetch_parser.add_argument(
        "--bbox",
        type=str,
        help="min_longitude,min_latitude,max_longitude,max_latitude",
    )
    fetch_parser.add_argument("--place-id", type=str)
    fetch_parser.add_argument("--country-code", type=str)
    fetch_parser.add_argument("--observed-from", type=str)
    fetch_parser.add_argument("--observed-to", type=str)

    qualify_parser = subparsers.add_parser("qualify-inat-snapshot")
    qualify_parser.add_argument("--snapshot-id", required=True)
    qualify_parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_INAT_SNAPSHOT_ROOT)
    qualify_parser.add_argument("--gemini-api-key-env", default="GEMINI_API_KEY")
    qualify_parser.add_argument("--gemini-model", default=DEFAULT_GEMINI_MODEL)
    qualify_parser.add_argument(
        "--request-interval-seconds", type=float, default=DEFAULT_REQUEST_INTERVAL_SECONDS
    )
    qualify_parser.add_argument("--max-retries", type=int, default=DEFAULT_MAX_RETRIES)
    qualify_parser.add_argument(
        "--initial-backoff-seconds", type=float, default=DEFAULT_INITIAL_BACKOFF_SECONDS
    )
    qualify_parser.add_argument(
        "--max-backoff-seconds", type=float, default=DEFAULT_MAX_BACKOFF_SECONDS
    )

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument(
        "view",
        choices=[
            "summary",
            "review-queue",
            "canonical-governance-review-queue",
            "canonical-state-events",
            "canonical-change-events",
            "canonical-governance-events",
            "exportables",
            "snapshot-health",
            "run-metrics",
            "playable-corpus",
            "playable-invalidations",
            "pack-specs",
            "pack-revisions",
            "pack-diagnostics",
            "compiled-pack-builds",
            "pack-materializations",
            "enrichment-requests",
            "enrichment-executions",
            "enrichment-metrics",
            "confusion-events",
            "confusion-aggregates-global",
            "confusion-metrics",
        ],
    )
    inspect_parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    inspect_parser.add_argument("--snapshot-id", type=str)
    inspect_parser.add_argument("--enrichment-request-id", type=str)
    inspect_parser.add_argument("--enrichment-status", type=str)
    inspect_parser.add_argument("--batch-id", type=str)
    inspect_parser.add_argument("--taxon-confused-for-id", type=str)
    inspect_parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_INAT_SNAPSHOT_ROOT)
    inspect_parser.add_argument("--review-reason-code", type=str)
    inspect_parser.add_argument("--stage-name", type=str)
    inspect_parser.add_argument("--review-status", type=str)
    inspect_parser.add_argument("--canonical-taxon-id", type=str)
    inspect_parser.add_argument("--priority", type=str)
    inspect_parser.add_argument("--run-id", type=str)
    inspect_parser.add_argument("--invalidation-reason", type=str)
    inspect_parser.add_argument("--lifecycle-status", type=str)
    inspect_parser.add_argument("--limit", type=int, default=100)
    inspect_parser.add_argument("--difficulty-level", type=str)
    inspect_parser.add_argument("--media-role", type=str)
    inspect_parser.add_argument("--learning-suitability", type=str)
    inspect_parser.add_argument("--confusion-relevance", type=str)
    inspect_parser.add_argument("--country-code", type=str)
    inspect_parser.add_argument("--observed-from", type=str)
    inspect_parser.add_argument("--observed-to", type=str)
    inspect_parser.add_argument(
        "--bbox",
        type=str,
        help="min_longitude,min_latitude,max_longitude,max_latitude",
    )
    inspect_parser.add_argument(
        "--point-radius",
        type=str,
        help="longitude,latitude,radius_meters",
    )
    inspect_parser.add_argument("--pack-id", type=str)
    inspect_parser.add_argument("--revision", type=int)
    inspect_parser.add_argument(
        "--purpose",
        choices=["assignment", "daily_challenge"],
        type=str,
    )

    pack_parser = subparsers.add_parser("pack")
    pack_subparsers = pack_parser.add_subparsers(dest="pack_command", required=True)

    pack_create_parser = pack_subparsers.add_parser("create")
    pack_create_parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    pack_create_parser.add_argument("--pack-id", type=str)
    pack_create_parser.add_argument(
        "--canonical-taxon-id",
        action="append",
        dest="canonical_taxon_ids",
        required=True,
    )
    pack_create_parser.add_argument(
        "--difficulty-policy",
        choices=["easy", "balanced", "hard", "mixed"],
        required=True,
    )
    pack_create_parser.add_argument("--country-code", type=str)
    pack_create_parser.add_argument(
        "--bbox",
        type=str,
        help="min_longitude,min_latitude,max_longitude,max_latitude",
    )
    pack_create_parser.add_argument(
        "--point-radius",
        type=str,
        help="longitude,latitude,radius_meters",
    )
    pack_create_parser.add_argument("--observed-from", type=str)
    pack_create_parser.add_argument("--observed-to", type=str)
    pack_create_parser.add_argument("--owner-id", type=str)
    pack_create_parser.add_argument("--org-id", type=str)
    pack_create_parser.add_argument(
        "--visibility",
        choices=["private", "org", "public"],
        default="private",
    )
    pack_create_parser.add_argument("--intended-use", type=str, default="training")

    pack_revise_parser = pack_subparsers.add_parser("revise")
    pack_revise_parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    pack_revise_parser.add_argument("--pack-id", required=True)
    pack_revise_parser.add_argument(
        "--canonical-taxon-id",
        action="append",
        dest="canonical_taxon_ids",
        required=True,
    )
    pack_revise_parser.add_argument(
        "--difficulty-policy",
        choices=["easy", "balanced", "hard", "mixed"],
        required=True,
    )
    pack_revise_parser.add_argument("--country-code", type=str)
    pack_revise_parser.add_argument(
        "--bbox",
        type=str,
        help="min_longitude,min_latitude,max_longitude,max_latitude",
    )
    pack_revise_parser.add_argument(
        "--point-radius",
        type=str,
        help="longitude,latitude,radius_meters",
    )
    pack_revise_parser.add_argument("--observed-from", type=str)
    pack_revise_parser.add_argument("--observed-to", type=str)
    pack_revise_parser.add_argument("--owner-id", type=str)
    pack_revise_parser.add_argument("--org-id", type=str)
    pack_revise_parser.add_argument(
        "--visibility",
        choices=["private", "org", "public"],
        default="private",
    )
    pack_revise_parser.add_argument("--intended-use", type=str, default="training")

    pack_diagnose_parser = pack_subparsers.add_parser("diagnose")
    pack_diagnose_parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    pack_diagnose_parser.add_argument("--pack-id", required=True)
    pack_diagnose_parser.add_argument("--revision", type=int)

    pack_compile_parser = pack_subparsers.add_parser("compile")
    pack_compile_parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    pack_compile_parser.add_argument("--pack-id", required=True)
    pack_compile_parser.add_argument("--revision", type=int)
    pack_compile_parser.add_argument("--question-count", type=int, default=20)
    pack_compile_parser.add_argument(
        "--contract-version",
        choices=["v1", "v2"],
        default="v1",
    )

    pack_materialize_parser = pack_subparsers.add_parser("materialize")
    pack_materialize_parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    pack_materialize_parser.add_argument("--pack-id", required=True)
    pack_materialize_parser.add_argument("--revision", type=int)
    pack_materialize_parser.add_argument("--question-count", type=int, default=20)
    pack_materialize_parser.add_argument(
        "--contract-version",
        choices=["v1", "v2"],
        default="v1",
    )
    pack_materialize_parser.add_argument(
        "--purpose",
        choices=["assignment", "daily_challenge"],
        default="assignment",
    )
    pack_materialize_parser.add_argument("--ttl-hours", type=int)

    pack_enrich_enqueue_parser = pack_subparsers.add_parser("enrich-enqueue")
    pack_enrich_enqueue_parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    pack_enrich_enqueue_parser.add_argument("--pack-id", required=True)
    pack_enrich_enqueue_parser.add_argument("--revision", type=int)
    pack_enrich_enqueue_parser.add_argument("--question-count", type=int, default=20)

    pack_enrich_execute_parser = pack_subparsers.add_parser("enrich-execute")
    pack_enrich_execute_parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    pack_enrich_execute_parser.add_argument("--enrichment-request-id", required=True)
    pack_enrich_execute_parser.add_argument(
        "--execution-status",
        choices=["success", "partial", "failed"],
        default="success",
    )
    pack_enrich_execute_parser.add_argument("--error-info", type=str)
    pack_enrich_execute_parser.add_argument("--trigger-recompile", action="store_true")

    confusion_parser = subparsers.add_parser("confusion")
    confusion_subparsers = confusion_parser.add_subparsers(
        dest="confusion_command", required=True
    )

    confusion_ingest_parser = confusion_subparsers.add_parser("ingest-batch")
    confusion_ingest_parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    confusion_ingest_parser.add_argument("--batch-id", required=True)
    confusion_ingest_parser.add_argument("--events-file", type=Path, required=True)

    confusion_recompute_parser = confusion_subparsers.add_parser("aggregate-recompute")
    confusion_recompute_parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )

    review_overrides_parser = subparsers.add_parser("review-overrides")
    review_overrides_subparsers = review_overrides_parser.add_subparsers(
        dest="review_overrides_command", required=True
    )

    review_overrides_init_parser = review_overrides_subparsers.add_parser("init")
    review_overrides_init_parser.add_argument("--snapshot-id", required=True)
    review_overrides_init_parser.add_argument("--path", type=Path)
    review_overrides_init_parser.add_argument("--force", action="store_true")

    review_overrides_list_parser = review_overrides_subparsers.add_parser("list")
    review_overrides_list_parser.add_argument("--snapshot-id", required=True)
    review_overrides_list_parser.add_argument("--path", type=Path)

    review_overrides_upsert_parser = review_overrides_subparsers.add_parser("upsert")
    review_overrides_upsert_parser.add_argument("--snapshot-id", required=True)
    review_overrides_upsert_parser.add_argument("--path", type=Path)
    review_overrides_upsert_parser.add_argument("--media-asset-id", required=True)
    review_overrides_upsert_parser.add_argument(
        "--status",
        required=True,
        choices=["accepted", "review_required", "rejected"],
    )
    review_overrides_upsert_parser.add_argument("--note", required=True)

    governance_review_parser = subparsers.add_parser("governance-review")
    governance_review_subparsers = governance_review_parser.add_subparsers(
        dest="governance_review_command", required=True
    )
    governance_review_resolve_parser = governance_review_subparsers.add_parser("resolve")
    governance_review_resolve_parser.add_argument(
        "--governance-review-item-id",
        required=True,
    )
    governance_review_resolve_parser.add_argument(
        "--note",
        required=True,
        help="mandatory operator closure note",
    )
    governance_review_resolve_parser.add_argument("--resolved-by", default="operator")
    governance_review_resolve_parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    governance_review_resolve_parser.add_argument("--snapshot-id", type=str)

    migrate_parser = subparsers.add_parser("migrate")
    migrate_parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )

    args = parser.parse_args()
    if args.command == "run-pipeline":
        gemini_api_key = None
        if args.qualifier_mode == "gemini":
            gemini_api_key = os.environ.get(args.gemini_api_key_env)
            if not gemini_api_key:
                raise SystemExit(f"Missing Gemini API key in env var {args.gemini_api_key_env}")
        result = run_pipeline(
            source_mode=args.source_mode,
            fixture_path=args.fixture_path,
            snapshot_id=args.snapshot_id,
            snapshot_root=args.snapshot_root,
            database_url=args.database_url,
            normalized_snapshot_path=args.normalized_path,
            qualification_snapshot_path=args.qualified_path,
            export_path=args.export_path,
            review_overrides_path=args.review_overrides_path,
            apply_review_overrides=args.apply_review_overrides,
            qualifier_mode=args.qualifier_mode,
            uncertain_policy=args.uncertain_policy,
            gemini_api_key=gemini_api_key,
            gemini_model=args.gemini_model,
            allow_schema_reset=args.allow_schema_reset,
        )
        print(
            "Pipeline complete | "
            f"run_id={result.run_id} | "
            f"qualified={result.qualified_resource_count} | "
            f"exportable={result.exportable_resource_count} | "
            f"review={result.review_queue_count}"
        )
        return

    if args.command == "fetch-inat-snapshot":
        snapshot_id = args.snapshot_id or default_snapshot_id()
        result = fetch_inat_snapshot(
            snapshot_id=snapshot_id,
            snapshot_root=args.snapshot_root,
            pilot_taxa_path=args.pilot_taxa_path,
            max_observations_per_taxon=args.max_observations_per_taxon,
            timeout_seconds=args.timeout_seconds,
            bbox=_normalize_bbox_arg(args.bbox) if args.bbox else None,
            place_id=args.place_id,
            country_code=args.country_code,
            observed_from=args.observed_from,
            observed_to=args.observed_to,
        )
        print(
            "Snapshot fetched | "
            f"snapshot_id={result.snapshot_id} | "
            f"harvested={result.harvested_observation_count} | "
            f"downloaded={result.downloaded_image_count} | "
            f"path={result.snapshot_dir}"
        )
        return

    if args.command == "qualify-inat-snapshot":
        gemini_api_key = os.environ.get(args.gemini_api_key_env)
        if not gemini_api_key:
            raise SystemExit(f"Missing Gemini API key in env var {args.gemini_api_key_env}")
        result = qualify_inat_snapshot(
            snapshot_id=args.snapshot_id,
            snapshot_root=args.snapshot_root,
            gemini_api_key=gemini_api_key,
            gemini_model=args.gemini_model,
            request_interval_seconds=args.request_interval_seconds,
            max_retries=args.max_retries,
            initial_backoff_seconds=args.initial_backoff_seconds,
            max_backoff_seconds=args.max_backoff_seconds,
        )
        print(
            "Snapshot AI qualification complete | "
            f"snapshot_id={result.snapshot_id} | "
            f"processed={result.processed_media_count} | "
            f"sent_to_gemini={result.images_sent_to_gemini_count} | "
            f"ok={result.ai_valid_output_count} | "
            f"insufficient_resolution={result.insufficient_resolution_count} | "
            f"pre_ai_rejected={result.pre_ai_rejection_count} | "
            f"path={result.ai_outputs_path}"
        )
        return

    if args.command == "pack":
        services = build_storage_services(args.database_url)
        services.database.initialize()
        pack_store = services.pack_store
        if args.pack_command == "create":
            parameters = _build_pack_revision_parameters_from_args(args)
            payload = pack_store.create_pack(
                pack_id=args.pack_id,
                parameters=parameters,
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return
        if args.pack_command == "revise":
            parameters = _build_pack_revision_parameters_from_args(args)
            payload = pack_store.revise_pack(
                pack_id=args.pack_id,
                parameters=parameters,
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return
        if args.pack_command == "diagnose":
            payload = pack_store.diagnose_pack(
                pack_id=args.pack_id,
                revision=args.revision,
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return
        if args.pack_command == "compile":
            if args.contract_version == "v2":
                payload = pack_store.compile_pack_v2(
                    pack_id=args.pack_id,
                    revision=args.revision,
                    question_count=args.question_count,
                )
            else:
                payload = pack_store.compile_pack(
                    pack_id=args.pack_id,
                    revision=args.revision,
                    question_count=args.question_count,
                )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return
        if args.pack_command == "materialize":
            if args.contract_version == "v2":
                payload = pack_store.materialize_pack_v2(
                    pack_id=args.pack_id,
                    revision=args.revision,
                    question_count=args.question_count,
                    purpose=args.purpose,
                    ttl_hours=args.ttl_hours,
                )
            else:
                payload = pack_store.materialize_pack(
                    pack_id=args.pack_id,
                    revision=args.revision,
                    question_count=args.question_count,
                    purpose=args.purpose,
                    ttl_hours=args.ttl_hours,
                )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return
        if args.pack_command == "enrich-enqueue":
            payload = services.enrichment_store.enqueue_enrichment_for_pack(
                pack_id=args.pack_id,
                revision=args.revision,
                question_count=args.question_count,
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return
        if args.pack_command == "enrich-execute":
            payload = services.enrichment_store.record_enrichment_execution(
                enrichment_request_id=args.enrichment_request_id,
                execution_status=args.execution_status,
                execution_context={
                    "operator": "pack enrich-execute",
                    "trigger_recompile": bool(args.trigger_recompile),
                },
                error_info=args.error_info,
                trigger_recompile=args.trigger_recompile,
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return
        raise SystemExit(f"Unsupported pack command: {args.pack_command}")

    if args.command == "confusion":
        services = build_storage_services(args.database_url)
        services.database.initialize()
        if args.confusion_command == "ingest-batch":
            events = _load_confusion_events_from_file(args.events_file)
            payload = services.confusion_store.ingest_confusion_batch(
                batch_id=args.batch_id,
                events=events,
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return
        if args.confusion_command == "aggregate-recompute":
            payload = services.confusion_store.recompute_confusion_aggregates_global()
            print(json.dumps(payload, indent=2, sort_keys=True))
            return
        raise SystemExit(f"Unsupported confusion command: {args.confusion_command}")

    if args.command == "migrate":
        services = build_storage_services(args.database_url)
        redacted_database_url = redact_database_url(args.database_url)
        version_before = services.database.current_schema_version()
        applied_versions = services.database.migrate_to_latest()
        version_after = services.database.current_schema_version()
        if version_before == 0 and version_after > 0:
            print(
                "Database initialized at latest schema | "
                f"database_url={redacted_database_url} | "
                f"schema_version={version_after}"
            )
            return
        if applied_versions:
            print(
                "Database migrated | "
                f"database_url={redacted_database_url} | "
                f"applied={','.join(str(item) for item in applied_versions)}"
            )
        else:
            print(
                "Database already up to date | "
                f"database_url={redacted_database_url} | "
                f"schema_version={services.database.current_schema_version()}"
            )
        return

    if args.command == "review-overrides":
        override_path = resolve_review_overrides_path(args.snapshot_id, args.path)
        if args.review_overrides_command == "init":
            try:
                override_file = initialize_review_override_file(
                    override_path,
                    snapshot_id=args.snapshot_id,
                    force=args.force,
                )
            except FileExistsError as exc:
                raise SystemExit(str(exc)) from exc
            print(
                "Review overrides initialized | "
                f"snapshot_id={override_file.snapshot_id} | "
                f"count={len(override_file.overrides)} | "
                f"path={override_path}"
            )
            return

        if args.review_overrides_command == "list":
            override_file = load_review_override_file(override_path, snapshot_id=args.snapshot_id)
            if override_file is None:
                print(
                    "Review overrides | "
                    f"snapshot_id={args.snapshot_id} | "
                    f"count=0 | path={override_path} | file=missing"
                )
                return
            print(
                "Review overrides | "
                f"snapshot_id={override_file.snapshot_id} | "
                f"count={len(override_file.overrides)} | "
                f"path={override_path}"
            )
            for item in override_file.overrides:
                print(
                    f"- media_asset_id={item.media_asset_id} | "
                    f"status={item.qualification_status} | note={item.note}"
                )
            return

        try:
            override_file = upsert_review_override(
                override_path,
                snapshot_id=args.snapshot_id,
                media_asset_id=args.media_asset_id,
                qualification_status=args.status,
                note=args.note,
            )
        except FileNotFoundError as exc:
            raise SystemExit(f"{exc}. Run `review-overrides init` first.") from exc
        print(
            "Review override upserted | "
            f"snapshot_id={override_file.snapshot_id} | "
            f"count={len(override_file.overrides)} | "
            f"path={override_path}"
        )
        return

    if args.command == "governance-review":
        if args.governance_review_command != "resolve":
            raise SystemExit(
                f"Unsupported governance-review command: {args.governance_review_command}"
            )
        services = build_storage_services(args.database_url)
        services.database.initialize()
        try:
            updated = services.repository.resolve_canonical_governance_review_item(
                governance_review_item_id=args.governance_review_item_id,
                resolved_note=args.note,
                resolved_by=args.resolved_by,
            )
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        print(
            "Canonical governance review item resolved | "
            f"id={updated['governance_review_item_id']} | "
            f"run_id={updated['run_id']} | "
            f"reason_code={updated['reason_code']} | "
            f"resolved_by={updated['resolved_by']} | "
            f"resolved_at={updated['resolved_at']}"
        )
        return

    services = build_storage_services(args.database_url)
    services.database.initialize()
    repository = services.repository
    pack_store = services.pack_store
    if args.view == "summary":
        print(render_summary(repository))
    elif args.view == "review-queue":
        print(
            render_review_queue(
                repository,
                review_reason_code=args.review_reason_code,
                stage_name=args.stage_name,
                review_status=args.review_status,
                canonical_taxon_id=args.canonical_taxon_id,
                priority=args.priority,
            )
        )
    elif args.view == "canonical-governance-review-queue":
        print(
            render_canonical_governance_review_queue(
                repository,
                run_id=args.run_id,
                reason_code=args.review_reason_code,
                review_status=args.review_status,
            )
        )
    elif args.view == "canonical-state-events":
        print(
            render_canonical_state_events(
                repository,
                run_id=args.run_id,
                limit=args.limit,
            )
        )
    elif args.view == "canonical-change-events":
        print(
            render_canonical_change_events(
                repository,
                run_id=args.run_id,
                limit=args.limit,
            )
        )
    elif args.view == "canonical-governance-events":
        print(
            render_canonical_governance_events(
                repository,
                run_id=args.run_id,
                limit=args.limit,
            )
        )
    elif args.view == "snapshot-health":
        if not args.snapshot_id:
            raise SystemExit("--snapshot-id is required for snapshot-health")
        print(
            render_snapshot_health(
                repository,
                snapshot_id=args.snapshot_id,
                snapshot_root=args.snapshot_root,
            )
        )
    elif args.view == "run-metrics":
        print(render_run_metrics(repository, run_id=args.run_id))
    elif args.view == "playable-corpus":
        payload = repository.fetch_playable_corpus_payload(
            canonical_taxon_id=args.canonical_taxon_id,
            country_code=args.country_code,
            difficulty_level=args.difficulty_level,
            media_role=args.media_role,
            learning_suitability=args.learning_suitability,
            confusion_relevance=args.confusion_relevance,
            observed_from=_parse_optional_iso8601_datetime(args.observed_from),
            observed_to=_parse_optional_iso8601_datetime(args.observed_to),
            bbox=_parse_bbox(args.bbox),
            point_radius=_parse_point_radius(args.point_radius),
            limit=args.limit,
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif args.view == "playable-invalidations":
        print(
            render_playable_invalidations(
                repository,
                invalidated_run_id=args.run_id,
                invalidation_reason=args.invalidation_reason,
                lifecycle_status=args.lifecycle_status or "invalidated",
                limit=args.limit,
            )
        )
    elif args.view == "pack-specs":
        payload = pack_store.fetch_pack_specs(pack_id=args.pack_id, limit=args.limit)
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif args.view == "pack-revisions":
        if not args.pack_id:
            raise SystemExit("--pack-id is required for pack-revisions")
        payload = pack_store.fetch_pack_revisions(
            pack_id=args.pack_id,
            revision=args.revision,
            limit=args.limit,
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif args.view == "pack-diagnostics":
        payload = pack_store.fetch_pack_diagnostics(
            pack_id=args.pack_id,
            revision=args.revision,
            limit=args.limit,
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif args.view == "compiled-pack-builds":
        payload = pack_store.fetch_compiled_pack_builds(
            pack_id=args.pack_id,
            revision=args.revision,
            limit=args.limit,
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif args.view == "pack-materializations":
        payload = pack_store.fetch_pack_materializations(
            pack_id=args.pack_id,
            revision=args.revision,
            purpose=args.purpose,
            limit=args.limit,
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
    elif args.view == "enrichment-requests":
        print(
            render_enrichment_requests(
                repository,
                request_status=args.enrichment_status,
                pack_id=args.pack_id,
                revision=args.revision,
                limit=args.limit,
            )
        )
    elif args.view == "enrichment-executions":
        print(
            render_enrichment_executions(
                repository,
                enrichment_request_id=args.enrichment_request_id,
                limit=args.limit,
            )
        )
    elif args.view == "enrichment-metrics":
        print(render_enrichment_metrics(repository))
    elif args.view == "confusion-events":
        print(
            render_confusion_events(
                repository,
                batch_id=args.batch_id,
                limit=args.limit,
            )
        )
    elif args.view == "confusion-aggregates-global":
        print(
            render_confusion_aggregates_global(
                repository,
                taxon_confused_for_id=args.taxon_confused_for_id,
                limit=args.limit,
            )
        )
    elif args.view == "confusion-metrics":
        print(render_confusion_metrics(repository))
    else:
        print(render_exportables(repository))


def _load_confusion_events_from_file(path: Path) -> list[dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"Cannot read events file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in events file: {path}") from exc

    if not isinstance(payload, list):
        raise SystemExit("--events-file must be a JSON list of confusion event objects")

    validated: list[dict[str, object]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise SystemExit(f"Invalid event at index {index}: expected JSON object")
        try:
            event = ConfusionEventInput(**item)
        except Exception as exc:  # pragma: no cover - CLI validation failure path.
            raise SystemExit(f"Invalid event at index {index}: {exc}") from exc
        validated.append(event.model_dump(mode="json"))
    return validated


def _parse_optional_iso8601_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    candidate = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:  # pragma: no cover - CLI parse failure path.
        raise SystemExit(f"Invalid ISO-8601 datetime value: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _parse_bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    parts = [item.strip() for item in value.split(",")]
    if len(parts) != 4:
        raise SystemExit("--bbox expects min_longitude,min_latitude,max_longitude,max_latitude")
    try:
        min_longitude, min_latitude, max_longitude, max_latitude = (float(item) for item in parts)
    except ValueError as exc:  # pragma: no cover - CLI parse failure path.
        raise SystemExit("--bbox values must be numeric") from exc
    return min_longitude, min_latitude, max_longitude, max_latitude


def _normalize_bbox_arg(value: str) -> str:
    parsed = _parse_bbox(value)
    if parsed is None:  # pragma: no cover - defensive branch for optional parser reuse.
        raise SystemExit("--bbox expects min_longitude,min_latitude,max_longitude,max_latitude")
    min_longitude, min_latitude, max_longitude, max_latitude = parsed
    return ",".join(
        str(component)
        for component in (min_longitude, min_latitude, max_longitude, max_latitude)
    )


def _parse_point_radius(value: str | None) -> tuple[float, float, float] | None:
    if value is None:
        return None
    parts = [item.strip() for item in value.split(",")]
    if len(parts) != 3:
        raise SystemExit("--point-radius expects longitude,latitude,radius_meters")
    try:
        longitude, latitude, radius_meters = (float(item) for item in parts)
    except ValueError as exc:  # pragma: no cover - CLI parse failure path.
        raise SystemExit("--point-radius values must be numeric") from exc
    return longitude, latitude, radius_meters


def _build_pack_revision_parameters_from_args(args: argparse.Namespace) -> PackRevisionParameters:
    bbox = _parse_bbox(args.bbox)
    point_radius = _parse_point_radius(args.point_radius)
    location_point = None
    location_radius_meters = None
    if point_radius is not None:
        longitude, latitude, location_radius_meters = point_radius
        location_point = {
            "longitude": longitude,
            "latitude": latitude,
        }
    return PackRevisionParameters(
        canonical_taxon_ids=list(args.canonical_taxon_ids),
        difficulty_policy=args.difficulty_policy,
        country_code=args.country_code,
        location_bbox=(
            {
                "min_longitude": bbox[0],
                "min_latitude": bbox[1],
                "max_longitude": bbox[2],
                "max_latitude": bbox[3],
            }
            if bbox is not None
            else None
        ),
        location_point=location_point,
        location_radius_meters=location_radius_meters,
        observed_from=_parse_optional_iso8601_datetime(args.observed_from),
        observed_to=_parse_optional_iso8601_datetime(args.observed_to),
        owner_id=args.owner_id,
        org_id=args.org_id,
        visibility=args.visibility,
        intended_use=args.intended_use,
    )


def run_pipeline_entrypoint() -> None:
    sys.argv.insert(1, "run-pipeline")
    main()


def inspect_entrypoint() -> None:
    sys.argv.insert(1, "inspect")
    main()


def fetch_inat_snapshot_entrypoint() -> None:
    sys.argv.insert(1, "fetch-inat-snapshot")
    main()


def qualify_inat_snapshot_entrypoint() -> None:
    sys.argv.insert(1, "qualify-inat-snapshot")
    main()


def review_overrides_entrypoint() -> None:
    sys.argv.insert(1, "review-overrides")
    main()


def governance_review_entrypoint() -> None:
    sys.argv.insert(1, "governance-review")
    main()


def migrate_entrypoint() -> None:
    sys.argv.insert(1, "migrate")
    main()


def pack_entrypoint() -> None:
    sys.argv.insert(1, "pack")
    main()


def confusion_entrypoint() -> None:
    sys.argv.insert(1, "confusion")
    main()


if __name__ == "__main__":
    main()
