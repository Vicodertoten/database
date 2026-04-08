from __future__ import annotations

import argparse
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
from database_core.inspect.summary import (
    render_exportables,
    render_review_queue,
    render_snapshot_health,
    render_summary,
)
from database_core.pipeline.runner import (
    DEFAULT_DATABASES_DIR,
    DEFAULT_DB_PATH,
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
from database_core.storage.sqlite import SQLiteRepository


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
    pipeline_parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    pipeline_parser.add_argument("--normalized-path", type=Path, default=DEFAULT_NORMALIZED_PATH)
    pipeline_parser.add_argument("--qualified-path", type=Path, default=DEFAULT_QUALIFIED_PATH)
    pipeline_parser.add_argument("--export-path", type=Path, default=DEFAULT_EXPORT_PATH)
    pipeline_parser.add_argument("--reset-db", action="store_true")
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
        "view", choices=["summary", "review-queue", "exportables", "snapshot-health"]
    )
    inspect_parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    inspect_parser.add_argument("--snapshot-id", type=str)
    inspect_parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_INAT_SNAPSHOT_ROOT)
    inspect_parser.add_argument("--review-reason-code", type=str)
    inspect_parser.add_argument("--stage-name", type=str)
    inspect_parser.add_argument("--review-status", type=str)
    inspect_parser.add_argument("--canonical-taxon-id", type=str)
    inspect_parser.add_argument("--priority", type=str)

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
            db_path=args.db_path,
            normalized_snapshot_path=args.normalized_path,
            qualification_snapshot_path=args.qualified_path,
            export_path=args.export_path,
            review_overrides_path=args.review_overrides_path,
            apply_review_overrides=args.apply_review_overrides,
            qualifier_mode=args.qualifier_mode,
            uncertain_policy=args.uncertain_policy,
            gemini_api_key=gemini_api_key,
            gemini_model=args.gemini_model,
            reset_db=args.reset_db,
            allow_schema_reset=args.allow_schema_reset,
        )
        print(
            "Pipeline complete | "
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
            f"path={result.ai_outputs_path}"
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

    repository = SQLiteRepository(_resolve_inspect_db_path(args.db_path, args.snapshot_id))
    repository.initialize()
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
    else:
        print(render_exportables(repository))


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


def _resolve_inspect_db_path(db_path: Path, snapshot_id: str | None) -> Path:
    if snapshot_id and db_path == DEFAULT_DB_PATH:
        return DEFAULT_DATABASES_DIR / f"{snapshot_id}.sqlite"
    return db_path


if __name__ == "__main__":
    main()
