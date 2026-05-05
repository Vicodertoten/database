"""
Audit distractor relationship v1 current-state coverage.

Reads canonical taxa from an iNaturalist snapshot (raw taxa/ directory) and
an optional export bundle, then reports how many potential distractor candidates
exist per target taxon across the three main sources:

    1. iNaturalist external_similarity_hints (similar_taxa in raw response)
    2. Taxonomic neighbors (same genus / family / order within snapshot)
    3. Referenced-taxon shells (from export bundle referenced_taxa list)

Does NOT persist any DistractorRelationship records.
Does NOT modify packs, runtime, or any existing artifact.

Usage:
    python scripts/audit_distractor_relationships_v1_current_state.py
    python scripts/audit_distractor_relationships_v1_current_state.py \\
        --snapshot-id palier1-be-birds-50taxa-run003-v11-baseline \\
        --output-json docs/audits/evidence/distractor_v1_current_state.json \\
        --output-md  docs/audits/distractor-relationships-v1-current-state-audit.md
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SNAPSHOT_ID = "palier1-be-birds-50taxa-run003-v11-baseline"
DEFAULT_SNAPSHOT_BASE = REPO_ROOT / "data" / "raw" / "inaturalist"
DEFAULT_EXPORT_BASE = REPO_ROOT / "data" / "exports"
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT / "docs" / "audits" / "evidence"
    / "distractor_v1_current_state_audit.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "docs" / "audits"
    / "distractor-relationships-v1-current-state-audit.md"
)

# Minimum distractors for readiness
READY_THRESHOLD = 3

# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------


def _load_snapshot_taxa(snapshot_dir: Path) -> list[dict[str, Any]]:
    """Load all taxon records from the snapshot taxa/ directory."""
    taxa_dir = snapshot_dir / "taxa"
    if not taxa_dir.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for fn in sorted(os.listdir(taxa_dir)):
        if not fn.endswith(".json"):
            continue
        with open(taxa_dir / fn) as f:
            payload = json.load(f)
        for t in payload.get("results", [payload]):
            if isinstance(t, dict) and t.get("name"):
                records.append(t)
    return records


def _load_export_bundle(export_path: Path) -> dict[str, Any]:
    """Load export bundle JSON. Returns empty dict if not found."""
    if not export_path.is_file():
        return {}
    with open(export_path) as f:
        return json.load(f)


def _find_export_bundle(snapshot_id: str, export_base: Path) -> Path:
    """Try to find an export bundle matching the snapshot_id."""
    candidates = [
        export_base / f"{snapshot_id}.export.json",
        export_base / f"{snapshot_id.replace('-', '_')}.export.json",
    ]
    for c in candidates:
        if c.is_file():
            return c
    # Try partial match
    for fn in sorted(export_base.iterdir()):
        if fn.suffix == ".json" and snapshot_id in fn.stem:
            return fn
    return export_base / f"{snapshot_id}.export.json"  # may not exist; handled gracefully


# ---------------------------------------------------------------------------
# Ancestry extraction
# ---------------------------------------------------------------------------


def _extract_lineage(taxon: dict[str, Any]) -> dict[str, int | None]:
    """Extract genus_id, family_id, order_id from the ancestors list."""
    genus_id = family_id = order_id = None
    for ancestor in taxon.get("ancestors") or []:
        rank = ancestor.get("rank")
        aid = ancestor.get("id")
        if rank == "genus":
            genus_id = aid
        elif rank == "family":
            family_id = aid
        elif rank == "order":
            order_id = aid
    return {"genus_id": genus_id, "family_id": family_id, "order_id": order_id}


# ---------------------------------------------------------------------------
# Core audit logic
# ---------------------------------------------------------------------------


def run_audit(
    *,
    snapshot_dir: Path,
    export_bundle: dict[str, Any],
    snapshot_id: str,
) -> dict[str, Any]:
    """Compute coverage metrics and return the structured audit result."""

    # --- Load raw snapshot taxa ---
    raw_taxa = _load_snapshot_taxa(snapshot_dir)
    if not raw_taxa:
        return {
            "execution_status": "blocked",
            "block_reason": f"No taxa found in snapshot dir: {snapshot_dir}",
            "input_source": str(snapshot_dir),
            "snapshot_id": snapshot_id,
        }

    # --- Index lineage ---
    lineage_by_name: dict[str, dict[str, int | None]] = {}
    genus_members: dict[int, list[str]] = defaultdict(list)
    family_members: dict[int, list[str]] = defaultdict(list)
    order_members: dict[int, list[str]] = defaultdict(list)

    for t in raw_taxa:
        name = t["name"]
        lineage = _extract_lineage(t)
        lineage_by_name[name] = lineage
        if lineage["genus_id"]:
            genus_members[lineage["genus_id"]].append(name)
        if lineage["family_id"]:
            family_members[lineage["family_id"]].append(name)
        if lineage["order_id"]:
            order_members[lineage["order_id"]].append(name)

    # --- Export bundle data ---
    bundle_taxa = export_bundle.get("canonical_taxa") or []
    bundle_referenced_taxa = export_bundle.get("referenced_taxa") or []

    # Index canonical taxa by scientific_name for enrichment check
    bundle_taxa_by_name: dict[str, dict[str, Any]] = {
        t.get("accepted_scientific_name", ""): t
        for t in bundle_taxa
        if t.get("accepted_scientific_name")
    }

    # Build referenced_taxon set (by scientific_name)
    referenced_taxa_names: set[str] = {
        r.get("scientific_name", "") for r in bundle_referenced_taxa
        if r.get("scientific_name")
    }

    # --- Per-target analysis ---
    per_target: list[dict[str, Any]] = []
    inat_hint_total = 0
    internal_similarity_total = 0
    same_genus_total = 0
    same_family_total = 0
    same_order_total = 0

    taxa_with_ext_hints = 0
    taxa_with_inat_hints = 0
    taxa_with_3plus_inat = 0
    taxa_with_internal = 0
    taxa_with_taxonomy_profile = 0
    taxa_with_genus_neighbors = 0
    taxa_with_family_neighbors = 0
    taxa_with_3plus_candidates = 0
    taxa_without_candidates = 0

    targets_missing_inat: list[str] = []
    targets_missing_profile: list[str] = []
    targets_no_candidates: list[str] = []
    targets_weak_only: list[str] = []
    unresolved_candidate_names: set[str] = set()
    ref_shell_needed: set[str] = set()

    # Readiness counters
    ready_count = 0
    insufficient_count = 0
    needs_enrichment_count = 0
    needs_ref_shells_count = 0

    for t in raw_taxa:
        name = t["name"]
        taxon_id = str(t.get("id", ""))
        lineage = lineage_by_name[name]

        # iNat hints from raw similar_taxa field
        raw_hints = t.get("similar_taxa") or []
        inat_hint_count = len(raw_hints)

        # Internal similar taxa (from export bundle)
        bundle_entry = bundle_taxa_by_name.get(name, {})
        internal_similar = bundle_entry.get("similar_taxa") or []
        internal_count = len(internal_similar)

        # Authority taxonomy profile (from enrichment)
        has_profile = bool(bundle_entry.get("authority_taxonomy_profile"))

        # Taxonomic neighbors within snapshot (exclude self)
        sg_names = [n for n in genus_members.get(lineage["genus_id"] or -1, []) if n != name]
        # same_family = in family but not same genus
        genus_set = set(genus_members.get(lineage["genus_id"] or -1, []))
        sf_names = [
            n for n in family_members.get(lineage["family_id"] or -1, [])
            if n != name and n not in genus_set
        ]
        # same_order = in order but not same family
        family_set = set(family_members.get(lineage["family_id"] or -1, []))
        so_names = [
            n for n in order_members.get(lineage["order_id"] or -1, [])
            if n != name and n not in family_set
        ]

        sg_count = len(sg_names)
        sf_count = len(sf_names)
        so_count = len(so_names)

        # Aggregate candidates (without double-counting)
        # Priority: inat_hints > internal > taxonomic
        candidate_names: set[str] = set()
        for h in raw_hints:
            cname = h.get("name") or h.get("accepted_scientific_name")
            if cname and cname != name:
                candidate_names.add(cname)
        for s in internal_similar:
            cname = s.get("accepted_scientific_name")
            if cname and cname != name:
                candidate_names.add(cname)
        candidate_names.update(sg_names)
        candidate_names.update(sf_names)
        candidate_names.update(so_names)
        total_candidates = len(candidate_names)

        # Localized name check for candidate taxa
        for cname in candidate_names:
            ce = bundle_taxa_by_name.get(cname)
            if ce is None:
                # Not canonical — check referenced taxa
                if cname not in referenced_taxa_names:
                    unresolved_candidate_names.add(cname)
                    ref_shell_needed.add(cname)

        # Readiness status
        if total_candidates >= READY_THRESHOLD and inat_hint_count > 0:
            readiness = "ready_for_distractor_v1"
        elif total_candidates >= READY_THRESHOLD and inat_hint_count == 0:
            readiness = "inat_missing_but_taxonomic_ok"
        elif total_candidates > 0:
            readiness = "insufficient_distractors"
        elif not has_profile and not raw_hints:
            readiness = "needs_taxon_enrichment"
        else:
            readiness = "no_candidates"

        # Reasons
        reasons: list[str] = []
        if inat_hint_count == 0:
            reasons.append("no_inat_hints")
            targets_missing_inat.append(name)
        if not has_profile:
            reasons.append("no_taxonomy_profile")
            targets_missing_profile.append(name)
        if total_candidates == 0:
            reasons.append("no_candidates")
            targets_no_candidates.append(name)
        elif total_candidates < READY_THRESHOLD:
            reasons.append(f"only_{total_candidates}_candidates")
            targets_weak_only.append(name)

        per_target.append({
            "target_canonical_taxon_id": (
                f"taxon:birds:{taxon_id.zfill(6)}" if taxon_id else "unknown"
            ),
            "scientific_name": name,
            "inat_hint_count": inat_hint_count,
            "internal_similar_count": internal_count,
            "same_genus_count": sg_count,
            "same_family_count": sf_count,
            "same_order_count": so_count,
            "total_potential_candidates": total_candidates,
            "readiness_status": readiness,
            "readiness_reasons": reasons,
        })

        # Accumulate totals
        inat_hint_total += inat_hint_count
        internal_similarity_total += internal_count
        same_genus_total += sg_count
        same_family_total += sf_count
        same_order_total += so_count

        if inat_hint_count > 0:
            taxa_with_ext_hints += 1
            taxa_with_inat_hints += 1
        if inat_hint_count >= 3:
            taxa_with_3plus_inat += 1
        if internal_count > 0:
            taxa_with_internal += 1
        if has_profile:
            taxa_with_taxonomy_profile += 1
        if sg_count > 0:
            taxa_with_genus_neighbors += 1
        if sf_count > 0:
            taxa_with_family_neighbors += 1
        if total_candidates >= READY_THRESHOLD:
            taxa_with_3plus_candidates += 1
        if total_candidates == 0:
            taxa_without_candidates += 1

        if readiness == "ready_for_distractor_v1":
            ready_count += 1
        elif readiness == "inat_missing_but_taxonomic_ok":
            needs_enrichment_count += 1
        elif readiness == "needs_taxon_enrichment":
            needs_enrichment_count += 1
        elif readiness == "insufficient_distractors":
            insufficient_count += 1
        elif readiness == "no_candidates":
            insufficient_count += 1

        needs_ref_shell_for_target = any(
            n in ref_shell_needed
            for n in (list(candidate_names) if candidate_names else [])
        )
        if needs_ref_shell_for_target:
            needs_ref_shells_count += 1

    # --- Determine decision ---
    n = len(raw_taxa)
    if ready_count + needs_enrichment_count == n and ready_count > n // 2:
        decision = "READY_FOR_CANDIDATE_GENERATION"
    elif needs_enrichment_count > ready_count:
        decision = "NEEDS_TAXON_ENRICHMENT_BEFORE_DISTRACTORS"
    elif not raw_taxa:
        decision = "BLOCKED_BY_MISSING_INPUT_DATA"
    else:
        decision = "NEEDS_TAXON_ENRICHMENT_BEFORE_DISTRACTORS"

    # --- Build result ---
    return {
        "audit_version": "distractor_relationships_v1_current_state.v1",
        "run_date": str(date.today()),
        "execution_status": "complete",
        "input_source": str(snapshot_dir),
        "snapshot_id": snapshot_id,
        "decision": decision,
        "target_taxa_count": n,
        "active_target_taxa_count": n,
        "taxa_with_external_similarity_hints": taxa_with_ext_hints,
        "taxa_with_inat_similarity_hints": taxa_with_inat_hints,
        "taxa_with_3_plus_inat_hints": taxa_with_3plus_inat,
        "taxa_with_internal_similar_taxa": taxa_with_internal,
        "taxa_with_taxonomy_profile": taxa_with_taxonomy_profile,
        "taxa_with_same_genus_neighbors": taxa_with_genus_neighbors,
        "taxa_with_same_family_neighbors": taxa_with_family_neighbors,
        "taxa_with_3_plus_total_potential_candidates": taxa_with_3plus_candidates,
        "taxa_without_candidates": taxa_without_candidates,
        "source_coverage": {
            "inaturalist_hint_count": inat_hint_total,
            "internal_similarity_count": internal_similarity_total,
            "same_genus_candidate_count": same_genus_total,
            "same_family_candidate_count": same_family_total,
            "same_order_candidate_count": same_order_total,
        },
        "gaps": {
            "targets_missing_inat_hints": targets_missing_inat,
            "targets_missing_taxonomy_profile": targets_missing_profile,
            "targets_with_no_candidates": targets_no_candidates,
            "targets_with_only_weak_candidates": targets_weak_only,
            "candidate_taxa_missing_localized_names": list(unresolved_candidate_names),
            "referenced_taxon_shell_needed_count": len(ref_shell_needed),
            "unresolved_candidate_taxa_count": len(unresolved_candidate_names),
        },
        "first_corpus_readiness_preview": {
            "ready_for_distractor_v1_count": ready_count,
            "insufficient_distractors_count": insufficient_count,
            "needs_taxon_enrichment_count": needs_enrichment_count,
            "needs_referenced_taxon_shells_count": needs_ref_shells_count,
        },
        "per_target_summaries": per_target,
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def _write_markdown(result: dict[str, Any], output_path: Path) -> None:
    decision = result.get("decision", "UNKNOWN")
    n = result.get("target_taxa_count", 0)
    inat = result.get("taxa_with_inat_similarity_hints", 0)
    genus = result.get("taxa_with_same_genus_neighbors", 0)
    family = result.get("taxa_with_same_family_neighbors", 0)
    no_cand = result.get("taxa_without_candidates", 0)
    three_plus = result.get("taxa_with_3_plus_total_potential_candidates", 0)
    sc = result.get("source_coverage", {})
    gaps = result.get("gaps", {})
    per_target = result.get("per_target_summaries", [])
    today = result.get("run_date", str(date.today()))
    exec_status = result.get("execution_status", "unknown")
    snapshot_id = result.get("snapshot_id", "unknown")

    lines: list[str] = [
        "---",
        "owner: vicodertoten",
        "status: ready_for_validation",
        f"last_reviewed: {today}",
        "source_of_truth: docs/audits/evidence/distractor_v1_current_state_audit.json",
        "scope: distractor_relationships_v1_current_state_audit",
        "---",
        "",
        "# Distractor Relationships V1 — Current State Audit",
        "",
        "## Purpose",
        "",
        "Audit existing data to determine how much potential distractor coverage exists",
        "before implementing harvest/persistence of `DistractorRelationship` records.",
        "",
        "This audit does not persist any relationships.",
        "It does not modify runtime, packs, or any existing artifact.",
        "",
        "---",
        "",
        "## Input Data",
        "",
        f"- **Snapshot**: `{snapshot_id}`",
        f"- **Execution status**: `{exec_status}`",
        f"- **Run date**: {today}",
        "",
    ]

    if exec_status == "blocked":
        lines += [
            "## Result: BLOCKED",
            "",
            f"**Block reason**: {result.get('block_reason', 'unknown')}",
            "",
        ]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines))
        return

    # --- Current coverage ---
    lines += [
        "---",
        "",
        "## Current Coverage",
        "",
        "| Metric | Count |",
        "|---|---|",
        f"| Target taxa in snapshot | {n} |",
        f"| Active target taxa | {n} |",
        f"| Taxa with iNat similarity hints | {inat} |",
        f"| Taxa with ≥3 iNat hints | {result.get('taxa_with_3_plus_inat_hints', 0)} |",
        f"| Taxa with internal similar_taxa | {result.get('taxa_with_internal_similar_taxa', 0)} |",
        f"| Taxa with taxonomy profile | {result.get('taxa_with_taxonomy_profile', 0)} |",
        f"| Taxa with ≥1 same-genus neighbor | {genus} |",
        f"| Taxa with ≥1 same-family neighbor | {family} |",
        f"| Taxa with ≥{READY_THRESHOLD} total candidates | {three_plus} |",
        f"| Taxa with no candidates | {no_cand} |",
        "",
        "---",
        "",
        "## iNaturalist Hint Coverage",
        "",
        f"Total iNat similarity hints available: **{sc.get('inaturalist_hint_count', 0)}**",
        "",
        "iNaturalist `similar_taxa` data is the first-priority source for distractor",
        "candidates. These hints are populated during taxon enrichment from the iNat API.",
        "",
    ]
    if inat == 0:
        lines += [
            "**Current state**: No iNat similarity hints found in snapshot taxa.",
            "These hints are fetched during the enrichment pipeline run.",
            "The taxa files in the snapshot may predate the enrichment step.",
            "",
        ]
    else:
        lines += [
            f"**Current state**: {inat}/{n} taxa have at least one iNat similarity hint.",
            "",
        ]

    # --- Taxonomic fallback ---
    lines += [
        "---",
        "",
        "## Taxonomic Fallback Coverage",
        "",
        "Taxonomic neighbors are inferred from the ancestry chain within the snapshot.",
        "They are the second and third priority sources (same genus → family → order).",
        "",
        "| Source | Total candidates across all targets |",
        "|---|---|",
        f"| Same genus | {sc.get('same_genus_candidate_count', 0)} |",
        f"| Same family (not same genus) | {sc.get('same_family_candidate_count', 0)} |",
        f"| Same order (not same family) | {sc.get('same_order_candidate_count', 0)} |",
        "",
        f"Taxa with ≥1 same-genus neighbor: **{genus}/{n}**",
        "",
    ]

    # --- Referenced taxon shells ---
    lines += [
        "---",
        "",
        "## Referenced Taxon Shell Needs",
        "",
        f"Unresolved candidate taxa (no canonical or referenced taxon): "
        f"**{gaps.get('unresolved_candidate_taxa_count', 0)}**",
        "",
        f"Referenced taxon shells needed: **{gaps.get('referenced_taxon_shell_needed_count', 0)}**",
        "",
        "Candidates that are not yet canonical taxa in this repository need",
        "a `ReferencedTaxon` shell to be usable in compiled question options.",
        "",
    ]

    # --- Localization gaps ---
    lines += [
        "---",
        "",
        "## Localization Gaps",
        "",
        "Candidate taxa missing localized names (no canonical or referenced taxon entry): "
        f"**{gaps.get('referenced_taxon_shell_needed_count', 0)}**",
        "",
        "Localized names are required for displaying question options to learners.",
        "Missing names must be resolved before a relationship can be `validated`.",
        "",
    ]

    # --- Diversity fallback risk ---
    lines += [
        "---",
        "",
        "## Diversity Fallback Risk",
        "",
        f"Taxa with no candidates at all: **{no_cand}/{n}**",
        "",
        "Per Sprint 11 Phase 1 policy, `emergency_diversity_fallback` relationships",
        "**must not** be used for the first corpus candidate.",
        "If a taxon has no real pedagogical distractor candidates, it must either be",
        "enriched first (iNat hints + taxonomy profile) or excluded from playable corpus.",
        "",
    ]

    # --- Target readiness preview ---
    lines += [
        "---",
        "",
        "## Target Readiness Preview",
        "",
        "| Readiness status | Count |",
        "|---|---|",
    ]
    status_counts: dict[str, int] = Counter(t["readiness_status"] for t in per_target)
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| `{status}` | {count} |")
    lines += [
        "",
        "### Per-target details",
        "",
        "| Scientific name | iNat | Genus | Family | Order | Total | Status |",
        "|---|---|---|---|---|---|---|",
    ]
    for t in sorted(per_target, key=lambda x: x["scientific_name"]):
        lines.append(
            f"| {t['scientific_name']} "
            f"| {t['inat_hint_count']} "
            f"| {t['same_genus_count']} "
            f"| {t['same_family_count']} "
            f"| {t['same_order_count']} "
            f"| {t['total_potential_candidates']} "
            f"| `{t['readiness_status']}` |"
        )
    lines += [""]

    # --- Top blockers ---
    lines += [
        "---",
        "",
        "## Top Blockers",
        "",
    ]
    if gaps.get("unresolved_candidate_taxa_count", 0) > 0:
        lines.append(
            f"1. **{gaps['unresolved_candidate_taxa_count']} unresolved candidate taxa** — "
            "no canonical or referenced taxon shell exists. Cannot validate relationships."
        )
    if inat == 0:
        lines.append(
            "2. **0 iNat similarity hints** — enrichment pipeline has not yet populated "
            "external_similarity_hints for snapshot taxa."
        )
    if result.get("taxa_with_taxonomy_profile", 0) == 0:
        lines.append(
            "3. **0 taxa with taxonomy profile** — authority_taxonomy_profile not yet "
            "populated in export bundle."
        )
    lines += [""]

    # --- Recommendation ---
    lines += [
        "---",
        "",
        "## Recommendation for Next Phase",
        "",
        f"**Decision: `{decision}`**",
        "",
    ]
    if decision == "READY_FOR_CANDIDATE_GENERATION":
        lines += [
            "The snapshot has sufficient coverage to begin generating `DistractorRelationship`",
            "candidate records. Proceed with Sprint 11 Phase 3 (harvest + seed from iNat hints).",
            "",
        ]
    elif decision == "NEEDS_TAXON_ENRICHMENT_BEFORE_DISTRACTORS":
        lines += [
            "The snapshot taxa are not yet enriched with iNat similarity hints or",
            "authority taxonomy profiles. Before Phase 3 candidate generation:",
            "",
            "1. Re-run the enrichment pipeline on the target snapshot to populate",
            "   `external_similarity_hints` from the iNat API.",
            "2. Ensure `authority_taxonomy_profile` is populated for ancestry-based",
            "   genus/family/order inference.",
            "3. Create `ReferencedTaxon` shells for candidate taxa that are not yet",
            "   canonicalized.",
            "4. Re-run this audit to confirm readiness.",
            "",
            "Taxonomy-based neighbors are already computable from ancestry chains.",
            f"**{three_plus}/{n} taxa** have ≥{READY_THRESHOLD} taxonomic candidates.",
            "Taxonomy-based candidate generation can proceed without iNat hints,",
            "but iNat hints should be the primary source.",
            "",
        ]
    else:
        lines += [
            "Input data is missing or insufficient. Check the snapshot path and re-run.",
            "",
        ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit distractor relationship v1 current-state coverage."
    )
    parser.add_argument(
        "--snapshot-id",
        default=DEFAULT_SNAPSHOT_ID,
        help="Snapshot identifier (directory name under data/raw/inaturalist/).",
    )
    parser.add_argument(
        "--input-path",
        default=None,
        help="Explicit path to snapshot directory (overrides --snapshot-id lookup).",
    )
    parser.add_argument(
        "--output-json",
        default=str(DEFAULT_OUTPUT_JSON),
        help="Output JSON path.",
    )
    parser.add_argument(
        "--output-md",
        default=str(DEFAULT_OUTPUT_MD),
        help="Output Markdown path.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.input_path:
        snapshot_dir = Path(args.input_path)
        snapshot_id = Path(args.input_path).name
    else:
        snapshot_id = args.snapshot_id
        snapshot_dir = DEFAULT_SNAPSHOT_BASE / snapshot_id

    export_bundle_path = _find_export_bundle(snapshot_id, DEFAULT_EXPORT_BASE)
    export_bundle = _load_export_bundle(export_bundle_path)

    result = run_audit(
        snapshot_dir=snapshot_dir,
        export_bundle=export_bundle,
        snapshot_id=snapshot_id,
    )

    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, indent=2))

    output_md = Path(args.output_md)
    _write_markdown(result, output_md)

    decision = result.get("decision", result.get("execution_status", "unknown"))
    print(f"Decision: {decision}")
    print(f"Target taxa: {result.get('target_taxa_count', 0)}")
    print(f"iNat hints: {result.get('taxa_with_inat_similarity_hints', 0)}")
    print(
        f"With ≥{READY_THRESHOLD} candidates: "
        f"{result.get('taxa_with_3_plus_total_potential_candidates', 0)}"
    )
    print(f"JSON: {output_json}")
    print(f"MD:   {output_md}")


if __name__ == "__main__":
    main()
