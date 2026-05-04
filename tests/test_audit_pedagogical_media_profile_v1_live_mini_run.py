from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_script_module():
    script_path = Path("scripts/audit_pedagogical_media_profile_v1_live_mini_run.py")
    spec = importlib.util.spec_from_file_location(
        "audit_pedagogical_media_profile_v1_live_mini_run",
        script_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load live mini-run audit script module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_live_mini_run_skips_safely_without_credentials(tmp_path: Path) -> None:
    module = _load_script_module()
    output_path = tmp_path / "live-mini-report.json"

    report = module.run_live_mini_audit(
        snapshot_id=None,
        snapshot_root=tmp_path,
        snapshot_manifest_path=None,
        sample_file=None,
        sample_size=5,
        gemini_api_key=None,
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_model="gemini-2.0-flash-lite",
        gemini_concurrency=1,
        output_path=output_path,
    )

    assert report["execution_status"] == "skipped_missing_credentials"
    assert report["decision"] == module.DECISION_SKIPPED
    assert report["sample_size"] == 0
    assert report["summary"]["skip_reason"] == "missing_live_credentials"
    assert module.validate_live_mini_run_report_schema(report) is True


def test_skipped_report_does_not_contain_api_key(tmp_path: Path) -> None:
    module = _load_script_module()
    output_path = tmp_path / "live-mini-report.json"

    report = module.run_live_mini_audit(
        snapshot_id=None,
        snapshot_root=tmp_path,
        snapshot_manifest_path=None,
        sample_file=None,
        sample_size=5,
        gemini_api_key=None,
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_model="gemini-2.0-flash-lite",
        gemini_concurrency=1,
        output_path=output_path,
    )

    # No secret value in report (key env name is allowed; actual key value must not appear)
    assert "GEMINI_API_KEY" in report["summary"]["credential_env_name"]
    # credential_env_name stores the env var name, not a secret value
    assert report["summary"]["credential_env_name"] == "GEMINI_API_KEY"


def test_skipped_report_has_required_keys(tmp_path: Path) -> None:
    module = _load_script_module()
    output_path = tmp_path / "live-mini-report.json"

    report = module.run_live_mini_audit(
        snapshot_id=None,
        snapshot_root=tmp_path,
        snapshot_manifest_path=None,
        sample_file=None,
        sample_size=5,
        gemini_api_key=None,
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_model="gemini-2.0-flash-lite",
        gemini_concurrency=1,
        output_path=output_path,
    )

    required_keys = {
        "schema_version",
        "run_id",
        "generated_at",
        "execution_status",
        "sample_size",
        "model",
        "credential_env_name",
        "summary",
        "per_item_results",
        "decision",
        "decision_thresholds",
    }
    assert required_keys.issubset(report.keys())


def test_skipped_summary_has_required_keys(tmp_path: Path) -> None:
    module = _load_script_module()
    output_path = tmp_path / "live-mini-report.json"

    report = module.run_live_mini_audit(
        snapshot_id=None,
        snapshot_root=tmp_path,
        snapshot_manifest_path=None,
        sample_file=None,
        sample_size=5,
        gemini_api_key=None,
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_model="gemini-2.0-flash-lite",
        gemini_concurrency=1,
        output_path=output_path,
    )

    summary = report["summary"]
    required_summary_keys = {
        "sample_size",
        "model",
        "credential_env_name",
        "concurrency",
        "valid_count",
        "failed_count",
        "failure_reason_distribution",
        "schema_failure_cause_distribution",
        "evidence_type_distribution",
        "organism_group_distribution",
        "average_global_quality_score",
        "average_usage_scores",
        "low_basic_identification_valid_count",
        "high_indirect_evidence_valid_count",
        "feedback_rejection_count",
        "selection_field_rejection_count",
        "biological_basis_rejection_count",
        "qualitative_examples",
        "skip_reason",
    }
    assert required_summary_keys.issubset(summary.keys())


def test_decide_outcome_ready() -> None:
    module = _load_script_module()

    summary = {
        "sample_size": 5,
        "valid_count": 5,
        "failed_count": 0,
        "failure_reason_distribution": {},
        "feedback_rejection_count": 0,
        "selection_field_rejection_count": 0,
    }
    assert module.decide_live_mini_run_outcome(summary) == module.DECISION_READY


def test_decide_outcome_adjust() -> None:
    module = _load_script_module()

    summary = {
        "sample_size": 5,
        "valid_count": 3,
        "failed_count": 2,
        "failure_reason_distribution": {"schema_validation_failed": 2},
        "feedback_rejection_count": 0,
        "selection_field_rejection_count": 0,
    }
    assert module.decide_live_mini_run_outcome(summary) == module.DECISION_ADJUST


def test_decide_outcome_investigate_low_valid_rate() -> None:
    module = _load_script_module()

    summary = {
        "sample_size": 5,
        "valid_count": 1,
        "failed_count": 4,
        "failure_reason_distribution": {"model_output_invalid": 4},
        "feedback_rejection_count": 0,
        "selection_field_rejection_count": 0,
    }
    assert module.decide_live_mini_run_outcome(summary) == module.DECISION_INVESTIGATE


def test_decide_outcome_investigate_model_output_invalid() -> None:
    module = _load_script_module()

    # valid_rate >= 0.8 but model_output_invalid > 0 -> INVESTIGATE
    summary = {
        "sample_size": 5,
        "valid_count": 4,
        "failed_count": 1,
        "failure_reason_distribution": {"model_output_invalid": 1},
        "feedback_rejection_count": 0,
        "selection_field_rejection_count": 0,
    }
    assert module.decide_live_mini_run_outcome(summary) == module.DECISION_INVESTIGATE


def test_decide_outcome_not_ready_if_feedback_rejected() -> None:
    module = _load_script_module()

    # Even with high valid rate, feedback_rejection_count > 0 blocks READY
    summary = {
        "sample_size": 5,
        "valid_count": 5,
        "failed_count": 0,
        "failure_reason_distribution": {},
        "feedback_rejection_count": 1,
        "selection_field_rejection_count": 0,
    }
    result = module.decide_live_mini_run_outcome(summary)
    assert result != module.DECISION_READY


def test_schema_version_is_correct(tmp_path: Path) -> None:
    module = _load_script_module()
    output_path = tmp_path / "report.json"

    report = module.run_live_mini_audit(
        snapshot_id=None,
        snapshot_root=tmp_path,
        snapshot_manifest_path=None,
        sample_file=None,
        sample_size=5,
        gemini_api_key=None,
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_model="gemini-2.0-flash-lite",
        gemini_concurrency=1,
        output_path=output_path,
    )

    assert report["schema_version"] == module.LIVE_MINI_RUN_SCHEMA_VERSION
