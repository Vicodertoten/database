from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_script_module():
    script_path = Path("scripts/audit_bird_image_review_v12_dry_run.py")
    spec = importlib.util.spec_from_file_location(
        "audit_bird_image_review_v12_dry_run",
        script_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load dry-run audit script module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_v12_dry_run_audit_reports_expected_metrics() -> None:
    module = _load_script_module()
    report = module.run_dry_run_audit()

    assert report["schema_version"] == "bird_image_review_v12_dry_run_audit.v1"
    assert report["candidate_images_reviewed"] == 4
    assert report["successful_v12_reviews"] == 1
    assert report["failed_v12_reviews"] == 3
    assert report["average_pedagogical_score"] > 0
    assert report["feedback_completeness_rate"] == 1.0
    assert report["failure_reasons"]["schema_validation_failed"] == 1
    assert report["failure_reasons"]["model_output_invalid"] == 1
    assert report["failure_reasons"]["image_too_blurry"] == 1
