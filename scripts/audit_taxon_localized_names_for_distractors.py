"""
audit_taxon_localized_names_for_distractors.py

Sprint 12 Phase C — Task 1: Audit missing localized names for distractor readiness.

Workflow:
1. Load canonical taxa from normalized JSON.
2. Load candidate relationships from Phase B/Phase 3 evidence.
3. Identify taxa (targets + candidates) missing fr/nl/en in common_names_by_language.
4. For each taxon with a missing language, attempt to resolve names from:
   a. iNat all_names cache (data/enriched/{snapshot_id}/all_names/{canonical_taxon_id}.json)
   b. Live iNat GET /v1/taxa/{id}?all_names=true  (when --fetch-inat is set)
5. Write proposed names to data/manual/taxon_common_names_i18n_sprint12.csv (if --write-csv).
6. Write audit evidence JSON and Markdown.

Outputs:
  docs/audits/evidence/taxon_localized_names_gap_audit_sprint12.json
  docs/audits/taxon-localized-names-gap-audit-sprint12.md
  data/manual/taxon_common_names_i18n_sprint12.csv  (optional, with --write-csv)
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

AUDIT_VERSION = "localized_names_gap.v1"
INAT_TAXA_API = "https://api.inaturalist.org/v1/taxa"
USER_AGENT = "BioLearnDatabaseBot/1.0"
REQUEST_TIMEOUT = 15
RATE_LIMIT_SECONDS = 1.1
TARGET_LANGS = ("fr", "en", "nl")

DEFAULT_SNAPSHOT_ID = "palier1-be-birds-50taxa-run003-v11-baseline"
DEFAULT_NORMALIZED_PATH = Path(
    "data/normalized/palier1_be_birds_50taxa_run003_v11_baseline.normalized.json"
)
DEFAULT_CANDIDATES_PATH = Path(
    "docs/audits/evidence/distractor_relationship_candidates_v1.json"
)
DEFAULT_ENRICHED_DIR = Path("data/enriched")
DEFAULT_OUTPUT_JSON = Path(
    "docs/audits/evidence/taxon_localized_names_gap_audit_sprint12.json"
)
DEFAULT_OUTPUT_MD = Path("docs/audits/taxon-localized-names-gap-audit-sprint12.md")
DEFAULT_MANUAL_CSV = Path("data/manual/taxon_common_names_i18n_sprint12.csv")

CSV_COLUMNS = [
    "scientific_name",
    "source_taxon_id",
    "canonical_taxon_id",
    "referenced_taxon_id",
    "common_name_fr",
    "common_name_en",
    "common_name_nl",
    "source",
    "reviewer",
    "notes",
]


# ---------------------------------------------------------------------------
# iNat all_names helpers
# ---------------------------------------------------------------------------


def _all_names_cache_path(enriched_dir: Path, snapshot_id: str, canonical_taxon_id: str) -> Path:
    slug = canonical_taxon_id.replace(":", "_")
    return enriched_dir / snapshot_id / "all_names" / f"{slug}.json"


def _fetch_all_names(inat_id: str, *, timeout: int = REQUEST_TIMEOUT) -> dict[str, Any]:
    url = f"{INAT_TAXA_API}/{inat_id}?all_names=true"
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_preferred_names_from_all_names(
    payload: dict[str, Any],
) -> dict[str, str]:
    """Return {locale: first_is_valid_name} from all_names array."""
    results = payload.get("results", [payload])
    if not results:
        return {}
    taxon = results[0]
    names_list: list[dict[str, Any]] = taxon.get("names", [])
    # Prefer is_valid=True; take first per locale
    by_locale: dict[str, str] = {}
    for entry in names_list:
        locale = str(entry.get("locale", "")).strip().lower()
        name = str(entry.get("name", "")).strip()
        if not locale or not name:
            continue
        if locale not in by_locale and entry.get("is_valid", True):
            by_locale[locale] = name
    # Fallback: preferred_common_name → en
    if "en" not in by_locale:
        pcn = taxon.get("preferred_common_name", "")
        if pcn:
            by_locale["en"] = pcn
    return by_locale


def _load_or_fetch_all_names(
    inat_id: str,
    canonical_taxon_id: str,
    *,
    enriched_dir: Path,
    snapshot_id: str,
    fetch_live: bool,
) -> tuple[dict[str, str], str]:
    """Return (locale→name dict, source_label)."""
    cache_file = _all_names_cache_path(enriched_dir, snapshot_id, canonical_taxon_id)
    if cache_file.exists():
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
        return _extract_preferred_names_from_all_names(payload), "inat_all_names_cache"

    if not fetch_live:
        return {}, "unavailable_no_cache_no_fetch"

    try:
        payload = _fetch_all_names(inat_id)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        time.sleep(RATE_LIMIT_SECONDS)
        return _extract_preferred_names_from_all_names(payload), "inat_all_names_live"
    except (HTTPError, URLError, TimeoutError) as exc:
        return {}, f"fetch_error:{exc}"


# ---------------------------------------------------------------------------
# Gap analysis
# ---------------------------------------------------------------------------


def _get_lang(taxon: dict[str, Any], lang: str) -> list[str]:
    cbn = taxon.get("common_names_by_language") or {}
    return cbn.get(lang, [])


def _get_inat_id(taxon: dict[str, Any]) -> str | None:
    for m in taxon.get("external_source_mappings", []):
        if m.get("source_name") == "inaturalist":
            return str(m["external_id"])
    return None


def analyze_names_gap(
    normalized_taxa: list[dict[str, Any]],
    candidate_relationships: list[dict[str, Any]],
    *,
    enriched_dir: Path,
    snapshot_id: str,
    fetch_live: bool,
) -> dict[str, Any]:
    """
    For every target taxon and every unique candidate taxon,
    analyze current name coverage and attempt to resolve missing names from iNat.
    Returns per-taxon analysis dict.
    """
    # Collect candidate taxon IDs (both targets and candidates)
    target_ids: set[str] = {t["canonical_taxon_id"] for t in normalized_taxa}
    candidate_ids: set[str] = set()
    for rel in candidate_relationships:
        candidate_ids.add(rel["candidate_taxon_ref_id"])

    per_taxon: list[dict[str, Any]] = []

    for taxon in normalized_taxa:
        tid = taxon["canonical_taxon_id"]
        inat_id = _get_inat_id(taxon)
        existing_fr = _get_lang(taxon, "fr")
        existing_nl = _get_lang(taxon, "nl")
        existing_en = _get_lang(taxon, "en")

        proposed_names: dict[str, str] = {}
        name_source = "none"

        # Try to resolve missing langs from iNat
        missing = [
            lang for lang, vals in [("fr", existing_fr), ("nl", existing_nl), ("en", existing_en)]
            if not vals
        ]
        if missing and inat_id:
            resolved, name_source = _load_or_fetch_all_names(
                inat_id,
                tid,
                enriched_dir=enriched_dir,
                snapshot_id=snapshot_id,
                fetch_live=fetch_live,
            )
            proposed_names = {lang: resolved[lang] for lang in missing if lang in resolved}

        per_taxon.append({
            "canonical_taxon_id": tid,
            "scientific_name": taxon["accepted_scientific_name"],
            "inat_id": inat_id,
            "is_target": tid in target_ids,
            "is_candidate": tid in candidate_ids,
            "existing_fr": existing_fr,
            "existing_nl": existing_nl,
            "existing_en": existing_en,
            "missing_langs": missing,
            "proposed_names": proposed_names,
            "name_source": name_source,
            "fr_resolvable": bool(proposed_names.get("fr")),
            "nl_resolvable": bool(proposed_names.get("nl")),
            "en_resolvable": bool(proposed_names.get("en")),
        })

    return {"per_taxon": per_taxon}


# ---------------------------------------------------------------------------
# FR usability projection
# ---------------------------------------------------------------------------


def _project_fr_usability(
    candidate_relationships: list[dict[str, Any]],
    per_taxon_by_id: dict[str, dict[str, Any]],
) -> dict[str, int]:
    """Project how many candidates would be FR-usable after applying proposed names."""
    now_fr = 0
    after_fr = 0
    for rel in candidate_relationships:
        cid = rel["candidate_taxon_ref_id"]
        if rel.get("candidate_has_french_name"):
            now_fr += 1
            after_fr += 1
        elif per_taxon_by_id.get(cid, {}).get("fr_resolvable"):
            after_fr += 1
    return {"candidates_fr_usable_now": now_fr, "candidates_fr_usable_projected": after_fr}


# ---------------------------------------------------------------------------
# Evidence builder
# ---------------------------------------------------------------------------


def build_evidence(
    snapshot_id: str,
    normalized_taxa: list[dict[str, Any]],
    candidate_relationships: list[dict[str, Any]],
    gap_analysis: dict[str, Any],
    *,
    fetch_live: bool,
) -> dict[str, Any]:
    per_taxon = gap_analysis["per_taxon"]
    per_taxon_by_id = {t["canonical_taxon_id"]: t for t in per_taxon}

    targets = [t for t in per_taxon if t["is_target"]]
    candidates = [t for t in per_taxon if t["is_candidate"]]

    # Targets missing
    targets_missing_fr = [t for t in targets if not t["existing_fr"]]
    targets_missing_nl = [t for t in targets if not t["existing_nl"]]
    targets_missing_en = [t for t in targets if not t["existing_en"]]

    # Candidates missing
    cand_ids = {t["canonical_taxon_id"] for t in candidates}
    cand_taxa = [t for t in per_taxon if t["canonical_taxon_id"] in cand_ids]
    cands_missing_fr = [t for t in cand_taxa if not t["existing_fr"]]
    cands_missing_nl = [t for t in cand_taxa if not t["existing_nl"]]
    cands_missing_en = [t for t in cand_taxa if not t["existing_en"]]

    # Resolution stats
    fr_resolvable = [t for t in cands_missing_fr if t["fr_resolvable"]]
    nl_resolvable = [t for t in cands_missing_nl if t["nl_resolvable"]]
    fr_needing_manual = [t for t in cands_missing_fr if not t["fr_resolvable"]]

    # FR usability projection
    usability = _project_fr_usability(candidate_relationships, per_taxon_by_id)

    # Determine names_from_inat / names_requiring_manual
    names_from_inat = sum(
        1 for t in per_taxon if t["proposed_names"] and "inat" in t["name_source"]
    )
    names_requiring_manual = len(fr_needing_manual)

    # Decision
    if fr_needing_manual:
        decision = "NEEDS_MANUAL_NAME_COMPLETION"
        decision_note = (
            f"{len(fr_needing_manual)} candidate(s) have FR names not resolvable from iNat. "
            "Populate data/manual/taxon_common_names_i18n_sprint12.csv and re-run apply script."
        )
    elif not fetch_live and cands_missing_fr:
        decision = "NEEDS_MANUAL_NAME_COMPLETION"
        decision_note = (
            f"{len(cands_missing_fr)} candidates missing FR. "
            "Run with --fetch-inat to attempt resolution from iNat, or populate CSV manually."
        )
    elif usability["candidates_fr_usable_projected"] > 0:
        decision = "READY_FOR_DISTRACTOR_READINESS_RERUN"
        decision_note = (
            f"After applying names, {usability['candidates_fr_usable_projected']} "
            "candidates will be FR-usable. Proceed to apply, then rerun readiness."
        )
    else:
        decision = "BLOCKED_BY_NAME_SOURCE_GAPS"
        decision_note = "No FR names resolvable from available sources."

    return {
        "audit_version": AUDIT_VERSION,
        "run_date": datetime.now(UTC).isoformat(),
        "execution_status": "complete",
        "snapshot_id": snapshot_id,
        "fetch_live": fetch_live,
        "decision": decision,
        "decision_note": decision_note,
        "targets_total": len(targets),
        "targets_missing_fr": len(targets_missing_fr),
        "targets_missing_nl": len(targets_missing_nl),
        "targets_missing_en": len(targets_missing_en),
        "candidate_taxa_total": len(cand_ids),
        "candidate_taxa_missing_fr": len(cands_missing_fr),
        "candidate_taxa_missing_nl": len(cands_missing_nl),
        "candidate_taxa_missing_en": len(cands_missing_en),
        "fr_resolvable_from_inat": len(fr_resolvable),
        "nl_resolvable_from_inat": len(nl_resolvable),
        "names_from_inat": names_from_inat,
        "names_requiring_manual": names_requiring_manual,
        "candidates_fr_usable_now": usability["candidates_fr_usable_now"],
        "candidates_fr_usable_projected": usability["candidates_fr_usable_projected"],
        "per_taxon": per_taxon,
    }


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------


def write_proposed_csv(
    evidence: dict[str, Any],
    output_path: Path,
) -> int:
    """Write proposed names CSV from per_taxon analysis. Returns rows written."""
    rows = []
    for t in evidence["per_taxon"]:
        proposed = t.get("proposed_names", {})
        if not proposed and not any([t["existing_fr"], t["existing_nl"], t["existing_en"]]):
            # No data at all — include as blank row for manual completion
            rows.append({
                "scientific_name": t["scientific_name"],
                "source_taxon_id": t.get("inat_id", ""),
                "canonical_taxon_id": t["canonical_taxon_id"],
                "referenced_taxon_id": "",
                "common_name_fr": "",
                "common_name_en": (t["existing_en"] or [""])[0] if t["existing_en"] else "",
                "common_name_nl": "",
                "source": "manual_needed",
                "reviewer": "",
                "notes": "no iNat resolution; manual entry required",
            })
        elif proposed or t["missing_langs"]:
            # Merge existing + proposed
            fr = (t["existing_fr"] or [proposed.get("fr", "")])[0] if t["existing_fr"] \
                else proposed.get("fr", "")
            en_val = (t["existing_en"] or [proposed.get("en", "")])[0] if t["existing_en"] \
                else proposed.get("en", "")
            nl = (t["existing_nl"] or [proposed.get("nl", "")])[0] if t["existing_nl"] \
                else proposed.get("nl", "")
            rows.append({
                "scientific_name": t["scientific_name"],
                "source_taxon_id": t.get("inat_id", ""),
                "canonical_taxon_id": t["canonical_taxon_id"],
                "referenced_taxon_id": "",
                "common_name_fr": fr,
                "common_name_en": en_val,
                "common_name_nl": nl,
                "source": t.get("name_source", "unknown"),
                "reviewer": "",
                "notes": "",
            })

    if not rows:
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def write_markdown_report(evidence: dict[str, Any], output_path: Path) -> None:
    run_date = evidence["run_date"][:10]
    decision = evidence["decision"]

    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        f"last_reviewed: {run_date}",
        "source_of_truth: docs/audits/taxon-localized-names-gap-audit-sprint12.md",
        "scope: audit",
        "---",
        "",
        "# Taxon Localized Names Gap Audit — Sprint 12",
        "",
        "## Purpose",
        "",
        "Identify missing French, Dutch, and English localized names for target taxa "
        "and distractor candidate taxa. Determine which gaps can be resolved from "
        "iNaturalist, and which require manual CSV entry.",
        "",
        "## Context",
        "",
        "Sprint 11 showed 43 candidate taxa missing French names, "
        "resulting in 0/50 targets ready for the FR distractor gate. "
        "Phase C resolves this gap.",
        "",
        "---",
        "",
        "## Gap Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Target taxa | {evidence['targets_total']} |",
        f"| Targets missing FR | {evidence['targets_missing_fr']} |",
        f"| Targets missing NL | {evidence['targets_missing_nl']} |",
        f"| Targets missing EN | {evidence['targets_missing_en']} |",
        f"| Candidate taxa | {evidence['candidate_taxa_total']} |",
        f"| Candidates missing FR | {evidence['candidate_taxa_missing_fr']} |",
        f"| Candidates missing NL | {evidence['candidate_taxa_missing_nl']} |",
        f"| Candidates missing EN | {evidence['candidate_taxa_missing_en']} |",
        f"| FR resolvable from iNat | {evidence['fr_resolvable_from_inat']} |",
        f"| NL resolvable from iNat | {evidence['nl_resolvable_from_inat']} |",
        f"| Names requiring manual entry | {evidence['names_requiring_manual']} |",
        f"| Candidates FR-usable now | {evidence['candidates_fr_usable_now']} |",
        f"| Candidates FR-usable after applying | {evidence['candidates_fr_usable_projected']} |",
        "",
        "---",
        "",
        "## Name Sources",
        "",
        "Priority order:",
        "",
        "1. Existing `common_names_by_language` in canonical records",
        "2. iNaturalist `GET /v1/taxa/{id}?all_names=true` → `names[]` with locale/is_valid",
        "3. Manual CSV: `data/manual/taxon_common_names_i18n_sprint12.csv`",
        "",
        "---",
        "",
        "## Next Step Recommendation",
        "",
        f"**Decision: `{decision}`**",
        "",
        evidence.get("decision_note", ""),
        "",
        "---",
        "",
        "## Doctrine",
        "",
        "- iNat names are source-side hints; they do not define canonical identity.",
        "- `accepted_scientific_name` is never derived from vernacular names.",
        "- Existing names are never silently overwritten; conflicts are reported.",
        "- `similar_taxa` and `similar_taxon_ids` are not modified by this phase.",
    ]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_audit(
    snapshot_id: str,
    normalized_path: Path,
    candidates_path: Path,
    enriched_dir: Path,
    *,
    fetch_live: bool = False,
    write_csv: bool = False,
    csv_path: Path | None = None,
) -> dict[str, Any]:
    data = json.loads(normalized_path.read_text(encoding="utf-8"))
    normalized_taxa: list[dict[str, Any]] = data.get("canonical_taxa", [])

    if candidates_path.exists():
        cdata = json.loads(candidates_path.read_text(encoding="utf-8"))
        candidate_relationships: list[dict[str, Any]] = cdata.get("relationships", [])
    else:
        candidate_relationships = []

    gap = analyze_names_gap(
        normalized_taxa,
        candidate_relationships,
        enriched_dir=enriched_dir,
        snapshot_id=snapshot_id,
        fetch_live=fetch_live,
    )

    evidence = build_evidence(
        snapshot_id=snapshot_id,
        normalized_taxa=normalized_taxa,
        candidate_relationships=candidate_relationships,
        gap_analysis=gap,
        fetch_live=fetch_live,
    )

    if write_csv and csv_path is not None:
        evidence["csv_rows_written"] = write_proposed_csv(evidence, csv_path)
        evidence["csv_path"] = str(csv_path)

    return evidence


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Sprint 12 Phase C Task 1 — Audit missing localized names"
    )
    p.add_argument("--snapshot-id", default=DEFAULT_SNAPSHOT_ID)
    p.add_argument("--normalized-path", type=Path, default=DEFAULT_NORMALIZED_PATH)
    p.add_argument("--candidates-path", type=Path, default=DEFAULT_CANDIDATES_PATH)
    p.add_argument("--enriched-dir", type=Path, default=DEFAULT_ENRICHED_DIR)
    p.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    p.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    p.add_argument("--write-csv", action="store_true", default=False)
    p.add_argument("--csv-path", type=Path, default=DEFAULT_MANUAL_CSV)
    p.add_argument(
        "--fetch-inat",
        action="store_true",
        default=False,
        help="Fetch iNat all_names live (rate-limited); writes cache.",
    )
    args = p.parse_args(argv)

    if not args.normalized_path.exists():
        print(f"ERROR: normalized path not found: {args.normalized_path}", file=sys.stderr)
        return 1

    evidence = run_audit(
        snapshot_id=args.snapshot_id,
        normalized_path=args.normalized_path,
        candidates_path=args.candidates_path,
        enriched_dir=args.enriched_dir,
        fetch_live=args.fetch_inat,
        write_csv=args.write_csv,
        csv_path=args.csv_path,
    )

    # Write evidence JSON (strip heavy per_taxon proposed payload if large)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(f"Audit evidence written: {args.output_json}")

    write_markdown_report(evidence, args.output_md)
    print(f"Markdown report written: {args.output_md}")

    if args.write_csv:
        print(f"CSV written: {args.csv_path} ({evidence.get('csv_rows_written', 0)} rows)")

    print()
    print("=== Summary ===")
    print(f"  Targets missing FR        : {evidence['targets_missing_fr']}")
    print(f"  Candidates missing FR      : {evidence['candidate_taxa_missing_fr']}")
    print(f"  FR resolvable from iNat    : {evidence['fr_resolvable_from_inat']}")
    print(f"  Names requiring manual     : {evidence['names_requiring_manual']}")
    print(f"  Projected FR-usable cands  : {evidence['candidates_fr_usable_projected']}")
    print(f"  Decision                   : {evidence['decision']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
