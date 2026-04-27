from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def _default_evidence_month_dir() -> Path:
    return Path("docs/archive/evidence") / datetime.now(UTC).strftime("%Y-%m")

DEFAULT_SNAPSHOT_ID = "inaturalist-birds-v2-20260421T210221Z"
DEFAULT_EXPORT_PATH = Path(f"data/exports/{DEFAULT_SNAPSHOT_ID}.json")
DEFAULT_OUTPUT_PATH = _default_evidence_month_dir() / "owner_benchmark_summary.v1.json"
DEFAULT_SMOKE_REPORT_DIR = Path("docs/archive/evidence/smoke-reports")
DEFAULT_PACK_ID = "pack:phase0:birds:europe:mixed:v1"
DEFAULT_RUNS = 3
DEFAULT_ATTEMPTS_PER_RUN = 10
DEFAULT_QUESTION_COUNT = 20


@dataclass(frozen=True)
class RunResult:
    run_index: int
    attempts: int
    successes: int
    failures: int
    compile_success_ratio_segment: float
    distractor_diversity_segment: float
    unique_directed_pairs: int
    total_distractor_slots: int
    overall_pass: bool
    smoke_report_path: str


def _bootstrap_src_path() -> None:
    src_path = str(SRC)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def _load_segment_canonical_taxon_ids(export_path: Path) -> list[str]:
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    resources = payload.get("qualified_resources")
    if not isinstance(resources, list):
        raise SystemExit(f"Invalid export file (qualified_resources missing): {export_path}")

    taxon_counts: dict[str, int] = {}
    for item in resources:
        if not isinstance(item, dict):
            continue
        if not bool(item.get("export_eligible")):
            continue
        taxon_id = str(item.get("canonical_taxon_id") or "").strip()
        if not taxon_id.startswith("taxon:birds:"):
            continue
        taxon_counts[taxon_id] = taxon_counts.get(taxon_id, 0) + 1

    unique = [taxon_id for taxon_id, count in taxon_counts.items() if count >= 2]
    if not unique:
        raise SystemExit("No exportable birds canonical_taxon_ids found for Phase 0 segment")
    return unique


def _ensure_pack_for_phase0(
    *,
    database_url: str,
    pack_id: str,
    canonical_taxon_ids: list[str],
    difficulty_policy: str,
) -> dict[str, Any]:
    _bootstrap_src_path()
    from database_core.domain.models import PackRevisionParameters
    from database_core.storage.services import build_storage_services

    services = build_storage_services(database_url)
    services.database.initialize()
    pack_store = services.pack_store

    parameters = PackRevisionParameters(
        canonical_taxon_ids=canonical_taxon_ids,
        difficulty_policy=difficulty_policy,
        country_code=None,
        location_bbox=None,
        location_point=None,
        location_radius_meters=None,
        observed_from=None,
        observed_to=None,
        owner_id="phase0",
        org_id=None,
        visibility="private",
        intended_use="benchmark_phase0",
    )

    existing_specs = pack_store.fetch_pack_specs(pack_id=pack_id, limit=1)
    if existing_specs:
        payload = pack_store.revise_pack(pack_id=pack_id, parameters=parameters)
        payload["pack_action"] = "revise"
        return payload

    payload = pack_store.create_pack(pack_id=pack_id, parameters=parameters)
    payload["pack_action"] = "create"
    return payload


def _compute_quantities_from_build(
    build_payload: dict[str, Any],
) -> tuple[set[tuple[str, str]], int]:
    pairs: set[tuple[str, str]] = set()
    total_slots = 0
    questions = build_payload.get("questions")
    if not isinstance(questions, list):
        return pairs, total_slots

    for question in questions:
        if not isinstance(question, dict):
            continue
        target = str(question.get("target_canonical_taxon_id") or "").strip()
        distractors = question.get("distractor_canonical_taxon_ids")
        if not target or not isinstance(distractors, list):
            continue
        for distractor in distractors:
            distractor_id = str(distractor or "").strip()
            if not distractor_id:
                continue
            total_slots += 1
            pairs.add((target, distractor_id))
    return pairs, total_slots


def _run_owner_benchmark(
    *,
    database_url: str,
    snapshot_id: str,
    pack_id: str,
    runs: int,
    attempts_per_run: int,
    question_count: int,
) -> list[RunResult]:
    _bootstrap_src_path()
    from database_core.ops import generate_smoke_report
    from database_core.storage.services import build_storage_services

    services = build_storage_services(database_url)
    services.database.initialize()
    pack_store = services.pack_store

    output_dir = DEFAULT_SMOKE_REPORT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[RunResult] = []
    for run_index in range(1, runs + 1):
        successes = 0
        failures = 0
        unique_pairs: set[tuple[str, str]] = set()
        total_slots = 0

        for _ in range(attempts_per_run):
            try:
                payload = pack_store.compile_pack(
                    pack_id=pack_id,
                    revision=None,
                    question_count=question_count,
                )
                successes += 1
                run_pairs, run_slots = _compute_quantities_from_build(payload)
                unique_pairs.update(run_pairs)
                total_slots += run_slots
            except Exception:
                failures += 1

        compile_ratio = (successes / attempts_per_run) if attempts_per_run > 0 else 0.0
        distractor_diversity = (len(unique_pairs) / total_slots) if total_slots > 0 else 0.0

        report = generate_smoke_report(
            services.pipeline_store,
            snapshot_id=snapshot_id,
            database_url=database_url,
        )
        smoke_report_path = output_dir / f"{snapshot_id}.smoke_report.v1.json"
        smoke_report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        results.append(
            RunResult(
                run_index=run_index,
                attempts=attempts_per_run,
                successes=successes,
                failures=failures,
                compile_success_ratio_segment=compile_ratio,
                distractor_diversity_segment=distractor_diversity,
                unique_directed_pairs=len(unique_pairs),
                total_distractor_slots=total_slots,
                overall_pass=bool(report.get("overall_pass")),
                smoke_report_path=str(smoke_report_path),
            )
        )

    return results


def main() -> int:
    load_dotenv(dotenv_path=ROOT / ".env")
    _bootstrap_src_path()
    from database_core.security import redact_database_url

    parser = argparse.ArgumentParser(description="Phase 0 owner benchmark runner (database)")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", "postgresql://localhost:5432/postgres"),
    )
    parser.add_argument("--snapshot-id", default=DEFAULT_SNAPSHOT_ID)
    parser.add_argument("--export-path", type=Path, default=DEFAULT_EXPORT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--pack-id", default=DEFAULT_PACK_ID)
    parser.add_argument(
        "--difficulty-policy",
        choices=["easy", "balanced", "hard", "mixed"],
        default="mixed",
    )
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--attempts-per-run", type=int, default=DEFAULT_ATTEMPTS_PER_RUN)
    parser.add_argument("--question-count", type=int, default=DEFAULT_QUESTION_COUNT)
    args = parser.parse_args()

    if args.difficulty_policy != "mixed":
        raise SystemExit("Phase 0 benchmark is locked to difficulty_policy=mixed")
    if args.runs < 1:
        raise SystemExit("--runs must be >= 1")
    if args.attempts_per_run < 1:
        raise SystemExit("--attempts-per-run must be >= 1")

    canonical_taxon_ids = _load_segment_canonical_taxon_ids(args.export_path)
    pack_payload = _ensure_pack_for_phase0(
        database_url=args.database_url,
        pack_id=args.pack_id,
        canonical_taxon_ids=canonical_taxon_ids,
        difficulty_policy=args.difficulty_policy,
    )

    run_results = _run_owner_benchmark(
        database_url=args.database_url,
        snapshot_id=args.snapshot_id,
        pack_id=args.pack_id,
        runs=args.runs,
        attempts_per_run=args.attempts_per_run,
        question_count=args.question_count,
    )

    summary = {
        "schema_version": "phase0.owner.benchmark.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "snapshot_id": args.snapshot_id,
        "segment": {
            "taxon_group": "birds-only",
            "media_type": "image-only",
            "zone": "Europe",
            "difficulty_policy": args.difficulty_policy,
            "season_filter": None,
        },
        "comparability": {
            "same_snapshot_id": True,
            "same_difficulty_policy": True,
            "same_question_count": True,
            "same_attempts_per_run": True,
        },
        "database_url": redact_database_url(args.database_url),
        "pack": {
            "pack_id": args.pack_id,
            "pack_action": pack_payload.get("pack_action"),
            "latest_revision": pack_payload.get("latest_revision"),
            "canonical_taxon_count": len(canonical_taxon_ids),
        },
        "runs": [
            {
                "run_index": item.run_index,
                "attempts": item.attempts,
                "successes": item.successes,
                "failures": item.failures,
                "compile_success_ratio_segment": item.compile_success_ratio_segment,
                "distractor_diversity_segment": item.distractor_diversity_segment,
                "unique_directed_pairs": item.unique_directed_pairs,
                "total_distractor_slots": item.total_distractor_slots,
                "overall_pass": item.overall_pass,
                "smoke_report_path": item.smoke_report_path,
            }
            for item in run_results
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
