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


def _normalization_qualification_context(*, run_dir: Path, source_context: dict[str, Any]) -> dict[str, Any]:
    normalized_path = run_dir / "normalized" / "normalized_snapshot.json"
    qualified_path = run_dir / "qualified" / "qualified_snapshot.json"
    export_path = run_dir / "qualified" / "export_bundle.json"
    return {
        "snapshot_id": source_context["snapshot_id"],
        "snapshot_root": source_context["snapshot_root"],
        "normalized_path": str(normalized_path),
        "qualified_path": str(qualified_path),
        "export_path": str(export_path),
    }


def _normalization_command(context: dict[str, Any]) -> list[str]:
    return [
        sys.executable,
        "scripts/run_pipeline.py",
        "--source-mode",
        "inat_snapshot",
        "--snapshot-id",
        str(context["snapshot_id"]),
        "--snapshot-root",
        str(context["snapshot_root"]),
        "--normalized-path",
        str(context["normalized_path"]),
        "--qualified-path",
        str(context["qualified_path"]),
        "--export-path",
        str(context["export_path"]),
        "--qualifier-mode",
        "rules",
        "--qualification-policy",
        "v1",
    ]


def _qualification_command(context: dict[str, Any]) -> list[str]:
    return [
        sys.executable,
        "scripts/run_pipeline.py",
        "--source-mode",
        "inat_snapshot",
        "--snapshot-id",
        str(context["snapshot_id"]),
        "--snapshot-root",
        str(context["snapshot_root"]),
        "--normalized-path",
        str(context["normalized_path"]),
        "--qualified-path",
        str(context["qualified_path"]),
        "--export-path",
        str(context["export_path"]),
        "--qualifier-mode",
        "cached",
        "--qualification-policy",
        "v1",
    ]


def _pmp_generation_context(*, run_dir: Path, source_context: dict[str, Any], max_media_per_taxon: int | None) -> dict[str, Any]:
    snapshot_dir = Path(source_context["snapshot_dir"])
    ai_outputs_path = snapshot_dir / "ai_outputs.json"
    return {
        "snapshot_id": source_context["snapshot_id"],
        "snapshot_root": source_context["snapshot_root"],
        "snapshot_dir": str(snapshot_dir),
        "ai_outputs_path": str(ai_outputs_path),
        "gemini_concurrency": 4,
        "max_retries": 2,
        "request_interval_seconds": 0.0,
        "max_media_per_taxon": max_media_per_taxon if max_media_per_taxon is not None else 3,
        "max_total": 150,
        "ai_role": "signal_only",
    }


def _pmp_generation_command(context: dict[str, Any]) -> list[str]:
    return [
        sys.executable,
        "scripts/qualify_inat_snapshot.py",
        "--snapshot-id",
        str(context["snapshot_id"]),
        "--snapshot-root",
        str(context["snapshot_root"]),
        "--gemini-concurrency",
        str(context["gemini_concurrency"]),
        "--max-retries",
        str(context["max_retries"]),
        "--request-interval-seconds",
        str(context["request_interval_seconds"]),
    ]


def _materialization_context(
    *,
    run_dir: Path,
    source_context: dict[str, Any],
    norm_qual_context: dict[str, Any],
    pmp_context: dict[str, Any],
) -> dict[str, Any]:
    return {
        "plan_path": str(run_dir / "localized_names" / "apply_plan.json"),
        "distractor_path": str(run_dir / "distractors" / "projection.json"),
        "qualified_export_path": str(norm_qual_context["export_path"]),
        "inat_manifest_path": str(Path(source_context["snapshot_dir"]) / "manifest.json"),
        "inat_ai_outputs_path": str(pmp_context["ai_outputs_path"]),
        "materialization_source_path": str(mat.MATERIALIZATION_SOURCE_PATH),
        "output_dir": str(run_dir / "golden_pack"),
        "pack_id": "belgian_birds_mvp_v1",
        "locale": "fr",
        "target_count": 30,
    }


def _materialization_command(context: dict[str, Any]) -> list[str]:
    return [
        sys.executable,
        "scripts/materialize_golden_pack_belgian_birds_mvp_v1.py",
        "--plan-path",
        str(context["plan_path"]),
        "--distractor-path",
        str(context["distractor_path"]),
        "--qualified-export-path",
        str(context["qualified_export_path"]),
        "--inat-manifest-path",
        str(context["inat_manifest_path"]),
        "--inat-ai-outputs-path",
        str(context["inat_ai_outputs_path"]),
        "--materialization-source-path",
        str(context["materialization_source_path"]),
        "--output-dir",
        str(context["output_dir"]),
        "--pack-id",
        str(context["pack_id"]),
        "--locale",
        str(context["locale"]),
        "--target-count",
        str(context["target_count"]),
    ]


def _set_source_stage_command(stage_states: list[dict[str, Any]], context: dict[str, Any]) -> None:
    command = _source_inat_refresh_command(context)
    command_str = " ".join(shlex.quote(part) for part in command)
    for row in stage_states:
        if row.get("step") == "source_inat_refresh":
            row["next_command"] = command_str
            return


def _set_stage_command(stage_states: list[dict[str, Any]], stage_name: str, command: list[str]) -> None:
    command_str = " ".join(shlex.quote(part) for part in command)
    for row in stage_states:
        if row.get("step") == stage_name:
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


def _run_normalization_stage(run_dir: Path, context: dict[str, Any]) -> tuple[bool, str]:
    command = _normalization_command(context)
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    normalized_path = Path(context["normalized_path"])
    report = {
        "schema_version": "golden_pack_scoped_normalization_stage.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "context": context,
        "command": command,
        "returncode": int(result.returncode),
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
        "normalized_output_exists": normalized_path.exists(),
    }
    _write_json(run_dir / "normalized" / "normalization_stage_report.json", report)
    if result.returncode != 0:
        return False, f"normalization_command_failed_exit_{result.returncode}"
    if not normalized_path.exists():
        return False, "normalization_missing_normalized_output"
    return True, "completed"


def _run_qualification_stage(run_dir: Path, context: dict[str, Any]) -> tuple[bool, str]:
    command = _qualification_command(context)
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    normalized_path = Path(context["normalized_path"])
    qualified_path = Path(context["qualified_path"])
    export_path = Path(context["export_path"])
    report = {
        "schema_version": "golden_pack_scoped_qualification_stage.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "context": context,
        "command": command,
        "returncode": int(result.returncode),
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
        "normalized_output_exists": normalized_path.exists(),
        "qualified_output_exists": qualified_path.exists(),
        "export_output_exists": export_path.exists(),
    }
    _write_json(run_dir / "qualified" / "qualification_stage_report.json", report)
    if result.returncode != 0:
        return False, f"qualification_command_failed_exit_{result.returncode}"
    if not qualified_path.exists() or not export_path.exists():
        return False, "qualification_missing_qualified_or_export_output"

    _write_json(
        run_dir / "qualified" / "lineage.json",
        {
            "schema_version": "golden_pack_scoped_lineage.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_id": run_dir.name,
            "snapshot_id": context["snapshot_id"],
            "artifacts": {
                "normalized_path": str(normalized_path),
                "qualified_path": str(qualified_path),
                "export_path": str(export_path),
            },
            "commands": {
                "normalization": _normalization_command(context),
                "qualification": command,
            },
        },
    )
    return True, "completed"


def _write_pmp_queue(run_dir: Path, context: dict[str, Any], *, reason: str) -> None:
    _write_json(
        run_dir / "pmp" / "pmp_evaluation_queue.json",
        {
            "schema_version": "golden_pack_scoped_pmp_evaluation_queue.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "snapshot_id": context["snapshot_id"],
            "snapshot_dir": context["snapshot_dir"],
            "ai_outputs_path": context["ai_outputs_path"],
            "max_media_per_taxon": context["max_media_per_taxon"],
            "max_total": context["max_total"],
            "resume_instruction": "run apply --resume <run_id> without --skip-external",
        },
    )


def _run_pmp_profile_generation(run_dir: Path, context: dict[str, Any]) -> tuple[bool, str]:
    command = _pmp_generation_command(context)
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    ai_outputs_path = Path(context["ai_outputs_path"])
    report = {
        "schema_version": "golden_pack_scoped_pmp_profile_generation_report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "context": context,
        "command": command,
        "returncode": int(result.returncode),
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
        "ai_outputs_exists": ai_outputs_path.exists(),
        "status": "completed" if result.returncode == 0 and ai_outputs_path.exists() else "failed",
    }
    _write_json(run_dir / "pmp" / "pmp_profile_generation_report.json", report)
    if result.returncode != 0:
        _write_pmp_queue(run_dir, context, reason=f"pmp_command_failed_exit_{result.returncode}")
        return False, f"pmp_profile_generation_command_failed_exit_{result.returncode}"
    if not ai_outputs_path.exists():
        _write_pmp_queue(run_dir, context, reason="pmp_ai_outputs_missing_after_success")
        return False, "pmp_profile_generation_missing_ai_outputs"
    return True, "completed"


def _run_materialization_stage(run_dir: Path, context: dict[str, Any]) -> tuple[bool, str]:
    command = _materialization_command(context)
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    output_dir = Path(context["output_dir"])
    validation_report_path = output_dir / "validation_report.json"
    validation_status = None
    if validation_report_path.exists():
        try:
            validation = _load_json(validation_report_path)
            validation_status = str(validation.get("status") or "")
        except Exception:
            validation_status = "invalid"

    report = {
        "schema_version": "golden_pack_scoped_materialization_stage_report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "context": context,
        "command": command,
        "returncode": int(result.returncode),
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
        "validation_report_exists": validation_report_path.exists(),
        "validation_report_status": validation_status,
        "runtime_pack_present": (output_dir / "pack.json").exists(),
        "partial_pack_present": (output_dir / "failed_build" / "partial_pack.json").exists(),
    }
    _write_json(run_dir / "golden_pack" / "materialization_stage_report.json", report)

    if validation_status == "passed":
        return True, "completed"
    if validation_status == "failed":
        return True, "completed_with_fail_report"
    if result.returncode != 0:
        return False, f"materialization_command_failed_exit_{result.returncode}"
    return False, "materialization_validation_report_missing_or_invalid"


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


def _run_scoped_localized_names(run_dir: Path) -> dict[str, Any]:
    plan = _load_json(mat.PLAN_PATH)
    safe_targets = set(mat._safe_ready_targets_from_plan(plan))
    filtered_items: list[dict[str, Any]] = []
    fr_safe_count = 0
    for item in plan.get("items", []):
        if not isinstance(item, dict):
            continue
        tid = str(item.get("taxon_id") or "").strip()
        locale = str(item.get("locale") or "").strip()
        decision = str(item.get("decision") or "").strip()
        chosen_value = str(item.get("chosen_value") or "").strip()
        if tid not in safe_targets:
            continue
        filtered_items.append(item)
        if locale == "fr" and decision in {"auto_accept", "same_value"} and chosen_value:
            fr_safe_count += 1

    apply_plan_payload = {
        "schema_version": "golden_pack_scoped_localized_names_apply_plan.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(mat.PLAN_PATH.relative_to(REPO_ROOT)),
        "safe_ready_targets_from_plan": sorted(safe_targets),
        "items": filtered_items,
        "non_actions": ["no_runtime_business_logic_shift"],
    }
    coverage_payload = {
        "schema_version": "golden_pack_scoped_localized_names_coverage_report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "safe_ready_target_count": len(safe_targets),
        "fr_runtime_safe_label_count": fr_safe_count,
        "fr_runtime_safe_complete": fr_safe_count >= 30,
        "manual_overrides_path": "localized_names/manual_overrides.json",
    }
    _write_json(run_dir / "localized_names" / "apply_plan.json", apply_plan_payload)
    _write_json(run_dir / "localized_names" / "coverage_report.json", coverage_payload)
    return coverage_payload


def _run_scoped_distractors(run_dir: Path) -> dict[str, Any]:
    plan = _load_json(mat.PLAN_PATH)
    distractor = _load_json(mat.DISTRACTOR_PATH)
    safe_targets = set(mat._safe_ready_targets_from_plan(plan))

    candidates = [
        row
        for row in distractor.get("projected_records", [])
        if isinstance(row, dict) and str(row.get("target_canonical_taxon_id") or "").strip() in safe_targets
    ]
    projection = {
        "schema_version": "golden_pack_scoped_distractor_projection.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "safe_ready_targets_from_plan": sorted(safe_targets),
        "projected_records": candidates,
        "non_actions": ["no_distractor_relationship_persistence"],
    }
    readiness_rows = []
    by_target: dict[str, int] = {}
    for row in candidates:
        tid = str(row.get("target_canonical_taxon_id") or "").strip()
        by_target[tid] = by_target.get(tid, 0) + 1
    for tid in sorted(safe_targets):
        cnt = by_target.get(tid, 0)
        readiness_rows.append(
            {
                "taxon_ref": tid,
                "candidate_count": cnt,
                "label_safe_minimum_met": cnt >= 3,
            }
        )
    readiness = {
        "schema_version": "golden_pack_scoped_distractor_readiness.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": readiness_rows,
        "non_actions": ["no_distractor_relationship_persistence"],
    }
    _write_json(run_dir / "distractors" / "candidates.json", {"schema_version": "golden_pack_scoped_distractor_candidates.v1", "generated_at": datetime.now(timezone.utc).isoformat(), "rows": candidates})
    _write_json(run_dir / "distractors" / "projection.json", projection)
    _write_json(run_dir / "distractors" / "readiness.json", readiness)
    return readiness


def _run_local_stage(stage: str, run_dir: Path, state: dict[str, Any]) -> None:
    if stage == "scope_resolution":
        return

    if stage == "pmp_policy_projection":
        pmp_ctx = state.get("pmp_generation") if isinstance(state.get("pmp_generation"), dict) else {}
        ai_outputs_path = Path(str(pmp_ctx.get("ai_outputs_path") or mat.INAT_AI_OUTPUTS_PATH))
        if ai_outputs_path.exists():
            ai_outputs = _load_json(ai_outputs_path)
        else:
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
        coverage = _run_scoped_localized_names(run_dir)
        state["metrics"]["fr_runtime_safe_label_count"] = int(coverage.get("fr_runtime_safe_label_count", 0))
        return

    if stage == "distractors_projection":
        readiness = _run_scoped_distractors(run_dir)
        met = sum(1 for row in readiness["rows"] if row["label_safe_minimum_met"])
        state["metrics"]["distractor_ready_count"] = met
        return

    if stage == "candidate_readiness":
        required_inputs = [
            run_dir / "policy" / "pmp_policy_projection.json",
            run_dir / "localized_names" / "apply_plan.json",
            run_dir / "localized_names" / "coverage_report.json",
            run_dir / "distractors" / "candidates.json",
            run_dir / "distractors" / "projection.json",
            run_dir / "distractors" / "readiness.json",
        ]
        missing = [str(path.relative_to(run_dir)) for path in required_inputs if not path.exists()]
        if missing:
            raise RuntimeError("candidate_readiness_missing_inputs:" + ",".join(missing))

        candidate = local_canonical._build_candidate_readiness()
        candidate["run_scoped_inputs"] = [str(path.relative_to(run_dir)) for path in required_inputs]
        _write_json(run_dir / "readiness" / "candidate_readiness.json", candidate)

        diagnosis = diagnose.build_diagnosis()
        diagnosis["run_scoped_inputs"] = [str(path.relative_to(run_dir)) for path in required_inputs]
        diagnosis["non_actions"] = ["no_distractor_relationship_persistence"]
        _write_json(run_dir / "reports" / "blocker_diagnosis.json", diagnosis)

        state["metrics"]["ready_count"] = int(candidate.get("summary", {}).get("golden_pack_ready_targets", 0))
        state["metrics"]["blockers"] = diagnosis.get("rejection_reason_counts", {})
        return

    if stage == "promotion_check":
        ready = int(state["metrics"].get("ready_count") or 0)
        materialization_report_path = run_dir / "golden_pack" / "validation_report.json"
        validation_status = None
        if materialization_report_path.exists():
            try:
                validation_status = str(_load_json(materialization_report_path).get("status") or "")
            except Exception:
                validation_status = "invalid"
        promotable = validation_status == "passed"
        report = {
            "ready_count": ready,
            "blockers": state["metrics"].get("blockers", {}),
            "media_eligible_count": int(state["metrics"].get("media_eligible_count") or 0),
            "policy_borderline_count": int(state["metrics"].get("policy_borderline_count") or 0),
            "golden_pack_generated": promotable,
            "materialization_status": validation_status or "missing",
            "validation_report_status": validation_status or "missing",
            "runtime_pack_present": (run_dir / "golden_pack" / "pack.json").exists(),
            "blocked_step": "promotion_apply" if promotable else "golden_pack_materialization_run_scoped",
            "reason": "materialization passed; manual promotion required"
            if promotable
            else "materialization failed or missing validation report",
            "required_manual_or_external_action": "run explicit promotion command"
            if promotable
            else "inspect golden_pack/validation_report.json and rerun upstream stages",
            "next_command": "python scripts/promote_golden_pack_v1_run_output.py --run-output-dir <run_dir>/golden_pack",
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
    norm_qual_context = _normalization_qualification_context(run_dir=run_dir, source_context=source_refresh_context)
    pmp_context = _pmp_generation_context(
        run_dir=run_dir,
        source_context=source_refresh_context,
        max_media_per_taxon=max_media_per_taxon,
    )
    manifest["source_inat_refresh"] = source_refresh_context
    manifest["normalization_qualification"] = norm_qual_context
    manifest["pmp_generation"] = pmp_context
    materialization_ctx = _materialization_context(
        run_dir=run_dir,
        source_context=source_refresh_context,
        norm_qual_context=norm_qual_context,
        pmp_context=pmp_context,
    )
    manifest["materialization"] = materialization_ctx
    _set_source_stage_command(stage_states, source_refresh_context)
    _set_stage_command(stage_states, "normalization", _normalization_command(norm_qual_context))
    _set_stage_command(stage_states, "qualification", _qualification_command(norm_qual_context))
    _set_stage_command(stage_states, "pmp_profile_generation", _pmp_generation_command(pmp_context))
    _set_stage_command(stage_states, "golden_pack_materialization_run_scoped", _materialization_command(materialization_ctx))

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
                if stage == "pmp_profile_generation":
                    _write_json(
                        run_dir / "pmp" / "pmp_profile_generation_report.json",
                        {
                            "schema_version": "golden_pack_scoped_pmp_profile_generation_report.v1",
                            "generated_at": datetime.now(timezone.utc).isoformat(),
                            "context": pmp_context,
                            "status": "skipped_external_by_flag",
                        },
                    )
                    _write_pmp_queue(run_dir, pmp_context, reason="skipped_external_by_flag")
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
            elif stage == "normalization":
                ok, message = _run_normalization_stage(run_dir, norm_qual_context)
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
            elif stage == "qualification":
                ok, message = _run_qualification_stage(run_dir, norm_qual_context)
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
            elif stage == "pmp_profile_generation":
                ok, message = _run_pmp_profile_generation(run_dir, pmp_context)
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
            elif stage == "golden_pack_materialization_run_scoped":
                ok, message = _run_materialization_stage(run_dir, materialization_ctx)
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
            try:
                _run_local_stage(stage, run_dir, manifest)
                row["status"] = "completed"
                row["message"] = "completed"
            except RuntimeError as exc:
                row["status"] = "blocked_external"
                row["message"] = str(exc)
                manifest["status"] = "blocked_external"
                manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
                _persist_state(run_dir, manifest, stage_states, inventory, expected)
                break

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
