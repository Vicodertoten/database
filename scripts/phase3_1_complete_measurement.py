from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
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


def _load_snapshot_seed_payloads(manifest_path: Path) -> list[dict[str, Any]]:
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


def _load_extension_seed_payloads(goldset_path: Path, extension_count: int) -> list[dict[str, Any]]:
    payload = json.loads(goldset_path.read_text(encoding="utf-8"))
    if len(payload) < extension_count:
        raise ValueError(
            "goldset taxa length "
            f"({len(payload)}) is smaller than extension_count "
            f"({extension_count})"
        )
    tail = payload[-extension_count:]
    seeds: list[dict[str, Any]] = []
    start_index = 81
    for index, item in enumerate(tail):
        canonical_taxon_id = f"taxon:birds:{start_index + index:06d}"
        seeds.append(
            {
                "canonical_taxon_id": canonical_taxon_id,
                "accepted_scientific_name": str(item["scientific_name"]).strip(),
                "canonical_rank": "species",
                "taxon_status": "active",
                "authority_source": "inaturalist",
                "display_slug": None,
                "synonyms": [],
                "common_names": [],
                "source_taxon_id": str(item["source_taxon_id"]).strip(),
            }
        )
    return seeds


def _write_json(path: Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_params_hash(params: dict[str, Any]) -> str:
    encoded = json.dumps(params, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _extract_run_record(
    *,
    run_type: str,
    run_label: str,
    summary: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any]:
    pass_payload = (summary.get("passes") or [{}])[0]
    idempotence = pass_payload.get("idempotence") or {}

    images_sent_to_gemini = int(pass_payload.get("images_sent_to_gemini", 0))
    pre_ai_rejection_count = int(pass_payload.get("pre_ai_rejection_count", 0))
    estimated_ai_cost_eur = round(images_sent_to_gemini * 0.0012, 6)
    exportable_resources = int(pass_payload.get("exportable_resources", 0))
    qualified_resources = int(pass_payload.get("qualified_resources", 0))
    cost_per_exportable = _safe_div(float(estimated_ai_cost_eur), float(exportable_resources))
    exportable_rate = _safe_div(float(exportable_resources), float(qualified_resources))
    accepted_new = int(idempotence.get("accepted_new_observation_media", 0))

    baseline = summary.get("baseline") or {}
    final = summary.get("final") or {}
    delta = summary.get("delta") or {}
    run_context = {
        "run_type": run_type,
        "run_label": run_label,
        "pack_id": summary.get("pack_id"),
        "run_id": (
            (
                (summary.get("enrichment") or {})
                .get("execution", {})
                .get("enrichment_execution_id")
            )
            or run_label
        ),
        "snapshot_id": pass_payload.get("snapshot_id"),
        "params_hash": _build_params_hash(params),
        "max_passes": params["max_passes"],
        "max_obs_per_taxon": params["max_observations_per_taxon"],
        "order_by": params["harvest_order_by"],
        "order": params["harvest_order"],
        "observed_from": params["harvest_observed_from"],
        "observed_to": params["harvest_observed_to"],
        "downloaded_images": int(pass_payload.get("downloaded_images", 0)),
        "accepted_new_observation_media": accepted_new,
        "ignored_existing_observation": int(idempotence.get("ignored_existing_observation", 0)),
        "ignored_existing_media": int(idempotence.get("ignored_existing_media", 0)),
        "images_sent_to_gemini": images_sent_to_gemini,
        "pre_ai_rejection_count": pre_ai_rejection_count,
        "estimated_ai_cost_eur": estimated_ai_cost_eur,
        "cost_per_exportable": (
            None if cost_per_exportable is None else round(cost_per_exportable, 6)
        ),
        "qualified_resources": qualified_resources,
        "exportable_resources": exportable_resources,
        "exportable_rate": None if exportable_rate is None else round(exportable_rate, 6),
        "reason_code_before": (baseline.get("diagnostic") or {}).get("reason_code"),
        "reason_code_after": (final.get("diagnostic") or {}).get("reason_code"),
        "insufficient_media_count_before": int(
            baseline.get("insufficient_media_per_taxon_reason_count", 0)
        ),
        "insufficient_media_count_after": int(
            final.get("insufficient_media_per_taxon_reason_count", 0)
        ),
        "delta_insufficient_media": int(delta.get("insufficient_media_per_taxon_reason_count", 0)),
        "ratio_before": float(baseline.get("taxon_with_min2_media_ratio", 0.0)),
        "ratio_after": float(final.get("taxon_with_min2_media_ratio", 0.0)),
        "delta_ratio": float(delta.get("taxon_with_min2_media_ratio", 0.0)),
        "overall_pass_before": bool(baseline.get("overall_pass")),
        "overall_pass_after": bool(final.get("overall_pass")),
        "artifact_path": summary.get("output_path"),
    }
    run_context["efficiency_accept_per_gemini"] = (
        None
        if images_sent_to_gemini == 0
        else round(accepted_new / images_sent_to_gemini, 6)
    )
    run_context["efficiency_exportable_per_gemini"] = (
        None
        if images_sent_to_gemini == 0
        else round(exportable_resources / images_sent_to_gemini, 6)
    )
    run_context["efficiency_compile_delta_per_gemini"] = (
        None
        if images_sent_to_gemini == 0
        else round(run_context["delta_insufficient_media"] / images_sent_to_gemini, 6)
    )
    return run_context


def _compute_scale_statistics(rows: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    metrics = [
        "accepted_new_observation_media",
        "images_sent_to_gemini",
        "pre_ai_rejection_count",
        "estimated_ai_cost_eur",
        "cost_per_exportable",
        "exportable_resources",
        "exportable_rate",
        "delta_insufficient_media",
        "delta_ratio",
        "efficiency_accept_per_gemini",
        "efficiency_exportable_per_gemini",
        "efficiency_compile_delta_per_gemini",
    ]
    stats: dict[str, dict[str, float | None]] = {}
    for metric in metrics:
        values = [
            float(row[metric])
            for row in rows
            if row.get(metric) is not None
        ]
        if not values:
            stats[metric] = {"median": None, "min": None, "max": None, "variance": None}
            continue
        stats[metric] = {
            "median": round(float(statistics.median(values)), 6),
            "min": round(float(min(values)), 6),
            "max": round(float(max(values)), 6),
            "variance": round(float(statistics.pvariance(values)), 6),
        }
    return stats


def _decide_scale_outcome(rows: list[dict[str, Any]]) -> dict[str, Any]:
    improving_insufficient = sum(1 for row in rows if row["delta_insufficient_media"] < 0)
    improving_ratio = sum(1 for row in rows if row["delta_ratio"] > 0)

    cost_rows = [row for row in rows if row["cost_per_exportable"] is not None]
    cost_stable_or_improving = True
    if len(cost_rows) >= 2:
        for idx in range(1, len(cost_rows)):
            prev = float(cost_rows[idx - 1]["cost_per_exportable"])
            curr = float(cost_rows[idx]["cost_per_exportable"])
            if curr > prev:
                cost_stable_or_improving = False
                break

    if improving_insufficient >= 2 and improving_ratio >= 2 and cost_stable_or_improving:
        status = "CONTINUE_SCALE"
    elif improving_ratio >= 1 and any(row["exportable_resources"] > 0 for row in rows):
        status = "GO_WITH_GAPS"
    else:
        status = "STOP_RETARGET"

    return {
        "status": status,
        "improving_insufficient_runs": improving_insufficient,
        "improving_ratio_runs": improving_ratio,
        "cost_stable_or_improving": cost_stable_or_improving,
    }


def _build_markdown_table(rows: list[dict[str, Any]]) -> str:
    header = (
        "| run | type | accepted_new | gemini | pre_ai_reject | est_cost_eur | "
        "exportable | delta_insufficient | delta_ratio | cost_per_exportable |\n"
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n"
    )
    lines: list[str] = []
    for row in rows:
        lines.append(
            (
                "| {run_label} | {run_type} | {accepted_new_observation_media} | "
                "{images_sent_to_gemini} | {pre_ai_rejection_count} | "
                "{estimated_ai_cost_eur} | {exportable_resources} | "
                "{delta_insufficient_media} | {delta_ratio} | "
                "{cost_per_exportable} |"
            ).format(**row)
        )
    return header + "\n".join(lines) + "\n"


def _load_preflight_artifact(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid preflight artifact payload at {path}")
    return payload


def _write_precheck_stop_summary(
    *,
    output_dir: Path,
    reason: str,
    preflight_artifact_path: Path,
    preflight_payload: dict[str, Any] | None,
) -> tuple[Path, Path]:
    summary_payload = {
        "phase3_1_measurement_version": "phase3.1.measurement.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "decision": {
            "status": "STOP_RETARGET_PRECHECK",
            "rules_evaluation": {
                "preflight_gate": "blocked",
                "reason": reason,
            },
            "what_works": (
                "Preflight gate prevents costly scale runs when compile-impact signal "
                "is absent."
            ),
            "what_does_not_work": "Scale run blocked by preflight hard stop.",
            "causal_hypothesis": (
                "Running full measurement now would likely spend Gemini budget "
                "without compile movement."
            ),
            "next_recommended_action": (
                "Run targeted retargeting and rerun preflight until "
                "`preflight_go=true`."
            ),
        },
        "preflight": {
            "artifact_path": preflight_artifact_path.as_posix(),
            "payload": preflight_payload,
        },
        "run_level_rows": [],
        "scale_statistics": {},
        "analysis_questions": {
            "q1_novelty_reduces_duplicate_churn": False,
            "q2_novelty_reduces_compile_deficits": False,
            "q3_marginal_ai_cost_acceptable_for_compile_gain": False,
            "q4_extension_marginal_value_better_than_scale": False,
        },
    }
    summary_json_path = output_dir / "phase3_1_summary.v1.json"
    _write_json(summary_json_path, summary_payload)

    markdown_path = output_dir / "phase3_1_summary.md"
    markdown_parts = [
        "# Phase 3.1 Summary",
        "",
        f"- created_at: `{summary_payload['created_at']}`",
        "- phase3 closure: `not_executed_precheck_block`",
        "- scale decision: `STOP_RETARGET_PRECHECK`",
        "",
        "## Decision Narrative",
        "",
        f"- ce qui marche: {summary_payload['decision']['what_works']}",
        f"- ce qui ne marche pas: {summary_payload['decision']['what_does_not_work']}",
        f"- hypothese causale: {summary_payload['decision']['causal_hypothesis']}",
        f"- action suivante recommandee: {summary_payload['decision']['next_recommended_action']}",
        "",
        f"- preflight reason: `{reason}`",
        f"- preflight artifact: `{preflight_artifact_path.as_posix()}`",
    ]
    markdown_path.write_text("\n".join(markdown_parts) + "\n", encoding="utf-8")
    return summary_json_path, markdown_path


def main() -> None:
    load_dotenv(dotenv_path=Path(".env"))
    _bootstrap_src_path()

    from database_core.ops.phase3_taxon_remediation import run_phase3_taxon_remediation
    from database_core.storage.services import build_storage_services

    parser = argparse.ArgumentParser(prog="phase3.1-complete-measurement")
    parser.add_argument(
        "--database-url",
        type=str,
        default=os.environ.get("DATABASE_URL"),
    )
    parser.add_argument("--gemini-api-key-env", default="GEMINI_API_KEY")
    parser.add_argument(
        "--base-pack-id",
        default="pack:pilot:birds-v2-nogeo:20260421T215543Z",
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=Path("data/raw/inaturalist/inaturalist-birds-v2-20260421T210221Z/manifest.json"),
    )
    parser.add_argument(
        "--goldset-path",
        type=Path,
        default=Path("data/fixtures/goldset_birds_v2_taxa.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs/20_execution/phase3_1"),
    )
    parser.add_argument(
        "--preflight-artifact-path",
        type=Path,
        default=Path("docs/20_execution/phase3_1/phase3_1_preflight.v1.json"),
    )
    parser.add_argument("--scale-runs", type=int, default=3)
    parser.add_argument("--max-passes", type=int, default=3)
    parser.add_argument("--max-observations-per-taxon", type=int, default=10)
    parser.add_argument("--harvest-order-by", type=str, default="observed_on")
    parser.add_argument("--harvest-order", choices=["asc", "desc"], default="asc")
    parser.add_argument("--harvest-observed-from", type=str, default="2010-01-01")
    parser.add_argument("--harvest-observed-to", type=str, default="2022-12-31")
    parser.add_argument("--harvest-bbox", type=str, default="-11.0,34.0,32.0,71.0")
    parser.add_argument("--extension-count", type=int, default=20)
    args = parser.parse_args()

    now = datetime.now(UTC)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    preflight_payload = _load_preflight_artifact(args.preflight_artifact_path)
    preflight_reason = None
    if preflight_payload is None:
        preflight_reason = "preflight_artifact_missing"
    elif not bool(preflight_payload.get("preflight_go", False)):
        preflight_reason = str(preflight_payload.get("preflight_reason", "preflight_no_go"))
    if preflight_reason is not None:
        summary_json_path, markdown_path = _write_precheck_stop_summary(
            output_dir=output_dir,
            reason=preflight_reason,
            preflight_artifact_path=args.preflight_artifact_path,
            preflight_payload=preflight_payload,
        )
        print(
            json.dumps(
                {
                    "summary_json": summary_json_path.as_posix(),
                    "summary_markdown": markdown_path.as_posix(),
                    "scale_decision": "STOP_RETARGET_PRECHECK",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if not args.database_url:
        raise SystemExit("DATABASE_URL is required")
    gemini_api_key = os.environ.get(args.gemini_api_key_env)
    if not gemini_api_key:
        raise SystemExit(f"Missing Gemini API key in env var {args.gemini_api_key_env}")

    scale_seed_path = output_dir / f"pilot_taxa_scale80.{timestamp}.json"
    extension_seed_path = output_dir / f"pilot_taxa_extension20.{timestamp}.json"

    scale_seeds = _load_snapshot_seed_payloads(args.manifest_path)
    _write_json(scale_seed_path, scale_seeds)
    extension_seeds = _load_extension_seed_payloads(args.goldset_path, args.extension_count)
    _write_json(extension_seed_path, extension_seeds)

    services = build_storage_services(args.database_url)
    services.database.initialize()

    extension_pack_id = f"pack:phase3_1:birds:europe:extension20:{timestamp}"
    extension_taxon_ids = [item["canonical_taxon_id"] for item in extension_seeds]
    services.pack_store.create_pack(
        pack_id=extension_pack_id,
        parameters={
            "canonical_taxon_ids": extension_taxon_ids,
            "difficulty_policy": "mixed",
            "country_code": None,
            "location_bbox": {
                "min_longitude": -11.0,
                "min_latitude": 34.0,
                "max_longitude": 32.0,
                "max_latitude": 71.0,
            },
            "location_point": None,
            "location_radius_meters": None,
            "observed_from": f"{args.harvest_observed_from}T00:00:00+00:00",
            "observed_to": f"{args.harvest_observed_to}T00:00:00+00:00",
            "owner_id": "phase3_1",
            "org_id": None,
            "visibility": "private",
            "intended_use": "phase3_1_extension",
        },
    )

    common_params = {
        "max_passes": args.max_passes,
        "max_observations_per_taxon": args.max_observations_per_taxon,
        "harvest_order_by": args.harvest_order_by,
        "harvest_order": args.harvest_order,
        "harvest_observed_from": args.harvest_observed_from,
        "harvest_observed_to": args.harvest_observed_to,
        "harvest_bbox": args.harvest_bbox,
    }

    run_records: list[dict[str, Any]] = []
    scale_artifacts: list[str] = []
    safe_base_pack_id = args.base_pack_id.replace(":", "_")

    for run_idx in range(1, args.scale_runs + 1):
        run_label = f"scale_run{run_idx}"
        artifact = (
            output_dir
            / f"{safe_base_pack_id}.{timestamp}.{run_label}.phase3_remediation.v1.json"
        )
        summary = run_phase3_taxon_remediation(
            pack_id=args.base_pack_id,
            revision=None,
            database_url=args.database_url,
            pilot_taxa_path=scale_seed_path,
            gemini_api_key=gemini_api_key,
            summary_output_path=artifact,
            **common_params,
        )
        run_records.append(
            _extract_run_record(
                run_type="scale",
                run_label=run_label,
                summary=summary,
                params={**common_params, "pack_id": args.base_pack_id},
            )
        )
        scale_artifacts.append(summary["output_path"])

    safe_extension_pack_id = extension_pack_id.replace(":", "_")
    extension_artifact = (
        output_dir
        / f"{safe_extension_pack_id}.{timestamp}.extension_run.phase3_remediation.v1.json"
    )
    extension_summary = run_phase3_taxon_remediation(
        pack_id=extension_pack_id,
        revision=None,
        database_url=args.database_url,
        pilot_taxa_path=extension_seed_path,
        gemini_api_key=gemini_api_key,
        summary_output_path=extension_artifact,
        **common_params,
    )
    run_records.append(
        _extract_run_record(
            run_type="extension",
            run_label="extension_run1",
            summary=extension_summary,
            params={**common_params, "pack_id": extension_pack_id},
        )
    )

    scale_rows = [row for row in run_records if row["run_type"] == "scale"]
    extension_rows = [row for row in run_records if row["run_type"] == "extension"]
    scale_stats = _compute_scale_statistics(scale_rows)
    scale_decision = _decide_scale_outcome(scale_rows)

    q1 = any(row["accepted_new_observation_media"] > 0 for row in scale_rows)
    q2 = any(row["delta_insufficient_media"] < 0 for row in scale_rows)
    q3 = any(
        row["delta_insufficient_media"] < 0 and row["images_sent_to_gemini"] > 0
        for row in scale_rows
    )
    q4 = False
    if extension_rows and scale_rows:
        extension_eff = extension_rows[0]["efficiency_exportable_per_gemini"]
        scale_eff_values = [
            row["efficiency_exportable_per_gemini"]
            for row in scale_rows
            if row["efficiency_exportable_per_gemini"] is not None
        ]
        if extension_eff is not None and scale_eff_values:
            q4 = extension_eff > statistics.mean(scale_eff_values)

    verdict_by_status = {
        "CONTINUE_SCALE": {
            "what_works": (
                "Scale remediation improves compile deficits and coverage under "
                "controlled cost."
            ),
            "what_does_not_work": "No major blocker observed in current parameter envelope.",
            "causal_hypothesis": (
                "Novelty acquisition is reaching taxa that directly unlock "
                "compile constraints."
            ),
            "next_recommended_action": (
                "Continue Phase 3 targeted remediation on the same segment "
                "until compile deficits plateau."
            ),
        },
        "GO_WITH_GAPS": {
            "what_works": (
                "Novelty and exportable growth are measurable under the Phase "
                "3.1 protocol."
            ),
            "what_does_not_work": "Compile-deficit reduction is partial or unstable run-over-run.",
            "causal_hypothesis": (
                "New media are added but not concentrated enough on blocking "
                "taxa to move compile gates decisively."
            ),
            "next_recommended_action": (
                "Retarget remediation selection toward top blocking taxa "
                "concentration before increasing volume."
            ),
        },
        "STOP_RETARGET": {
            "what_works": "Protocol and observability are stable and decision-ready.",
            "what_does_not_work": "Cost rises without meaningful compile-deficit improvement.",
            "causal_hypothesis": (
                "Current acquisition strategy maximizes volume novelty, not "
                "compile-relevant novelty."
            ),
            "next_recommended_action": (
                "Stop scale expansion and redesign targeting logic to maximize "
                "compile-impact per Gemini call."
            ),
        },
    }
    verdict = verdict_by_status[scale_decision["status"]]

    phase3_closure = {
        "phase3_status": "closed_go_with_gaps",
        "closure_reason": (
            "Remediation pipeline and novelty strategy validated; compile gate "
            "movement remains partial."
        ),
        "baseline_artifacts": [
            "docs/20_execution/phase3/pack_pilot_birds-v2-nogeo_20260421T215543Z.20260422T125207Z.phase3_remediation.v1.json",
            "docs/20_execution/phase3/pack_pilot_birds-v2-nogeo_20260421T215543Z.20260422T125858Z.phase3_remediation.v1.json",
        ],
    }

    summary_payload = {
        "phase3_1_measurement_version": "phase3.1.measurement.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "phase3_closure": phase3_closure,
        "scale_protocol": {
            "pack_id": args.base_pack_id,
            "runs": args.scale_runs,
            **common_params,
            "pilot_taxa_path": scale_seed_path.as_posix(),
            "artifacts": scale_artifacts,
        },
        "extension_protocol": {
            "pack_id": extension_pack_id,
            "taxon_count": args.extension_count,
            **common_params,
            "pilot_taxa_path": extension_seed_path.as_posix(),
            "artifact": extension_summary["output_path"],
        },
        "run_level_rows": run_records,
        "scale_statistics": scale_stats,
        "analysis_questions": {
            "q1_novelty_reduces_duplicate_churn": q1,
            "q2_novelty_reduces_compile_deficits": q2,
            "q3_marginal_ai_cost_acceptable_for_compile_gain": q3,
            "q4_extension_marginal_value_better_than_scale": q4,
        },
        "decision": {
            "status": scale_decision["status"],
            "rules_evaluation": scale_decision,
            **verdict,
        },
    }

    summary_json_path = output_dir / "phase3_1_summary.v1.json"
    _write_json(summary_json_path, summary_payload)

    markdown_path = output_dir / "phase3_1_summary.md"
    markdown_parts = [
        "# Phase 3.1 Summary",
        "",
        f"- created_at: `{summary_payload['created_at']}`",
        f"- phase3 closure: `{phase3_closure['phase3_status']}`",
        f"- scale decision: `{scale_decision['status']}`",
        "",
        "## Run-Level Table",
        "",
        _build_markdown_table(run_records),
        "## Decision Narrative",
        "",
        f"- ce qui marche: {verdict['what_works']}",
        f"- ce qui ne marche pas: {verdict['what_does_not_work']}",
        f"- hypothese causale: {verdict['causal_hypothesis']}",
        f"- action suivante recommandee: {verdict['next_recommended_action']}",
        "",
        "## Analysis Questions",
        "",
        f"- Q1 novelty-seeking reduit le churn doublons: `{q1}`",
        f"- Q2 nouveaute reduit deficits compile: `{q2}`",
        f"- Q3 cout IA marginal acceptable pour gain compile: `{q3}`",
        f"- Q4 extension taxons meilleure valeur marginale que scale: `{q4}`",
    ]
    markdown_path.write_text("\n".join(markdown_parts) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "summary_json": summary_json_path.as_posix(),
                "summary_markdown": markdown_path.as_posix(),
                "scale_decision": scale_decision["status"],
                "extension_pack_id": extension_pack_id,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
