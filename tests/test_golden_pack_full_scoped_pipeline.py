from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts import run_golden_pack_v1_full_scoped_pipeline as orchestrator


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_full_scoped_pipeline_dry_run_and_apply_safety(tmp_path: Path) -> None:
    evidence_path = Path("docs/audits/evidence/database_integrity_runtime_handoff_audit.json")
    before = evidence_path.read_text(encoding="utf-8")

    dry_dir = orchestrator.run_pipeline(mode="dry-run", output_root=tmp_path)
    assert (dry_dir / "run_manifest.json").exists()
    assert (dry_dir / "pipeline_plan.json").exists()
    assert (dry_dir / "input_inventory.json").exists()
    assert (dry_dir / "expected_outputs.json").exists()
    assert not (dry_dir / "golden_pack" / "pack.json").exists()

    dry_manifest = _load(dry_dir / "run_manifest.json")
    assert dry_manifest["status"] == "planned_only"

    apply_dir = orchestrator.run_pipeline(mode="apply", output_root=tmp_path, skip_external=True)
    assert (apply_dir / "run_manifest.json").exists()
    assert (apply_dir / "reports" / "final_report.json").exists()
    assert (apply_dir / "policy" / "pmp_policy_projection.json").exists()
    assert not (apply_dir / "golden_pack" / "pack.json").exists()

    manifest = _load(apply_dir / "run_manifest.json")
    assert manifest["flags"]["DATABASE_PHASE_CLOSED"] is False
    assert manifest["flags"]["PERSIST_DISTRACTOR_RELATIONSHIPS_V1"] is False
    assert manifest["scope"]["target_scope"] == "50-baseline"

    policy = _load(apply_dir / "policy" / "pmp_policy_projection.json")
    for row in policy["rows"]:
        if row.get("borderline") is True:
            assert row.get("eligible") is False

    stage_states = _load(apply_dir / "pipeline_plan.json")["steps"]
    by_step = {row["step"]: row["status"] for row in stage_states}
    assert by_step["source_inat_refresh"] == "skipped"
    assert by_step["pmp_policy_projection"] == "completed"

    after = evidence_path.read_text(encoding="utf-8")
    assert before == after


def test_full_scoped_pipeline_stop_after_and_resume(tmp_path: Path) -> None:
    first_dir = orchestrator.run_pipeline(
        mode="apply",
        output_root=tmp_path,
        skip_external=True,
        stop_after="localized_names",
        target_scope="32-safe-ready",
        max_media_per_taxon=3,
    )
    first_manifest = _load(first_dir / "run_manifest.json")
    assert first_manifest["status"] == "stopped"
    assert first_manifest["scope"]["target_scope"] == "32-safe-ready"
    assert first_manifest["scope"]["max_media_per_taxon"] == 3

    first_steps = {row["step"]: row["status"] for row in _load(first_dir / "pipeline_plan.json")["steps"]}
    assert first_steps["localized_names"] == "completed"
    assert first_steps["distractors_projection"] == "planned"

    resumed_dir = orchestrator.run_pipeline(
        mode="apply",
        output_root=tmp_path,
        resume_run_id=first_manifest["run_id"],
        skip_external=True,
    )
    assert resumed_dir == first_dir

    resumed_manifest = _load(resumed_dir / "run_manifest.json")
    assert resumed_manifest["status"] in {"applied_with_skips", "completed"}

    resumed_steps = {row["step"]: row["status"] for row in _load(resumed_dir / "pipeline_plan.json")["steps"]}
    assert resumed_steps["candidate_readiness"] == "completed"
    assert resumed_steps["promotion_check"] == "completed"
    assert resumed_steps["promotion_apply"] == "skipped"


def test_full_scoped_pipeline_apply_without_skip_blocks_external(tmp_path: Path, monkeypatch) -> None:
    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        return subprocess.CompletedProcess(args=args, returncode=9, stdout="", stderr="simulated external failure")

    monkeypatch.setattr(orchestrator.subprocess, "run", fake_run)
    run_dir = orchestrator.run_pipeline(mode="apply", output_root=tmp_path, skip_external=False)
    manifest = _load(run_dir / "run_manifest.json")
    assert manifest["status"] == "blocked_external"

    steps = _load(run_dir / "pipeline_plan.json")["steps"]
    by_step = {row["step"]: row["status"] for row in steps}
    assert by_step["source_inat_refresh"] == "blocked_external"
    assert by_step["pmp_policy_projection"] == "planned"
    assert not (run_dir / "policy" / "pmp_policy_projection.json").exists()


def test_full_scoped_pipeline_source_inat_refresh_success_then_blocks_next_external(tmp_path: Path, monkeypatch) -> None:
    def fake_run(cmd, cwd, check, capture_output, text):  # type: ignore[no-untyped-def]
        snapshot_id = cmd[cmd.index("--snapshot-id") + 1]
        snapshot_root = Path(cmd[cmd.index("--snapshot-root") + 1])
        snapshot_dir = snapshot_root / snapshot_id
        (snapshot_dir / "responses").mkdir(parents=True, exist_ok=True)
        (snapshot_dir / "taxa").mkdir(parents=True, exist_ok=True)
        (snapshot_dir / "images").mkdir(parents=True, exist_ok=True)
        (snapshot_dir / "manifest.json").write_text('{"manifest_version":"v1"}\n', encoding="utf-8")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(orchestrator.subprocess, "run", fake_run)
    run_dir = orchestrator.run_pipeline(mode="apply", output_root=tmp_path, skip_external=False)

    manifest = _load(run_dir / "run_manifest.json")
    assert manifest["status"] == "blocked_external"
    assert manifest["source_inat_refresh"]["snapshot_id"].endswith("_inat")

    steps = _load(run_dir / "pipeline_plan.json")["steps"]
    source_step = next(row for row in steps if row["step"] == "source_inat_refresh")
    assert source_step["status"] == "completed"
    assert "--country-code BE" in source_step["next_command"]

    assert (run_dir / "source_fetch" / "source_inat_refresh.json").exists()
    assert (run_dir / "raw" / "snapshot_link.json").exists()
    assert _load(run_dir / "raw" / "snapshot_link.json")["snapshot_id"] == manifest["source_inat_refresh"]["snapshot_id"]
