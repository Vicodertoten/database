"""
Sprint 12 Phase D — Referenced taxon shell preparation for distractor candidates.

This script audits iNat similar-species candidates and prepares referenced-taxon
shell candidates without creating active canonical taxa.

Default behavior is dry-run. If --apply is provided but no safe storage pathway is
configured, the script reports the required future storage work and does not mutate
records.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_SNAPSHOT_ID = "palier1-be-birds-50taxa-run003-v11-baseline"
DEFAULT_PHASE_B_PATH = Path("docs/audits/evidence/inat_similarity_enrichment_sprint12.json")
DEFAULT_CANONICAL_PATH = Path(
    "data/normalized/palier1_be_birds_50taxa_run003_v11_baseline.normalized.json"
)
DEFAULT_LOCALIZED_PATH = Path(
    "data/enriched/palier1_be_birds_50taxa_run003_v11_baseline.names_enriched_v1.json"
)
DEFAULT_CANDIDATES_PATH = Path("docs/audits/evidence/distractor_relationship_candidates_v1.json")
DEFAULT_MANUAL_CSV = Path("data/manual/taxon_common_names_i18n_sprint12.csv")
DEFAULT_EXISTING_REFERENCED_PATH = Path("data/review_overrides/referenced_taxa_snapshot.json")

DEFAULT_OUTPUT_JSON = Path("docs/audits/evidence/referenced_taxon_shell_needs_sprint12.json")
DEFAULT_OUTPUT_MD = Path("docs/audits/referenced-taxon-shell-needs-sprint12.md")
DEFAULT_OUTPUT_CANDIDATES = Path(
    "docs/audits/evidence/referenced_taxon_shell_candidates_sprint12.json"
)

_STATUS_MAPPED = "mapped"
_STATUS_AUTO_HIGH = "auto_referenced_high_confidence"
_STATUS_AUTO_LOW = "auto_referenced_low_confidence"
_STATUS_AMBIGUOUS = "ambiguous"
_STATUS_IGNORED = "ignored"

LANGS = ("fr", "en", "nl")


def _load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _load_manual_name_index(
    csv_path: Path,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    """Return indexes by source_taxon_id and scientific_name (lowercased)."""
    by_source_id: dict[str, dict[str, str]] = {}
    by_scientific: dict[str, dict[str, str]] = {}
    if not csv_path.exists():
        return by_source_id, by_scientific

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            source_taxon_id = str(row.get("source_taxon_id", "")).strip()
            scientific = str(row.get("scientific_name", "")).strip().lower()
            values = {
                "fr": str(row.get("common_name_fr", "")).strip(),
                "en": str(row.get("common_name_en", "")).strip(),
                "nl": str(row.get("common_name_nl", "")).strip(),
            }
            if source_taxon_id:
                by_source_id[source_taxon_id] = values
            if scientific:
                by_scientific[scientific] = values
    return by_source_id, by_scientific


def _build_canonical_indexes(
    canonical_taxa: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, list[str]], dict[str, dict[str, list[str]]]]:
    """
    Return:
      - iNat external id -> canonical_taxon_id
      - scientific name -> list[canonical_taxon_id]
      - canonical_taxon_id -> common_names_by_language
    """
    by_inat_id: dict[str, str] = {}
    by_scientific: dict[str, list[str]] = defaultdict(list)
    localized_by_id: dict[str, dict[str, list[str]]] = {}

    for taxon in canonical_taxa:
        canonical_id = str(taxon["canonical_taxon_id"])
        scientific_name = str(taxon.get("accepted_scientific_name", "")).strip()
        by_scientific[scientific_name.lower()].append(canonical_id)
        localized_by_id[canonical_id] = dict(taxon.get("common_names_by_language") or {})

        for mapping in taxon.get("external_source_mappings", []):
            if mapping.get("source_name") == "inaturalist" and mapping.get("external_id"):
                by_inat_id[str(mapping["external_id"])] = canonical_id

    return by_inat_id, dict(by_scientific), localized_by_id


def _parse_count_from_note(note: str | None) -> int:
    if not note:
        return 0
    match = re.search(r"count:\s*(\d+)", note)
    if not match:
        return 0
    return int(match.group(1))


def _confidence_from_hint(note: str | None) -> tuple[float, str]:
    """Count-based confidence fallback for shell prep."""
    count = _parse_count_from_note(note)
    if count >= 5:
        return 0.85, _STATUS_AUTO_HIGH
    if count >= 1:
        return 0.6, _STATUS_AUTO_LOW
    return 0.5, _STATUS_AUTO_LOW


def _extract_existing_referenced_index(data: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Normalize a potential existing referenced-taxa artifact into source_taxon_id index."""
    if not data:
        return {}

    candidates = data.get("referenced_taxa")
    if candidates is None and isinstance(data, list):
        candidates = data
    if candidates is None:
        candidates = data.get("items", [])

    index: dict[str, dict[str, Any]] = {}
    for item in candidates or []:
        source_taxon_id = str(item.get("source_taxon_id", "")).strip()
        if source_taxon_id:
            index[source_taxon_id] = item
    return index


def _merge_names(
    hint_common_name: str | None,
    manual_values: dict[str, str] | None,
    canonical_values: dict[str, list[str]] | None,
) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {"fr": [], "en": [], "nl": []}

    # Priority 1: canonical localized names (for mapped candidates)
    for lang in LANGS:
        if canonical_values and canonical_values.get(lang):
            merged[lang] = [str(canonical_values[lang][0]).strip()]

    # Priority 2: manual CSV for missing languages
    if manual_values:
        for lang in LANGS:
            if not merged[lang] and manual_values.get(lang):
                merged[lang] = [manual_values[lang]]

    # Priority 3: hint common_name as EN fallback
    if not merged["en"] and hint_common_name:
        merged["en"] = [hint_common_name]

    return merged


def prepare_shell_candidates(
    *,
    phase_b_evidence: dict[str, Any],
    canonical_taxa: list[dict[str, Any]],
    localized_taxa: list[dict[str, Any]] | None,
    existing_referenced: dict[str, Any] | None,
    manual_csv_path: Path,
) -> dict[str, Any]:
    by_inat_id, by_scientific, canonical_localized = _build_canonical_indexes(canonical_taxa)

    # Prefer localized names from Phase C enriched output when available.
    if localized_taxa:
        for taxon in localized_taxa:
            canonical_id = str(taxon.get("canonical_taxon_id", ""))
            if canonical_id:
                canonical_localized[canonical_id] = dict(
                    taxon.get("common_names_by_language") or {}
                )

    existing_index = _extract_existing_referenced_index(existing_referenced)
    manual_by_source_id, manual_by_scientific = _load_manual_name_index(manual_csv_path)

    grouped: dict[str, dict[str, Any]] = {}
    for target in phase_b_evidence.get("per_target", []):
        target_id = str(target.get("canonical_taxon_id", "")).strip()
        for hint in target.get("hints", []):
            source_taxon_id = str(hint.get("external_taxon_id", "")).strip()
            if not source_taxon_id:
                continue

            scientific_name = str(hint.get("accepted_scientific_name", "")).strip()
            common_name = str(hint.get("common_name", "")).strip() or None
            note = str(hint.get("note", "")).strip() or None

            entry = grouped.get(source_taxon_id)
            if entry is None:
                entry = {
                    "source": "inaturalist_similar_species",
                    "source_taxon_id": source_taxon_id,
                    "scientific_name": scientific_name,
                    "hint_common_name": common_name,
                    "hints_seen": 0,
                    "source_targets": [],
                    "notes_seen": [],
                }
                grouped[source_taxon_id] = entry

            entry["hints_seen"] += 1
            if target_id and target_id not in entry["source_targets"]:
                entry["source_targets"].append(target_id)
            if note and note not in entry["notes_seen"]:
                entry["notes_seen"].append(note)
            # Keep first non-empty scientific/common names.
            if not entry["scientific_name"] and scientific_name:
                entry["scientific_name"] = scientific_name
            if not entry["hint_common_name"] and common_name:
                entry["hint_common_name"] = common_name

    shell_candidates: list[dict[str, Any]] = []
    metrics = {
        "total_candidate_taxa_from_inat_similar_species": 0,
        "candidates_mapped_to_canonical_taxa": 0,
        "candidates_already_existing_as_referenced_taxa": 0,
        "candidates_needing_new_referenced_shell": 0,
        "candidates_ambiguous": 0,
        "candidates_ignored": 0,
        "candidates_missing_scientific_name": 0,
        "candidates_with_fr_name": 0,
        "candidates_without_fr_name": 0,
    }

    for source_taxon_id, entry in sorted(grouped.items()):
        scientific_name = str(entry.get("scientific_name", "")).strip()
        scientific_key = scientific_name.lower()

        mapped_canonical_taxon_id = by_inat_id.get(source_taxon_id)
        existing_ref = existing_index.get(source_taxon_id)
        existing_referenced_taxon_id = (
            str(existing_ref.get("referenced_taxon_id", "")).strip() if existing_ref else None
        )

        reason_codes: list[str] = ["inat_similar_species"]
        confidence, inferred_status = _confidence_from_hint((entry.get("notes_seen") or [None])[0])

        if mapped_canonical_taxon_id:
            proposed_status = _STATUS_MAPPED
            confidence = 1.0
            reason_codes.extend(["mapped_by_external_id", "existing_canonical_match"])
        elif existing_ref:
            proposed_status = str(existing_ref.get("mapping_status", _STATUS_AUTO_LOW))
            reason_codes.extend(["already_exists_as_referenced_taxon"])
        elif not scientific_name:
            proposed_status = _STATUS_IGNORED
            reason_codes.extend(["missing_scientific_name"])
        else:
            scientific_matches = by_scientific.get(scientific_key, [])
            if len(scientific_matches) > 1:
                proposed_status = _STATUS_AMBIGUOUS
                reason_codes.extend(["ambiguous_scientific_name_match"])
            elif len(scientific_matches) == 1:
                # Conservative mapping by exact scientific name if unique.
                proposed_status = _STATUS_MAPPED
                mapped_canonical_taxon_id = scientific_matches[0]
                confidence = 0.95
                reason_codes.extend(["mapped_by_unique_scientific_name"])
            else:
                proposed_status = inferred_status
                reason_codes.extend(["unmapped_to_canonical", "candidate_for_referenced_shell"])

        manual_values = manual_by_source_id.get(source_taxon_id)
        if not manual_values and scientific_key:
            manual_values = manual_by_scientific.get(scientific_key)

        canonical_values = (
            canonical_localized.get(mapped_canonical_taxon_id, {})
            if mapped_canonical_taxon_id
            else None
        )
        common_names_i18n = _merge_names(
            entry.get("hint_common_name"),
            manual_values,
            canonical_values,
        )

        has_fr = bool(common_names_i18n.get("fr"))
        can_be_distractor_fr = (
            has_fr and proposed_status in {_STATUS_MAPPED, _STATUS_AUTO_HIGH}
        )

        notes: list[str] = []
        if proposed_status == _STATUS_AUTO_LOW:
            notes.append("Low confidence referenced shell; diagnostic-first handling recommended.")
        if proposed_status == _STATUS_AMBIGUOUS:
            notes.append("Requires manual mapping decision before shell creation.")
        if proposed_status == _STATUS_IGNORED:
            notes.append("Missing required scientific name; ignored for shell creation.")

        candidate = {
            "source": "inaturalist",
            "source_taxon_id": source_taxon_id,
            "scientific_name": scientific_name,
            "common_names_i18n": common_names_i18n,
            "proposed_mapping_status": proposed_status,
            "confidence": round(confidence, 3),
            "reason_codes": reason_codes,
            "mapped_canonical_taxon_id": mapped_canonical_taxon_id,
            "existing_referenced_taxon_id": existing_referenced_taxon_id,
            "can_be_distractor_fr": can_be_distractor_fr,
            "notes": notes,
            "source_targets": sorted(entry.get("source_targets", [])),
            "hints_seen": int(entry.get("hints_seen", 0)),
        }
        shell_candidates.append(candidate)

    metrics["total_candidate_taxa_from_inat_similar_species"] = len(shell_candidates)
    for candidate in shell_candidates:
        status = candidate["proposed_mapping_status"]
        if status == _STATUS_MAPPED:
            metrics["candidates_mapped_to_canonical_taxa"] += 1
        if candidate.get("existing_referenced_taxon_id"):
            metrics["candidates_already_existing_as_referenced_taxa"] += 1
        if status in {_STATUS_AUTO_HIGH, _STATUS_AUTO_LOW} and not candidate.get(
            "existing_referenced_taxon_id"
        ):
            metrics["candidates_needing_new_referenced_shell"] += 1
        if status == _STATUS_AMBIGUOUS:
            metrics["candidates_ambiguous"] += 1
        if status == _STATUS_IGNORED:
            metrics["candidates_ignored"] += 1
        if not candidate.get("scientific_name"):
            metrics["candidates_missing_scientific_name"] += 1
        if candidate.get("common_names_i18n", {}).get("fr"):
            metrics["candidates_with_fr_name"] += 1
        else:
            metrics["candidates_without_fr_name"] += 1

    return {
        "metrics": metrics,
        "shell_candidates": shell_candidates,
    }


def _determine_decision(
    metrics: dict[str, int],
    *,
    apply_requested: bool,
    safe_pathway: bool,
) -> tuple[str, str]:
    total = metrics["total_candidate_taxa_from_inat_similar_species"]
    shell_needed = metrics["candidates_needing_new_referenced_shell"]
    ambiguous = metrics["candidates_ambiguous"]

    if total == 0:
        return "NO_REFERENCED_SHELLS_NEEDED", "No iNat similar-species candidates found."
    if ambiguous > 0 and shell_needed == 0:
        return "BLOCKED_BY_AMBIGUOUS_TAXA", "Candidates exist but are blocked by ambiguity."
    if shell_needed == 0:
        return (
            "READY_FOR_DISTRACTOR_READINESS_RERUN",
            "All candidates already mapped or already represented as referenced taxa.",
        )
    if apply_requested and not safe_pathway:
        return (
            "NEEDS_REFERENCED_TAXON_STORAGE_WORK",
            "Shell candidates identified, but no safe standalone storage apply path is available.",
        )
    if safe_pathway:
        return (
            "READY_TO_CREATE_REFERENCED_TAXON_SHELLS",
            "Shell candidates are ready and can be created via safe apply path.",
        )
    return (
        "NEEDS_REFERENCED_TAXON_STORAGE_WORK",
        "Shell candidates identified. Implement a reviewed storage apply path before creation.",
    )


def _storage_work_items() -> list[str]:
    return [
        "Provide a reviewed admin script to upsert ReferencedTaxon records outside runtime paths.",
        "Use transaction-safe writes with explicit dry-run and --apply confirmation.",
        "Enforce mapping_status invariants and unique (source, source_taxon_id).",
        "Capture before/after snapshots and conflict logs for governance review.",
    ]


def run_audit(
    *,
    snapshot_id: str,
    phase_b_path: Path,
    canonical_path: Path,
    localized_path: Path | None,
    candidates_path: Path | None,
    existing_referenced_path: Path | None,
    manual_csv_path: Path,
    apply: bool,
) -> dict[str, Any]:
    phase_b = _load_json_if_exists(phase_b_path)
    if phase_b is None:
        raise FileNotFoundError(f"Phase B evidence not found: {phase_b_path}")

    canonical_data = _load_json_if_exists(canonical_path)
    if canonical_data is None:
        raise FileNotFoundError(f"Canonical taxa input not found: {canonical_path}")
    canonical_taxa = canonical_data.get("canonical_taxa", [])

    localized_taxa: list[dict[str, Any]] | None = None
    if localized_path and localized_path.exists():
        localized_data = _load_json_if_exists(localized_path)
        localized_taxa = (localized_data or {}).get("canonical_taxa", [])

    candidates_data = _load_json_if_exists(candidates_path) if candidates_path else None
    candidate_relationships = (candidates_data or {}).get("relationships", [])

    existing_referenced = (
        _load_json_if_exists(existing_referenced_path) if existing_referenced_path else None
    )

    prep = prepare_shell_candidates(
        phase_b_evidence=phase_b,
        canonical_taxa=canonical_taxa,
        localized_taxa=localized_taxa,
        existing_referenced=existing_referenced,
        manual_csv_path=manual_csv_path,
    )

    metrics = prep["metrics"]
    shell_candidates = prep["shell_candidates"]

    # We intentionally keep Phase D default in dry-run mode.
    safe_apply_pathway_available = False
    shell_creation_mode = "dry_run"
    apply_result = {
        "apply_requested": apply,
        "records_created": 0,
        "records_updated": 0,
        "storage_mutated": False,
    }

    if apply and not safe_apply_pathway_available:
        shell_creation_mode = "apply_requested_but_unavailable"

    decision, decision_note = _determine_decision(
        metrics,
        apply_requested=apply,
        safe_pathway=safe_apply_pathway_available,
    )

    evidence = {
        "audit_version": "referenced_taxon_shell_prep.v1",
        "run_date": datetime.now(UTC).isoformat(),
        "execution_status": "complete",
        "snapshot_id": snapshot_id,
        "inputs": {
            "phase_b_path": str(phase_b_path),
            "canonical_path": str(canonical_path),
            "localized_path": str(localized_path) if localized_path else None,
            "candidates_path": str(candidates_path) if candidates_path else None,
            "existing_referenced_path": (
                str(existing_referenced_path) if existing_referenced_path else None
            ),
            "manual_csv_path": str(manual_csv_path),
        },
        "decision": decision,
        "decision_note": decision_note,
        "metrics": metrics,
        "shell_creation_mode": shell_creation_mode,
        "safe_apply_pathway_available": safe_apply_pathway_available,
        "apply_result": apply_result,
        "required_future_storage_changes": (
            _storage_work_items() if not safe_apply_pathway_available else []
        ),
        "candidate_relationships_count": len(candidate_relationships),
    }

    return {
        "evidence": evidence,
        "shell_candidates": shell_candidates,
    }


def write_markdown_report(evidence: dict[str, Any], output_path: Path) -> None:
    run_date = evidence["run_date"][:10]
    metrics = evidence["metrics"]

    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        f"last_reviewed: {run_date}",
        "source_of_truth: docs/audits/referenced-taxon-shell-needs-sprint12.md",
        "scope: audit",
        "---",
        "",
        "# Referenced Taxon Shell Needs — Sprint 12",
        "",
        "## Purpose",
        "",
        "Audit iNaturalist similar-species candidates and prepare referenced taxon shell "
        "candidates for unmapped taxa without creating active canonical taxa.",
        "",
        "## Summary Metrics",
        "",
        "| Metric | Value |",
        "|---|---|",
        (
            "| Total candidate taxa from iNat similar species | "
            f"{metrics['total_candidate_taxa_from_inat_similar_species']} |"
        ),
        (
            "| Candidates mapped to canonical taxa | "
            f"{metrics['candidates_mapped_to_canonical_taxa']} |"
        ),
        (
            "| Candidates already existing as referenced taxa | "
            f"{metrics['candidates_already_existing_as_referenced_taxa']} |"
        ),
        (
            "| Candidates needing new referenced shell | "
            f"{metrics['candidates_needing_new_referenced_shell']} |"
        ),
        f"| Candidates ambiguous | {metrics['candidates_ambiguous']} |",
        f"| Candidates ignored | {metrics['candidates_ignored']} |",
        (
            "| Candidates missing scientific name | "
            f"{metrics['candidates_missing_scientific_name']} |"
        ),
        f"| Candidates with FR name | {metrics['candidates_with_fr_name']} |",
        f"| Candidates without FR name | {metrics['candidates_without_fr_name']} |",
        "",
        "## Decision",
        "",
        f"**{evidence['decision']}**",
        "",
        evidence.get("decision_note", ""),
        "",
        "## Shell Creation Mode",
        "",
        f"- mode: {evidence.get('shell_creation_mode')}",
        f"- safe_apply_pathway_available: {evidence.get('safe_apply_pathway_available')}",
    ]

    future_work = evidence.get("required_future_storage_changes") or []
    if future_work:
        lines += ["", "## Required Future Storage Changes", ""]
        for item in future_work:
            lines.append(f"- {item}")

    lines += [
        "",
        "## Guardrails",
        "",
        "- No active CanonicalTaxon was created automatically.",
        "- No canonical promotion was performed automatically.",
        "- Runtime, pack materialization, compile_pack_v2, and QuestionOption were untouched.",
        "- This phase only prepares shell candidates and governance evidence.",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sprint 12 Phase D — Referenced taxon shell needs audit"
    )
    parser.add_argument("--snapshot-id", default=DEFAULT_SNAPSHOT_ID)
    parser.add_argument("--phase-b-path", type=Path, default=DEFAULT_PHASE_B_PATH)
    parser.add_argument("--canonical-path", type=Path, default=DEFAULT_CANONICAL_PATH)
    parser.add_argument("--localized-path", type=Path, default=DEFAULT_LOCALIZED_PATH)
    parser.add_argument("--candidates-path", type=Path, default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument(
        "--existing-referenced-path",
        type=Path,
        default=DEFAULT_EXISTING_REFERENCED_PATH,
    )
    parser.add_argument("--manual-csv-path", type=Path, default=DEFAULT_MANUAL_CSV)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--output-candidates", type=Path, default=DEFAULT_OUTPUT_CANDIDATES)
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help=(
            "Attempt shell creation. If no safe apply pathway exists, this is reported and "
            "no storage mutation is performed."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        result = run_audit(
            snapshot_id=args.snapshot_id,
            phase_b_path=args.phase_b_path,
            canonical_path=args.canonical_path,
            localized_path=args.localized_path,
            candidates_path=args.candidates_path,
            existing_referenced_path=args.existing_referenced_path,
            manual_csv_path=args.manual_csv_path,
            apply=args.apply,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    evidence = result["evidence"]
    shell_candidates = result["shell_candidates"]

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    candidates_payload = {
        "artifact_version": "referenced_taxon_shell_candidates.v1",
        "run_date": evidence["run_date"],
        "snapshot_id": args.snapshot_id,
        "count": len(shell_candidates),
        "items": shell_candidates,
    }
    args.output_candidates.parent.mkdir(parents=True, exist_ok=True)
    args.output_candidates.write_text(
        json.dumps(candidates_payload, indent=2),
        encoding="utf-8",
    )

    write_markdown_report(evidence, args.output_md)

    metrics = evidence["metrics"]
    print(f"Audit evidence written: {args.output_json}")
    print(f"Shell candidates written: {args.output_candidates}")
    print(f"Markdown report written: {args.output_md}")
    print()
    print("=== Summary ===")
    print(
        "  mapped candidates                : "
        f"{metrics['candidates_mapped_to_canonical_taxa']}"
    )
    print(
        "  shell candidates                 : "
        f"{metrics['candidates_needing_new_referenced_shell']}"
    )
    print(
        "  ambiguous/ignored                : "
        f"{metrics['candidates_ambiguous']}/{metrics['candidates_ignored']}"
    )
    print(f"  shell creation mode              : {evidence['shell_creation_mode']}")
    print(f"  decision                         : {evidence['decision']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
