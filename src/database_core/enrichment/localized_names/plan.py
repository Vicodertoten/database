from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from database_core.enrichment.localized_names.evidence import collect_name_evidence, load_json
from database_core.enrichment.localized_names.models import (
    LocalizedNameApplyPlan,
    LocalizedNameReviewItem,
    NameDecision,
    RuntimeTaxon,
)
from database_core.enrichment.localized_names.normalization import (
    normalize_name_map,
)
from database_core.enrichment.localized_names.resolver import decision_is_displayable, resolve_taxa

SCHEMA_VERSION = "localized_name_apply_plan_v1"
REPO_ROOT = Path(__file__).resolve().parents[4]

DEFAULT_PLAN_JSON = Path("docs/audits/evidence/localized_name_apply_plan_v1.json")
DEFAULT_REQUIRED_REVIEW_JSON = Path(
    "docs/audits/evidence/localized_name_review_queue_required_v1.json"
)
DEFAULT_OPTIONAL_REPORT_JSON = Path(
    "docs/audits/evidence/localized_name_optional_coverage_report_v1.json"
)
DEFAULT_REQUIRED_REVIEW_MD = Path("docs/audits/localized-name-review-queue-required-v1.md")
DEFAULT_OPTIONAL_REPORT_MD = Path("docs/audits/localized-name-optional-coverage-report-v1.md")

DEFAULT_CANONICAL_PATCHED = Path(
    "data/enriched/taxon_localized_names_v1/canonical_taxa_patched.json"
)
DEFAULT_REFERENCED_PATCHED = Path(
    "data/enriched/taxon_localized_names_v1/referenced_taxa_patched.json"
)
DEFAULT_SHELL_PLAN = Path("docs/audits/evidence/referenced_taxon_shell_apply_plan_sprint13.json")
DEFAULT_PROJECTED_REL = Path(
    "docs/audits/evidence/distractor_relationships_v1_projected_sprint13.json"
)
DEFAULT_READINESS = Path("docs/audits/evidence/distractor_readiness_v1_sprint13.json")
DEFAULT_ALL_NAMES_DIR = Path("data/enriched/palier1-be-birds-50taxa-run003-v11-baseline/all_names")
DEFAULT_FETCH_CACHE_DIR = Path("docs/audits/evidence/fetch_cache")


def _root(root: Path | None) -> Path:
    return root or REPO_ROOT


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_json_if_exists(path: Path, default: Any) -> Any:
    return load_json(path) if path.exists() else default


def _canonical_taxa(path: Path) -> list[RuntimeTaxon]:
    payload = _load_json_if_exists(path, {"canonical_taxa": []})
    taxa: list[RuntimeTaxon] = []
    for item in payload.get("canonical_taxa", []):
        if not isinstance(item, dict):
            continue
        taxon_id = str(item.get("canonical_taxon_id", "")).strip()
        scientific_name = str(
            item.get("scientific_name") or item.get("accepted_scientific_name") or ""
        ).strip()
        if not taxon_id or not scientific_name:
            continue
        names = normalize_name_map(
            item.get("common_names_i18n") or item.get("common_names_by_language") or {}
        )
        source_taxon_id = None
        profile = item.get("authority_taxonomy_profile") or {}
        if isinstance(profile, dict) and profile.get("source_taxon_id"):
            source_taxon_id = str(profile.get("source_taxon_id"))
        taxa.append(
            RuntimeTaxon(
                taxon_kind="canonical_taxon",
                taxon_id=taxon_id,
                scientific_name=scientific_name,
                existing_names=names,
                source_taxon_id=source_taxon_id,
                is_active=_coerce_bool(profile.get("is_active"))
                if isinstance(profile, dict)
                else True,
                rank=str(item.get("canonical_rank") or item.get("rank") or "") or None,
                runtime_relevant=True,
            )
        )
    return taxa


def _referenced_taxa(path: Path) -> list[RuntimeTaxon]:
    payload = _load_json_if_exists(path, {"referenced_taxa": []})
    taxa: list[RuntimeTaxon] = []
    for item in payload.get("referenced_taxa", []):
        if not isinstance(item, dict):
            continue
        taxon_id = str(item.get("referenced_taxon_id", "")).strip()
        scientific_name = str(item.get("scientific_name", "")).strip()
        if not taxon_id or not scientific_name:
            continue
        taxa.append(
            RuntimeTaxon(
                taxon_kind="referenced_taxon",
                taxon_id=taxon_id,
                scientific_name=scientific_name,
                existing_names=normalize_name_map(item.get("common_names_i18n") or {}),
                source_taxon_id=str(item.get("source_taxon_id") or "").strip() or None,
                is_active=True,
                rank=str(item.get("rank") or "").strip() or None,
                runtime_relevant=True,
            )
        )
    return taxa


def _coerce_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _shell_taxa(path: Path, existing: dict[tuple[str, str], RuntimeTaxon]) -> list[RuntimeTaxon]:
    payload = _load_json_if_exists(path, {"apply_records": []})
    taxa: list[RuntimeTaxon] = []
    for item in payload.get("apply_records", []):
        if not isinstance(item, dict):
            continue
        taxon_id = str(item.get("proposed_referenced_taxon_id", "")).strip()
        if not taxon_id or ("referenced_taxon", taxon_id) in existing:
            continue
        scientific_name = str(item.get("scientific_name", "")).strip()
        if not scientific_name:
            continue
        taxa.append(
            RuntimeTaxon(
                taxon_kind="referenced_taxon",
                taxon_id=taxon_id,
                scientific_name=scientific_name,
                existing_names=normalize_name_map(item.get("common_names_i18n") or {}),
                source_taxon_id=str(item.get("source_taxon_id") or "").strip() or None,
            )
        )
    return taxa


def load_runtime_taxa(root: Path | None = None) -> list[RuntimeTaxon]:
    base = _root(root)
    taxa = _canonical_taxa(base / DEFAULT_CANONICAL_PATCHED)
    taxa.extend(_referenced_taxa(base / DEFAULT_REFERENCED_PATCHED))
    existing = {(taxon.taxon_kind, taxon.taxon_id): taxon for taxon in taxa}
    taxa.extend(_shell_taxa(base / DEFAULT_SHELL_PLAN, existing))
    return sorted(taxa, key=lambda item: (item.taxon_kind, item.taxon_id))


def load_relationship_context(
    root: Path | None = None,
) -> tuple[set[str], dict[str, list[tuple[str, str]]]]:
    base = _root(root)
    readiness = _load_json_if_exists(base / DEFAULT_READINESS, {"per_target_readiness": []})
    ready_targets = {
        str(row.get("target_canonical_taxon_id", "")).strip()
        for row in readiness.get("per_target_readiness", [])
        if str(row.get("readiness_status", "")).strip() == "ready_for_first_corpus_distractor_gate"
    }
    projected = _load_json_if_exists(base / DEFAULT_PROJECTED_REL, {"projected_records": []})
    target_candidates: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in projected.get("projected_records", []):
        if str(row.get("status", "")).strip() != "candidate":
            continue
        target_id = str(row.get("target_canonical_taxon_id", "")).strip()
        kind = str(row.get("candidate_taxon_ref_type", "")).strip()
        taxon_id = str(row.get("candidate_taxon_ref_id", "")).strip()
        if target_id and kind in {"canonical_taxon", "referenced_taxon"} and taxon_id:
            target_candidates[target_id].append((kind, taxon_id))
    return ready_targets, target_candidates


def _review_item(decision: NameDecision) -> LocalizedNameReviewItem:
    return LocalizedNameReviewItem(
        taxon_kind=decision.taxon_kind,
        taxon_id=decision.taxon_id,
        scientific_name=decision.scientific_name,
        locale=decision.locale,
        reason=decision.reason,
        existing_value=decision.existing_value,
        candidates=decision.evidence,
    )


def _plan_hash(items: list[NameDecision]) -> str:
    canonical = [
        {
            "taxon_kind": item.taxon_kind,
            "taxon_id": item.taxon_id,
            "locale": item.locale,
            "existing_value": item.existing_value,
            "decision": item.decision,
            "chosen_value": item.chosen_value,
            "reason": item.reason,
            "source_identity": item.source_identity,
            "source_value": item.source_value,
        }
        for item in sorted(items, key=lambda i: (i.taxon_kind, i.taxon_id, i.locale))
    ]
    encoded = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _metrics(
    items: list[NameDecision],
    ready_targets: set[str],
    target_candidates: dict[str, list[tuple[str, str]]],
) -> dict[str, Any]:
    by_locale = Counter(item.locale for item in items)
    by_decision = Counter(item.decision for item in items)
    by_reason = Counter(item.reason for item in items)
    displayable_fr = {
        (item.taxon_kind, item.taxon_id)
        for item in items
        if item.locale == "fr" and decision_is_displayable(item)
    }
    safe_ready_targets = sorted(
        target_id
        for target_id in ready_targets
        if sum(
            1 for candidate in target_candidates.get(target_id, []) if candidate in displayable_fr
        )
        >= 3
    )
    return {
        "total_items": len(items),
        "by_locale": dict(by_locale),
        "by_decision": dict(by_decision),
        "by_reason": dict(by_reason),
        "ready_target_count": len(ready_targets),
        "safe_ready_target_count_from_plan": len(safe_ready_targets),
        "safe_ready_targets_from_plan": safe_ready_targets,
        "first_corpus_minimum_target_count": 30,
    }


def build_localized_name_apply_plan(root: Path | None = None) -> LocalizedNameApplyPlan:
    base = _root(root)
    taxa = load_runtime_taxa(base)
    evidences = collect_name_evidence(
        taxa,
        all_names_dir=base / DEFAULT_ALL_NAMES_DIR,
        fetch_cache_dir=base / DEFAULT_FETCH_CACHE_DIR,
    )
    items = resolve_taxa(taxa, evidences)
    ready_targets, target_candidates = load_relationship_context(base)
    required_review = tuple(
        _review_item(item)
        for item in items
        if item.locale in {"fr", "en"} and item.decision in {"needs_review", "evidence_only"}
    )
    optional_gaps = tuple(
        _review_item(item)
        for item in items
        if item.locale == "nl"
        and item.decision in {"skip_optional_missing", "needs_review", "evidence_only"}
    )
    config = {
        "required_locales": ["fr", "en"],
        "optional_locales": ["nl"],
        "allow_scientific_fallback_for_missing_common_name": False,
        "source_order": [
            "inaturalist_preferred",
            "inaturalist_all_names",
            "wikipedia_langlinks",
            "wikidata_labels",
            "review_queue",
        ],
    }
    return LocalizedNameApplyPlan(
        schema_version=SCHEMA_VERSION,
        generated_at=datetime.now(UTC).isoformat(),
        config=config,
        plan_hash=_plan_hash(items),
        items=tuple(items),
        review_items_required=required_review,
        optional_coverage_gaps=optional_gaps,
        metrics=_metrics(items, ready_targets, target_candidates),
    )


def write_plan_artifacts(plan: LocalizedNameApplyPlan, root: Path | None = None) -> None:
    base = _root(root)
    write_json(base / DEFAULT_PLAN_JSON, plan.to_dict())
    write_json(
        base / DEFAULT_REQUIRED_REVIEW_JSON,
        {
            "schema_version": "localized_name_review_queue_required_v1",
            "plan_hash": plan.plan_hash,
            "items": [item.to_dict() for item in plan.review_items_required],
        },
    )
    write_json(
        base / DEFAULT_OPTIONAL_REPORT_JSON,
        {
            "schema_version": "localized_name_optional_coverage_report_v1",
            "plan_hash": plan.plan_hash,
            "items": [item.to_dict() for item in plan.optional_coverage_gaps],
        },
    )
    _write_review_markdown(base / DEFAULT_REQUIRED_REVIEW_MD, plan, required=True)
    _write_review_markdown(base / DEFAULT_OPTIONAL_REPORT_MD, plan, required=False)


def _write_review_markdown(path: Path, plan: LocalizedNameApplyPlan, *, required: bool) -> None:
    items = plan.review_items_required if required else plan.optional_coverage_gaps
    title = (
        "Localized Name Required Review Queue"
        if required
        else "Localized Name Optional Coverage Report"
    )
    reason_counts = Counter(item.reason for item in items)
    lines = [
        "---",
        "owner: database",
        "status: ready_for_validation",
        f"last_reviewed: {plan.generated_at[:10]}",
        f"source_of_truth: {path.as_posix()}",
        "scope: sprint14b_localized_names",
        "---",
        "",
        f"# {title}",
        "",
        f"- plan_hash: {plan.plan_hash}",
        f"- item_count: {len(items)}",
        "",
        "## Reasons",
        "",
    ]
    for reason, count in sorted(reason_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- {reason}: {count}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_plan(path: Path) -> dict[str, Any]:
    return load_json(path)


def apply_plan_to_taxa(
    plan: LocalizedNameApplyPlan,
    canonical_taxa: list[dict[str, Any]],
    referenced_taxa: list[dict[str, Any]],
) -> dict[str, Any]:
    canonical_work = [dict(item) for item in canonical_taxa]
    referenced_work = [dict(item) for item in referenced_taxa]
    by_key = {
        ("canonical_taxon", str(item.get("canonical_taxon_id", "")).strip()): item
        for item in canonical_work
        if item.get("canonical_taxon_id")
    }
    by_key.update(
        {
            ("referenced_taxon", str(item.get("referenced_taxon_id", "")).strip()): item
            for item in referenced_work
            if item.get("referenced_taxon_id")
        }
    )
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in plan.items:
        if item.decision != "auto_accept" or not item.chosen_value:
            continue
        target = by_key.get((item.taxon_kind, item.taxon_id))
        if target is None:
            skipped.append(
                {"taxon_id": item.taxon_id, "locale": item.locale, "reason": "target_not_found"}
            )
            continue
        names = normalize_name_map(target.get("common_names_i18n") or {})
        names[item.locale] = [item.chosen_value]
        target["common_names_i18n"] = names
        applied.append(
            {
                "taxon_kind": item.taxon_kind,
                "taxon_id": item.taxon_id,
                "locale": item.locale,
                "value": item.chosen_value,
                "reason": item.reason,
            }
        )
    return {
        "canonical_taxa": canonical_work,
        "referenced_taxa": referenced_work,
        "applied": applied,
        "skipped": skipped,
    }


def write_backward_compatible_csvs(plan: LocalizedNameApplyPlan, root: Path | None = None) -> None:
    base = _root(root)
    review_csv = base / "data/manual/taxon_localized_name_multisource_review_queue_sprint14.csv"
    patch_csv = base / "data/manual/taxon_localized_name_source_attested_patches_sprint14.csv"
    review_csv.parent.mkdir(parents=True, exist_ok=True)
    with review_csv.open("w", encoding="utf-8", newline="") as f:
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
        for item in plan.items:
            writer.writerow(_legacy_review_row(item))
    with patch_csv.open("w", encoding="utf-8", newline="") as f:
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
        for item in plan.items:
            if item.decision in {"auto_accept", "same_value"} and item.chosen_value:
                writer.writerow(
                    {
                        "taxon_id": item.taxon_id,
                        "taxon_kind": item.taxon_kind,
                        "scientific_name": item.scientific_name,
                        "language": item.locale,
                        "common_name": item.chosen_value,
                        "source": item.source_identity or "manual_or_curated_existing",
                        "source_priority": 1,
                        "confidence": "source_attested"
                        if item.decision == "auto_accept"
                        else "high",
                        "display_status": "displayable_source_attested"
                        if item.decision == "auto_accept"
                        else "displayable_curated",
                        "reviewer": "system/source_policy"
                        if item.decision == "auto_accept"
                        else "",
                        "notes": "source-attested by localized-name-apply-plan-v1",
                        "apply_status": "ready",
                    }
                )


def _legacy_review_row(item: NameDecision) -> dict[str, Any]:
    display_status = "not_displayable_missing"
    recommendation = "not_for_corpus_display_missing"
    if item.decision == "auto_accept":
        display_status = "displayable_source_attested"
        recommendation = "apply_source_attested_name"
    elif item.decision == "same_value":
        display_status = "displayable_curated"
        recommendation = "keep_existing_curated"
    elif item.reason == "scientific_fallback":
        display_status = "not_displayable_scientific_fallback"
        recommendation = "not_for_corpus_display_scientific_fallback"
    elif item.reason.startswith("existing_value_conflict"):
        display_status = "needs_review_conflict"
        recommendation = "needs_human_review_conflict"
    return {
        "priority": "P1" if item.locale in {"fr", "en"} else "P3",
        "taxon_id": item.taxon_id,
        "taxon_kind": item.taxon_kind,
        "scientific_name": item.scientific_name,
        "language": item.locale,
        "existing_name": item.existing_value or "",
        "selected_candidate_name": item.chosen_value or item.source_value or "",
        "selected_source": item.source_identity or "",
        "selected_source_priority": 1,
        "display_status": display_status,
        "recommendation": recommendation,
        "conflict_status": "curated_conflict"
        if item.reason.startswith("existing_value_conflict")
        else "none",
        "alternatives": " | ".join(
            f"{alt.source_identity}:{alt.value}" for alt in item.alternatives
        ),
        "affected_target_count": 0,
        "affected_ready_target_count": 0,
        "relationship_occurrence_count": 0,
        "projected_unlock_value": 0,
        "reviewer": "",
        "reviewed_name": "",
        "review_confidence": "",
        "review_source": "",
        "review_notes": "",
        "apply_status": "pending",
    }
