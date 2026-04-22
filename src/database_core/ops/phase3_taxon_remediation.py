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


@dataclass(frozen=True)
class RemediationSelection:
    prioritized_taxon_ids: list[str]
    reason_code: str
    deficits: list[dict[str, object]]
    blocking_taxa: list[dict[str, object]]


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
        manifest, _ = load_snapshot_manifest(manifest_path=manifest_path)
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


def run_phase3_taxon_remediation(
    *,
    pack_id: str,
    revision: int | None,
    database_url: str,
    snapshot_root: Path = DEFAULT_INAT_SNAPSHOT_ROOT,
    pilot_taxa_path: Path = DEFAULT_PILOT_TAXA_PATH,
    gemini_api_key: str,
    summary_output_path: Path | None = None,
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

    for remediation_pass in range(1, PHASE3_MAX_PASSES + 1):
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
            max_observations_per_taxon=PHASE3_MAX_OBSERVATIONS_PER_TAXON,
            timeout_seconds=PHASE3_TIMEOUT_SECONDS,
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
    execution_payload = services.enrichment_store.record_enrichment_execution(
        enrichment_request_id=enrichment_request_id,
        execution_status=execution_status,
        execution_context=execution_context,
        trigger_recompile=True,
    )

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
        "passes": passes,
        "enrichment": {
            "request": request_payload,
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
