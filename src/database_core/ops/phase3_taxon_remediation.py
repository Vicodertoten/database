from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from database_core.adapters import (
    DEFAULT_INAT_SNAPSHOT_ROOT,
    DEFAULT_PILOT_TAXA_PATH,
    PilotTaxonSeed,
    fetch_inat_snapshot,
    load_pilot_taxa,
    load_snapshot_manifest,
    qualify_inat_snapshot,
    write_snapshot_manifest,
)
from database_core.export.json_exporter import write_json
from database_core.ops.smoke_report import generate_smoke_report
from database_core.pipeline.runner import run_pipeline
from database_core.storage.pack_store import MIN_PACK_TOTAL_QUESTIONS
from database_core.storage.services import build_storage_services

PHASE3_REMEDIATION_VERSION = "phase3.remediation.v1"
PHASE3_MAX_PASSES = 3
PHASE3_MAX_OBSERVATIONS_PER_TAXON = 15
PHASE3_TIMEOUT_SECONDS = 30
PHASE3_NORMALIZED_OUTPUT_DIR = Path("data/normalized")
PHASE3_QUALIFIED_OUTPUT_DIR = Path("data/qualified")
PHASE3_EXPORT_OUTPUT_DIR = Path("data/exports")
PHASE3_SUMMARY_OUTPUT_DIR = Path("docs/20_execution/phase3")
PHASE3_PREFLIGHT_VERSION = "phase3.preflight.v1"
PHASE3_PREFLIGHT_OUTPUT_DIR = Path("docs/20_execution/phase3_1")


@dataclass(frozen=True)
class RemediationSelection:
    prioritized_taxon_ids: list[str]
    reason_code: str
    deficits: list[dict[str, object]]
    blocking_taxa: list[dict[str, object]]


def evaluate_preflight_gate(
    *,
    is_compilable_before: bool,
    insufficient_media_before: int,
    accepted_new_observation_media_probe: int,
) -> tuple[bool, bool, str]:
    if is_compilable_before:
        return False, False, "pack_already_compilable"
    if insufficient_media_before <= 0:
        return False, False, "no_compile_deficit"
    expected_compile_impact_signal = accepted_new_observation_media_probe > 0
    if expected_compile_impact_signal:
        return True, True, "signal_positive"
    return False, False, "signal_absent_on_blocking_taxa"


def extract_min_media_missing_from_diagnostic(diagnostic: dict[str, Any]) -> int:
    deficits = diagnostic.get("deficits") or []
    for item in deficits:
        code = str(item.get("code", "")).strip()
        if code != "min_media_per_taxon":
            continue
        return int(item.get("missing", 0))
    return 0


def build_remediation_selection(diagnostic: dict[str, object]) -> RemediationSelection:
    blocking_taxa_payload = diagnostic.get("blocking_taxa") or []
    blocking_taxa = [
        {
            "canonical_taxon_id": str(item.get("canonical_taxon_id", "")).strip(),
            "media_count": int(item.get("media_count", 0)),
            "missing_media_count": int(item.get("missing_media_count", 0)),
        }
        for item in blocking_taxa_payload
        if str(item.get("canonical_taxon_id", "")).strip()
    ]
    blocking_taxa.sort(
        key=lambda item: (
            -int(item["missing_media_count"]),
            int(item["media_count"]),
            str(item["canonical_taxon_id"]),
        )
    )
    prioritized_taxon_ids = list(
        dict.fromkeys(str(item["canonical_taxon_id"]) for item in blocking_taxa)
    )
    return RemediationSelection(
        prioritized_taxon_ids=prioritized_taxon_ids,
        reason_code=str(diagnostic.get("reason_code", "")),
        deficits=list(diagnostic.get("deficits") or []),
        blocking_taxa=blocking_taxa,
    )


def collect_known_source_ids(
    *,
    snapshot_root: Path,
    exclude_snapshot_ids: set[str] | None = None,
) -> tuple[set[str], set[str]]:
    excluded = exclude_snapshot_ids or set()
    known_observation_ids: set[str] = set()
    known_media_ids: set[str] = set()
    for manifest_path in snapshot_root.glob("*/manifest.json"):
        snapshot_id = manifest_path.parent.name
        if snapshot_id in excluded:
            continue
        try:
            manifest, _ = load_snapshot_manifest(manifest_path=manifest_path)
        except ValueError:
            # Ignore legacy/unsupported manifests in snapshot root; Phase 3 idempotence
            # must only compare against canonical v3-compatible snapshots.
            continue
        for item in manifest.media_downloads:
            known_observation_ids.add(str(item.source_observation_id))
            known_media_ids.add(str(item.source_media_id))
    return known_observation_ids, known_media_ids


def filter_snapshot_media_for_idempotence(
    *,
    snapshot_id: str,
    snapshot_root: Path,
    known_observation_ids: set[str],
    known_media_ids: set[str],
) -> dict[str, int]:
    manifest, snapshot_dir = load_snapshot_manifest(snapshot_id=snapshot_id, snapshot_root=snapshot_root)
    kept_media_ids: set[str] = set()
    ignored_existing_observation = 0
    ignored_existing_media = 0
    accepted_new_observation_media = 0

    response_payloads: dict[str, dict[str, object]] = {}
    for seed in manifest.taxon_seeds:
        payload_path = snapshot_dir / seed.response_path
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        response_payloads[seed.response_path] = payload
        kept_results: list[dict[str, object]] = []
        for result in payload.get("results", []):
            observation_id = str(result.get("id", "")).strip()
            photos = result.get("photos") or []
            primary_photo = photos[0] if photos else None
            media_id = str((primary_photo or {}).get("id", "")).strip()
            if not observation_id or not media_id:
                continue
            if observation_id in known_observation_ids:
                ignored_existing_observation += 1
                continue
            if media_id in known_media_ids:
                ignored_existing_media += 1
                continue
            kept_results.append(result)
            kept_media_ids.add(media_id)
            known_observation_ids.add(observation_id)
            known_media_ids.add(media_id)
            accepted_new_observation_media += 1
        payload["results"] = kept_results

    for response_path, payload in response_payloads.items():
        path = snapshot_dir / response_path
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    filtered_downloads = [
        item
        for item in manifest.media_downloads
        if str(item.source_media_id) in kept_media_ids
    ]
    write_snapshot_manifest(
        snapshot_dir,
        manifest.model_copy(update={"media_downloads": filtered_downloads, "ai_outputs_path": None}),
    )
    return {
        "ignored_existing_observation": ignored_existing_observation,
        "ignored_existing_media": ignored_existing_media,
        "accepted_new_observation_media": accepted_new_observation_media,
    }


def _build_seed_subset(
    *,
    pilot_taxa_path: Path,
    prioritized_taxon_ids: list[str],
) -> tuple[list[PilotTaxonSeed], list[str]]:
    seeds = load_pilot_taxa(pilot_taxa_path)
    seeds_by_canonical_taxon_id = {
        str(seed.canonical_taxon_id): seed
        for seed in seeds
        if seed.canonical_taxon_id is not None
    }
    selected: list[PilotTaxonSeed] = []
    missing: list[str] = []
    for canonical_taxon_id in prioritized_taxon_ids:
        seed = seeds_by_canonical_taxon_id.get(canonical_taxon_id)
        if seed is None:
            missing.append(canonical_taxon_id)
            continue
        selected.append(seed)
    return selected, missing


def _write_seed_subset_file(
    *,
    snapshot_root: Path,
    pack_id: str,
    remediation_pass: int,
    selected_seeds: list[PilotTaxonSeed],
) -> Path:
    safe_pack_id = pack_id.replace(":", "_")
    output_path = snapshot_root / f"phase3_pilot_{safe_pack_id}_pass{remediation_pass}.json"
    payload = [seed.model_dump(mode="json") for seed in selected_seeds]
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def run_phase3_preflight(
    *,
    pack_id: str,
    revision: int | None,
    database_url: str,
    snapshot_root: Path = DEFAULT_INAT_SNAPSHOT_ROOT,
    pilot_taxa_path: Path = DEFAULT_PILOT_TAXA_PATH,
    summary_output_path: Path | None = None,
    max_observations_per_taxon_probe: int = 3,
    harvest_order_by: str | None = None,
    harvest_order: str | None = None,
    harvest_observed_from: str | None = None,
    harvest_observed_to: str | None = None,
    harvest_bbox: str | None = None,
) -> dict[str, object]:
    services = build_storage_services(database_url)
    services.database.initialize()

    baseline_diagnostic = services.pack_store.diagnose_pack(pack_id=pack_id, revision=revision)
    selection = build_remediation_selection(baseline_diagnostic)
    insufficient_media_before = extract_min_media_missing_from_diagnostic(baseline_diagnostic)
    is_compilable_before = bool(baseline_diagnostic.get("compilable"))
    now = datetime.now(UTC)
    resolved_probe_obs = max(1, int(max_observations_per_taxon_probe))
    snapshot_id = None
    probe_result: dict[str, Any] = {
        "harvested_observations": 0,
        "downloaded_images": 0,
        "accepted_new_observation_media_probe": 0,
        "ignored_existing_observation": 0,
        "ignored_existing_media": 0,
        "missing_taxa_in_pilot": [],
        "probe_executed": False,
    }

    expected_compile_impact_signal = False
    preflight_go, _, preflight_reason = evaluate_preflight_gate(
        is_compilable_before=is_compilable_before,
        insufficient_media_before=insufficient_media_before,
        accepted_new_observation_media_probe=0,
    )

    if (not is_compilable_before) and insufficient_media_before > 0:
        selected_seeds, missing_taxa = _build_seed_subset(
            pilot_taxa_path=pilot_taxa_path,
            prioritized_taxon_ids=selection.prioritized_taxon_ids,
        )
        probe_result["missing_taxa_in_pilot"] = missing_taxa
        if selected_seeds:
            snapshot_id = f"inaturalist-birds-v2-phase3pre-{now.strftime('%Y%m%dT%H%M%SZ')}-p1"
            seed_subset_path = _write_seed_subset_file(
                snapshot_root=snapshot_root,
                pack_id=pack_id,
                remediation_pass=0,
                selected_seeds=selected_seeds,
            )
            known_observation_ids, known_media_ids = collect_known_source_ids(
                snapshot_root=snapshot_root,
            )
            harvest_result = fetch_inat_snapshot(
                snapshot_id=snapshot_id,
                snapshot_root=snapshot_root,
                pilot_taxa_path=seed_subset_path,
                max_observations_per_taxon=resolved_probe_obs,
                timeout_seconds=PHASE3_TIMEOUT_SECONDS,
                observed_from=harvest_observed_from,
                observed_to=harvest_observed_to,
                order_by=harvest_order_by,
                order=harvest_order,
                bbox=harvest_bbox,
                exclude_observation_ids=known_observation_ids,
                exclude_media_ids=known_media_ids,
            )
            idempotence_stats = filter_snapshot_media_for_idempotence(
                snapshot_id=snapshot_id,
                snapshot_root=snapshot_root,
                known_observation_ids=known_observation_ids,
                known_media_ids=known_media_ids,
            )
            accepted_new = int(idempotence_stats["accepted_new_observation_media"])
            preflight_go, expected_compile_impact_signal, preflight_reason = evaluate_preflight_gate(
                is_compilable_before=is_compilable_before,
                insufficient_media_before=insufficient_media_before,
                accepted_new_observation_media_probe=accepted_new,
            )
            probe_result = {
                "harvested_observations": int(harvest_result.harvested_observation_count),
                "downloaded_images": int(harvest_result.downloaded_image_count),
                "accepted_new_observation_media_probe": accepted_new,
                "ignored_existing_observation": int(idempotence_stats["ignored_existing_observation"]),
                "ignored_existing_media": int(idempotence_stats["ignored_existing_media"]),
                "missing_taxa_in_pilot": missing_taxa,
                "probe_executed": True,
            }
        else:
            preflight_reason = "no_blocking_taxa_seed_mapping"

    summary = {
        "phase3_preflight_version": PHASE3_PREFLIGHT_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "candidate_pack_id": pack_id,
        "revision": int(baseline_diagnostic["revision"]),
        "candidate_pack_reason_code_before": str(baseline_diagnostic["reason_code"]),
        "is_compilable_before": is_compilable_before,
        "insufficient_media_before": insufficient_media_before,
        "blocking_taxa_count": len(selection.blocking_taxa),
        "prioritized_taxon_ids": selection.prioritized_taxon_ids,
        "snapshot_id": snapshot_id,
        "probe": probe_result,
        "expected_compile_impact_signal": expected_compile_impact_signal,
        "decision": "preflight_go" if preflight_go else "preflight_no_go",
        "preflight_go": preflight_go,
        "preflight_reason": preflight_reason,
        "run_limits": {
            "max_observations_per_taxon_probe": resolved_probe_obs,
        },
        "harvest_query": {
            "order_by": harvest_order_by or "votes",
            "order": harvest_order or "desc",
            "observed_from": harvest_observed_from,
            "observed_to": harvest_observed_to,
            "bbox": harvest_bbox,
        },
    }

    safe_pack_id = pack_id.replace(":", "_")
    output_path = summary_output_path or (
        PHASE3_PREFLIGHT_OUTPUT_DIR
        / f"{safe_pack_id}.{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.phase3_preflight.v1.json"
    )
    write_json(output_path, summary)
    summary["output_path"] = output_path.as_posix()
    return summary


def run_phase3_taxon_remediation(
    *,
    pack_id: str,
    revision: int | None,
    database_url: str,
    snapshot_root: Path = DEFAULT_INAT_SNAPSHOT_ROOT,
    pilot_taxa_path: Path = DEFAULT_PILOT_TAXA_PATH,
    gemini_api_key: str,
    summary_output_path: Path | None = None,
    max_passes: int = PHASE3_MAX_PASSES,
    max_observations_per_taxon: int = PHASE3_MAX_OBSERVATIONS_PER_TAXON,
    harvest_order_by: str | None = None,
    harvest_order: str | None = None,
    harvest_observed_from: str | None = None,
    harvest_observed_to: str | None = None,
    harvest_bbox: str | None = None,
) -> dict[str, object]:
    services = build_storage_services(database_url)
    services.database.initialize()

    baseline_smoke = generate_smoke_report(
        services.pipeline_store,
        snapshot_id=None,
        database_url=database_url,
    )
    baseline_diagnostic = services.pack_store.diagnose_pack(pack_id=pack_id, revision=revision)
    selection = build_remediation_selection(baseline_diagnostic)

    request_payload: dict[str, Any] | None = None
    execution_payload: dict[str, Any] | None = None
    enrichment_request_id: str | None = None
    if not bool(baseline_diagnostic.get("compilable")):
        request_payload = services.enrichment_store.create_or_merge_enrichment_request(
            pack_id=pack_id,
            revision=int(baseline_diagnostic["revision"]),
            reason_code=selection.reason_code,
            targets=[
                {
                    "resource_type": "canonical_taxon",
                    "resource_id": taxon_id,
                    "target_attribute": "playable_availability",
                }
                for taxon_id in selection.prioritized_taxon_ids
            ]
            or [
                {
                    "resource_type": "pack",
                    "resource_id": pack_id,
                    "target_attribute": "playable_availability",
                }
            ],
        )
        enrichment_request_id = str(request_payload["request"]["enrichment_request_id"])

    known_observation_ids, known_media_ids = collect_known_source_ids(
        snapshot_root=snapshot_root,
    )
    passes: list[dict[str, Any]] = []
    current_diagnostic = baseline_diagnostic
    now = datetime.now(UTC)

    resolved_max_passes = max(1, int(max_passes))
    resolved_max_observations_per_taxon = max(1, int(max_observations_per_taxon))

    for remediation_pass in range(1, resolved_max_passes + 1):
        if bool(current_diagnostic.get("compilable")):
            break
        pass_selection = build_remediation_selection(current_diagnostic)
        selected_seeds, missing_taxa = _build_seed_subset(
            pilot_taxa_path=pilot_taxa_path,
            prioritized_taxon_ids=pass_selection.prioritized_taxon_ids,
        )
        if not selected_seeds:
            passes.append(
                {
                    "pass": remediation_pass,
                    "snapshot_id": None,
                    "missing_taxa_in_pilot": missing_taxa,
                    "status": "no_target_seeds",
                }
            )
            break

        snapshot_id = (
            f"inaturalist-birds-v2-phase3rem-{now.strftime('%Y%m%dT%H%M%SZ')}-p{remediation_pass}"
        )
        seed_subset_path = _write_seed_subset_file(
            snapshot_root=snapshot_root,
            pack_id=pack_id,
            remediation_pass=remediation_pass,
            selected_seeds=selected_seeds,
        )
        harvest_result = fetch_inat_snapshot(
            snapshot_id=snapshot_id,
            snapshot_root=snapshot_root,
            pilot_taxa_path=seed_subset_path,
            max_observations_per_taxon=resolved_max_observations_per_taxon,
            timeout_seconds=PHASE3_TIMEOUT_SECONDS,
            observed_from=harvest_observed_from,
            observed_to=harvest_observed_to,
            order_by=harvest_order_by,
            order=harvest_order,
            bbox=harvest_bbox,
            exclude_observation_ids=known_observation_ids,
            exclude_media_ids=known_media_ids,
        )
        idempotence_stats = filter_snapshot_media_for_idempotence(
            snapshot_id=snapshot_id,
            snapshot_root=snapshot_root,
            known_observation_ids=known_observation_ids,
            known_media_ids=known_media_ids,
        )
        qualify_result = qualify_inat_snapshot(
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
            normalized_snapshot_path=PHASE3_NORMALIZED_OUTPUT_DIR / f"{snapshot_id}.json",
            qualification_snapshot_path=PHASE3_QUALIFIED_OUTPUT_DIR / f"{snapshot_id}.json",
            export_path=PHASE3_EXPORT_OUTPUT_DIR / f"{snapshot_id}.json",
        )
        current_diagnostic = services.pack_store.diagnose_pack(pack_id=pack_id, revision=revision)
        passes.append(
            {
                "pass": remediation_pass,
                "snapshot_id": snapshot_id,
                "missing_taxa_in_pilot": missing_taxa,
                "harvested_observations": int(harvest_result.harvested_observation_count),
                "downloaded_images": int(harvest_result.downloaded_image_count),
                "idempotence": idempotence_stats,
                "qualified_resources": int(pipeline_result.qualified_resource_count),
                "exportable_resources": int(pipeline_result.exportable_resource_count),
                "pack_diagnostic_reason_code_after_pass": str(current_diagnostic["reason_code"]),
                "pack_compilable_after_pass": bool(current_diagnostic["compilable"]),
                "images_sent_to_gemini": int(qualify_result.images_sent_to_gemini_count),
                "pre_ai_rejection_count": int(qualify_result.pre_ai_rejection_count),
            }
        )

    final_smoke = generate_smoke_report(
        services.pipeline_store,
        snapshot_id=None,
        database_url=database_url,
    )

    execution_status = "success" if bool(current_diagnostic.get("compilable")) else "partial"
    execution_context: dict[str, object] = {
        "phase3_remediation_version": PHASE3_REMEDIATION_VERSION,
        "passes": passes,
        "baseline_reason_code": str(baseline_diagnostic["reason_code"]),
        "final_reason_code": str(current_diagnostic["reason_code"]),
    }
    if enrichment_request_id is not None:
        execution_payload = services.enrichment_store.record_enrichment_execution(
            enrichment_request_id=enrichment_request_id,
            execution_status=execution_status,
            execution_context=execution_context,
            trigger_recompile=True,
        )
    else:
        execution_payload = {
            "skipped": True,
            "reason": "pack_compilable_baseline",
            "execution_status": execution_status,
        }

    baseline_ratio = float(
        baseline_smoke["extended_kpis"]["taxon_with_min2_media_ratio"]["actual"]
    )
    final_ratio = float(final_smoke["extended_kpis"]["taxon_with_min2_media_ratio"]["actual"])
    baseline_deficits = int(
        baseline_smoke["compile_deficits_summary"]["reason_counts"].get(
            "insufficient_media_per_taxon", 0
        )
    )
    final_deficits = int(
        final_smoke["compile_deficits_summary"]["reason_counts"].get(
            "insufficient_media_per_taxon", 0
        )
    )
    decision_status = "NO_GO"
    if (
        final_ratio > baseline_ratio
        and final_deficits < baseline_deficits
        and bool(final_smoke.get("overall_pass"))
    ):
        decision_status = "GO"
    elif (
        (final_ratio > baseline_ratio or final_deficits < baseline_deficits)
        and bool(final_smoke.get("overall_pass"))
    ):
        decision_status = "GO_WITH_GAPS"

    summary = {
        "phase3_remediation_version": PHASE3_REMEDIATION_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "pack_id": pack_id,
        "revision": int(baseline_diagnostic["revision"]),
        "baseline": {
            "diagnostic": baseline_diagnostic,
            "taxon_with_min2_media_ratio": baseline_ratio,
            "insufficient_media_per_taxon_reason_count": baseline_deficits,
            "overall_pass": bool(baseline_smoke.get("overall_pass")),
        },
        "final": {
            "diagnostic": current_diagnostic,
            "taxon_with_min2_media_ratio": final_ratio,
            "insufficient_media_per_taxon_reason_count": final_deficits,
            "overall_pass": bool(final_smoke.get("overall_pass")),
        },
        "delta": {
            "taxon_with_min2_media_ratio": round(final_ratio - baseline_ratio, 6),
            "insufficient_media_per_taxon_reason_count": final_deficits - baseline_deficits,
        },
        "selection": {
            "reason_code": selection.reason_code,
            "deficits": selection.deficits,
            "blocking_taxa": selection.blocking_taxa,
            "prioritized_taxon_ids": selection.prioritized_taxon_ids,
        },
        "run_limits": {
            "max_passes": resolved_max_passes,
            "max_observations_per_taxon": resolved_max_observations_per_taxon,
        },
        "harvest_query": {
            "order_by": harvest_order_by or "votes",
            "order": harvest_order or "desc",
            "observed_from": harvest_observed_from,
            "observed_to": harvest_observed_to,
            "bbox": harvest_bbox,
        },
        "passes": passes,
        "enrichment": {
            "request": request_payload
            or {
                "skipped": True,
                "reason": "pack_compilable_baseline",
            },
            "execution": execution_payload,
        },
        "decision": {
            "status": decision_status,
            "go_condition": "ratio_up AND insufficient_media_per_taxon_down AND overall_pass_true",
        },
    }

    safe_pack_id = pack_id.replace(":", "_")
    output_path = summary_output_path or (
        PHASE3_SUMMARY_OUTPUT_DIR
        / f"{safe_pack_id}.{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.phase3_remediation.v1.json"
    )
    write_json(output_path, summary)
    summary["output_path"] = output_path.as_posix()
    return summary
