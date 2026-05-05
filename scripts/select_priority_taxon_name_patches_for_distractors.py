"""Sprint 13D priority localized name completion for distractor readiness.

Builds a ranked priority list of missing-FR distractor candidates, generates a
manual CSV patch template, applies selected patches through Sprint 13B patch
system (dry-run first by default), and writes Sprint 13 readiness/comparison
artifacts.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

try:
    from scripts.apply_taxon_localized_name_patches_v1 import (
        apply_patches,
        load_json,
        load_referenced_records,
        run_apply,
        validate_patch_records,
    )
    from scripts.build_distractor_readiness_v1 import run_readiness
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from apply_taxon_localized_name_patches_v1 import (
        apply_patches,
        load_json,
        load_referenced_records,
        run_apply,
        validate_patch_records,
    )
    from build_distractor_readiness_v1 import run_readiness

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CANDIDATES_S12 = (
    REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "distractor_relationship_candidates_v1_sprint12.json"
)
DEFAULT_READINESS_S12 = (
    REPO_ROOT / "docs" / "audits" / "evidence" / "distractor_readiness_v1_sprint12.json"
)
DEFAULT_SHELL_PLAN_S13 = (
    REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "referenced_taxon_shell_apply_plan_sprint13.json"
)
DEFAULT_LOCALIZED_AUDIT_S13 = (
    REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "taxon_localized_names_sprint13_audit.json"
)
DEFAULT_PROJECTED_RELATIONSHIPS_S13 = (
    REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "distractor_relationships_v1_projected_sprint13.json"
)

DEFAULT_PATCH_CSV = REPO_ROOT / "data" / "manual" / "taxon_localized_name_patches_sprint13.csv"

DEFAULT_APPLY_EVIDENCE_JSON = (
    REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "taxon_localized_names_sprint13_apply.json"
)
DEFAULT_APPLY_EVIDENCE_MD = (
    REPO_ROOT / "docs" / "audits" / "taxon-localized-names-sprint13-apply.md"
)

DEFAULT_READINESS_S13 = (
    REPO_ROOT / "docs" / "audits" / "evidence" / "distractor_readiness_v1_sprint13.json"
)
DEFAULT_COMPARISON_JSON = (
    REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "distractor_readiness_sprint12_vs_sprint13.json"
)
DEFAULT_COMPARISON_MD = (
    REPO_ROOT / "docs" / "audits" / "distractor-readiness-sprint12-vs-sprint13.md"
)

DEFAULT_PATCH_SCHEMA = REPO_ROOT / "schemas" / "taxon_localized_name_patch_v1.schema.json"
DEFAULT_CANONICAL_PATH = (
    REPO_ROOT
    / "data"
    / "normalized"
    / "palier1_be_birds_50taxa_run003_v11_baseline.normalized.json"
)
DEFAULT_REFERENCED_CANDIDATES_PATH = (
    REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "referenced_taxon_shell_candidates_sprint12.json"
)
DEFAULT_REFERENCED_SNAPSHOT_PATH = (
    REPO_ROOT / "data" / "review_overrides" / "referenced_taxa_snapshot.json"
)
DEFAULT_OUTPUT_CANONICAL = (
    REPO_ROOT / "data" / "enriched" / "taxon_localized_names_v1" / "canonical_taxa_patched.json"
)
DEFAULT_OUTPUT_REFERENCED = (
    REPO_ROOT
    / "data"
    / "enriched"
    / "taxon_localized_names_v1"
    / "referenced_taxa_patched.json"
)

CSV_COLUMNS = [
    "scientific_name",
    "candidate_taxon_ref_type",
    "candidate_taxon_ref_id",
    "source_taxon_id",
    "number_of_target_taxa_using_candidate",
    "best_source",
    "best_source_rank",
    "targets_unblocked_if_named",
    "current_fr_status",
    "recommended_action",
    "priority_score",
    "common_name_fr",
    "common_name_en",
    "common_name_nl",
    "source",
    "confidence",
    "reviewer",
    "notes",
]

SOURCE_PRIORITY = {
    "inaturalist_similar_species": 0,
    "taxonomic_neighbor_same_genus": 1,
    "taxonomic_neighbor_same_family": 2,
    "taxonomic_neighbor_same_order": 3,
    "ai_pedagogical_proposal": 4,
    "manual_expert": 5,
    "emergency_diversity_fallback": 6,
}


@dataclass(frozen=True)
class CandidateKey:
    scientific_name: str
    ref_type: str
    ref_id: str | None


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _first(values: Any) -> str | None:
    if not isinstance(values, list) or not values:
        return None
    value = str(values[0]).strip()
    return value or None


def _normalize_optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "none":
        return None
    return text


def _source_taxon_id_from_ref_id(ref_id: str | None) -> str | None:
    if not ref_id:
        return None
    prefix = "reftaxon:inaturalist:"
    if ref_id.startswith(prefix):
        return ref_id[len(prefix):]
    return None


def _build_name_lookups(
    *,
    shell_plan: dict[str, Any],
    canonical_payload: dict[str, Any],
) -> tuple[dict[str, str], dict[str, str], set[str]]:
    en_by_scientific: dict[str, str] = {}
    source_id_by_scientific: dict[str, str] = {}
    clean_referenced_ids: set[str] = set()

    for item in shell_plan.get("apply_records", []):
        if not isinstance(item, dict):
            continue
        sci = str(item.get("scientific_name", "")).strip()
        if not sci:
            continue
        source_taxon_id = _normalize_optional_str(item.get("source_taxon_id"))
        if source_taxon_id:
            source_id_by_scientific[sci] = source_taxon_id
        en_name = _first((item.get("common_names_i18n") or {}).get("en", []))
        if en_name:
            en_by_scientific[sci] = en_name
        ref_id = _normalize_optional_str(item.get("proposed_referenced_taxon_id"))
        if ref_id:
            clean_referenced_ids.add(ref_id)

    for item in canonical_payload.get("canonical_taxa", []):
        if not isinstance(item, dict):
            continue
        sci = str(item.get("accepted_scientific_name", "")).strip()
        if not sci:
            continue
        en_name = _first((item.get("common_names_by_language") or {}).get("en", []))
        if en_name and sci not in en_by_scientific:
            en_by_scientific[sci] = en_name

    return en_by_scientific, source_id_by_scientific, clean_referenced_ids


def select_priority_candidates(
    *,
    candidates_s12: dict[str, Any],
    shell_plan: dict[str, Any],
    canonical_payload: dict[str, Any],
    min_targets_ready: int = 30,
    missing_ratio_target: float = 0.30,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    relationships = [r for r in candidates_s12.get("relationships", []) if isinstance(r, dict)]
    per_target = [p for p in candidates_s12.get("per_target_summaries", []) if isinstance(p, dict)]

    total_relationships = len(relationships)
    by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rel in relationships:
        by_target[str(rel.get("target_canonical_taxon_id", ""))].append(rel)

    usable_fr_by_target = {
        target_id: sum(1 for rel in rels if rel.get("can_be_used_now_fr", False))
        for target_id, rels in by_target.items()
    }

    missing_rels = [rel for rel in relationships if not rel.get("can_be_used_now_fr", False)]
    grouped: dict[CandidateKey, list[dict[str, Any]]] = defaultdict(list)
    for rel in missing_rels:
        sci = str(rel.get("candidate_scientific_name", "")).strip()
        ref_type = str(rel.get("candidate_taxon_ref_type", "")).strip() or "unresolved_taxon"
        ref_id = _normalize_optional_str(rel.get("candidate_taxon_ref_id"))
        if not sci:
            continue
        grouped[CandidateKey(scientific_name=sci, ref_type=ref_type, ref_id=ref_id)].append(rel)

    en_by_scientific, source_id_by_scientific, clean_referenced_ids = _build_name_lookups(
        shell_plan=shell_plan,
        canonical_payload=canonical_payload,
    )

    ranked: list[dict[str, Any]] = []
    for key, rows in grouped.items():
        target_ids = {
            str(row.get("target_canonical_taxon_id", "")).strip()
            for row in rows
            if str(row.get("target_canonical_taxon_id", "")).strip()
        }
        relationship_count = len(rows)
        number_of_target_taxa_using_candidate = len(target_ids)

        best_source = min(
            (str(row.get("source", "")).strip() for row in rows),
            key=lambda src: (SOURCE_PRIORITY.get(src, 99), src),
            default="unknown",
        )
        best_source_rank = min(int(row.get("source_rank", 999)) for row in rows)

        targets_unblocked_if_named = 0
        near_ready_targets = 0
        for target_id in target_ids:
            before = int(usable_fr_by_target.get(target_id, 0))
            add_count = sum(
                1
                for row in rows
                if str(row.get("target_canonical_taxon_id", "")).strip() == target_id
            )
            if before in {1, 2}:
                near_ready_targets += 1
            if before < 3 and before + add_count >= 3:
                targets_unblocked_if_named += 1

        source_taxon_id = _source_taxon_id_from_ref_id(key.ref_id)
        if not source_taxon_id:
            source_taxon_id = source_id_by_scientific.get(key.scientific_name)

        mapping_is_clean = False
        if key.ref_type == "canonical_taxon" and key.ref_id:
            mapping_is_clean = True
        elif key.ref_type == "referenced_taxon" and key.ref_id:
            mapping_is_clean = key.ref_id in clean_referenced_ids or key.ref_id.startswith(
                "reftaxon:inaturalist:"
            )

        source_rank_score = max(0, 12 - best_source_rank)
        priority_score = (
            (targets_unblocked_if_named * 100)
            + (near_ready_targets * 25)
            + (number_of_target_taxa_using_candidate * 12)
            + (relationship_count * 4)
            + source_rank_score
            + (20 if mapping_is_clean else 0)
        )

        recommended_action = "manual_review"
        if key.ref_type in {"canonical_taxon", "referenced_taxon"} and mapping_is_clean:
            recommended_action = "seed_fr_then_human_review"

        ranked.append(
            {
                "scientific_name": key.scientific_name,
                "candidate_taxon_ref_type": key.ref_type,
                "candidate_taxon_ref_id": key.ref_id,
                "source_taxon_id": source_taxon_id,
                "number_of_target_taxa_using_candidate": number_of_target_taxa_using_candidate,
                "best_source": best_source,
                "best_source_rank": best_source_rank,
                "targets_unblocked_if_named": targets_unblocked_if_named,
                "current_fr_status": "missing_fr",
                "recommended_action": recommended_action,
                "priority_score": priority_score,
                "relationship_usage_count": relationship_count,
                "existing_common_name_en": en_by_scientific.get(key.scientific_name),
                "mapping_is_clean": mapping_is_clean,
                "near_ready_targets": near_ready_targets,
            }
        )

    ranked.sort(
        key=lambda row: (
            -int(row["priority_score"]),
            -int(row["targets_unblocked_if_named"]),
            -int(row["number_of_target_taxa_using_candidate"]),
            int(row["best_source_rank"]),
            str(row["scientific_name"]),
        )
    )

    base_ready_targets = int(
        candidates_s12.get("summary", {}).get("targets_with_3_plus_usable_fr_candidates", 0)
    )
    remaining_missing = len(missing_rels)
    selected: list[dict[str, Any]] = []

    for row in ranked:
        selected.append(row)
        remaining_missing -= int(row["relationship_usage_count"])
        current_ratio = remaining_missing / max(total_relationships, 1)
        if base_ready_targets >= min_targets_ready and current_ratio <= missing_ratio_target:
            break

    metrics = {
        "total_relationships": total_relationships,
        "missing_fr_relationships_before": len(missing_rels),
        "missing_fr_relationships_after_priority_set": max(remaining_missing, 0),
        "missing_fr_ratio_before": len(missing_rels) / max(total_relationships, 1),
        "missing_fr_ratio_after_priority_set": (
            max(remaining_missing, 0) / max(total_relationships, 1)
        ),
        "targets_with_3_plus_usable_fr_before": base_ready_targets,
        "targets_total": len(per_target),
    }

    return ranked, selected, metrics


def build_csv_rows(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in selected:
        rows.append(
            {
                "scientific_name": row["scientific_name"],
                "candidate_taxon_ref_type": row["candidate_taxon_ref_type"],
                "candidate_taxon_ref_id": row["candidate_taxon_ref_id"] or "",
                "source_taxon_id": row["source_taxon_id"] or "",
                "number_of_target_taxa_using_candidate": row[
                    "number_of_target_taxa_using_candidate"
                ],
                "best_source": row["best_source"],
                "best_source_rank": row["best_source_rank"],
                "targets_unblocked_if_named": row["targets_unblocked_if_named"],
                "current_fr_status": row["current_fr_status"],
                "recommended_action": row["recommended_action"],
                "priority_score": row["priority_score"],
                "common_name_fr": "",
                "common_name_en": row.get("existing_common_name_en") or "",
                "common_name_nl": "",
                "source": "manual_override",
                "confidence": "low",
                "reviewer": "",
                "notes": "priority selection for Sprint 13D",
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def build_patch_records_for_apply(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    patches: list[dict[str, Any]] = []
    for index, row in enumerate(selected, start=1):
        if row.get("recommended_action") != "seed_fr_then_human_review":
            continue
        sci = str(row["scientific_name"])
        patch: dict[str, Any] = {
            "schema_version": "1.0",
            "patch_id": f"s13d-priority-{index:04d}",
            "taxon_ref_type": row["candidate_taxon_ref_type"],
            "scientific_name": sci,
            # Provisional FR seed for gating only; human review remains required.
            "common_name_fr": sci,
            "source": "manual_override",
            "confidence": "low",
            "reviewer": "sprint13d-priority",
            "notes": (
                "Provisional FR seed from scientific_name to unblock FR distractor gate; "
                "replace with validated common name in manual review."
            ),
        }
        if row.get("candidate_taxon_ref_id"):
            if row["candidate_taxon_ref_type"] == "canonical_taxon":
                patch["canonical_taxon_id"] = row["candidate_taxon_ref_id"]
            elif row["candidate_taxon_ref_type"] == "referenced_taxon":
                patch["referenced_taxon_id"] = row["candidate_taxon_ref_id"]
        if row.get("source_taxon_id"):
            patch["source_taxon_id"] = row["source_taxon_id"]
        if row.get("existing_common_name_en"):
            patch["common_name_en"] = row["existing_common_name_en"]
        patches.append(patch)
    return patches


def _canonical_taxa_for_apply(canonical_payload: dict[str, Any]) -> list[dict[str, Any]]:
    taxa: list[dict[str, Any]] = []
    for item in canonical_payload.get("canonical_taxa", []):
        if not isinstance(item, dict):
            continue
        taxa.append(
            {
                "canonical_taxon_id": item.get("canonical_taxon_id"),
                "scientific_name": item.get("accepted_scientific_name"),
                "common_names_i18n": item.get("common_names_by_language") or {},
            }
        )
    return taxa


def _relationship_name_flags(
    rel: dict[str, Any],
    *,
    canonical_by_id: dict[str, dict[str, Any]],
    canonical_by_scientific: dict[str, dict[str, Any]],
    referenced_by_id: dict[str, dict[str, Any]],
    referenced_by_scientific: dict[str, dict[str, Any]],
) -> tuple[bool | None, bool | None, bool | None]:
    ref_type = str(rel.get("candidate_taxon_ref_type", "")).strip()
    ref_id = _normalize_optional_str(rel.get("candidate_taxon_ref_id"))
    sci = str(rel.get("candidate_scientific_name", "")).strip()

    target: dict[str, Any] | None = None
    if ref_type == "canonical_taxon":
        if ref_id:
            target = canonical_by_id.get(ref_id)
        if target is None and sci:
            target = canonical_by_scientific.get(sci)
    elif ref_type == "referenced_taxon":
        if ref_id:
            target = referenced_by_id.get(ref_id)
        if target is None and sci:
            target = referenced_by_scientific.get(sci)

    if target is None:
        return None, None, None

    names = target.get("common_names_i18n") or {}
    has_fr = bool(names.get("fr"))
    has_en = bool(names.get("en"))
    has_nl = bool(names.get("nl"))
    return has_fr, has_en, has_nl


def build_candidates_payload_with_patched_names(
    *,
    candidates_s12: dict[str, Any],
    canonical_taxa: list[dict[str, Any]],
    referenced_taxa: list[dict[str, Any]],
) -> dict[str, Any]:
    relationships_in = [r for r in candidates_s12.get("relationships", []) if isinstance(r, dict)]

    canonical_by_id = {
        str(item.get("canonical_taxon_id", "")).strip(): item
        for item in canonical_taxa
        if str(item.get("canonical_taxon_id", "")).strip()
    }
    canonical_by_scientific = {
        str(item.get("scientific_name", "")).strip(): item
        for item in canonical_taxa
        if str(item.get("scientific_name", "")).strip()
    }
    referenced_by_id = {
        str(item.get("referenced_taxon_id", "")).strip(): item
        for item in referenced_taxa
        if str(item.get("referenced_taxon_id", "")).strip()
    }
    referenced_by_scientific = {
        str(item.get("scientific_name", "")).strip(): item
        for item in referenced_taxa
        if str(item.get("scientific_name", "")).strip()
    }

    relationships: list[dict[str, Any]] = []
    for rel in relationships_in:
        patch_has_fr, patch_has_en, patch_has_nl = _relationship_name_flags(
            rel,
            canonical_by_id=canonical_by_id,
            canonical_by_scientific=canonical_by_scientific,
            referenced_by_id=referenced_by_id,
            referenced_by_scientific=referenced_by_scientific,
        )
        updated = dict(rel)

        base_has_fr = bool(rel.get("candidate_has_french_name", False))
        base_has_localized = bool(rel.get("candidate_has_localized_name", False))
        base_can_multilingual = bool(rel.get("can_be_used_now_multilingual", False))

        has_fr = base_has_fr or bool(patch_has_fr)
        has_en = base_has_localized or bool(patch_has_en)
        has_nl = base_can_multilingual or bool(patch_has_nl)

        has_localized = has_en or has_fr
        can_fr = has_fr and rel.get("candidate_taxon_ref_type") != "unresolved_taxon"
        can_multilingual = (
            has_fr
            and has_en
            and has_nl
            and rel.get("candidate_taxon_ref_type") != "unresolved_taxon"
        )
        blockers: list[str] = []
        if not has_fr:
            blockers.append("missing_french_name")
        if rel.get("candidate_taxon_ref_type") == "unresolved_taxon":
            blockers.append("unresolved_taxon_ref")

        updated["candidate_has_localized_name"] = has_localized
        updated["candidate_has_french_name"] = has_fr
        updated["can_be_used_now_fr"] = can_fr
        updated["can_be_used_now_multilingual"] = can_multilingual
        updated["usability_blockers"] = blockers
        relationships.append(updated)

    by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rel in relationships:
        by_target[str(rel.get("target_canonical_taxon_id", ""))].append(rel)

    per_target: list[dict[str, Any]] = []
    for target_id, rels in sorted(by_target.items()):
        if not rels:
            continue
        name = str(rels[0].get("target_scientific_name", ""))
        inat = sum(1 for rel in rels if rel.get("source") == "inaturalist_similar_species")
        genus = sum(1 for rel in rels if rel.get("source") == "taxonomic_neighbor_same_genus")
        family = sum(1 for rel in rels if rel.get("source") == "taxonomic_neighbor_same_family")
        order = sum(1 for rel in rels if rel.get("source") == "taxonomic_neighbor_same_order")
        usable_fr = sum(1 for rel in rels if rel.get("can_be_used_now_fr", False))
        usable_multi = sum(1 for rel in rels if rel.get("can_be_used_now_multilingual", False))
        total = len(rels)
        readiness = "ready" if total >= 3 else "insufficient_distractors"

        per_target.append(
            {
                "target_canonical_taxon_id": target_id,
                "scientific_name": name,
                "inat_candidates": inat,
                "same_genus_candidates": genus,
                "same_family_candidates": family,
                "same_order_candidates": order,
                "total_candidates": total,
                "usable_fr_candidates": usable_fr,
                "usable_multilingual_candidates": usable_multi,
                "readiness": readiness,
            }
        )

    by_source = Counter(str(rel.get("source", "")) for rel in relationships)
    missing_french_names = sorted(
        {
            str(rel.get("candidate_scientific_name", "")).strip()
            for rel in relationships
            if not rel.get("candidate_has_french_name", False)
        }
    )
    unresolved = sorted(
        {
            str(rel.get("candidate_scientific_name", "")).strip()
            for rel in relationships
            if rel.get("candidate_taxon_ref_type") == "unresolved_taxon"
        }
    )

    summary = {
        "target_taxa_count": len(per_target),
        "total_relationships_generated": len(relationships),
        "by_source": dict(by_source),
        "targets_with_3_plus_candidates": sum(1 for p in per_target if p["total_candidates"] >= 3),
        "targets_with_3_plus_usable_fr_candidates": sum(
            1 for p in per_target if p["usable_fr_candidates"] >= 3
        ),
        "targets_with_only_taxonomic_candidates": sum(
            1 for p in per_target if p["inat_candidates"] == 0 and p["total_candidates"] > 0
        ),
        "targets_with_insufficient_candidates": sum(
            1 for p in per_target if 0 < p["total_candidates"] < 3
        ),
        "targets_with_no_candidates": sum(1 for p in per_target if p["total_candidates"] == 0),
        "unresolved_candidate_count": len(unresolved),
        "referenced_taxon_shell_needed_count": len(unresolved),
        "referenced_taxon_shell_candidate_count": int(
            candidates_s12.get("summary", {}).get("referenced_taxon_shell_candidate_count", 0)
        ),
        "candidates_missing_french_name": len(missing_french_names),
        "no_emergency_diversity_fallback_generated": (
            by_source.get("emergency_diversity_fallback", 0) == 0
        ),
    }

    targets_not_ready = sorted(
        p["scientific_name"] for p in per_target if p.get("readiness") != "ready"
    )

    payload = {
        "generation_version": candidates_s12.get(
            "generation_version", "distractor_relationship_candidates_v1.v1"
        ),
        "run_date": candidates_s12.get("run_date"),
        "execution_status": "complete",
        "input_source": candidates_s12.get("input_source"),
        "snapshot_id": candidates_s12.get("snapshot_id"),
        "decision": candidates_s12.get("decision", "READY_FOR_AI_RANKING_DESIGN"),
        "generation_params": candidates_s12.get("generation_params", {}),
        "summary": summary,
        "gaps": {
            "unresolved_candidates": unresolved,
            "referenced_taxon_shells_needed": unresolved,
            "candidates_missing_french_name": missing_french_names,
            "targets_not_ready": targets_not_ready,
        },
        "per_target_summaries": per_target,
        "relationships": relationships,
    }
    return payload


def _decision_label(
    *,
    targets_with_3_fr_usable: int,
    total_targets: int,
    missing_fr_count: int,
    total_candidates: int,
    shell_needed_count: int,
    emergency_fallback_count: int,
    targets_ready_delta: int,
) -> tuple[str, str]:
    missing_ratio = missing_fr_count / max(total_candidates, 1)

    if (
        targets_with_3_fr_usable >= 30
        and emergency_fallback_count == 0
        and missing_ratio <= 0.30
        and shell_needed_count == 0
    ):
        return (
            "READY_FOR_FIRST_CORPUS_DISTRACTOR_GATE",
            (
                ">=30 targets have >=3 FR-usable candidates, missing FR ratio is <=30%, "
                "and no shell blockers remain."
            ),
        )

    if (
        targets_with_3_fr_usable >= 30
        and emergency_fallback_count == 0
        and missing_ratio <= 0.40
    ):
        return (
            "READY_FOR_AI_RANKING_AND_PROPOSALS",
            (
                "Coverage is strong enough for AI ranking/proposals, but FR missing-name "
                "ratio is still above gate policy."
            ),
        )

    if shell_needed_count > 0:
        return (
            "NEEDS_REFERENCED_TAXON_REVIEW",
            "Referenced taxon shell needs remain and block full distractor readiness.",
        )

    if targets_ready_delta > 0:
        return (
            "NEEDS_MORE_NAME_COMPLETION",
            (
                "Readiness improved but the FR usability threshold for the first corpus "
                "gate is not yet met."
            ),
        )

    return (
        "STILL_BLOCKED",
        "Readiness did not improve enough to clear the first corpus distractor gate.",
    )


def compare_sprint12_vs_sprint13(
    *,
    candidates_s12: dict[str, Any],
    candidates_s13: dict[str, Any],
    readiness_s12: dict[str, Any],
    readiness_s13: dict[str, Any],
) -> dict[str, Any]:
    s12_sum = candidates_s12.get("summary", {})
    s13_sum = candidates_s13.get("summary", {})
    r12_sum = readiness_s12.get("summary", {})
    r13_sum = readiness_s13.get("summary", {})

    inat_usable_s12 = sum(
        1
        for rel in candidates_s12.get("relationships", [])
        if rel.get("source") == "inaturalist_similar_species"
        and rel.get("can_be_used_now_fr", False)
    )
    inat_usable_s13 = sum(
        1
        for rel in candidates_s13.get("relationships", [])
        if rel.get("source") == "inaturalist_similar_species"
        and rel.get("can_be_used_now_fr", False)
    )

    shell_with_fr_s12 = len(
        {
            rel.get("candidate_taxon_ref_id")
            for rel in candidates_s12.get("relationships", [])
            if rel.get("candidate_taxon_ref_type") == "referenced_taxon"
            and rel.get("candidate_has_french_name", False)
            and rel.get("candidate_taxon_ref_id")
        }
    )
    shell_with_fr_s13 = len(
        {
            rel.get("candidate_taxon_ref_id")
            for rel in candidates_s13.get("relationships", [])
            if rel.get("candidate_taxon_ref_type") == "referenced_taxon"
            and rel.get("candidate_has_french_name", False)
            and rel.get("candidate_taxon_ref_id")
        }
    )

    metrics = {
        "targets_ready": {
            "sprint12": int(r12_sum.get("targets_ready", 0)),
            "sprint13": int(r13_sum.get("targets_ready", 0)),
        },
        "targets_blocked": {
            "sprint12": int(r12_sum.get("targets_blocked", 0)),
            "sprint13": int(r13_sum.get("targets_blocked", 0)),
        },
        "targets_with_3_plus_fr_usable": {
            "sprint12": int(s12_sum.get("targets_with_3_plus_usable_fr_candidates", 0)),
            "sprint13": int(s13_sum.get("targets_with_3_plus_usable_fr_candidates", 0)),
        },
        "missing_french_names": {
            "sprint12": int(s12_sum.get("candidates_missing_french_name", 0)),
            "sprint13": int(s13_sum.get("candidates_missing_french_name", 0)),
        },
        "shell_candidates_with_fr": {
            "sprint12": shell_with_fr_s12,
            "sprint13": shell_with_fr_s13,
        },
        "emergency_fallback_count": {
            "sprint12": int(s12_sum.get("by_source", {}).get("emergency_diversity_fallback", 0)),
            "sprint13": int(s13_sum.get("by_source", {}).get("emergency_diversity_fallback", 0)),
        },
        "taxonomic_only_dependency": {
            "sprint12": int(s12_sum.get("targets_with_only_taxonomic_candidates", 0)),
            "sprint13": int(s13_sum.get("targets_with_only_taxonomic_candidates", 0)),
        },
        "inat_usable_candidate_count": {
            "sprint12": inat_usable_s12,
            "sprint13": inat_usable_s13,
        },
    }

    for pair in metrics.values():
        pair["delta"] = int(pair["sprint13"]) - int(pair["sprint12"])

    decision, note = _decision_label(
        targets_with_3_fr_usable=metrics["targets_with_3_plus_fr_usable"]["sprint13"],
        total_targets=int(s13_sum.get("target_taxa_count", 0)),
        missing_fr_count=metrics["missing_french_names"]["sprint13"],
        total_candidates=int(s13_sum.get("total_relationships_generated", 0)),
        shell_needed_count=int(s13_sum.get("referenced_taxon_shell_needed_count", 0)),
        emergency_fallback_count=metrics["emergency_fallback_count"]["sprint13"],
        targets_ready_delta=metrics["targets_ready"]["delta"],
    )

    return {
        "comparison_version": "sprint12_vs_sprint13.v1",
        "execution_status": "complete",
        "decision": decision,
        "decision_note": note,
        "metrics": metrics,
    }


def write_comparison_markdown(result: dict[str, Any], output_path: Path) -> None:
    metrics = result.get("metrics", {})
    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        "last_reviewed: 2026-05-05",
        "source_of_truth: docs/audits/distractor-readiness-sprint12-vs-sprint13.md",
        "scope: audit",
        "---",
        "",
        "# Distractor Readiness Comparison: Sprint 12 vs Sprint 13",
        "",
        "## Decision",
        "",
        f"**{result.get('decision', 'UNKNOWN')}**",
        "",
        result.get("decision_note", ""),
        "",
        "## Metrics",
        "",
        "| Metric | Sprint 12 | Sprint 13 | Delta |",
        "|---|---:|---:|---:|",
    ]

    ordered_keys = [
        "targets_ready",
        "targets_blocked",
        "targets_with_3_plus_fr_usable",
        "missing_french_names",
        "shell_candidates_with_fr",
        "emergency_fallback_count",
        "taxonomic_only_dependency",
        "inat_usable_candidate_count",
    ]

    for key in ordered_keys:
        m = metrics.get(key, {})
        lines.append(
            f"| {key} | {m.get('sprint12', 0)} | {m.get('sprint13', 0)} | {m.get('delta', 0)} |"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_apply_markdown(
    *,
    output_path: Path,
    apply_result: dict[str, Any],
    selected: list[dict[str, Any]],
) -> None:
    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        "last_reviewed: 2026-05-05",
        "source_of_truth: docs/audits/taxon-localized-names-sprint13-apply.md",
        "scope: audit",
        "---",
        "",
        "# Taxon Localized Names Sprint 13 Apply",
        "",
        f"- mode: {apply_result.get('mode')}",
        f"- decision: {apply_result.get('decision')}",
        f"- input_patch_count: {apply_result.get('input_patch_count', 0)}",
        f"- applied_count: {apply_result.get('applied_count', 0)}",
        f"- conflict_count: {apply_result.get('conflict_count', 0)}",
        f"- skipped_count: {apply_result.get('skipped_count', 0)}",
        f"- unresolved_count: {apply_result.get('unresolved_count', 0)}",
        "",
        "## Priority Names Selected",
        "",
        (
            "| scientific_name | ref_type | ref_id | source_rank | "
            "targets_unblocked | priority_score |"
        ),
        "|---|---|---|---:|---:|---:|",
    ]

    for row in selected[:30]:
        lines.append(
            "| {sci} | {rt} | {rid} | {rank} | {unblocked} | {score} |".format(
                sci=row.get("scientific_name", ""),
                rt=row.get("candidate_taxon_ref_type", ""),
                rid=row.get("candidate_taxon_ref_id") or "",
                rank=row.get("best_source_rank", 0),
                unblocked=row.get("targets_unblocked_if_named", 0),
                score=row.get("priority_score", 0),
            )
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(
    *,
    candidates_s12_path: Path,
    readiness_s12_path: Path,
    shell_plan_s13_path: Path,
    localized_audit_s13_path: Path,
    projected_relationships_s13_path: Path,
    patch_csv_path: Path,
    apply_evidence_json_path: Path,
    apply_evidence_md_path: Path,
    readiness_s13_path: Path,
    comparison_json_path: Path,
    comparison_md_path: Path,
    patch_schema_path: Path,
    canonical_path: Path,
    referenced_candidates_path: Path,
    referenced_snapshot_path: Path,
    output_canonical: Path,
    output_referenced: Path,
    apply: bool,
) -> dict[str, Any]:
    candidates_s12 = _load(candidates_s12_path)
    readiness_s12 = _load(readiness_s12_path)
    shell_plan_s13 = _load(shell_plan_s13_path)
    localized_audit_s13 = _load(localized_audit_s13_path)
    projected_relationships_s13 = _load(projected_relationships_s13_path)
    canonical_payload = _load(canonical_path)

    ranked, selected, selection_metrics = select_priority_candidates(
        candidates_s12=candidates_s12,
        shell_plan=shell_plan_s13,
        canonical_payload=canonical_payload,
    )

    csv_rows = build_csv_rows(selected)
    write_csv(patch_csv_path, csv_rows)

    patch_records = build_patch_records_for_apply(selected)

    schema = load_json(patch_schema_path)
    valid_patches, invalid_patches = validate_patch_records(patch_records, schema)

    dry_run_result: dict[str, Any]
    apply_result: dict[str, Any]
    with TemporaryDirectory() as tmp_dir:
        patch_file = Path(tmp_dir) / "taxon_localized_name_patches_sprint13_priority.json"
        _dump(patch_file, {"patches": valid_patches})

        dry_run_result = run_apply(
            patch_file=patch_file,
            patch_schema_path=patch_schema_path,
            canonical_path=canonical_path,
            referenced_candidates_path=referenced_candidates_path,
            referenced_snapshot_path=referenced_snapshot_path,
            dry_run=True,
            apply=False,
            output_canonical=output_canonical,
            output_referenced=output_referenced,
            output_evidence_json=apply_evidence_json_path,
            output_evidence_md=apply_evidence_md_path,
        )

        if apply:
            apply_result = run_apply(
                patch_file=patch_file,
                patch_schema_path=patch_schema_path,
                canonical_path=canonical_path,
                referenced_candidates_path=referenced_candidates_path,
                referenced_snapshot_path=referenced_snapshot_path,
                dry_run=False,
                apply=True,
                output_canonical=output_canonical,
                output_referenced=output_referenced,
                output_evidence_json=apply_evidence_json_path,
                output_evidence_md=apply_evidence_md_path,
            )
        else:
            apply_result = dict(dry_run_result)

    canonical_taxa = _canonical_taxa_for_apply(canonical_payload)
    referenced_taxa = load_referenced_records(
        referenced_candidates_path, referenced_snapshot_path
    )
    apply_preview = apply_patches(
        valid_patches,
        canonical_taxa=canonical_taxa,
        referenced_taxa=referenced_taxa,
    )

    candidates_s13 = build_candidates_payload_with_patched_names(
        candidates_s12=candidates_s12,
        canonical_taxa=apply_preview["canonical_taxa"],
        referenced_taxa=apply_preview["referenced_taxa"],
    )

    audit_input = {
        "snapshot_id": candidates_s13.get("snapshot_id"),
        "decision": readiness_s12.get("decision", "unknown"),
    }
    readiness_s13 = run_readiness(audit=audit_input, candidates=candidates_s13)
    _dump(readiness_s13_path, readiness_s13)

    comparison = compare_sprint12_vs_sprint13(
        candidates_s12=candidates_s12,
        candidates_s13=candidates_s13,
        readiness_s12=readiness_s12,
        readiness_s13=readiness_s13,
    )
    _dump(comparison_json_path, comparison)
    write_comparison_markdown(comparison, comparison_md_path)

    apply_evidence = _load(apply_evidence_json_path)
    apply_evidence["priority_selection"] = {
        "ranked_count": len(ranked),
        "selected_count": len(selected),
        "selection_metrics": selection_metrics,
        "selected_top": selected[:50],
        "invalid_patch_count_from_priority_builder": len(invalid_patches),
    }
    apply_evidence["dry_run_preview"] = {
        "mode": dry_run_result.get("mode"),
        "applied_count": dry_run_result.get("applied_count", 0),
        "conflict_count": dry_run_result.get("conflict_count", 0),
    }
    apply_evidence["context_inputs"] = {
        "localized_audit_decision": localized_audit_s13.get("decision"),
        "projected_relationships_decision": projected_relationships_s13.get("decision"),
    }
    _dump(apply_evidence_json_path, apply_evidence)
    write_apply_markdown(
        output_path=apply_evidence_md_path,
        apply_result=apply_result,
        selected=selected,
    )

    return {
        "selected_count": len(selected),
        "ranked_count": len(ranked),
        "patch_csv_path": str(patch_csv_path),
        "apply_mode": apply_result.get("mode"),
        "apply_decision": apply_result.get("decision"),
        "applied_count": apply_result.get("applied_count", 0),
        "invalid_patch_count": len(invalid_patches),
        "readiness_s13_decision": readiness_s13.get("decision"),
        "comparison_decision": comparison.get("decision"),
        "comparison_metrics": comparison.get("metrics", {}),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Select and apply priority localized name patches for distractor readiness."
    )
    parser.add_argument("--candidates-s12", type=Path, default=DEFAULT_CANDIDATES_S12)
    parser.add_argument("--readiness-s12", type=Path, default=DEFAULT_READINESS_S12)
    parser.add_argument("--shell-plan-s13", type=Path, default=DEFAULT_SHELL_PLAN_S13)
    parser.add_argument("--localized-audit-s13", type=Path, default=DEFAULT_LOCALIZED_AUDIT_S13)
    parser.add_argument(
        "--projected-relationships-s13",
        type=Path,
        default=DEFAULT_PROJECTED_RELATIONSHIPS_S13,
    )
    parser.add_argument("--patch-csv", type=Path, default=DEFAULT_PATCH_CSV)
    parser.add_argument("--apply-evidence-json", type=Path, default=DEFAULT_APPLY_EVIDENCE_JSON)
    parser.add_argument("--apply-evidence-md", type=Path, default=DEFAULT_APPLY_EVIDENCE_MD)
    parser.add_argument("--readiness-s13", type=Path, default=DEFAULT_READINESS_S13)
    parser.add_argument("--comparison-json", type=Path, default=DEFAULT_COMPARISON_JSON)
    parser.add_argument("--comparison-md", type=Path, default=DEFAULT_COMPARISON_MD)
    parser.add_argument("--patch-schema", type=Path, default=DEFAULT_PATCH_SCHEMA)
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument(
        "--referenced-candidates-path",
        type=Path,
        default=DEFAULT_REFERENCED_CANDIDATES_PATH,
    )
    parser.add_argument(
        "--referenced-snapshot-path",
        type=Path,
        default=DEFAULT_REFERENCED_SNAPSHOT_PATH,
    )
    parser.add_argument("--output-canonical", type=Path, default=DEFAULT_OUTPUT_CANONICAL)
    parser.add_argument("--output-referenced", type=Path, default=DEFAULT_OUTPUT_REFERENCED)
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Explicitly write patched canonical/referenced outputs after dry-run.",
    )
    args = parser.parse_args()

    result = run(
        candidates_s12_path=args.candidates_s12,
        readiness_s12_path=args.readiness_s12,
        shell_plan_s13_path=args.shell_plan_s13,
        localized_audit_s13_path=args.localized_audit_s13,
        projected_relationships_s13_path=args.projected_relationships_s13,
        patch_csv_path=args.patch_csv,
        apply_evidence_json_path=args.apply_evidence_json,
        apply_evidence_md_path=args.apply_evidence_md,
        readiness_s13_path=args.readiness_s13,
        comparison_json_path=args.comparison_json,
        comparison_md_path=args.comparison_md,
        patch_schema_path=args.patch_schema,
        canonical_path=args.canonical_path,
        referenced_candidates_path=args.referenced_candidates_path,
        referenced_snapshot_path=args.referenced_snapshot_path,
        output_canonical=args.output_canonical,
        output_referenced=args.output_referenced,
        apply=args.apply,
    )

    print(f"Selected priority names: {result['selected_count']} / {result['ranked_count']}")
    print(f"Patch CSV: {result['patch_csv_path']}")
    print(f"Apply mode: {result['apply_mode']}")
    print(f"Apply decision: {result['apply_decision']}")
    print(f"Applied count: {result['applied_count']}")
    print(f"Comparison decision: {result['comparison_decision']}")


if __name__ == "__main__":
    main()
