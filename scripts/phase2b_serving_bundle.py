#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

load_dotenv(ROOT / ".env")

from database_core.ops.phase2b_serving_bundle import (  # noqa: E402
    DEFAULT_SERVING_BUNDLE_FILENAME,
    DEFAULT_SERVING_BUNDLE_OUTPUT_DIR,
    export_serving_bundle_v1,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase 2B serving_bundle.v1 tooling.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser("export")
    export_parser.add_argument("--pool-id", required=True)
    export_parser.add_argument(
        "--database-url",
        default=os.environ.get("PHASE1_DATABASE_URL"),
    )
    export_parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_SERVING_BUNDLE_OUTPUT_DIR,
    )
    export_parser.add_argument(
        "--output-filename",
        default=DEFAULT_SERVING_BUNDLE_FILENAME,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "export":
        if not args.database_url:
            raise SystemExit("--database-url or PHASE1_DATABASE_URL is required")
        result = export_serving_bundle_v1(
            database_url=args.database_url,
            pool_id=args.pool_id,
            output_dir=args.output_dir,
            output_filename=args.output_filename,
        )
        print(
            "Phase 2B serving_bundle.v1 exported "
            f"status={result['audit']['status']} "
            f"pool_id={args.pool_id} "
            f"output={args.output_dir / args.output_filename}"
        )
        return
    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
