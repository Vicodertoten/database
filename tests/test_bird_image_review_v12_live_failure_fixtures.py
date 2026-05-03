from __future__ import annotations

import json
from pathlib import Path


def test_live_failure_fixture_contains_actionable_schema_diagnostics() -> None:
    fixture_path = Path(
        "tests/fixtures/bird_image_review_v12_live_failures_run003_sample5.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert payload["fixture_version"] == "bird_image_review_v12_live_failures.v1"

    items = payload["items"]
    assert isinstance(items, list)
    assert items

    for item in items:
        diagnostics = item.get("schema_diagnostics") or {}
        assert diagnostics.get("parsed_json_available") is True
        assert diagnostics.get("raw_model_output_sha256")
        assert diagnostics.get("raw_model_output_excerpt")
        assert diagnostics.get("prompt_version") == "bird_image_review_prompt.v1.2"
        assert diagnostics.get("schema_version") == "bird_image_pedagogical_review.v1.2"
        assert diagnostics.get("media_id")
        assert diagnostics.get("scientific_name")


def test_live_failure_fixture_cause_distribution_matches_expected() -> None:
    fixture_path = Path(
        "tests/fixtures/bird_image_review_v12_live_failures_run003_sample5.json"
    )
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    items = payload["items"]
    causes = [
        str((item.get("schema_diagnostics") or {}).get("schema_failure_cause"))
        for item in items
    ]
    assert "malformed_success_failed_shape" in causes
    assert "missing_feedback" in causes
