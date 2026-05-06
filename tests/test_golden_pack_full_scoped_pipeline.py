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
    assert (apply_dir / "localized_names" / "apply_plan.json").exists()
    assert (apply_dir / "localized_names" / "coverage_report.json").exists()
    assert (apply_dir / "distractors" / "candidates.json").exists()
    assert (apply_dir / "distractors" / "projection.json").exists()
    assert (apply_dir / "distractors" / "readiness.json").exists()
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
    assert by_step["candidate_readiness"] == "completed"

    coverage = _load(apply_dir / "localized_names" / "coverage_report.json")
    assert coverage["fr_runtime_safe_label_count"] >= 1
    assert isinstance(coverage["fr_runtime_safe_complete"], bool)

    projection = _load(apply_dir / "distractors" / "projection.json")
    assert "no_distractor_relationship_persistence" in projection["non_actions"]

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


def test_full_scoped_pipeline_normalization_and_qualification_success(tmp_path: Path, monkeypatch) -> None:
    def fake_run(cmd, cwd, check, capture_output, text):  # type: ignore[no-untyped-def]
        if cmd[1] == "scripts/fetch_inat_snapshot.py":
            snapshot_id = cmd[cmd.index("--snapshot-id") + 1]
            snapshot_root = Path(cmd[cmd.index("--snapshot-root") + 1])
            snapshot_dir = snapshot_root / snapshot_id
            (snapshot_dir / "responses").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "taxa").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "images").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "manifest.json").write_text('{"manifest_version":"v1"}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="fetch-ok", stderr="")

        if cmd[1] == "scripts/run_pipeline.py":
            normalized = Path(cmd[cmd.index("--normalized-path") + 1])
            qualified = Path(cmd[cmd.index("--qualified-path") + 1])
            export = Path(cmd[cmd.index("--export-path") + 1])
            normalized.parent.mkdir(parents=True, exist_ok=True)
            qualified.parent.mkdir(parents=True, exist_ok=True)
            export.parent.mkdir(parents=True, exist_ok=True)
            normalized.write_text('{"normalized":true}\n', encoding="utf-8")
            qualified.write_text('{"qualified":true}\n', encoding="utf-8")
            export.write_text('{"export":true}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="pipeline-ok", stderr="")

        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="unexpected command")

    monkeypatch.setattr(orchestrator.subprocess, "run", fake_run)
    run_dir = orchestrator.run_pipeline(mode="apply", output_root=tmp_path, skip_external=False)

    steps = _load(run_dir / "pipeline_plan.json")["steps"]
    by_step = {row["step"]: row for row in steps}
    assert by_step["source_inat_refresh"]["status"] == "completed"
    assert by_step["normalization"]["status"] == "completed"
    assert by_step["qualification"]["status"] == "completed"
    assert by_step["pmp_profile_generation"]["status"] == "blocked_external"

    assert (run_dir / "normalized" / "normalization_stage_report.json").exists()
    assert (run_dir / "qualified" / "qualification_stage_report.json").exists()
    assert (run_dir / "qualified" / "lineage.json").exists()

    norm_cmd = by_step["normalization"]["next_command"]
    qual_cmd = by_step["qualification"]["next_command"]
    manifest = _load(run_dir / "run_manifest.json")
    snapshot_id = manifest["source_inat_refresh"]["snapshot_id"]
    assert f"--snapshot-id {snapshot_id}" in norm_cmd
    assert f"--snapshot-id {snapshot_id}" in qual_cmd


def test_full_scoped_pipeline_blocks_when_qualification_fails(tmp_path: Path, monkeypatch) -> None:
    def fake_run(cmd, cwd, check, capture_output, text):  # type: ignore[no-untyped-def]
        if cmd[1] == "scripts/fetch_inat_snapshot.py":
            snapshot_id = cmd[cmd.index("--snapshot-id") + 1]
            snapshot_root = Path(cmd[cmd.index("--snapshot-root") + 1])
            snapshot_dir = snapshot_root / snapshot_id
            (snapshot_dir / "responses").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "taxa").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "images").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "manifest.json").write_text('{"manifest_version":"v1"}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="fetch-ok", stderr="")
        if cmd[1] == "scripts/run_pipeline.py":
            qualifier_mode = cmd[cmd.index("--qualifier-mode") + 1]
            normalized = Path(cmd[cmd.index("--normalized-path") + 1])
            normalized.parent.mkdir(parents=True, exist_ok=True)
            normalized.write_text('{"normalized":true}\n', encoding="utf-8")
            if qualifier_mode == "cached":
                return subprocess.CompletedProcess(args=cmd, returncode=7, stdout="", stderr="qualification failed")
            qualified = Path(cmd[cmd.index("--qualified-path") + 1])
            export = Path(cmd[cmd.index("--export-path") + 1])
            qualified.parent.mkdir(parents=True, exist_ok=True)
            export.parent.mkdir(parents=True, exist_ok=True)
            qualified.write_text('{"qualified":true}\n', encoding="utf-8")
            export.write_text('{"export":true}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="normalization-ok", stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="unexpected command")

    monkeypatch.setattr(orchestrator.subprocess, "run", fake_run)
    run_dir = orchestrator.run_pipeline(mode="apply", output_root=tmp_path, skip_external=False)

    manifest = _load(run_dir / "run_manifest.json")
    assert manifest["status"] == "blocked_external"
    steps = _load(run_dir / "pipeline_plan.json")["steps"]
    by_step = {row["step"]: row for row in steps}
    assert by_step["normalization"]["status"] == "completed"
    assert by_step["qualification"]["status"] == "blocked_external"
    assert by_step["pmp_profile_generation"]["status"] == "planned"
    assert not (run_dir / "qualified" / "lineage.json").exists()


def test_full_scoped_pipeline_pmp_skip_external_writes_queue(tmp_path: Path) -> None:
    run_dir = orchestrator.run_pipeline(mode="apply", output_root=tmp_path, skip_external=True)
    steps = _load(run_dir / "pipeline_plan.json")["steps"]
    by_step = {row["step"]: row for row in steps}
    assert by_step["pmp_profile_generation"]["status"] == "skipped"
    assert (run_dir / "pmp" / "pmp_profile_generation_report.json").exists()
    assert (run_dir / "pmp" / "pmp_evaluation_queue.json").exists()


def test_full_scoped_pipeline_pmp_success(tmp_path: Path, monkeypatch) -> None:
    def fake_run(cmd, cwd, check, capture_output, text):  # type: ignore[no-untyped-def]
        if cmd[1] == "scripts/fetch_inat_snapshot.py":
            snapshot_id = cmd[cmd.index("--snapshot-id") + 1]
            snapshot_root = Path(cmd[cmd.index("--snapshot-root") + 1])
            snapshot_dir = snapshot_root / snapshot_id
            (snapshot_dir / "responses").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "taxa").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "images").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "manifest.json").write_text('{"manifest_version":"v1"}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="fetch-ok", stderr="")
        if cmd[1] == "scripts/run_pipeline.py":
            normalized = Path(cmd[cmd.index("--normalized-path") + 1])
            qualified = Path(cmd[cmd.index("--qualified-path") + 1])
            export = Path(cmd[cmd.index("--export-path") + 1])
            normalized.parent.mkdir(parents=True, exist_ok=True)
            qualified.parent.mkdir(parents=True, exist_ok=True)
            export.parent.mkdir(parents=True, exist_ok=True)
            normalized.write_text('{"normalized":true}\n', encoding="utf-8")
            qualified.write_text('{"qualified":true}\n', encoding="utf-8")
            export.write_text('{"export":true}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="pipeline-ok", stderr="")
        if cmd[1] == "scripts/qualify_inat_snapshot.py":
            snapshot_id = cmd[cmd.index("--snapshot-id") + 1]
            snapshot_root = Path(cmd[cmd.index("--snapshot-root") + 1])
            ai_outputs_path = snapshot_root / snapshot_id / "ai_outputs.json"
            ai_outputs_path.parent.mkdir(parents=True, exist_ok=True)
            ai_outputs_path.write_text('{"inaturalist::1":{"pedagogical_media_profile":{"quality":"ok"}}}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="pmp-ok", stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="unexpected")

    monkeypatch.setattr(orchestrator.subprocess, "run", fake_run)
    run_dir = orchestrator.run_pipeline(mode="apply", output_root=tmp_path, skip_external=False)
    steps = _load(run_dir / "pipeline_plan.json")["steps"]
    by_step = {row["step"]: row for row in steps}
    assert by_step["pmp_profile_generation"]["status"] == "completed"
    assert "--snapshot-id " in by_step["pmp_profile_generation"]["next_command"]
    assert (run_dir / "pmp" / "pmp_profile_generation_report.json").exists()
    assert not (run_dir / "pmp" / "pmp_evaluation_queue.json").exists()
    assert by_step["golden_pack_materialization_run_scoped"]["status"] == "blocked_external"


def test_full_scoped_pipeline_pmp_failure_then_resume_success(tmp_path: Path, monkeypatch) -> None:
    state = {"pmp_calls": 0}

    def fake_run(cmd, cwd, check, capture_output, text):  # type: ignore[no-untyped-def]
        if cmd[1] == "scripts/fetch_inat_snapshot.py":
            snapshot_id = cmd[cmd.index("--snapshot-id") + 1]
            snapshot_root = Path(cmd[cmd.index("--snapshot-root") + 1])
            snapshot_dir = snapshot_root / snapshot_id
            (snapshot_dir / "responses").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "taxa").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "images").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "manifest.json").write_text('{"manifest_version":"v1"}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="fetch-ok", stderr="")
        if cmd[1] == "scripts/run_pipeline.py":
            normalized = Path(cmd[cmd.index("--normalized-path") + 1])
            qualified = Path(cmd[cmd.index("--qualified-path") + 1])
            export = Path(cmd[cmd.index("--export-path") + 1])
            normalized.parent.mkdir(parents=True, exist_ok=True)
            qualified.parent.mkdir(parents=True, exist_ok=True)
            export.parent.mkdir(parents=True, exist_ok=True)
            normalized.write_text('{"normalized":true}\n', encoding="utf-8")
            qualified.write_text('{"qualified":true}\n', encoding="utf-8")
            export.write_text('{"export":true}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="pipeline-ok", stderr="")
        if cmd[1] == "scripts/qualify_inat_snapshot.py":
            state["pmp_calls"] += 1
            snapshot_id = cmd[cmd.index("--snapshot-id") + 1]
            snapshot_root = Path(cmd[cmd.index("--snapshot-root") + 1])
            ai_outputs_path = snapshot_root / snapshot_id / "ai_outputs.json"
            ai_outputs_path.parent.mkdir(parents=True, exist_ok=True)
            if state["pmp_calls"] == 1:
                return subprocess.CompletedProcess(args=cmd, returncode=6, stdout="", stderr="pmp failure")
            ai_outputs_path.write_text('{"inaturalist::1":{"pedagogical_media_profile":{"quality":"ok"}}}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="pmp-ok", stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="unexpected")

    monkeypatch.setattr(orchestrator.subprocess, "run", fake_run)
    run_dir = orchestrator.run_pipeline(mode="apply", output_root=tmp_path, skip_external=False)
    first_steps = _load(run_dir / "pipeline_plan.json")["steps"]
    by_step_first = {row["step"]: row for row in first_steps}
    assert by_step_first["pmp_profile_generation"]["status"] == "blocked_external"
    assert (run_dir / "pmp" / "pmp_evaluation_queue.json").exists()

    resumed_dir = orchestrator.run_pipeline(
        mode="apply",
        output_root=tmp_path,
        resume_run_id=_load(run_dir / "run_manifest.json")["run_id"],
        skip_external=False,
    )
    assert resumed_dir == run_dir
    resumed_steps = _load(run_dir / "pipeline_plan.json")["steps"]
    by_step_resumed = {row["step"]: row for row in resumed_steps}
    assert by_step_resumed["pmp_profile_generation"]["status"] == "completed"


def test_full_scoped_pipeline_candidate_readiness_blocks_when_scoped_inputs_missing(tmp_path: Path) -> None:
    run_dir = orchestrator.run_pipeline(
        mode="apply",
        output_root=tmp_path,
        skip_external=True,
        stop_after="distractors_projection",
    )
    missing = run_dir / "distractors" / "readiness.json"
    missing.unlink()

    resumed = orchestrator.run_pipeline(
        mode="apply",
        output_root=tmp_path,
        resume_run_id=_load(run_dir / "run_manifest.json")["run_id"],
        skip_external=True,
    )
    assert resumed == run_dir
    manifest = _load(run_dir / "run_manifest.json")
    assert manifest["status"] == "blocked_external"
    steps = _load(run_dir / "pipeline_plan.json")["steps"]
    by_step = {row["step"]: row for row in steps}
    assert by_step["candidate_readiness"]["status"] == "blocked_external"
    assert "candidate_readiness_missing_inputs" in by_step["candidate_readiness"]["message"]


def test_full_scoped_pipeline_materialization_passed_run_scoped(tmp_path: Path, monkeypatch) -> None:
    def fake_run(cmd, cwd, check, capture_output, text):  # type: ignore[no-untyped-def]
        if cmd[1] == "scripts/fetch_inat_snapshot.py":
            snapshot_id = cmd[cmd.index("--snapshot-id") + 1]
            snapshot_root = Path(cmd[cmd.index("--snapshot-root") + 1])
            snapshot_dir = snapshot_root / snapshot_id
            (snapshot_dir / "responses").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "taxa").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "images").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "manifest.json").write_text('{"manifest_version":"v1"}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="fetch-ok", stderr="")
        if cmd[1] == "scripts/run_pipeline.py":
            normalized = Path(cmd[cmd.index("--normalized-path") + 1])
            qualified = Path(cmd[cmd.index("--qualified-path") + 1])
            export = Path(cmd[cmd.index("--export-path") + 1])
            normalized.parent.mkdir(parents=True, exist_ok=True)
            qualified.parent.mkdir(parents=True, exist_ok=True)
            export.parent.mkdir(parents=True, exist_ok=True)
            normalized.write_text('{"normalized":true}\n', encoding="utf-8")
            qualified.write_text('{"qualified":true}\n', encoding="utf-8")
            export.write_text('{"export":true}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="pipeline-ok", stderr="")
        if cmd[1] == "scripts/qualify_inat_snapshot.py":
            snapshot_id = cmd[cmd.index("--snapshot-id") + 1]
            snapshot_root = Path(cmd[cmd.index("--snapshot-root") + 1])
            ai_outputs_path = snapshot_root / snapshot_id / "ai_outputs.json"
            ai_outputs_path.parent.mkdir(parents=True, exist_ok=True)
            ai_outputs_path.write_text('{"inaturalist::1":{"pedagogical_media_profile":{"quality":"ok"}}}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="pmp-ok", stderr="")
        if cmd[1] == "scripts/materialize_golden_pack_belgian_birds_mvp_v1.py":
            out_dir = Path(cmd[cmd.index("--output-dir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "validation_report.json").write_text('{"status":"passed"}\n', encoding="utf-8")
            (out_dir / "pack.json").write_text('{"schema_version":"golden_pack.v1"}\n', encoding="utf-8")
            (out_dir / "manifest.json").write_text('{"schema_version":"golden_pack_manifest.v1"}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="mat-ok", stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="unexpected")

    monkeypatch.setattr(orchestrator.subprocess, "run", fake_run)
    run_dir = orchestrator.run_pipeline(mode="apply", output_root=tmp_path, skip_external=False)
    steps = _load(run_dir / "pipeline_plan.json")["steps"]
    by_step = {row["step"]: row for row in steps}
    assert by_step["golden_pack_materialization_run_scoped"]["status"] == "completed"
    assert by_step["promotion_check"]["status"] == "completed"
    assert by_step["promotion_apply"]["status"] == "blocked_external"
    final_report = _load(run_dir / "reports" / "final_report.json")
    assert final_report["validation_report_status"] == "passed"
    assert final_report["runtime_pack_present"] is True


def test_full_scoped_pipeline_materialization_failed_no_runtime_pack(tmp_path: Path, monkeypatch) -> None:
    def fake_run(cmd, cwd, check, capture_output, text):  # type: ignore[no-untyped-def]
        if cmd[1] == "scripts/fetch_inat_snapshot.py":
            snapshot_id = cmd[cmd.index("--snapshot-id") + 1]
            snapshot_root = Path(cmd[cmd.index("--snapshot-root") + 1])
            snapshot_dir = snapshot_root / snapshot_id
            (snapshot_dir / "responses").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "taxa").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "images").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "manifest.json").write_text('{"manifest_version":"v1"}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="fetch-ok", stderr="")
        if cmd[1] == "scripts/run_pipeline.py":
            normalized = Path(cmd[cmd.index("--normalized-path") + 1])
            qualified = Path(cmd[cmd.index("--qualified-path") + 1])
            export = Path(cmd[cmd.index("--export-path") + 1])
            normalized.parent.mkdir(parents=True, exist_ok=True)
            qualified.parent.mkdir(parents=True, exist_ok=True)
            export.parent.mkdir(parents=True, exist_ok=True)
            normalized.write_text('{"normalized":true}\n', encoding="utf-8")
            qualified.write_text('{"qualified":true}\n', encoding="utf-8")
            export.write_text('{"export":true}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="pipeline-ok", stderr="")
        if cmd[1] == "scripts/qualify_inat_snapshot.py":
            snapshot_id = cmd[cmd.index("--snapshot-id") + 1]
            snapshot_root = Path(cmd[cmd.index("--snapshot-root") + 1])
            ai_outputs_path = snapshot_root / snapshot_id / "ai_outputs.json"
            ai_outputs_path.parent.mkdir(parents=True, exist_ok=True)
            ai_outputs_path.write_text('{"inaturalist::1":{"pedagogical_media_profile":{"quality":"ok"}}}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="pmp-ok", stderr="")
        if cmd[1] == "scripts/materialize_golden_pack_belgian_birds_mvp_v1.py":
            out_dir = Path(cmd[cmd.index("--output-dir") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "validation_report.json").write_text('{"status":"failed"}\n', encoding="utf-8")
            (out_dir / "failed_build").mkdir(parents=True, exist_ok=True)
            (out_dir / "failed_build" / "partial_pack.json").write_text('{"schema_version":"golden_pack.v1"}\n', encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="mat-failed")
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="unexpected")

    monkeypatch.setattr(orchestrator.subprocess, "run", fake_run)
    run_dir = orchestrator.run_pipeline(mode="apply", output_root=tmp_path, skip_external=False)
    steps = _load(run_dir / "pipeline_plan.json")["steps"]
    by_step = {row["step"]: row for row in steps}
    assert by_step["golden_pack_materialization_run_scoped"]["status"] == "completed"
    assert by_step["golden_pack_materialization_run_scoped"]["message"] == "completed_with_fail_report"
    assert by_step["promotion_check"]["status"] == "completed"
    final_report = _load(run_dir / "reports" / "final_report.json")
    assert final_report["validation_report_status"] == "failed"
    assert final_report["runtime_pack_present"] is False
    assert (run_dir / "golden_pack" / "failed_build" / "partial_pack.json").exists()
