from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from database_core.enrichment.localized_names import normalize_localized_name_for_compare
from database_core.pack.contract import validate_pack_materialization

PLAN_PATH = REPO_ROOT / "docs" / "audits" / "evidence" / "localized_name_apply_plan_v1.json"
MATERIALIZATION_SOURCE_PATH = (
    REPO_ROOT / "docs" / "audits" / "evidence" / "palier1_v11_baseline" / "pack_materialization_v2.json"
)
DISTRACTOR_PATH = REPO_ROOT / "docs" / "audits" / "evidence" / "distractor_relationships_v1_projected_sprint13.json"

OUT_JSON = REPO_ROOT / "docs" / "audits" / "evidence" / "golden_pack_belgian_birds_mvp_v1.json"
OUT_MD = REPO_ROOT / "docs" / "audits" / "golden-pack-belgian-birds-mvp-v1.md"


class ContractError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing required artifact: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Artifact must be a JSON object: {path}")
    return payload


def _target_label_safe_fr_map(plan: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in plan.get("items", []):
        if not isinstance(item, dict):
            continue
        if item.get("taxon_kind") != "canonical_taxon":
            continue
        if item.get("locale") != "fr":
            continue
        if item.get("decision") not in {"auto_accept", "same_value"}:
            continue
        taxon_id = str(item.get("taxon_id") or "").strip()
        label = str(item.get("chosen_value") or "").strip()
        if not taxon_id or not label:
            continue
        out[taxon_id] = label
    return out


def _option_label_safe_fr_map(plan: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in plan.get("items", []):
        if not isinstance(item, dict):
            continue
        if item.get("taxon_kind") not in {"canonical_taxon", "referenced_taxon"}:
            continue
        if item.get("locale") != "fr":
            continue
        if item.get("decision") not in {"auto_accept", "same_value"}:
            continue
        taxon_id = str(item.get("taxon_id") or "").strip()
        label = str(item.get("chosen_value") or "").strip()
        if not taxon_id or not label:
            continue
        out[taxon_id] = label
    return out


def _safe_ready_targets_from_plan(plan: dict[str, Any]) -> list[str]:
    metrics = plan.get("metrics")
    if not isinstance(metrics, dict):
        raise ContractError("Plan missing metrics")
    source_targets = metrics.get("safe_ready_targets_from_plan")
    if not isinstance(source_targets, list):
        raise ContractError("Plan missing safe_ready_targets_from_plan")
    targets = [str(item).strip() for item in source_targets if str(item).strip()]
    if len(targets) != len(set(targets)):
        raise ContractError("Plan safe-ready target set has duplicates")
    if any(not item.startswith("taxon:birds:") for item in targets):
        raise ContractError("Plan safe-ready target set contains malformed ids")
    if len(targets) < 30:
        raise ContractError(f"observed_safe_target_count={len(targets)} < 30")
    return sorted(targets)


def _candidate_counts_by_target(distractor: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in distractor.get("projected_records", []):
        if not isinstance(row, dict) or row.get("status") != "candidate":
            continue
        target = str(row.get("target_canonical_taxon_id") or "").strip()
        ctype = str(row.get("candidate_taxon_ref_type") or "").strip()
        cid = str(row.get("candidate_taxon_ref_id") or "").strip()
        if target and ctype in {"canonical_taxon", "referenced_taxon"} and cid:
            counts[target] = counts.get(target, 0) + 1
    return counts


def _candidate_refs_by_target(distractor: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in distractor.get("projected_records", []):
        if not isinstance(row, dict) or row.get("status") != "candidate":
            continue
        target = str(row.get("target_canonical_taxon_id") or "").strip()
        ctype = str(row.get("candidate_taxon_ref_type") or "").strip()
        cid = str(row.get("candidate_taxon_ref_id") or "").strip()
        if not target or ctype not in {"canonical_taxon", "referenced_taxon"} or not cid:
            continue
        rank_raw = row.get("source_rank")
        try:
            rank = int(rank_raw)
        except (TypeError, ValueError):
            rank = 10**9
        out.setdefault(target, []).append(
            {
                "source_rank": rank,
                "candidate_taxon_ref_type": ctype,
                "candidate_taxon_ref_id": cid,
            }
        )
    resolved: dict[str, list[dict[str, Any]]] = {}
    for target, values in out.items():
        resolved[target] = sorted(
            values,
            key=lambda item: (
                int(item["source_rank"]),
                str(item["candidate_taxon_ref_type"]),
                str(item["candidate_taxon_ref_id"]),
            ),
        )
    return resolved


def build_golden_pack() -> dict[str, Any]:
    plan = _load_json(PLAN_PATH)
    materialization_source = _load_json(MATERIALIZATION_SOURCE_PATH)
    distractor = _load_json(DISTRACTOR_PATH)

    safe_targets = _safe_ready_targets_from_plan(plan)

    source_questions = materialization_source.get("questions")
    if not isinstance(source_questions, list):
        raise ContractError("Source pack_materialization_v2 missing questions list")

    questions_by_target: dict[str, dict[str, Any]] = {}
    for question in source_questions:
        if not isinstance(question, dict):
            continue
        target = str(question.get("target_canonical_taxon_id") or "").strip()
        if not target:
            continue
        if target in questions_by_target:
            raise ContractError(f"Duplicate target question in source materialization: {target}")
        questions_by_target[target] = question

    target_fr_labels = _target_label_safe_fr_map(plan)
    option_fr_labels = _option_label_safe_fr_map(plan)
    candidate_counts = _candidate_counts_by_target(distractor)
    candidate_refs_by_target = _candidate_refs_by_target(distractor)

    target_to_distractors: dict[str, list[dict[str, Any]]] = {}
    for target_id in safe_targets:
        if target_id not in questions_by_target:
            continue
        if candidate_counts.get(target_id, 0) < 3:
            continue
        if target_id not in target_fr_labels:
            continue
        candidate_refs = candidate_refs_by_target.get(target_id, [])
        label_safe_candidate_refs = [
            ref
            for ref in candidate_refs
            if ref["candidate_taxon_ref_id"] != target_id and ref["candidate_taxon_ref_id"] in option_fr_labels
        ]
        deduped_candidates: list[dict[str, Any]] = []
        seen_pairs: set[tuple[str, str]] = set()
        for ref in label_safe_candidate_refs:
            key = (str(ref["candidate_taxon_ref_type"]), str(ref["candidate_taxon_ref_id"]))
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            deduped_candidates.append(ref)
        if len(deduped_candidates) >= 3:
            target_to_distractors[target_id] = deduped_candidates[:3]

    selected = sorted(target_to_distractors.keys())[:30]
    if len(selected) != 30:
        raise ContractError(
            f"Unable to select 30 deterministic targets with 3 label-safe distractors "
            f"(available={len(target_to_distractors)})"
        )

    output_questions: list[dict[str, Any]] = []
    for position, target_id in enumerate(selected, start=1):
        source_question = questions_by_target[target_id]
        source_options = source_question.get("options")
        if not isinstance(source_options, list):
            raise ContractError(f"Target {target_id} source options missing")
        target_option = next((opt for opt in source_options if bool(opt.get("is_correct"))), None)
        if target_option is None:
            raise ContractError(f"Target {target_id} source question has no correct option")

        target_canonical_taxon_id = str(target_option.get("canonical_taxon_id") or "").strip()
        if target_canonical_taxon_id != target_id:
            raise ContractError(
                f"Target {target_id} correct option mismatch canonical_taxon_id={target_canonical_taxon_id}"
            )
        target_label = target_fr_labels[target_id]
        selected_distractors = target_to_distractors[target_id]

        localized_options: list[dict[str, Any]] = [
            {
                "option_id": f"q{position}:opt:1",
                "canonical_taxon_id": target_id,
                "taxon_label": target_label,
                "is_correct": True,
                "playable_item_id": target_option.get("playable_item_id"),
                "source": str(target_option.get("source") or "playable_corpus.v1"),
                "score": target_option.get("score"),
                "reason_codes": sorted(
                    [str(code) for code in target_option.get("reason_codes", []) if str(code).strip()]
                ),
                "referenced_only": bool(target_option.get("referenced_only", False)),
            }
        ]
        normalized_labels: list[str] = [
            normalize_localized_name_for_compare(target_label)
        ]
        for idx, candidate_ref in enumerate(selected_distractors, start=2):
            candidate_id = str(candidate_ref["candidate_taxon_ref_id"])
            candidate_type = str(candidate_ref["candidate_taxon_ref_type"])
            label = option_fr_labels[candidate_id]
            normalized = normalize_localized_name_for_compare(label)
            if not normalized:
                raise ContractError(
                    f"Target {target_id} option {candidate_id} has empty normalized label"
                )
            normalized_labels.append(normalized)
            localized_options.append(
                {
                    "option_id": f"q{position}:opt:{idx}",
                    "canonical_taxon_id": candidate_id,
                    "taxon_label": label,
                    "is_correct": False,
                    "playable_item_id": None,
                    "source": "distractor_relationships_v1_projected_sprint13",
                    "score": None,
                    "reason_codes": ["sprint14c2_label_safe_gate"],
                    "referenced_only": candidate_type == "referenced_taxon",
                }
            )

        if len(set(normalized_labels)) != 4:
            raise ContractError(
                f"Target {target_id} has non-distinct option labels after normalization: {normalized_labels}"
            )

        output_questions.append(
            {
                "position": position,
                "target_playable_item_id": source_question.get("target_playable_item_id"),
                "target_canonical_taxon_id": target_id,
                "options": localized_options,
            }
        )

    output_questions = sorted(output_questions, key=lambda q: str(q["target_canonical_taxon_id"]))
    for idx, question in enumerate(output_questions, start=1):
        question["position"] = idx

    payload = {
        "schema_version": "pack_materialization_v2",
        "pack_materialization_version": "pack.materialization.v2",
        "materialization_id": "golden_pack_belgian_birds_mvp_v1",
        "pack_id": "belgian_birds_mvp_v1",
        "revision": 1,
        "source_build_id": str(plan.get("plan_hash") or "unknown_plan_hash"),
        "created_at": "2026-05-05T00:00:00Z",
        "purpose": "assignment",
        "ttl_hours": None,
        "expires_at": None,
        "question_count": len(output_questions),
        "questions": output_questions,
    }

    validate_pack_materialization(payload)
    return payload


def write_outputs(payload: dict[str, Any]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        "last_reviewed: 2026-05-05",
        "source_of_truth: docs/audits/golden-pack-belgian-birds-mvp-v1.md",
        "scope: sprint14c2_golden_pack_artifact_only",
        "---",
        "",
        "# Golden Pack Belgian Birds MVP v1",
        "",
        "- contract_version: pack.materialization.v2",
        f"- materialization_id: {payload['materialization_id']}",
        f"- question_count: {payload['question_count']}",
        "- selection: first 30 safe-ready targets sorted lexically from localized_name_apply_plan_v1.json",
        "- fallbacks: none (fail-fast contract)",
    ]
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    payload = build_golden_pack()
    write_outputs(payload)
    print(f"Materialization: {payload['materialization_id']}")
    print(f"Question count: {payload['question_count']}")


if __name__ == "__main__":
    main()
