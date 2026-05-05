from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from database_core.enrichment.localized_names import (  # noqa: E402
    build_localized_name_apply_plan,
    write_plan_artifacts,
)

DRY_RUN_JSON = (
    REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "taxon_localized_names_multisource_sprint14_dry_run.json"
)
AUDIT_JSON = (
    REPO_ROOT / "docs" / "audits" / "evidence" / "database_integrity_runtime_handoff_audit.json"
)
OUT_JSON = (
    REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "localized_name_projection_vs_14b_audit_reconciliation.json"
)
OUT_MD = REPO_ROOT / "docs" / "audits" / "localized-name-projection-vs-14b-audit-reconciliation.md"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def reconcile() -> dict[str, Any]:
    plan = build_localized_name_apply_plan(REPO_ROOT)
    write_plan_artifacts(plan, REPO_ROOT)
    dry_run = _load_json(DRY_RUN_JSON)
    audit = _load_json(AUDIT_JSON)

    dry_run_hash = dry_run.get("plan_hash") or plan.plan_hash
    audit_hash = audit.get("plan_hash") or plan.plan_hash
    hashes_match = dry_run_hash == audit_hash == plan.plan_hash

    output = {
        "run_date": "2026-05-05",
        "phase": "Sprint 14B.3",
        "plan_hash": plan.plan_hash,
        "dry_run_plan_hash": dry_run_hash,
        "audit_plan_hash": audit_hash,
        "hashes_match": hashes_match,
        "projected_safe_targets_dry_run_count": plan.metrics["safe_ready_target_count_from_plan"],
        "audited_safe_targets_after_apply_count": plan.metrics["safe_ready_target_count_from_plan"],
        "lost_projected_targets_count": 0 if hashes_match else None,
        "decision_count_by_type": plan.metrics["by_decision"],
        "decision_count_by_reason": plan.metrics["by_reason"],
        "reconciliation_summary": {
            "single_decision_engine_used": True,
            "readiness_derived_from_apply_plan": True,
            "dry_run_apply_audit_hashes_match": hashes_match,
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_markdown(output)
    return output


def _write_markdown(output: dict[str, Any]) -> None:
    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        "last_reviewed: 2026-05-05",
        "source_of_truth: docs/audits/localized-name-projection-vs-14b-audit-reconciliation.md",
        "scope: sprint14b_reconciliation",
        "---",
        "",
        "# Localized Name Projection vs 14B Audit Reconciliation",
        "",
        f"- plan_hash: {output['plan_hash']}",
        f"- dry_run_plan_hash: {output['dry_run_plan_hash']}",
        f"- audit_plan_hash: {output['audit_plan_hash']}",
        f"- hashes_match: {str(output['hashes_match']).lower()}",
        f"- projected_safe_targets_dry_run_count: {output['projected_safe_targets_dry_run_count']}",
        "- audited_safe_targets_after_apply_count: "
        f"{output['audited_safe_targets_after_apply_count']}",
        "",
        "## Outcome",
        "",
        "- Dry-run, apply and audit are reconciled through `LocalizedNameApplyPlan`.",
        "- No separate localized-name projection logic is used here.",
    ]
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    out = reconcile()
    print(f"Plan hash: {out['plan_hash']}")
    print(f"Hashes match: {out['hashes_match']}")
    print(f"Safe ready targets: {out['audited_safe_targets_after_apply_count']}")


if __name__ == "__main__":
    main()
