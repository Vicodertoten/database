from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import materialize_golden_pack_belgian_birds_mvp_v1 as mat
from scripts import plan_golden_pack_v1_coverage_uplift as coverage

OUTPUT_PATH = REPO_ROOT / "data" / "intermediate" / "golden_pack" / "belgian_birds_mvp_v1" / "targeted_media_uplift_plan.json"
FLAGS = {
    "DATABASE_PHASE_CLOSED": False,
    "PERSIST_DISTRACTOR_RELATIONSHIPS_V1": False,
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_coverage_plan() -> dict[str, Any]:
    path = coverage.OUTPUT_PATH
    if not path.exists():
        raise FileNotFoundError(f"Missing coverage plan: {path}")
    return _load_json(path)


def _candidate_readiness_from_coverage(coverage_plan: dict[str, Any]) -> dict[str, Any]:
    rel = str(coverage_plan.get("source_candidate_readiness_path") or "").strip()
    if not rel:
        raise ValueError("Coverage plan missing source_candidate_readiness_path")
    path = REPO_ROOT / rel
    if not path.exists():
        raise FileNotFoundError(f"Missing candidate readiness file: {path}")
    return _load_json(path)


def _media_status_for_id(ai_outputs: dict[str, Any], media_id: str) -> dict[str, Any]:
    key = f"inaturalist::{media_id}"
    outcome = ai_outputs.get(key)
    if not isinstance(outcome, dict):
        return {
            "evaluated": False,
            "eligible": False,
            "basic_status": "missing",
            "basic_reason": "no_pmp_profile",
            "borderline": False,
            "rejected": False,
            "policy_status": "missing",
        }
    profile = outcome.get("pedagogical_media_profile")
    if not isinstance(profile, dict):
        return {
            "evaluated": False,
            "eligible": False,
            "basic_status": "missing",
            "basic_reason": "missing_profile",
            "borderline": False,
            "rejected": False,
            "policy_status": "missing_profile",
        }
    decision = mat.evaluate_pmp_profile_policy(profile)
    usage = decision.get("usage_statuses") if isinstance(decision.get("usage_statuses"), dict) else {}
    basic = usage.get("basic_identification") if isinstance(usage.get("basic_identification"), dict) else {}
    status = str(basic.get("status") or "missing")
    reason = str(basic.get("reason") or "")
    return {
        "evaluated": True,
        "eligible": status == "eligible",
        "basic_status": status,
        "basic_reason": reason,
        "borderline": status == "borderline",
        "rejected": status in {"not_recommended", "not_applicable", "policy_error", "missing", "unknown"},
        "policy_status": str(decision.get("policy_status") or "unknown"),
    }


def _scientific_name_map(qualified_export: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in qualified_export.get("canonical_taxa", []):
        if not isinstance(row, dict):
            continue
        tid = str(row.get("canonical_taxon_id") or "").strip()
        sn = str(row.get("accepted_scientific_name") or "").strip()
        if tid and sn:
            out[tid] = sn
    return out


def _qualified_media_by_taxon(qualified_export: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in qualified_export.get("qualified_resources", []):
        if not isinstance(row, dict):
            continue
        taxon_ref = str(row.get("canonical_taxon_id") or "").strip()
        prov = row.get("provenance") if isinstance(row.get("provenance"), dict) else {}
        source = prov.get("source") if isinstance(prov.get("source"), dict) else {}
        media_id = str(source.get("source_media_id") or "").strip()
        if not taxon_ref or not media_id:
            continue
        out.setdefault(taxon_ref, []).append(row)
    return out


def _manifest_media_map(inat_manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in inat_manifest.get("media_downloads", []):
        if not isinstance(row, dict):
            continue
        media_id = str(row.get("source_media_id") or "").strip()
        if media_id:
            out[media_id] = row
    return out


def build_targeted_media_uplift_plan() -> dict[str, Any]:
    coverage_plan = _load_coverage_plan()
    candidate = _candidate_readiness_from_coverage(coverage_plan)
    qualified_export = _load_json(mat.QUALIFIED_EXPORT_PATH)
    inat_manifest = _load_json(mat.INAT_MANIFEST_PATH)
    ai_outputs = _load_json(mat.INAT_AI_OUTPUTS_PATH)

    name_map = _scientific_name_map(qualified_export)
    media_by_taxon = _qualified_media_by_taxon(qualified_export)
    manifest_map = _manifest_media_map(inat_manifest)

    target_rows = coverage_plan.get("target_matrix", [])
    if not isinstance(target_rows, list):
        raise ValueError("coverage target_matrix must be a list")

    media_blocked: list[dict[str, Any]] = []
    for row in target_rows:
        if not isinstance(row, dict):
            continue
        reasons = {str(x) for x in row.get("rejection_reasons", [])}
        if reasons.intersection({"no_basic_identification_eligible_media", "no_local_media_file", "no_pmp_profile"}):
            media_blocked.append(row)

    candidate_map: dict[str, dict[str, Any]] = {
        str(t.get("taxon_ref") or ""): t
        for t in candidate.get("targets", [])
        if isinstance(t, dict) and str(t.get("taxon_ref") or "")
    }

    target_media_matrix: list[dict[str, Any]] = []
    pmp_refresh_batch: list[dict[str, Any]] = []

    for row in sorted(media_blocked, key=lambda x: str(x.get("taxon_ref") or "")):
        taxon_ref = str(row.get("taxon_ref") or "")
        c = candidate_map.get(taxon_ref, {})
        qualified_rows = media_by_taxon.get(taxon_ref, [])

        evaluated_count = 0
        eligible_count = 0
        borderline_count = 0
        rejected_count = 0
        rejection_reasons: list[str] = []
        refresh_candidates: list[dict[str, Any]] = []

        for qrow in qualified_rows:
            prov = qrow.get("provenance") if isinstance(qrow.get("provenance"), dict) else {}
            source = prov.get("source") if isinstance(prov.get("source"), dict) else {}
            media_id = str(source.get("source_media_id") or "").strip()
            if not media_id:
                continue
            status = _media_status_for_id(ai_outputs, media_id)
            if status["evaluated"]:
                evaluated_count += 1
            if status["eligible"]:
                eligible_count += 1
            if status["borderline"]:
                borderline_count += 1
            if status["rejected"]:
                rejected_count += 1
            if status["basic_reason"]:
                rejection_reasons.append(str(status["basic_reason"]))

            should_refresh = (not status["evaluated"]) or (status["evaluated"] and not status["eligible"])
            if should_refresh:
                mrow = manifest_map.get(media_id, {})
                image_path = str(mrow.get("image_path") or "").strip()
                local_path = str((mat.INAT_SNAPSHOT_PATH / image_path)) if image_path else None
                refresh_candidates.append(
                    {
                        "taxon_ref": taxon_ref,
                        "media_id": media_id,
                        "local_path": local_path,
                        "source_url": str(mrow.get("source_url") or source.get("source_media_key") or ""),
                        "source": str(source.get("source_name") or "inaturalist"),
                        "creator": str(source.get("raw_payload_ref") or ""),
                        "license": str(source.get("media_license") or ""),
                        "license_url": mat._license_url_from_code(str(source.get("media_license") or "")),
                        "priority": "high" if not status["evaluated"] else "medium",
                        "reason_for_selection": "unevaluated_qualified_media"
                        if not status["evaluated"]
                        else "re-evaluate_non_eligible_existing_media",
                        "is_basic_identification_eligible": False,
                        "is_borderline": bool(status["borderline"]),
                    }
                )

        total_qualified = len(qualified_rows)
        unevaluated_count = max(0, total_qualified - evaluated_count)

        reasons = {str(x) for x in row.get("rejection_reasons", [])}
        if "no_local_media_file" in reasons:
            rec_action = "add_or_materialize_local_media"
        elif "no_pmp_profile" in reasons:
            rec_action = "evaluate_more_existing_qualified_media" if total_qualified > 0 else "add_or_materialize_local_media"
        elif total_qualified > evaluated_count:
            rec_action = "evaluate_more_existing_qualified_media"
        elif eligible_count > 0:
            rec_action = "already_has_eligible_media_check_join"
        elif evaluated_count > 0:
            rec_action = "inspect_policy_rejection_reasons"
        else:
            rec_action = "manual_media_review_needed"

        target_media_matrix.append(
            {
                "taxon_ref": taxon_ref,
                "scientific_name": c.get("scientific_name") or name_map.get(taxon_ref),
                "display_label_fr": c.get("display_label_fr"),
                "local_media_count": int(c.get("local_media_count", row.get("local_media_count", 0))),
                "pmp_profile_count": int(c.get("pmp_profile_count", row.get("pmp_profile_count", 0))),
                "policy_projection_count": int(c.get("pmp_policy_projection_count", row.get("policy_projection_count", 0))),
                "eligible_media_count": int(c.get("basic_identification_eligible_media_count", row.get("eligible_media_count", 0))),
                "borderline_media_count": borderline_count,
                "rejected_media_count": rejected_count,
                "available_qualified_media_count": total_qualified,
                "already_pmp_evaluated_media_count": evaluated_count,
                "unevaluated_qualified_media_count": unevaluated_count,
                "best_existing_candidates": [x.get("media_id") for x in refresh_candidates[:3]],
                "policy_rejection_reasons": sorted(set(x for x in rejection_reasons if x)),
                "recommended_action": rec_action,
            }
        )

        pmp_refresh_batch.extend(refresh_candidates)

    targets_with_local_media = sum(1 for t in target_media_matrix if int(t["local_media_count"]) > 0)
    targets_with_no_local_media = len(target_media_matrix) - targets_with_local_media
    targets_with_pmp = sum(1 for t in target_media_matrix if int(t["pmp_profile_count"]) > 0)
    targets_with_no_pmp = len(target_media_matrix) - targets_with_pmp
    targets_with_policy = sum(1 for t in target_media_matrix if int(t["policy_projection_count"]) > 0)
    targets_zero_eligible = sum(1 for t in target_media_matrix if int(t["eligible_media_count"]) == 0)

    total_qualified_for_blocked = sum(int(t["available_qualified_media_count"]) for t in target_media_matrix)
    total_evaluated_for_blocked = sum(int(t["already_pmp_evaluated_media_count"]) for t in target_media_matrix)
    estimated_additional = sum(int(t["unevaluated_qualified_media_count"]) for t in target_media_matrix)

    payload = {
        "schema_version": "golden_pack_v1_targeted_media_uplift_plan.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "flags": FLAGS,
        "source_coverage_uplift_plan": str(coverage.OUTPUT_PATH.relative_to(REPO_ROOT)),
        "summary": {
            "total_media_blocked_targets": len(target_media_matrix),
            "targets_with_local_media": targets_with_local_media,
            "targets_with_no_local_media": targets_with_no_local_media,
            "targets_with_pmp_profiles": targets_with_pmp,
            "targets_with_no_pmp_profiles": targets_with_no_pmp,
            "targets_with_policy_projections": targets_with_policy,
            "targets_with_zero_eligible_media": targets_zero_eligible,
            "total_available_qualified_media_for_blocked_targets": total_qualified_for_blocked,
            "total_already_pmp_evaluated_media_for_blocked_targets": total_evaluated_for_blocked,
            "estimated_additional_media_candidates_to_evaluate": estimated_additional,
        },
        "target_media_matrix": target_media_matrix,
        "pmp_refresh_batch": pmp_refresh_batch,
        "non_actions": [
            "no_borderline_as_primary_quiz_image",
            "no_forced_eligibility",
            "no_runtime_media_selection",
            "no_remote_fetch_at_runtime",
            "no_pack_generation_in_this_phase",
        ],
    }
    return payload


def write_plan(payload: dict[str, Any], output_path: Path = OUTPUT_PATH) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def main() -> None:
    payload = build_targeted_media_uplift_plan()
    out = write_plan(payload)
    print(f"output={out}")
    s = payload["summary"]
    print(f"total_media_blocked_targets={s['total_media_blocked_targets']}")
    print(f"estimated_additional_media_candidates_to_evaluate={s['estimated_additional_media_candidates_to_evaluate']}")
    print(f"pmp_refresh_batch_size={len(payload['pmp_refresh_batch'])}")


if __name__ == "__main__":
    main()

