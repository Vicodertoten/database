from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

RUN_DATE = "2026-05-05"
PHASE = "Sprint 14B"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_JSON = REPO_ROOT / "docs" / "audits" / "evidence" / "database_integrity_runtime_handoff_audit.json"
DEFAULT_OUTPUT_MD = REPO_ROOT / "docs" / "audits" / "database-integrity-runtime-handoff-audit.md"
POLICY_DOC = "docs/foundation/localized-name-source-policy-v1.md"

PROJECTED_REL = REPO_ROOT / "docs" / "audits" / "evidence" / "distractor_relationships_v1_projected_sprint13.json"
READINESS = REPO_ROOT / "docs" / "audits" / "evidence" / "distractor_readiness_v1_sprint13.json"
CANONICAL_PATCHED = REPO_ROOT / "data" / "enriched" / "taxon_localized_names_v1" / "canonical_taxa_patched.json"
REFERENCED_PATCHED = REPO_ROOT / "data" / "enriched" / "taxon_localized_names_v1" / "referenced_taxa_patched.json"
MULTISOURCE_EVIDENCE = REPO_ROOT / "docs" / "audits" / "evidence" / "taxon_localized_names_multisource_sprint14_dry_run.json"
SOURCE_ATTESTED_CSV = REPO_ROOT / "data" / "manual" / "taxon_localized_name_source_attested_patches_sprint14.csv"

LATIN_BINOMIAL_RE = re.compile(r"^[A-Z][a-z]+\s+[a-z][a-z-]+(?:\s+[a-z][a-z-]+)?$")


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    value: Any
    detail: str


def _load_json(path: Path) -> dict[str, Any] | list[Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def looks_like_latin_binomial(name: str) -> bool:
    return bool(LATIN_BINOMIAL_RE.match(name.strip()))


def _norm(s: str) -> str:
    return " ".join(s.strip().split()).casefold()


def _is_scifallback(name: str, sci: str) -> bool:
    if not name.strip():
        return False
    return _norm(name) == _norm(sci) or looks_like_latin_binomial(name.strip())


def _first_name(name_map: dict[str, Any], lang: str) -> str:
    values = name_map.get(lang, []) if isinstance(name_map, dict) else []
    if not isinstance(values, list):
        return ""
    for v in values:
        if isinstance(v, str) and v.strip():
            return " ".join(v.strip().split())
    return ""


def classify_decision(
    *,
    hard_integrity: bool,
    source_attested_policy_enabled: bool,
    runtime_facing_unsafe_labels: bool,
    safe_ready_target_count_after_source_attested_policy: int,
    first_corpus_minimum_target_count: int,
    needs_review_conflict_count: int,
    not_displayable_missing_count: int,
) -> str:
    if hard_integrity:
        return "BLOCKED_NEEDS_DISTRACTOR_INTEGRITY_FIXES"
    if not source_attested_policy_enabled:
        return "BLOCKED_NEEDS_NAME_POLICY"
    if runtime_facing_unsafe_labels:
        return "BLOCKED_NEEDS_PLACEHOLDER_EXCLUSION"
    if safe_ready_target_count_after_source_attested_policy >= first_corpus_minimum_target_count:
        return "READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS"
    if needs_review_conflict_count > 0:
        return "BLOCKED_NEEDS_NAME_CONFLICT_REVIEW"
    if not_displayable_missing_count > 0:
        return "BLOCKED_NEEDS_NAME_SOURCE_ENRICHMENT"
    return "BLOCKED_NEEDS_NAME_SOURCE_ENRICHMENT"


def next_phase_for_decision(decision: str) -> str:
    if decision == "READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS":
        return "14C Robustness and regression tests"
    if decision == "BLOCKED_NEEDS_NAME_CONFLICT_REVIEW":
        return "Resolve localized-name conflicts then rerun Sprint 14B"
    if decision == "BLOCKED_NEEDS_NAME_SOURCE_ENRICHMENT":
        return "Add missing source-attested localized names then rerun Sprint 14B"
    if decision == "BLOCKED_NEEDS_NAME_POLICY":
        return "Document and enable localized-name source policy then rerun Sprint 14B"
    if decision == "BLOCKED_NEEDS_PLACEHOLDER_EXCLUSION":
        return "Remove runtime-facing placeholder/scientific-fallback labels then rerun Sprint 14B"
    return "Fix integrity blockers then rerun Sprint 14B"


def _load_status_map() -> tuple[dict[tuple[str, str, str], str], dict[tuple[str, str], str]]:
    source_rows = _read_csv(SOURCE_ATTESTED_CSV)
    source_attested = {
        (str(r.get("taxon_kind", "")).strip(), str(r.get("taxon_id", "")).strip(), str(r.get("language", "")).strip()):
        str(r.get("common_name", "")).strip()
        for r in source_rows
        if str(r.get("apply_status", "")).strip().lower() == "ready"
        and str(r.get("confidence", "")).strip().lower() == "source_attested"
    }

    statuses: dict[tuple[str, str, str], str] = {}
    scientific: dict[tuple[str, str], str] = {}

    canonical = _load_json(CANONICAL_PATCHED)
    for row in canonical.get("canonical_taxa", []):
        tid = str(row.get("canonical_taxon_id", "")).strip()
        if not tid:
            continue
        sci = str(row.get("scientific_name", "")).strip()
        scientific[("canonical_taxon", tid)] = sci
        names = row.get("common_names_i18n", {}) or {}
        for lang in ("fr", "en", "nl"):
            nm = _first_name(names, lang)
            if not nm:
                statuses[("canonical_taxon", tid, lang)] = "not_displayable_missing"
                continue
            if lang == "fr" and _is_scifallback(nm, sci):
                statuses[("canonical_taxon", tid, lang)] = "not_displayable_scientific_fallback"
                continue
            if ("canonical_taxon", tid, lang) in source_attested and _norm(source_attested[("canonical_taxon", tid, lang)]) == _norm(nm):
                statuses[("canonical_taxon", tid, lang)] = "displayable_source_attested"
            else:
                statuses[("canonical_taxon", tid, lang)] = "displayable_curated"

    referenced = _load_json(REFERENCED_PATCHED)
    for row in referenced.get("referenced_taxa", []):
        tid = str(row.get("referenced_taxon_id", "")).strip()
        if not tid:
            continue
        sci = str(row.get("scientific_name", "")).strip()
        scientific[("referenced_taxon", tid)] = sci
        names = row.get("common_names_i18n", {}) or {}
        for lang in ("fr", "en", "nl"):
            nm = _first_name(names, lang)
            if not nm:
                statuses[("referenced_taxon", tid, lang)] = "not_displayable_missing"
                continue
            if lang == "fr" and _is_scifallback(nm, sci):
                statuses[("referenced_taxon", tid, lang)] = "not_displayable_scientific_fallback"
                continue
            if ("referenced_taxon", tid, lang) in source_attested and _norm(source_attested[("referenced_taxon", tid, lang)]) == _norm(nm):
                statuses[("referenced_taxon", tid, lang)] = "displayable_source_attested"
            else:
                statuses[("referenced_taxon", tid, lang)] = "displayable_curated"

    return statuses, scientific


def run_audit(output_json: Path = DEFAULT_OUTPUT_JSON, output_md: Path = DEFAULT_OUTPUT_MD) -> dict[str, Any]:
    projected = _load_json(PROJECTED_REL)
    readiness = _load_json(READINESS)
    multisource = _load_json(MULTISOURCE_EVIDENCE) if MULTISOURCE_EVIDENCE.exists() else {}
    status_map, _scientific = _load_status_map()

    per_target_candidates: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in projected.get("projected_records", []):
        if str(row.get("status", "")).strip() != "candidate":
            continue
        tid = str(row.get("target_canonical_taxon_id", "")).strip()
        ctype = str(row.get("candidate_taxon_ref_type", "")).strip()
        cid = str(row.get("candidate_taxon_ref_id", "")).strip()
        if tid and ctype in {"canonical_taxon", "referenced_taxon"} and cid:
            per_target_candidates[tid].append((ctype, cid))

    ready_targets = {
        str(r.get("target_canonical_taxon_id", "")).strip()
        for r in readiness.get("per_target_readiness", [])
        if str(r.get("readiness_status", "")).strip() == "ready_for_first_corpus_distractor_gate"
    }

    displayable_source_attested_label_count = 0
    displayable_curated_label_count = 0
    not_displayable_missing_count = 0
    not_displayable_placeholder_count = 0
    not_displayable_scientific_fallback_count = 0
    needs_review_conflict_count = int(multisource.get("conflict_count", 0))

    for (kind, tid, lang), status in status_map.items():
        if lang != "fr":
            continue
        if status == "displayable_source_attested":
            displayable_source_attested_label_count += 1
        elif status == "displayable_curated":
            displayable_curated_label_count += 1
        elif status == "not_displayable_missing":
            not_displayable_missing_count += 1
        elif status == "not_displayable_placeholder":
            not_displayable_placeholder_count += 1
        elif status == "not_displayable_scientific_fallback":
            not_displayable_scientific_fallback_count += 1

    safe_ready_targets = 0
    runtime_facing_unsafe_labels = False
    for tid in ready_targets:
        displayable_fr_candidates = 0
        for ctype, cid in per_target_candidates.get(tid, []):
            st = status_map.get((ctype, cid, "fr"), "not_displayable_missing")
            if st in {"displayable_curated", "displayable_source_attested"}:
                displayable_fr_candidates += 1
            elif st in {
                "not_displayable_placeholder",
                "not_displayable_scientific_fallback",
                "needs_review_conflict",
            }:
                runtime_facing_unsafe_labels = True
        if displayable_fr_candidates >= 3:
            safe_ready_targets += 1

    first_corpus_minimum_target_count = 30
    source_attested_display_policy_enabled = Path(REPO_ROOT / POLICY_DOC).exists()

    decision = classify_decision(
        hard_integrity=False,
        source_attested_policy_enabled=source_attested_display_policy_enabled,
        runtime_facing_unsafe_labels=runtime_facing_unsafe_labels,
        safe_ready_target_count_after_source_attested_policy=safe_ready_targets,
        first_corpus_minimum_target_count=first_corpus_minimum_target_count,
        needs_review_conflict_count=needs_review_conflict_count,
        not_displayable_missing_count=not_displayable_missing_count,
    )

    warnings = [
        "Source-attested names not human-reviewed remain warning-level for MVP display.",
        "Runtime must display only displayable_curated or displayable_source_attested.",
        "Runtime must not invent/fetch localized names.",
    ]

    payload = {
        "run_date": RUN_DATE,
        "phase": PHASE,
        "decision": decision,
        "localized_name_source_policy": POLICY_DOC,
        "source_attested_display_policy_enabled": source_attested_display_policy_enabled,
        "displayable_source_attested_label_count": displayable_source_attested_label_count,
        "displayable_curated_label_count": displayable_curated_label_count,
        "non_human_reviewed_source_attested_label_count": displayable_source_attested_label_count,
        "not_displayable_missing_count": not_displayable_missing_count,
        "not_displayable_placeholder_count": not_displayable_placeholder_count,
        "not_displayable_scientific_fallback_count": not_displayable_scientific_fallback_count,
        "needs_review_conflict_count": needs_review_conflict_count,
        "safe_ready_target_count_after_source_attested_policy": safe_ready_targets,
        "first_corpus_minimum_target_count": first_corpus_minimum_target_count,
        "first_corpus_target_count_after_source_policy_status": (
            "pass" if safe_ready_targets >= first_corpus_minimum_target_count else "fail"
        ),
        "runtime_display_name_policy_warnings": warnings,
        "non_actions": [
            "PERSIST_DISTRACTOR_RELATIONSHIPS_V1 remains false",
            "DATABASE_PHASE_CLOSED remains false",
            "No runtime app code created",
            "No invented names",
        ],
        "recommended_next_phase": next_phase_for_decision(decision),
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        "last_reviewed: 2026-05-05",
        "source_of_truth: docs/audits/database-integrity-runtime-handoff-audit.md",
        "scope: sprint14b_data_integrity_gate",
        "---",
        "",
        "# Database Integrity Runtime Handoff Audit (Sprint 14B)",
        "",
        f"- decision: {decision}",
        f"- source_attested_display_policy_enabled: {str(source_attested_display_policy_enabled).lower()}",
        f"- safe_ready_target_count_after_source_attested_policy: {safe_ready_targets}",
        f"- first_corpus_minimum_target_count: {first_corpus_minimum_target_count}",
        "",
        "Source-attested names are accepted for MVP display even when not human-reviewed; this is warning-level, not a blocker.",
        "Runtime must display only `displayable_curated` and `displayable_source_attested`.",
        "Runtime must not display placeholders/scientific fallbacks/conflicts and must not invent or fetch labels.",
        "",
        "## Key Counts",
        "",
        f"- displayable_source_attested_label_count: {displayable_source_attested_label_count}",
        f"- displayable_curated_label_count: {displayable_curated_label_count}",
        f"- not_displayable_missing_count: {not_displayable_missing_count}",
        f"- not_displayable_placeholder_count: {not_displayable_placeholder_count}",
        f"- not_displayable_scientific_fallback_count: {not_displayable_scientific_fallback_count}",
        f"- needs_review_conflict_count: {needs_review_conflict_count}",
        "",
        "## Exact Non-Actions",
        "",
        "- PERSIST_DISTRACTOR_RELATIONSHIPS_V1 remains false",
        "- DATABASE_PHASE_CLOSED remains false",
        "- No runtime app code created",
        "- No names invented",
        "",
        "## Next Phase Recommendation",
        "",
        f"- {next_phase_for_decision(decision)}",
    ]
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return payload


def main() -> None:
    result = run_audit()
    print(f"Decision: {result['decision']}")
    print(
        "safe_ready_target_count_after_source_attested_policy: "
        f"{result['safe_ready_target_count_after_source_attested_policy']}"
    )


if __name__ == "__main__":
    main()
