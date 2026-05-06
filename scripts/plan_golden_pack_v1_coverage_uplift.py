from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import materialize_golden_pack_belgian_birds_mvp_v1 as mat

LOCAL_CANONICAL_RUNS_ROOT = (
    REPO_ROOT / "data" / "intermediate" / "golden_pack" / "belgian_birds_mvp_v1" / "local_canonical_run"
)
OUTPUT_PATH = REPO_ROOT / "data" / "intermediate" / "golden_pack" / "belgian_birds_mvp_v1" / "coverage_uplift_plan.json"

FLAGS = {
    "DATABASE_PHASE_CLOSED": False,
    "PERSIST_DISTRACTOR_RELATIONSHIPS_V1": False,
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_candidate_readiness_path() -> Path:
    if not LOCAL_CANONICAL_RUNS_ROOT.exists():
        raise FileNotFoundError(f"Missing run directory root: {LOCAL_CANONICAL_RUNS_ROOT}")
    run_dirs = [p for p in LOCAL_CANONICAL_RUNS_ROOT.iterdir() if p.is_dir()]
    if not run_dirs:
        raise FileNotFoundError(f"No local canonical runs found in: {LOCAL_CANONICAL_RUNS_ROOT}")
    latest = sorted(run_dirs, key=lambda p: p.name)[-1]
    path = latest / "candidate_readiness.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing candidate_readiness.json in latest run: {latest}")
    return path


def _reason_set(target: dict[str, Any]) -> set[str]:
    return {str(x) for x in target.get("rejection_reasons", [])}


def _normalize_reasons_for_plan(target: dict[str, Any]) -> set[str]:
    raw = _reason_set(target)
    out: set[str] = set()
    if "missing_fr_runtime_safe_label" in raw:
        out.add("missing_fr_runtime_safe_label")
    if "insufficient_label_safe_distractors" in raw:
        out.add("insufficient_label_safe_distractors")
    if "no_basic_identification_eligible_media" in raw:
        out.add("no_basic_identification_eligible_media")
    if "no_local_media_file" in raw:
        out.add("no_local_media_file")
    if "no_pmp_profile" in raw:
        out.add("no_pmp_profile")
    return out


def _missing_requirements(target: dict[str, Any], reasons: set[str]) -> list[str]:
    missing: list[str] = []
    if not target.get("display_label_fr"):
        missing.append("fr_runtime_safe_label")
    if int(target.get("basic_identification_eligible_media_count", 0)) < 1:
        missing.append("eligible_primary_media")
    if int(target.get("distractor_label_safe_count", 0)) < 3:
        missing.append("3_label_safe_distractors")
    for reason in sorted(reasons):
        if reason not in {"missing_fr_runtime_safe_label", "insufficient_label_safe_distractors", "no_basic_identification_eligible_media"}:
            missing.append(f"diagnose:{reason}")
    return missing


def _minimal_unlock_actions(target: dict[str, Any], reasons: set[str]) -> list[str]:
    actions: list[str] = []
    if "no_pmp_profile" in reasons:
        actions.append("rerun_or_materialize_pmp_profile_for_source_media")
    if "no_local_media_file" in reasons:
        actions.append("add_or_materialize_local_media")
    if "no_basic_identification_eligible_media" in reasons:
        actions.append("rerun_pmp_policy_on_existing_media")
        actions.append("inspect_policy_rejection_reasons")
    if "insufficient_label_safe_distractors" in reasons:
        actions.append("rerun_distractor_projection_against_current_name_policy")
    if "missing_fr_runtime_safe_label" in reasons:
        actions.append("rerun_localized_name_resolver")
    return actions


def _classification_buckets(target: dict[str, Any], reasons: set[str]) -> tuple[str | None, str | None, str | None]:
    media_reason: str | None = None
    if "no_pmp_profile" in reasons:
        media_reason = "no_pmp_profile"
    elif "no_local_media_file" in reasons:
        media_reason = "no_local_media_file"
    elif "no_basic_identification_eligible_media" in reasons:
        if int(target.get("pmp_policy_projection_count", 0)) > 0:
            media_reason = "policy_projection_exists_but_not_eligible"
        else:
            media_reason = "no_basic_identification_eligible_media"

    distractor_reason: str | None = None
    if "insufficient_label_safe_distractors" in reasons:
        if int(target.get("distractor_candidates_total", 0)) <= int(target.get("distractor_label_safe_count", 0)):
            distractor_reason = "referenced_taxon_missing_runtime_safe_label"
        else:
            distractor_reason = "insufficient_label_safe_distractors"

    label_reason: str | None = None
    if "missing_fr_runtime_safe_label" in reasons:
        label_reason = "missing_fr_runtime_safe_label"

    return media_reason, distractor_reason, label_reason


def _simulate_ready_count(targets: list[dict[str, Any]], fix_media: bool, fix_distractors: bool, fix_labels: bool) -> int:
    ready = 0
    for t in targets:
        reasons = _normalize_reasons_for_plan(t)
        unresolved = set(reasons)
        if fix_media:
            unresolved -= {"no_basic_identification_eligible_media", "no_local_media_file", "no_pmp_profile"}
        if fix_distractors:
            unresolved -= {"insufficient_label_safe_distractors"}
        if fix_labels:
            unresolved -= {"missing_fr_runtime_safe_label"}
        if len(unresolved) == 0:
            ready += 1
    return ready


def build_coverage_uplift_plan() -> dict[str, Any]:
    candidate_path = _latest_candidate_readiness_path()
    candidate_payload = _load_json(candidate_path)
    targets = list(candidate_payload.get("targets", []))
    if not isinstance(targets, list):
        raise ValueError("Invalid candidate_readiness format: targets must be a list")

    # Inputs read for lineage/context anchoring for this planning phase.
    # These are intentionally not written to runtime artifacts.
    _ = _load_json(mat.PLAN_PATH)
    _ = _load_json(mat.DISTRACTOR_PATH)
    _ = _load_json(mat.QUALIFIED_EXPORT_PATH)
    _ = _load_json(mat.INAT_AI_OUTPUTS_PATH)

    safe_ready_targets = int(candidate_payload.get("summary", {}).get("safe_ready_targets", len(targets)))
    current_ready_targets = sum(1 for t in targets if bool(t.get("golden_pack_ready")))
    required_ready_targets = 30
    readiness_gap = max(0, required_ready_targets - current_ready_targets)

    reason_counts: Counter[str] = Counter()
    overlapping_reason_counts: Counter[str] = Counter()

    target_matrix: list[dict[str, Any]] = []
    media_uplift_plan: list[dict[str, Any]] = []
    distractor_uplift_plan: list[dict[str, Any]] = []
    localized_name_uplift_plan: list[dict[str, Any]] = []

    for t in sorted(targets, key=lambda x: str(x.get("taxon_ref") or "")):
        reasons = _normalize_reasons_for_plan(t)
        for r in reasons:
            reason_counts[r] += 1
        if len(reasons) > 1:
            key = "+".join(sorted(reasons))
            overlapping_reason_counts[key] += 1

        missing = _missing_requirements(t, reasons)
        actions = _minimal_unlock_actions(t, reasons)
        media_reason, distractor_reason, label_reason = _classification_buckets(t, reasons)

        target_matrix.append(
            {
                "taxon_ref": t.get("taxon_ref"),
                "scientific_name": t.get("scientific_name"),
                "display_label_fr": t.get("display_label_fr"),
                "currently_golden_pack_ready": bool(t.get("golden_pack_ready")),
                "rejection_reasons": sorted(reasons),
                "has_fr_runtime_safe_label": bool(t.get("display_label_fr")),
                "eligible_media_count": int(t.get("basic_identification_eligible_media_count", 0)),
                "local_media_count": int(t.get("local_media_count", 0)),
                "pmp_profile_count": int(t.get("pmp_profile_count", 0)),
                "policy_projection_count": int(t.get("pmp_policy_projection_count", 0)),
                "label_safe_distractor_count": int(t.get("distractor_label_safe_count", 0)),
                "missing_requirements": missing,
                "minimal_unlock_actions": actions,
            }
        )

        if media_reason:
            if media_reason == "no_pmp_profile":
                media_action = "add_or_materialize_local_media"
                priority = "high"
            elif media_reason == "no_local_media_file":
                media_action = "add_or_materialize_local_media"
                priority = "high"
            elif media_reason == "policy_projection_exists_but_not_eligible":
                media_action = "inspect_policy_rejection_reasons"
                priority = "high"
            else:
                media_action = "rerun_pmp_policy_on_existing_media"
                priority = "medium"
            media_uplift_plan.append(
                {
                    "taxon_ref": t.get("taxon_ref"),
                    "current_local_media_count": int(t.get("local_media_count", 0)),
                    "current_pmp_profile_count": int(t.get("pmp_profile_count", 0)),
                    "current_eligible_media_count": int(t.get("basic_identification_eligible_media_count", 0)),
                    "current_best_media_candidates": [t.get("selected_primary_media_candidate")] if t.get("selected_primary_media_candidate") else [],
                    "reason": media_reason,
                    "recommended_action": media_action,
                    "priority": priority,
                    "expected_unlock_impact": 1,
                }
            )

        if distractor_reason:
            if distractor_reason == "referenced_taxon_missing_runtime_safe_label":
                d_action = "enrich_referenced_taxon_labels"
                d_reason = "referenced_taxon_missing_runtime_safe_label"
            else:
                d_action = "rerun_distractor_projection_against_current_name_policy"
                d_reason = "insufficient_label_safe_distractors"
            distractor_uplift_plan.append(
                {
                    "taxon_ref": t.get("taxon_ref"),
                    "current_label_safe_distractor_count": int(t.get("distractor_label_safe_count", 0)),
                    "candidates_total": int(t.get("distractor_candidates_total", 0)),
                    "rejected_candidates_count": max(
                        0,
                        int(t.get("distractor_candidates_total", 0)) - int(t.get("distractor_label_safe_count", 0)),
                    ),
                    "reason": d_reason,
                    "recommended_action": d_action,
                    "priority": "high",
                    "expected_unlock_impact": 1,
                }
            )

        if label_reason:
            localized_name_uplift_plan.append(
                {
                    "taxon_ref": t.get("taxon_ref"),
                    "current_label_state": "missing_fr_runtime_safe_label",
                    "source_candidates": [],
                    "recommended_action": "rerun_localized_name_resolver",
                    "priority": "high",
                    "expected_unlock_impact": 1,
                }
            )

    unlock_simulation = {
        "current_ready_count": _simulate_ready_count(targets, fix_media=False, fix_distractors=False, fix_labels=False),
        "ready_count_if_media_fixed_only": _simulate_ready_count(targets, fix_media=True, fix_distractors=False, fix_labels=False),
        "ready_count_if_distractors_fixed_only": _simulate_ready_count(targets, fix_media=False, fix_distractors=True, fix_labels=False),
        "ready_count_if_labels_fixed_only": _simulate_ready_count(targets, fix_media=False, fix_distractors=False, fix_labels=True),
        "ready_count_if_media_plus_distractors_fixed": _simulate_ready_count(targets, fix_media=True, fix_distractors=True, fix_labels=False),
        "ready_count_if_media_plus_labels_fixed": _simulate_ready_count(targets, fix_media=True, fix_distractors=False, fix_labels=True),
        "ready_count_if_distractors_plus_labels_fixed": _simulate_ready_count(targets, fix_media=False, fix_distractors=True, fix_labels=True),
        "ready_count_if_all_known_issues_fixed": _simulate_ready_count(targets, fix_media=True, fix_distractors=True, fix_labels=True),
    }

    path_steps = [
        {
            "step": 1,
            "action": "targeted_media_policy_uplift",
            "expected_ready_count_after_step": unlock_simulation["ready_count_if_media_fixed_only"],
            "remaining_blockers": [
                "insufficient_label_safe_distractors",
                "missing_fr_runtime_safe_label",
            ],
        },
        {
            "step": 2,
            "action": "targeted_distractor_label_safe_uplift",
            "expected_ready_count_after_step": unlock_simulation["ready_count_if_media_plus_distractors_fixed"],
            "remaining_blockers": [
                "missing_fr_runtime_safe_label",
            ],
        },
        {
            "step": 3,
            "action": "targeted_localized_name_fr_uplift",
            "expected_ready_count_after_step": unlock_simulation["ready_count_if_all_known_issues_fixed"],
            "remaining_blockers": [],
        },
    ]

    recommended_strategy = "TARGETED_PMP_POLICY_PLUS_DISTRACTOR_PLUS_LOCALIZED_NAME_UPLIFT"
    if unlock_simulation["ready_count_if_all_known_issues_fixed"] < required_ready_targets:
        recommended_strategy = "TARGETED_UPLIFT_PLUS_MANUAL_DATA_REVIEW_REQUIRED"

    payload = {
        "schema_version": "golden_pack_v1_coverage_uplift_plan.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_candidate_readiness_path": str(candidate_path.relative_to(REPO_ROOT)),
        "flags": FLAGS,
        "summary": {
            "safe_ready_targets": safe_ready_targets,
            "current_ready_targets": current_ready_targets,
            "required_ready_targets": required_ready_targets,
            "readiness_gap": readiness_gap,
            "reason_counts": dict(sorted(reason_counts.items())),
            "overlapping_reason_counts": dict(sorted(overlapping_reason_counts.items())),
            "recommended_strategy": recommended_strategy,
        },
        "target_matrix": target_matrix,
        "unlock_simulation": unlock_simulation,
        "media_uplift_plan": sorted(media_uplift_plan, key=lambda x: (x["priority"], x["taxon_ref"])),
        "distractor_uplift_plan": sorted(distractor_uplift_plan, key=lambda x: (x["priority"], x["taxon_ref"])),
        "localized_name_uplift_plan": sorted(localized_name_uplift_plan, key=lambda x: (x["priority"], x["taxon_ref"])),
        "minimal_path_to_30": path_steps,
        "non_actions": [
            "no_borderline_media_as_primary_quiz_image",
            "no_emergency_fallback_distractors",
            "no_runtime_generated_names",
            "no_runtime_selected_distractors",
            "no_distractorrelationship_persistence",
            "no_database_closure_yet",
        ],
    }
    return payload


def write_plan(payload: dict[str, Any], output_path: Path = OUTPUT_PATH) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def main() -> None:
    payload = build_coverage_uplift_plan()
    out = write_plan(payload)
    print(f"output={out}")
    print(f"current_ready_count={payload['unlock_simulation']['current_ready_count']}")
    print(f"ready_count_if_all_known_issues_fixed={payload['unlock_simulation']['ready_count_if_all_known_issues_fixed']}")


if __name__ == "__main__":
    main()

