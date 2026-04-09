from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _bootstrap_src_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    src_path = str(src)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def _default_output_path(*, snapshot_id: str | None) -> Path:
    identifier = snapshot_id or "postgres"
    return Path("docs/smoke_reports") / f"{identifier}.smoke_report.v1.json"


def main() -> None:
    _bootstrap_src_path()
    from database_core.ops import generate_smoke_report
    from database_core.pipeline.runner import DEFAULT_DATABASE_URL
    from database_core.storage.postgres import PostgresRepository

    parser = argparse.ArgumentParser(prog="generate-smoke-report")
    parser.add_argument("--snapshot-id", type=str)
    parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    parser.add_argument("--output-path", type=Path)
    parser.add_argument(
        "--fail-on-kpi-breach",
        action="store_true",
        help="exit with code 1 when at least one KPI target is not met",
    )
    args = parser.parse_args()

    repository = PostgresRepository(args.database_url)
    repository.initialize()
    report = generate_smoke_report(
        repository,
        snapshot_id=args.snapshot_id,
        database_url=args.database_url,
    )

    output_path = args.output_path or _default_output_path(snapshot_id=args.snapshot_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "Smoke report generated | "
        f"path={output_path} | "
        f"overall_pass={report['overall_pass']}"
    )
    if args.fail_on_kpi_breach and not bool(report["overall_pass"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
