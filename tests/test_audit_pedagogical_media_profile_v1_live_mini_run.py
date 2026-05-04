from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Internal fixture helpers
# ---------------------------------------------------------------------------


def _make_valid_result(media_id: str = "m1") -> dict:
    return {
        "media_id": media_id,
        "expected_scientific_name": "Turdus merula",
        "organism_group_input": "bird",
        "organism_group_output": "bird",
        "evidence_type": "whole_organism",
        "review_status": "valid",
        "failure_reason": None,
        "global_quality_score": 75,
        "usage_scores": {
            "basic_identification": 65,
            "field_observation": 70,
            "confusion_learning": 50,
            "morphology_learning": 60,
            "species_card": 70,
            "indirect_evidence_learning": 30,
        },
        "schema_failure_cause": None,
        "schema_error_count": 0,
        "schema_errors": [],
        "feedback_rejection": False,
        "selection_field_rejection": False,
        "biological_basis_rejection": False,
        "raw_model_output_sha256": "abc123",
        "raw_model_output_excerpt": "excerpt...",
        "image_sha256": "def456",
    }


def _make_failed_result(
    media_id: str = "m1",
    failure_reason: str = "schema_validation_failed",
    schema_errors: list | None = None,
) -> dict:
    return {
        "media_id": media_id,
        "expected_scientific_name": "Turdus merula",
        "organism_group_input": "bird",
        "organism_group_output": None,
        "evidence_type": None,
        "review_status": "failed",
        "failure_reason": failure_reason,
        "global_quality_score": None,
        "usage_scores": None,
        "schema_failure_cause": "enum_mismatch",
        "schema_error_count": 1,
        "schema_errors": schema_errors or [
            {
                "path": "technical_profile.framing",
                "message": "'excellent' is not one of ['good', 'acceptable', 'poor', 'unknown']",
                "validator": "enum",
                "expected": ["good", "acceptable", "poor", "unknown"],
                "actual": "excellent",
                "cause": "enum_mismatch",
            }
        ],
        "feedback_rejection": False,
        "selection_field_rejection": False,
        "biological_basis_rejection": False,
        "raw_model_output_sha256": None,
        "raw_model_output_excerpt": None,
        "image_sha256": None,
    }


def _make_sample_json(tmp_path: Path, count: int = 5) -> Path:
    items = [
        {
            "media_id": f"m{i}",
            "media_url": f"https://example.com/image{i}.jpg",
            "expected_scientific_name": "Turdus merula",
            "organism_group": "bird",
        }
        for i in range(count)
    ]
    sample_file = tmp_path / "sample.json"
    sample_file.write_text(json.dumps(items), encoding="utf-8")
    return sample_file


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


# ---------------------------------------------------------------------------
# _compute_summary unit tests
# ---------------------------------------------------------------------------


def test_compute_summary_all_valid_fields() -> None:
    module = _load_script_module()

    results = [_make_valid_result(f"m{i}") for i in range(5)]
    summary = module._compute_summary(
        results,
        sample_size=5,
        model="gemini-2.0-flash-lite",
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_concurrency=1,
    )

    assert summary["valid_count"] == 5
    assert summary["failed_count"] == 0
    assert summary["failure_reason_distribution"] == {}
    assert summary["feedback_rejection_count"] == 0
    assert summary["selection_field_rejection_count"] == 0
    assert summary["average_global_quality_score"] == 75.0
    assert "basic_identification" in summary["average_usage_scores"]
    assert summary["evidence_type_distribution"] == {"whole_organism": 5}
    assert summary["organism_group_distribution"] == {"bird": 5}


def test_compute_summary_failure_distributions() -> None:
    module = _load_script_module()

    results = [
        _make_valid_result("m0"),
        _make_valid_result("m1"),
        _make_valid_result("m2"),
        _make_failed_result("m3", failure_reason="schema_validation_failed"),
        _make_failed_result("m4", failure_reason="model_output_invalid"),
    ]
    summary = module._compute_summary(
        results,
        sample_size=5,
        model="gemini-2.0-flash-lite",
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_concurrency=1,
    )

    assert summary["valid_count"] == 3
    assert summary["failed_count"] == 2
    assert summary["failure_reason_distribution"]["schema_validation_failed"] == 1
    assert summary["failure_reason_distribution"]["model_output_invalid"] == 1


# ---------------------------------------------------------------------------
# Mocked full-run tests — monkeypatch _run_single_item
# ---------------------------------------------------------------------------


def test_mocked_run_all_valid_produces_ready_decision(tmp_path: Path) -> None:
    module = _load_script_module()
    sample_file = _make_sample_json(tmp_path, 5)

    def _mock(item, *, api_key, model_name):
        return _make_valid_result(media_id=item["media_id"])

    module._run_single_item = _mock

    report = module.run_live_mini_audit(
        snapshot_id=None,
        snapshot_root=tmp_path,
        snapshot_manifest_path=None,
        sample_file=sample_file,
        sample_size=5,
        gemini_api_key="fake-api-key",
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_model="gemini-2.0-flash-lite",
        gemini_concurrency=1,
        output_path=tmp_path / "report.json",
    )

    assert report["execution_status"] == "completed"
    assert report["decision"] == module.DECISION_READY
    assert report["sample_size"] == 5
    assert report["summary"]["valid_count"] == 5
    assert report["summary"]["failed_count"] == 0
    assert module.validate_live_mini_run_report_schema(report) is True


def test_mocked_run_partial_failure_produces_adjust_decision(tmp_path: Path) -> None:
    module = _load_script_module()
    sample_file = _make_sample_json(tmp_path, 5)

    results_cycle = [
        _make_valid_result("m0"),
        _make_valid_result("m1"),
        _make_valid_result("m2"),
        _make_failed_result("m3", failure_reason="schema_validation_failed"),
        _make_failed_result("m4", failure_reason="schema_validation_failed"),
    ]
    _call_index = {"n": 0}

    def _mock(item, *, api_key, model_name):
        r = results_cycle[_call_index["n"]]
        _call_index["n"] += 1
        return r

    module._run_single_item = _mock

    report = module.run_live_mini_audit(
        snapshot_id=None,
        snapshot_root=tmp_path,
        snapshot_manifest_path=None,
        sample_file=sample_file,
        sample_size=5,
        gemini_api_key="fake-api-key",
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_model="gemini-2.0-flash-lite",
        gemini_concurrency=1,
        output_path=tmp_path / "report.json",
    )

    assert report["decision"] == module.DECISION_ADJUST
    assert report["summary"]["valid_count"] == 3
    assert report["summary"]["failed_count"] == 2


def test_mocked_run_major_failure_produces_investigate_decision(tmp_path: Path) -> None:
    module = _load_script_module()
    sample_file = _make_sample_json(tmp_path, 5)

    results_cycle = [
        _make_valid_result("m0"),
        _make_failed_result("m1", failure_reason="model_output_invalid"),
        _make_failed_result("m2", failure_reason="model_output_invalid"),
        _make_failed_result("m3", failure_reason="model_output_invalid"),
        _make_failed_result("m4", failure_reason="model_output_invalid"),
    ]
    _call_index = {"n": 0}

    def _mock(item, *, api_key, model_name):
        r = results_cycle[_call_index["n"]]
        _call_index["n"] += 1
        return r

    module._run_single_item = _mock

    report = module.run_live_mini_audit(
        snapshot_id=None,
        snapshot_root=tmp_path,
        snapshot_manifest_path=None,
        sample_file=sample_file,
        sample_size=5,
        gemini_api_key="fake-api-key",
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_model="gemini-2.0-flash-lite",
        gemini_concurrency=1,
        output_path=tmp_path / "report.json",
    )

    assert report["decision"] == module.DECISION_INVESTIGATE


# ---------------------------------------------------------------------------
# Sample size validation
# ---------------------------------------------------------------------------


def test_sample_size_too_small_raises_value_error(tmp_path: Path) -> None:
    module = _load_script_module()
    sample_file = _make_sample_json(tmp_path, 3)

    import pytest

    with pytest.raises(ValueError, match="sample-size"):
        module.run_live_mini_audit(
            snapshot_id=None,
            snapshot_root=tmp_path,
            snapshot_manifest_path=None,
            sample_file=sample_file,
            sample_size=4,
            gemini_api_key="fake-api-key",
            gemini_api_key_env="GEMINI_API_KEY",
            gemini_model="gemini-2.0-flash-lite",
            gemini_concurrency=1,
            output_path=tmp_path / "report.json",
        )


def test_sample_size_too_large_raises_value_error(tmp_path: Path) -> None:
    module = _load_script_module()
    sample_file = _make_sample_json(tmp_path, 5)

    import pytest

    with pytest.raises(ValueError, match="sample-size"):
        module.run_live_mini_audit(
            snapshot_id=None,
            snapshot_root=tmp_path,
            snapshot_manifest_path=None,
            sample_file=sample_file,
            sample_size=11,
            gemini_api_key="fake-api-key",
            gemini_api_key_env="GEMINI_API_KEY",
            gemini_model="gemini-2.0-flash-lite",
            gemini_concurrency=1,
            output_path=tmp_path / "report.json",
        )


# ---------------------------------------------------------------------------
# _load_sample_file unit tests
# ---------------------------------------------------------------------------


def test_load_sample_file_from_valid_json(tmp_path: Path) -> None:
    module = _load_script_module()
    sample_file = _make_sample_json(tmp_path, 5)

    items = module._load_sample_file(sample_file)

    assert len(items) == 5
    for item in items:
        assert "media_url" in item
        assert "expected_scientific_name" in item
        assert "organism_group" in item
        assert "mime_type" in item


def test_load_sample_file_missing_media_url_raises(tmp_path: Path) -> None:
    module = _load_script_module()
    bad_items = [{"expected_scientific_name": "Turdus merula", "organism_group": "bird"}]
    sample_file = tmp_path / "bad.json"
    sample_file.write_text(json.dumps(bad_items), encoding="utf-8")

    import pytest

    with pytest.raises(ValueError, match="media_url"):
        module._load_sample_file(sample_file)


def test_load_sample_file_not_array_raises(tmp_path: Path) -> None:
    module = _load_script_module()
    sample_file = tmp_path / "bad.json"
    sample_file.write_text(json.dumps({"key": "value"}), encoding="utf-8")

    import pytest

    with pytest.raises(ValueError, match="JSON array"):
        module._load_sample_file(sample_file)


# ---------------------------------------------------------------------------
# Raw output handling: no API key in report
# ---------------------------------------------------------------------------


def test_per_item_results_do_not_contain_api_key(tmp_path: Path) -> None:
    module = _load_script_module()
    sample_file = _make_sample_json(tmp_path, 5)
    fake_key = "my-very-secret-api-key-12345"

    def _mock(item, *, api_key, model_name):
        r = _make_valid_result(media_id=item["media_id"])
        r["raw_model_output_sha256"] = "sha256hex"
        r["raw_model_output_excerpt"] = "short excerpt from model output"
        return r

    module._run_single_item = _mock

    report = module.run_live_mini_audit(
        snapshot_id=None,
        snapshot_root=tmp_path,
        snapshot_manifest_path=None,
        sample_file=sample_file,
        sample_size=5,
        gemini_api_key=fake_key,
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_model="gemini-2.0-flash-lite",
        gemini_concurrency=1,
        output_path=tmp_path / "report.json",
    )

    report_text = json.dumps(report)
    assert fake_key not in report_text
    for item in report["per_item_results"]:
        assert "raw_model_output_sha256" in item


def test_per_item_results_excerpt_is_bounded(tmp_path: Path) -> None:
    module = _load_script_module()
    sample_file = _make_sample_json(tmp_path, 5)
    long_text = "x" * 1000

    def _mock(item, *, api_key, model_name):
        r = _make_valid_result(media_id=item["media_id"])
        # Simulate _excerpt() applied upstream by _run_single_item
        r["raw_model_output_excerpt"] = module._excerpt(long_text)
        return r

    module._run_single_item = _mock

    report = module.run_live_mini_audit(
        snapshot_id=None,
        snapshot_root=tmp_path,
        snapshot_manifest_path=None,
        sample_file=sample_file,
        sample_size=5,
        gemini_api_key="fake-api-key",
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_model="gemini-2.0-flash-lite",
        gemini_concurrency=1,
        output_path=tmp_path / "report.json",
    )

    for item in report["per_item_results"]:
        excerpt = item.get("raw_model_output_excerpt") or ""
        assert len(excerpt) <= 300


# ---------------------------------------------------------------------------
# Doctrine preservation
# ---------------------------------------------------------------------------


def test_doctrine_low_basic_identification_item_remains_valid() -> None:
    module = _load_script_module()

    # An item with basic_identification below threshold is still a valid review
    result = _make_valid_result("m1")
    result["usage_scores"]["basic_identification"] = 30  # below LOW_BASIC_IDENTIFICATION_THRESHOLD

    summary = module._compute_summary(
        [result],
        sample_size=1,
        model="gemini-2.0-flash-lite",
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_concurrency=1,
    )

    assert summary["valid_count"] == 1
    assert summary["failed_count"] == 0
    assert summary["low_basic_identification_valid_count"] == 1


def test_doctrine_no_feedback_rejection_in_clean_run(tmp_path: Path) -> None:
    module = _load_script_module()
    sample_file = _make_sample_json(tmp_path, 5)

    def _mock(item, *, api_key, model_name):
        r = _make_valid_result(media_id=item["media_id"])
        r["feedback_rejection"] = False
        r["selection_field_rejection"] = False
        return r

    module._run_single_item = _mock

    report = module.run_live_mini_audit(
        snapshot_id=None,
        snapshot_root=tmp_path,
        snapshot_manifest_path=None,
        sample_file=sample_file,
        sample_size=5,
        gemini_api_key="fake-api-key",
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_model="gemini-2.0-flash-lite",
        gemini_concurrency=1,
        output_path=tmp_path / "report.json",
    )

    assert report["summary"]["feedback_rejection_count"] == 0
    assert report["summary"]["selection_field_rejection_count"] == 0
    assert report["decision"] == module.DECISION_READY


def test_doctrine_feedback_rejection_blocks_ready_decision(tmp_path: Path) -> None:
    module = _load_script_module()
    sample_file = _make_sample_json(tmp_path, 5)

    def _mock(item, *, api_key, model_name):
        r = _make_valid_result(media_id=item["media_id"])
        r["feedback_rejection"] = True  # model injected forbidden feedback field
        return r

    module._run_single_item = _mock

    report = module.run_live_mini_audit(
        snapshot_id=None,
        snapshot_root=tmp_path,
        snapshot_manifest_path=None,
        sample_file=sample_file,
        sample_size=5,
        gemini_api_key="fake-api-key",
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_model="gemini-2.0-flash-lite",
        gemini_concurrency=1,
        output_path=tmp_path / "report.json",
    )

    assert report["summary"]["feedback_rejection_count"] == 5
    assert report["decision"] != module.DECISION_READY


def test_doctrine_selection_field_rejection_blocks_ready_decision(tmp_path: Path) -> None:
    module = _load_script_module()
    sample_file = _make_sample_json(tmp_path, 5)

    def _mock(item, *, api_key, model_name):
        r = _make_valid_result(media_id=item["media_id"])
        r["selection_field_rejection"] = True  # model injected forbidden selection field
        return r

    module._run_single_item = _mock

    report = module.run_live_mini_audit(
        snapshot_id=None,
        snapshot_root=tmp_path,
        snapshot_manifest_path=None,
        sample_file=sample_file,
        sample_size=5,
        gemini_api_key="fake-api-key",
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_model="gemini-2.0-flash-lite",
        gemini_concurrency=1,
        output_path=tmp_path / "report.json",
    )

    assert report["summary"]["selection_field_rejection_count"] == 5
    assert report["decision"] != module.DECISION_READY


# ---------------------------------------------------------------------------
# Sprint 4: Deeper diagnostics tests
# ---------------------------------------------------------------------------


def test_per_item_schema_errors_includes_enum_mismatch_details() -> None:
    enum_error = {
        "path": "technical_profile.framing",
        "message": "'excellent' is not one of ['good', 'acceptable', 'poor', 'unknown']",
        "validator": "enum",
        "expected": ["good", "acceptable", "poor", "unknown"],
        "actual": "excellent",
        "cause": "enum_mismatch",
    }
    result = _make_failed_result("m1", schema_errors=[enum_error])

    errors = result.get("schema_errors") or []
    assert len(errors) == 1
    assert errors[0]["path"] == "technical_profile.framing"
    assert errors[0]["actual"] == "excellent"
    assert "expected" in errors[0]
    assert "good" in errors[0]["expected"]
    assert errors[0]["cause"] == "enum_mismatch"


def test_per_item_schema_errors_includes_missing_required_field() -> None:
    missing_field_error = {
        "path": "group_specific_profile.bird",
        "message": "group_specific_profile.bird is required when organism_group is bird",
        "validator": "consistency_rule",
        "expected": "object",
        "actual": None,
        "cause": "missing_required_field",
    }
    result = _make_failed_result("m2", schema_errors=[missing_field_error])

    errors = result.get("schema_errors") or []
    assert len(errors) == 1
    assert errors[0]["path"] == "group_specific_profile.bird"
    assert errors[0]["cause"] == "missing_required_field"
    assert "message" in errors[0]


def test_compute_top_schema_error_paths_aggregates_correctly() -> None:
    module = _load_script_module()

    results = [
        _make_failed_result("m1", schema_errors=[
            {"path": "technical_profile.framing", "cause": "enum_mismatch",
             "message": "bad framing", "validator": "enum", "expected": [], "actual": "x"},
            {"path": "observation_profile.view_angle", "cause": "enum_mismatch",
             "message": "bad view", "validator": "enum", "expected": [], "actual": "y"},
        ]),
        _make_failed_result("m2", schema_errors=[
            {"path": "technical_profile.framing", "cause": "enum_mismatch",
             "message": "bad framing", "validator": "enum", "expected": [], "actual": "z"},
        ]),
        _make_valid_result("m3"),
    ]

    top_paths = module._compute_top_schema_error_paths(results)

    assert isinstance(top_paths, list)
    assert len(top_paths) >= 1
    # technical_profile.framing appears 2x, should be first
    assert top_paths[0]["path"] == "technical_profile.framing"
    assert top_paths[0]["count"] == 2
    # view_angle appears 1x
    view_angle_entry = next(
        (e for e in top_paths if e["path"] == "observation_profile.view_angle"), None
    )
    assert view_angle_entry is not None
    assert view_angle_entry["count"] == 1


def test_compute_top_schema_error_paths_empty_when_no_errors() -> None:
    module = _load_script_module()

    results = [_make_valid_result(f"m{i}") for i in range(3)]
    top_paths = module._compute_top_schema_error_paths(results)

    assert top_paths == []


def test_compute_examples_by_schema_error_path_groups_by_path() -> None:
    module = _load_script_module()

    results = [
        _make_failed_result("m1", schema_errors=[
            {"path": "technical_profile.framing", "cause": "enum_mismatch",
             "message": "bad", "validator": "enum",
             "expected": ["good", "acceptable"], "actual": "excellent"},
        ]),
        _make_failed_result("m2", schema_errors=[
            {"path": "technical_profile.framing", "cause": "enum_mismatch",
             "message": "bad", "validator": "enum",
             "expected": ["good", "acceptable"], "actual": "well_composed"},
        ]),
    ]

    examples = module._compute_examples_by_schema_error_path(results)

    assert "technical_profile.framing" in examples
    framing_examples = examples["technical_profile.framing"]
    assert len(framing_examples) <= 2
    assert all("actual" in ex for ex in framing_examples)
    assert all("expected" in ex for ex in framing_examples)


def test_compute_examples_by_failure_cause_groups_by_cause() -> None:
    module = _load_script_module()

    results = [
        _make_failed_result("m1", schema_errors=[
            {"path": "technical_profile.framing", "cause": "enum_mismatch",
             "message": "bad", "validator": "enum",
             "expected": ["good"], "actual": "excellent"},
        ]),
        _make_failed_result("m2", schema_errors=[
            {"path": "group_specific_profile.bird", "cause": "missing_required_field",
             "message": "required", "validator": "required",
             "expected": ["bird"], "actual": None},
        ]),
    ]

    examples = module._compute_examples_by_failure_cause(results)

    assert "enum_mismatch" in examples
    assert "missing_required_field" in examples
    assert all("path" in ex for ex in examples["enum_mismatch"])
    assert all("path" in ex for ex in examples["missing_required_field"])


def test_summary_includes_top_schema_error_paths() -> None:
    module = _load_script_module()

    results = [
        _make_failed_result("m1"),
        _make_failed_result("m2"),
        _make_valid_result("m3"),
    ]

    summary = module._compute_summary(
        results,
        sample_size=3,
        model="gemini-2.5-flash-lite",
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_concurrency=1,
    )

    assert "top_schema_error_paths" in summary
    assert "examples_by_schema_error_path" in summary
    assert "examples_by_failure_cause" in summary
    assert isinstance(summary["top_schema_error_paths"], list)
    assert isinstance(summary["examples_by_schema_error_path"], dict)
    assert isinstance(summary["examples_by_failure_cause"], dict)


def test_top_schema_error_paths_is_deterministic() -> None:
    module = _load_script_module()

    results = [
        _make_failed_result("m1", schema_errors=[
            {"path": "technical_profile.framing", "cause": "enum_mismatch",
             "message": "bad", "validator": "enum", "expected": [], "actual": "x"},
            {"path": "observation_profile.view_angle", "cause": "enum_mismatch",
             "message": "bad", "validator": "enum", "expected": [], "actual": "y"},
        ]),
    ]

    top1 = module._compute_top_schema_error_paths(results)
    top2 = module._compute_top_schema_error_paths(results)

    assert top1 == top2


def test_skipped_summary_includes_diagnostic_fields(tmp_path: Path) -> None:
    module = _load_script_module()

    report = module.run_live_mini_audit(
        snapshot_id=None,
        snapshot_root=tmp_path,
        snapshot_manifest_path=None,
        sample_file=None,
        sample_size=5,
        gemini_api_key=None,
        gemini_api_key_env="GEMINI_API_KEY",
        gemini_model="gemini-2.5-flash-lite",
        gemini_concurrency=1,
        output_path=tmp_path / "report.json",
    )

    summary = report["summary"]
    assert "top_schema_error_paths" in summary
    assert summary["top_schema_error_paths"] == []
    assert "examples_by_schema_error_path" in summary
    assert summary["examples_by_schema_error_path"] == {}
    assert "examples_by_failure_cause" in summary
    assert summary["examples_by_failure_cause"] == {}
