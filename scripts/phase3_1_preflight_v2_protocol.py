from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


def _bootstrap_src_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    src_path = str(src)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def _write_json(path: Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _missing_min_media(deficits: list[dict[str, Any]]) -> int:
    for item in deficits:
        if str(item.get("code", "")).strip() != "min_media_per_taxon":
            continue
        return int(item.get("missing", 0))
    return 0


def _is_pack_eligible(diagnostic: dict[str, Any]) -> bool:
    if bool(diagnostic.get("compilable")):
        return False
    deficits = list(diagnostic.get("deficits") or [])
    if _missing_min_media(deficits) <= 0:
        return False
    return len(list(diagnostic.get("blocking_taxa") or [])) > 0


def _map_scale_decision(scale_decision: str) -> str:
    if scale_decision == "CONTINUE_SCALE":
        return "GO"
    if scale_decision == "GO_WITH_GAPS":
        return "GO_WITH_GAPS"
    return "NO_GO"


def _probe_has_compile_signal(summary: dict[str, Any], *, gemini_cap: int) -> tuple[bool, str]:
    delta = summary.get("delta") or {}
    final = summary.get("final") or {}
    passes = list(summary.get("passes") or [])
    images_sent_to_gemini = sum(int(item.get("images_sent_to_gemini", 0)) for item in passes)
    if images_sent_to_gemini > gemini_cap:
        return False, "probe_cost_cap_exceeded"
    if not bool(final.get("overall_pass")):
        return False, "overall_pass_regressed"
    delta_insufficient = int(delta.get("insufficient_media_per_taxon_reason_count", 0))
    delta_ratio = float(delta.get("taxon_with_min2_media_ratio", 0.0))
    if delta_insufficient < 0 or delta_ratio > 0.0:
        return True, "probe_compile_signal_positive"
    return False, "probe_no_compile_signal"


def _load_scale_seeds_from_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    seeds = payload.get("taxon_seeds") or []
    normalized: list[dict[str, Any]] = []
    for item in seeds:
        normalized.append(
            {
                "canonical_taxon_id": item["canonical_taxon_id"],
                "accepted_scientific_name": item["accepted_scientific_name"],
                "canonical_rank": item.get("canonical_rank", "species"),
                "taxon_status": item.get("taxon_status", "active"),
                "authority_source": item.get("authority_source", "inaturalist"),
                "display_slug": item.get("display_slug"),
                "synonyms": item.get("synonyms", []),
                "common_names": item.get("common_names", []),
                "source_taxon_id": item["source_taxon_id"],
            }
        )
    return normalized


def _build_weak_seed_subset(
    *,
    scale_seeds: list[dict[str, Any]],
    blocking_taxa: list[dict[str, Any]],
    weak_taxa_count: int,
) -> list[dict[str, Any]]:
    by_id = {
        str(item.get("canonical_taxon_id", "")).strip(): item
        for item in scale_seeds
        if str(item.get("canonical_taxon_id", "")).strip()
    }
    selected: list[dict[str, Any]] = []
    for entry in blocking_taxa[:weak_taxa_count]:
        canonical_taxon_id = str(entry.get("canonical_taxon_id", "")).strip()
        seed = by_id.get(canonical_taxon_id)
        if seed is not None:
            selected.append(seed)
    return selected


def main() -> None:
    load_dotenv(dotenv_path=Path(".env"))
    _bootstrap_src_path()

    from database_core.ops.phase3_taxon_remediation import (
        run_phase3_preflight,
        run_phase3_taxon_remediation,
    )
    from database_core.storage.services import build_storage_services

    parser = argparse.ArgumentParser(prog="phase3.1-preflight-v2-protocol")
    parser.add_argument("--database-url", type=str, default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--gemini-api-key-env", type=str, default="GEMINI_API_KEY")
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=Path("data/raw/inaturalist/inaturalist-birds-v2-20260421T210221Z/manifest.json"),
    )
    parser.add_argument("--candidate-scan-limit", type=int, default=20)
    parser.add_argument("--max-preflight-attempts", type=int, default=3)
    parser.add_argument("--weak-taxa-count", type=int, default=15)
    parser.add_argument("--probe-gemini-cap", type=int, default=80)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/20_execution/phase3_1"))
    parser.add_argument("--base-pack-id", type=str, default=None)
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("DATABASE_URL is required")
    gemini_api_key = os.environ.get(args.gemini_api_key_env)
    if not gemini_api_key:
        raise SystemExit(f"Missing Gemini API key in env var {args.gemini_api_key_env}")

    now = datetime.now(UTC)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    scale_seeds = _load_scale_seeds_from_manifest(args.manifest_path)
    scale_seed_path = output_dir / f"pilot_taxa_scale80.{timestamp}.json"
    _write_json(scale_seed_path, scale_seeds)

    services = build_storage_services(args.database_url)
    services.database.initialize()
    diagnostics = services.pack_store.fetch_pack_diagnostics(
        limit=max(1, int(args.candidate_scan_limit))
    )

    selected_diagnostic: dict[str, Any] | None = None
    if args.base_pack_id:
        for item in diagnostics:
            if str(item.get("pack_id")) == args.base_pack_id and _is_pack_eligible(item):
                selected_diagnostic = item
                break
    if selected_diagnostic is None:
        for item in diagnostics:
            if _is_pack_eligible(item):
                selected_diagnostic = item
                break

    summary: dict[str, Any] = {
        "phase3_1_preflight_v2_version": "phase3.1.preflight.v2",
        "created_at": now.isoformat(),
        "config": {
            "candidate_scan_limit": int(args.candidate_scan_limit),
            "max_preflight_attempts": int(args.max_preflight_attempts),
            "weak_taxa_count": int(args.weak_taxa_count),
            "probe_gemini_cap": int(args.probe_gemini_cap),
        },
        "candidate_selection": {
            "base_pack_id_requested": args.base_pack_id,
            "selected_pack_id": None,
            "selected_revision": None,
            "selected_reason_code": None,
            "selected_missing_min_media": 0,
        },
        "preflight_attempts": [],
        "probe_attempts": [],
        "full_run": None,
        "decision": {
            "status": "NO_GO",
            "cause": "no_eligible_pack",
            "next_action": (
                "Select a candidate pack with `compilable=false` and missing "
                "`min_media_per_taxon`."
            ),
        },
    }

    if selected_diagnostic is None:
        verdict_path = output_dir / "phase3_1_preflight_v2_verdict.v1.json"
        _write_json(verdict_path, summary)
        summary["output_path"] = verdict_path.as_posix()
        print(json.dumps(summary, indent=2, sort_keys=True))
        return

    pack_id = str(selected_diagnostic["pack_id"])
    revision = int(selected_diagnostic["revision"])
    blocking_taxa = list(selected_diagnostic.get("blocking_taxa") or [])
    summary["candidate_selection"] = {
        "base_pack_id_requested": args.base_pack_id,
        "selected_pack_id": pack_id,
        "selected_revision": revision,
        "selected_reason_code": str(selected_diagnostic.get("reason_code", "")),
        "selected_missing_min_media": _missing_min_media(
            list(selected_diagnostic.get("deficits") or [])
        ),
    }
    safe_pack_id = pack_id.replace(":", "_")

    windows = [
        ("2010-01-01", "2022-12-31"),
        ("2000-01-01", "2015-12-31"),
        ("2023-01-01", "2026-12-31"),
    ]
    max_preflight_attempts = max(1, min(int(args.max_preflight_attempts), len(windows)))
    selected_preflight_artifact: Path | None = None
    selected_window: tuple[str, str] | None = None
    for idx in range(max_preflight_attempts):
        observed_from, observed_to = windows[idx]
        artifact_path = output_dir / f"{safe_pack_id}.{timestamp}.preflightA{idx + 1}.v1.json"
        attempt = run_phase3_preflight(
            pack_id=pack_id,
            revision=revision,
            database_url=args.database_url,
            pilot_taxa_path=scale_seed_path,
            summary_output_path=artifact_path,
            max_observations_per_taxon_probe=3,
            harvest_order_by="observed_on",
            harvest_order="asc",
            harvest_observed_from=observed_from,
            harvest_observed_to=observed_to,
            harvest_bbox="-11.0,34.0,32.0,71.0",
        )
        summary["preflight_attempts"].append(attempt)
        if bool(attempt.get("preflight_go", False)):
            selected_preflight_artifact = artifact_path
            selected_window = (observed_from, observed_to)
            break

    if selected_preflight_artifact is None or selected_window is None:
        summary["decision"] = {
            "status": "NO_GO",
            "cause": "preflight_no_signal",
            "next_action": "Retarget candidate pack selection before any Gemini-qualified run.",
        }
        verdict_path = output_dir / "phase3_1_preflight_v2_verdict.v1.json"
        _write_json(verdict_path, summary)
        summary["output_path"] = verdict_path.as_posix()
        print(json.dumps(summary, indent=2, sort_keys=True))
        return

    weak_seeds = _build_weak_seed_subset(
        scale_seeds=scale_seeds,
        blocking_taxa=blocking_taxa,
        weak_taxa_count=max(1, int(args.weak_taxa_count)),
    )
    weak_taxa_count = max(1, int(args.weak_taxa_count))
    weak_seed_path = output_dir / f"pilot_taxa_weak{weak_taxa_count}.{timestamp}.json"
    _write_json(weak_seed_path, weak_seeds)

    observed_from, observed_to = selected_window
    probe_observations = [3, 5]
    probe_passed = False
    for idx, max_obs in enumerate(probe_observations, start=1):
        probe_output_path = (
            output_dir / f"{safe_pack_id}.{timestamp}.probeB{idx}.phase3_remediation.v1.json"
        )
        probe_summary = run_phase3_taxon_remediation(
            pack_id=pack_id,
            revision=revision,
            database_url=args.database_url,
            pilot_taxa_path=weak_seed_path,
            gemini_api_key=gemini_api_key,
            summary_output_path=probe_output_path,
            max_passes=1,
            max_observations_per_taxon=max_obs,
            harvest_order_by="observed_on",
            harvest_order="asc",
            harvest_observed_from=observed_from,
            harvest_observed_to=observed_to,
            harvest_bbox="-11.0,34.0,32.0,71.0",
        )
        probe_go, probe_reason = _probe_has_compile_signal(
            probe_summary,
            gemini_cap=max(1, int(args.probe_gemini_cap)),
        )
        probe_payload = {
            "attempt": idx,
            "max_observations_per_taxon": max_obs,
            "probe_go": probe_go,
            "probe_reason": probe_reason,
            "summary_artifact": probe_output_path.as_posix(),
            "delta": probe_summary.get("delta"),
            "final_overall_pass": (probe_summary.get("final") or {}).get("overall_pass"),
            "images_sent_to_gemini": sum(
                int(item.get("images_sent_to_gemini", 0))
                for item in list(probe_summary.get("passes") or [])
            ),
        }
        summary["probe_attempts"].append(probe_payload)
        if probe_go:
            probe_passed = True
            break

    if not probe_passed:
        summary["decision"] = {
            "status": "NO_GO",
            "cause": "no_compile_signal_under_capped_probe",
            "next_action": (
                "Stop scale and retarget taxon/source strategy before any full "
                "3.1 campaign."
            ),
        }
        verdict_path = output_dir / "phase3_1_preflight_v2_verdict.v1.json"
        _write_json(verdict_path, summary)
        summary["output_path"] = verdict_path.as_posix()
        print(json.dumps(summary, indent=2, sort_keys=True))
        return

    full_cmd = [
        sys.executable,
        "scripts/phase3_1_complete_measurement.py",
        "--database-url",
        args.database_url,
        "--base-pack-id",
        pack_id,
        "--manifest-path",
        args.manifest_path.as_posix(),
        "--preflight-artifact-path",
        selected_preflight_artifact.as_posix(),
        "--harvest-order-by",
        "observed_on",
        "--harvest-order",
        "asc",
        "--harvest-observed-from",
        observed_from,
        "--harvest-observed-to",
        observed_to,
        "--harvest-bbox=-11.0,34.0,32.0,71.0",
    ]
    full_run = subprocess.run(full_cmd, check=True, capture_output=True, text=True)
    full_payload = json.loads(full_run.stdout)
    summary_json_path = Path(str(full_payload["summary_json"]))
    summary_json = json.loads(summary_json_path.read_text(encoding="utf-8"))
    scale_decision = str(full_payload.get("scale_decision", "STOP_RETARGET"))
    mapped_status = _map_scale_decision(scale_decision)

    summary["full_run"] = {
        "command": full_cmd,
        "scale_decision": scale_decision,
        "summary_json": str(full_payload.get("summary_json")),
        "summary_markdown": str(full_payload.get("summary_markdown")),
        "run_level_rows_count": len(list(summary_json.get("run_level_rows") or [])),
        "decision_status": str((summary_json.get("decision") or {}).get("status", "")),
    }
    summary["decision"] = {
        "status": mapped_status,
        "cause": scale_decision.lower(),
        "next_action": (
            "Continue targeted remediation on the same segment."
            if mapped_status in {"GO", "GO_WITH_GAPS"}
            else "Retarget candidate pack/taxa selection before new scale run."
        ),
    }

    verdict_path = output_dir / "phase3_1_preflight_v2_verdict.v1.json"
    _write_json(verdict_path, summary)
    summary["output_path"] = verdict_path.as_posix()
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
