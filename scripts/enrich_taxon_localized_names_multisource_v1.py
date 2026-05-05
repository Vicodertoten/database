from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

RUN_DATE = "2026-05-05"
PHASE = "Sprint 14B.2"

REPO_ROOT = Path(__file__).resolve().parent.parent

POLICY_DOC = "docs/foundation/localized-name-source-policy-v1.md"
OUTPUT_JSON = REPO_ROOT / "docs" / "audits" / "evidence" / "taxon_localized_names_multisource_sprint14_dry_run.json"
OUTPUT_MD = REPO_ROOT / "docs" / "audits" / "taxon-localized-names-multisource-sprint14-dry-run.md"
OUTPUT_REVIEW_CSV = REPO_ROOT / "data" / "manual" / "taxon_localized_name_multisource_review_queue_sprint14.csv"
OUTPUT_PATCH_CSV = REPO_ROOT / "data" / "manual" / "taxon_localized_name_source_attested_patches_sprint14.csv"

CANONICAL_PATCHED = REPO_ROOT / "data" / "enriched" / "taxon_localized_names_v1" / "canonical_taxa_patched.json"
REFERENCED_PATCHED = REPO_ROOT / "data" / "enriched" / "taxon_localized_names_v1" / "referenced_taxa_patched.json"
PROJECTED_REL = REPO_ROOT / "docs" / "audits" / "evidence" / "distractor_relationships_v1_projected_sprint13.json"
READINESS = REPO_ROOT / "docs" / "audits" / "evidence" / "distractor_readiness_v1_sprint13.json"
SHELL_PLAN = REPO_ROOT / "docs" / "audits" / "evidence" / "referenced_taxon_shell_apply_plan_sprint13.json"
PRIORITY_CSV = REPO_ROOT / "data" / "manual" / "taxon_localized_name_patches_sprint13.csv"

INAT_ALL_NAMES_DIR = REPO_ROOT / "data" / "enriched" / "palier1-be-birds-50taxa-run003-v11-baseline" / "all_names"

LANGS = ("fr", "en", "nl")
SOURCE_PRIORITY = {
    "manual_or_curated_existing": 0,
    "inaturalist": 1,
    "wikidata": 2,
    "gbif": 3,
}

PLACEHOLDER_HINTS = ("placeholder", "provisional", "seed_fr_then_human_review")
LATIN_BINOMIAL_RE = re.compile(r"^[A-Z][a-z]+\s+[a-z][a-z-]+(?:\s+[a-z][a-z-]+)?$")


def _load_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_whitespace(value: str) -> str:
    return " ".join(value.strip().split())


def normalize_compare_text(value: str) -> str:
    text = normalize_whitespace(value).casefold()
    return re.sub(r"\s+", " ", text)


def is_empty_name(value: str) -> bool:
    return not normalize_whitespace(value)


def looks_like_latin_binomial(value: str) -> bool:
    return bool(LATIN_BINOMIAL_RE.match(normalize_whitespace(value)))


def is_scientific_name_as_common_name(value: str, scientific_name: str) -> bool:
    return normalize_compare_text(value) == normalize_compare_text(scientific_name)


def is_internal_placeholder(value: str, notes: str = "") -> bool:
    nv = normalize_compare_text(value)
    nn = normalize_compare_text(notes)
    if any(h in nv for h in PLACEHOLDER_HINTS):
        return True
    if any(h in nn for h in PLACEHOLDER_HINTS):
        return True
    return False


def names_equivalent(a: str, b: str) -> bool:
    return normalize_compare_text(a) == normalize_compare_text(b)


def _first_name(mapping: dict[str, Any], lang: str) -> str:
    values = mapping.get(lang, []) if isinstance(mapping, dict) else []
    if not isinstance(values, list):
        return ""
    for v in values:
        if isinstance(v, str) and normalize_whitespace(v):
            return normalize_whitespace(v)
    return ""


def _build_taxa() -> dict[tuple[str, str], dict[str, Any]]:
    taxa: dict[tuple[str, str], dict[str, Any]] = {}

    canonical = _load_json(CANONICAL_PATCHED)
    for item in canonical.get("canonical_taxa", []):
        cid = str(item.get("canonical_taxon_id", "")).strip()
        if not cid:
            continue
        taxa[("canonical_taxon", cid)] = {
            "taxon_kind": "canonical_taxon",
            "taxon_id": cid,
            "source_taxon_id": "",
            "scientific_name": str(item.get("scientific_name", "")).strip(),
            "existing_names": item.get("common_names_i18n", {}) or {},
            "from": {"canonical_patched"},
        }

    referenced = _load_json(REFERENCED_PATCHED)
    for item in referenced.get("referenced_taxa", []):
        rid = str(item.get("referenced_taxon_id", "")).strip()
        if not rid:
            continue
        taxa[("referenced_taxon", rid)] = {
            "taxon_kind": "referenced_taxon",
            "taxon_id": rid,
            "source_taxon_id": str(item.get("source_taxon_id", "")).strip(),
            "scientific_name": str(item.get("scientific_name", "")).strip(),
            "existing_names": item.get("common_names_i18n", {}) or {},
            "from": {"referenced_patched"},
        }

    shell = _load_json(SHELL_PLAN)
    for row in shell.get("apply_records", []):
        rid = str(row.get("proposed_referenced_taxon_id", "")).strip()
        if not rid:
            continue
        key = ("referenced_taxon", rid)
        if key not in taxa:
            taxa[key] = {
                "taxon_kind": "referenced_taxon",
                "taxon_id": rid,
                "source_taxon_id": str(row.get("source_taxon_id", "")).strip(),
                "scientific_name": str(row.get("scientific_name", "")).strip(),
                "existing_names": row.get("common_names_i18n", {}) or {},
                "from": {"shell_plan"},
            }
        else:
            taxa[key]["from"].add("shell_plan")

    projected = _load_json(PROJECTED_REL)
    for row in projected.get("projected_records", []):
        rtype = str(row.get("candidate_taxon_ref_type", "")).strip()
        rid = str(row.get("candidate_taxon_ref_id", "")).strip()
        if rtype not in {"canonical_taxon", "referenced_taxon"} or not rid:
            continue
        key = (rtype, rid)
        if key in taxa:
            taxa[key]["from"].add("projected_relationships")

    return taxa


def _collect_inat_candidates() -> dict[tuple[str, str], dict[str, str]]:
    by_source_id: dict[str, dict[str, str]] = {}
    by_scientific: dict[str, dict[str, str]] = {}
    if not INAT_ALL_NAMES_DIR.exists():
        return {}

    for path in sorted(INAT_ALL_NAMES_DIR.glob("*.json")):
        payload = _load_json(path)
        for result in payload.get("results", []):
            sid = str(result.get("id", "")).strip()
            sci = normalize_compare_text(str(result.get("name", "")))
            langs: dict[str, str] = {}
            for n in result.get("names", []):
                if not isinstance(n, dict):
                    continue
                locale = str(n.get("locale", "")).strip().lower()
                name = normalize_whitespace(str(n.get("name", "")))
                if locale in LANGS and name and locale not in langs:
                    langs[locale] = name
            if sid and langs:
                by_source_id.setdefault(sid, {}).update({k: v for k, v in langs.items() if k not in by_source_id[sid]})
            if sci and langs:
                by_scientific.setdefault(sci, {}).update({k: v for k, v in langs.items() if k not in by_scientific[sci]})

    out: dict[tuple[str, str], dict[str, str]] = {}
    for sid, langs in by_source_id.items():
        out[("source_taxon_id", sid)] = langs
    for sci, langs in by_scientific.items():
        out[("scientific_name", sci)] = langs
    return out


def _priority_csv_notes() -> dict[str, str]:
    notes: dict[str, str] = {}
    if not PRIORITY_CSV.exists():
        return notes
    with PRIORITY_CSV.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rid = str(row.get("candidate_taxon_ref_id", "")).strip()
            n = str(row.get("notes", "")).strip()
            if rid and n:
                notes[rid] = n
    return notes


def build_multisource_dry_run() -> dict[str, Any]:
    taxa = _build_taxa()
    readiness = _load_json(READINESS)
    ready_targets = {
        str(row.get("target_canonical_taxon_id", "")).strip()
        for row in readiness.get("per_target_readiness", [])
        if str(row.get("readiness_status", "")).strip() == "ready_for_first_corpus_distractor_gate"
    }

    relationship_by_candidate: Counter[str] = Counter()
    target_by_candidate: dict[str, set[str]] = defaultdict(set)
    projected = _load_json(PROJECTED_REL)
    for row in projected.get("projected_records", []):
        cid = str(row.get("candidate_taxon_ref_id", "")).strip()
        tid = str(row.get("target_canonical_taxon_id", "")).strip()
        if cid:
            relationship_by_candidate[cid] += 1
            if tid:
                target_by_candidate[cid].add(tid)

    inat_candidates = _collect_inat_candidates()
    provider_status = {
        "inaturalist": "available_local_artifact" if inat_candidates else "not_run",
        "wikidata": "not_configured",
        "gbif": "not_configured",
    }

    priority_notes = _priority_csv_notes()

    selected: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    patch_rows: list[dict[str, Any]] = []
    source_priority_distribution: Counter[str] = Counter()
    candidate_names_by_language: Counter[str] = Counter()
    selected_names_by_language: Counter[str] = Counter()
    displayable_source_attested_count_by_language: Counter[str] = Counter()
    displayable_curated_count_by_language: Counter[str] = Counter()
    needs_review_conflict_count_by_language: Counter[str] = Counter()
    not_displayable_count_by_language: Counter[str] = Counter()

    for taxon in sorted(taxa.values(), key=lambda t: (t["taxon_kind"], t["taxon_id"])):
        sci = taxon["scientific_name"]
        ex = taxon.get("existing_names", {})
        sid = taxon.get("source_taxon_id", "")
        inat_by_sid = inat_candidates.get(("source_taxon_id", sid), {}) if sid else {}
        inat_by_sci = inat_candidates.get(("scientific_name", normalize_compare_text(sci)), {}) if sci else {}

        for lang in LANGS:
            existing_name = _first_name(ex, lang)
            existing_placeholder = is_internal_placeholder(existing_name, priority_notes.get(taxon["taxon_id"], ""))
            existing_scifallback = bool(existing_name) and (
                is_scientific_name_as_common_name(existing_name, sci) or looks_like_latin_binomial(existing_name)
            )

            candidates = []
            if existing_name:
                candidates.append(("manual_or_curated_existing", existing_name))
            inat_name = inat_by_sid.get(lang) or inat_by_sci.get(lang, "")
            if inat_name:
                candidates.append(("inaturalist", inat_name))

            for src, nm in candidates:
                candidate_names_by_language[lang] += 1

            selected_name = ""
            selected_source = ""
            display_status = "not_displayable_missing"
            recommendation = "not_for_corpus_display_missing"
            conflict_status = "none"
            alternatives: list[str] = []

            if existing_name and not existing_placeholder and not (lang == "fr" and existing_scifallback):
                selected_name = existing_name
                selected_source = "manual_or_curated_existing"
                display_status = "displayable_curated"
                recommendation = "keep_existing_curated"
            else:
                if inat_name:
                    selected_name = inat_name
                    selected_source = "inaturalist"
                    if lang == "fr" and (
                        is_scientific_name_as_common_name(inat_name, sci)
                        or looks_like_latin_binomial(inat_name)
                    ):
                        display_status = "not_displayable_scientific_fallback"
                        recommendation = "not_for_corpus_display_scientific_fallback"
                    elif is_internal_placeholder(inat_name):
                        display_status = "not_displayable_placeholder"
                        recommendation = "not_for_corpus_display_placeholder"
                    else:
                        display_status = "displayable_source_attested"
                        recommendation = "apply_source_attested_name"
                elif existing_name and existing_placeholder:
                    selected_name = existing_name
                    selected_source = "manual_or_curated_existing"
                    display_status = "not_displayable_placeholder"
                    recommendation = "not_for_corpus_display_placeholder"
                elif existing_name and lang == "fr" and existing_scifallback:
                    selected_name = existing_name
                    selected_source = "manual_or_curated_existing"
                    display_status = "not_displayable_scientific_fallback"
                    recommendation = "not_for_corpus_display_scientific_fallback"

            if existing_name and selected_source == "inaturalist" and not names_equivalent(existing_name, selected_name):
                conflict_status = "curated_conflict"
                display_status = "needs_review_conflict"
                recommendation = "needs_human_review_conflict"
                needs_review_conflict_count_by_language[lang] += 1
                alternatives.append(f"manual_or_curated_existing:{existing_name}")

            if selected_source:
                source_priority_distribution[selected_source] += 1
            if selected_name:
                selected_names_by_language[lang] += 1

            if display_status == "displayable_source_attested":
                displayable_source_attested_count_by_language[lang] += 1
            elif display_status == "displayable_curated":
                displayable_curated_count_by_language[lang] += 1
            elif display_status.startswith("not_displayable_"):
                not_displayable_count_by_language[lang] += 1

            affected_targets = target_by_candidate.get(taxon["taxon_id"], set())
            affected_ready = len(affected_targets & ready_targets)
            projected_unlock_value = affected_ready if display_status in {"displayable_curated", "displayable_source_attested"} else 0

            row = {
                "priority": "P1" if affected_ready else "P3",
                "taxon_id": taxon["taxon_id"],
                "taxon_kind": taxon["taxon_kind"],
                "scientific_name": sci,
                "language": lang,
                "existing_name": existing_name,
                "selected_candidate_name": selected_name,
                "selected_source": selected_source,
                "selected_source_priority": SOURCE_PRIORITY.get(selected_source, 4),
                "display_status": display_status,
                "recommendation": recommendation,
                "conflict_status": conflict_status,
                "alternatives": " | ".join(alternatives),
                "affected_target_count": len(affected_targets),
                "affected_ready_target_count": affected_ready,
                "relationship_occurrence_count": relationship_by_candidate.get(taxon["taxon_id"], 0),
                "projected_unlock_value": projected_unlock_value,
                "reviewer": "",
                "reviewed_name": "",
                "review_confidence": "",
                "review_source": "",
                "review_notes": "",
                "apply_status": "pending",
            }
            review_rows.append(row)

            if recommendation in {"apply_source_attested_name", "keep_existing_curated"} and selected_name:
                patch_rows.append(
                    {
                        "taxon_id": taxon["taxon_id"],
                        "taxon_kind": taxon["taxon_kind"],
                        "scientific_name": sci,
                        "language": lang,
                        "common_name": selected_name,
                        "source": selected_source,
                        "source_priority": SOURCE_PRIORITY.get(selected_source, 4),
                        "confidence": "source_attested" if selected_source != "manual_or_curated_existing" else "high",
                        "display_status": display_status,
                        "reviewer": "system/source_policy" if selected_source != "manual_or_curated_existing" else "",
                        "notes": "source-attested by localized-name-source-policy-v1",
                        "apply_status": "ready",
                    }
                )

            selected.append(row)

    fr_displayable = {
        r["taxon_id"]
        for r in selected
        if r["language"] == "fr" and r["display_status"] in {"displayable_curated", "displayable_source_attested"}
    }
    projected_safe_ready = len(
        {
            tid
            for tid in ready_targets
            if any(tid in target_by_candidate.get(cid, set()) for cid in fr_displayable)
        }
    )

    evidence = {
        "run_date": RUN_DATE,
        "phase": PHASE,
        "policy_doc": POLICY_DOC,
        "providers": ["inaturalist", "wikidata", "gbif"],
        "provider_status": provider_status,
        "taxa_considered_count": len(taxa),
        "taxa_considered_by_kind": dict(Counter(t["taxon_kind"] for t in taxa.values())),
        "candidate_names_by_language": dict(candidate_names_by_language),
        "selected_names_by_language": dict(selected_names_by_language),
        "displayable_source_attested_count_by_language": dict(displayable_source_attested_count_by_language),
        "displayable_curated_count_by_language": dict(displayable_curated_count_by_language),
        "needs_review_conflict_count_by_language": dict(needs_review_conflict_count_by_language),
        "not_displayable_count_by_language": dict(not_displayable_count_by_language),
        "conflict_count": sum(needs_review_conflict_count_by_language.values()),
        "source_priority_distribution": dict(source_priority_distribution),
        "projected_fr_safe_label_gain": sum(
            1
            for r in selected
            if r["language"] == "fr" and r["recommendation"] == "apply_source_attested_name"
        ),
        "current_safe_ready_target_count_after_guard": 10,
        "projected_safe_ready_target_count_after_source_attested_names": projected_safe_ready,
        "first_corpus_minimum_target_count": 30,
        "projected_decision": (
            "READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS"
            if projected_safe_ready >= 30
            else "BLOCKED_NEEDS_NAME_SOURCE_ENRICHMENT"
        ),
        "selected_high_value_name_candidates": sorted(
            [
                {
                    "taxon_id": r["taxon_id"],
                    "taxon_kind": r["taxon_kind"],
                    "scientific_name": r["scientific_name"],
                    "language": r["language"],
                    "selected_candidate_name": r["selected_candidate_name"],
                    "selected_source": r["selected_source"],
                    "display_status": r["display_status"],
                    "affected_ready_target_count": r["affected_ready_target_count"],
                    "projected_unlock_value": r["projected_unlock_value"],
                }
                for r in selected
                if r["language"] == "fr" and r["projected_unlock_value"] > 0
            ],
            key=lambda x: (-x["projected_unlock_value"], x["taxon_id"]),
        )[:50],
        "non_actions": [
            "No DistractorRelationship persistence",
            "No ReferencedTaxon shell creation",
            "No PMP/media score changes",
            "No runtime app code",
            "No invented names",
        ],
    }

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    with OUTPUT_REVIEW_CSV.open("w", encoding="utf-8", newline="") as f:
        fields = [
            "priority",
            "taxon_id",
            "taxon_kind",
            "scientific_name",
            "language",
            "existing_name",
            "selected_candidate_name",
            "selected_source",
            "selected_source_priority",
            "display_status",
            "recommendation",
            "conflict_status",
            "alternatives",
            "affected_target_count",
            "affected_ready_target_count",
            "relationship_occurrence_count",
            "projected_unlock_value",
            "reviewer",
            "reviewed_name",
            "review_confidence",
            "review_source",
            "review_notes",
            "apply_status",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(review_rows)

    with OUTPUT_PATCH_CSV.open("w", encoding="utf-8", newline="") as f:
        fields = [
            "taxon_id",
            "taxon_kind",
            "scientific_name",
            "language",
            "common_name",
            "source",
            "source_priority",
            "confidence",
            "display_status",
            "reviewer",
            "notes",
            "apply_status",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(patch_rows)

    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        "last_reviewed: 2026-05-05",
        "source_of_truth: docs/audits/taxon-localized-names-multisource-sprint14-dry-run.md",
        "scope: sprint14b_localized_names",
        "---",
        "",
        "# Taxon Localized Names Multisource Sprint 14 Dry Run",
        "",
        "Localized names remain the primary Sprint 14B blocker because runtime-safe FR labels are below first-corpus minimum.",
        "Source-attested names are acceptable for MVP display when traceable and policy-selected, even if not fully human-reviewed.",
        "",
        f"- policy: `{POLICY_DOC}`",
        f"- sources used: inaturalist(local artifacts), curated/manual existing",
        f"- unavailable sources: wikidata={provider_status['wikidata']}, gbif={provider_status['gbif']}",
        "- source preference: curated/manual > iNaturalist > Wikidata > GBIF > missing",
        "- this is not human-reviewed perfection; it is deterministic, attested, and conflict-aware MVP safety",
        f"- projected FR displayable gain: {evidence['projected_fr_safe_label_gain']}",
        f"- projected safe ready targets: {evidence['projected_safe_ready_target_count_after_source_attested_names']} / 30",
        f"- projected decision: {evidence['projected_decision']}",
        "",
        "## Remaining Warnings",
        "",
        "- Non-human-reviewed source-attested names remain warning-level and should be sampled in later QA.",
        "- Wikidata/GBIF local artifacts were unavailable in this run.",
        "",
        "## Non-Actions",
        "",
        "- No DistractorRelationship persistence",
        "- No ReferencedTaxon shell creation",
        "- No runtime app changes",
        "- No invented labels",
    ]
    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return evidence


def main() -> None:
    evidence = build_multisource_dry_run()
    print(f"Decision: {evidence['projected_decision']}")
    print(
        "Projected safe-ready targets after source-attested policy: "
        f"{evidence['projected_safe_ready_target_count_after_source_attested_names']}"
    )


if __name__ == "__main__":
    main()
