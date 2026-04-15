import io
import json
import shutil
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from database_core.adapters import load_snapshot_dataset, qualify_inat_snapshot
from database_core.adapters.inaturalist_harvest import _candidate_photo_sources
from database_core.adapters.inaturalist_snapshot import (
    load_snapshot_manifest,
    summarize_snapshot_manifest,
)
from database_core.domain.enums import (
    PedagogicalQuality,
    Sex,
    SourceName,
    TechnicalQuality,
    ViewAngle,
)
from database_core.domain.models import AIQualification
from database_core.pipeline.runner import run_pipeline
from database_core.qualification.ai import source_external_key
from database_core.storage.services import build_storage_services


def _build_repository(database_url: str):
    return build_storage_services(database_url).repository

SNAPSHOT_MANIFEST = Path("tests/fixtures/inaturalist_snapshot_smoke/manifest.json")


class StaticQualifier:
    def __init__(self, qualification: AIQualification) -> None:
        self.qualification = qualification

    def qualify(self, media_asset, *, image_bytes: bytes | None = None) -> AIQualification | None:
        del media_asset, image_bytes
        return self.qualification


class InvalidJsonQualifier:
    def qualify(self, media_asset, *, image_bytes: bytes | None = None) -> AIQualification | None:
        del media_asset, image_bytes
        raise json.JSONDecodeError("invalid", "{}", 0)


def test_snapshot_loader_rebuilds_records_without_network() -> None:
    dataset = load_snapshot_dataset(manifest_path=SNAPSHOT_MANIFEST)

    assert [item.canonical_taxon_id for item in dataset.canonical_taxa] == [
        "taxon:birds:000004",
        "taxon:birds:000009",
        "taxon:birds:000014",
    ]
    assert [item.source_observation_id for item in dataset.observations] == [
        "910001",
        "910002",
        "910003",
    ]
    assert [item.source_media_id for item in dataset.media_assets] == ["810001", "810002", "810003"]
    assert [item.width for item in dataset.media_assets] == [1600, 1400, 1280]
    assert [item.height for item in dataset.media_assets] == [1200, 1050, 960]
    assert dataset.observations[0].raw_payload_ref == "responses/taxon_birds_000014.json#/results/0"
    media_key = source_external_key(source_name=SourceName.INATURALIST, external_id="810001")
    assert dataset.cached_image_paths_by_source_media_key[media_key].name == "810001.jpg"
    assert dataset.ai_qualification_outcomes[media_key].status == "ok"
    assert sorted(dataset.taxon_payloads_by_canonical_taxon_id) == [
        "taxon:birds:000004",
        "taxon:birds:000009",
        "taxon:birds:000014",
    ]


def test_snapshot_manifest_v3_is_accepted() -> None:
    manifest, snapshot_dir = load_snapshot_manifest(manifest_path=SNAPSHOT_MANIFEST)

    assert manifest.manifest_version == "inaturalist.snapshot.v3"
    assert snapshot_dir == SNAPSHOT_MANIFEST.parent


def test_snapshot_manifest_without_version_is_rejected(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    payload = json.loads(SNAPSHOT_MANIFEST.read_text(encoding="utf-8"))
    payload.pop("manifest_version", None)
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported snapshot manifest_version"):
        load_snapshot_manifest(manifest_path=manifest_path)


def test_snapshot_manifest_unknown_version_is_rejected(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    payload = json.loads(SNAPSHOT_MANIFEST.read_text(encoding="utf-8"))
    payload["manifest_version"] = "inaturalist.snapshot.v999"
    manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported snapshot manifest_version"):
        load_snapshot_manifest(manifest_path=manifest_path)


def test_snapshot_pipeline_is_reproducible_from_saved_snapshot(
    tmp_path: Path,
    database_url_factory,
) -> None:
    fixed_run_id = "run:20260408T000000Z:aaaaaaaa"
    first_database_url = database_url_factory()
    first_result = run_pipeline(
        source_mode="inat_snapshot",
        snapshot_manifest_path=SNAPSHOT_MANIFEST,
        database_url=first_database_url,
        normalized_snapshot_path=tmp_path / "first_normalized.json",
        qualification_snapshot_path=tmp_path / "first_qualified.json",
        export_path=tmp_path / "first_export.json",
        run_id=fixed_run_id,
        qualifier_mode="cached",
        uncertain_policy="reject",
    )
    second_database_url = database_url_factory()
    second_result = run_pipeline(
        source_mode="inat_snapshot",
        snapshot_manifest_path=SNAPSHOT_MANIFEST,
        database_url=second_database_url,
        normalized_snapshot_path=tmp_path / "second_normalized.json",
        qualification_snapshot_path=tmp_path / "second_qualified.json",
        export_path=tmp_path / "second_export.json",
        run_id=fixed_run_id,
        qualifier_mode="cached",
        uncertain_policy="reject",
    )

    assert first_result.qualified_resource_count == 3
    assert first_result.exportable_resource_count == 3
    assert first_result.review_queue_count == 0
    assert second_result.qualified_resource_count == 3
    assert second_result.exportable_resource_count == 3
    assert second_result.review_queue_count == 0
    assert (tmp_path / "first_normalized.json").read_text(encoding="utf-8") == (
        tmp_path / "second_normalized.json"
    ).read_text(encoding="utf-8")
    assert (tmp_path / "first_qualified.json").read_text(encoding="utf-8") == (
        tmp_path / "second_qualified.json"
    ).read_text(encoding="utf-8")
    assert (tmp_path / "first_export.json").read_text(encoding="utf-8") == (
        tmp_path / "second_export.json"
    ).read_text(encoding="utf-8")


def test_snapshot_pipeline_enriches_canonical_taxa_from_cached_taxon_payloads(
    tmp_path: Path,
    database_url: str,
) -> None:
    run_pipeline(
        source_mode="inat_snapshot",
        snapshot_manifest_path=SNAPSHOT_MANIFEST,
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "enriched_normalized.json",
        qualification_snapshot_path=tmp_path / "enriched_qualified.json",
        export_path=tmp_path / "enriched_export.json",
        qualifier_mode="cached",
        uncertain_policy="reject",
    )

    normalized_payload = json.loads(
        (tmp_path / "enriched_normalized.json").read_text(encoding="utf-8")
    )
    taxa_by_id = {item["canonical_taxon_id"]: item for item in normalized_payload["canonical_taxa"]}
    blackbird = taxa_by_id["taxon:birds:000014"]

    assert normalized_payload["enrichment_version"] == "canonical.enrichment.v2"
    assert blackbird["source_enrichment_status"] == "partial"
    assert blackbird["similar_taxon_ids"] == ["taxon:birds:000004"]
    assert blackbird["similar_taxa"][0]["target_canonical_taxon_id"] == "taxon:birds:000004"
    assert len(blackbird["external_similarity_hints"]) == 2
    assert "yellow eye_ring" in blackbird["key_identification_features"]


def test_candidate_photo_sources_promote_square_url_to_higher_resolution_variants() -> None:
    candidates = _candidate_photo_sources(
        {"url": "https://inaturalist-open-data.s3.amazonaws.com/photos/634853967/square.jpg"}
    )

    assert candidates == [
        ("original", "https://inaturalist-open-data.s3.amazonaws.com/photos/634853967/original.jpg"),
        ("large", "https://inaturalist-open-data.s3.amazonaws.com/photos/634853967/large.jpg"),
        ("medium", "https://inaturalist-open-data.s3.amazonaws.com/photos/634853967/medium.jpg"),
    ]


def test_missing_cached_image_is_rejected_when_uncertain_policy_is_reject(
    tmp_path: Path,
    database_url: str,
) -> None:
    snapshot_dir = tmp_path / "snapshot"
    shutil.copytree(SNAPSHOT_MANIFEST.parent, snapshot_dir)
    (snapshot_dir / "images/810001.jpg").unlink()

    qualification = _accepted_ai_qualification()
    run_pipeline(
        source_mode="inat_snapshot",
        snapshot_manifest_path=snapshot_dir / "manifest.json",
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "missing-image-normalized.json",
        qualification_snapshot_path=tmp_path / "missing-image-qualified.json",
        export_path=tmp_path / "missing-image-export.json",
        qualifier_mode="gemini",
        uncertain_policy="reject",
        ai_qualifier=StaticQualifier(qualification),
    )

    qualification_payload = json.loads(
        (tmp_path / "missing-image-qualified.json").read_text(encoding="utf-8")
    )
    resources_by_media_id = {
        item["media_asset_id"]: item for item in qualification_payload["qualified_resources"]
    }
    missing_image_resource = resources_by_media_id["media:inaturalist:810001"]
    assert missing_image_resource["qualification_status"] == "rejected"
    assert "missing_cached_image" in missing_image_resource["qualification_notes"]


def test_invalid_gemini_json_is_rejected_with_traceable_notes(
    tmp_path: Path,
    database_url: str,
) -> None:
    run_pipeline(
        source_mode="inat_snapshot",
        snapshot_manifest_path=SNAPSHOT_MANIFEST,
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "invalid-json-normalized.json",
        qualification_snapshot_path=tmp_path / "invalid-json-qualified.json",
        export_path=tmp_path / "invalid-json-export.json",
        qualifier_mode="gemini",
        uncertain_policy="reject",
        ai_qualifier=InvalidJsonQualifier(),
    )

    qualification_payload = json.loads(
        (tmp_path / "invalid-json-qualified.json").read_text(encoding="utf-8")
    )
    resources_by_media_id = {
        item["media_asset_id"]: item for item in qualification_payload["qualified_resources"]
    }
    invalid_json_resource = resources_by_media_id["media:inaturalist:810001"]
    assert invalid_json_resource["qualification_status"] == "rejected"
    assert "invalid_gemini_json" in invalid_json_resource["qualification_notes"]
    assert "gemini returned invalid json" in invalid_json_resource["qualification_notes"]


def test_downloaded_dimensions_override_large_source_dimensions_for_acceptance(
    tmp_path: Path,
    database_url: str,
) -> None:
    snapshot_dir = tmp_path / "snapshot"
    shutil.copytree(SNAPSHOT_MANIFEST.parent, snapshot_dir)
    manifest_path = snapshot_dir / "manifest.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_payload["media_downloads"][0]["downloaded_width"] = 75
    manifest_payload["media_downloads"][0]["downloaded_height"] = 75
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    run_pipeline(
        source_mode="inat_snapshot",
        snapshot_manifest_path=manifest_path,
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "low-res-normalized.json",
        qualification_snapshot_path=tmp_path / "low-res-qualified.json",
        export_path=tmp_path / "low-res-export.json",
        qualifier_mode="cached",
        uncertain_policy="reject",
    )

    qualification_payload = json.loads(
        (tmp_path / "low-res-qualified.json").read_text(encoding="utf-8")
    )
    resources_by_media_id = {
        item["media_asset_id"]: item for item in qualification_payload["qualified_resources"]
    }
    low_res_resource = resources_by_media_id["media:inaturalist:810001"]
    assert low_res_resource["qualification_status"] == "rejected"
    assert "insufficient_resolution" in low_res_resource["qualification_notes"]


def test_qualify_inat_snapshot_writes_replayable_ai_outputs(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "raw"
    snapshot_dir = snapshot_root / "smoke-snapshot"
    shutil.copytree(SNAPSHOT_MANIFEST.parent, snapshot_dir)
    manifest_path = snapshot_dir / "manifest.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_payload["ai_outputs_path"] = None
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = qualify_inat_snapshot(
        snapshot_id="smoke-snapshot",
        snapshot_root=snapshot_root,
        gemini_api_key="test-key",
        qualifier=StaticQualifier(_accepted_ai_qualification()),
    )

    ai_outputs_payload = json.loads(result.ai_outputs_path.read_text(encoding="utf-8"))
    updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert result.processed_media_count == 3
    assert result.ai_valid_output_count == 3
    assert updated_manifest["ai_outputs_path"] == "ai_outputs.json"
    serialized_key = "inaturalist::810001"
    assert ai_outputs_payload[serialized_key]["status"] == "ok"
    assert ai_outputs_payload[serialized_key]["prompt_version"] == "phase1.inat.image.v2"


def test_qualify_inat_snapshot_prints_progress(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "raw"
    snapshot_dir = snapshot_root / "smoke-snapshot"
    shutil.copytree(SNAPSHOT_MANIFEST.parent, snapshot_dir)
    manifest_path = snapshot_dir / "manifest.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_payload["ai_outputs_path"] = None
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        qualify_inat_snapshot(
            snapshot_id="smoke-snapshot",
            snapshot_root=snapshot_root,
            gemini_api_key="test-key",
            qualifier=StaticQualifier(_accepted_ai_qualification()),
        )

    output = buffer.getvalue()
    assert "Starting Gemini qualification | snapshot_id=smoke-snapshot | media=3" in output
    assert "Gemini qualification progress | 1/3 | source_media_id=810001 | status=ok" in output
    assert "Gemini qualification progress | 3/3 | source_media_id=810003 | status=ok" in output


def test_prompt_version_mismatch_rejects_cached_ai_outputs(
    tmp_path: Path,
    database_url: str,
) -> None:
    snapshot_dir = tmp_path / "snapshot"
    shutil.copytree(SNAPSHOT_MANIFEST.parent, snapshot_dir)
    ai_outputs_path = snapshot_dir / "ai_outputs.json"
    ai_outputs_payload = json.loads(ai_outputs_path.read_text(encoding="utf-8"))
    key = "inaturalist::810001" if "inaturalist::810001" in ai_outputs_payload else "810001"
    ai_outputs_payload[key]["prompt_version"] = "legacy.prompt.v1"
    ai_outputs_path.write_text(
        json.dumps(ai_outputs_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    run_pipeline(
        source_mode="inat_snapshot",
        snapshot_manifest_path=snapshot_dir / "manifest.json",
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "mismatch_normalized.json",
        qualification_snapshot_path=tmp_path / "mismatch_qualified.json",
        export_path=tmp_path / "mismatch_export.json",
        qualifier_mode="cached",
        uncertain_policy="reject",
    )

    qualification_payload = json.loads(
        (tmp_path / "mismatch_qualified.json").read_text(encoding="utf-8")
    )
    resources_by_media_id = {
        item["media_asset_id"]: item for item in qualification_payload["qualified_resources"]
    }
    mismatched = resources_by_media_id["media:inaturalist:810001"]
    assert mismatched["qualification_status"] == "rejected"
    assert "cached_prompt_version_mismatch" in mismatched["qualification_flags"]


def test_review_overrides_are_reapplied_after_qualification(
    tmp_path: Path,
    database_url: str,
) -> None:
    override_path = tmp_path / "review_overrides.json"
    override_path.write_text(
        json.dumps(
            {
                "override_version": "review.override.v1",
                "snapshot_id": "smoke-snapshot",
                "overrides": [
                    {
                        "media_asset_id": "media:inaturalist:810001",
                        "qualification_status": "review_required",
                        "note": "manual spot-check requested",
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_pipeline(
        source_mode="inat_snapshot",
        snapshot_manifest_path=SNAPSHOT_MANIFEST,
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "override_normalized.json",
        qualification_snapshot_path=tmp_path / "override_qualified.json",
        export_path=tmp_path / "override_export.json",
        qualifier_mode="cached",
        uncertain_policy="reject",
        review_overrides_path=override_path,
        apply_review_overrides=True,
    )

    assert result.review_queue_count == 1
    qualification_payload = json.loads(
        (tmp_path / "override_qualified.json").read_text(encoding="utf-8")
    )
    review_item = qualification_payload["review_queue"][0]
    assert review_item["review_reason_code"] == "human_override"
    assert review_item["stage_name"] == "review_queue_assembly"
    assert review_item["priority"] == "high"
    assert "manual spot-check requested" in review_item["review_note"]

    repository = _build_repository(database_url)
    repository.initialize()
    filtered = repository.fetch_review_queue(review_reason_code="human_override", priority="high")
    assert len(filtered) == 1
    assert filtered[0]["media_asset_id"] == "media:inaturalist:810001"


def test_review_overrides_are_not_applied_without_flag(
    tmp_path: Path,
    monkeypatch,
    database_url: str,
) -> None:
    snapshot_dir = tmp_path / "snapshot"
    shutil.copytree(SNAPSHOT_MANIFEST.parent, snapshot_dir)
    override_dir = tmp_path / "data" / "review_overrides"
    override_dir.mkdir(parents=True)
    (override_dir / "smoke-snapshot.json").write_text(
        json.dumps(
            {
                "override_version": "review.override.v1",
                "snapshot_id": "smoke-snapshot",
                "overrides": [
                    {
                        "media_asset_id": "media:inaturalist:810001",
                        "qualification_status": "review_required",
                        "note": "manual spot-check requested",
                    }
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    result = run_pipeline(
        source_mode="inat_snapshot",
        snapshot_manifest_path=snapshot_dir / "manifest.json",
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "no-override-normalized.json",
        qualification_snapshot_path=tmp_path / "no-override-qualified.json",
        export_path=tmp_path / "no-override-export.json",
        qualifier_mode="cached",
        uncertain_policy="reject",
    )

    assert result.review_queue_count == 0
    qualification_payload = json.loads(
        (tmp_path / "no-override-qualified.json").read_text(encoding="utf-8")
    )
    assert qualification_payload["review_queue"] == []


def test_snapshot_loader_rejects_captive_true_but_accepts_null_or_absent(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshot"
    shutil.copytree(SNAPSHOT_MANIFEST.parent, snapshot_dir)
    response_path = snapshot_dir / "responses/taxon_birds_000014.json"
    payload = json.loads(response_path.read_text(encoding="utf-8"))
    payload["results"][0]["captive"] = True
    response_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    dataset = load_snapshot_dataset(manifest_path=snapshot_dir / "manifest.json")

    assert [item.source_observation_id for item in dataset.observations] == ["910002", "910003"]

    payload["results"][0]["captive"] = None
    response_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    dataset_with_null = load_snapshot_dataset(manifest_path=snapshot_dir / "manifest.json")
    assert [item.source_observation_id for item in dataset_with_null.observations] == [
        "910001",
        "910002",
        "910003",
    ]

    payload["results"][0].pop("captive", None)
    response_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    dataset_without_field = load_snapshot_dataset(manifest_path=snapshot_dir / "manifest.json")
    assert [item.source_observation_id for item in dataset_without_field.observations] == [
        "910001",
        "910002",
        "910003",
    ]


def test_snapshot_loader_rejects_unsafe_observation_or_photo_license(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshot"
    shutil.copytree(SNAPSHOT_MANIFEST.parent, snapshot_dir)
    response_path = snapshot_dir / "responses/taxon_birds_000014.json"
    payload = json.loads(response_path.read_text(encoding="utf-8"))
    payload["results"][0]["license_code"] = "cc-by-nc"
    response_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    dataset = load_snapshot_dataset(manifest_path=snapshot_dir / "manifest.json")
    assert [item.source_observation_id for item in dataset.observations] == ["910002", "910003"]

    payload["results"][0]["license_code"] = "cc-by"
    payload["results"][0]["photos"][0]["license_code"] = "cc-by-nd"
    response_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    dataset_with_unsafe_photo = load_snapshot_dataset(manifest_path=snapshot_dir / "manifest.json")
    assert [item.source_observation_id for item in dataset_with_unsafe_photo.observations] == [
        "910002",
        "910003",
    ]


def test_snapshot_manifest_summary_includes_taxon_breakdown() -> None:
    summary = summarize_snapshot_manifest(manifest_path=SNAPSHOT_MANIFEST)

    assert summary["harvested_observations"] == 3
    assert summary["taxa_with_results"] == 3
    assert summary["harvested_per_taxon"] == {
        "taxon:birds:000004": 1,
        "taxon:birds:000009": 1,
        "taxon:birds:000014": 1,
    }


def _accepted_ai_qualification() -> AIQualification:
    return AIQualification(
        technical_quality=TechnicalQuality.HIGH,
        pedagogical_quality=PedagogicalQuality.HIGH,
        life_stage="adult",
        sex=Sex.UNKNOWN,
        visible_parts=["full_body", "head", "beak"],
        view_angle=ViewAngle.LATERAL,
        confidence=0.92,
        model_name="gemini-3.1-flash-lite-preview",
        notes="synthetic test qualification",
    )
