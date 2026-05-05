from __future__ import annotations

from pathlib import Path

from scripts.reconcile_localized_name_projection_vs_14b_audit import reconcile


def test_reconcile_uses_single_apply_plan_engine() -> None:
    out = reconcile()
    assert out["reconciliation_summary"]["single_decision_engine_used"] is True
    assert (
        out["projected_safe_targets_dry_run_count"] == out["audited_safe_targets_after_apply_count"]
    )


def test_reconcile_script_has_no_legacy_failure_classifier() -> None:
    source = Path("scripts/reconcile_localized_name_projection_vs_14b_audit.py").read_text(
        encoding="utf-8"
    )
    assert "classify_failure_reason" not in source
    assert "build_status_map" not in source
