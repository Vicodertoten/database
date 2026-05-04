#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _bootstrap_src_path() -> None:
    root = Path(__file__).resolve().parents[1]
    root_str = str(root)
    src = str(root / "src")
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    if src not in sys.path:
        sys.path.insert(0, src)


_bootstrap_src_path()

DEFAULT_MAX_MEDIA_COUNT = 400
DEFAULT_MAX_MEDIA_PER_TAXON = 10
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
DEFAULT_GEMINI_CONCURRENCY = 4
DEFAULT_GEMINI_API_KEY_ENV = "GEMINI_API_KEY"


def prepare_pmp_policy_broader_run(
    *,
    snapshot_id: str,
    output_snapshot_id: str,
    max_media_count: int = DEFAULT_MAX_MEDIA_COUNT,
    max_media_per_taxon: int = DEFAULT_MAX_MEDIA_PER_TAXON,
    snapshot_root: Path | None = None,
    gemini_model: str = DEFAULT_GEMINI_MODEL,
    gemini_concurrency: int = DEFAULT_GEMINI_CONCURRENCY,
    gemini_api_key_env: str = DEFAULT_GEMINI_API_KEY_ENV,
) -> tuple[dict[str, object], str]:
    if snapshot_root is None:
        from database_core.adapters.inaturalist_snapshot import DEFAULT_INAT_SNAPSHOT_ROOT

        snapshot_root = DEFAULT_INAT_SNAPSHOT_ROOT

    from scripts.build_controlled_inat_snapshot_subset import build_controlled_inat_snapshot_subset

    audit = build_controlled_inat_snapshot_subset(
        snapshot_id=snapshot_id,
        output_snapshot_id=output_snapshot_id,
        max_media_count=max_media_count,
        max_media_per_taxon=max_media_per_taxon,
        snapshot_root=snapshot_root,
    )

    python_executable = Path(sys.executable)
    command = (
        f"{python_executable} -m database_core.cli qualify-inat-snapshot "
        f"--snapshot-id {output_snapshot_id} "
        f"--ai-review-contract-version pedagogical_media_profile_v1 "
        f"--gemini-model {gemini_model} "
        f"--gemini-concurrency {gemini_concurrency} "
        f"--gemini-api-key-env {gemini_api_key_env}"
    )
    return audit, command


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build a broader deterministic iNaturalist subset for PMP policy audit "
            "and print the qualifying Gemini command."
        )
    )
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--output-snapshot-id", required=True)
    parser.add_argument("--max-media-count", type=int, default=DEFAULT_MAX_MEDIA_COUNT)
    parser.add_argument(
        "--max-media-per-taxon",
        type=int,
        default=DEFAULT_MAX_MEDIA_PER_TAXON,
    )
    parser.add_argument(
        "--snapshot-root",
        type=Path,
        default=None,
        help="Optional snapshot root; defaults to the repository inaturalist snapshot root.",
    )
    parser.add_argument(
        "--gemini-model",
        default=DEFAULT_GEMINI_MODEL,
    )
    parser.add_argument(
        "--gemini-concurrency",
        type=int,
        default=DEFAULT_GEMINI_CONCURRENCY,
    )
    parser.add_argument(
        "--gemini-api-key-env",
        default=DEFAULT_GEMINI_API_KEY_ENV,
    )
    args = parser.parse_args()

    audit, command = prepare_pmp_policy_broader_run(
        snapshot_id=args.snapshot_id,
        output_snapshot_id=args.output_snapshot_id,
        max_media_count=args.max_media_count,
        max_media_per_taxon=args.max_media_per_taxon,
        snapshot_root=args.snapshot_root,
        gemini_model=args.gemini_model,
        gemini_concurrency=args.gemini_concurrency,
        gemini_api_key_env=args.gemini_api_key_env,
    )

    print(
        json.dumps(
            {
                "source_snapshot_id": audit["source_snapshot_id"],
                "output_snapshot_id": audit["output_snapshot_id"],
                "selected_media_count": audit["selected_media_count"],
                "selected_taxon_count": audit["selected_taxon_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    print("\nBroader snapshot built successfully.")
    print("Run the following command from the repository root to execute the live PMP critique:")
    print(command)


if __name__ == "__main__":
    main()
