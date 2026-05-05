"""
Build distractor readiness synthesis for Sprint 11.

Reads:
  - docs/audits/evidence/distractor_v1_current_state_audit.json
  - docs/audits/evidence/distractor_relationship_candidates_v1.json

Produces:
  - docs/audits/evidence/distractor_readiness_v1.json
  - docs/audits/distractor-readiness-v1.md

Does NOT persist relationships, modify runtime, packs, or run AI.

Usage:
    python scripts/build_distractor_readiness_v1.py
    python scripts/build_distractor_readiness_v1.py \\
        --audit-json docs/audits/evidence/distractor_v1_current_state_audit.json \\
        --candidates-json docs/audits/evidence/distractor_relationship_candidates_v1.json \\
        --output-json docs/audits/evidence/distractor_readiness_v1.json \\
        --output-md  docs/audits/distractor-readiness-v1.md
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_AUDIT_JSON = (
    REPO_ROOT / "docs" / "audits" / "evidence" / "distractor_v1_current_state_audit.json"
)
DEFAULT_CANDIDATES_JSON = (
    REPO_ROOT / "docs" / "audits" / "evidence" / "distractor_relationship_candidates_v1.json"
)
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "docs" / "audits" / "evidence" / "distractor_readiness_v1.json"
)
DEFAULT_OUTPUT_MD = REPO_ROOT / "docs" / "audits" / "distractor-readiness-v1.md"

# Thresholds
FR_READY_THRESHOLD = 3
STRONG_SOURCES = {
    "inaturalist_similar_species",
    "taxonomic_neighbor_same_genus",
    "taxonomic_neighbor_same_family",
}

# ---------------------------------------------------------------------------
# Per-target readiness logic
# ---------------------------------------------------------------------------


def _strongest_source(sources: Counter) -> str:
    """Return the highest-priority source present in the candidate set."""
    priority = [
        "inaturalist_similar_species",
        "taxonomic_neighbor_same_genus",
        "taxonomic_neighbor_same_family",
        "taxonomic_neighbor_same_order",
        "ai_pedagogical_proposal",
        "manual_expert",
        "emergency_diversity_fallback",
    ]
    for s in priority:
        if sources.get(s, 0) > 0:
            return s
    return "none"


def _compute_target_readiness(
    target_id: str,
    name: str,
    rels: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute per-target readiness from its relationship list."""
    total = len(rels)
    sources: Counter = Counter(r["source"] for r in rels)
    inat = sources.get("inaturalist_similar_species", 0)
    genus = sources.get("taxonomic_neighbor_same_genus", 0)
    family = sources.get("taxonomic_neighbor_same_family", 0)
    order = sources.get("taxonomic_neighbor_same_order", 0)
    taxonomic = genus + family + order
    unresolved = sum(
        1 for r in rels if r.get("candidate_taxon_ref_type") == "unresolved_taxon"
    )
    missing_fr = sum(
        1 for r in rels if not r.get("candidate_has_french_name", False)
    )
    usable_fr = sum(1 for r in rels if r.get("can_be_used_now_fr", False))
    has_strong_source = bool(STRONG_SOURCES & set(sources.keys()))
    all_unresolved = total > 0 and unresolved == total
    has_emergency_fallback_only = total > 0 and all(
        r["source"] == "emergency_diversity_fallback" for r in rels
    )

    reasons: list[str] = []

    if total == 0:
        status = "no_candidates"
        reasons.append("no_candidates_found")
    elif all_unresolved:
        status = "needs_review"
        reasons.append("all_candidates_unresolved")
    elif (
        usable_fr >= FR_READY_THRESHOLD
        and has_strong_source
        and not has_emergency_fallback_only
        and not all_unresolved
    ):
        status = "ready_for_first_corpus_distractor_gate"
    elif total >= FR_READY_THRESHOLD and has_strong_source and missing_fr > 0:
        status = "missing_localized_names"
        reasons.append("candidates_exist_but_no_french_label")
    elif total >= FR_READY_THRESHOLD and not has_strong_source:
        status = "ready_with_taxonomic_fallback"
        reasons.append("only_same_order_or_weak_source")
    elif total > 0 and total < FR_READY_THRESHOLD and inat == 0:
        status = "needs_inat_enrichment"
        reasons.append("insufficient_candidates_no_inat_hints")
    elif total > 0 and unresolved > 0:
        status = "needs_referenced_taxon_shells"
        reasons.append("some_candidates_unresolved")
    elif total > 0:
        status = "insufficient_distractors"
        reasons.append(f"only_{total}_total_candidates")
    else:
        status = "needs_review"
        reasons.append("uncategorised")

    return {
        "target_canonical_taxon_id": target_id,
        "scientific_name": name,
        "total_candidate_relationships": total,
        "usable_fr_candidate_count": usable_fr,
        "inat_candidate_count": inat,
        "taxonomic_candidate_count": taxonomic,
        "unresolved_candidate_count": unresolved,
        "missing_french_name_count": missing_fr,
        "strongest_source": _strongest_source(sources),
        "readiness_status": status,
        "readiness_reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Core synthesis
# ---------------------------------------------------------------------------


def run_readiness(
    *,
    audit: dict[str, Any],
    candidates: dict[str, Any],
) -> dict[str, Any]:
    """Synthesise per-target readiness from audit + candidates data."""

    snapshot_id = candidates.get("snapshot_id", audit.get("snapshot_id", "unknown"))
    today = str(date.today())

    # Build per-target relationship index from candidates
    rels_by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in candidates.get("relationships", []):
        rels_by_target[r["target_canonical_taxon_id"]].append(r)

    # Per-target summaries from candidates drive readiness
    per_target_results: list[dict[str, Any]] = []
    status_counts: Counter = Counter()

    for pts in candidates.get("per_target_summaries", []):
        tid = pts["target_canonical_taxon_id"]
        name = pts["scientific_name"]
        rels = rels_by_target.get(tid, [])
        result = _compute_target_readiness(tid, name, rels)
        per_target_results.append(result)
        status_counts[result["readiness_status"]] += 1

    n = len(per_target_results)
    ready = status_counts.get("ready_for_first_corpus_distractor_gate", 0)
    missing_loc = status_counts.get("missing_localized_names", 0)
    taxo_fallback = status_counts.get("ready_with_taxonomic_fallback", 0)
    insufficient = status_counts.get("insufficient_distractors", 0)
    needs_inat = status_counts.get("needs_inat_enrichment", 0)
    needs_ref = status_counts.get("needs_referenced_taxon_shells", 0)
    no_cand = status_counts.get("no_candidates", 0)
    needs_review = status_counts.get("needs_review", 0)

    blocked = n - ready

    # Source totals from candidates summary
    cand_summary = candidates.get("summary", {})
    by_source = cand_summary.get("by_source", {})
    total_rels = cand_summary.get("total_relationships_generated", 0)
    inat_total = by_source.get("inaturalist_similar_species", 0)

    # Gaps
    gaps_from_candidates = candidates.get("gaps", {})
    missing_fr_names = gaps_from_candidates.get("candidates_missing_french_name", [])
    ref_shells_needed = gaps_from_candidates.get("referenced_taxon_shells_needed", [])
    unresolved = gaps_from_candidates.get("unresolved_candidates", [])
    targets_not_ready = gaps_from_candidates.get("targets_not_ready", [])

    # Determine final decision
    if ready > 0 and missing_loc == 0:
        decision = "READY_FOR_FIRST_CORPUS_DISTRACTOR_GATE"
    elif inat_total == 0 and n > 0:
        decision = "NEEDS_TAXON_ENRICHMENT_BEFORE_DISTRACTORS"
    elif len(ref_shells_needed) > 0:
        decision = "READY_FOR_REFERENCED_TAXON_HARVEST"
    elif missing_loc > n // 2:
        decision = "NEEDS_AI_PROPOSAL_PHASE"
    else:
        decision = "INSUFFICIENT_DISTRACTOR_COVERAGE"

    return {
        "synthesis_version": "distractor_readiness_v1.v1",
        "run_date": today,
        "snapshot_id": snapshot_id,
        "execution_status": "complete",
        "decision": decision,
        "summary": {
            "target_taxa_count": n,
            "total_candidate_relationships": total_rels,
            "targets_ready": ready,
            "targets_blocked": blocked,
            "targets_missing_localized_names": missing_loc,
            "targets_ready_with_taxonomic_fallback": taxo_fallback,
            "targets_insufficient_distractors": insufficient,
            "targets_needs_inat_enrichment": needs_inat,
            "targets_needs_referenced_taxon_shells": needs_ref,
            "targets_no_candidates": no_cand,
            "targets_needs_review": needs_review,
        },
        "source_distribution": {
            "inaturalist_similar_species": inat_total,
            "taxonomic_neighbor_same_genus": by_source.get("taxonomic_neighbor_same_genus", 0),
            "taxonomic_neighbor_same_family": by_source.get("taxonomic_neighbor_same_family", 0),
            "taxonomic_neighbor_same_order": by_source.get("taxonomic_neighbor_same_order", 0),
        },
        "gaps": {
            "unresolved_candidates": unresolved,
            "referenced_taxon_shells_needed": ref_shells_needed,
            "candidates_missing_french_name_count": len(missing_fr_names),
            "targets_not_ready": targets_not_ready,
        },
        "audit_input_decision": audit.get("decision", "unknown"),
        "candidates_input_decision": candidates.get("decision", "unknown"),
        "per_target_readiness": per_target_results,
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def _write_markdown(result: dict[str, Any], output_path: Path) -> None:
    today = result.get("run_date", str(date.today()))
    decision = result.get("decision", "UNKNOWN")
    snapshot_id = result.get("snapshot_id", "unknown")
    summary = result.get("summary", {})
    src = result.get("source_distribution", {})
    gaps = result.get("gaps", {})
    per_target = result.get("per_target_readiness", [])

    n = summary.get("target_taxa_count", 0)
    ready = summary.get("targets_ready", 0)
    blocked = summary.get("targets_blocked", 0)
    missing_loc = summary.get("targets_missing_localized_names", 0)
    taxo_fallback = summary.get("targets_ready_with_taxonomic_fallback", 0)
    insufficient = summary.get("targets_insufficient_distractors", 0)
    needs_inat = summary.get("targets_needs_inat_enrichment", 0)
    no_cand = summary.get("targets_no_candidates", 0)
    total_rels = summary.get("total_candidate_relationships", 0)

    inat = src.get("inaturalist_similar_species", 0)
    genus = src.get("taxonomic_neighbor_same_genus", 0)
    family = src.get("taxonomic_neighbor_same_family", 0)
    order = src.get("taxonomic_neighbor_same_order", 0)

    unresolved_count = len(gaps.get("unresolved_candidates", []))
    ref_needed = len(gaps.get("referenced_taxon_shells_needed", []))
    missing_fr_count = gaps.get("candidates_missing_french_name_count", 0)

    status_counts: Counter = Counter(t["readiness_status"] for t in per_target)

    lines: list[str] = [
        "---",
        "owner: vicodertoten",
        "status: ready_for_validation",
        f"last_reviewed: {today}",
        "source_of_truth: docs/audits/evidence/distractor_readiness_v1.json",
        "scope: distractor_readiness_v1",
        "---",
        "",
        "# Distractor Readiness V1",
        "",
        "## Purpose",
        "",
        "Synthesis of Sprint 11 distractor relationship work.",
        "Combines the current-state audit and candidate generation results into",
        "a per-target readiness assessment for the first corpus distractor gate.",
        "",
        "This report does not persist any relationships, modify runtime, packs, or run AI.",
        "",
        "---",
        "",
        "## Inputs",
        "",
        "- `docs/audits/evidence/distractor_v1_current_state_audit.json`",
        "- `docs/audits/evidence/distractor_relationship_candidates_v1.json`",
        f"- Snapshot: `{snapshot_id}`",
        "",
        "---",
        "",
        "## Decision",
        "",
        f"**{decision}**",
        "",
        "Audit input decision: "
        f"`{result.get('audit_input_decision', 'unknown')}`",
        "Candidates input decision: "
        f"`{result.get('candidates_input_decision', 'unknown')}`",
        "",
        "---",
        "",
        "## Target Readiness Summary",
        "",
        "| Readiness status | Count |",
        "|---|---|",
        f"| ready_for_first_corpus_distractor_gate | "
        f"{status_counts.get('ready_for_first_corpus_distractor_gate', 0)} |",
        f"| missing_localized_names | {status_counts.get('missing_localized_names', 0)} |",
        f"| ready_with_taxonomic_fallback | "
        f"{status_counts.get('ready_with_taxonomic_fallback', 0)} |",
        f"| needs_inat_enrichment | {status_counts.get('needs_inat_enrichment', 0)} |",
        f"| insufficient_distractors | {status_counts.get('insufficient_distractors', 0)} |",
        f"| needs_referenced_taxon_shells | "
        f"{status_counts.get('needs_referenced_taxon_shells', 0)} |",
        f"| no_candidates | {status_counts.get('no_candidates', 0)} |",
        f"| needs_review | {status_counts.get('needs_review', 0)} |",
        f"| **Total** | **{n}** |",
        "",
        "---",
        "",
        "## Source Coverage",
        "",
        f"Total candidate relationships: **{total_rels}**",
        "",
        "| Source | Relationships |",
        "|---|---|",
        f"| iNaturalist similar species | {inat} |",
        f"| Taxonomic neighbor — same genus | {genus} |",
        f"| Taxonomic neighbor — same family | {family} |",
        f"| Taxonomic neighbor — same order | {order} |",
        "",
        "---",
        "",
        "## iNaturalist Coverage",
        "",
        f"iNaturalist similar-species hints: **{inat}**",
        "",
        (
            "No iNat similar-species hints have been populated yet. "
            "All existing candidates come from taxonomic neighbors."
            if inat == 0
            else f"{inat} iNat hints available."
        ),
        "",
        "The iNat enrichment pass must be triggered to unlock higher-quality candidates.",
        "",
        "---",
        "",
        "## Taxonomic Fallback Coverage",
        "",
        f"- Targets with ≥3 candidates (taxonomic only): {taxo_fallback + ready}",
        f"- Targets with insufficient taxonomic candidates: {insufficient + needs_inat}",
        f"- Targets with no candidates at all: {no_cand}",
        "",
        "---",
        "",
        "## Unresolved / Reference Shell Needs",
        "",
        f"- Unresolved candidates (no canonical or referenced record): **{unresolved_count}**",
        f"- Referenced taxon shells needed: **{ref_needed}**",
        "",
        "---",
        "",
        "## Localization Gaps",
        "",
        f"- Candidates missing French name: **{missing_fr_count}**",
        f"- Targets missing localized names (blocking FR readiness): **{missing_loc}**",
        "",
        "French name is the minimum label requirement for the first Belgian/francophone corpus.",
        "",
        "---",
        "",
        "## First Corpus Implications",
        "",
        f"- **{ready}** target(s) are ready for the first corpus distractor gate.",
        f"- **{blocked}** target(s) are blocked.",
        "",
        "Primary blockers:",
    ]

    if inat == 0:
        lines.append("1. **No iNaturalist similar-species hints** — highest priority gap.")
    if missing_fr_count > 0:
        lines.append(
            f"2. **{missing_fr_count} candidates missing French names"
            " — blocks FR corpus usability."
        )
    if no_cand > 0:
        lines.append(f"3. **{no_cand} targets with no candidates at all** — may need AI proposal.")

    lines += [
        "",
        "---",
        "",
        "## Recommended Next Sprint",
        "",
    ]

    if decision == "READY_FOR_FIRST_CORPUS_DISTRACTOR_GATE":
        lines += [
            "**Sprint 12 Option C — First corpus distractor gate.**",
            "",
            "Proceed to first corpus distractor gate. Run gate against ready targets.",
        ]
    elif decision == "NEEDS_TAXON_ENRICHMENT_BEFORE_DISTRACTORS":
        lines += [
            "**Sprint 12 Option A — Referenced taxon harvest + iNat enrichment.**",
            "",
            "Trigger iNaturalist similar-species enrichment for all 50 targets.",
            "Re-run candidate generation after enrichment.",
            "If referenced taxon shells are needed, harvest them first.",
        ]
    elif decision == "READY_FOR_REFERENCED_TAXON_HARVEST":
        lines += [
            "**Sprint 12 Option A — Referenced taxon harvest + persistence.**",
            "",
            f"Harvest {ref_needed} referenced taxon shells.",
            "Re-run readiness after harvest to promote unresolved candidates.",
        ]
    else:
        lines += [
            "**Sprint 12 Option B — AI ranking/proposals dry-run.**",
            "",
            "Run AI pedagogical proposal dry-run against targets with insufficient candidates.",
            "Validate AI outputs against the schema before any promotion.",
        ]

    lines += [
        "",
        "---",
        "",
        "## Per-Target Readiness (first 20)",
        "",
        "| Target | iNat | Genus | Family | Order | Total | FR-usable | Status |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for t in per_target[:20]:
        lines.append(
            f"| {t['scientific_name']} "
            f"| {t['inat_candidate_count']} "
            f"| {t['taxonomic_candidate_count'] - 0} "
            f"| — "
            f"| — "
            f"| {t['total_candidate_relationships']} "
            f"| {t['usable_fr_candidate_count']} "
            f"| {t['readiness_status']} |"
        )
    if len(per_target) > 20:
        lines.append(f"| … ({len(per_target) - 20} more) | | | | | | | |")

    lines += [
        "",
        "---",
        "",
        f"*Generated: {today} | snapshot: {snapshot_id}*",
        "",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build distractor readiness synthesis from audit + candidates evidence."
    )
    parser.add_argument("--audit-json", type=Path, default=DEFAULT_AUDIT_JSON)
    parser.add_argument("--candidates-json", type=Path, default=DEFAULT_CANDIDATES_JSON)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    args = parser.parse_args()

    if not args.audit_json.is_file():
        print(f"ERROR: audit JSON not found: {args.audit_json}")
        raise SystemExit(1)
    if not args.candidates_json.is_file():
        print(f"ERROR: candidates JSON not found: {args.candidates_json}")
        raise SystemExit(1)

    with open(args.audit_json) as f:
        audit = json.load(f)
    with open(args.candidates_json) as f:
        candidates = json.load(f)

    result = run_readiness(audit=audit, candidates=candidates)

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2))
    _write_markdown(result, args.output_md)

    summary = result.get("summary", {})
    print(f"Decision: {result.get('decision')}")
    print(f"Target taxa: {summary.get('target_taxa_count', 0)}")
    print(f"Targets ready: {summary.get('targets_ready', 0)}")
    print(f"Targets blocked: {summary.get('targets_blocked', 0)}")
    missing_fr = result.get("gaps", {}).get("candidates_missing_french_name_count", 0)
    print(f"Missing French names: {missing_fr}")
    print(f"JSON: {args.output_json}")
    print(f"MD:   {args.output_md}")


if __name__ == "__main__":
    main()
