"""
Generate DistractorRelationship candidate artifacts from iNaturalist
similar-species hints and taxonomic neighbors.

Source priority (per sprint-11 spec):
  1. iNaturalist similar species  (source = inaturalist_similar_species)
  2. Taxonomic neighbor — same genus  (source = taxonomic_neighbor_same_genus)
  3. Taxonomic neighbor — same family  (source = taxonomic_neighbor_same_family)
  4. Taxonomic neighbor — same order   (source = taxonomic_neighbor_same_order)
     — used only when stronger candidates are insufficient

NOT produced in this phase:
  • AI pedagogical proposals
  • emergency_diversity_fallback relationships

Does NOT persist to Postgres.
Does NOT modify packs, runtime, or any existing artifact.
Does NOT do hard regional filtering (distractors may be outside target region).

Usage:
    python scripts/generate_distractor_relationship_candidates_v1.py
    python scripts/generate_distractor_relationship_candidates_v1.py \\
        --snapshot-id palier1-be-birds-50taxa-run003-v11-baseline \\
        --output-json docs/audits/evidence/distractor_relationship_candidates_v1.json \\
        --output-md  docs/audits/distractor-relationship-candidates-v1.md \\
        --max-taxonomic-neighbors-per-target 10 \\
        --include-same-order
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_SNAPSHOT_ID = "palier1-be-birds-50taxa-run003-v11-baseline"
DEFAULT_SNAPSHOT_BASE = REPO_ROOT / "data" / "raw" / "inaturalist"
DEFAULT_NORMALIZED_BASE = REPO_ROOT / "data" / "normalized"
DEFAULT_OUTPUT_JSON = (
    REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "distractor_relationship_candidates_v1.json"
)
DEFAULT_OUTPUT_MD = (
    REPO_ROOT / "docs" / "audits" / "distractor-relationship-candidates-v1.md"
)
DEFAULT_INAT_SIMILARITY_JSON = (
    REPO_ROOT / "docs" / "audits" / "evidence" / "inat_similarity_enrichment_sprint12.json"
)
DEFAULT_REFERENCED_SHELL_CANDIDATES_JSON = (
    REPO_ROOT
    / "docs"
    / "audits"
    / "evidence"
    / "referenced_taxon_shell_candidates_sprint12.json"
)

# Minimum candidates for a target to be considered "ready"
READY_THRESHOLD = 3
# Default neighbour cap per taxonomic level (per target)
DEFAULT_MAX_NEIGHBORS = 10

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


def _find_normalized_path(snapshot_id: str, normalized_base: Path) -> Path | None:
    """Return path to normalized snapshot JSON if it exists."""
    stem = snapshot_id.replace("-", "_")
    candidates = [
        normalized_base / f"{stem}.normalized.json",
        normalized_base / f"{snapshot_id}.normalized.json",
    ]
    for c in candidates:
        if c.is_file():
            return c
    # Partial match
    for fn in sorted(normalized_base.iterdir()):
        if fn.suffix == ".json" and snapshot_id in fn.stem:
            return fn
    return None


def _load_normalized_index(
    normalized_path: Path | None,
) -> dict[str, dict[str, Any]]:
    """Load normalized snapshot, return dict keyed by accepted_scientific_name."""
    if normalized_path is None or not normalized_path.is_file():
        return {}
    with open(normalized_path) as f:
        payload = json.load(f)
    taxa = payload.get("canonical_taxa") or []
    return {
        t.get("accepted_scientific_name", ""): t
        for t in taxa
        if t.get("accepted_scientific_name")
    }


def _load_inat_similarity_by_canonical_id(path: Path | None) -> dict[str, list[dict[str, Any]]]:
    """Load Phase B evidence and index hints by target canonical taxon ID."""
    if path is None or not path.is_file():
        return {}
    with open(path) as f:
        payload = json.load(f)
    index: dict[str, list[dict[str, Any]]] = {}
    for item in payload.get("per_target", []):
        target_id = str(item.get("canonical_taxon_id", "")).strip()
        if not target_id:
            continue
        hints = [h for h in item.get("hints", []) if isinstance(h, dict)]
        index[target_id] = hints
    return index


def _load_referenced_shell_candidates(path: Path | None) -> list[dict[str, Any]]:
    """Load Phase D shell candidates artifact items."""
    if path is None or not path.is_file():
        return []
    with open(path) as f:
        payload = json.load(f)
    items = payload.get("items", [])
    return [i for i in items if isinstance(i, dict)]


def _build_referenced_by_name_from_shell_candidates(
    shell_candidates: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Build a virtual referenced_by_name index from Phase D shell candidates."""
    by_name: dict[str, dict[str, Any]] = {}
    for item in shell_candidates:
        status = item.get("proposed_mapping_status")
        if status not in {"auto_referenced_high_confidence", "auto_referenced_low_confidence"}:
            continue
        scientific_name = str(item.get("scientific_name", "")).strip()
        if not scientific_name:
            continue
        source_taxon_id = str(item.get("source_taxon_id", "")).strip()
        if not source_taxon_id:
            continue
        by_name[scientific_name] = {
            "referenced_taxon_id": f"reftaxon:inaturalist:{source_taxon_id}",
            "scientific_name": scientific_name,
            "mapping_status": status,
        }
    return by_name


def _inject_inat_hints_into_raw_taxa(
    *,
    raw_taxa: list[dict[str, Any]],
    canonical_by_name: dict[str, dict[str, Any]],
    hints_by_canonical_id: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """
    Populate per-target raw `similar_taxa` from Phase B evidence when available.
    This keeps existing generation logic unchanged while enabling Sprint 12 reruns.
    """
    if not hints_by_canonical_id:
        return raw_taxa

    enriched: list[dict[str, Any]] = []
    for taxon in raw_taxa:
        updated = dict(taxon)
        name = str(taxon.get("name", "")).strip()
        canonical_id = str(
            (canonical_by_name.get(name) or {}).get("canonical_taxon_id", "")
        ).strip()
        hints = hints_by_canonical_id.get(canonical_id, [])
        existing = list(updated.get("similar_taxa") or [])
        existing_names = {
            str(h.get("name") or h.get("accepted_scientific_name") or "").strip()
            for h in existing
        }
        for h in hints:
            cname = str(h.get("accepted_scientific_name") or "").strip()
            if not cname or cname in existing_names:
                continue
            existing.append(
                {
                    "name": cname,
                    "accepted_scientific_name": cname,
                    "id": h.get("external_taxon_id"),
                    "preferred_common_name": h.get("common_name"),
                    "relation_type": h.get("relation_type", "visual_lookalike"),
                }
            )
            existing_names.add(cname)
        updated["similar_taxa"] = existing
        enriched.append(updated)
    return enriched


def _load_export_bundle(snapshot_id: str, export_base: Path) -> dict[str, Any]:
    """Find and load export bundle; return empty dict if not found."""
    stem = snapshot_id.replace("-", "_")
    candidates = [
        export_base / f"{stem}.export.json",
        export_base / f"{snapshot_id}.export.json",
    ]
    for c in candidates:
        if c.is_file():
            with open(c) as f:
                return json.load(f)
    # Partial match
    for fn in sorted(export_base.iterdir()):
        if fn.suffix == ".json" and snapshot_id.replace("-", "_") in fn.stem:
            with open(fn) as f:
                return json.load(f)
    return {}


# ---------------------------------------------------------------------------
# Ancestry / lineage helpers
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
# Candidate resolution helpers
# ---------------------------------------------------------------------------


def _resolve_ref(
    candidate_name: str,
    canonical_by_name: dict[str, dict[str, Any]],
    referenced_by_name: dict[str, dict[str, Any]],
) -> tuple[str, str | None]:
    """
    Return (candidate_taxon_ref_type, candidate_taxon_ref_id).

    Checks canonical taxa first, then referenced taxa, then marks unresolved.
    """
    if candidate_name in canonical_by_name:
        ref_id = canonical_by_name[candidate_name].get("canonical_taxon_id") or candidate_name
        return "canonical_taxon", ref_id
    if candidate_name in referenced_by_name:
        ref_id = referenced_by_name[candidate_name].get("referenced_taxon_id") or candidate_name
        return "referenced_taxon", ref_id
    return "unresolved_taxon", None


def _has_french_name(entry: dict[str, Any] | None) -> bool:
    """Return True if the taxon entry has at least one French common name."""
    if not entry:
        return False
    cbn = entry.get("common_names_by_language") or {}
    return bool(cbn.get("fr"))


def _has_localized_name(entry: dict[str, Any] | None, lang: str = "en") -> bool:
    """Return True if the taxon entry has at least one common name in `lang`."""
    if not entry:
        return False
    cbn = entry.get("common_names_by_language") or {}
    return bool(cbn.get(lang))


def _relationship_id(target_id: str, source_abbrev: str, candidate_name: str) -> str:
    """Deterministic relationship ID (short hash of inputs)."""
    raw = f"{target_id}|{source_abbrev}|{candidate_name}"
    digest = hashlib.sha1(raw.encode()).hexdigest()[:12]
    return f"dr:{digest}"


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-")


# ---------------------------------------------------------------------------
# Source abbreviations (for relationship_id generation)
# ---------------------------------------------------------------------------

_SOURCE_ABBREV = {
    "inaturalist_similar_species": "inat",
    "taxonomic_neighbor_same_genus": "genus",
    "taxonomic_neighbor_same_family": "family",
    "taxonomic_neighbor_same_order": "order",
}

# ---------------------------------------------------------------------------
# Candidate generation for one target taxon
# ---------------------------------------------------------------------------


def _generate_for_target(
    *,
    target: dict[str, Any],
    all_taxa_by_name: dict[str, dict[str, Any]],
    genus_members: dict[int, list[str]],
    family_members: dict[int, list[str]],
    order_members: dict[int, list[str]],
    canonical_by_name: dict[str, dict[str, Any]],
    referenced_by_name: dict[str, dict[str, Any]],
    normalized_by_name: dict[str, dict[str, Any]],
    max_neighbors: int,
    include_same_order: bool,
    now_iso: str,
) -> list[dict[str, Any]]:
    """Return a list of candidate relationship dicts for one target taxon."""

    name = target["name"]
    lineage = _extract_lineage(target)
    target_entry = canonical_by_name.get(name) or {}
    _raw_id = str(target.get("id", "")).zfill(6)
    target_canonical_id = target_entry.get("canonical_taxon_id") or f"taxon:birds:{_raw_id}"

    relationships: list[dict[str, Any]] = []
    # Track pairs already emitted per source (target-name, candidate-name, source)
    seen: set[tuple[str, str, str]] = set()
    source_rank_counter = 0

    def _emit(
        *,
        candidate_name: str,
        source: str,
        confusion_types: list[str],
        pedagogical_value: str,
        difficulty_level: str = "medium",
        learner_level: str = "mixed",
    ) -> None:
        nonlocal source_rank_counter
        if candidate_name == name:
            return
        key = (name, candidate_name, source)
        if key in seen:
            return
        seen.add(key)

        ref_type, ref_id = _resolve_ref(candidate_name, canonical_by_name, referenced_by_name)

        # unresolved_taxon must use needs_review status (model constraint)
        status = "needs_review" if ref_type == "unresolved_taxon" else "candidate"

        source_rank_counter += 1
        rel_id = _relationship_id(
            target_canonical_id, _SOURCE_ABBREV.get(source, source), candidate_name
        )

        # Audit-only readiness fields
        cand_entry = canonical_by_name.get(candidate_name) or normalized_by_name.get(candidate_name)
        has_fr = _has_french_name(cand_entry)
        has_en = _has_localized_name(cand_entry, "en")
        has_nl = _has_localized_name(cand_entry, "nl")
        has_localized = has_en or has_fr

        usability_blockers: list[str] = []
        if not has_fr:
            usability_blockers.append("missing_french_name")
        can_fr = has_fr and ref_type != "unresolved_taxon"
        can_multilingual = has_fr and has_en and has_nl and ref_type != "unresolved_taxon"
        if ref_type == "unresolved_taxon":
            usability_blockers.append("unresolved_taxon_ref")

        relationships.append({
            "relationship_id": rel_id,
            "target_canonical_taxon_id": target_canonical_id,
            "target_scientific_name": name,
            "candidate_taxon_ref_type": ref_type,
            "candidate_taxon_ref_id": ref_id,
            "candidate_scientific_name": candidate_name,
            "source": source,
            "source_rank": source_rank_counter,
            "confusion_types": confusion_types,
            "pedagogical_value": pedagogical_value,
            "difficulty_level": difficulty_level,
            "learner_level": learner_level,
            "status": status,
            "created_at": now_iso,
            # audit-only fields
            "candidate_has_localized_name": has_localized,
            "candidate_has_french_name": has_fr,
            "can_be_used_now_fr": can_fr,
            "can_be_used_now_multilingual": can_multilingual,
            "usability_blockers": usability_blockers,
        })

    # --- Source 1: iNaturalist similar species ---
    raw_hints = target.get("similar_taxa") or []
    for hint in raw_hints:
        cname = hint.get("name") or hint.get("accepted_scientific_name")
        if not cname:
            continue
        _emit(
            candidate_name=cname,
            source="inaturalist_similar_species",
            confusion_types=["visual_similarity"],
            pedagogical_value="high",
            difficulty_level="medium",
            learner_level="mixed",
        )

    # --- Source 2: same-genus neighbors ---
    genus_id = lineage["genus_id"]
    genus_set = set(genus_members.get(genus_id or -1, []))
    sg_names = [n for n in genus_set if n != name][:max_neighbors]
    for cname in sorted(sg_names):
        _emit(
            candidate_name=cname,
            source="taxonomic_neighbor_same_genus",
            confusion_types=["same_genus"],
            pedagogical_value="medium",
        )

    # --- Source 3: same-family neighbors (not same genus) ---
    family_id = lineage["family_id"]
    family_all = set(family_members.get(family_id or -1, []))
    sf_names = [n for n in family_all if n != name and n not in genus_set][:max_neighbors]
    for cname in sorted(sf_names):
        _emit(
            candidate_name=cname,
            source="taxonomic_neighbor_same_family",
            confusion_types=["same_family"],
            pedagogical_value="medium",
        )

    # --- Source 4: same-order neighbors — only if still insufficient ---
    strong_count = len([r for r in relationships if r["source"] != "taxonomic_neighbor_same_order"])
    if include_same_order and strong_count < READY_THRESHOLD:
        order_id = lineage["order_id"]
        order_all = set(order_members.get(order_id or -1, []))
        so_names = [
            n for n in order_all
            if n != name and n not in family_all
        ][:max_neighbors]
        for cname in sorted(so_names):
            _emit(
                candidate_name=cname,
                source="taxonomic_neighbor_same_order",
                confusion_types=["same_order"],
                pedagogical_value="low",
            )

    return relationships


# ---------------------------------------------------------------------------
# Core generation logic
# ---------------------------------------------------------------------------


def run_generation(
    *,
    snapshot_dir: Path,
    canonical_by_name: dict[str, dict[str, Any]],
    referenced_by_name: dict[str, dict[str, Any]],
    normalized_by_name: dict[str, dict[str, Any]],
    snapshot_id: str,
    max_neighbors: int = DEFAULT_MAX_NEIGHBORS,
    include_same_order: bool = False,
    inat_hints_by_canonical_id: dict[str, list[dict[str, Any]]] | None = None,
    referenced_shell_candidate_count: int = 0,
) -> dict[str, Any]:
    """Run candidate generation and return the structured result dict."""

    raw_taxa = _load_snapshot_taxa(snapshot_dir)
    if not raw_taxa:
        return {
            "execution_status": "blocked",
            "block_reason": f"No taxa found in snapshot dir: {snapshot_dir}",
            "snapshot_id": snapshot_id,
        }

    raw_taxa = _inject_inat_hints_into_raw_taxa(
        raw_taxa=raw_taxa,
        canonical_by_name=canonical_by_name,
        hints_by_canonical_id=inat_hints_by_canonical_id or {},
    )

    # Build lineage indexes
    lineage_by_name: dict[str, dict[str, int | None]] = {}
    genus_members: dict[int, list[str]] = defaultdict(list)
    family_members: dict[int, list[str]] = defaultdict(list)
    order_members: dict[int, list[str]] = defaultdict(list)
    all_taxa_by_name: dict[str, dict[str, Any]] = {}

    for t in raw_taxa:
        n = t["name"]
        all_taxa_by_name[n] = t
        lin = _extract_lineage(t)
        lineage_by_name[n] = lin
        if lin["genus_id"]:
            genus_members[lin["genus_id"]].append(n)
        if lin["family_id"]:
            family_members[lin["family_id"]].append(n)
        if lin["order_id"]:
            order_members[lin["order_id"]].append(n)

    now_iso = datetime.now(tz=UTC).isoformat()

    all_relationships: list[dict[str, Any]] = []
    per_target_summaries: list[dict[str, Any]] = []

    # Counters
    inat_count = 0
    genus_count = 0
    family_count = 0
    order_count = 0

    targets_ready = 0
    targets_ready_fr = 0
    targets_inat_only = 0
    targets_taxonomic_only = 0
    targets_insufficient = 0
    targets_no_candidates = 0

    unresolved_names: set[str] = set()
    ref_shell_needed: set[str] = set()
    missing_fr: set[str] = set()

    for target in raw_taxa:
        rels = _generate_for_target(
            target=target,
            all_taxa_by_name=all_taxa_by_name,
            genus_members=genus_members,
            family_members=family_members,
            order_members=order_members,
            canonical_by_name=canonical_by_name,
            referenced_by_name=referenced_by_name,
            normalized_by_name=normalized_by_name,
            max_neighbors=max_neighbors,
            include_same_order=include_same_order,
            now_iso=now_iso,
        )
        all_relationships.extend(rels)

        tname = target["name"]
        target_entry = canonical_by_name.get(tname) or {}
        target_canonical_id = target_entry.get("canonical_taxon_id") or (
            f"taxon:birds:{str(target.get('id', '')).zfill(6)}"
        )

        by_source = Counter(r["source"] for r in rels)
        n_inat = by_source.get("inaturalist_similar_species", 0)
        n_genus = by_source.get("taxonomic_neighbor_same_genus", 0)
        n_family = by_source.get("taxonomic_neighbor_same_family", 0)
        n_order = by_source.get("taxonomic_neighbor_same_order", 0)
        total = len(rels)

        inat_count += n_inat
        genus_count += n_genus
        family_count += n_family
        order_count += n_order

        usable_fr = sum(1 for r in rels if r.get("can_be_used_now_fr"))
        usable_multi = sum(1 for r in rels if r.get("can_be_used_now_multilingual"))

        # Collect blockers
        for r in rels:
            if r["candidate_taxon_ref_type"] == "unresolved_taxon":
                unresolved_names.add(r["candidate_scientific_name"])
                ref_shell_needed.add(r["candidate_scientific_name"])
            if not r["candidate_has_french_name"]:
                missing_fr.add(r["candidate_scientific_name"])

        # Readiness
        if total == 0:
            readiness = "no_candidates"
            targets_no_candidates += 1
        elif total < READY_THRESHOLD:
            readiness = "insufficient_distractors"
            targets_insufficient += 1
        else:
            readiness = "ready"
            targets_ready += 1
            if n_inat == 0:
                targets_taxonomic_only += 1
            if n_inat > 0 and n_genus == 0 and n_family == 0:
                targets_inat_only += 1

        if usable_fr >= READY_THRESHOLD:
            targets_ready_fr += 1

        per_target_summaries.append({
            "target_canonical_taxon_id": target_canonical_id,
            "scientific_name": tname,
            "inat_candidates": n_inat,
            "same_genus_candidates": n_genus,
            "same_family_candidates": n_family,
            "same_order_candidates": n_order,
            "total_candidates": total,
            "usable_fr_candidates": usable_fr,
            "usable_multilingual_candidates": usable_multi,
            "readiness": readiness,
        })

    n_targets = len(raw_taxa)

    # Decision
    if targets_ready >= n_targets * 0.8 and targets_ready_fr >= n_targets * 0.5:
        decision = "READY_FOR_AI_RANKING_DESIGN"
    elif len(ref_shell_needed) > 0 and targets_ready < n_targets // 2:
        decision = "READY_FOR_REFERENCED_TAXON_HARVEST"
    elif targets_insufficient + targets_no_candidates > targets_ready:
        decision = "NEEDS_TAXON_ENRICHMENT_BEFORE_DISTRACTORS"
    else:
        decision = "INSUFFICIENT_DISTRACTOR_COVERAGE"

    return {
        "generation_version": "distractor_relationship_candidates_v1.v1",
        "run_date": str(date.today()),
        "execution_status": "complete",
        "input_source": str(snapshot_dir),
        "snapshot_id": snapshot_id,
        "decision": decision,
        "generation_params": {
            "max_taxonomic_neighbors_per_target": max_neighbors,
            "include_same_order": include_same_order,
            "ready_threshold": READY_THRESHOLD,
        },
        "summary": {
            "target_taxa_count": n_targets,
            "total_relationships_generated": len(all_relationships),
            "by_source": {
                "inaturalist_similar_species": inat_count,
                "taxonomic_neighbor_same_genus": genus_count,
                "taxonomic_neighbor_same_family": family_count,
                "taxonomic_neighbor_same_order": order_count,
            },
            "targets_with_3_plus_candidates": targets_ready,
            "targets_with_3_plus_usable_fr_candidates": targets_ready_fr,
            "targets_with_only_taxonomic_candidates": targets_taxonomic_only,
            "targets_with_insufficient_candidates": targets_insufficient,
            "targets_with_no_candidates": targets_no_candidates,
            "unresolved_candidate_count": len(unresolved_names),
            "referenced_taxon_shell_needed_count": len(ref_shell_needed),
            "referenced_taxon_shell_candidate_count": referenced_shell_candidate_count,
            "candidates_missing_french_name": len(missing_fr),
            "no_emergency_diversity_fallback_generated": True,
        },
        "gaps": {
            "unresolved_candidates": sorted(unresolved_names),
            "referenced_taxon_shells_needed": sorted(ref_shell_needed),
            "candidates_missing_french_name": sorted(missing_fr),
            "targets_not_ready": [
                s["scientific_name"]
                for s in per_target_summaries
                if s["readiness"] != "ready"
            ],
        },
        "per_target_summaries": per_target_summaries,
        "relationships": all_relationships,
    }


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def _write_markdown(result: dict[str, Any], output_path: Path) -> None:
    decision = result.get("decision", "UNKNOWN")
    today = result.get("run_date", str(date.today()))
    snapshot_id = result.get("snapshot_id", "unknown")
    summary = result.get("summary", {})
    gaps = result.get("gaps", {})
    params = result.get("generation_params", {})
    per_target = result.get("per_target_summaries", [])
    exec_status = result.get("execution_status", "unknown")

    n = summary.get("target_taxa_count", 0)
    total_rel = summary.get("total_relationships_generated", 0)
    by_source = summary.get("by_source", {})
    ready_count = summary.get("targets_with_3_plus_candidates", 0)
    ready_fr = summary.get("targets_with_3_plus_usable_fr_candidates", 0)
    taxo_only = summary.get("targets_with_only_taxonomic_candidates", 0)
    insufficient = summary.get("targets_with_insufficient_candidates", 0)
    no_cand = summary.get("targets_with_no_candidates", 0)
    unresolved = summary.get("unresolved_candidate_count", 0)
    ref_needed = summary.get("referenced_taxon_shell_needed_count", 0)
    ref_candidate_count = summary.get("referenced_taxon_shell_candidate_count", 0)
    missing_fr = summary.get("candidates_missing_french_name", 0)
    no_emergency = summary.get("no_emergency_diversity_fallback_generated", True)

    lines: list[str] = [
        "---",
        "owner: vicodertoten",
        "status: ready_for_validation",
        f"last_reviewed: {today}",
        "source_of_truth: docs/audits/evidence/distractor_relationship_candidates_v1.json",
        "scope: distractor_relationship_candidates_v1",
        "---",
        "",
        "# Distractor Relationship Candidates V1",
        "",
        "## Purpose",
        "",
        (
            "Generate candidate `DistractorRelationship` artifacts from "
            "iNaturalist similar-species hints and taxonomic neighbors."
        ),
        "",
        "This report does not persist any relationships to the database.",
        "It does not modify packs, runtime, or any existing artifact.",
        "Regional filtering is not applied — candidates may be outside the target region.",
        "",
        "---",
        "",
        "## Inputs",
        "",
        f"- Snapshot: `{snapshot_id}`",
        "- Max taxonomic neighbors per target: "
        f"{params.get('max_taxonomic_neighbors_per_target', '?')}",
        f"- Include same-order fallback: {params.get('include_same_order', False)}",
        f"- Ready threshold: {params.get('ready_threshold', READY_THRESHOLD)} candidates",
        "",
        "---",
        "",
        "## Decision",
        "",
        f"**{decision}**",
        "",
        "---",
        "",
        "## Source Distribution",
        "",
        "| Source | Relationships |",
        "|---|---|",
        f"| iNaturalist similar species | {by_source.get('inaturalist_similar_species', 0)} |",
        f"| Taxonomic — same genus | {by_source.get('taxonomic_neighbor_same_genus', 0)} |",
        f"| Taxonomic — same family | {by_source.get('taxonomic_neighbor_same_family', 0)} |",
        f"| Taxonomic — same order | {by_source.get('taxonomic_neighbor_same_order', 0)} |",
        f"| **Total** | **{total_rel}** |",
        "",
        "---",
        "",
        "## Readiness Metrics",
        "",
        "| Metric | Count |",
        "|---|---|",
        f"| Target taxa | {n} |",
        f"| Targets with ≥{READY_THRESHOLD} candidates | {ready_count} |",
        f"| Targets with ≥{READY_THRESHOLD} usable FR candidates | {ready_fr} |",
        f"| Targets with only taxonomic candidates | {taxo_only} |",
        f"| Targets with insufficient candidates | {insufficient} |",
        f"| Targets with no candidates | {no_cand} |",
        "",
        "---",
        "",
        "## Unresolved and Referenced Taxon Needs",
        "",
        f"- Unresolved candidates (no canonical or referenced taxon record): **{unresolved}**",
        f"- Referenced taxon shells needed: **{ref_needed}**",
        f"- Referenced taxon shell candidates (Phase D): **{ref_candidate_count}**",
        f"- Candidates missing French name: **{missing_fr}**",
        (
            "- Emergency diversity fallback generated: **No**"
            if no_emergency
            else "- Emergency diversity fallback generated: **Yes**"
        ),
        "",
    ]

    if gaps.get("referenced_taxon_shells_needed"):
        lines += [
            "### Referenced Taxon Shell Needs",
            "",
        ]
        for cname in gaps["referenced_taxon_shells_needed"][:20]:
            lines.append(f"- {cname}")
        if len(gaps["referenced_taxon_shells_needed"]) > 20:
            lines.append(f"- … and {len(gaps['referenced_taxon_shells_needed']) - 20} more")
        lines.append("")

    if gaps.get("targets_not_ready"):
        lines += [
            "---",
            "",
            "## Targets Not Ready",
            "",
        ]
        for tname in gaps["targets_not_ready"][:20]:
            lines.append(f"- {tname}")
        if len(gaps["targets_not_ready"]) > 20:
            lines.append(f"- … and {len(gaps['targets_not_ready']) - 20} more")
        lines.append("")

    lines += [
        "---",
        "",
        "## Per-Target Summary (first 20)",
        "",
        "| Target | iNat | Genus | Family | Order | Total | FR-usable | Readiness |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in per_target[:20]:
        lines.append(
            f"| {s['scientific_name']} "
            f"| {s['inat_candidates']} "
            f"| {s['same_genus_candidates']} "
            f"| {s['same_family_candidates']} "
            f"| {s['same_order_candidates']} "
            f"| {s['total_candidates']} "
            f"| {s['usable_fr_candidates']} "
            f"| {s['readiness']} |"
        )
    if len(per_target) > 20:
        lines.append(f"| … ({len(per_target) - 20} more) | | | | | | | |")

    lines += [
        "",
        "---",
        "",
        "## Recommendation for Next Phase",
        "",
    ]

    if decision == "READY_FOR_AI_RANKING_DESIGN":
        lines += [
            "The candidate set is sufficient to proceed with AI ranking design.",
            "Next: design AI pedagogical ranking pass over existing candidates.",
        ]
    elif decision == "READY_FOR_REFERENCED_TAXON_HARVEST":
        lines += [
            f"Harvest {ref_needed} referenced taxon shells before proceeding.",
            "Once shells exist, re-run generation to promote unresolved candidates.",
        ]
    elif decision == "NEEDS_TAXON_ENRICHMENT_BEFORE_DISTRACTORS":
        lines += [
            "iNaturalist similar-species hints are missing.",
            "Trigger iNat enrichment pass to populate `similar_taxa` for all targets.",
            "Then re-run this generator.",
        ]
    else:
        lines += [
            "Distractor coverage is insufficient.",
            "Review targets not ready and address individually.",
        ]

    lines += [
        "",
        "---",
        "",
        f"*Generated: {today} | snapshot: {snapshot_id} | status: {exec_status}*",
        "",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate DistractorRelationship candidate artifacts."
    )
    parser.add_argument("--snapshot-id", default=DEFAULT_SNAPSHOT_ID)
    parser.add_argument(
        "--input-path",
        type=Path,
        help="Base directory for raw iNat snapshots (default: data/raw/inaturalist)",
    )
    parser.add_argument(
        "--audit-json",
        type=Path,
        help="Optional path to existing current-state audit JSON (informational only)",
    )
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument(
        "--max-taxonomic-neighbors-per-target",
        type=int,
        default=DEFAULT_MAX_NEIGHBORS,
    )
    parser.add_argument(
        "--include-same-order",
        action="store_true",
        default=False,
        help="Include same-order neighbors when stronger candidates are insufficient",
    )
    parser.add_argument(
        "--normalized-path",
        type=Path,
        help="Optional explicit normalized JSON path (use Phase C enriched file for Sprint 12)",
    )
    parser.add_argument(
        "--inat-similarity-json",
        type=Path,
        default=DEFAULT_INAT_SIMILARITY_JSON,
        help="Optional Phase B evidence JSON for injecting iNat similar species hints",
    )
    parser.add_argument(
        "--referenced-shell-candidates-json",
        type=Path,
        default=DEFAULT_REFERENCED_SHELL_CANDIDATES_JSON,
        help="Optional Phase D shell candidates JSON to build virtual referenced index",
    )
    args = parser.parse_args()

    snapshot_id = args.snapshot_id
    input_base = args.input_path or DEFAULT_SNAPSHOT_BASE
    snapshot_dir = input_base / snapshot_id

    # Load normalized index for ref resolution & French name checks
    normalized_path = args.normalized_path or _find_normalized_path(
        snapshot_id, DEFAULT_NORMALIZED_BASE
    )
    normalized_by_name = _load_normalized_index(normalized_path)

    # Build canonical_by_name from normalized data (primary) or export bundle
    canonical_by_name = normalized_by_name.copy()

    # Load export bundle for referenced taxa
    export_base = REPO_ROOT / "data" / "exports"
    export_bundle = _load_export_bundle(snapshot_id, export_base)
    referenced_taxa = export_bundle.get("referenced_taxa") or []
    referenced_by_name: dict[str, dict[str, Any]] = {
        t.get("scientific_name", ""): t
        for t in referenced_taxa
        if t.get("scientific_name")
    }

    # Merge Phase D shell candidates as virtual referenced taxa (non-persistent).
    shell_candidates = _load_referenced_shell_candidates(args.referenced_shell_candidates_json)
    referenced_by_name.update(_build_referenced_by_name_from_shell_candidates(shell_candidates))

    # Phase B similar-species hints indexed by target canonical taxon ID.
    inat_hints_by_canonical_id = _load_inat_similarity_by_canonical_id(args.inat_similarity_json)

    result = run_generation(
        snapshot_dir=snapshot_dir,
        canonical_by_name=canonical_by_name,
        referenced_by_name=referenced_by_name,
        normalized_by_name=normalized_by_name,
        snapshot_id=snapshot_id,
        max_neighbors=args.max_taxonomic_neighbors_per_target,
        include_same_order=args.include_same_order,
        inat_hints_by_canonical_id=inat_hints_by_canonical_id,
        referenced_shell_candidate_count=sum(
            1
            for item in shell_candidates
            if item.get("proposed_mapping_status")
            in {"auto_referenced_high_confidence", "auto_referenced_low_confidence"}
        ),
    )

    # Write JSON
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(result, indent=2))

    # Write Markdown
    _write_markdown(result, args.output_md)

    # Print summary
    summary = result.get("summary", {})
    print(f"Decision: {result.get('decision')}")
    print(f"Target taxa: {summary.get('target_taxa_count', 0)}")
    print(f"Total relationships: {summary.get('total_relationships_generated', 0)}")
    by_source = summary.get("by_source", {})
    print(f"  iNat hints: {by_source.get('inaturalist_similar_species', 0)}")
    print(f"  Same genus: {by_source.get('taxonomic_neighbor_same_genus', 0)}")
    print(f"  Same family: {by_source.get('taxonomic_neighbor_same_family', 0)}")
    print(f"  Same order: {by_source.get('taxonomic_neighbor_same_order', 0)}")
    print(f"Targets with >=3 candidates: {summary.get('targets_with_3_plus_candidates', 0)}")
    fr_usable = summary.get('targets_with_3_plus_usable_fr_candidates', 0)
    print(f"Targets with >=3 FR-usable: {fr_usable}")
    print(f"Unresolved candidates: {summary.get('unresolved_candidate_count', 0)}")
    print(f"JSON: {args.output_json}")
    print(f"MD:   {args.output_md}")


if __name__ == "__main__":
    main()
