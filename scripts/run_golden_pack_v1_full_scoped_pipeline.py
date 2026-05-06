from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import diagnose_golden_pack_belgian_birds_mvp_v1_blockers as diagnose
from scripts import materialize_golden_pack_belgian_birds_mvp_v1 as mat
from scripts import run_golden_pack_v1_local_canonical_pipeline as local_canonical

RUN_PREFIX = "golden_pack_belgian_birds_mvp_v1_full_scoped"
RUNS_ROOT = REPO_ROOT / "data" / "runs"

EXTERNAL_STAGES = {
    "source_inat_refresh",
    "normalization",
    "qualification",
    "pmp_profile_generation",
    "golden_pack_materialization_run_scoped",
    "promotion_apply",
}

FLAGS = {
    "DATABASE_PHASE_CLOSED": False,
    "PERSIST_DISTRACTOR_RELATIONSHIPS_V1": False,
}

TARGET_SCOPE_PILOT_TAXA = {
    "50-baseline": REPO_ROOT / "data" / "fixtures" / "inaturalist_pilot_taxa_palier1_be_50_run003_v11_baseline.json",
    "32-safe-ready": REPO_ROOT / "data" / "fixtures" / "inaturalist_pilot_taxa_palier1_be_50_run003_v11_selected.json",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _stage_records() -> list[dict[str, Any]]:
    return [
        {"step": "scope_resolution", "executable_local": True, "next_command": "internal"},
        {"step": "source_inat_refresh", "executable_local": False, "next_command": "python scripts/fetch_inat_snapshot.py"},
        {"step": "normalization", "executable_local": False, "next_command": "python scripts/run_pipeline.py"},
        {"step": "qualification", "executable_local": False, "next_command": "python scripts/qualify_inat_snapshot.py"},
        {"step": "pmp_profile_generation", "executable_local": False, "next_command": "python scripts/qualify_inat_snapshot.py"},
        {"step": "pmp_policy_projection", "executable_local": True, "next_command": "local_policy_from_ai_outputs"},
        {"step": "localized_names", "executable_local": True, "next_command": "reuse_or_reproject_localized_names"},
        {"step": "distractors_projection", "executable_local": True, "next_command": "reuse_or_reproject_distractors"},
        {"step": "candidate_readiness", "executable_local": True, "next_command": "local_candidate_readiness"},
        {"step": "golden_pack_materialization_run_scoped", "executable_local": False, "next_command": "python scripts/materialize_golden_pack_belgian_birds_mvp_v1.py"},
        {"step": "promotion_check", "executable_local": True, "next_command": "validate_passed_before_promotion"},
        {"step": "promotion_apply", "executable_local": False, "next_command": "python scripts/promote_golden_pack_v1_run_output.py"},
    ]


def _new_run_dir(output_root: Path | None = None) -> tuple[str, Path]:
    root = output_root or RUNS_ROOT
    run_id = f"{RUN_PREFIX}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    for rel in (
        "source_fetch",
        "raw",
        "normalized",
        "qualified",
        "media",
        "pmp",
        "policy",
        "localized_names",
        "distractors",
        "readiness",
        "golden_pack",
        "reports",
    ):
        (run_dir / rel).mkdir(parents=True, exist_ok=True)
    return run_id, run_dir


def _resolve_existing_run(run_id: str, output_root: Path | None = None) -> Path:
    root = output_root or RUNS_ROOT
    run_dir = root / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"Unknown run_id: {run_id}")
    return run_dir


def _scope_summary(target_scope: str, max_media_per_taxon: int | None) -> dict[str, Any]:
    normalized_path = REPO_ROOT / "data" / "normalized" / "palier1_be_birds_50taxa_run003_v11_baseline.normalized.json"
    normalized = _load_json(normalized_path) if normalized_path.exists() else {}
    canonical_count = len(normalized.get("canonical_taxa", [])) if isinstance(normalized, dict) else 0
    safe_ready = 0
    if mat.PLAN_PATH.exists():
        plan = _load_json(mat.PLAN_PATH)
        safe_ready = len(mat._safe_ready_targets_from_plan(plan))
    return {
        "region": "Belgian birds MVP",
        "locale": "fr",
        "mode": "image-first",
        "target_scope": target_scope,
        "baseline_taxa_count": canonical_count,
        "safe_ready_targets_count": safe_ready,
        "max_media_per_taxon": max_media_per_taxon,
        "golden_pack_target_question_count": 30,
    }


def _input_inventory() -> list[dict[str, Any]]:
    inputs: list[tuple[Path, str]] = [
        (mat.PLAN_PATH, "localized_names"),
        (mat.DISTRACTOR_PATH, "distractors"),
        (mat.QUALIFIED_EXPORT_PATH, "qualified"),
        (REPO_ROOT / "data" / "normalized" / "palier1_be_birds_50taxa_run003_v11_baseline.normalized.json", "normalized"),
        (mat.INAT_MANIFEST_PATH, "raw_media_manifest"),
        (mat.INAT_AI_OUTPUTS_PATH, "pmp_snapshot"),
        (mat.MATERIALIZATION_SOURCE_PATH, "legacy_materialization_source"),
        (REPO_ROOT / "schemas" / "golden_pack_v1.schema.json", "schema"),
        (REPO_ROOT / "schemas" / "golden_pack_manifest_v1.schema.json", "schema"),
        (REPO_ROOT / "schemas" / "golden_pack_validation_report_v1.schema.json", "schema"),
    ]
    out: list[dict[str, Any]] = []
    for path, role in inputs:
        item: dict[str, Any] = {
            "path": str(path.relative_to(REPO_ROOT)),
            "role": role,
            "exists": path.exists(),
        }
        if path.exists():
            item["sha256"] = _sha256(path)
        out.append(item)
    return out


def _expected_outputs() -> dict[str, Any]:
    return {
        "always": [
            "run_manifest.json",
            "pipeline_plan.json",
            "input_inventory.json",
            "expected_outputs.json",
            "reports/final_report.json",
        ],
        "apply_local_possible": [
            "policy/pmp_policy_projection.json",
            "localized_names/localized_names_snapshot.json",
            "distractors/distractor_projection_snapshot.json",
            "readiness/candidate_readiness.json",
            "reports/blocker_diagnosis.json",
        ],
        "conditional_runtime_output": [
            "golden_pack/pack.json only if strict 30/30 and validation_report.status=passed",
        ],
    }


def _source_inat_refresh_context(
    *,
    run_id: str,
    target_scope: str,
    max_observations_per_taxon: int = 8,
    timeout_seconds: int = 30,
    country_code: str = "BE",
) -> dict[str, Any]:
    pilot_taxa_path = TARGET_SCOPE_PILOT_TAXA[target_scope]
    snapshot_id = f"{run_id}_inat"
    snapshot_root = REPO_ROOT / "data" / "raw" / "inaturalist"
    snapshot_dir = snapshot_root / snapshot_id
    return {
        "snapshot_id": snapshot_id,
        "snapshot_root": str(snapshot_root),
        "snapshot_dir": str(snapshot_dir),
        "pilot_taxa_path": str(pilot_taxa_path),
        "max_observations_per_taxon": max_observations_per_taxon,
        "timeout_seconds": timeout_seconds,
        "country_code": country_code,
    }


def _source_inat_refresh_command(context: dict[str, Any]) -> list[str]:
    return [
        sys.executable,
        "scripts/fetch_inat_snapshot.py",
        "--snapshot-id",
        str(context["snapshot_id"]),
        "--snapshot-root",
        str(context["snapshot_root"]),
        "--pilot-taxa-path",
        str(context["pilot_taxa_path"]),
        "--max-observations-per-taxon",
        str(context["max_observations_per_taxon"]),
        "--timeout-seconds",
        str(context["timeout_seconds"]),
        "--country-code",
        str(context["country_code"]),
    ]


def _set_source_stage_command(stage_states: list[dict[str, Any]], context: dict[str, Any]) -> None:
    command = _source_inat_refresh_command(context)
    command_str = " ".join(shlex.quote(part) for part in command)
    for row in stage_states:
        if row.get("step") == "source_inat_refresh":
            row["next_command"] = command_str
            return


def _run_source_inat_refresh(run_dir: Path, context: dict[str, Any]) -> tuple[bool, str]:
    command = _source_inat_refresh_command(context)
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    manifest_path = Path(context["snapshot_dir"]) / "manifest.json"
    responses_dir = Path(context["snapshot_dir"]) / "responses"
    taxa_dir = Path(context["snapshot_dir"]) / "taxa"
    images_dir = Path(context["snapshot_dir"]) / "images"

    report = {
        "schema_version": "golden_pack_scoped_source_inat_refresh.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "context": context,
        "command": command,
        "returncode": int(result.returncode),
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
        "snapshot_manifest_exists": manifest_path.exists(),
        "responses_dir_exists": responses_dir.exists(),
        "taxa_dir_exists": taxa_dir.exists(),
        "images_dir_exists": images_dir.exists(),
    }
    _write_json(run_dir / "source_fetch" / "source_inat_refresh.json", report)

    if result.returncode != 0:
        return False, f"source_inat_refresh_command_failed_exit_{result.returncode}"

    required_ok = manifest_path.exists() and responses_dir.exists() and taxa_dir.exists() and images_dir.exists()
    if not required_ok:
        return False, "source_inat_refresh_missing_expected_snapshot_artifacts"

    _write_json(
        run_dir / "raw" / "snapshot_link.json",
        {
            "schema_version": "golden_pack_scoped_snapshot_link.v1",
            "snapshot_id": context["snapshot_id"],
            "snapshot_dir": context["snapshot_dir"],
            "manifest_path": str(manifest_path),
        },
    )
    return True, "completed"


def _evaluate_policy_rows(ai_outputs: dict[str, Any]) -> tuple[list[dict[str, Any]], int, int]:
    rows: list[dict[str, Any]] = []
    eligible_count = 0
    borderline_count = 0
    for key, value in ai_outputs.items():
        if not isinstance(key, str) or "::" not in key or not isinstance(value, dict):
            continue
        media_id = key.split("::", 1)[1]
        profile = value.get("pedagogical_media_profile")
        if not isinstance(profile, dict):
            continue
        decision = mat.evaluate_pmp_profile_policy(profile)
        usage = decision.get("usage_statuses") if isinstance(decision.get("usage_statuses"), dict) else {}
        basic = usage.get("basic_identification") if isinstance(usage.get("basic_identification"), dict) else {}
        status = str(basic.get("status") or "missing")
        is_eligible = status == "eligible"
        is_borderline = status == "borderline"
        if is_eligible:
            eligible_count += 1
        if is_borderline:
            borderline_count += 1
        rows.append(
            {
                "media_id": media_id,
                "basic_identification_status": status,
                "basic_identification_reason": str(basic.get("reason") or ""),
                "eligible": is_eligible,
                "borderline": is_borderline,
            }
        )
    return rows, eligible_count, borderline_count


def _run_local_stage(stage: str, run_dir: Path, state: dict[str, Any]) -> None:
    if stage == "scope_resolution":
        return

    if stage == "pmp_policy_projection":
        ai_outputs = _load_json(mat.INAT_AI_OUTPUTS_PATH)
        rows, eligible_count, borderline_count = _evaluate_policy_rows(ai_outputs)
        _write_json(
            run_dir / "policy" / "pmp_policy_projection.json",
            {
                "schema_version": "golden_pack_scoped_pmp_policy_projection.v1",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "flags": FLAGS,
                "rows": rows,
            },
        )
        state["metrics"]["media_eligible_count"] = eligible_count
        state["metrics"]["policy_borderline_count"] = borderline_count
        return

    if stage == "localized_names":
        plan = _load_json(mat.PLAN_PATH)
        _write_json(
            run_dir / "localized_names" / "localized_names_snapshot.json",
            {
                "schema_version": "golden_pack_scoped_localized_names_snapshot.v1",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "flags": FLAGS,
                "source_path": str(mat.PLAN_PATH.relative_to(REPO_ROOT)),
                "safe_ready_targets_from_plan": mat._safe_ready_targets_from_plan(plan),
            },
        )
        return

    if stage == "distractors_projection":
        distractors = _load_json(mat.DISTRACTOR_PATH)
        _write_json(
            run_dir / "distractors" / "distractor_projection_snapshot.json",
            {
                "schema_version": "golden_pack_scoped_distractor_projection_snapshot.v1",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "flags": FLAGS,
                "source_path": str(mat.DISTRACTOR_PATH.relative_to(REPO_ROOT)),
                "projected_records_count": len(distractors.get("projected_records", [])),
            },
        )
        return

    if stage == "candidate_readiness":
        candidate = local_canonical._build_candidate_readiness()
        _write_json(run_dir / "readiness" / "candidate_readiness.json", candidate)

        diagnosis = diagnose.build_diagnosis()
        _write_json(run_dir / "reports" / "blocker_diagnosis.json", diagnosis)

        state["metrics"]["ready_count"] = int(candidate.get("summary", {}).get("golden_pack_ready_targets", 0))
        state["metrics"]["blockers"] = diagnosis.get("rejection_reason_counts", {})
        return

    if stage == "promotion_check":
        ready = int(state["metrics"].get("ready_count") or 0)
        report = {
            "ready_count": ready,
            "blockers": state["metrics"].get("blockers", {}),
            "media_eligible_count": int(state["metrics"].get("media_eligible_count") or 0),
            "policy_borderline_count": int(state["metrics"].get("policy_borderline_count") or 0),
            "golden_pack_generated": False,
            "blocked_step": "golden_pack_materialization_run_scoped",
            "reason": "scoped materialization output not yet implemented and current readiness < 30",
            "required_manual_or_external_action": "implement scoped materializer output override and rerun after upstream refresh",
            "next_command": "python scripts/materialize_golden_pack_belgian_birds_mvp_v1.py",
        }
        _write_json(run_dir / "reports" / "final_report.json", report)
        return

    raise ValueError(f"Unknown local stage: {stage}")


def _planned_stage_state(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "step": row["step"],
            "status": "planned",
            "executable_local": bool(row["executable_local"]),
            "next_command": row["next_command"],
            "message": "",
        }
        for row in records
    ]


def _first_incomplete_stage_index(stage_states: list[dict[str, Any]]) -> int:
    for idx, row in enumerate(stage_states):
        if row.get("status") != "completed":
            return idx
    return len(stage_states)


def _persist_state(run_dir: Path, manifest: dict[str, Any], stage_states: list[dict[str, Any]], inventory: list[dict[str, Any]], expected: dict[str, Any]) -> None:
    _write_json(run_dir / "run_manifest.json", manifest)
    _write_json(run_dir / "pipeline_plan.json", {"steps": stage_states})
    _write_json(run_dir / "input_inventory.json", {"inputs": inventory})
    _write_json(run_dir / "expected_outputs.json", expected)


def run_pipeline(
    *,
    mode: str,
    output_root: Path | None = None,
    resume_run_id: str | None = None,
    stop_after: str | None = None,
    skip_external: bool = False,
    target_scope: str = "50-baseline",
    max_media_per_taxon: int | None = None,
) -> Path:
    if mode not in {"dry-run", "apply"}:
        raise ValueError("mode must be dry-run or apply")

    stage_templates = _stage_records()
    stage_names = [row["step"] for row in stage_templates]
    if stop_after is not None and stop_after not in stage_names:
        raise ValueError(f"Unknown stage for --stop-after: {stop_after}")

    if resume_run_id:
        run_dir = _resolve_existing_run(resume_run_id, output_root=output_root)
        manifest = _load_json(run_dir / "run_manifest.json")
        stage_states = _load_json(run_dir / "pipeline_plan.json").get("steps", [])
        if not isinstance(stage_states, list) or not stage_states:
            raise ValueError("Invalid pipeline_plan.json for resume")
        inventory = _load_json(run_dir / "input_inventory.json").get("inputs", _input_inventory())
        expected = _expected_outputs()
        run_id = resume_run_id
    else:
        run_id, run_dir = _new_run_dir(output_root=output_root)
        inventory = _input_inventory()
        expected = _expected_outputs()
        stage_states = _planned_stage_state(stage_templates)
        manifest = {
            "schema_version": "golden_pack_v1_full_scoped_pipeline_run_manifest.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run_id,
            "run_dir": str(run_dir),
            "mode": mode,
            "scope": _scope_summary(target_scope=target_scope, max_media_per_taxon=max_media_per_taxon),
            "flags": FLAGS,
            "status": "planned_only" if mode == "dry-run" else "in_progress",
            "resume_supported": True,
            "metrics": {
                "ready_count": None,
                "blockers": {},
                "media_eligible_count": 0,
                "policy_borderline_count": 0,
            },
            "non_actions": [
                "no historical artifact overwrite",
                "no borderline eligible",
                "no runtime business logic reassignment",
                "no distractor relationship persistence",
            ],
        }

    scope = manifest.get("scope") if isinstance(manifest.get("scope"), dict) else {}
    effective_scope = str(scope.get("target_scope") or target_scope)
    source_refresh_context = _source_inat_refresh_context(
        run_id=run_id,
        target_scope=effective_scope,
    )
    manifest["source_inat_refresh"] = source_refresh_context
    _set_source_stage_command(stage_states, source_refresh_context)

    _persist_state(run_dir, manifest, stage_states, inventory, expected)

    if mode == "dry-run":
        _write_json(
            run_dir / "reports" / "final_report.json",
            {
                "ready_count": None,
                "golden_pack_generated": False,
                "blocked_step": "source_inat_refresh",
                "reason": "dry-run only; no stage execution",
                "required_manual_or_external_action": "run apply after validating executable scope",
                "next_command": "python scripts/run_golden_pack_v1_full_scoped_pipeline.py --apply",
            },
        )
        manifest["status"] = "planned_only"
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        _persist_state(run_dir, manifest, stage_states, inventory, expected)
        return run_dir

    current_idx = _first_incomplete_stage_index(stage_states)
    manifest["status"] = "in_progress"

    for idx in range(current_idx, len(stage_states)):
        row = stage_states[idx]
        stage = str(row.get("step"))

        if row.get("status") == "completed":
            continue

        if stage in EXTERNAL_STAGES:
            if skip_external:
                row["status"] = "skipped"
                row["message"] = "skipped_external_by_flag"
            elif stage == "source_inat_refresh":
                ok, message = _run_source_inat_refresh(run_dir, source_refresh_context)
                if ok:
                    row["status"] = "completed"
                    row["message"] = message
                else:
                    row["status"] = "blocked_external"
                    row["message"] = message
                    manifest["status"] = "blocked_external"
                    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
                    _persist_state(run_dir, manifest, stage_states, inventory, expected)
                    break
            else:
                row["status"] = "blocked_external"
                row["message"] = "requires_external_execution"
                manifest["status"] = "blocked_external"
                manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
                _persist_state(run_dir, manifest, stage_states, inventory, expected)
                break
        else:
            _run_local_stage(stage, run_dir, manifest)
            row["status"] = "completed"
            row["message"] = "completed"

        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        _persist_state(run_dir, manifest, stage_states, inventory, expected)

        if stop_after and stage == stop_after:
            manifest["status"] = "stopped"
            manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
            _persist_state(run_dir, manifest, stage_states, inventory, expected)
            return run_dir

    if manifest.get("status") == "in_progress":
        if all(str(item.get("status")) == "completed" for item in stage_states):
            manifest["status"] = "completed"
        elif any(str(item.get("status")) == "blocked_external" for item in stage_states):
            manifest["status"] = "blocked_external"
        else:
            manifest["status"] = "applied_with_skips"

    if not (run_dir / "reports" / "final_report.json").exists():
        _write_json(
            run_dir / "reports" / "final_report.json",
            {
                "ready_count": manifest["metrics"].get("ready_count"),
                "golden_pack_generated": False,
                "blocked_step": "source_inat_refresh",
                "reason": "external stages not executed in this commit",
                "required_manual_or_external_action": "continue with external stages in next commits",
                "next_command": "python scripts/run_golden_pack_v1_full_scoped_pipeline.py --apply --resume " + str(manifest["run_id"]),
            },
        )

    manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
    _persist_state(run_dir, manifest, stage_states, inventory, expected)
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--resume", type=str)
    parser.add_argument("--stop-after", type=str)
    parser.add_argument("--skip-external", action="store_true")
    parser.add_argument("--max-media-per-taxon", type=int)
    parser.add_argument("--target-scope", choices=["50-baseline", "32-safe-ready"], default="50-baseline")
    args = parser.parse_args()

    if args.dry_run == args.apply:
        raise SystemExit("Use exactly one mode: --dry-run or --apply")

    mode = "dry-run" if args.dry_run else "apply"
    run_dir = run_pipeline(
        mode=mode,
        resume_run_id=args.resume,
        stop_after=args.stop_after,
        skip_external=args.skip_external,
        target_scope=args.target_scope,
        max_media_per_taxon=args.max_media_per_taxon,
    )
    print(f"run_dir={run_dir}")
    manifest = _load_json(run_dir / "run_manifest.json")
    report = _load_json(run_dir / "reports" / "final_report.json")
    print(f"status={manifest.get('status')}")
    print(f"golden_pack_generated={report.get('golden_pack_generated')}")


if __name__ == "__main__":
    main()
