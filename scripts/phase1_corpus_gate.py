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

from database_core.adapters.inaturalist_snapshot import DEFAULT_INAT_SNAPSHOT_ROOT  # noqa: E402
from database_core.ops.phase1_corpus_gate import (  # noqa: E402
    PHASE1_BUDGET_CAP_EUR,
    PHASE1_ESTIMATED_COST_PER_IMAGE_EUR,
    PHASE1_MAX_CANDIDATES_PER_SPECIES,
    PHASE1_TARGET_TAXA_PATH,
    audit_phase1_corpus_gate,
    build_pre_ai_selection,
    build_preflight_report,
    merge_phase1_ai_outputs,
)


def _default_run_id() -> str:
    return f"phase1-be-fr-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"


def _default_output_dir(run_id: str) -> Path:
    return Path("docs/archive/evidence/dynamic-pack-phase-1") / run_id


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 1 BE+FR dynamic pack corpus gate tooling.")
    parser.add_argument("--run-id", default=_default_run_id())
    parser.add_argument("--output-dir", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument(
        "--phase1-database-url",
        default=os.environ.get("PHASE1_DATABASE_URL", ""),
    )
    preflight.add_argument(
        "--current-database-url",
        default=os.environ.get("DATABASE_URL", ""),
    )
    preflight.add_argument("--target-taxa-path", type=Path, default=PHASE1_TARGET_TAXA_PATH)

    select = subparsers.add_parser("select-pre-ai")
    select.add_argument("--snapshot-id", action="append", dest="snapshot_ids", required=True)
    select.add_argument("--output-snapshot-id", required=True)
    select.add_argument(
        "--final-input-snapshot-id",
        help=(
            "Optional full BE+FR corpus snapshot to preserve already-known media. "
            "--output-snapshot-id remains the Gemini worklist."
        ),
    )
    select.add_argument("--snapshot-root", type=Path, default=DEFAULT_INAT_SNAPSHOT_ROOT)
    select.add_argument(
        "--current-database-url",
        default=os.environ.get("DATABASE_URL", ""),
    )
    select.add_argument(
        "--max-candidates-per-species",
        type=int,
        default=PHASE1_MAX_CANDIDATES_PER_SPECIES,
    )
    select.add_argument("--budget-cap-eur", type=float, default=PHASE1_BUDGET_CAP_EUR)
    select.add_argument(
        "--estimated-cost-per-image-eur",
        type=float,
        default=PHASE1_ESTIMATED_COST_PER_IMAGE_EUR,
    )

    merge = subparsers.add_parser("merge-ai-outputs")
    merge.add_argument("--final-input-snapshot-id", required=True)
    merge.add_argument("--gemini-worklist-snapshot-id", required=True)
    merge.add_argument("--snapshot-root", type=Path, default=DEFAULT_INAT_SNAPSHOT_ROOT)
    merge.add_argument(
        "--current-database-url",
        default=os.environ.get("DATABASE_URL", ""),
    )

    audit = subparsers.add_parser("audit")
    audit.add_argument(
        "--database-url",
        default=os.environ.get("PHASE1_DATABASE_URL", ""),
    )
    audit.add_argument("--target-taxa-path", type=Path, default=PHASE1_TARGET_TAXA_PATH)
    audit.add_argument("--question-generation-success-rate", type=float)

    return parser


def main() -> None:
    load_dotenv(dotenv_path=Path(".env"))
    parser = _build_parser()
    args = parser.parse_args()
    output_dir = args.output_dir or _default_output_dir(args.run_id)

    if args.command == "preflight":
        if not args.phase1_database_url:
            raise SystemExit("PHASE1_DATABASE_URL or --phase1-database-url is required")
        report = build_preflight_report(
            phase1_database_url=args.phase1_database_url,
            current_database_url=args.current_database_url or None,
            target_taxa_path=args.target_taxa_path,
            output_dir=output_dir,
        )
        print(
            "Phase 1 preflight generated"
            f" | output_dir={output_dir}"
            f" | target_taxa={report['checks']['target_taxa_count']}"
        )
        return

    if args.command == "select-pre-ai":
        result = build_pre_ai_selection(
            snapshot_ids=args.snapshot_ids,
            output_snapshot_id=args.output_snapshot_id,
            output_dir=output_dir,
            final_input_snapshot_id=args.final_input_snapshot_id,
            snapshot_root=args.snapshot_root,
            current_database_url=args.current_database_url or None,
            max_candidates_per_species=args.max_candidates_per_species,
            budget_cap_eur=args.budget_cap_eur,
            estimated_cost_per_image_eur=args.estimated_cost_per_image_eur,
        )
        print(
            "Phase 1 pre-AI selection generated"
            f" | output_dir={output_dir}"
            f" | selected={len(result.selected_candidates)}"
            f" | within_budget={result.report['budget']['within_budget']}"
            f" | final_input={args.final_input_snapshot_id or 'not-written'}"
        )
        return

    if args.command == "merge-ai-outputs":
        if not args.current_database_url:
            raise SystemExit("DATABASE_URL or --current-database-url is required")
        report = merge_phase1_ai_outputs(
            final_input_snapshot_id=args.final_input_snapshot_id,
            gemini_worklist_snapshot_id=args.gemini_worklist_snapshot_id,
            current_database_url=args.current_database_url,
            output_dir=output_dir,
            snapshot_root=args.snapshot_root,
        )
        print(
            "Phase 1 AI outputs merged"
            f" | output_dir={output_dir}"
            f" | merged={report['merged_ai_outputs_count']}"
            f" | missing={report['missing_ai_outputs_count']}"
        )
        return

    if args.command == "audit":
        if not args.database_url:
            raise SystemExit("PHASE1_DATABASE_URL or --database-url is required")
        report = audit_phase1_corpus_gate(
            database_url=args.database_url,
            output_dir=output_dir,
            target_taxa_path=args.target_taxa_path,
            question_generation_success_rate=args.question_generation_success_rate,
        )
        print(
            "Phase 1 corpus gate generated"
            f" | output_dir={output_dir}"
            f" | status={report['gate']['status']}"
        )
        return

    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
