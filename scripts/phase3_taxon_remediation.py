from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _bootstrap_src_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    src_path = str(src)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def main() -> None:
    load_dotenv(dotenv_path=Path(".env"))
    _bootstrap_src_path()
    from database_core.adapters import DEFAULT_INAT_SNAPSHOT_ROOT, DEFAULT_PILOT_TAXA_PATH
    from database_core.pipeline.runner import DEFAULT_DATABASE_URL
    from database_core.ops.phase3_taxon_remediation import run_phase3_taxon_remediation

    parser = argparse.ArgumentParser(prog="phase3-taxon-remediation")
    parser.add_argument("--pack-id", required=True)
    parser.add_argument("--revision", type=int)
    parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_INAT_SNAPSHOT_ROOT)
    parser.add_argument("--pilot-taxa-path", type=Path, default=DEFAULT_PILOT_TAXA_PATH)
    parser.add_argument("--gemini-api-key-env", default="GEMINI_API_KEY")
    parser.add_argument("--output-path", type=Path)
    parser.add_argument("--max-passes", type=int, default=3)
    parser.add_argument("--max-observations-per-taxon", type=int, default=15)
    parser.add_argument("--harvest-order-by", type=str)
    parser.add_argument("--harvest-order", choices=["asc", "desc"])
    parser.add_argument("--harvest-observed-from", type=str)
    parser.add_argument("--harvest-observed-to", type=str)
    parser.add_argument("--harvest-bbox", type=str)
    args = parser.parse_args()

    gemini_api_key = os.environ.get(args.gemini_api_key_env)
    if not gemini_api_key:
        raise SystemExit(f"Missing Gemini API key in env var {args.gemini_api_key_env}")

    summary = run_phase3_taxon_remediation(
        pack_id=args.pack_id,
        revision=args.revision,
        database_url=args.database_url,
        snapshot_root=args.snapshot_root,
        pilot_taxa_path=args.pilot_taxa_path,
        gemini_api_key=gemini_api_key,
        summary_output_path=args.output_path,
        max_passes=args.max_passes,
        max_observations_per_taxon=args.max_observations_per_taxon,
        harvest_order_by=args.harvest_order_by,
        harvest_order=args.harvest_order,
        harvest_observed_from=args.harvest_observed_from,
        harvest_observed_to=args.harvest_observed_to,
        harvest_bbox=args.harvest_bbox,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
