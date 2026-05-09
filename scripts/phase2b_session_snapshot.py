#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from database_core.ops.phase2b_session_snapshot import (  # noqa: E402
    PHASE2B_QUESTION_COUNT,
    audit_session_snapshots_v2,
    build_session_fixtures_v2,
)


def _default_run_id() -> str:
    return f"session-snapshot-v2-palier-a-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"


def _default_output_dir() -> Path:
    return Path("docs/archive/evidence/dynamic-pack-phase-2b/session-snapshot-v2-palier-a")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 2B session_snapshot.v2 tooling.")
    parser.add_argument("--run-id", default=_default_run_id())
    parser.add_argument("--output-dir", type=Path, default=_default_output_dir())
    parser.add_argument(
        "--database-url",
        default=os.environ.get("PHASE1_DATABASE_URL", ""),
        help="Database URL for the corrected Phase 1/2B clone.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build-fixtures")
    build.add_argument("--pool-id", required=True)
    build.add_argument("--question-count", type=int, default=PHASE2B_QUESTION_COUNT)

    audit = subparsers.add_parser("audit")
    audit.add_argument("--pool-id", required=True)

    return parser


def main() -> None:
    load_dotenv(dotenv_path=Path(".env"))
    parser = _build_parser()
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("PHASE1_DATABASE_URL or --database-url is required")

    if args.command == "build-fixtures":
        sessions = build_session_fixtures_v2(
            database_url=args.database_url,
            pool_id=args.pool_id,
            output_dir=args.output_dir,
            question_count=args.question_count,
        )
        print(
            "Phase 2B session_snapshot.v2 fixtures generated"
            f" | output_dir={args.output_dir}"
            f" | pool_id={args.pool_id}"
            f" | sessions={len(sessions)}"
            f" | question_count={args.question_count}"
        )
        return

    if args.command == "audit":
        report = audit_session_snapshots_v2(
            database_url=args.database_url,
            pool_id=args.pool_id,
            output_dir=args.output_dir,
        )
        print(
            "Phase 2B session_snapshot.v2 audit generated"
            f" | output_dir={args.output_dir}"
            f" | pool_id={args.pool_id}"
            f" | status={report['status']}"
        )
        return

    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
