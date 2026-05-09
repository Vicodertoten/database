from __future__ import annotations

import hashlib
import json
import random
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from database_core.dynamic_pack import validate_pack_pool, validate_session_snapshot
from database_core.storage.services import build_storage_services
from database_core.versioning import (
    PACK_POOL_VERSION,
    SCHEMA_VERSION_LABEL,
    SESSION_SNAPSHOT_VERSION,
)

PHASE2A_REPORT_VERSION = "dynamic_pack_phase2a.v1"
PHASE2A_PRODUCT_SCOPE = "be_fr_birds_50"
PHASE2A_COUNTRY_CODES = ("BE", "FR")
PHASE2A_LOCALES = ("fr", "en", "nl")
PHASE2A_SELECTOR_VERSION = "phase2a.selector.v1"
PHASE2A_DEFAULT_QUESTION_COUNT = 20
PHASE2A_MIN_TAXA_FOR_GO = 50
PHASE2A_MIN_ITEMS_PER_TAXON_FOR_GO = 20


def build_pack_pool(
    *,
    database_url: str,
    pool_id: str,
    source_run_id: str,
    output_dir: Path,
) -> dict[str, Any]:
    services = build_storage_services(database_url)
    items = _fetch_pool_candidates(database_url=database_url, source_run_id=source_run_id)
    generated_at = _now_iso()
    payload = {
        "schema_version": SCHEMA_VERSION_LABEL,
        "pack_pool_version": PACK_POOL_VERSION,
        "pool_id": pool_id,
        "generated_at": generated_at,
        "source_run_id": source_run_id,
        "scope": {
            "product_scope": PHASE2A_PRODUCT_SCOPE,
            "country_codes": list(PHASE2A_COUNTRY_CODES),
            "locale_policy": "fallback_allowed_internal",
        },
        "metrics": _build_pool_metrics(items),
        "items": items,
    }
    validate_pack_pool(payload)
    services.dynamic_pack_store.save_pack_pool(payload)
    _write_json(output_dir / "pack_pool.v1.json", payload)
    _write_markdown(
        output_dir / "pack_pool_report.md",
        [
            "# Phase 2A Pack Pool",
            "",
            f"- pool_id: `{pool_id}`",
            f"- source_run_id: `{source_run_id}`",
            f"- items: `{payload['metrics']['item_count']}`",
            f"- taxa: `{payload['metrics']['taxon_count']}`",
            f"- min_items_per_taxon: `{payload['metrics']['min_items_per_taxon']}`",
        ],
    )
    return payload


def build_session_fixtures(
    *,
    database_url: str,
    pool_id: str,
    question_count: int,
    seed: str,
    locales: list[str],
    output_dir: Path,
) -> list[dict[str, Any]]:
    services = build_storage_services(database_url)
    pool = services.dynamic_pack_store.fetch_pack_pool(pool_id=pool_id)
    if pool is None:
        raise ValueError(f"Unknown pool_id: {pool_id}")
    sessions = [
        build_session_snapshot(
            pool=pool,
            locale=locale,
            seed=seed,
            question_count=question_count,
        )
        for locale in locales
    ]
    for session in sessions:
        validate_session_snapshot(session)
        services.dynamic_pack_store.save_session_snapshot(session)
        _write_json(
            output_dir / f"session_snapshot.{session['locale']}.v1.json",
            session,
        )
    _write_json(output_dir / "session_fixture_index.json", {"sessions": sessions})
    return sessions


def build_session_snapshot(
    *,
    pool: dict[str, Any],
    locale: str,
    seed: str,
    question_count: int,
) -> dict[str, Any]:
    if locale not in PHASE2A_LOCALES:
        raise ValueError(f"Unsupported locale: {locale}")
    if question_count <= 0:
        raise ValueError("question_count must be > 0")

    items = _as_pool_items(pool)
    by_taxon: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_taxon[str(item["canonical_taxon_id"])].append(item)
    if len(by_taxon) < question_count:
        raise ValueError(
            "Pool does not contain enough distinct taxa for one-question-per-taxon "
            f"selection: requested={question_count}, available_taxa={len(by_taxon)}"
        )

    rng = random.Random(_stable_seed(f"{seed}:{locale}:{pool['pool_id']}"))
    taxon_ids = sorted(by_taxon)
    rng.shuffle(taxon_ids)
    selected_taxa = taxon_ids[:question_count]
    questions = []
    for index, taxon_id in enumerate(selected_taxa, start=1):
        candidates = sorted(by_taxon[taxon_id], key=lambda item: str(item["playable_item_id"]))
        item = candidates[rng.randrange(len(candidates))]
        labels = item["labels"]
        label_sources = item["label_sources"]
        question_id = _stable_id(
            "question",
            str(pool["pool_id"]),
            seed,
            locale,
            str(index),
            str(item["playable_item_id"]),
        )
        questions.append(
            {
                "question_id": question_id,
                "question_index": index,
                "playable_item_id": item["playable_item_id"],
                "canonical_taxon_id": item["canonical_taxon_id"],
                "media_asset_id": item["media_asset_id"],
                "scientific_name": item["scientific_name"],
                "label": labels[locale],
                "label_source": label_sources[locale],
                "feedback_short": item["feedback_short"],
                "media": item["media"],
                "country_code": item["country_code"],
                "options": [],
                "option_generation": {
                    "status": "deferred_phase3",
                    "reason": "Advanced distractor generation is outside Phase 2A scope.",
                },
            }
        )

    payload = {
        "schema_version": SCHEMA_VERSION_LABEL,
        "session_snapshot_version": SESSION_SNAPSHOT_VERSION,
        "session_snapshot_id": _stable_id("session", str(pool["pool_id"]), seed, locale),
        "pool_id": pool["pool_id"],
        "generated_at": _now_iso(),
        "locale": locale,
        "seed": seed,
        "question_count": question_count,
        "selector_policy": {
            "version": PHASE2A_SELECTOR_VERSION,
            "max_questions_per_taxon": 1,
            "option_generation": "deferred_phase3",
        },
        "questions": questions,
    }
    validate_session_snapshot(payload)
    return payload


def audit_phase2a(
    *,
    database_url: str,
    pool_id: str,
    output_dir: Path,
    question_count: int = PHASE2A_DEFAULT_QUESTION_COUNT,
) -> dict[str, Any]:
    services = build_storage_services(database_url)
    pool = services.dynamic_pack_store.fetch_pack_pool(pool_id=pool_id)
    if pool is None:
        raise ValueError(f"Unknown pool_id: {pool_id}")

    locale_sessions: dict[str, dict[str, object]] = {}
    blockers: list[str] = []
    warnings: list[str] = []
    for locale in PHASE2A_LOCALES:
        try:
            session = build_session_snapshot(
                pool=pool,
                locale=locale,
                seed="phase2a-audit",
                question_count=question_count,
            )
        except ValueError as exc:
            locale_sessions[locale] = {"can_generate": False, "reason": str(exc)}
            blockers.append(f"session_generation_failed_{locale}")
        else:
            locale_sessions[locale] = {
                "can_generate": True,
                "question_count": session["question_count"],
            }

    metrics = pool["metrics"]
    if int(metrics["taxon_count"]) < PHASE2A_MIN_TAXA_FOR_GO:
        blockers.append("taxon_count_below_50")
    if int(metrics["taxa_with_at_least_20_items"]) < PHASE2A_MIN_TAXA_FOR_GO:
        blockers.append("taxa_with_at_least_20_items_below_50")
    if float(metrics["attribution_completeness"]) < 1.0:
        blockers.append("attribution_incomplete")
    if float(metrics["media_url_completeness"]) < 1.0:
        blockers.append("media_url_incomplete")

    locale_label_completeness = metrics["locale_label_completeness"]
    if any(float(locale_label_completeness[locale]) < 1.0 for locale in PHASE2A_LOCALES):
        blockers.append("locale_label_resolution_incomplete")
    fallback_counts = metrics.get("locale_label_fallback_counts", {})
    if any(int(fallback_counts.get(locale, 0)) > 0 for locale in ("fr", "nl")):
        warnings.append("fr_nl_labels_use_internal_fallback")

    status = "GO"
    if blockers:
        status = "NO_GO"
    elif warnings:
        status = "GO_WITH_WARNINGS"

    report = {
        "schema_version": PHASE2A_REPORT_VERSION,
        "report_type": "audit",
        "generated_at": _now_iso(),
        "pool_id": pool_id,
        "status": status,
        "blockers": blockers,
        "warnings": warnings,
        "metrics": metrics,
        "locale_sessions": locale_sessions,
        "promotion_allowed": False,
    }
    _write_json(output_dir / "phase2a_audit_report.json", report)
    _write_markdown(
        output_dir / "phase2a_audit_summary.md",
        [
            "# Phase 2A Audit",
            "",
            f"Status: `{status}`",
            "",
            f"- pool_id: `{pool_id}`",
            f"- items: `{metrics['item_count']}`",
            f"- taxa: `{metrics['taxon_count']}`",
            f"- taxa_with_at_least_20_items: `{metrics['taxa_with_at_least_20_items']}`",
            f"- warnings: `{len(warnings)}`",
            f"- blockers: `{len(blockers)}`",
        ],
    )
    return report


def _fetch_pool_candidates(*, database_url: str, source_run_id: str) -> list[dict[str, Any]]:
    services = build_storage_services(database_url)
    with services.database.connect() as connection:
        rows = connection.execute(
            """
            SELECT
                p.playable_item_id,
                p.qualified_resource_id,
                p.canonical_taxon_id,
                p.media_asset_id,
                p.scientific_name,
                p.common_names_i18n_json,
                p.difficulty_level,
                p.media_role,
                p.learning_suitability,
                p.diagnostic_feature_visibility,
                p.what_to_look_at_specific_json,
                p.what_to_look_at_general_json,
                p.confusion_hint,
                p.country_code,
                m.source_url AS media_render_url,
                m.attribution AS media_attribution,
                m.license AS media_license
            FROM playable_corpus_v1 AS p
            JOIN qualified_resources AS q
                ON q.qualified_resource_id = p.qualified_resource_id
            JOIN media_assets AS m
                ON m.media_id = p.media_asset_id
            WHERE p.run_id = %s
              AND q.export_eligible IS TRUE
              AND p.country_code IN ('BE', 'FR')
              AND NULLIF(TRIM(m.source_url), '') IS NOT NULL
              AND NULLIF(TRIM(m.attribution), '') IS NOT NULL
              AND NULLIF(TRIM(p.canonical_taxon_id), '') IS NOT NULL
            ORDER BY p.canonical_taxon_id, p.playable_item_id
            """,
            (source_run_id,),
        ).fetchall()

    return [_pool_item_from_row(row) for row in rows]


def _pool_item_from_row(row: dict[str, Any]) -> dict[str, Any]:
    common_names_i18n = json.loads(str(row["common_names_i18n_json"]))
    scientific_name = str(row["scientific_name"])
    labels, label_sources = _resolve_labels(
        common_names_i18n=common_names_i18n,
        scientific_name=scientific_name,
    )
    return {
        "playable_item_id": row["playable_item_id"],
        "qualified_resource_id": row["qualified_resource_id"],
        "canonical_taxon_id": row["canonical_taxon_id"],
        "media_asset_id": row["media_asset_id"],
        "scientific_name": scientific_name,
        "labels": labels,
        "label_sources": label_sources,
        "difficulty_level": row["difficulty_level"],
        "media_role": row["media_role"],
        "learning_suitability": row["learning_suitability"],
        "diagnostic_feature_visibility": row["diagnostic_feature_visibility"],
        "feedback_short": _resolve_feedback_short(row),
        "media": {
            "render_url": str(row["media_render_url"]).strip(),
            "attribution": str(row["media_attribution"]).strip(),
            "license": row["media_license"],
        },
        "country_code": row["country_code"],
    }


def _resolve_labels(
    *,
    common_names_i18n: dict[str, object],
    scientific_name: str,
) -> tuple[dict[str, str], dict[str, str]]:
    labels: dict[str, str] = {}
    sources: dict[str, str] = {}
    for locale in PHASE2A_LOCALES:
        names = common_names_i18n.get(locale)
        label = _first_non_empty_string(names if isinstance(names, list) else [])
        if label:
            labels[locale] = label
            sources[locale] = "common_name"
        else:
            labels[locale] = scientific_name
            sources[locale] = "scientific_name"
    return labels, sources


def _resolve_feedback_short(row: dict[str, Any]) -> str | None:
    for key in ("what_to_look_at_specific_json", "what_to_look_at_general_json"):
        values = json.loads(str(row[key]))
        value = _first_non_empty_string(values if isinstance(values, list) else [])
        if value:
            return value
    hint = row["confusion_hint"]
    if isinstance(hint, str) and hint.strip():
        return hint.strip()
    return None


def _build_pool_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    item_count = len(items)
    by_taxon = Counter(str(item["canonical_taxon_id"]) for item in items)
    country_counts = Counter(str(item["country_code"]) for item in items)
    locale_common_counts = {
        locale: sum(
            1 for item in items if item["label_sources"][locale] == "common_name"
        )
        for locale in PHASE2A_LOCALES
    }
    locale_fallback_counts = {
        locale: item_count - locale_common_counts[locale] for locale in PHASE2A_LOCALES
    }
    return {
        "item_count": item_count,
        "taxon_count": len(by_taxon),
        "country_counts": dict(sorted(country_counts.items())),
        "min_items_per_taxon": min(by_taxon.values()) if by_taxon else 0,
        "taxa_with_at_least_20_items": sum(
            1 for count in by_taxon.values() if count >= PHASE2A_MIN_ITEMS_PER_TAXON_FOR_GO
        ),
        "items_per_taxon": dict(sorted(by_taxon.items())),
        "attribution_completeness": _ratio(
            sum(1 for item in items if item["media"]["attribution"]),
            item_count,
        ),
        "media_url_completeness": _ratio(
            sum(1 for item in items if item["media"]["render_url"]),
            item_count,
        ),
        "locale_label_completeness": {
            locale: _ratio(sum(1 for item in items if item["labels"][locale]), item_count)
            for locale in PHASE2A_LOCALES
        },
        "locale_label_common_name_counts": locale_common_counts,
        "locale_label_fallback_counts": locale_fallback_counts,
    }


def _as_pool_items(pool: dict[str, Any]) -> list[dict[str, Any]]:
    items = pool.get("items")
    if not isinstance(items, list):
        raise ValueError("pack_pool items must be a list")
    return [item for item in items if isinstance(item, dict)]


def _first_non_empty_string(values: list[object]) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _stable_seed(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:16], 16)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 6)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
