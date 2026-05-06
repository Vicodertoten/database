from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts import materialize_golden_pack_belgian_birds_mvp_v1 as mat

OUTPUT_PATH = REPO_ROOT / "docs" / "audits" / "evidence" / "golden_pack_v1_blocker_diagnosis.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _reason_bucket(reason: str) -> str:
    if "basic_identification_not_eligible" in reason or reason == "no_basic_identification_eligible_media":
        return "no_basic_identification_eligible_media"
    if "Missing local image file" in reason or reason == "no_local_media_file":
        return "no_local_media_file"
    if "insufficient_label_safe_distractors" in reason:
        return "insufficient_label_safe_distractors"
    if "missing_target_fr_label_safe" in reason:
        return "missing_fr_runtime_safe_label"
    if "attribution" in reason.lower():
        return "media_attribution_incomplete"
    return "unknown_or_needs_manual_review"


def build_diagnosis() -> dict[str, Any]:
    plan = _load_json(mat.PLAN_PATH)
    materialization = _load_json(mat.MATERIALIZATION_SOURCE_PATH)
    distractor = _load_json(mat.DISTRACTOR_PATH)
    qualified_export = _load_json(mat.QUALIFIED_EXPORT_PATH)
    inat_manifest = _load_json(mat.INAT_MANIFEST_PATH)
    ai_outputs = _load_json(mat.INAT_AI_OUTPUTS_PATH)

    safe_targets = mat._safe_ready_targets_from_plan(plan)
    target_labels = mat._target_label_safe_fr_map(plan)
    option_labels = mat._option_label_safe_fr_map(plan)
    scientific_names = _scientific_name_map(qualified_export)
    candidate_refs = mat._candidate_refs_by_target(distractor)

    questions_by_target: dict[str, dict[str, Any]] = {}
    for q in materialization.get("questions", []):
        if isinstance(q, dict) and q.get("target_canonical_taxon_id"):
            questions_by_target[str(q["target_canonical_taxon_id"])] = q

    manifest_map, qualified_map = mat._build_media_metadata_indices(inat_manifest, qualified_export)

    targets: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    passes = 0

    for tid in safe_targets:
        reasons: list[str] = []
        q = questions_by_target.get(tid)
        fr_label = target_labels.get(tid)

        if not fr_label:
            reasons.append("missing_fr_runtime_safe_label")

        playable = str((q or {}).get("target_playable_item_id") or "")
        source_media_id = mat._extract_source_media_id(playable) if playable else None

        local_media_count = 0
        eligible_media_count = 0
        attribution_ok = False
        pmp_policy_status = "missing"

        if source_media_id:
            if source_media_id in manifest_map:
                image_rel = str(manifest_map[source_media_id].get("image_path") or "")
                image_abs = mat.INAT_SNAPSHOT_PATH / image_rel
                if image_abs.exists():
                    local_media_count = 1
                else:
                    reasons.append("no_local_media_file")
            else:
                reasons.append("no_local_media_file")

            if mat._evaluate_basic_identification_eligible(ai_outputs, source_media_id):
                eligible_media_count = 1
                pmp_policy_status = "basic_identification_eligible"
            else:
                reasons.append("no_basic_identification_eligible_media")
                pmp_policy_status = "basic_identification_not_eligible"

            qrow = qualified_map.get(source_media_id)
            if isinstance(qrow, dict):
                provenance = qrow.get("provenance") if isinstance(qrow.get("provenance"), dict) else {}
                source = provenance.get("source") if isinstance(provenance.get("source"), dict) else {}
                attribution_ok = bool(source.get("raw_payload_ref")) and bool(source.get("media_license"))
            if not attribution_ok:
                reasons.append("media_attribution_incomplete")
        else:
            reasons.append("no_local_media_file")
            reasons.append("no_basic_identification_eligible_media")

        cands = candidate_refs.get(tid, [])
        seen_refs: set[tuple[str, str]] = set()
        seen_norms: set[str] = set()
        if fr_label:
            seen_norms.add(mat.normalize_localized_name_for_compare(fr_label))

        distractor_count = 0
        for c in cands:
            if c.ref_id == tid:
                continue
            label = option_labels.get(c.ref_id, "")
            if not label.strip():
                continue
            norm = mat.normalize_localized_name_for_compare(label)
            if not norm:
                continue
            key = (c.ref_type, c.ref_id)
            if key in seen_refs or norm in seen_norms:
                continue
            seen_refs.add(key)
            seen_norms.add(norm)
            distractor_count += 1
            if distractor_count == 3:
                break
        if distractor_count < 3:
            reasons.append("insufficient_label_safe_distractors")

        if not reasons:
            passes += 1

        buckets = sorted({_reason_bucket(r) for r in reasons})
        for b in buckets:
            reason_counts[b] += 1

        if not reasons:
            suggested_fix = "none"
        elif "no_basic_identification_eligible_media" in reasons:
            suggested_fix = "consolidate_pmp_policy_inputs_or_select_alternate_eligible_media"
        elif "insufficient_label_safe_distractors" in reasons:
            suggested_fix = "extend_projected_distractor_coverage_with_label_safe_candidates"
        elif "missing_fr_runtime_safe_label" in reasons:
            suggested_fix = "enrich_localized_name_apply_plan_fr_label"
        else:
            suggested_fix = "manual_review_needed"

        targets.append(
            {
                "taxon_ref": tid,
                "scientific_name": scientific_names.get(tid),
                "fr_label": fr_label,
                "source_media_id": source_media_id,
                "has_local_media": local_media_count > 0,
                "local_media_count": local_media_count,
                "pmp_policy_status": pmp_policy_status,
                "eligible_media_count": eligible_media_count,
                "distractor_count_label_safe": distractor_count,
                "attribution_complete": attribution_ok,
                "rejection_reasons": sorted(set(reasons)),
                "rejection_reason_buckets": buckets,
                "suggested_fix": suggested_fix,
            }
        )

    rejected = len(safe_targets) - passes
    summary = {
        "safe_ready_targets": len(safe_targets),
        "selected_targets": passes,
        "rejected_targets": rejected,
    }

    diagnosis = {
        "schema_version": "golden_pack_v1_blocker_diagnosis.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "rejection_reason_counts": dict(sorted(reason_counts.items())),
        "targets": sorted(targets, key=lambda t: t["taxon_ref"]),
    }
    return diagnosis


def write_diagnosis(payload: dict[str, Any]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    payload = build_diagnosis()
    write_diagnosis(payload)
    s = payload["summary"]
    print(f"safe_ready_targets={s['safe_ready_targets']}")
    print(f"selected_targets={s['selected_targets']}")
    print(f"rejected_targets={s['rejected_targets']}")
    for reason, count in payload["rejection_reason_counts"].items():
        print(f"{reason}={count}")
    print(f"output={OUTPUT_PATH}")


if __name__ == "__main__":
    main()
