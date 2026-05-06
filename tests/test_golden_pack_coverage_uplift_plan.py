from __future__ import annotations

import json
from pathlib import Path

from scripts import plan_golden_pack_v1_coverage_uplift as plan


def test_coverage_uplift_plan_shape_and_guards(tmp_path: Path) -> None:
    payload = plan.build_coverage_uplift_plan()
    out = plan.write_plan(payload, output_path=tmp_path / "coverage_uplift_plan.json")

    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))

    for key in (
        "summary",
        "target_matrix",
        "unlock_simulation",
        "media_uplift_plan",
        "distractor_uplift_plan",
        "localized_name_uplift_plan",
        "minimal_path_to_30",
    ):
        assert key in data

    sim = data["unlock_simulation"]
    assert sim["current_ready_count"] <= sim["ready_count_if_media_fixed_only"]
    assert sim["current_ready_count"] <= sim["ready_count_if_distractors_fixed_only"]
    assert sim["current_ready_count"] <= sim["ready_count_if_labels_fixed_only"]

    # Non-naive overlap handling: all-known must be <= safe_ready_targets, and
    # not lower than any partial combination.
    safe_count = data["summary"]["safe_ready_targets"]
    assert sim["ready_count_if_all_known_issues_fixed"] <= safe_count
    assert sim["ready_count_if_all_known_issues_fixed"] >= sim["ready_count_if_media_plus_distractors_fixed"]
    assert sim["ready_count_if_all_known_issues_fixed"] >= sim["ready_count_if_media_plus_labels_fixed"]
    assert sim["ready_count_if_all_known_issues_fixed"] >= sim["ready_count_if_distractors_plus_labels_fixed"]

    # This planning script must not write runtime pack artifacts.
    assert not (tmp_path / "pack.json").exists()

    flags = data.get("flags", {})
    assert flags.get("DATABASE_PHASE_CLOSED") is False
    assert flags.get("PERSIST_DISTRACTOR_RELATIONSHIPS_V1") is False

