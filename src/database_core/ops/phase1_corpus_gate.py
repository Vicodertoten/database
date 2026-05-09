from __future__ import annotations

import json
import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

from database_core.adapters.inaturalist_snapshot import (
    DEFAULT_INAT_SNAPSHOT_ROOT,
    INAT_PLACE_ID_TO_COUNTRY_CODE,
    InaturalistSnapshotManifest,
    SnapshotMediaDownload,
    SnapshotTaxonSeed,
    load_pilot_taxa,
    load_snapshot_manifest,
    write_snapshot_manifest,
)
from database_core.qualification.ai import (
    AI_REVIEW_CONTRACT_V1_1,
    DEFAULT_GEMINI_PROMPT_VERSION,
)
from database_core.security import redact_database_url
from database_core.storage.services import build_storage_services

PHASE1_REPORT_VERSION = "dynamic_pack_phase1_corpus_gate.v1"
PHASE1_TARGET_COUNTRY_CODES = ("BE", "FR")
PHASE1_FRANCE_INAT_PLACE_ID = "6753"
PHASE1_TARGET_SPECIES_COUNT = 50
PHASE1_TARGET_IMAGES_PER_SPECIES = 20
PHASE1_MAX_CANDIDATES_PER_SPECIES = 60
PHASE1_BUDGET_CAP_EUR = 10.0
PHASE1_ESTIMATED_COST_PER_IMAGE_EUR = 0.0012
PHASE1_MIN_QUESTION_SUCCESS_RATE = 0.99
PHASE1_TARGET_TAXA_PATH = Path(
    "data/fixtures/inaturalist_pilot_taxa_palier1_be_50_run003_v11_baseline.json"
)


@dataclass(frozen=True)
class Phase1Candidate:
    canonical_taxon_id: str
    accepted_scientific_name: str
    source_snapshot_id: str
    source_snapshot_dir: Path
    response_path: str
    taxon_payload_path: str | None
    country_code: str | None
    source_observation_id: str
    source_media_id: str
    source_url: str | None
    sha256: str | None
    image_path: str
    response_result: dict[str, Any]
    media_download: SnapshotMediaDownload
    taxon_seed: SnapshotTaxonSeed


@dataclass(frozen=True)
class Phase1SelectionResult:
    selected_candidates: list[Phase1Candidate]
    report: dict[str, Any]


@dataclass(frozen=True)
class ExistingMediaLookup:
    keys: set[tuple[str, str]]
    report: dict[str, Any]


def estimate_gemini_cost(
    *,
    candidate_count: int,
    estimated_cost_per_image_eur: float = PHASE1_ESTIMATED_COST_PER_IMAGE_EUR,
) -> float:
    return round(candidate_count * estimated_cost_per_image_eur, 6)


def assert_gemini_budget(
    *,
    candidate_count: int,
    budget_cap_eur: float = PHASE1_BUDGET_CAP_EUR,
    estimated_cost_per_image_eur: float = PHASE1_ESTIMATED_COST_PER_IMAGE_EUR,
) -> dict[str, object]:
    estimated_cost = estimate_gemini_cost(
        candidate_count=candidate_count,
        estimated_cost_per_image_eur=estimated_cost_per_image_eur,
    )
    return {
        "candidate_count": candidate_count,
        "estimated_cost_per_image_eur": estimated_cost_per_image_eur,
        "estimated_cost_eur": estimated_cost,
        "budget_cap_eur": budget_cap_eur,
        "within_budget": estimated_cost <= budget_cap_eur,
    }


def resolve_locale_label(
    *,
    common_names_i18n: dict[str, object],
    locale: str,
    scientific_name: str,
) -> str:
    names = common_names_i18n.get(locale)
    if isinstance(names, list):
        for name in names:
            label = str(name or "").strip()
            if label:
                return label
    return scientific_name.strip()


def has_resolved_locale_labels(
    *,
    common_names_i18n: dict[str, object],
    scientific_name: str,
    locales: tuple[str, ...] = ("fr", "en", "nl"),
) -> bool:
    return all(
        bool(
            resolve_locale_label(
                common_names_i18n=common_names_i18n,
                locale=locale,
                scientific_name=scientific_name,
            )
        )
        for locale in locales
    )


def build_preflight_report(
    *,
    phase1_database_url: str,
    current_database_url: str | None = None,
    target_taxa_path: Path = PHASE1_TARGET_TAXA_PATH,
    output_dir: Path,
) -> dict[str, Any]:
    seeds = load_pilot_taxa(target_taxa_path)
    report = {
        "schema_version": PHASE1_REPORT_VERSION,
        "report_type": "preflight",
        "generated_at": _now_iso(),
        "database": {
            "phase1_database_url": redact_database_url(phase1_database_url),
            "current_database_url": (
                redact_database_url(current_database_url) if current_database_url else None
            ),
            "clone_required": True,
            "promotion_allowed": False,
        },
        "scope": {
            "country_codes": list(PHASE1_TARGET_COUNTRY_CODES),
            "france_inat_place_id": PHASE1_FRANCE_INAT_PLACE_ID,
            "target_species_count": PHASE1_TARGET_SPECIES_COUNT,
            "target_images_per_species": PHASE1_TARGET_IMAGES_PER_SPECIES,
            "max_candidates_per_species": PHASE1_MAX_CANDIDATES_PER_SPECIES,
        },
        "gemini_budget": {
            "budget_cap_eur": PHASE1_BUDGET_CAP_EUR,
            "estimated_cost_per_image_eur": PHASE1_ESTIMATED_COST_PER_IMAGE_EUR,
        },
        "target_taxa": [
            {
                "canonical_taxon_id": seed.canonical_taxon_id,
                "accepted_scientific_name": seed.accepted_scientific_name,
                "source_taxon_id": seed.source_taxon_id,
            }
            for seed in seeds
        ],
        "checks": {
            "target_taxa_count": len(seeds),
            "target_taxa_count_ok": len(seeds) == PHASE1_TARGET_SPECIES_COUNT,
            "phase1_database_url_present": bool(phase1_database_url.strip()),
        },
    }
    _write_report_pair(
        output_dir=output_dir,
        json_name="preflight_report.json",
        markdown_name="preflight_report.md",
        payload=report,
        title="Phase 1 Preflight Report",
        summary_lines=[
            f"Target taxa: `{len(seeds)}`",
            f"Scope: `{', '.join(PHASE1_TARGET_COUNTRY_CODES)}`",
            f"Budget cap: `EUR {PHASE1_BUDGET_CAP_EUR}`",
            f"Clone DB: `{redact_database_url(phase1_database_url)}`",
        ],
    )
    return report


def build_pre_ai_selection(
    *,
    snapshot_ids: list[str],
    output_snapshot_id: str,
    output_dir: Path,
    final_input_snapshot_id: str | None = None,
    snapshot_root: Path = DEFAULT_INAT_SNAPSHOT_ROOT,
    current_database_url: str | None = None,
    max_candidates_per_species: int = PHASE1_MAX_CANDIDATES_PER_SPECIES,
    budget_cap_eur: float = PHASE1_BUDGET_CAP_EUR,
    estimated_cost_per_image_eur: float = PHASE1_ESTIMATED_COST_PER_IMAGE_EUR,
) -> Phase1SelectionResult:
    candidates = _collect_candidates(snapshot_ids=snapshot_ids, snapshot_root=snapshot_root)
    existing_lookup = (
        _fetch_existing_media_keys(current_database_url)
        if current_database_url
        else ExistingMediaLookup(
            keys=set(),
            report={
                "enabled": False,
                "status": "skipped",
                "key_count": 0,
                "media_asset_row_count": 0,
            },
        )
    )
    final_input_report = _build_candidate_inventory_report(candidates)
    if final_input_snapshot_id:
        _write_selected_snapshot(
            selected_candidates=candidates,
            output_snapshot_id=final_input_snapshot_id,
            snapshot_root=snapshot_root,
        )
        final_input_report["snapshot_id"] = final_input_snapshot_id
        final_input_report["snapshot_path"] = str(snapshot_root / final_input_snapshot_id)
    result = select_pre_ai_candidates(
        candidates=candidates,
        existing_media_keys=existing_lookup.keys,
        max_candidates_per_species=max_candidates_per_species,
        budget_cap_eur=budget_cap_eur,
        estimated_cost_per_image_eur=estimated_cost_per_image_eur,
    )
    result.report["gemini_worklist_snapshot_id"] = output_snapshot_id
    result.report["final_input_snapshot"] = final_input_report
    result.report["current_db_existing_media_lookup"] = existing_lookup.report
    budget = result.report["budget"]
    if not budget["within_budget"]:
        _write_report_pair(
            output_dir=output_dir,
            json_name="pre_ai_selection_report.json",
            markdown_name="pre_ai_selection_report.md",
            payload=result.report,
            title="Phase 1 Pre-AI Selection Report",
            summary_lines=[
                "Status: `BLOCKED_BUDGET_EXCEEDED`",
                f"Selected candidates: `{len(result.selected_candidates)}`",
                f"Estimated cost: `EUR {budget['estimated_cost_eur']}`",
            ],
        )
        return result

    _write_selected_snapshot(
        selected_candidates=result.selected_candidates,
        output_snapshot_id=output_snapshot_id,
        snapshot_root=snapshot_root,
    )
    result.report["output_snapshot_id"] = output_snapshot_id
    result.report["output_snapshot_path"] = str(snapshot_root / output_snapshot_id)
    _write_report_pair(
        output_dir=output_dir,
        json_name="pre_ai_selection_report.json",
        markdown_name="pre_ai_selection_report.md",
        payload=result.report,
        title="Phase 1 Pre-AI Selection Report",
        summary_lines=[
            "Status: `READY_FOR_GEMINI`",
            f"Selected candidates: `{len(result.selected_candidates)}`",
            f"Estimated cost: `EUR {budget['estimated_cost_eur']}`",
            f"Gemini worklist snapshot: `{output_snapshot_id}`",
            f"Final input snapshot: `{final_input_snapshot_id or 'not written'}`",
        ],
    )
    _write_json(output_dir / "gemini_cost_report.json", result.report["budget"])
    return result


def merge_phase1_ai_outputs(
    *,
    final_input_snapshot_id: str,
    gemini_worklist_snapshot_id: str,
    current_database_url: str,
    output_dir: Path,
    snapshot_root: Path = DEFAULT_INAT_SNAPSHOT_ROOT,
) -> dict[str, Any]:
    final_manifest, final_snapshot_dir = load_snapshot_manifest(
        snapshot_id=final_input_snapshot_id,
        snapshot_root=snapshot_root,
    )
    worklist_manifest, worklist_snapshot_dir = load_snapshot_manifest(
        snapshot_id=gemini_worklist_snapshot_id,
        snapshot_root=snapshot_root,
    )
    if not worklist_manifest.ai_outputs_path:
        raise ValueError(
            "Gemini worklist snapshot has no ai_outputs_path: "
            f"{gemini_worklist_snapshot_id}"
        )
    worklist_ai_outputs_path = worklist_snapshot_dir / worklist_manifest.ai_outputs_path
    worklist_ai_outputs = json.loads(worklist_ai_outputs_path.read_text(encoding="utf-8"))
    if not isinstance(worklist_ai_outputs, dict):
        raise ValueError(f"Invalid ai_outputs payload: {worklist_ai_outputs_path}")

    final_media_ids = {item.source_media_id for item in final_manifest.media_downloads}
    merged_outputs = {
        str(key): value
        for key, value in worklist_ai_outputs.items()
        if _source_media_id_from_ai_output_key(str(key)) in final_media_ids
    }
    missing_media_ids = sorted(
        media_id
        for media_id in final_media_ids
        if f"inaturalist::{media_id}" not in merged_outputs
    )
    cached_outputs = _fetch_cached_ai_outputs_from_current_db(
        database_url=current_database_url,
        source_media_ids=missing_media_ids,
    )
    merged_outputs.update(cached_outputs)

    still_missing_media_ids = sorted(
        media_id
        for media_id in final_media_ids
        if f"inaturalist::{media_id}" not in merged_outputs
    )
    ai_outputs_path = final_snapshot_dir / "ai_outputs.json"
    _write_json(ai_outputs_path, dict(sorted(merged_outputs.items())))
    write_snapshot_manifest(
        final_snapshot_dir,
        final_manifest.model_copy(update={"ai_outputs_path": "ai_outputs.json"}),
    )
    status_counts = Counter(
        str(value.get("status") or "unknown")
        for value in merged_outputs.values()
        if isinstance(value, dict)
    )
    report = {
        "schema_version": PHASE1_REPORT_VERSION,
        "report_type": "ai_outputs_merge",
        "generated_at": _now_iso(),
        "final_input_snapshot_id": final_input_snapshot_id,
        "gemini_worklist_snapshot_id": gemini_worklist_snapshot_id,
        "final_media_count": len(final_media_ids),
        "worklist_ai_outputs_count": len(worklist_ai_outputs),
        "merged_ai_outputs_count": len(merged_outputs),
        "cached_current_db_outputs_count": len(cached_outputs),
        "missing_ai_outputs_count": len(still_missing_media_ids),
        "missing_source_media_ids": still_missing_media_ids,
        "status_counts": dict(sorted(status_counts.items())),
        "ai_outputs_path": str(ai_outputs_path),
        "current_database_url": redact_database_url(current_database_url),
    }
    _write_report_pair(
        output_dir=output_dir,
        json_name="ai_outputs_merge_report.json",
        markdown_name="ai_outputs_merge_report.md",
        payload=report,
        title="Phase 1 AI Outputs Merge Report",
        summary_lines=[
            f"Final media: `{len(final_media_ids)}`",
            f"Merged outputs: `{len(merged_outputs)}`",
            f"Cached DB outputs: `{len(cached_outputs)}`",
            f"Missing outputs: `{len(still_missing_media_ids)}`",
        ],
    )
    return report


def select_pre_ai_candidates(
    *,
    candidates: list[Phase1Candidate],
    existing_media_keys: set[tuple[str, str]],
    max_candidates_per_species: int,
    budget_cap_eur: float = PHASE1_BUDGET_CAP_EUR,
    estimated_cost_per_image_eur: float = PHASE1_ESTIMATED_COST_PER_IMAGE_EUR,
) -> Phase1SelectionResult:
    selected: list[Phase1Candidate] = []
    selected_by_taxon: Counter[str] = Counter()
    seen_keys = set(existing_media_keys)
    duplicate_reason_counts: Counter[str] = Counter()
    raw_by_taxon: Counter[str] = Counter()
    raw_by_country: Counter[str] = Counter()
    selected_by_country: Counter[str] = Counter()
    existing_exclusions_by_taxon: Counter[str] = Counter()
    existing_exclusions_by_country: Counter[str] = Counter()
    internal_duplicate_by_taxon: Counter[str] = Counter()
    internal_duplicate_by_country: Counter[str] = Counter()

    for candidate in sorted(
        candidates,
        key=lambda item: (
            item.canonical_taxon_id,
            item.country_code or "",
            item.source_media_id,
            item.source_observation_id,
        ),
    ):
        raw_by_taxon[candidate.canonical_taxon_id] += 1
        raw_by_country[candidate.country_code or "unknown"] += 1
        if selected_by_taxon[candidate.canonical_taxon_id] >= max_candidates_per_species:
            duplicate_reason_counts["per_taxon_candidate_cap"] += 1
            internal_duplicate_by_taxon[candidate.canonical_taxon_id] += 1
            internal_duplicate_by_country[candidate.country_code or "unknown"] += 1
            continue
        keys = _candidate_keys(candidate)
        existing_duplicate_reasons = sorted(
            reason for reason, key in keys if key[1] and key in existing_media_keys
        )
        if existing_duplicate_reasons:
            duplicate_reason_counts["already_in_current_db"] += 1
            existing_exclusions_by_taxon[candidate.canonical_taxon_id] += 1
            existing_exclusions_by_country[candidate.country_code or "unknown"] += 1
            continue
        internal_duplicate_reasons = sorted(
            reason for reason, key in keys if key[1] and key in seen_keys
        )
        if internal_duplicate_reasons:
            duplicate_reason_counts[internal_duplicate_reasons[0]] += 1
            internal_duplicate_by_taxon[candidate.canonical_taxon_id] += 1
            internal_duplicate_by_country[candidate.country_code or "unknown"] += 1
            continue
        selected.append(candidate)
        selected_by_taxon[candidate.canonical_taxon_id] += 1
        selected_by_country[candidate.country_code or "unknown"] += 1
        seen_keys.update(key for _, key in keys if key[1])

    budget = assert_gemini_budget(
        candidate_count=len(selected),
        budget_cap_eur=budget_cap_eur,
        estimated_cost_per_image_eur=estimated_cost_per_image_eur,
    )
    report = {
        "schema_version": PHASE1_REPORT_VERSION,
        "report_type": "pre_ai_selection",
        "generated_at": _now_iso(),
        "raw_candidates_total": len(candidates),
        "selected_candidates_total": len(selected),
        "raw_candidates_by_taxon": dict(sorted(raw_by_taxon.items())),
        "raw_candidates_by_country": dict(sorted(raw_by_country.items())),
        "selected_candidates_by_taxon": dict(sorted(selected_by_taxon.items())),
        "selected_candidates_by_country": dict(sorted(selected_by_country.items())),
        "duplicate_or_blocked_reason_counts": dict(sorted(duplicate_reason_counts.items())),
        "already_in_current_db_by_taxon": dict(sorted(existing_exclusions_by_taxon.items())),
        "already_in_current_db_by_country": dict(sorted(existing_exclusions_by_country.items())),
        "internal_duplicate_or_blocked_by_taxon": dict(sorted(internal_duplicate_by_taxon.items())),
        "internal_duplicate_or_blocked_by_country": dict(
            sorted(internal_duplicate_by_country.items())
        ),
        "max_candidates_per_species": max_candidates_per_species,
        "budget": budget,
    }
    return Phase1SelectionResult(selected_candidates=selected, report=report)


def _build_candidate_inventory_report(candidates: list[Phase1Candidate]) -> dict[str, Any]:
    by_taxon: Counter[str] = Counter()
    by_country: Counter[str] = Counter()
    by_taxon_country: dict[str, Counter[str]] = {}
    for candidate in candidates:
        country = candidate.country_code or "unknown"
        by_taxon[candidate.canonical_taxon_id] += 1
        by_country[country] += 1
        by_taxon_country.setdefault(candidate.canonical_taxon_id, Counter())[country] += 1
    totals = list(by_taxon.values())
    return {
        "purpose": "phase1_final_input_before_gemini_merge",
        "candidate_count": len(candidates),
        "candidates_by_country": dict(sorted(by_country.items())),
        "candidates_by_taxon": dict(sorted(by_taxon.items())),
        "candidates_by_taxon_country": {
            taxon_id: dict(sorted(counts.items()))
            for taxon_id, counts in sorted(by_taxon_country.items())
        },
        "min_candidates_per_taxon": min(totals) if totals else 0,
        "max_candidates_per_taxon": max(totals) if totals else 0,
        "taxa_with_zero_candidates": PHASE1_TARGET_SPECIES_COUNT - len(by_taxon),
        "taxa_below_target_images": sum(
            1 for count in totals if count < PHASE1_TARGET_IMAGES_PER_SPECIES
        ),
    }


def audit_phase1_corpus_gate(
    *,
    database_url: str,
    output_dir: Path,
    target_taxa_path: Path = PHASE1_TARGET_TAXA_PATH,
    question_generation_success_rate: float | None = None,
) -> dict[str, Any]:
    metrics = _fetch_product_scoped_metrics(
        database_url=database_url,
        target_taxa_path=target_taxa_path,
    )
    question_rate = float(question_generation_success_rate or 0.0)
    gate = evaluate_phase1_gate(metrics=metrics, question_generation_success_rate=question_rate)
    report = {
        "schema_version": PHASE1_REPORT_VERSION,
        "report_type": "final_corpus_gate",
        "generated_at": _now_iso(),
        "database_url": redact_database_url(database_url),
        "scope": {
            "country_codes": list(PHASE1_TARGET_COUNTRY_CODES),
            "target_species_count": PHASE1_TARGET_SPECIES_COUNT,
            "target_images_per_species": PHASE1_TARGET_IMAGES_PER_SPECIES,
            "target_total_images": (
                PHASE1_TARGET_SPECIES_COUNT * PHASE1_TARGET_IMAGES_PER_SPECIES
            ),
        },
        "metrics": metrics,
        "question_generation_success_rate": question_rate,
        "gate": gate,
        "promotion_allowed": gate["status"] in {"GO", "GO_WITH_WARNINGS"},
    }
    _write_report_pair(
        output_dir=output_dir,
        json_name="phase1_corpus_gate_report.json",
        markdown_name="phase1_corpus_gate_summary.md",
        payload=report,
        title="Phase 1 Corpus Gate Summary",
        summary_lines=[
            f"Decision: `{gate['status']}`",
            f"Product items: `{metrics['be_fr_exportable_playable_items']}`",
            f"Covered taxa: `{metrics['be_fr_exportable_playable_taxa']}`",
            f"Question success: `{question_rate}`",
        ],
    )
    return report


def evaluate_phase1_gate(
    *,
    metrics: dict[str, Any],
    question_generation_success_rate: float,
) -> dict[str, Any]:
    target_total = PHASE1_TARGET_SPECIES_COUNT * PHASE1_TARGET_IMAGES_PER_SPECIES
    checks = {
        "target_species_count": {
            "actual": metrics["be_fr_exportable_playable_taxa"],
            "target": f"== {PHASE1_TARGET_SPECIES_COUNT}",
            "pass": metrics["be_fr_exportable_playable_taxa"] == PHASE1_TARGET_SPECIES_COUNT,
        },
        "target_total_images": {
            "actual": metrics["be_fr_exportable_playable_items"],
            "target": f">= {target_total}",
            "pass": metrics["be_fr_exportable_playable_items"] >= target_total,
        },
        "per_taxon_min_images": {
            "actual": metrics["taxa_with_at_least_20_images"],
            "target": f"== {PHASE1_TARGET_SPECIES_COUNT}",
            "pass": metrics["taxa_with_at_least_20_images"] == PHASE1_TARGET_SPECIES_COUNT,
        },
        "zero_image_taxa": {
            "actual": len(metrics["taxa_with_zero_images"]),
            "target": "== 0",
            "pass": len(metrics["taxa_with_zero_images"]) == 0,
        },
        "locale_labels_resolved": {
            "actual": metrics["locale_resolved_counts"],
            "target": "fr/en/nl == product item count",
            "pass": all(
                count == metrics["be_fr_exportable_playable_items"]
                for count in metrics["locale_resolved_counts"].values()
            ),
        },
        "attribution_completeness": {
            "actual": metrics["attribution_completeness"],
            "target": "== 1.0",
            "pass": metrics["attribution_completeness"] == 1.0,
        },
        "country_completeness": {
            "actual": metrics["country_code_completeness"],
            "target": "== 1.0",
            "pass": metrics["country_code_completeness"] == 1.0,
        },
        "question_generation_success_rate": {
            "actual": question_generation_success_rate,
            "target": f">= {PHASE1_MIN_QUESTION_SUCCESS_RATE}",
            "pass": question_generation_success_rate >= PHASE1_MIN_QUESTION_SUCCESS_RATE,
        },
    }
    hard_pass = all(item["pass"] for item in checks.values())
    status = "GO" if hard_pass else "NO_GO"
    return {"status": status, "checks": checks}


def _collect_candidates(
    *,
    snapshot_ids: list[str],
    snapshot_root: Path,
) -> list[Phase1Candidate]:
    candidates: list[Phase1Candidate] = []
    for snapshot_id in snapshot_ids:
        manifest, snapshot_dir = load_snapshot_manifest(
            snapshot_id=snapshot_id,
            snapshot_root=snapshot_root,
        )
        download_by_media_id = {item.source_media_id: item for item in manifest.media_downloads}
        for seed in manifest.taxon_seeds:
            payload = json.loads((snapshot_dir / seed.response_path).read_text(encoding="utf-8"))
            for result in payload.get("results", []):
                if not isinstance(result, dict):
                    continue
                photos = result.get("photos")
                if not isinstance(photos, list) or not photos:
                    continue
                primary = photos[0]
                if not isinstance(primary, dict):
                    continue
                source_media_id = str(primary.get("id") or "").strip()
                download = download_by_media_id.get(source_media_id)
                if download is None or download.download_status != "downloaded":
                    continue
                if not (snapshot_dir / download.image_path).exists():
                    continue
                country_code = _infer_candidate_country_code(result=result, seed=seed)
                response_result = dict(result)
                if country_code and not response_result.get("country_code"):
                    response_result["country_code"] = country_code
                candidates.append(
                    Phase1Candidate(
                        canonical_taxon_id=seed.canonical_taxon_id,
                        accepted_scientific_name=seed.accepted_scientific_name,
                        source_snapshot_id=manifest.snapshot_id,
                        source_snapshot_dir=snapshot_dir,
                        response_path=seed.response_path,
                        taxon_payload_path=seed.taxon_payload_path,
                        country_code=country_code,
                        source_observation_id=str(result.get("id") or ""),
                        source_media_id=source_media_id,
                        source_url=str(
                            primary.get("original_url")
                            or primary.get("large_url")
                            or primary.get("medium_url")
                            or primary.get("url")
                            or download.source_url
                            or ""
                        ),
                        sha256=download.sha256,
                        image_path=download.image_path,
                        response_result=response_result,
                        media_download=download,
                        taxon_seed=seed,
                    )
                )
    return candidates


def _write_selected_snapshot(
    *,
    selected_candidates: list[Phase1Candidate],
    output_snapshot_id: str,
    snapshot_root: Path,
) -> None:
    output_dir = snapshot_root / output_snapshot_id
    if output_dir.exists():
        raise ValueError(f"Output snapshot already exists: {output_dir}")
    (output_dir / "responses").mkdir(parents=True, exist_ok=False)
    (output_dir / "taxa").mkdir(parents=True, exist_ok=True)
    (output_dir / "images").mkdir(parents=True, exist_ok=True)

    candidates_by_taxon: dict[str, list[Phase1Candidate]] = {}
    for candidate in selected_candidates:
        candidates_by_taxon.setdefault(candidate.canonical_taxon_id, []).append(candidate)

    taxon_seeds: list[SnapshotTaxonSeed] = []
    media_downloads: list[SnapshotMediaDownload] = []
    for canonical_taxon_id, taxon_candidates in sorted(candidates_by_taxon.items()):
        first = taxon_candidates[0]
        response_path = Path("responses") / f"{canonical_taxon_id.replace(':', '_')}.json"
        taxon_payload_path = None
        if first.taxon_payload_path:
            source_taxon_path = first.source_snapshot_dir / first.taxon_payload_path
            if source_taxon_path.exists():
                taxon_payload_path = (
                    Path("taxa") / f"{canonical_taxon_id.replace(':', '_')}.json"
                )
                shutil.copy2(source_taxon_path, output_dir / taxon_payload_path)

        query_params = dict(first.taxon_seed.query_params)
        query_params["phase1_source_country_codes"] = ",".join(PHASE1_TARGET_COUNTRY_CODES)
        taxon_seeds.append(
            first.taxon_seed.model_copy(
                update={
                    "response_path": response_path.as_posix(),
                    "taxon_payload_path": taxon_payload_path.as_posix()
                    if taxon_payload_path
                    else None,
                    "query_params": query_params,
                }
            )
        )
        response_payload = {
            "results": [candidate.response_result for candidate in taxon_candidates]
        }
        _write_json(output_dir / response_path, response_payload)

        for candidate in taxon_candidates:
            image_path = Path("images") / Path(candidate.image_path).name
            source_image_path = candidate.source_snapshot_dir / candidate.image_path
            if source_image_path.exists():
                shutil.copy2(source_image_path, output_dir / image_path)
            media_downloads.append(
                candidate.media_download.model_copy(update={"image_path": image_path.as_posix()})
            )

    manifest = InaturalistSnapshotManifest(
        snapshot_id=output_snapshot_id,
        created_at=datetime.now(UTC),
        taxon_seeds=taxon_seeds,
        media_downloads=media_downloads,
        ai_outputs_path=None,
    )
    write_snapshot_manifest(output_dir, manifest)


def _fetch_product_scoped_metrics(
    *,
    database_url: str,
    target_taxa_path: Path,
) -> dict[str, Any]:
    target_taxa = {
        str(seed.canonical_taxon_id): seed.accepted_scientific_name
        for seed in load_pilot_taxa(target_taxa_path)
        if seed.canonical_taxon_id
    }
    services = build_storage_services(database_url)
    with services.database.connect() as connection:
        rows = connection.execute(
            """
            SELECT
                p.canonical_taxon_id,
                p.scientific_name,
                p.common_names_i18n_json,
                p.country_code,
                media.attribution AS media_attribution,
                media.license AS media_license,
                media.source_url AS media_source_url
            FROM playable_items AS p
            JOIN qualified_resources AS q
                ON q.qualified_resource_id = p.qualified_resource_id
               AND q.export_eligible IS TRUE
            LEFT JOIN media_assets AS media
                ON media.media_id = p.media_asset_id
            WHERE p.country_code = ANY(%s)
              AND p.canonical_taxon_id = ANY(%s)
            """,
            [list(PHASE1_TARGET_COUNTRY_CODES), list(target_taxa)],
        ).fetchall()

    counts_by_taxon = Counter(str(row["canonical_taxon_id"]) for row in rows)
    locale_resolved_counts = Counter({"fr": 0, "en": 0, "nl": 0})
    locale_strict_counts = Counter({"fr": 0, "en": 0, "nl": 0})
    attribution_complete = 0
    country_complete = 0
    for row in rows:
        common_names = json.loads(str(row["common_names_i18n_json"]))
        scientific_name = str(row["scientific_name"] or "")
        for locale in ("fr", "en", "nl"):
            strict_names = common_names.get(locale) if isinstance(common_names, dict) else None
            if isinstance(strict_names, list) and any(
                str(name or "").strip() for name in strict_names
            ):
                locale_strict_counts[locale] += 1
            if resolve_locale_label(
                common_names_i18n=common_names if isinstance(common_names, dict) else {},
                locale=locale,
                scientific_name=scientific_name,
            ):
                locale_resolved_counts[locale] += 1
        if row["country_code"]:
            country_complete += 1
        if row["media_attribution"] and row["media_license"] and row["media_source_url"]:
            attribution_complete += 1

    total = len(rows)
    taxa_with_zero = [
        {"canonical_taxon_id": taxon_id, "accepted_scientific_name": scientific_name}
        for taxon_id, scientific_name in target_taxa.items()
        if counts_by_taxon[taxon_id] == 0
    ]
    return {
        "accepted_taxa_total": len(target_taxa),
        "be_fr_exportable_playable_items": total,
        "be_fr_exportable_playable_taxa": len(counts_by_taxon),
        "items_by_taxon": dict(sorted(counts_by_taxon.items())),
        "taxa_with_at_least_20_images": sum(
            1 for count in counts_by_taxon.values() if count >= PHASE1_TARGET_IMAGES_PER_SPECIES
        ),
        "taxa_with_zero_images": taxa_with_zero,
        "locale_resolved_counts": dict(sorted(locale_resolved_counts.items())),
        "locale_strict_counts": dict(sorted(locale_strict_counts.items())),
        "country_code_completeness": _ratio(country_complete, total),
        "attribution_completeness": _ratio(attribution_complete, total),
    }


def _fetch_existing_media_keys(database_url: str) -> ExistingMediaLookup:
    keys: set[tuple[str, str]] = set()
    try:
        services = build_storage_services(database_url)
        with services.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT source_media_id, source_url, checksum
                FROM media_assets
                WHERE source_name = 'inaturalist'
                """
            ).fetchall()
    except (psycopg.Error, OSError) as exc:
        return ExistingMediaLookup(
            keys=keys,
            report={
                "enabled": True,
                "status": "failed",
                "key_count": 0,
                "media_asset_row_count": 0,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
    for row in rows:
        if row["source_media_id"]:
            keys.add(("source_media_id", str(row["source_media_id"])))
        if row["source_url"]:
            keys.add(("source_url", _normalize_url(str(row["source_url"]))))
        if row["checksum"]:
            keys.add(("sha256", str(row["checksum"])))
    return ExistingMediaLookup(
        keys=keys,
        report={
            "enabled": True,
            "status": "ok",
            "key_count": len(keys),
            "media_asset_row_count": len(rows),
        },
    )


def _fetch_cached_ai_outputs_from_current_db(
    *,
    database_url: str,
    source_media_ids: list[str],
) -> dict[str, Any]:
    if not source_media_ids:
        return {}
    services = build_storage_services(database_url)
    with services.database.connect() as connection:
        rows = connection.execute(
            """
            SELECT
                media.source_media_id,
                media.width AS image_width,
                media.height AS image_height,
                q.technical_quality,
                q.pedagogical_quality,
                q.life_stage,
                q.sex,
                q.visible_parts_json,
                q.view_angle,
                q.difficulty_level,
                q.media_role,
                q.confusion_relevance,
                q.diagnostic_feature_visibility,
                q.learning_suitability,
                q.uncertainty_reason,
                q.ai_confidence,
                q.qualification_notes,
                q.qualification_flags_json
            FROM qualified_resources AS q
            JOIN media_assets AS media
                ON media.media_id = q.media_asset_id
            WHERE media.source_name = 'inaturalist'
              AND media.source_media_id = ANY(%s)
            """,
            [source_media_ids],
        ).fetchall()

    outputs: dict[str, Any] = {}
    for row in rows:
        source_media_id = str(row["source_media_id"])
        visible_parts = _json_list(row["visible_parts_json"])
        flags = _json_list(row["qualification_flags_json"])
        qualification = {
            "technical_quality": str(row["technical_quality"]),
            "pedagogical_quality": str(row["pedagogical_quality"]),
            "life_stage": str(row["life_stage"]),
            "sex": str(row["sex"]),
            "visible_parts": visible_parts,
            "view_angle": str(row["view_angle"]),
            "difficulty_level": str(row["difficulty_level"]),
            "media_role": str(row["media_role"]),
            "confusion_relevance": str(row["confusion_relevance"]),
            "diagnostic_feature_visibility": str(row["diagnostic_feature_visibility"]),
            "learning_suitability": str(row["learning_suitability"]),
            "uncertainty_reason": str(row["uncertainty_reason"]),
            "confidence": float(row["ai_confidence"] or 0.0),
            "model_name": "current-db-cached",
            "notes": row["qualification_notes"],
        }
        outputs[f"inaturalist::{source_media_id}"] = {
            "status": "ok",
            "qualification": qualification,
            "flags": flags,
            "note": row["qualification_notes"],
            "model_name": "current-db-cached",
            "prompt_version": DEFAULT_GEMINI_PROMPT_VERSION,
            "review_contract_version": AI_REVIEW_CONTRACT_V1_1,
            "bird_image_pedagogical_review": None,
            "bird_image_pedagogical_score": None,
            "pedagogical_media_profile": None,
            "pedagogical_media_profile_score": None,
            "qualified_at": None,
            "image_width": row["image_width"],
            "image_height": row["image_height"],
        }
    return outputs


def _source_media_id_from_ai_output_key(value: str) -> str:
    if "::" in value:
        return value.rsplit("::", 1)[-1]
    return value


def _json_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        parsed = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed]


def _candidate_keys(candidate: Phase1Candidate) -> list[tuple[str, tuple[str, str]]]:
    return [
        ("duplicate_source_media", ("source_media_id", candidate.source_media_id)),
        ("duplicate_source_url", ("source_url", _normalize_url(candidate.source_url or ""))),
        ("duplicate_sha256", ("sha256", candidate.sha256 or "")),
    ]


def _infer_seed_country_code(seed: SnapshotTaxonSeed) -> str | None:
    country_code = str(seed.query_params.get("country_code") or "").strip().upper()
    if country_code and "," not in country_code:
        return country_code
    place_id = str(seed.query_params.get("place_id") or "").strip()
    if place_id == PHASE1_FRANCE_INAT_PLACE_ID:
        return "FR"
    if place_id in {"7008", "7083"}:
        return "BE"
    return None


def _infer_candidate_country_code(
    *,
    result: dict[str, Any],
    seed: SnapshotTaxonSeed,
) -> str | None:
    explicit = str(result.get("country_code") or "").strip().upper()
    if len(explicit) == 2:
        return explicit

    place_ids = result.get("place_ids")
    if isinstance(place_ids, list):
        for place_id in place_ids:
            mapped = INAT_PLACE_ID_TO_COUNTRY_CODE.get(str(place_id).strip())
            if mapped is not None:
                return mapped

    return _infer_seed_country_code(seed)


def _normalize_url(value: str) -> str:
    return value.strip()


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 6)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_report_pair(
    *,
    output_dir: Path,
    json_name: str,
    markdown_name: str,
    payload: dict[str, Any],
    title: str,
    summary_lines: list[str],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / json_name, payload)
    markdown_lines = [
        "---",
        "owner: database",
        "status: stable",
        "last_reviewed: 2026-05-09",
        f"source_of_truth: {output_dir / markdown_name}",
        "scope: dynamic_pack_phase_1_evidence",
        "---",
        "",
        f"# {title}",
        "",
        *[f"- {line}" for line in summary_lines],
        "",
        f"JSON evidence: `{json_name}`",
    ]
    (output_dir / markdown_name).write_text("\n".join(markdown_lines) + "\n", encoding="utf-8")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
