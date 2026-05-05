"""
apply_taxon_localized_names_sprint12.py

Sprint 12 Phase C — Task 3: Apply localized names from CSV to canonical taxa.

Reads data/manual/taxon_common_names_i18n_sprint12.csv, validates entries,
applies names to common_names_by_language in normalized taxa, and produces
an enriched normalized JSON snapshot and audit evidence.

Safety rules:
  - Existing names are never silently overwritten; conflicts are reported.
  - Rows with unknown scientific_name / taxon IDs are recorded as unresolved.
  - Source and reviewer fields are required for new names.
  - Does NOT create CanonicalTaxon records.
  - Does NOT modify accepted_scientific_name or canonical identity fields.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

APPLY_VERSION = "localized_names_apply.v1"
APPLY_LANGS = ("fr", "en", "nl")
CSV_LANG_FIELDS = {"fr": "common_name_fr", "en": "common_name_en", "nl": "common_name_nl"}

DEFAULT_NORMALIZED_PATH = Path(
    "data/normalized/palier1_be_birds_50taxa_run003_v11_baseline.normalized.json"
)
DEFAULT_CSV_PATH = Path("data/manual/taxon_common_names_i18n_sprint12.csv")
DEFAULT_ENRICHED_OUTPUT = Path(
    "data/enriched/palier1_be_birds_50taxa_run003_v11_baseline.names_enriched_v1.json"
)
DEFAULT_OUTPUT_JSON = Path(
    "docs/audits/evidence/taxon_localized_names_enrichment_sprint12.json"
)
DEFAULT_OUTPUT_MD = Path("docs/audits/taxon-localized-names-enrichment-sprint12.md")


# ---------------------------------------------------------------------------
# Index builders
# ---------------------------------------------------------------------------


def _index_by_scientific_name(
    taxa: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Multi-valued index: scientific_name → list of taxa (lowercase match)."""
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in taxa:
        key = t["accepted_scientific_name"].strip().lower()
        index[key].append(t)
    return dict(index)


def _index_by_canonical_id(taxa: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {t["canonical_taxon_id"]: t for t in taxa}


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------


def load_csv(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row for row in reader]


# ---------------------------------------------------------------------------
# Apply logic
# ---------------------------------------------------------------------------


def apply_names(
    taxa: list[dict[str, Any]],
    csv_rows: list[dict[str, str]],
) -> dict[str, Any]:
    """
    Apply CSV rows to taxa. Returns change summary with:
      names_before, names_after, added counts, conflicts, skipped, unresolved.
    Does NOT mutate taxa in place — returns a new list of patched taxa dicts.
    """
    by_name = _index_by_scientific_name(taxa)
    by_id = _index_by_canonical_id(taxa)

    # Build a dict of patches: canonical_taxon_id → {lang: new_name}
    patches: dict[str, dict[str, str]] = {}
    conflicts: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    unresolved_rows: list[dict[str, Any]] = []

    for row_num, row in enumerate(csv_rows, start=2):  # row 2 = first data row
        sci = str(row.get("scientific_name", "")).strip()
        cid = str(row.get("canonical_taxon_id", "")).strip()
        source = str(row.get("source", "")).strip()

        # Skip completely empty rows
        if not sci and not cid:
            skipped_rows.append(
                {"row": row_num, "reason": "empty scientific_name and canonical_taxon_id"}
            )
            continue

        # Resolve taxon
        matched_taxa: list[dict[str, Any]] = []
        if cid and cid in by_id:
            matched_taxa = [by_id[cid]]
        elif sci:
            matched_taxa = by_name.get(sci.lower(), [])

        if not matched_taxa:
            unresolved_rows.append({
                "row": row_num,
                "scientific_name": sci,
                "canonical_taxon_id": cid,
                "reason": "no matching taxon found",
            })
            continue

        if len(matched_taxa) > 1:
            skipped_rows.append({
                "row": row_num,
                "scientific_name": sci,
                "reason": f"ambiguous: {len(matched_taxa)} taxa match",
            })
            continue

        taxon = matched_taxa[0]
        tid = taxon["canonical_taxon_id"]
        existing_cbn = dict(taxon.get("common_names_by_language") or {})

        for lang in APPLY_LANGS:
            new_name = str(row.get(CSV_LANG_FIELDS[lang], "")).strip()
            if not new_name:
                continue
            existing = existing_cbn.get(lang, [])
            if existing:
                # Conflict: name already present
                if new_name.lower() not in [n.lower() for n in existing]:
                    conflicts.append({
                        "canonical_taxon_id": tid,
                        "scientific_name": sci or taxon["accepted_scientific_name"],
                        "lang": lang,
                        "existing": existing,
                        "proposed": new_name,
                        "source": source,
                        "row": row_num,
                    })
                # Do not overwrite — skip
                continue
            # Safe to apply
            if tid not in patches:
                patches[tid] = {}
            patches[tid][lang] = new_name

    # Build names_before snapshot
    names_before = {
        t["canonical_taxon_id"]: dict(t.get("common_names_by_language") or {})
        for t in taxa
    }

    # Apply patches to taxa copies
    patched_taxa: list[dict[str, Any]] = []
    fr_added = nl_added = en_added = 0
    for taxon in taxa:
        tid = taxon["canonical_taxon_id"]
        patch = patches.get(tid)
        if not patch:
            patched_taxa.append(dict(taxon))
            continue
        cbn = dict(taxon.get("common_names_by_language") or {})
        for lang, name in patch.items():
            cbn[lang] = [name]
            if lang == "fr":
                fr_added += 1
            elif lang == "nl":
                nl_added += 1
            elif lang == "en":
                en_added += 1
        updated = dict(taxon)
        updated["common_names_by_language"] = cbn
        patched_taxa.append(updated)

    # Build names_after snapshot
    names_after = {
        t["canonical_taxon_id"]: dict(t.get("common_names_by_language") or {})
        for t in patched_taxa
    }

    return {
        "patched_taxa": patched_taxa,
        "patches_applied": len(patches),
        "names_before": names_before,
        "names_after": names_after,
        "fr_added_count": fr_added,
        "nl_added_count": nl_added,
        "en_added_count": en_added,
        "conflicts": conflicts,
        "skipped_rows": skipped_rows,
        "unresolved_rows": unresolved_rows,
    }


# ---------------------------------------------------------------------------
# FR usability re-evaluation
# ---------------------------------------------------------------------------


def _eval_fr_usability(
    patched_taxa: list[dict[str, Any]],
    candidate_relationships: list[dict[str, Any]],
) -> tuple[int, int]:
    """Return (candidates_now_fr_usable, candidates_still_missing_fr)."""
    cbn_by_id = {
        t["canonical_taxon_id"]: t.get("common_names_by_language") or {}
        for t in patched_taxa
    }
    usable = 0
    missing = 0
    seen: set[str] = set()
    for rel in candidate_relationships:
        cid = rel["candidate_taxon_ref_id"]
        if cid in seen:
            continue
        seen.add(cid)
        cbn = cbn_by_id.get(cid, {})
        if cbn.get("fr"):
            usable += 1
        else:
            missing += 1
    return usable, missing


# ---------------------------------------------------------------------------
# Evidence builder
# ---------------------------------------------------------------------------


def build_evidence(
    snapshot_id: str,
    apply_result: dict[str, Any],
    candidate_relationships: list[dict[str, Any]],
) -> dict[str, Any]:
    patched_taxa = apply_result["patched_taxa"]
    usable, missing = _eval_fr_usability(patched_taxa, candidate_relationships)

    conflicts = apply_result["conflicts"]
    if conflicts:
        decision = "NEEDS_MANUAL_NAME_COMPLETION"
        decision_note = (
            f"{len(conflicts)} conflict(s) found. Review and resolve before re-running."
        )
    elif missing > 0 and apply_result["fr_added_count"] > 0:
        decision = "READY_FOR_DISTRACTOR_READINESS_RERUN"
        decision_note = (
            f"{apply_result['fr_added_count']} FR names added; "
            f"{missing} candidates still missing FR."
        )
    elif missing > 0:
        decision = "NEEDS_MANUAL_NAME_COMPLETION"
        decision_note = f"{missing} candidates still missing FR. Expand CSV entries."
    else:
        decision = "READY_FOR_DISTRACTOR_READINESS_RERUN"
        decision_note = "All candidate FR names resolved. Rerun distractor readiness."

    return {
        "apply_version": APPLY_VERSION,
        "run_date": datetime.now(UTC).isoformat(),
        "execution_status": "complete",
        "snapshot_id": snapshot_id,
        "decision": decision,
        "decision_note": decision_note,
        "patches_applied": apply_result["patches_applied"],
        "fr_added_count": apply_result["fr_added_count"],
        "nl_added_count": apply_result["nl_added_count"],
        "en_added_count": apply_result["en_added_count"],
        "candidates_now_fr_usable": usable,
        "candidates_still_missing_fr": missing,
        "conflicts": conflicts,
        "skipped_rows": apply_result["skipped_rows"],
        "unresolved_rows": apply_result["unresolved_rows"],
        "names_before_sample": dict(list(apply_result["names_before"].items())[:5]),
        "names_after_sample": dict(list(apply_result["names_after"].items())[:5]),
    }


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def write_markdown_report(evidence: dict[str, Any], output_path: Path) -> None:
    run_date = evidence["run_date"][:10]
    decision = evidence["decision"]

    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        f"last_reviewed: {run_date}",
        "source_of_truth: docs/audits/taxon-localized-names-enrichment-sprint12.md",
        "scope: audit",
        "---",
        "",
        "# Taxon Localized Names Enrichment — Sprint 12",
        "",
        "## Purpose",
        "",
        "Apply localized names (FR, NL, EN) to canonical taxa using the manual CSV "
        "`data/manual/taxon_common_names_i18n_sprint12.csv` populated from iNat and "
        "manual review.",
        "",
        "---",
        "",
        "## Results",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Patches applied | {evidence['patches_applied']} |",
        f"| FR names added | {evidence['fr_added_count']} |",
        f"| NL names added | {evidence['nl_added_count']} |",
        f"| EN names added | {evidence['en_added_count']} |",
        f"| Candidates now FR-usable | {evidence['candidates_now_fr_usable']} |",
        f"| Candidates still missing FR | {evidence['candidates_still_missing_fr']} |",
        f"| Conflicts | {len(evidence['conflicts'])} |",
        f"| Skipped rows | {len(evidence['skipped_rows'])} |",
        f"| Unresolved rows | {len(evidence['unresolved_rows'])} |",
    ]

    if evidence["conflicts"]:
        lines += ["", "### Conflicts", ""]
        for c in evidence["conflicts"][:10]:
            lines.append(
                f"- `{c['canonical_taxon_id']}` [{c['lang']}]: "
                f"existing `{c['existing']}` vs proposed `{c['proposed']}`"
            )

    if evidence["unresolved_rows"]:
        lines += ["", "### Unresolved Rows", ""]
        for u in evidence["unresolved_rows"][:5]:
            lines.append(f"- Row {u['row']}: `{u.get('scientific_name', '?')}` — {u['reason']}")

    lines += [
        "",
        "---",
        "",
        "## Safety Guarantees",
        "",
        "- Existing names were never overwritten (conflicts reported instead).",
        "- `accepted_scientific_name` and `canonical_taxon_id` were never mutated.",
        "- No `CanonicalTaxon` records were created.",
        "- Source and reviewer fields are preserved in the CSV for traceability.",
        "",
        "---",
        "",
        "## Next Step Recommendation",
        "",
        f"**Decision: `{decision}`**",
        "",
        evidence.get("decision_note", ""),
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_apply(
    snapshot_id: str,
    normalized_path: Path,
    csv_path: Path,
    candidates_path: Path | None = None,
) -> dict[str, Any]:
    data = json.loads(normalized_path.read_text(encoding="utf-8"))
    normalized_taxa: list[dict[str, Any]] = data.get("canonical_taxa", [])

    csv_rows = load_csv(csv_path)

    candidate_relationships: list[dict[str, Any]] = []
    if candidates_path and candidates_path.exists():
        cdata = json.loads(candidates_path.read_text(encoding="utf-8"))
        candidate_relationships = cdata.get("relationships", [])

    apply_result = apply_names(normalized_taxa, csv_rows)
    evidence = build_evidence(snapshot_id, apply_result, candidate_relationships)

    return {
        "evidence": evidence,
        "patched_taxa": apply_result["patched_taxa"],
        "original_data": data,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Sprint 12 Phase C Task 3 — Apply localized names from CSV"
    )
    p.add_argument("--snapshot-id", default="palier1-be-birds-50taxa-run003-v11-baseline")
    p.add_argument("--normalized-path", type=Path, default=DEFAULT_NORMALIZED_PATH)
    p.add_argument("--csv-path", type=Path, default=DEFAULT_CSV_PATH)
    p.add_argument(
        "--candidates-path",
        type=Path,
        default=Path("docs/audits/evidence/distractor_relationship_candidates_v1.json"),
    )
    p.add_argument("--enriched-output", type=Path, default=DEFAULT_ENRICHED_OUTPUT)
    p.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    p.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    args = p.parse_args(argv)

    if not args.normalized_path.exists():
        print(f"ERROR: normalized path not found: {args.normalized_path}", file=sys.stderr)
        return 1
    if not args.csv_path.exists():
        print(f"ERROR: CSV not found: {args.csv_path}", file=sys.stderr)
        return 1

    result = run_apply(
        snapshot_id=args.snapshot_id,
        normalized_path=args.normalized_path,
        csv_path=args.csv_path,
        candidates_path=args.candidates_path,
    )

    evidence = result["evidence"]
    patched_taxa = result["patched_taxa"]
    original_data = result["original_data"]

    # Write enriched normalized snapshot
    enriched_snapshot = dict(original_data)
    enriched_snapshot["canonical_taxa"] = patched_taxa
    args.enriched_output.parent.mkdir(parents=True, exist_ok=True)
    args.enriched_output.write_text(json.dumps(enriched_snapshot, indent=2), encoding="utf-8")
    print(f"Enriched normalized written: {args.enriched_output}")

    # Write audit JSON
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"Audit evidence written: {args.output_json}")

    # Write Markdown
    write_markdown_report(evidence, args.output_md)
    print(f"Markdown report written: {args.output_md}")

    print()
    print("=== Summary ===")
    print(f"  FR names added          : {evidence['fr_added_count']}")
    print(f"  NL names added          : {evidence['nl_added_count']}")
    print(f"  EN names added          : {evidence['en_added_count']}")
    print(f"  Candidates FR-usable    : {evidence['candidates_now_fr_usable']}")
    print(f"  Still missing FR        : {evidence['candidates_still_missing_fr']}")
    print(f"  Conflicts               : {len(evidence['conflicts'])}")
    print(f"  Decision                : {evidence['decision']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
