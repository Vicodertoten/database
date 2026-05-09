#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from database_core.ops.phase2b_audit import (  # noqa: E402
    DEFAULT_LOCALIZED_NAME_PLAN,
    DEFAULT_NAME_REPAIR_JSON,
    DEFAULT_NAME_REPAIR_MD,
    DEFAULT_REFERENCED_ONLY_JSON,
    DEFAULT_REFERENCED_ONLY_MD,
    run_name_repair_audit,
    run_referenced_only_audit,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 2B non-mutating audit tooling.")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("PHASE1_DATABASE_URL", ""),
        help="Phase 2B audit database URL. Must point to the isolated Phase 1/2A schema.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    name_repair = subparsers.add_parser("name-repair")
    name_repair.add_argument("--pool-id", required=True)
    name_repair.add_argument(
        "--localized-name-plan",
        type=Path,
        default=DEFAULT_LOCALIZED_NAME_PLAN,
        help="Optional localized-name evidence plan used for name source comparison.",
    )
    name_repair.add_argument("--output-json", type=Path, default=DEFAULT_NAME_REPAIR_JSON)
    name_repair.add_argument("--output-md", type=Path, default=DEFAULT_NAME_REPAIR_MD)

    referenced = subparsers.add_parser("referenced-only")
    referenced.add_argument("--output-json", type=Path, default=DEFAULT_REFERENCED_ONLY_JSON)
    referenced.add_argument("--output-md", type=Path, default=DEFAULT_REFERENCED_ONLY_MD)

    return parser


def main() -> None:
    load_dotenv(dotenv_path=Path(".env"))
    parser = _build_parser()
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("PHASE1_DATABASE_URL or --database-url is required")

    if args.command == "name-repair":
        report = run_name_repair_audit(
            database_url=args.database_url,
            pool_id=args.pool_id,
            localized_name_plan_path=args.localized_name_plan,
            output_json=args.output_json,
            output_md=args.output_md,
        )
        print(
            "Phase 2B name repair audit generated"
            f" | decision={report['decision']}"
            f" | pool_id={args.pool_id}"
            f" | output_json={args.output_json}"
            f" | output_md={args.output_md}"
        )
        return

    if args.command == "referenced-only":
        report = run_referenced_only_audit(
            database_url=args.database_url,
            output_json=args.output_json,
            output_md=args.output_md,
        )
        print(
            "Phase 2B referenced-only audit generated"
            f" | decision={report['decision']}"
            f" | output_json={args.output_json}"
            f" | output_md={args.output_md}"
        )
        return

    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
