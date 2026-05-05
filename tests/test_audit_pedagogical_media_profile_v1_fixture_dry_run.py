from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_script_module():
    script_path = Path("scripts/audit_pedagogical_media_profile_v1_fixture_dry_run.py")
    spec = importlib.util.spec_from_file_location(
        "audit_pedagogical_media_profile_v1_fixture_dry_run",
        script_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load pedagogical media profile fixture dry-run module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_fixture_dry_run_report_has_required_keys() -> None:
    module = _load_script_module()
    report = module.run_fixture_dry_run_audit()

    required_keys = {
        "execution_status",
        "fixture_count",
        "valid_count",
        "failed_count",
        "failure_reason_distribution",
        "schema_validation_failed_count",
        "model_output_invalid_count",
        "schema_failure_cause_distribution",
        "evidence_type_distribution",
        "organism_group_distribution",
        "average_global_quality_score",
        "average_usage_scores",
        "low_basic_identification_valid_count",
        "high_indirect_evidence_valid_count",
        "feedback_rejection_count",
        "biological_basis_rejection_count",
        "qualitative_examples",
        "decision",
    }
    assert required_keys.issubset(report.keys())


def test_fixture_dry_run_counts_and_decision() -> None:
    module = _load_script_module()
    report = module.run_fixture_dry_run_audit()

    assert report["schema_version"] == "pedagogical_media_profile_fixture_dry_run.v1"
    assert report["execution_status"] == "ok"
    assert report["fixture_count"] == 10
    assert report["valid_count"] == 7
    assert report["failed_count"] == 3

    assert report["schema_validation_failed_count"] == 2
    assert report["model_output_invalid_count"] == 0
    assert report["feedback_rejection_count"] == 1
    assert report["biological_basis_rejection_count"] == 1

    assert report["failure_reason_distribution"]["schema_validation_failed"] == 2
    assert report["failure_reason_distribution"]["media_uninspectable"] == 1

    assert report["low_basic_identification_valid_count"] >= 1
    assert report["high_indirect_evidence_valid_count"] >= 1
    assert report["decision"] == "READY_FOR_LIVE_MINI_RUN"


def test_fixture_dry_run_is_deterministic_excluding_decision_inputs() -> None:
    module = _load_script_module()

    report_a = module.run_fixture_dry_run_audit()
    report_b = module.run_fixture_dry_run_audit()

    assert report_a == report_b
