from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import materialize_golden_pack_belgian_birds_mvp_v1 as mat

BASE_RUN_DIR = REPO_ROOT / "data" / "intermediate" / "golden_pack" / "belgian_birds_mvp_v1" / "local_canonical_run"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_record_count(payload: dict[str, Any]) -> int | None:
    for key in ("items", "projected_records", "qualified_resources", "questions", "media_downloads"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return None


def _extract_meta(payload: dict[str, Any]) -> dict[str, Any]:
    meta = {
        "schema_version": payload.get("schema_version"),
        "run_id": payload.get("run_id"),
        "snapshot_id": payload.get("snapshot_id"),
        "plan_hash": payload.get("plan_hash"),
        "generated_at": payload.get("generated_at"),
        "created_at": payload.get("created_at"),
        "run_date": payload.get("run_date"),
        "decision": payload.get("decision"),
    }
    return {k: v for k, v in meta.items() if v is not None}


def _inventory_entry(path: Path, role: str) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "path": str(path.relative_to(REPO_ROOT)),
        "exists": path.exists(),
        "role": role,
    }
    if not path.exists():
        return entry
    entry["sha256"] = _sha256(path)
    if path.suffix == ".json":
        payload = _load_json(path)
        entry.update(_extract_meta(payload))
        count = _json_record_count(payload)
        if count is not None:
            entry["record_count"] = count
    return entry


def _extract_source_media_id(playable_item_id: str) -> str | None:
    m = re.search(r"inaturalist:(\d+)$", playable_item_id)
    return m.group(1) if m else None


def _read_materializer_targets() -> tuple[list[str], dict[str, dict[str, Any]]]:
    mat_src = _load_json(mat.MATERIALIZATION_SOURCE_PATH)
    questions_by_target: dict[str, dict[str, Any]] = {}
    for q in mat_src.get("questions", []):
        if not isinstance(q, dict):
            continue
        tid = str(q.get("target_canonical_taxon_id") or "").strip()
        if tid:
            questions_by_target[tid] = q
    return sorted(questions_by_target.keys()), questions_by_target


def _build_candidate_readiness() -> dict[str, Any]:
    plan = _load_json(mat.PLAN_PATH)
    distractor = _load_json(mat.DISTRACTOR_PATH)
    qualified_export = _load_json(mat.QUALIFIED_EXPORT_PATH)
    inat_manifest = _load_json(mat.INAT_MANIFEST_PATH)
    ai_outputs = _load_json(mat.INAT_AI_OUTPUTS_PATH)

    safe_targets = mat._safe_ready_targets_from_plan(plan)
    target_labels = mat._target_label_safe_fr_map(plan)
    option_labels = mat._option_label_safe_fr_map(plan)
    candidate_refs = mat._candidate_refs_by_target(distractor)

    scientific_name_map: dict[str, str] = {}
    for row in qualified_export.get("canonical_taxa", []):
        if isinstance(row, dict):
            tid = str(row.get("canonical_taxon_id") or "").strip()
            sn = str(row.get("accepted_scientific_name") or "").strip()
            if tid and sn:
                scientific_name_map[tid] = sn

    manifest_map, qualified_map = mat._build_media_metadata_indices(inat_manifest, qualified_export)
    _, questions_by_target = _read_materializer_targets()

    targets: list[dict[str, Any]] = []
    summary = {
        "safe_ready_targets": len(safe_targets),
        "golden_pack_ready_targets": 0,
        "rejected_targets": 0,
    }

    for tid in safe_targets:
        reasons: list[str] = []
        question = questions_by_target.get(tid)
        fr = target_labels.get(tid)

        if not fr:
            reasons.append("missing_fr_runtime_safe_label")
            name_status = "missing"
        else:
            name_status = "runtime_safe"

        playable = str((question or {}).get("target_playable_item_id") or "")
        source_media_id = _extract_source_media_id(playable) if playable else None

        local_media_count = 0
        pmp_profile_count = 0
        pmp_policy_projection_count = 0
        eligible_media_count = 0

        if source_media_id:
            if source_media_id in manifest_map:
                rel = str(manifest_map[source_media_id].get("image_path") or "")
                if rel and (mat.INAT_SNAPSHOT_PATH / rel).exists():
                    local_media_count = 1
                else:
                    reasons.append("no_local_media_file")
            else:
                reasons.append("no_local_media_file")

            if f"inaturalist::{source_media_id}" in ai_outputs:
                pmp_profile_count = 1
                pmp_policy_projection_count = 1
                if mat._evaluate_basic_identification_eligible(ai_outputs, source_media_id):
                    eligible_media_count = 1
                else:
                    reasons.append("no_basic_identification_eligible_media")
            else:
                reasons.append("no_pmp_profile")
        else:
            reasons.append("missing_target_source_media_id")

        distractor_candidates_total = len(candidate_refs.get(tid, []))

        seen_ref: set[tuple[str, str]] = set()
        seen_label: set[str] = set()
        if fr:
            seen_label.add(mat.normalize_localized_name_for_compare(fr))

        distractor_label_safe_count = 0
        for cand in candidate_refs.get(tid, []):
            if cand.ref_id == tid:
                continue
            label = option_labels.get(cand.ref_id, "")
            if not label.strip():
                continue
            norm = mat.normalize_localized_name_for_compare(label)
            if not norm:
                continue
            key = (cand.ref_type, cand.ref_id)
            if key in seen_ref or norm in seen_label:
                continue
            seen_ref.add(key)
            seen_label.add(norm)
            distractor_label_safe_count += 1
            if distractor_label_safe_count == 3:
                break

        if distractor_label_safe_count < 3:
            reasons.append("insufficient_label_safe_distractors")

        golden_pack_ready = len(reasons) == 0
        if golden_pack_ready:
            summary["golden_pack_ready_targets"] += 1
        else:
            summary["rejected_targets"] += 1

        if golden_pack_ready:
            suggested_fix = "none"
        elif "no_basic_identification_eligible_media" in reasons:
            suggested_fix = "refresh_or_align_pmp_policy_inputs"
        elif "insufficient_label_safe_distractors" in reasons:
            suggested_fix = "refresh_distractor_projection_label_safe"
        elif "missing_fr_runtime_safe_label" in reasons:
            suggested_fix = "refresh_localized_name_apply_plan"
        else:
            suggested_fix = "manual_data_alignment_review"

        targets.append(
            {
                "taxon_ref": tid,
                "scientific_name": scientific_name_map.get(tid),
                "display_label_fr": fr,
                "name_status": name_status,
                "source_media_id": source_media_id,
                "local_media_count": local_media_count,
                "pmp_profile_count": pmp_profile_count,
                "pmp_policy_projection_count": pmp_policy_projection_count,
                "basic_identification_eligible_media_count": eligible_media_count,
                "selected_primary_media_candidate": source_media_id,
                "distractor_candidates_total": distractor_candidates_total,
                "distractor_label_safe_count": distractor_label_safe_count,
                "golden_pack_ready": golden_pack_ready,
                "rejection_reasons": sorted(set(reasons)),
                "suggested_fix": suggested_fix,
            }
        )

    return {
        "summary": summary,
        "targets": targets,
    }


def _build_lineage_checks(candidate_readiness: dict[str, Any]) -> dict[str, Any]:
    plan = _load_json(mat.PLAN_PATH)
    distractor = _load_json(mat.DISTRACTOR_PATH)
    qualified_export = _load_json(mat.QUALIFIED_EXPORT_PATH)
    inat_manifest = _load_json(mat.INAT_MANIFEST_PATH)
    ai_outputs = _load_json(mat.INAT_AI_OUTPUTS_PATH)
    pmp_audit = _load_json(REPO_ROOT / "docs" / "audits" / "evidence" / "pmp_policy_v1_broader_400_20260504_snapshot_audit.json")

    safe_targets = set(mat._safe_ready_targets_from_plan(plan))
    canonical_targets = {
        str(item.get("taxon_id") or "").strip()
        for item in plan.get("items", [])
        if isinstance(item, dict) and item.get("taxon_kind") == "canonical_taxon" and item.get("locale") == "fr"
    }

    distractor_targets = {
        str(row.get("target_canonical_taxon_id") or "").strip()
        for row in distractor.get("projected_records", [])
        if isinstance(row, dict) and str(row.get("target_canonical_taxon_id") or "").strip()
    }

    qualified_media_ids = {
        str(((((row.get("provenance") or {}).get("source") or {}).get("source_media_id")) or "")).strip()
        for row in qualified_export.get("qualified_resources", [])
        if isinstance(row, dict)
    }
    qualified_media_ids.discard("")

    pmp_media_ids = {
        key.split("::", 1)[1]
        for key in ai_outputs.keys()
        if isinstance(key, str) and "::" in key
    }

    policy_media_ids = pmp_media_ids.copy()

    targets = candidate_readiness["targets"]
    targets_local_no_pmp = [
        t["taxon_ref"]
        for t in targets
        if t["local_media_count"] > 0 and t["pmp_profile_count"] == 0
    ]
    targets_pmp_no_policy = [
        t["taxon_ref"]
        for t in targets
        if t["pmp_profile_count"] > 0 and t["pmp_policy_projection_count"] == 0
    ]
    targets_policy_eligible_local_missing = [
        t["taxon_ref"]
        for t in targets
        if t["basic_identification_eligible_media_count"] > 0 and t["local_media_count"] == 0
    ]

    possible_join_or_copy_issues = [
        t["taxon_ref"]
        for t in targets
        if (
            "no_basic_identification_eligible_media" in t["rejection_reasons"]
            and t["local_media_count"] > 0
            and t["pmp_profile_count"] > 0
        )
    ]

    timestamp_meta = {
        "localized_name_apply_plan_generated_at": _load_json(mat.PLAN_PATH).get("generated_at"),
        "distractor_projection_run_date": distractor.get("run_date"),
        "pmp_snapshot_id": pmp_audit.get("snapshot_id"),
        "pmp_ai_outputs_path": pmp_audit.get("ai_outputs_path"),
        "qualified_export_generated_at": qualified_export.get("generated_at"),
        "localized_plan_hash": _load_json(mat.PLAN_PATH).get("plan_hash"),
    }

    artifacts_with_missing_lineage_fields = [
        item
        for item in [
            {"name": "qualified_export", "run_id": None, "generated_at": qualified_export.get("generated_at")},
            {"name": "distractor_projection", "run_date": distractor.get("run_date")},
            {"name": "localized_plan", "plan_hash": _load_json(mat.PLAN_PATH).get("plan_hash")},
        ]
        if not any(v for k, v in item.items() if k != "name")
    ]

    return {
        "overlaps": {
            "canonical_taxa_localized_plan_vs_qualified_export": {
                "localized_plan_count": len(canonical_targets),
                "qualified_export_count": len({t.get("taxon_ref") for t in targets}),
                "intersection_count": len(canonical_targets.intersection({t.get("taxon_ref") for t in targets})),
            },
            "safe_ready_targets_vs_distractor_projection_targets": {
                "safe_ready_count": len(safe_targets),
                "distractor_target_count": len(distractor_targets),
                "intersection_count": len(safe_targets.intersection(distractor_targets)),
            },
            "qualified_media_ids_vs_pmp_media_ids": {
                "qualified_media_count": len(qualified_media_ids),
                "pmp_media_count": len(pmp_media_ids),
                "intersection_count": len(qualified_media_ids.intersection(pmp_media_ids)),
            },
            "pmp_media_ids_vs_policy_media_ids": {
                "pmp_media_count": len(pmp_media_ids),
                "policy_media_count": len(policy_media_ids),
                "intersection_count": len(pmp_media_ids.intersection(policy_media_ids)),
            },
        },
        "target_level_gaps": {
            "targets_with_local_media_but_without_pmp": targets_local_no_pmp,
            "targets_with_pmp_but_without_policy_projection": targets_pmp_no_policy,
            "targets_with_policy_eligible_media_but_local_file_absent": targets_policy_eligible_local_missing,
            "targets_rejected_by_media_but_with_local_and_pmp_present": possible_join_or_copy_issues,
        },
        "artifact_lineage_meta": timestamp_meta,
        "artifacts_with_missing_lineage_fields": artifacts_with_missing_lineage_fields,
    }


def run_pipeline(output_root: Path | None = None) -> Path:
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_id = f"golden_pack_belgian_birds_mvp_v1_local_{run_ts}"

    root = output_root or BASE_RUN_DIR
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    inputs = [
        (mat.PLAN_PATH, "source"),
        (REPO_ROOT / "docs" / "audits" / "evidence" / "localized_name_projection_vs_14b_audit_reconciliation.json", "evidence"),
        (mat.DISTRACTOR_PATH, "intermediate"),
        (mat.QUALIFIED_EXPORT_PATH, "intermediate"),
        (REPO_ROOT / "data" / "normalized" / "palier1_be_birds_50taxa_run003_v11_baseline.normalized.json", "intermediate"),
        (mat.INAT_AI_OUTPUTS_PATH, "source"),
        (REPO_ROOT / "docs" / "audits" / "evidence" / "pmp_policy_v1_broader_400_20260504_snapshot_audit.json", "evidence"),
        (REPO_ROOT / "docs" / "audits" / "evidence" / "database_integrity_runtime_handoff_audit.json", "evidence"),
        (mat.SCHEMA_PACK_PATH, "runtime-support"),
        (mat.SCHEMA_MANIFEST_PATH, "runtime-support"),
        (mat.SCHEMA_VALIDATION_REPORT_PATH, "runtime-support"),
        (REPO_ROOT / "scripts" / "materialize_golden_pack_belgian_birds_mvp_v1.py", "runtime-support"),
        (REPO_ROOT / "scripts" / "diagnose_golden_pack_belgian_birds_mvp_v1_blockers.py", "runtime-support"),
    ]

    inventory = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": [_inventory_entry(path, role) for path, role in inputs],
    }

    candidate_readiness = _build_candidate_readiness()
    lineage_checks = _build_lineage_checks(candidate_readiness)

    try:
        output_dir_value = str(run_dir.relative_to(REPO_ROOT))
    except ValueError:
        output_dir_value = str(run_dir)

    run_manifest = {
        "schema_version": "golden_pack_local_canonical_run_manifest.v1",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": output_dir_value,
        "purpose": "prepare_coherent_local_canonical_rerun_inputs_for_golden_pack_v1",
        "non_actions": [
            "no_runtime_canonical_pack_generation",
            "PERSIST_DISTRACTOR_RELATIONSHIPS_V1 remains false",
            "DATABASE_PHASE_CLOSED remains false",
            "no_historical_evidence_rewrite",
        ],
        "flags": {
            "PERSIST_DISTRACTOR_RELATIONSHIPS_V1": False,
            "DATABASE_PHASE_CLOSED": False,
        },
        "artifacts": {
            "run_manifest": "run_manifest.json",
            "input_inventory": "input_inventory.json",
            "lineage_checks": "lineage_checks.json",
            "candidate_readiness": "candidate_readiness.json",
        },
    }

    (run_dir / "run_manifest.json").write_text(json.dumps(run_manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "input_inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "lineage_checks.json").write_text(json.dumps(lineage_checks, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    (run_dir / "candidate_readiness.json").write_text(json.dumps(candidate_readiness, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    return run_dir


def main() -> None:
    run_dir = run_pipeline()
    print(f"run_dir={run_dir}")


if __name__ == "__main__":
    main()
