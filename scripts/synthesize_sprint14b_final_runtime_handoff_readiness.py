from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

PLAN_PATH = REPO_ROOT / "docs" / "audits" / "evidence" / "localized_name_apply_plan_v1.json"
AUDIT_PATH = REPO_ROOT / "docs" / "audits" / "evidence" / "database_integrity_runtime_handoff_audit.json"
RECON_PATH = (
    REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "localized_name_projection_vs_14b_audit_reconciliation.json"
)
DISTRACTOR_PATH = REPO_ROOT / "docs" / "audits" / "evidence" / "distractor_readiness_v1_sprint13.json"
PMP_PATH = (
    REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "pmp_policy_v1_broader_400_20260504_snapshot_audit.json"
)
DISTRACTOR_DELTA_PATH = (
    REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "distractor_readiness_sprint12_vs_sprint13.json"
)

OUT_JSON = (
    REPO_ROOT / "docs" / "audits" / "evidence" / "sprint14b_final_runtime_handoff_readiness.json"
)
OUT_MD = REPO_ROOT / "docs" / "audits" / "sprint14b-final-runtime-handoff-readiness.md"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required artifact: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Artifact must be a JSON object: {path}")
    return payload


def _plan_safe_ready_targets(plan: dict[str, Any]) -> list[str]:
    metrics = plan.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError("localized_name_apply_plan_v1.json must contain metrics")
    safe_targets = metrics.get("safe_ready_targets_from_plan")
    if not isinstance(safe_targets, list):
        raise ValueError("safe_ready_targets_from_plan must be a list")
    normalized = [str(item).strip() for item in safe_targets if str(item).strip()]
    if len(normalized) != len(set(normalized)):
        raise ValueError("safe_ready_targets_from_plan contains duplicates")
    return sorted(normalized)


def build_synthesis() -> dict[str, Any]:
    plan = _load_json(PLAN_PATH)
    audit = _load_json(AUDIT_PATH)
    recon = _load_json(RECON_PATH)
    distractor = _load_json(DISTRACTOR_PATH)
    pmp = _load_json(PMP_PATH)
    distractor_delta = _load_json(DISTRACTOR_DELTA_PATH)

    plan_hash = str(plan.get("plan_hash") or "").strip()
    if not plan_hash:
        raise ValueError("localized_name_apply_plan_v1.json missing plan_hash")

    safe_ready_targets = _plan_safe_ready_targets(plan)
    observed_safe_target_count = len(safe_ready_targets)
    if observed_safe_target_count < 30:
        raise ValueError(
            f"Contract failed: observed_safe_target_count={observed_safe_target_count} < 30"
        )

    audit_hash = str(audit.get("plan_hash") or "").strip()
    recon_hash = str(recon.get("plan_hash") or "").strip()
    if not audit_hash or not recon_hash:
        raise ValueError("Audit/reconciliation artifacts must include plan_hash")
    if len({plan_hash, audit_hash, recon_hash}) != 1:
        raise ValueError(
            "Plan hash divergence across plan/audit/reconciliation: "
            f"plan={plan_hash} audit={audit_hash} reconciliation={recon_hash}"
        )

    emergency_fallback_count = (
        distractor_delta.get("metrics", {}).get("emergency_fallback_count", {}).get("sprint13")
    )
    if emergency_fallback_count is None:
        raise ValueError("Missing emergency_fallback_count.sprint13 in distractor delta artifact")
    if int(emergency_fallback_count) != 0:
        raise ValueError(f"Contract failed: emergency_fallback_count={emergency_fallback_count} != 0")

    payload = {
        "schema_version": "sprint14b_final_runtime_handoff_readiness_v1",
        "run_date": "2026-05-05",
        "decision": "READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS",
        "names_gate": {
            "status": "pass_with_warnings",
            "plan_hash": plan_hash,
            "observed_safe_target_count": observed_safe_target_count,
            "contractual_minimum": 30,
            "safe_target_source": "localized_name_apply_plan_v1.json",
        },
        "distractor_integrity": {
            "status": distractor.get("decision", "unknown"),
            "source": str(DISTRACTOR_PATH.relative_to(REPO_ROOT)),
            "targets_ready": distractor.get("summary", {}).get("targets_ready"),
            "targets_blocked": distractor.get("summary", {}).get("targets_blocked"),
        },
        "pmp_policy": {
            "status": pmp.get("decision", "unknown"),
            "source": str(PMP_PATH.relative_to(REPO_ROOT)),
            "doctrine_pollution_detected": pmp.get("doctrine_pollution_checks", {}).get(
                "doctrine_pollution_detected"
            ),
        },
        "cross_artifact_invariants": {
            "plan_hash_match": True,
            "emergency_fallback_count": int(emergency_fallback_count),
            "safe_target_count_threshold_pass": True,
        },
        "sources": {
            "localized_name_apply_plan": str(PLAN_PATH.relative_to(REPO_ROOT)),
            "runtime_handoff_audit": str(AUDIT_PATH.relative_to(REPO_ROOT)),
            "localized_name_reconciliation": str(RECON_PATH.relative_to(REPO_ROOT)),
            "distractor_readiness": str(DISTRACTOR_PATH.relative_to(REPO_ROOT)),
            "pmp_policy": str(PMP_PATH.relative_to(REPO_ROOT)),
            "distractor_delta": str(DISTRACTOR_DELTA_PATH.relative_to(REPO_ROOT)),
        },
    }
    return payload


def write_outputs(payload: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        "last_reviewed: 2026-05-05",
        "source_of_truth: docs/audits/sprint14b-final-runtime-handoff-readiness.md",
        "scope: sprint14b_final_synthesis",
        "---",
        "",
        "# Sprint 14B Final Runtime Handoff Readiness",
        "",
        f"- decision: {payload['decision']}",
        f"- plan_hash: {payload['names_gate']['plan_hash']}",
        f"- observed_safe_target_count: {payload['names_gate']['observed_safe_target_count']}",
        f"- contractual_minimum: {payload['names_gate']['contractual_minimum']}",
        f"- emergency_fallback_count: {payload['cross_artifact_invariants']['emergency_fallback_count']}",
        "",
        "## Gates",
        "",
        f"- names_gate: {payload['names_gate']['status']}",
        f"- distractor_integrity: {payload['distractor_integrity']['status']}",
        f"- pmp_policy: {payload['pmp_policy']['status']}",
        "",
        "## Final Decision",
        "",
        "- READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS",
    ]
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    payload = build_synthesis()
    write_outputs(payload)
    print(f"Decision: {payload['decision']}")
    print(f"Observed safe targets: {payload['names_gate']['observed_safe_target_count']}")
    print(f"Plan hash: {payload['names_gate']['plan_hash']}")


if __name__ == "__main__":
    main()
