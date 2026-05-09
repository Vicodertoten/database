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
    InaturalistSnapshotManifest,
    SnapshotMediaDownload,
    SnapshotTaxonSeed,
    load_pilot_taxa,
    load_snapshot_manifest,
    write_snapshot_manifest,
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
    snapshot_root: Path = DEFAULT_INAT_SNAPSHOT_ROOT,
    current_database_url: str | None = None,
    max_candidates_per_species: int = PHASE1_MAX_CANDIDATES_PER_SPECIES,
    budget_cap_eur: float = PHASE1_BUDGET_CAP_EUR,
    estimated_cost_per_image_eur: float = PHASE1_ESTIMATED_COST_PER_IMAGE_EUR,
) -> Phase1SelectionResult:
    candidates = _collect_candidates(snapshot_ids=snapshot_ids, snapshot_root=snapshot_root)
    existing_keys = (
        _fetch_existing_media_keys(current_database_url) if current_database_url else set()
    )
    result = select_pre_ai_candidates(
        candidates=candidates,
        existing_media_keys=existing_keys,
        max_candidates_per_species=max_candidates_per_species,
        budget_cap_eur=budget_cap_eur,
        estimated_cost_per_image_eur=estimated_cost_per_image_eur,
    )
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
            f"Output snapshot: `{output_snapshot_id}`",
        ],
    )
    _write_json(output_dir / "gemini_cost_report.json", result.report["budget"])
    return result


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
        if selected_by_taxon[candidate.canonical_taxon_id] >= max_candidates_per_species:
            duplicate_reason_counts["per_taxon_candidate_cap"] += 1
            continue
        keys = _candidate_keys(candidate)
        duplicate_reasons = sorted(
            reason
            for reason, key in keys
            if key[1] and key in seen_keys
        )
        if duplicate_reasons:
            duplicate_reason_counts[duplicate_reasons[0]] += 1
            continue
        selected.append(candidate)
        selected_by_taxon[candidate.canonical_taxon_id] += 1
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
        "selected_candidates_by_taxon": dict(sorted(selected_by_taxon.items())),
        "duplicate_or_blocked_reason_counts": dict(sorted(duplicate_reason_counts.items())),
        "max_candidates_per_species": max_candidates_per_species,
        "budget": budget,
    }
    return Phase1SelectionResult(selected_candidates=selected, report=report)


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
            country_code = _infer_seed_country_code(seed)
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


def _fetch_existing_media_keys(database_url: str) -> set[tuple[str, str]]:
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
    except (psycopg.Error, OSError):
        return keys
    for row in rows:
        if row["source_media_id"]:
            keys.add(("source_media_id", str(row["source_media_id"])))
        if row["source_url"]:
            keys.add(("source_url", _normalize_url(str(row["source_url"]))))
        if row["checksum"]:
            keys.add(("sha256", str(row["checksum"])))
    return keys


def _candidate_keys(candidate: Phase1Candidate) -> list[tuple[str, tuple[str, str]]]:
    return [
        ("duplicate_source_media", ("source_media_id", candidate.source_media_id)),
        ("duplicate_source_url", ("source_url", _normalize_url(candidate.source_url or ""))),
        ("duplicate_sha256", ("sha256", candidate.sha256 or "")),
    ]


def _infer_seed_country_code(seed: SnapshotTaxonSeed) -> str | None:
    country_code = str(seed.query_params.get("country_code") or "").strip().upper()
    if country_code:
        return country_code
    place_id = str(seed.query_params.get("place_id") or "").strip()
    if place_id == PHASE1_FRANCE_INAT_PLACE_ID:
        return "FR"
    if place_id in {"7008", "7083"}:
        return "BE"
    return None


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
