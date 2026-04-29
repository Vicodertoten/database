from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv


def _bootstrap_src_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    src_path = str(src)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def main() -> int:
    load_dotenv(dotenv_path=Path(".env"))
    _bootstrap_src_path()

    from database_core.adapters import DEFAULT_INAT_SNAPSHOT_ROOT
    from database_core.ops.phase2_playable_corpus import (
        PHASE2_DEFAULT_MAX_ATTEMPTS,
        PHASE2_DEFAULT_OUTPUT_DIR,
        PHASE2_DEFAULT_PILOT_TAXA_PATH,
        PHASE2_DEFAULT_QUESTION_ATTEMPTS,
        PHASE2_TARGET_COUNTRY_CODE,
        Phase2Thresholds,
        run_phase2_playable_corpus,
    )

    parser = argparse.ArgumentParser(
        prog="phase2-playable-corpus-v0.1",
        description=(
            "Run Phase 2 end-to-end: corpus audit, rebuild from iNaturalist snapshots, "
            "and gate validation for playable internal corpus."
        ),
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default="postgresql://127.0.0.1:5432/database_phase2_v01",
    )
    parser.add_argument("--gemini-api-key-env", type=str, default="GEMINI_API_KEY")
    parser.add_argument("--pilot-taxa-path", type=Path, default=PHASE2_DEFAULT_PILOT_TAXA_PATH)
    parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_INAT_SNAPSHOT_ROOT)
    parser.add_argument("--output-dir", type=Path, default=PHASE2_DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--target-country-code",
        type=str,
        default=PHASE2_TARGET_COUNTRY_CODE,
        help="Two-letter country code (default BE) or ANY to disable country filtering.",
    )
    parser.add_argument("--target-species-count", type=int, default=50)
    parser.add_argument("--min-images-per-species", type=int, default=10)
    parser.add_argument("--max-images-per-species", type=int, default=30)
    parser.add_argument("--max-attempts", type=int, default=PHASE2_DEFAULT_MAX_ATTEMPTS)
    parser.add_argument(
        "--question-attempts",
        type=int,
        default=PHASE2_DEFAULT_QUESTION_ATTEMPTS,
    )
    parser.add_argument("--question-count", type=int, default=20)
    parser.add_argument(
        "--skip-rebuild",
        action="store_true",
        help="Audit current corpus only without running harvest/qualification/pipeline.",
    )
    args = parser.parse_args()

    if args.target_species_count < 1:
        raise SystemExit("--target-species-count must be >= 1")
    if args.min_images_per_species < 1:
        raise SystemExit("--min-images-per-species must be >= 1")
    if args.max_images_per_species < args.min_images_per_species:
        raise SystemExit("--max-images-per-species must be >= --min-images-per-species")
    if args.max_attempts < 1:
        raise SystemExit("--max-attempts must be >= 1")
    if args.question_attempts < 1:
        raise SystemExit("--question-attempts must be >= 1")
    if args.question_count < 1:
        raise SystemExit("--question-count must be >= 1")

    gemini_api_key = os.environ.get(args.gemini_api_key_env)
    if not args.skip_rebuild and not gemini_api_key:
        raise SystemExit(f"Missing Gemini API key in env var {args.gemini_api_key_env}")

    normalized_country_code = (args.target_country_code or "").strip().upper()
    target_country_code = (
        None
        if not normalized_country_code or normalized_country_code == "ANY"
        else normalized_country_code
    )

    thresholds = Phase2Thresholds(
        target_country_code=target_country_code,
        target_species_count=args.target_species_count,
        min_images_per_species=args.min_images_per_species,
        max_images_per_species=args.max_images_per_species,
    )

    summary = run_phase2_playable_corpus(
        database_url=args.database_url,
        gemini_api_key=gemini_api_key or "",
        pilot_taxa_path=args.pilot_taxa_path,
        snapshot_root=args.snapshot_root,
        output_dir=args.output_dir,
        thresholds=thresholds,
        max_attempts=args.max_attempts,
        question_attempts=args.question_attempts,
        question_count=args.question_count,
        run_rebuild=not args.skip_rebuild,
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    if summary["final_analysis"]["gate"]["status"] != "GO":
        return 1
    print(
        "phase2 complete | "
        f"generated_at={datetime.now(UTC).isoformat()} | "
        f"report={summary.get('output_path')}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
