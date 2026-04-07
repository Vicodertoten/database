import json
import shutil
from pathlib import Path

from database_core.adapters import load_snapshot_dataset
from database_core.domain.enums import PedagogicalQuality, Sex, TechnicalQuality, ViewAngle
from database_core.domain.models import AIQualification
from database_core.pipeline.runner import run_pipeline

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
        "bird:erithacus-rubecula",
        "bird:passer-domesticus",
        "bird:turdus-merula",
    ]
    assert [item.source_observation_id for item in dataset.observations] == ["910001", "910002", "910003"]
    assert [item.source_media_id for item in dataset.media_assets] == ["810001", "810002", "810003"]
    assert dataset.observations[0].raw_payload_ref == "responses/bird_turdus_merula.json#/results/0"
    assert dataset.cached_image_paths_by_source_media_id["810001"].name == "810001.jpg"


def test_snapshot_pipeline_is_reproducible_from_saved_snapshot(tmp_path: Path) -> None:
    first_result = run_pipeline(
        source_mode="inat_snapshot",
        snapshot_manifest_path=SNAPSHOT_MANIFEST,
        db_path=tmp_path / "first.sqlite",
        normalized_snapshot_path=tmp_path / "first_normalized.json",
        qualification_snapshot_path=tmp_path / "first_qualified.json",
        export_path=tmp_path / "first_export.json",
        qualifier_mode="fixture",
    )
    second_result = run_pipeline(
        source_mode="inat_snapshot",
        snapshot_manifest_path=SNAPSHOT_MANIFEST,
        db_path=tmp_path / "second.sqlite",
        normalized_snapshot_path=tmp_path / "second_normalized.json",
        qualification_snapshot_path=tmp_path / "second_qualified.json",
        export_path=tmp_path / "second_export.json",
        qualifier_mode="fixture",
    )

    assert first_result.qualified_resource_count == 3
    assert first_result.exportable_resource_count == 2
    assert first_result.review_queue_count == 0
    assert second_result.qualified_resource_count == 3
    assert second_result.exportable_resource_count == 2
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


def test_missing_cached_image_routes_to_review_required(tmp_path: Path) -> None:
    snapshot_dir = tmp_path / "snapshot"
    shutil.copytree(SNAPSHOT_MANIFEST.parent, snapshot_dir)
    (snapshot_dir / "images/810001.jpg").unlink()

    qualification = _accepted_ai_qualification()
    run_pipeline(
        source_mode="inat_snapshot",
        snapshot_manifest_path=snapshot_dir / "manifest.json",
        db_path=tmp_path / "missing-image.sqlite",
        normalized_snapshot_path=tmp_path / "missing-image-normalized.json",
        qualification_snapshot_path=tmp_path / "missing-image-qualified.json",
        export_path=tmp_path / "missing-image-export.json",
        qualifier_mode="gemini",
        ai_qualifier=StaticQualifier(qualification),
    )

    qualification_payload = json.loads(
        (tmp_path / "missing-image-qualified.json").read_text(encoding="utf-8")
    )
    resources_by_media_id = {
        item["media_asset_id"]: item for item in qualification_payload["qualified_resources"]
    }
    missing_image_resource = resources_by_media_id["media:inaturalist:810001"]
    assert missing_image_resource["qualification_status"] == "review_required"
    assert "missing_cached_image" in missing_image_resource["qualification_notes"]


def test_invalid_gemini_json_routes_to_review_required_with_traceable_notes(tmp_path: Path) -> None:
    run_pipeline(
        source_mode="inat_snapshot",
        snapshot_manifest_path=SNAPSHOT_MANIFEST,
        db_path=tmp_path / "invalid-json.sqlite",
        normalized_snapshot_path=tmp_path / "invalid-json-normalized.json",
        qualification_snapshot_path=tmp_path / "invalid-json-qualified.json",
        export_path=tmp_path / "invalid-json-export.json",
        qualifier_mode="gemini",
        ai_qualifier=InvalidJsonQualifier(),
    )

    qualification_payload = json.loads(
        (tmp_path / "invalid-json-qualified.json").read_text(encoding="utf-8")
    )
    resources_by_media_id = {
        item["media_asset_id"]: item for item in qualification_payload["qualified_resources"]
    }
    invalid_json_resource = resources_by_media_id["media:inaturalist:810001"]
    assert invalid_json_resource["qualification_status"] == "review_required"
    assert "invalid_gemini_json" in invalid_json_resource["qualification_notes"]
    assert "gemini returned invalid json" in invalid_json_resource["qualification_notes"]


def _accepted_ai_qualification() -> AIQualification:
    return AIQualification(
        technical_quality=TechnicalQuality.HIGH,
        pedagogical_quality=PedagogicalQuality.HIGH,
        life_stage="adult",
        sex=Sex.UNKNOWN,
        visible_parts=["full_body", "head", "beak"],
        view_angle=ViewAngle.LATERAL,
        confidence=0.92,
        model_name="gemini-2.5-flash",
        notes="synthetic test qualification",
    )
