from __future__ import annotations

import json
from pathlib import Path

from scripts import plan_golden_pack_v1_targeted_media_uplift as plan


def test_targeted_media_uplift_plan_shape_and_safety(tmp_path: Path) -> None:
    payload = plan.build_targeted_media_uplift_plan()
    out = plan.write_plan(payload, output_path=tmp_path / "targeted_media_uplift_plan.json")

    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))

    for key in ("summary", "target_media_matrix", "pmp_refresh_batch", "non_actions"):
        assert key in data

    # Planning phase must never emit runtime pack artifacts.
    assert not (tmp_path / "pack.json").exists()

    # Borderline must never be treated as eligible.
    for item in data["pmp_refresh_batch"]:
        if item.get("is_borderline") is True:
            assert item.get("is_basic_identification_eligible") is False

    flags = data.get("flags", {})
    assert flags.get("DATABASE_PHASE_CLOSED") is False
    assert flags.get("PERSIST_DISTRACTOR_RELATIONSHIPS_V1") is False

