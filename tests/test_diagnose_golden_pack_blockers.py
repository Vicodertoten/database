from __future__ import annotations

from scripts.diagnose_golden_pack_belgian_birds_mvp_v1_blockers import build_diagnosis


def test_diagnosis_has_expected_structure() -> None:
    payload = build_diagnosis()
    assert "summary" in payload
    assert "targets" in payload
    assert "rejection_reason_counts" in payload
    assert isinstance(payload["targets"], list)
    assert isinstance(payload["rejection_reason_counts"], dict)
    assert payload["summary"]["safe_ready_targets"] >= payload["summary"]["selected_targets"]
