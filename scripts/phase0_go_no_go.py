from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_OWNER_SUMMARY = Path("docs/20_execution/phase0/owner_benchmark_summary.v1.json")
DEFAULT_PROTOTYPE_BASELINE = Path(
    "/Users/ryelandt/Documents/Inaturamouche/docs/20_execution/phase0/prototype_baseline.v1.json"
)
DEFAULT_CONSUMER_SUMMARY = Path(
    "/Users/ryelandt/Documents/runtime-app/docs/20_execution/phase0/consumer_latency_summary.v1.json"
)
DEFAULT_OUTPUT = Path("docs/20_execution/phase0/go_no_go_decision.v1.json")
EXPECTED_FLOW_DEFINITION = "start_round_or_session -> get_question -> submit_answer"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0 Go/No-Go decision generator")
    parser.add_argument("--owner-summary", type=Path, default=DEFAULT_OWNER_SUMMARY)
    parser.add_argument("--prototype-baseline", type=Path, default=DEFAULT_PROTOTYPE_BASELINE)
    parser.add_argument("--consumer-summary", type=Path, default=DEFAULT_CONSUMER_SUMMARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    owner = _load_json(args.owner_summary)
    prototype = _load_json(args.prototype_baseline)
    consumer = _load_json(args.consumer_summary)

    owner_runs = owner.get("runs") or []
    consumer_runs = consumer.get("runs") or []

    checks = {
        "owner_run_count": len(owner_runs) >= 3,
        "consumer_run_count": len(consumer_runs) >= 3,
        "owner_compile_success_ratio_absolute": all(
            float(run.get("compile_success_ratio_segment", 0.0)) == 1.0 for run in owner_runs
        ),
        "owner_distractor_diversity_vs_prototype": all(
            float(run.get("distractor_diversity_segment", 0.0))
            >= float(prototype.get("distractor_diversity_segment", 0.0))
            for run in owner_runs
        ),
        "owner_smoke_overall_pass": all(bool(run.get("overall_pass")) for run in owner_runs),
        "consumer_latency_vs_prototype": all(
            float(run.get("latency_e2e_segment_p95", 0.0))
            <= float(prototype.get("latency_e2e_segment_p95", 0.0))
            for run in consumer_runs
        ),
        "consumer_sample_count_min_30": all(
            int(run.get("sample_count", 0)) >= 30 for run in consumer_runs
        ),
        "flow_definition_aligned": (
            str(prototype.get("flow_definition", "")) == EXPECTED_FLOW_DEFINITION
            and str(consumer.get("flow_definition", "")) == EXPECTED_FLOW_DEFINITION
        ),
        "difficulty_policy_mixed": (
            str(owner.get("segment", {}).get("difficulty_policy", "")) == "mixed"
            and str(prototype.get("segment", {}).get("difficulty_policy_database", "")) == "mixed"
            and str(consumer.get("segment", {}).get("difficulty_policy_database", "")) == "mixed"
        ),
    }

    go = all(checks.values())

    decision = {
        "schema_version": "phase0.go_no_go.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "inputs": {
            "owner_summary": str(args.owner_summary),
            "prototype_baseline": str(args.prototype_baseline),
            "consumer_summary": str(args.consumer_summary),
        },
        "checks": checks,
        "decision": "GO" if go else "NO_GO",
        "criteria": {
            "compile_success_ratio_segment": "== 1.0 on each owner run",
            "distractor_diversity_segment": ">= prototype baseline on each owner run",
            "latency_e2e_segment_p95": "<= prototype baseline on each consumer run",
            "overall_pass": "true on each owner run",
            "consumer_sample_count": ">= 30 measured flows on each consumer run",
            "flow_definition": EXPECTED_FLOW_DEFINITION,
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(decision, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
