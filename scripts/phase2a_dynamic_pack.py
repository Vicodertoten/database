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

from database_core.ops.phase2a_dynamic_pack import (  # noqa: E402
    PHASE2A_DEFAULT_QUESTION_COUNT,
    audit_phase2a,
    build_pack_pool,
    build_session_fixtures,
)


def _default_run_id() -> str:
    return f"phase2a-be-fr-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"


def _default_output_dir(run_id: str) -> Path:
    return Path("docs/archive/evidence/dynamic-pack-phase-2a") / run_id


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 2A dynamic pack contract tooling.")
    parser.add_argument("--run-id", default=_default_run_id())
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("PHASE1_DATABASE_URL", ""),
        help="Phase 2A database URL. Must point to the isolated Phase 1 schema.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_pool = subparsers.add_parser("build-pool")
    build_pool.add_argument("--pool-id", required=True)
    build_pool.add_argument("--source-run-id", required=True)

    sessions = subparsers.add_parser("build-session-fixtures")
    sessions.add_argument("--pool-id", required=True)
    sessions.add_argument("--question-count", type=int, default=PHASE2A_DEFAULT_QUESTION_COUNT)
    sessions.add_argument("--seed", required=True)
    sessions.add_argument("--locale", action="append", dest="locales", required=True)

    audit = subparsers.add_parser("audit")
    audit.add_argument("--pool-id", required=True)
    audit.add_argument("--question-count", type=int, default=PHASE2A_DEFAULT_QUESTION_COUNT)

    return parser


def main() -> None:
    load_dotenv(dotenv_path=Path(".env"))
    parser = _build_parser()
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("PHASE1_DATABASE_URL or --database-url is required")
    output_dir = args.output_dir or _default_output_dir(args.run_id)

    if args.command == "build-pool":
        payload = build_pack_pool(
            database_url=args.database_url,
            pool_id=args.pool_id,
            source_run_id=args.source_run_id,
            output_dir=output_dir,
        )
        print(
            "Phase 2A pack pool generated"
            f" | output_dir={output_dir}"
            f" | pool_id={payload['pool_id']}"
            f" | items={payload['metrics']['item_count']}"
            f" | taxa={payload['metrics']['taxon_count']}"
        )
        return

    if args.command == "build-session-fixtures":
        sessions = build_session_fixtures(
            database_url=args.database_url,
            pool_id=args.pool_id,
            question_count=args.question_count,
            seed=args.seed,
            locales=args.locales,
            output_dir=output_dir,
        )
        print(
            "Phase 2A session fixtures generated"
            f" | output_dir={output_dir}"
            f" | pool_id={args.pool_id}"
            f" | sessions={len(sessions)}"
            f" | question_count={args.question_count}"
        )
        return

    if args.command == "audit":
        report = audit_phase2a(
            database_url=args.database_url,
            pool_id=args.pool_id,
            question_count=args.question_count,
            output_dir=output_dir,
        )
        print(
            "Phase 2A audit generated"
            f" | output_dir={output_dir}"
            f" | pool_id={args.pool_id}"
            f" | status={report['status']}"
        )
        return

    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
