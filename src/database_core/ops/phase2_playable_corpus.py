from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from database_core.adapters import (
    DEFAULT_INAT_SNAPSHOT_ROOT,
    fetch_inat_snapshot,
    qualify_inat_snapshot,
)
from database_core.ops.smoke_report import generate_smoke_report
from database_core.pipeline.runner import run_pipeline
from database_core.security import redact_database_url
from database_core.storage.services import build_storage_services

PHASE2_REPORT_VERSION = "phase2.playable_corpus.v1"
PHASE2_TARGET_COUNTRY_CODE = "BE"
PHASE2_TARGET_SPECIES_COUNT = 50
PHASE2_MIN_IMAGES_PER_SPECIES = 10
PHASE2_MAX_IMAGES_PER_SPECIES = 30
PHASE2_MIN_QUESTION_SUCCESS_RATE = 0.99
PHASE2_REQUIRED_COMPLETENESS = 1.0
PHASE2_DEFAULT_MAX_OBSERVATIONS_PER_TAXON = 30
PHASE2_DEFAULT_MAX_ATTEMPTS = 3
PHASE2_DEFAULT_QUESTION_ATTEMPTS = 10
PHASE2_DEFAULT_QUESTION_COUNT = 20
PHASE2_DEFAULT_OUTPUT_DIR = Path("docs/archive/evidence") / datetime.now(UTC).strftime("%Y-%m")
PHASE2_DEFAULT_PILOT_TAXA_PATH = Path("data/fixtures/birds_pilot_v2.json")


@dataclass(frozen=True)
class Phase2Thresholds:
    target_country_code: str | None = PHASE2_TARGET_COUNTRY_CODE
    target_species_count: int = PHASE2_TARGET_SPECIES_COUNT
    min_images_per_species: int = PHASE2_MIN_IMAGES_PER_SPECIES
    max_images_per_species: int = PHASE2_MAX_IMAGES_PER_SPECIES
    min_question_success_rate: float = PHASE2_MIN_QUESTION_SUCCESS_RATE
    required_common_name_fr_completeness: float = PHASE2_REQUIRED_COMPLETENESS
    required_country_code_completeness: float = PHASE2_REQUIRED_COMPLETENESS
    required_attribution_completeness: float = PHASE2_REQUIRED_COMPLETENESS


@dataclass(frozen=True)
class HarvestProfile:
    order_by: str
    order: str
    observed_from: str | None
    observed_to: str | None
    max_observations_per_taxon: int


def evaluate_phase2_gate(
    *,
    metrics: dict[str, Any],
    thresholds: Phase2Thresholds,
) -> dict[str, Any]:
    country_scope_enabled = bool(thresholds.target_country_code)
    checks = {
        "species_count": {
            "actual": int(metrics["species_count"]),
            "target": f">= {thresholds.target_species_count}",
            "pass": int(metrics["species_count"]) >= thresholds.target_species_count,
        },
        "species_with_min_images": {
            "actual": int(metrics["species_with_min_images"]),
            "target": f">= {thresholds.target_species_count}",
            "pass": int(metrics["species_with_min_images"]) >= thresholds.target_species_count,
        },
        "common_name_fr_effective_completeness": {
            "actual": float(metrics["common_name_fr_effective_completeness"]),
            "target": f">= {thresholds.required_common_name_fr_completeness}",
            "pass": float(metrics["common_name_fr_effective_completeness"])
            >= thresholds.required_common_name_fr_completeness,
        },
        "country_code_completeness": {
            "actual": float(metrics["country_code_completeness"]),
            "target": (
                f">= {thresholds.required_country_code_completeness}"
                if country_scope_enabled
                else "n/a (global scope)"
            ),
            "pass": (
                float(metrics["country_code_completeness"])
                >= thresholds.required_country_code_completeness
                if country_scope_enabled
                else True
            ),
        },
        "question_generation_success_rate": {
            "actual": float(metrics["question_generation_success_rate"]),
            "target": f">= {thresholds.min_question_success_rate}",
            "pass": float(metrics["question_generation_success_rate"])
            >= thresholds.min_question_success_rate,
        },
        "attribution_completeness": {
            "actual": float(metrics["attribution_completeness"]),
            "target": f">= {thresholds.required_attribution_completeness}",
            "pass": float(metrics["attribution_completeness"])
            >= thresholds.required_attribution_completeness,
        },
    }
    gate_status = "GO" if all(item["pass"] for item in checks.values()) else "NO_GO"
    return {
        "status": gate_status,
        "checks": checks,
    }


def recommend_phase2_strategy(
    *,
    metrics: dict[str, Any],
    thresholds: Phase2Thresholds,
) -> dict[str, str]:
    items_total = int(metrics["playable_items_total"])
    species_count = int(metrics["species_count"])
    species_with_min_images = int(metrics["species_with_min_images"])

    if items_total == 0:
        return {
            "strategy": "reconstruction",
            "database_posture": "clean_start_recommended",
            "rationale": "No active playable corpus was found in the target database.",
        }

    if species_with_min_images < max(1, thresholds.target_species_count // 2):
        return {
            "strategy": "reconstruction",
            "database_posture": "clean_start_recommended",
            "rationale": (
                "Current corpus density is too low on the target segment; a targeted rebuild "
                "is faster than patching sparse runs."
            ),
        }

    if species_count >= thresholds.target_species_count:
        return {
            "strategy": "reuse_and_complete",
            "database_posture": "reuse_with_remediation",
            "rationale": (
                "Species coverage exists, but density/completeness gates still require "
                "targeted remediation."
            ),
        }

    return {
        "strategy": "reuse_and_expand",
        "database_posture": "reuse_with_expansion",
        "rationale": "A partial corpus exists and can be expanded to reach phase 2 targets.",
    }


def run_phase2_playable_corpus(
    *,
    database_url: str,
    gemini_api_key: str,
    pilot_taxa_path: Path = PHASE2_DEFAULT_PILOT_TAXA_PATH,
    snapshot_root: Path = DEFAULT_INAT_SNAPSHOT_ROOT,
    output_dir: Path = PHASE2_DEFAULT_OUTPUT_DIR,
    thresholds: Phase2Thresholds | None = None,
    max_attempts: int = PHASE2_DEFAULT_MAX_ATTEMPTS,
    question_attempts: int = PHASE2_DEFAULT_QUESTION_ATTEMPTS,
    question_count: int = PHASE2_DEFAULT_QUESTION_COUNT,
    run_rebuild: bool = True,
) -> dict[str, Any]:
    if thresholds is None:
        thresholds = Phase2Thresholds()

    output_dir.mkdir(parents=True, exist_ok=True)
    services = build_storage_services(database_url)
    services.database.initialize()

    initial_metrics = _collect_phase2_metrics(
        services=services,
        thresholds=thresholds,
        question_attempts=question_attempts,
        question_count=question_count,
        run_label="baseline",
    )
    initial_strategy = recommend_phase2_strategy(metrics=initial_metrics, thresholds=thresholds)
    attempts: list[dict[str, Any]] = []

    if run_rebuild:
        profiles = _build_harvest_profiles(max_attempts=max_attempts)
        run_timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        target_seed_path = (
            output_dir / f"phase2_target_taxa_top{thresholds.target_species_count}.json"
        )
        selected_seed_ids = _materialize_target_seed_file(
            pilot_taxa_path=pilot_taxa_path,
            output_path=target_seed_path,
            target_species_count=thresholds.target_species_count,
        )

        for attempt_index, profile in enumerate(profiles, start=1):
            snapshot_id = f"phase2-birds-be-{run_timestamp}-a{attempt_index}"
            fetch_result = fetch_inat_snapshot(
                snapshot_id=snapshot_id,
                snapshot_root=snapshot_root,
                pilot_taxa_path=target_seed_path,
                max_observations_per_taxon=profile.max_observations_per_taxon,
                country_code=thresholds.target_country_code,
                observed_from=profile.observed_from,
                observed_to=profile.observed_to,
                order_by=profile.order_by,
                order=profile.order,
            )
            qualification_result = qualify_inat_snapshot(
                snapshot_id=snapshot_id,
                snapshot_root=snapshot_root,
                gemini_api_key=gemini_api_key,
            )
            pipeline_result = run_pipeline(
                source_mode="inat_snapshot",
                snapshot_id=snapshot_id,
                snapshot_root=snapshot_root,
                database_url=database_url,
                qualifier_mode="cached",
                uncertain_policy="reject",
                normalized_snapshot_path=Path("data/normalized") / f"{snapshot_id}.json",
                qualification_snapshot_path=Path("data/qualified") / f"{snapshot_id}.json",
                export_path=Path("data/exports") / f"{snapshot_id}.json",
            )
            metrics_after_attempt = _collect_phase2_metrics(
                services=services,
                thresholds=thresholds,
                question_attempts=question_attempts,
                question_count=question_count,
                run_label=f"attempt_{attempt_index}",
                selected_seed_ids=selected_seed_ids,
            )
            gate_after_attempt = evaluate_phase2_gate(
                metrics=metrics_after_attempt,
                thresholds=thresholds,
            )
            attempts.append(
                {
                    "attempt_index": attempt_index,
                    "snapshot_id": snapshot_id,
                    "harvest_profile": {
                        "order_by": profile.order_by,
                        "order": profile.order,
                        "observed_from": profile.observed_from,
                        "observed_to": profile.observed_to,
                        "max_observations_per_taxon": profile.max_observations_per_taxon,
                    },
                    "fetch": {
                        "harvested_observation_count": fetch_result.harvested_observation_count,
                        "downloaded_image_count": fetch_result.downloaded_image_count,
                    },
                    "qualification": {
                        "processed_media_count": qualification_result.processed_media_count,
                        "images_sent_to_gemini_count": (
                            qualification_result.images_sent_to_gemini_count
                        ),
                        "ai_valid_output_count": qualification_result.ai_valid_output_count,
                        "insufficient_resolution_count": (
                            qualification_result.insufficient_resolution_count
                        ),
                        "pre_ai_rejection_count": qualification_result.pre_ai_rejection_count,
                    },
                    "pipeline": {
                        "run_id": pipeline_result.run_id,
                        "qualified_resource_count": pipeline_result.qualified_resource_count,
                        "exportable_resource_count": pipeline_result.exportable_resource_count,
                        "review_queue_count": pipeline_result.review_queue_count,
                        "normalized_snapshot_path": str(pipeline_result.normalized_snapshot_path),
                        "qualification_snapshot_path": str(
                            pipeline_result.qualification_snapshot_path
                        ),
                        "export_path": str(pipeline_result.export_path),
                    },
                    "metrics": metrics_after_attempt,
                    "gate": gate_after_attempt,
                }
            )
            if gate_after_attempt["status"] == "GO":
                break

    final_metrics = (
        attempts[-1]["metrics"]
        if attempts
        else initial_metrics
    )
    final_gate = evaluate_phase2_gate(metrics=final_metrics, thresholds=thresholds)
    final_strategy = recommend_phase2_strategy(metrics=final_metrics, thresholds=thresholds)

    smoke_report = generate_smoke_report(
        services.pipeline_store,
        snapshot_id=None,
        database_url=database_url,
    )

    summary = {
        "schema_version": PHASE2_REPORT_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "database_url": redact_database_url(database_url),
        "thresholds": {
            "target_country_code": thresholds.target_country_code,
            "target_species_count": thresholds.target_species_count,
            "min_images_per_species": thresholds.min_images_per_species,
            "max_images_per_species": thresholds.max_images_per_species,
            "min_question_success_rate": thresholds.min_question_success_rate,
            "required_common_name_fr_completeness": (
                thresholds.required_common_name_fr_completeness
            ),
            "required_country_code_completeness": thresholds.required_country_code_completeness,
            "required_attribution_completeness": thresholds.required_attribution_completeness,
        },
        "initial_analysis": {
            "metrics": initial_metrics,
            "strategy": initial_strategy,
        },
        "execution": {
            "run_rebuild": run_rebuild,
            "attempts": attempts,
        },
        "final_analysis": {
            "metrics": final_metrics,
            "strategy": final_strategy,
            "gate": final_gate,
            "phase2_closed": final_gate["status"] == "GO",
        },
        "smoke_report": smoke_report,
    }

    summary_path = output_dir / "phase2_playable_corpus_report.v1.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary["output_path"] = str(summary_path)
    return summary


def _collect_phase2_metrics(
    *,
    services,
    thresholds: Phase2Thresholds,
    question_attempts: int,
    question_count: int,
    run_label: str,
    selected_seed_ids: list[str] | None = None,
) -> dict[str, Any]:
    playable_items = services.playable_store.fetch_playable_corpus(limit=200000)
    scoped_items = _scope_items_to_country(
        playable_items,
        country_code=thresholds.target_country_code,
    )
    canonical_counter = Counter(
        str(item.get("canonical_taxon_id") or "")
        for item in scoped_items
        if str(item.get("canonical_taxon_id") or "")
    )
    species_count = len(canonical_counter)
    species_with_min_images = sum(
        1 for count in canonical_counter.values() if count >= thresholds.min_images_per_species
    )
    species_within_range = sum(
        1
        for count in canonical_counter.values()
        if thresholds.min_images_per_species <= count <= thresholds.max_images_per_species
    )
    species_above_max_images = sum(
        1 for count in canonical_counter.values() if count > thresholds.max_images_per_species
    )
    images_per_species = dict(sorted(canonical_counter.items()))

    playable_items_total = len(scoped_items)
    strict_fr_non_empty_count = 0
    effective_fr_non_empty_count = 0
    country_code_non_empty_count = 0
    attribution_complete_count = 0
    required_contract_fields = {
        "playable_item_id": 0,
        "canonical_taxon_id": 0,
        "scientific_name": 0,
        "difficulty_level": 0,
        "feedback_short": 0,
        "similar_taxon_ids": 0,
        "country_code": 0,
        "observed_at": 0,
        "media_render_url": 0,
        "media_attribution": 0,
        "media_license": 0,
        "source_name": 0,
    }

    playable_by_id: dict[str, dict[str, Any]] = {}
    for item in scoped_items:
        playable_item_id = str(item.get("playable_item_id") or "")
        if playable_item_id:
            playable_by_id[playable_item_id] = item
        for field_name in required_contract_fields:
            if item.get(field_name) not in (None, "", []):
                required_contract_fields[field_name] += 1

        common_names = item.get("common_names_i18n") or {}
        fr_names = common_names.get("fr") if isinstance(common_names, dict) else None
        if fr_names:
            strict_fr_non_empty_count += 1

        if _resolve_effective_common_name_fr(item):
            effective_fr_non_empty_count += 1

        if item.get("country_code"):
            country_code_non_empty_count += 1

        if (
            item.get("media_render_url")
            and item.get("media_attribution")
            and item.get("media_license")
            and item.get("source_name")
        ):
            attribution_complete_count += 1

    qualified_stats = _fetch_qualification_stats(services=services)
    question_validation = _measure_question_generation(
        services=services,
        canonical_taxon_counts=canonical_counter,
        playable_by_id=playable_by_id,
        question_attempts=question_attempts,
        question_count=question_count,
        run_label=run_label,
        target_country_code=thresholds.target_country_code,
        selected_seed_ids=selected_seed_ids,
    )

    return {
        "playable_items_total": playable_items_total,
        "species_count": species_count,
        "species_with_min_images": species_with_min_images,
        "species_within_10_to_30_images": species_within_range,
        "species_above_30_images": species_above_max_images,
        "species_with_min_images_rate": _ratio(species_with_min_images, species_count),
        "images_per_species": images_per_species,
        "qualified_resources_total": qualified_stats["qualified_resources_total"],
        "qualified_resources_rejected": qualified_stats["qualified_resources_rejected"],
        "exportable_resources_total": qualified_stats["exportable_resources_total"],
        "image_rejection_rate": _ratio(
            qualified_stats["qualified_resources_rejected"],
            qualified_stats["qualified_resources_total"],
        ),
        "common_name_fr_strict_completeness": _ratio(
            strict_fr_non_empty_count,
            playable_items_total,
        ),
        "common_name_fr_effective_completeness": _ratio(
            effective_fr_non_empty_count,
            playable_items_total,
        ),
        "country_code_completeness": _ratio(country_code_non_empty_count, playable_items_total),
        "attribution_completeness": _ratio(attribution_complete_count, playable_items_total),
        "contract_field_completeness": {
            key: _ratio(value, playable_items_total)
            for key, value in sorted(required_contract_fields.items())
        },
        "question_generation_success_rate": question_validation["question_success_rate"],
        "question_generation_details": question_validation,
    }


def _fetch_qualification_stats(*, services) -> dict[str, int]:
    with services.pipeline_store.connect() as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS qualified_total,
                COUNT(*) FILTER (WHERE qualification_status = 'rejected') AS rejected_total,
                COUNT(*) FILTER (WHERE export_eligible IS TRUE) AS exportable_total
            FROM qualified_resources
            """
        ).fetchone()
    return {
        "qualified_resources_total": int(row["qualified_total"] or 0),
        "qualified_resources_rejected": int(row["rejected_total"] or 0),
        "exportable_resources_total": int(row["exportable_total"] or 0),
    }


def _measure_question_generation(
    *,
    services,
    canonical_taxon_counts: Counter[str],
    playable_by_id: dict[str, dict[str, Any]],
    question_attempts: int,
    question_count: int,
    run_label: str,
    target_country_code: str | None,
    selected_seed_ids: list[str] | None,
) -> dict[str, Any]:
    available_taxa = [
        taxon_id
        for taxon_id, count in sorted(
            canonical_taxon_counts.items(), key=lambda item: (-item[1], item[0])
        )
        if count > 0
    ]
    if selected_seed_ids:
        allowed = set(selected_seed_ids)
        available_taxa = [item for item in available_taxa if item in allowed]
    if len(available_taxa) < 10:
        return {
            "pack_compilation_attempts": 0,
            "pack_compilation_successes": 0,
            "questions_total": 0,
            "questions_valid": 0,
            "question_success_rate": 0.0,
            "reason": "insufficient_taxa_for_pack_compilation",
        }

    pack_id = f"pack:phase2:validation:{run_label}:{uuid4().hex[:8]}"
    parameters = {
        "canonical_taxon_ids": available_taxa,
        "difficulty_policy": "mixed",
        "country_code": target_country_code,
        "location_bbox": None,
        "location_point": None,
        "location_radius_meters": None,
        "observed_from": None,
        "observed_to": None,
        "owner_id": "phase2",
        "org_id": None,
        "visibility": "private",
        "intended_use": "phase2_validation",
    }
    pack_payload = services.pack_store.create_pack(pack_id=pack_id, parameters=parameters)
    revision = int(pack_payload["revision"])

    attempts = max(1, question_attempts)
    successes = 0
    questions_total = 0
    questions_valid = 0

    for _ in range(attempts):
        try:
            compiled = services.pack_store.compile_pack(
                pack_id=pack_id,
                revision=revision,
                question_count=max(1, question_count),
            )
        except Exception:
            continue

        successes += 1
        for question in compiled.get("questions") or []:
            questions_total += 1
            if _is_valid_phase2_question(question=question, playable_by_id=playable_by_id):
                questions_valid += 1

    return {
        "pack_compilation_attempts": attempts,
        "pack_compilation_successes": successes,
        "questions_total": questions_total,
        "questions_valid": questions_valid,
        "question_success_rate": _ratio(questions_valid, questions_total),
    }


def _is_valid_phase2_question(
    *,
    question: dict[str, Any],
    playable_by_id: dict[str, dict[str, Any]],
) -> bool:
    target_playable_item_id = str(question.get("target_playable_item_id") or "")
    target_canonical_taxon_id = str(question.get("target_canonical_taxon_id") or "")
    distractor_taxon_ids = question.get("distractor_canonical_taxon_ids") or []

    if not target_playable_item_id or not target_canonical_taxon_id:
        return False
    if len(distractor_taxon_ids) != 3 or len(set(distractor_taxon_ids)) != 3:
        return False
    if target_canonical_taxon_id in distractor_taxon_ids:
        return False

    target_item = playable_by_id.get(target_playable_item_id)
    if target_item is None:
        return False

    has_image = bool(target_item.get("media_render_url"))
    has_feedback = bool(target_item.get("feedback_short"))
    has_attribution = bool(target_item.get("media_attribution")) and bool(
        target_item.get("media_license")
    )
    return has_image and has_feedback and has_attribution


def _scope_items_to_country(
    items: list[dict[str, Any]],
    *,
    country_code: str | None,
) -> list[dict[str, Any]]:
    if not country_code:
        return list(items)
    normalized_country_code = country_code.upper()
    scoped = [
        item
        for item in items
        if str(item.get("country_code") or "").upper() == normalized_country_code
    ]
    return scoped if scoped else list(items)


def _resolve_effective_common_name_fr(item: dict[str, Any]) -> str | None:
    common_names = item.get("common_names_i18n")
    if isinstance(common_names, dict):
        fr_names = common_names.get("fr")
        if isinstance(fr_names, list) and fr_names:
            return str(fr_names[0]).strip() or None
        en_names = common_names.get("en")
        if isinstance(en_names, list) and en_names:
            return str(en_names[0]).strip() or None
        nl_names = common_names.get("nl")
        if isinstance(nl_names, list) and nl_names:
            return str(nl_names[0]).strip() or None
    scientific_name = str(item.get("scientific_name") or "").strip()
    return scientific_name or None


def _materialize_target_seed_file(
    *,
    pilot_taxa_path: Path,
    output_path: Path,
    target_species_count: int,
) -> list[str]:
    payload = json.loads(pilot_taxa_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Invalid pilot taxa payload: expected list ({pilot_taxa_path})")
    selected = payload[:target_species_count]
    if len(selected) < target_species_count:
        raise ValueError(
            "Pilot taxa payload does not contain enough species for phase 2 target "
            f"(required={target_species_count}, available={len(selected)})"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(selected, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    selected_ids: list[str] = []
    for item in selected:
        canonical_taxon_id = str(item.get("canonical_taxon_id") or "").strip()
        if canonical_taxon_id:
            selected_ids.append(canonical_taxon_id)
    return selected_ids


def _build_harvest_profiles(*, max_attempts: int) -> list[HarvestProfile]:
    base_profiles = [
        HarvestProfile(
            order_by="votes",
            order="desc",
            observed_from=None,
            observed_to=None,
            max_observations_per_taxon=PHASE2_DEFAULT_MAX_OBSERVATIONS_PER_TAXON,
        ),
        HarvestProfile(
            order_by="observed_on",
            order="desc",
            observed_from="2020-01-01",
            observed_to=None,
            max_observations_per_taxon=PHASE2_DEFAULT_MAX_OBSERVATIONS_PER_TAXON,
        ),
        HarvestProfile(
            order_by="observed_on",
            order="asc",
            observed_from="2010-01-01",
            observed_to="2020-12-31",
            max_observations_per_taxon=PHASE2_DEFAULT_MAX_OBSERVATIONS_PER_TAXON,
        ),
    ]
    return base_profiles[: max(1, max_attempts)]


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 6)
