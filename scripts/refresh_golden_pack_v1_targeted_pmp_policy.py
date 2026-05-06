from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import materialize_golden_pack_belgian_birds_mvp_v1 as mat
from scripts import plan_golden_pack_v1_targeted_media_uplift as uplift

RUNS_ROOT = (
    REPO_ROOT
    / "data"
    / "intermediate"
    / "golden_pack"
    / "belgian_birds_mvp_v1"
    / "targeted_pmp_policy_refresh"
)

FLAGS = {
    "DATABASE_PHASE_CLOSED": False,
    "PERSIST_DISTRACTOR_RELATIONSHIPS_V1": False,
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _policy_eval_for_media_id(ai_outputs: dict[str, Any], media_id: str) -> dict[str, Any]:
    key = f"inaturalist::{media_id}"
    outcome = ai_outputs.get(key)
    if not isinstance(outcome, dict):
        return {
            "has_profile": False,
            "policy_status": "missing_profile",
            "basic_identification_status": "missing",
            "basic_identification_reason": "no_pmp_profile",
            "eligible": False,
            "borderline": False,
        }
    profile = outcome.get("pedagogical_media_profile")
    if not isinstance(profile, dict):
        return {
            "has_profile": False,
            "policy_status": "missing_profile",
            "basic_identification_status": "missing",
            "basic_identification_reason": "missing_pedagogical_media_profile",
            "eligible": False,
            "borderline": False,
        }
    decision = mat.evaluate_pmp_profile_policy(profile)
    usage = decision.get("usage_statuses") if isinstance(decision.get("usage_statuses"), dict) else {}
    basic = usage.get("basic_identification") if isinstance(usage.get("basic_identification"), dict) else {}
    status = str(basic.get("status") or "missing")
    return {
        "has_profile": True,
        "policy_status": str(decision.get("policy_status") or "unknown"),
        "basic_identification_status": status,
        "basic_identification_reason": str(basic.get("reason") or ""),
        "eligible": status == "eligible",
        "borderline": status == "borderline",
    }


def _priority_rank(candidate: dict[str, Any], policy_eval: dict[str, Any]) -> tuple[int, str]:
    has_profile = bool(policy_eval["has_profile"])
    attr_complete = bool(candidate["attribution_complete"])
    if (not has_profile) and attr_complete:
        return (1, "priority_1_unevaluated_with_complete_attribution")
    if (not has_profile) and (not attr_complete):
        return (2, "priority_2_unevaluated_attribution_incomplete")
    if policy_eval["borderline"]:
        return (4, "priority_4_borderline_inspection_only")
    return (3, "priority_3_already_evaluated_non_eligible_inspection")


def _build_candidates(max_per_target: int, max_total: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    plan = _load_json(uplift.OUTPUT_PATH)
    ai_outputs = _load_json(mat.INAT_AI_OUTPUTS_PATH)
    target_rows = {
        str(row.get("taxon_ref") or ""): row
        for row in plan.get("target_media_matrix", [])
        if isinstance(row, dict) and str(row.get("taxon_ref") or "")
    }
    raw_candidates = [row for row in plan.get("pmp_refresh_batch", []) if isinstance(row, dict)]

    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    skip_counts: Counter[str] = Counter()
    per_target_kept: defaultdict[str, int] = defaultdict(int)
    total_kept = 0

    # Sort by provided priority then target/media for determinism.
    priority_order = {"high": 1, "medium": 2, "low": 3}
    raw_sorted = sorted(
        raw_candidates,
        key=lambda c: (
            priority_order.get(str(c.get("priority") or "low"), 9),
            str(c.get("taxon_ref") or ""),
            str(c.get("media_id") or ""),
        ),
    )

    for c in raw_sorted:
        taxon_ref = str(c.get("taxon_ref") or "").strip()
        media_id = str(c.get("media_id") or "").strip()
        local_path = str(c.get("local_path") or "").strip()
        source_url = str(c.get("source_url") or "").strip()
        creator = str(c.get("creator") or "").strip()
        license_name = str(c.get("license") or "").strip()
        license_url = str(c.get("license_url") or "").strip()

        local_exists = bool(local_path) and Path(local_path).exists()
        attribution_complete = bool(source_url and creator and license_name and license_url)

        policy_eval = _policy_eval_for_media_id(ai_outputs, media_id)
        rank, rank_label = _priority_rank(
            {"attribution_complete": attribution_complete},
            policy_eval,
        )

        apply_ready = True
        skip_reasons: list[str] = []
        if not local_exists:
            apply_ready = False
            skip_reasons.append("missing_local_file")
        if not source_url:
            apply_ready = False
            skip_reasons.append("missing_source_url")
        if not creator:
            apply_ready = False
            skip_reasons.append("missing_creator")
        if not license_name:
            apply_ready = False
            skip_reasons.append("missing_license")
        if not license_url:
            apply_ready = False
            skip_reasons.append("missing_license_url")
        if policy_eval["borderline"]:
            apply_ready = False
            skip_reasons.append("borderline_inspection_only")

        candidate = {
            "taxon_ref": taxon_ref,
            "media_id": media_id,
            "local_path": local_path,
            "local_path_exists": local_exists,
            "source_url": source_url,
            "source": str(c.get("source") or "inaturalist"),
            "creator": creator,
            "license": license_name,
            "license_url": license_url,
            "attribution_complete": attribution_complete,
            "priority_rank": rank,
            "priority_label": rank_label,
            "apply_ready": apply_ready,
            "skip_reasons": skip_reasons,
            "policy_eval": policy_eval,
            "reason_for_selection": str(c.get("reason_for_selection") or ""),
        }

        if not apply_ready:
            for reason in skip_reasons:
                skip_counts[reason] += 1
            skipped.append(candidate)
            continue

        if per_target_kept[taxon_ref] >= max_per_target:
            skip_counts["over_max_per_target"] += 1
            skipped.append({**candidate, "apply_ready": False, "skip_reasons": ["over_max_per_target"]})
            continue
        if total_kept >= max_total:
            skip_counts["over_max_total"] += 1
            skipped.append({**candidate, "apply_ready": False, "skip_reasons": ["over_max_total"]})
            continue

        candidates.append(candidate)
        per_target_kept[taxon_ref] += 1
        total_kept += 1

    summary = {
        "total_candidates": len(raw_candidates),
        "targets_covered": len({str(c.get("taxon_ref") or "") for c in raw_candidates}),
        "apply_ready_candidates": len(candidates),
        "skipped_candidates": len(skipped),
        "skip_reason_counts": dict(sorted(skip_counts.items())),
        "targets_with_apply_ready": len({c["taxon_ref"] for c in candidates}),
        "estimation_coverage_by_target": {
            taxon_ref: {
                "available_candidates": sum(1 for x in raw_candidates if str(x.get("taxon_ref") or "") == taxon_ref),
                "apply_ready_selected": per_target_kept[taxon_ref],
            }
            for taxon_ref in sorted(target_rows.keys())
        },
    }
    return candidates, {"summary": summary, "skipped": skipped}


def run_refresh(
    mode: str,
    max_per_target: int = 5,
    max_total: int = 100,
    output_root: Path | None = None,
) -> Path:
    run_id = f"targeted_pmp_policy_refresh_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"
    root = output_root or RUNS_ROOT
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    candidates, prep = _build_candidates(max_per_target=max_per_target, max_total=max_total)
    dry_run_plan = {
        "schema_version": "golden_pack_v1_targeted_pmp_policy_refresh_dry_run.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "flags": FLAGS,
        "max_per_target": max_per_target,
        "max_total": max_total,
        "summary": prep["summary"],
        "apply_ready_batch": candidates,
    }
    (run_dir / "dry_run_plan.json").write_text(json.dumps(dry_run_plan, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "rejected_or_skipped_media.json").write_text(
        json.dumps(
            {
                "schema_version": "golden_pack_v1_targeted_pmp_policy_refresh_skipped.v1",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "flags": FLAGS,
                "skipped": prep["skipped"],
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    manifest = {
        "schema_version": "golden_pack_v1_targeted_pmp_policy_refresh_run_manifest.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "mode": mode,
        "flags": FLAGS,
        "inputs": {
            "targeted_media_uplift_plan": str(uplift.OUTPUT_PATH.relative_to(REPO_ROOT)),
            "ai_outputs": str(mat.INAT_AI_OUTPUTS_PATH.relative_to(REPO_ROOT)),
            "inaturalist_manifest": str(mat.INAT_MANIFEST_PATH.relative_to(REPO_ROOT)),
            "qualified_export": str(mat.QUALIFIED_EXPORT_PATH.relative_to(REPO_ROOT)),
        },
        "non_actions": [
            "no_pack_generation",
            "no_forced_eligibility",
            "no_borderline_eligible",
            "no_runtime_decision",
        ],
    }

    if mode == "dry-run":
        (run_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        return run_dir

    ai_outputs = _load_json(mat.INAT_AI_OUTPUTS_PATH)
    refresh_rows: list[dict[str, Any]] = []
    queue: list[dict[str, Any]] = []
    newly_eligible = 0
    still_not_eligible = 0
    taxon_newly_eligible: set[str] = set()

    for c in candidates:
        media_id = c["media_id"]
        taxon_ref = c["taxon_ref"]
        policy_eval = _policy_eval_for_media_id(ai_outputs, media_id)
        source_profile = "reused" if policy_eval["has_profile"] else "needs_pmp_profile_generation"
        if not policy_eval["has_profile"]:
            queue.append(
                {
                    "taxon_ref": taxon_ref,
                    "media_id": media_id,
                    "local_path": c["local_path"],
                    "source_url": c["source_url"],
                    "reason": "needs_pmp_profile_generation",
                }
            )

        eligible = bool(policy_eval["eligible"])
        borderline = bool(policy_eval["borderline"])
        if eligible:
            newly_eligible += 1
            taxon_newly_eligible.add(taxon_ref)
        else:
            still_not_eligible += 1

        refresh_rows.append(
            {
                "media_id": media_id,
                "taxon_ref": taxon_ref,
                "pmp_status": policy_eval["policy_status"],
                "basic_identification_status": policy_eval["basic_identification_status"],
                "basic_identification_reason": policy_eval["basic_identification_reason"],
                "eligible": eligible,
                "borderline": borderline,
                "source_profile": source_profile,
                "attribution_complete": c["attribution_complete"],
                "local_path_exists": c["local_path_exists"],
                "errors": [] if policy_eval["has_profile"] else ["missing_pmp_profile"],
            }
        )

    refresh_results = {
        "schema_version": "golden_pack_v1_targeted_pmp_policy_refresh_results.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "flags": FLAGS,
        "summary": {
            "processed_apply_ready_media": len(candidates),
            "media_newly_eligible": newly_eligible,
            "media_still_not_eligible": still_not_eligible,
            "targets_with_newly_eligible_media": len(taxon_newly_eligible),
            "targets_still_blocked": max(0, prep["summary"]["targets_covered"] - len(taxon_newly_eligible)),
        },
        "results": refresh_rows,
        "suggested_next_step": [
            "rerun_local_canonical_pipeline",
            "evaluate_more_media",
            "add_local_media",
            "inspect_policy_rejection_reasons",
        ],
    }

    (run_dir / "refresh_results.json").write_text(json.dumps(refresh_results, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "updated_ai_outputs.json").write_text(json.dumps(ai_outputs, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "pmp_evaluation_queue.json").write_text(
        json.dumps(
            {
                "schema_version": "golden_pack_v1_pmp_evaluation_queue.v1",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "flags": FLAGS,
                "items": queue,
            },
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return run_dir


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--max-per-target", type=int, default=5)
    parser.add_argument("--max-total", type=int, default=100)
    args = parser.parse_args()

    if args.dry_run == args.apply:
        raise SystemExit("Use exactly one mode: --dry-run or --apply")

    mode = "dry-run" if args.dry_run else "apply"
    run_dir = run_refresh(mode=mode, max_per_target=args.max_per_target, max_total=args.max_total)
    print(f"run_dir={run_dir}")
    if (run_dir / "dry_run_plan.json").exists():
        dry = _load_json(run_dir / "dry_run_plan.json")
        s = dry["summary"]
        print(f"total_candidates={s['total_candidates']}")
        print(f"apply_ready_candidates={s['apply_ready_candidates']}")
        print(f"skipped_candidates={s['skipped_candidates']}")
    if mode == "apply":
        res = _load_json(run_dir / "refresh_results.json")
        s = res["summary"]
        print(f"media_newly_eligible={s['media_newly_eligible']}")
        print(f"targets_with_newly_eligible_media={s['targets_with_newly_eligible_media']}")


if __name__ == "__main__":
    main()
