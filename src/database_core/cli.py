from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from database_core.adapters import (
    DEFAULT_INAT_SNAPSHOT_ROOT,
    DEFAULT_PILOT_TAXA_PATH,
    fetch_inat_snapshot,
)
from database_core.inspect.summary import (
    render_exportables,
    render_review_queue,
    render_snapshot_health,
    render_summary,
)
from database_core.pipeline.runner import (
    DEFAULT_DB_PATH,
    DEFAULT_EXPORT_PATH,
    DEFAULT_FIXTURE_PATH,
    DEFAULT_NORMALIZED_PATH,
    DEFAULT_QUALIFIED_PATH,
    run_pipeline,
)
from database_core.storage.sqlite import SQLiteRepository


def main() -> None:
    parser = argparse.ArgumentParser(prog="database-core")
    subparsers = parser.add_subparsers(dest="command", required=True)

    pipeline_parser = subparsers.add_parser("run-pipeline")
    pipeline_parser.add_argument("--fixture-path", type=Path, default=DEFAULT_FIXTURE_PATH)
    pipeline_parser.add_argument("--source-mode", choices=["fixture", "inat_snapshot"], default="fixture")
    pipeline_parser.add_argument("--snapshot-id", type=str)
    pipeline_parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_INAT_SNAPSHOT_ROOT)
    pipeline_parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    pipeline_parser.add_argument("--normalized-path", type=Path, default=DEFAULT_NORMALIZED_PATH)
    pipeline_parser.add_argument("--qualified-path", type=Path, default=DEFAULT_QUALIFIED_PATH)
    pipeline_parser.add_argument("--export-path", type=Path, default=DEFAULT_EXPORT_PATH)
    pipeline_parser.add_argument("--qualifier-mode", choices=["fixture", "rules", "gemini"])
    pipeline_parser.add_argument("--gemini-api-key-env", default="GEMINI_API_KEY")
    pipeline_parser.add_argument("--gemini-model", default="gemini-2.5-flash")

    fetch_parser = subparsers.add_parser("fetch-inat-snapshot")
    fetch_parser.add_argument("--snapshot-id", type=str)
    fetch_parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_INAT_SNAPSHOT_ROOT)
    fetch_parser.add_argument("--pilot-taxa-path", type=Path, default=DEFAULT_PILOT_TAXA_PATH)
    fetch_parser.add_argument("--max-observations-per-taxon", type=int, default=5)
    fetch_parser.add_argument("--timeout-seconds", type=int, default=30)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("view", choices=["summary", "review-queue", "exportables", "snapshot-health"])
    inspect_parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    inspect_parser.add_argument("--snapshot-id", type=str)
    inspect_parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_INAT_SNAPSHOT_ROOT)

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
            qualifier_mode=args.qualifier_mode,
            gemini_api_key=gemini_api_key,
            gemini_model=args.gemini_model,
        )
        print(
            "Pipeline complete | "
            f"qualified={result.qualified_resource_count} | "
            f"exportable={result.exportable_resource_count} | "
            f"review={result.review_queue_count}"
        )
        return

    if args.command == "fetch-inat-snapshot":
        snapshot_id = args.snapshot_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
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

    repository = SQLiteRepository(args.db_path)
    repository.initialize()
    if args.view == "summary":
        print(render_summary(repository))
    elif args.view == "review-queue":
        print(render_review_queue(repository))
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


if __name__ == "__main__":
    main()
