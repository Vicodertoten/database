from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from database_core.storage.services import build_storage_services

PHASE2B_AUDIT_VERSION = "dynamic_pack_phase2b_audit.v1"
PHASE2B_LOCALES = ("fr", "en", "nl")
USABLE_REFERENCED_MAPPING_STATUSES = {"mapped", "auto_referenced_high_confidence"}

DEFAULT_NAME_REPAIR_JSON = Path("docs/audits/evidence/phase2b/name_repair_audit.json")
DEFAULT_NAME_REPAIR_MD = Path("docs/audits/phase2b-name-repair-audit.md")
DEFAULT_REFERENCED_ONLY_JSON = Path("docs/audits/evidence/phase2b/referenced_only_audit.json")
DEFAULT_REFERENCED_ONLY_MD = Path("docs/audits/phase2b-referenced-only-audit.md")
DEFAULT_LOCALIZED_NAME_PLAN = Path("docs/audits/evidence/localized_name_apply_plan_v1.json")


def run_name_repair_audit(
    *,
    database_url: str,
    pool_id: str,
    localized_name_plan_path: Path | None = DEFAULT_LOCALIZED_NAME_PLAN,
    output_json: Path = DEFAULT_NAME_REPAIR_JSON,
    output_md: Path = DEFAULT_NAME_REPAIR_MD,
) -> dict[str, Any]:
    services = build_storage_services(database_url)
    pool = services.dynamic_pack_store.fetch_pack_pool(pool_id=pool_id)
    if pool is None:
        raise ValueError(f"Unknown pool_id: {pool_id}")

    pool_items = _pool_items(pool)
    localized_evidence_names = load_localized_name_plan(localized_name_plan_path)
    rows_by_playable_id = _fetch_name_rows(
        database_url=database_url,
        playable_item_ids=[str(item["playable_item_id"]) for item in pool_items],
    )
    item_reports = [
        classify_pool_item_names(
            pool_item=item,
            db_row=rows_by_playable_id.get(str(item["playable_item_id"])),
            source_run_id=str(pool["source_run_id"]),
            localized_evidence_names=localized_evidence_names.get(
                str(item["canonical_taxon_id"]), {}
            ),
        )
        for item in pool_items
    ]
    report = build_name_repair_report(pool=pool, item_reports=item_reports)
    _write_json(output_json, report)
    _write_markdown(output_md, render_name_repair_markdown(report))
    return report


def run_referenced_only_audit(
    *,
    database_url: str,
    output_json: Path = DEFAULT_REFERENCED_ONLY_JSON,
    output_md: Path = DEFAULT_REFERENCED_ONLY_MD,
) -> dict[str, Any]:
    rows = _fetch_referenced_taxa(database_url=database_url)
    items = [classify_referenced_taxon(row) for row in rows]
    report = build_referenced_only_report(items)
    _write_json(output_json, report)
    _write_markdown(output_md, render_referenced_only_markdown(report))
    return report


def classify_pool_item_names(
    *,
    pool_item: dict[str, Any],
    db_row: dict[str, Any] | None,
    source_run_id: str,
    localized_evidence_names: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    playable_item_id = str(pool_item.get("playable_item_id", ""))
    canonical_taxon_id = str(pool_item.get("canonical_taxon_id", ""))
    evidence_names = localized_evidence_names or {}
    labels = _dict_or_empty(pool_item.get("labels"))
    label_sources = _dict_or_empty(pool_item.get("label_sources"))
    pool_scientific_name = str(pool_item.get("scientific_name") or "")

    if db_row is None:
        return {
            "playable_item_id": playable_item_id,
            "canonical_taxon_id": canonical_taxon_id,
            "scientific_name": pool_scientific_name,
            "issues": ["wrong_source_run"],
            "locale_reports": [
                {
                    "locale": locale,
                    "pool_label": labels.get(locale),
                    "pool_label_source": label_sources.get(locale),
                    "issues": ["wrong_source_run"],
                }
                for locale in PHASE2B_LOCALES
            ],
        }

    playable_names = _parse_i18n(db_row.get("playable_corpus_names_json"))
    item_names = _parse_i18n(db_row.get("playable_item_names_json"))
    canonical_common_names = _parse_string_list(db_row.get("canonical_common_names_json"))
    item_run_id = str(db_row.get("item_run_id") or "")
    corpus_run_id = str(db_row.get("corpus_run_id") or "")
    scientific_name = str(
        db_row.get("playable_scientific_name")
        or db_row.get("canonical_scientific_name")
        or pool_scientific_name
    )

    locale_reports = []
    all_issues: list[str] = []
    for locale in PHASE2B_LOCALES:
        pool_label = _non_empty(labels.get(locale))
        pool_label_source = _non_empty(label_sources.get(locale))
        locale_issues = classify_locale_label(
            locale=locale,
            pool_label=pool_label,
            pool_label_source=pool_label_source,
            playable_names=playable_names,
            item_names=item_names,
            localized_evidence_names=evidence_names,
            canonical_common_names=canonical_common_names,
            scientific_name=scientific_name,
        )
        if item_run_id and item_run_id != source_run_id:
            locale_issues.append("wrong_source_run")
        if corpus_run_id and corpus_run_id != source_run_id:
            locale_issues.append("wrong_source_run")
        locale_issues = _dedupe(locale_issues)
        all_issues.extend(locale_issues)
        locale_reports.append(
            {
                "locale": locale,
                "pool_label": pool_label,
                "pool_label_source": pool_label_source,
                "playable_corpus_names": _names(playable_names, locale),
                "playable_item_names": _names(item_names, locale),
                "localized_evidence_names": _names(evidence_names, locale),
                "issues": locale_issues,
            }
        )

    return {
        "playable_item_id": playable_item_id,
        "canonical_taxon_id": canonical_taxon_id,
        "scientific_name": scientific_name,
        "source_run_id": source_run_id,
        "item_run_id": item_run_id,
        "corpus_run_id": corpus_run_id,
        "issues": _dedupe(all_issues),
        "locale_reports": locale_reports,
    }


def classify_locale_label(
    *,
    locale: str,
    pool_label: str | None,
    pool_label_source: str | None,
    playable_names: dict[str, list[str]],
    item_names: dict[str, list[str]],
    localized_evidence_names: dict[str, list[str]] | None = None,
    canonical_common_names: list[str],
    scientific_name: str,
) -> list[str]:
    issues: list[str] = []
    evidence_names = localized_evidence_names or {}
    source_names = _dedupe([*_names(playable_names, locale), *_names(item_names, locale)])
    item_locale_names = _names(item_names, locale)
    playable_locale_names = _names(playable_names, locale)
    evidence_locale_names = _names(evidence_names, locale)
    approved_locale_names = _dedupe([*source_names, *evidence_locale_names])
    other_locale_names = _other_locale_names(playable_names, item_names, locale)
    evidence_other_locale_names = [
        name
        for evidence_locale, names in evidence_names.items()
        if evidence_locale != locale
        for name in names
    ]
    all_other_locale_names = _dedupe([*other_locale_names, *evidence_other_locale_names])

    if pool_label and _matches_any(pool_label, all_other_locale_names):
        if evidence_locale_names:
            if not _matches_any(pool_label, evidence_locale_names):
                issues.append("wrong_locale_mapping")
        elif not _matches_any(pool_label, approved_locale_names):
            issues.append("wrong_locale_mapping")

    if pool_label_source == "scientific_name":
        if item_locale_names and not playable_locale_names:
            issues.append("stale_playable_item")
        elif evidence_locale_names and not source_names:
            issues.append("stale_playable_item")
        elif source_names:
            issues.append("wrong_pool_projection")
        elif evidence_locale_names:
            issues.append("wrong_pool_projection")
        elif locale == "en" and canonical_common_names:
            issues.append("wrong_pool_projection")
        else:
            issues.append("missing_source_name")
    elif pool_label_source == "common_name":
        if evidence_locale_names and pool_label and not _matches_any(
            pool_label, evidence_locale_names
        ):
            if not _matches_any(pool_label, all_other_locale_names):
                issues.append("approved_source_conflict")
        elif approved_locale_names and pool_label and not _matches_any(
            pool_label, approved_locale_names
        ):
            if not _matches_any(pool_label, all_other_locale_names):
                issues.append("approved_source_conflict")
        if not approved_locale_names and not (locale == "en" and canonical_common_names):
            issues.append("unknown")
    elif pool_label_source:
        issues.append("unknown")
    else:
        issues.append("unknown")

    if pool_label and scientific_name and _norm(pool_label) == _norm(scientific_name):
        if source_names:
            issues.append("wrong_pool_projection")
        elif "missing_source_name" not in issues:
            issues.append("missing_source_name")

    return _dedupe(issues)


def classify_referenced_taxon(row: dict[str, Any]) -> dict[str, Any]:
    common_names = _parse_i18n(row.get("common_names_i18n_json"))
    mapping_status = str(row.get("mapping_status") or "").strip()
    scientific_name = str(row.get("scientific_name") or "").strip()
    status_usable = mapping_status in USABLE_REFERENCED_MAPPING_STATUSES
    internal_eligible = bool(scientific_name and status_usable)
    public_eligible_by_locale = {
        locale: bool(internal_eligible and _names(common_names, locale))
        for locale in PHASE2B_LOCALES
    }
    missing_common_name_locales = [
        locale for locale in PHASE2B_LOCALES if not _names(common_names, locale)
    ]
    return {
        "referenced_taxon_id": row.get("referenced_taxon_id"),
        "source": row.get("source"),
        "source_taxon_id": row.get("source_taxon_id"),
        "scientific_name": scientific_name,
        "preferred_common_name": row.get("preferred_common_name"),
        "mapping_status": mapping_status,
        "mapped_canonical_taxon_id": row.get("mapped_canonical_taxon_id"),
        "reason_codes": _parse_json_list(row.get("reason_codes_json")),
        "common_names_i18n": common_names,
        "internal_eligible": internal_eligible,
        "public_eligible_by_locale": public_eligible_by_locale,
        "missing_common_name_locales": missing_common_name_locales,
        "correction_recommendations": _referenced_corrections(
            scientific_name=scientific_name,
            status_usable=status_usable,
            missing_common_name_locales=missing_common_name_locales,
        ),
    }


def load_localized_name_plan(path: Path | None) -> dict[str, dict[str, list[str]]]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, dict[str, list[str]]] = {}
    for item in payload.get("items", []):
        if item.get("taxon_kind") != "canonical_taxon":
            continue
        taxon_id = str(item.get("taxon_id") or "").strip()
        locale = str(item.get("locale") or "").strip()
        if not taxon_id or locale not in PHASE2B_LOCALES:
            continue
        values = []
        chosen = _non_empty(item.get("chosen_value"))
        if chosen:
            values.append(chosen)
        for evidence in item.get("evidence_refs", []) or []:
            value = _non_empty(evidence.get("value") if isinstance(evidence, dict) else None)
            if value:
                values.append(value)
        result.setdefault(taxon_id, {}).setdefault(locale, [])
        result[taxon_id][locale] = _dedupe([*result[taxon_id][locale], *values])
    return result


def build_name_repair_report(
    *,
    pool: dict[str, Any],
    item_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    locale_metrics: dict[str, dict[str, Any]] = {}
    issue_counts = Counter()
    examples: dict[str, list[dict[str, Any]]] = {}
    for locale in PHASE2B_LOCALES:
        reports = [
            locale_report
            for item in item_reports
            for locale_report in item["locale_reports"]
            if locale_report["locale"] == locale
        ]
        strict_common = sum(
            1 for report in reports if report.get("pool_label_source") == "common_name"
        )
        fallback = sum(
            1 for report in reports if report.get("pool_label_source") == "scientific_name"
        )
        suspect = sum(1 for report in reports if "wrong_locale_mapping" in report["issues"])
        locale_metrics[locale] = {
            "pool_common_name_count": strict_common,
            "pool_scientific_fallback_count": fallback,
            "suspect_language_count": suspect,
            "issue_counts": dict(
                Counter(issue for report in reports for issue in report["issues"])
            ),
        }

    for item in item_reports:
        for issue in item["issues"]:
            issue_counts[issue] += 1
            examples.setdefault(issue, [])
            if len(examples[issue]) < 8:
                examples[issue].append(_example_from_item_report(item, issue))

    decision = _audit_decision(issue_counts)
    report = {
        "schema_version": PHASE2B_AUDIT_VERSION,
        "report_type": "phase2b_name_repair_audit",
        "generated_at": _now_iso(),
        "pool_id": pool["pool_id"],
        "source_run_id": pool["source_run_id"],
        "decision": decision,
        "metrics": {
            "pool_item_count": len(item_reports),
            "items_with_issues": sum(1 for item in item_reports if item["issues"]),
            "issue_counts": dict(sorted(issue_counts.items())),
            "locale_metrics": locale_metrics,
        },
        "examples": examples,
        "correction_recommendations": _name_repair_recommendations(issue_counts),
    }
    return report


def build_referenced_only_report(items: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(str(item["mapping_status"]) for item in items)
    public_eligible_by_locale = {
        locale: sum(1 for item in items if item["public_eligible_by_locale"][locale])
        for locale in PHASE2B_LOCALES
    }
    missing_by_locale = {
        locale: sum(1 for item in items if locale in item["missing_common_name_locales"])
        for locale in PHASE2B_LOCALES
    }
    correction_items = [
        item
        for item in items
        if item["correction_recommendations"] and item["internal_eligible"]
    ]
    issue_exists = bool(correction_items) or any(
        status not in USABLE_REFERENCED_MAPPING_STATUSES for status in status_counts
    )
    report = {
        "schema_version": PHASE2B_AUDIT_VERSION,
        "report_type": "phase2b_referenced_only_audit",
        "generated_at": _now_iso(),
        "decision": "READY_FOR_CORRECTION" if issue_exists else "NO_ISSUE_FOUND",
        "metrics": {
            "referenced_taxa_total": len(items),
            "mapping_status_counts": dict(sorted(status_counts.items())),
            "internal_eligible_count": sum(1 for item in items if item["internal_eligible"]),
            "public_eligible_by_locale": public_eligible_by_locale,
            "missing_common_name_by_locale": missing_by_locale,
        },
        "examples": {
            "missing_public_names": [
                _referenced_example(item)
                for item in correction_items[:8]
            ],
            "non_usable_statuses": [
                _referenced_example(item)
                for item in items
                if item["mapping_status"] not in USABLE_REFERENCED_MAPPING_STATUSES
            ][:8],
        },
        "correction_recommendations": _referenced_report_recommendations(items),
    }
    return report


def render_name_repair_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        f"last_reviewed: {_today()}",
        "source_of_truth: docs/audits/phase2b-name-repair-audit.md",
        "scope: phase2b_name_repair_audit",
        "---",
        "",
        "# Phase 2B Name Repair Audit",
        "",
        f"- decision: `{report['decision']}`",
        f"- pool_id: `{report['pool_id']}`",
        f"- source_run_id: `{report['source_run_id']}`",
        f"- pool items: `{metrics['pool_item_count']}`",
        f"- items with issues: `{metrics['items_with_issues']}`",
        "",
        "## Locale Metrics",
        "",
        "| Locale | Pool common names | Scientific fallbacks | Suspect language |",
        "|---|---:|---:|---:|",
    ]
    for locale, locale_metrics in metrics["locale_metrics"].items():
        lines.append(
            "| "
            f"{locale} | {locale_metrics['pool_common_name_count']} | "
            f"{locale_metrics['pool_scientific_fallback_count']} | "
            f"{locale_metrics['suspect_language_count']} |"
        )
    lines.extend(["", "## Issue Counts", ""])
    for issue, count in metrics["issue_counts"].items():
        lines.append(f"- `{issue}`: `{count}`")
    lines.extend(["", "## Correction Recommendations", ""])
    for recommendation in report["correction_recommendations"]:
        lines.append(f"- {recommendation}")
    return "\n".join(lines).rstrip() + "\n"


def render_referenced_only_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        f"last_reviewed: {_today()}",
        "source_of_truth: docs/audits/phase2b-referenced-only-audit.md",
        "scope: phase2b_referenced_only_audit",
        "---",
        "",
        "# Phase 2B Referenced-Only Audit",
        "",
        f"- decision: `{report['decision']}`",
        f"- referenced taxa total: `{metrics['referenced_taxa_total']}`",
        f"- internal eligible: `{metrics['internal_eligible_count']}`",
        "",
        "## Public Eligibility By Locale",
        "",
        "| Locale | Public eligible | Missing common name |",
        "|---|---:|---:|",
    ]
    for locale in PHASE2B_LOCALES:
        lines.append(
            "| "
            f"{locale} | {metrics['public_eligible_by_locale'][locale]} | "
            f"{metrics['missing_common_name_by_locale'][locale]} |"
        )
    lines.extend(["", "## Mapping Status Counts", ""])
    for status, count in metrics["mapping_status_counts"].items():
        lines.append(f"- `{status}`: `{count}`")
    lines.extend(["", "## Correction Recommendations", ""])
    for recommendation in report["correction_recommendations"]:
        lines.append(f"- {recommendation}")
    return "\n".join(lines).rstrip() + "\n"


def _fetch_name_rows(
    *,
    database_url: str,
    playable_item_ids: list[str],
) -> dict[str, dict[str, Any]]:
    if not playable_item_ids:
        return {}
    services = build_storage_services(database_url)
    with services.database.connect() as connection:
        rows = connection.execute(
            """
            SELECT
                pi.playable_item_id,
                pi.run_id AS item_run_id,
                pc.run_id AS corpus_run_id,
                pi.canonical_taxon_id,
                pi.scientific_name AS playable_scientific_name,
                pi.common_names_i18n_json AS playable_item_names_json,
                pc.common_names_i18n_json AS playable_corpus_names_json,
                ct.accepted_scientific_name AS canonical_scientific_name,
                ct.common_names_json AS canonical_common_names_json
            FROM playable_items pi
            LEFT JOIN playable_corpus_v1 pc
                ON pc.playable_item_id = pi.playable_item_id
            LEFT JOIN canonical_taxa ct
                ON ct.canonical_taxon_id = pi.canonical_taxon_id
            WHERE pi.playable_item_id = ANY(%s)
            """,
            (playable_item_ids,),
        ).fetchall()
    return {str(row["playable_item_id"]): row for row in rows}


def _fetch_referenced_taxa(*, database_url: str) -> list[dict[str, Any]]:
    services = build_storage_services(database_url)
    with services.database.connect() as connection:
        return connection.execute(
            """
            SELECT
                referenced_taxon_id,
                source,
                source_taxon_id,
                scientific_name,
                preferred_common_name,
                common_names_i18n_json,
                mapping_status,
                mapped_canonical_taxon_id,
                reason_codes_json
            FROM referenced_taxa
            ORDER BY mapping_status, source, source_taxon_id
            """
        ).fetchall()


def _pool_items(pool: dict[str, Any]) -> list[dict[str, Any]]:
    items = pool.get("items")
    if not isinstance(items, list):
        raise ValueError("pack_pool payload items must be a list")
    return [item for item in items if isinstance(item, dict)]


def _audit_decision(issue_counts: Counter[str]) -> str:
    if not issue_counts:
        return "NO_ISSUE_FOUND"
    if issue_counts.get("wrong_locale_mapping", 0) > 0:
        return "BLOCKED_BY_UNKNOWN_SOURCE"
    if issue_counts.get("approved_source_conflict", 0) > 0:
        return "BLOCKED_BY_UNKNOWN_SOURCE"
    if issue_counts.get("unknown", 0) > 0:
        return "BLOCKED_BY_UNKNOWN_SOURCE"
    return "READY_FOR_CORRECTION"


def _name_repair_recommendations(issue_counts: Counter[str]) -> list[str]:
    recommendations: list[str] = []
    if issue_counts.get("wrong_locale_mapping"):
        recommendations.append(
            "Inspect localized-name mapping/projection; at least one label appears "
            "under the wrong locale."
        )
    if issue_counts.get("wrong_pool_projection"):
        recommendations.append(
            "Repair pack pool label projection so existing localized names are "
            "selected before scientific fallback."
        )
    if issue_counts.get("approved_source_conflict"):
        recommendations.append(
            "Inspect label projection against approved localized-name sources; at least "
            "one label conflicts with the expected locale value."
        )
    if issue_counts.get("stale_playable_item"):
        recommendations.append(
            "Regenerate or refresh playable corpus rows from the latest localized-name source."
        )
    if issue_counts.get("missing_source_name"):
        recommendations.append(
            "Backfill missing localized names from approved sources before the "
            "next Phase 2B generation run."
        )
    if issue_counts.get("wrong_source_run"):
        recommendations.append(
            "Rebuild the pack pool from the expected source_run_id in the Phase 1/2A clone."
        )
    if issue_counts.get("unknown"):
        recommendations.append(
            "Manually inspect unknown label states before creating session_snapshot.v2."
        )
    if not recommendations:
        recommendations.append("No name repair required before Phase 2B generation.")
    return recommendations


def _referenced_report_recommendations(items: list[dict[str, Any]]) -> list[str]:
    recommendations: list[str] = []
    if any(item["internal_eligible"] and item["missing_common_name_locales"] for item in items):
        recommendations.append(
            "Backfill FR/EN/NL common names for internally eligible referenced-only "
            "distractors before public use."
        )
    if any(item["mapping_status"] == "auto_referenced_low_confidence" for item in items):
        recommendations.append(
            "Review low-confidence referenced taxa before allowing them as distractors."
        )
    if any(item["mapping_status"] in {"ambiguous", "ignored"} for item in items):
        recommendations.append(
            "Keep ambiguous or ignored referenced taxa excluded from distractor selection."
        )
    if not recommendations:
        recommendations.append("No referenced-only correction required before Phase 2B generation.")
    return recommendations


def _referenced_corrections(
    *,
    scientific_name: str,
    status_usable: bool,
    missing_common_name_locales: list[str],
) -> list[str]:
    recommendations: list[str] = []
    if not scientific_name:
        recommendations.append("add_scientific_name")
    if not status_usable:
        recommendations.append("review_mapping_status")
    for locale in missing_common_name_locales:
        recommendations.append(f"backfill_common_name_{locale}")
    return recommendations


def _example_from_item_report(item: dict[str, Any], issue: str) -> dict[str, Any]:
    matching_locale_reports = [
        locale_report
        for locale_report in item["locale_reports"]
        if issue in locale_report["issues"]
    ]
    return {
        "playable_item_id": item["playable_item_id"],
        "canonical_taxon_id": item["canonical_taxon_id"],
        "scientific_name": item["scientific_name"],
        "issue": issue,
        "locales": [
            {
                "locale": report["locale"],
                "pool_label": report.get("pool_label"),
                "pool_label_source": report.get("pool_label_source"),
                "playable_corpus_names": report.get("playable_corpus_names", []),
                "playable_item_names": report.get("playable_item_names", []),
                "localized_evidence_names": report.get("localized_evidence_names", []),
            }
            for report in matching_locale_reports[:3]
        ],
    }


def _referenced_example(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "referenced_taxon_id": item["referenced_taxon_id"],
        "source_taxon_id": item["source_taxon_id"],
        "scientific_name": item["scientific_name"],
        "mapping_status": item["mapping_status"],
        "missing_common_name_locales": item["missing_common_name_locales"],
        "public_eligible_by_locale": item["public_eligible_by_locale"],
    }


def _parse_i18n(raw_value: object) -> dict[str, list[str]]:
    parsed = _parse_json_object(raw_value)
    result: dict[str, list[str]] = {}
    for locale in PHASE2B_LOCALES:
        values = parsed.get(locale, [])
        result[locale] = _string_list(values)
    return result


def _parse_string_list(raw_value: object) -> list[str]:
    return _string_list(_parse_json_value(raw_value))


def _parse_json_list(raw_value: object) -> list[str]:
    return _string_list(_parse_json_value(raw_value))


def _parse_json_object(raw_value: object) -> dict[str, Any]:
    parsed = _parse_json_value(raw_value)
    return parsed if isinstance(parsed, dict) else {}


def _parse_json_value(raw_value: object) -> object:
    if raw_value is None:
        return None
    if isinstance(raw_value, (dict, list)):
        return raw_value
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return _dedupe([str(item).strip() for item in value if str(item).strip()])


def _names(names_by_locale: dict[str, list[str]], locale: str) -> list[str]:
    return names_by_locale.get(locale, [])


def _other_locale_names(
    playable_names: dict[str, list[str]],
    item_names: dict[str, list[str]],
    locale: str,
) -> list[str]:
    values: list[str] = []
    for other_locale in PHASE2B_LOCALES:
        if other_locale == locale:
            continue
        values.extend(_names(playable_names, other_locale))
        values.extend(_names(item_names, other_locale))
    return _dedupe(values)


def _matches_any(value: str, candidates: list[str]) -> bool:
    normalized = _norm(value)
    return any(normalized == _norm(candidate) for candidate in candidates)


def _norm(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def _non_empty(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _dict_or_empty(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _norm(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")
