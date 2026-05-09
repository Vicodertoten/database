from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from database_core.domain.enums import (
    CandidateTaxonRefType,
    DistractorRelationshipStatus,
)
from database_core.domain.models import DistractorRelationship
from database_core.dynamic_pack import validate_serving_bundle
from database_core.ops.phase2b_session_snapshot import (
    PHASE2B_DISTRACTOR_POLICY_VERSION,
    PHASE2B_FALLBACK_SOURCE,
    PHASE2B_QUESTION_COUNT,
    PHASE2B_SELECTOR_VERSION,
    PHASE2B_SOURCE_SCORES,
    _ancestor_ids,
    _as_pool_items,
    _fetch_taxonomy_profiles,
    _now_iso,
    _write_json,
)
from database_core.storage.services import build_storage_services
from database_core.versioning import (
    SCHEMA_VERSION_LABEL,
    SERVING_BUNDLE_VERSION,
)

PHASE2B_SERVING_BUNDLE_AUDIT_VERSION = "phase2b.serving_bundle_v1.audit.v1"
DEFAULT_SERVING_BUNDLE_OUTPUT_DIR = Path(
    "docs/archive/evidence/dynamic-pack-phase-2b/serving-bundle-v1"
)
DEFAULT_SERVING_BUNDLE_FILENAME = "serving_bundle.be-fr-birds-50.v1.json"


def export_serving_bundle_v1(
    *,
    database_url: str,
    pool_id: str,
    output_dir: Path = DEFAULT_SERVING_BUNDLE_OUTPUT_DIR,
    output_filename: str = DEFAULT_SERVING_BUNDLE_FILENAME,
) -> dict[str, Any]:
    services = build_storage_services(database_url)
    pool = services.dynamic_pack_store.fetch_pack_pool(pool_id=pool_id)
    if pool is None:
        raise ValueError(f"Unknown pool_id: {pool_id}")

    relationships_by_target = (
        services.distractor_relationship_store.fetch_validated_distractors_by_target()
    )
    taxonomy_profiles = _fetch_taxonomy_profiles(database_url=database_url)
    bundle = build_serving_bundle_v1(
        pool=pool,
        relationships_by_target=relationships_by_target,
        taxonomy_profiles=taxonomy_profiles,
    )
    validate_serving_bundle(bundle)
    report = audit_serving_bundle_v1(bundle)
    _write_json(output_dir / output_filename, bundle)
    _write_json(output_dir / "serving_bundle_v1_audit.json", report)
    _write_markdown_report(output_dir / "serving_bundle_v1_audit.md", report)
    return {"bundle": bundle, "audit": report}


def build_serving_bundle_v1(
    *,
    pool: dict[str, Any],
    relationships_by_target: dict[str, list[DistractorRelationship]],
    taxonomy_profiles: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    items = _as_pool_items(pool)
    taxon_ids = sorted({str(item["canonical_taxon_id"]) for item in items})
    relationships = _flatten_validated_relationships(
        relationships_by_target=relationships_by_target,
        eligible_taxon_ids=set(taxon_ids),
    )
    scoped_profiles = {
        taxon_id: _taxonomy_profile_payload(
            taxon_id=taxon_id,
            profile=taxonomy_profiles.get(taxon_id, {}),
        )
        for taxon_id in taxon_ids
    }
    media_asset_ids = {str(item["media_asset_id"]) for item in items}
    fallback_ready_count = sum(
        1
        for taxon_id in taxon_ids
        if _fallback_candidate_count(
            target_taxon_id=taxon_id,
            candidate_taxon_ids=taxon_ids,
            taxonomy_profiles=scoped_profiles,
        )
        >= 3
    )
    relationship_counts = Counter(str(item["source"]) for item in relationships)
    bundle = {
        "schema_version": SCHEMA_VERSION_LABEL,
        "serving_bundle_version": SERVING_BUNDLE_VERSION,
        "bundle_id": _bundle_id(str(pool["pool_id"])),
        "pool_id": pool["pool_id"],
        "source_run_id": pool["source_run_id"],
        "generated_at": _now_iso(),
        "question_count": PHASE2B_QUESTION_COUNT,
        "selector_policy": {
            "version": PHASE2B_SELECTOR_VERSION,
            "max_questions_per_taxon": 1,
            "unique_media_per_session": True,
        },
        "distractor_policy": {
            "version": PHASE2B_DISTRACTOR_POLICY_VERSION,
            "referenced_only_allowed": False,
            "max_referenced_only_per_question": 0,
            "fallback_source": PHASE2B_FALLBACK_SOURCE,
        },
        "source_scores": dict(PHASE2B_SOURCE_SCORES),
        "pack_pool": pool,
        "relationships": relationships,
        "taxonomy_profiles": scoped_profiles,
        "metrics": {
            "item_count": len(items),
            "taxon_count": len(taxon_ids),
            "media_asset_count": len(media_asset_ids),
            "relationship_count": len(relationships),
            "relationship_counts_by_source": dict(sorted(relationship_counts.items())),
            "taxonomy_profile_count": len(scoped_profiles),
            "fallback_ready_taxon_count": fallback_ready_count,
        },
    }
    validate_serving_bundle(bundle)
    return bundle


def audit_serving_bundle_v1(bundle: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    pool = bundle.get("pack_pool") if isinstance(bundle.get("pack_pool"), dict) else {}
    items = _as_pool_items(pool)
    taxon_ids = sorted({str(item.get("canonical_taxon_id") or "") for item in items})
    media_ids = [str(item.get("media_asset_id") or "") for item in items]
    relationships = [
        item for item in bundle.get("relationships", []) if isinstance(item, dict)
    ]
    taxonomy_profiles = (
        bundle.get("taxonomy_profiles")
        if isinstance(bundle.get("taxonomy_profiles"), dict)
        else {}
    )

    try:
        validate_serving_bundle(bundle)
    except ValueError:
        blockers.append("invalid_serving_bundle_contract")

    if len(taxon_ids) < PHASE2B_QUESTION_COUNT:
        blockers.append("insufficient_distinct_taxa")
    if len(set(media_ids)) < PHASE2B_QUESTION_COUNT:
        blockers.append("insufficient_unique_media")

    missing_labels = _items_missing_locale_labels(items)
    if missing_labels:
        blockers.append("missing_locale_labels")
    missing_media = [
        str(item.get("playable_item_id") or "")
        for item in items
        if not _item_has_media(item)
    ]
    if missing_media:
        blockers.append("missing_media")

    if any(
        item.get("status") != "validated"
        or item.get("candidate_taxon_ref_type") != "canonical_taxon"
        or not item.get("candidate_taxon_ref_id")
        for item in relationships
    ):
        blockers.append("non_validated_or_non_canonical_relationship")

    relationship_targets = defaultdict(int)
    for item in relationships:
        relationship_targets[str(item.get("target_canonical_taxon_id") or "")] += 1
    sparse_targets = [
        taxon_id for taxon_id in taxon_ids if relationship_targets.get(taxon_id, 0) < 3
    ]
    if sparse_targets:
        warnings.append("taxonomic_fallback_db_required")

    fallback_blocked_taxa = [
        taxon_id
        for taxon_id in taxon_ids
        if _fallback_candidate_count(
            target_taxon_id=taxon_id,
            candidate_taxon_ids=taxon_ids,
            taxonomy_profiles=taxonomy_profiles,
        )
        < 3
    ]
    if fallback_blocked_taxa:
        blockers.append("fallback_taxonomy_unavailable")

    status = "GO"
    if blockers:
        status = "NO_GO"
    elif warnings:
        status = "GO_WITH_WARNINGS"

    return {
        "schema_version": PHASE2B_SERVING_BUNDLE_AUDIT_VERSION,
        "report_type": "serving_bundle_v1_audit",
        "generated_at": _now_iso(),
        "pool_id": bundle.get("pool_id"),
        "status": status,
        "blockers": sorted(set(blockers)),
        "warnings": sorted(set(warnings)),
        "metrics": bundle.get("metrics"),
        "missing_label_item_count": len(missing_labels),
        "missing_media_item_count": len(missing_media),
        "targets_below_3_validated_relationships": sparse_targets,
        "fallback_blocked_taxa": fallback_blocked_taxa,
    }


def _flatten_validated_relationships(
    *,
    relationships_by_target: dict[str, list[DistractorRelationship]],
    eligible_taxon_ids: set[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for target_taxon_id in sorted(relationships_by_target):
        if target_taxon_id not in eligible_taxon_ids:
            continue
        for relationship in sorted(
            relationships_by_target[target_taxon_id],
            key=lambda item: (item.source_rank, item.relationship_id),
        ):
            candidate_id = str(relationship.candidate_taxon_ref_id or "")
            if (
                relationship.status != DistractorRelationshipStatus.VALIDATED
                or relationship.candidate_taxon_ref_type
                != CandidateTaxonRefType.CANONICAL_TAXON
                or not candidate_id
                or candidate_id not in eligible_taxon_ids
            ):
                continue
            rows.append(
                {
                    "relationship_id": relationship.relationship_id,
                    "target_canonical_taxon_id": relationship.target_canonical_taxon_id,
                    "target_scientific_name": relationship.target_scientific_name,
                    "candidate_taxon_ref_type": str(relationship.candidate_taxon_ref_type),
                    "candidate_taxon_ref_id": candidate_id,
                    "candidate_scientific_name": relationship.candidate_scientific_name,
                    "source": str(relationship.source),
                    "source_rank": relationship.source_rank,
                    "status": str(relationship.status),
                    "confusion_types": [str(value) for value in relationship.confusion_types],
                    "pedagogical_value": str(relationship.pedagogical_value),
                    "difficulty_level": str(relationship.difficulty_level),
                    "learner_level": str(relationship.learner_level),
                    "reason": relationship.reason,
                }
            )
    return rows


def _taxonomy_profile_payload(
    *,
    taxon_id: str,
    profile: dict[str, Any],
) -> dict[str, Any]:
    ancestor_ids = sorted(_ancestor_ids(profile))
    parent_id = profile.get("parent_id")
    return {
        **profile,
        "canonical_taxon_id": taxon_id,
        "parent_id": str(parent_id) if parent_id else None,
        "ancestor_ids": ancestor_ids,
    }


def _fallback_candidate_count(
    *,
    target_taxon_id: str,
    candidate_taxon_ids: list[str],
    taxonomy_profiles: dict[str, Any],
) -> int:
    target_profile = taxonomy_profiles.get(target_taxon_id)
    if not isinstance(target_profile, dict):
        return 0
    return sum(
        1
        for candidate_taxon_id in candidate_taxon_ids
        if candidate_taxon_id != target_taxon_id
        and isinstance(taxonomy_profiles.get(candidate_taxon_id), dict)
    )


def _items_missing_locale_labels(items: list[dict[str, Any]]) -> list[str]:
    missing: list[str] = []
    for item in items:
        labels = item.get("labels")
        label_sources = item.get("label_sources")
        if not isinstance(labels, dict) or not isinstance(label_sources, dict):
            missing.append(str(item.get("playable_item_id") or ""))
            continue
        if any(not str(labels.get(locale) or "").strip() for locale in ("fr", "en", "nl")):
            missing.append(str(item.get("playable_item_id") or ""))
            continue
        if any(
            str(label_sources.get(locale) or "") not in {"common_name", "scientific_name"}
            for locale in ("fr", "en", "nl")
        ):
            missing.append(str(item.get("playable_item_id") or ""))
    return missing


def _item_has_media(item: dict[str, Any]) -> bool:
    media = item.get("media")
    return (
        isinstance(media, dict)
        and bool(str(item.get("media_asset_id") or "").strip())
        and bool(str(media.get("render_url") or "").strip())
        and bool(str(media.get("attribution") or "").strip())
    )


def _bundle_id(pool_id: str) -> str:
    normalized = pool_id.replace("pack-pool:", "").replace(":", "-")
    return f"serving-bundle:{normalized}"


def _write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        f"last_reviewed: {str(report['generated_at'])[:10]}",
        "source_of_truth: docs/archive/evidence/dynamic-pack-phase-2b/"
        "serving-bundle-v1/serving_bundle_v1_audit.md",
        "scope: dynamic_pack_phase_4_serving_bundle_v1",
        "---",
        "",
        "# Phase 4 Serving Bundle V1 Audit",
        "",
        f"- status: `{report['status']}`",
        f"- pool_id: `{report['pool_id']}`",
        f"- blockers: `{len(report['blockers'])}`",
        f"- warnings: `{len(report['warnings'])}`",
        "",
        "## Blockers",
        "",
    ]
    lines.extend(f"- `{item}`" for item in report["blockers"] or ["none"])
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- `{item}`" for item in report["warnings"] or ["none"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
