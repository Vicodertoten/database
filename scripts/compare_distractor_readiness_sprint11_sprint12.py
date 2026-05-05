"""Compare Sprint 11 and Sprint 12 distractor candidates/readiness evidence."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CANDIDATES_S11 = (
    REPO_ROOT / "docs" / "audits" / "evidence" / "distractor_relationship_candidates_v1.json"
)
DEFAULT_CANDIDATES_S12 = (
    REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "distractor_relationship_candidates_v1_sprint12.json"
)
DEFAULT_READINESS_S11 = (
    REPO_ROOT / "docs" / "audits" / "evidence" / "distractor_readiness_v1.json"
)
DEFAULT_READINESS_S12 = (
    REPO_ROOT / "docs" / "audits" / "evidence" / "distractor_readiness_v1_sprint12.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "distractor_readiness_sprint11_vs_sprint12.json"
)
DEFAULT_OUTPUT_MD = REPO_ROOT / "docs" / "audits" / "distractor-readiness-sprint11-vs-sprint12.md"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _delta(a: int, b: int) -> int:
    return b - a


def _decision_label(
    *,
    targets_ready_s12: int,
    targets_with_3_fr_s12: int,
    total_targets_s12: int,
    inat_count_s12: int,
    same_genus_count_s12: int,
    missing_french_names_s12: int,
    total_candidates_s12: int,
    referenced_shells_needed_s12: int,
    emergency_fallback_count_s12: int,
    iNat_improved: bool,
    fr_improved: bool,
    targets_ready_improved: bool,
) -> tuple[str, str]:
    meaningful_source_share = 0.0
    if total_targets_s12 > 0:
        meaningful_source_share = (inat_count_s12 + same_genus_count_s12) / max(
            total_targets_s12, 1
        )

    missing_names_ratio = 1.0
    if total_candidates_s12 > 0:
        missing_names_ratio = missing_french_names_s12 / total_candidates_s12

    if (
        targets_with_3_fr_s12 >= 30
        and emergency_fallback_count_s12 == 0
        and meaningful_source_share >= 0.4
        and missing_names_ratio <= 0.3
    ):
        return (
            "READY_FOR_FIRST_CORPUS_DISTRACTOR_GATE",
            "At least 30 targets have >=3 FR-usable candidates with no emergency fallback.",
        )

    if referenced_shells_needed_s12 > 0:
        return (
            "NEEDS_REFERENCED_TAXON_REVIEW",
            "Referenced taxon shells are still needed before full distractor readiness.",
        )

    if missing_names_ratio > 0.3:
        return (
            "NEEDS_MORE_TAXON_NAME_ENRICHMENT",
            "Missing French names still dominate candidate coverage.",
        )

    if inat_count_s12 == 0 or not iNat_improved:
        return (
            "NEEDS_MORE_INAT_ENRICHMENT",
            "iNaturalist similar-species coverage remains insufficient.",
        )

    if fr_improved or targets_ready_improved:
        return (
            "READY_FOR_AI_RANKING_AND_PROPOSALS",
            "Coverage improved meaningfully; AI ranking/proposals can proceed safely.",
        )

    if targets_ready_s12 > 0 and referenced_shells_needed_s12 == 0:
        return (
            "READY_FOR_PERSISTENCE",
            "Candidate relationship set appears stable for persistence planning.",
        )

    return (
        "STILL_BLOCKED",
        "No material improvement in readiness metrics versus Sprint 11 baseline.",
    )


def compare(
    *,
    candidates_s11: dict[str, Any],
    candidates_s12: dict[str, Any],
    readiness_s11: dict[str, Any],
    readiness_s12: dict[str, Any],
) -> dict[str, Any]:
    s11_sum = candidates_s11.get("summary", {})
    s12_sum = candidates_s12.get("summary", {})
    r11_sum = readiness_s11.get("summary", {})
    r12_sum = readiness_s12.get("summary", {})

    by_source_11 = s11_sum.get("by_source", {})
    by_source_12 = s12_sum.get("by_source", {})

    inat_11 = int(by_source_11.get("inaturalist_similar_species", 0))
    inat_12 = int(by_source_12.get("inaturalist_similar_species", 0))

    total_c11 = int(s11_sum.get("total_relationships_generated", 0))
    total_c12 = int(s12_sum.get("total_relationships_generated", 0))

    fr_ready_11 = int(s11_sum.get("targets_with_3_plus_usable_fr_candidates", 0))
    fr_ready_12 = int(s12_sum.get("targets_with_3_plus_usable_fr_candidates", 0))

    targets_3plus_11 = int(s11_sum.get("targets_with_3_plus_candidates", 0))
    targets_3plus_12 = int(s12_sum.get("targets_with_3_plus_candidates", 0))

    missing_fr_11 = int(s11_sum.get("candidates_missing_french_name", 0))
    missing_fr_12 = int(s12_sum.get("candidates_missing_french_name", 0))

    shells_needed_11 = int(s11_sum.get("referenced_taxon_shell_needed_count", 0))
    shells_needed_12 = int(s12_sum.get("referenced_taxon_shell_needed_count", 0))

    no_candidates_11 = int(s11_sum.get("targets_with_no_candidates", 0))
    no_candidates_12 = int(s12_sum.get("targets_with_no_candidates", 0))

    taxonomic_only_11 = int(s11_sum.get("targets_with_only_taxonomic_candidates", 0))
    taxonomic_only_12 = int(s12_sum.get("targets_with_only_taxonomic_candidates", 0))

    # same-order dependency from per-target summaries
    per_t11 = candidates_s11.get("per_target_summaries", [])
    per_t12 = candidates_s12.get("per_target_summaries", [])
    same_order_dep_11 = sum(1 for t in per_t11 if int(t.get("same_order_candidates", 0)) > 0)
    same_order_dep_12 = sum(1 for t in per_t12 if int(t.get("same_order_candidates", 0)) > 0)

    ready_targets_11 = int(r11_sum.get("targets_ready", 0))
    ready_targets_12 = int(r12_sum.get("targets_ready", 0))
    blocked_targets_11 = int(r11_sum.get("targets_blocked", 0))
    blocked_targets_12 = int(r12_sum.get("targets_blocked", 0))

    emergency_fallback_count_12 = int(by_source_12.get("emergency_diversity_fallback", 0))

    iNat_improved = inat_12 > inat_11
    fr_improved = fr_ready_12 > fr_ready_11
    targets_ready_improved = ready_targets_12 > ready_targets_11

    decision, decision_note = _decision_label(
        targets_ready_s12=ready_targets_12,
        targets_with_3_fr_s12=fr_ready_12,
        total_targets_s12=int(s12_sum.get("target_taxa_count", 0)),
        inat_count_s12=inat_12,
        same_genus_count_s12=int(by_source_12.get("taxonomic_neighbor_same_genus", 0)),
        missing_french_names_s12=missing_fr_12,
        total_candidates_s12=total_c12,
        referenced_shells_needed_s12=shells_needed_12,
        emergency_fallback_count_s12=emergency_fallback_count_12,
        iNat_improved=iNat_improved,
        fr_improved=fr_improved,
        targets_ready_improved=targets_ready_improved,
    )

    return {
        "comparison_version": "sprint11_vs_sprint12.v1",
        "run_date": datetime.now(UTC).isoformat(),
        "execution_status": "complete",
        "decision": decision,
        "decision_note": decision_note,
        "metrics": {
            "inat_similar_count": {
                "sprint11": inat_11,
                "sprint12": inat_12,
                "delta": _delta(inat_11, inat_12),
            },
            "total_candidates": {
                "sprint11": total_c11,
                "sprint12": total_c12,
                "delta": _delta(total_c11, total_c12),
            },
            "source_distribution": {
                "sprint11": by_source_11,
                "sprint12": by_source_12,
            },
            "targets_ready": {
                "sprint11": ready_targets_11,
                "sprint12": ready_targets_12,
                "delta": _delta(ready_targets_11, ready_targets_12),
            },
            "targets_blocked": {
                "sprint11": blocked_targets_11,
                "sprint12": blocked_targets_12,
                "delta": _delta(blocked_targets_11, blocked_targets_12),
            },
            "targets_with_3_plus_candidates": {
                "sprint11": targets_3plus_11,
                "sprint12": targets_3plus_12,
                "delta": _delta(targets_3plus_11, targets_3plus_12),
            },
            "targets_with_3_plus_fr_usable": {
                "sprint11": fr_ready_11,
                "sprint12": fr_ready_12,
                "delta": _delta(fr_ready_11, fr_ready_12),
            },
            "missing_french_names": {
                "sprint11": missing_fr_11,
                "sprint12": missing_fr_12,
                "delta": _delta(missing_fr_11, missing_fr_12),
            },
            "referenced_shells_needed": {
                "sprint11": shells_needed_11,
                "sprint12": shells_needed_12,
                "delta": _delta(shells_needed_11, shells_needed_12),
            },
            "targets_with_no_candidates": {
                "sprint11": no_candidates_11,
                "sprint12": no_candidates_12,
                "delta": _delta(no_candidates_11, no_candidates_12),
            },
            "taxonomic_only_dependency": {
                "sprint11": taxonomic_only_11,
                "sprint12": taxonomic_only_12,
                "delta": _delta(taxonomic_only_11, taxonomic_only_12),
            },
            "same_order_dependency": {
                "sprint11": same_order_dep_11,
                "sprint12": same_order_dep_12,
                "delta": _delta(same_order_dep_11, same_order_dep_12),
            },
            "no_emergency_diversity_fallback_generated": {
                "sprint11": int(by_source_11.get("emergency_diversity_fallback", 0)) == 0,
                "sprint12": emergency_fallback_count_12 == 0,
            },
        },
    }


def write_markdown(result: dict[str, Any], output_path: Path) -> None:
    run_date = result["run_date"][:10]
    metrics = result["metrics"]

    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        f"last_reviewed: {run_date}",
        "source_of_truth: docs/audits/distractor-readiness-sprint11-vs-sprint12.md",
        "scope: audit",
        "---",
        "",
        "# Distractor Readiness Comparison: Sprint 11 vs Sprint 12",
        "",
        "## Decision",
        "",
        f"**{result['decision']}**",
        "",
        result.get("decision_note", ""),
        "",
        "## Metric Comparison",
        "",
        "| Metric | Sprint 11 | Sprint 12 | Delta |",
        "|---|---:|---:|---:|",
    ]

    key_order = [
        "inat_similar_count",
        "total_candidates",
        "targets_ready",
        "targets_blocked",
        "targets_with_3_plus_candidates",
        "targets_with_3_plus_fr_usable",
        "missing_french_names",
        "referenced_shells_needed",
        "targets_with_no_candidates",
        "taxonomic_only_dependency",
        "same_order_dependency",
    ]
    labels = {
        "inat_similar_count": "iNat similar count",
        "total_candidates": "Total candidates",
        "targets_ready": "Targets ready",
        "targets_blocked": "Targets blocked",
        "targets_with_3_plus_candidates": "Targets with >=3 candidates",
        "targets_with_3_plus_fr_usable": "Targets with >=3 FR-usable",
        "missing_french_names": "Missing French names",
        "referenced_shells_needed": "Referenced shells needed",
        "targets_with_no_candidates": "No candidates",
        "taxonomic_only_dependency": "Taxonomic-only dependency",
        "same_order_dependency": "Same-order dependency",
    }

    for key in key_order:
        item = metrics[key]
        lines.append(
            f"| {labels[key]} | {item['sprint11']} | {item['sprint12']} | {item['delta']} |"
        )

    lines += [
        "",
        "## Source Distribution",
        "",
        "- Sprint 11:",
        f"  {json.dumps(metrics['source_distribution']['sprint11'], ensure_ascii=True)}",
        "- Sprint 12:",
        f"  {json.dumps(metrics['source_distribution']['sprint12'], ensure_ascii=True)}",
        "",
        "## Guardrail Check",
        "",
        (
            "- No emergency diversity fallback generated in Sprint 12: Yes"
            if metrics["no_emergency_diversity_fallback_generated"]["sprint12"]
            else "- No emergency diversity fallback generated in Sprint 12: No"
        ),
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare Sprint 11 vs Sprint 12 distractor candidates/readiness"
    )
    parser.add_argument("--candidates-sprint11", type=Path, default=DEFAULT_CANDIDATES_S11)
    parser.add_argument("--candidates-sprint12", type=Path, default=DEFAULT_CANDIDATES_S12)
    parser.add_argument("--readiness-sprint11", type=Path, default=DEFAULT_READINESS_S11)
    parser.add_argument("--readiness-sprint12", type=Path, default=DEFAULT_READINESS_S12)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    args = parser.parse_args(argv)

    c11 = _load(args.candidates_sprint11)
    c12 = _load(args.candidates_sprint12)
    r11 = _load(args.readiness_sprint11)
    r12 = _load(args.readiness_sprint12)

    result = compare(
        candidates_s11=c11,
        candidates_s12=c12,
        readiness_s11=r11,
        readiness_s12=r12,
    )

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_markdown(result, args.output_md)

    print(f"Decision: {result['decision']}")
    print(f"JSON: {args.output_json}")
    print(f"MD:   {args.output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
