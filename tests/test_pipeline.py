import json
from pathlib import Path

import pytest
from jsonschema import validate

from database_core.pipeline.runner import run_pipeline


def test_pipeline_produces_reproducible_output(tmp_path: Path) -> None:
    fixture_path = Path("data/fixtures/birds_pilot.json")

    first_db = tmp_path / "first.sqlite"
    first_normalized = tmp_path / "first_normalized.json"
    first_qualified = tmp_path / "first_qualified.json"
    first_export = tmp_path / "first_export.json"
    second_db = tmp_path / "second.sqlite"
    second_normalized = tmp_path / "second_normalized.json"
    second_qualified = tmp_path / "second_qualified.json"
    second_export = tmp_path / "second_export.json"

    first_result = run_pipeline(
        fixture_path=fixture_path,
        db_path=first_db,
        normalized_snapshot_path=first_normalized,
        qualification_snapshot_path=first_qualified,
        export_path=first_export,
    )
    second_result = run_pipeline(
        fixture_path=fixture_path,
        db_path=second_db,
        normalized_snapshot_path=second_normalized,
        qualification_snapshot_path=second_qualified,
        export_path=second_export,
    )

    assert first_result.qualified_resource_count == 4
    assert first_result.exportable_resource_count == 2
    assert first_result.review_queue_count == 1
    assert second_result == first_result.__class__(
        database_path=second_db,
        normalized_snapshot_path=second_normalized,
        qualification_snapshot_path=second_qualified,
        export_path=second_export,
        qualified_resource_count=4,
        exportable_resource_count=2,
        review_queue_count=1,
    )
    assert first_normalized.read_text(encoding="utf-8") == second_normalized.read_text(
        encoding="utf-8"
    )
    assert first_qualified.read_text(encoding="utf-8") == second_qualified.read_text(
        encoding="utf-8"
    )
    assert first_export.read_text(encoding="utf-8") == second_export.read_text(encoding="utf-8")

    export_payload = json.loads(first_export.read_text(encoding="utf-8"))
    export_schema = json.loads(
        Path("schemas/qualified_resources_bundle.schema.json").read_text(encoding="utf-8")
    )
    validate(instance=export_payload, schema=export_schema)

    assert export_payload["schema_version"] == "database.schema.v2"
    assert export_payload["export_version"] == "export.bundle.v1"
    assert export_payload["qualification_version"] == "qualification.staged.v1"
    assert export_payload["enrichment_version"] == "canonical.enrichment.v1"
    assert [item["canonical_taxon_id"] for item in export_payload["canonical_taxa"]] == [
        "bird:passer-domesticus",
        "bird:turdus-merula",
    ]
    assert export_payload["canonical_taxa"][0]["taxon_group"] == "birds"
    assert [item["media_asset_id"] for item in export_payload["qualified_resources"]] == [
        "media:inaturalist:fixture-media-blackbird-001",
        "media:inaturalist:fixture-media-sparrow-001",
    ]

    normalized_payload = json.loads(first_normalized.read_text(encoding="utf-8"))
    assert normalized_payload["schema_version"] == "database.schema.v2"
    assert normalized_payload["normalized_snapshot_version"] == "normalized.snapshot.v2"
    assert normalized_payload["enrichment_version"] == "canonical.enrichment.v1"


def test_pipeline_rejects_invalid_export_bundle(monkeypatch, tmp_path: Path) -> None:
    def fake_build_export_bundle(**kwargs):
        del kwargs
        return {
            "schema_version": "database.schema.v2",
            "export_version": "export.bundle.v1",
        }

    monkeypatch.setattr(
        "database_core.pipeline.runner.build_export_bundle", fake_build_export_bundle
    )

    export_path = tmp_path / "invalid_export.json"
    with pytest.raises(ValueError, match="Export bundle validation failed"):
        run_pipeline(
            fixture_path=Path("data/fixtures/birds_pilot.json"),
            db_path=tmp_path / "invalid.sqlite",
            normalized_snapshot_path=tmp_path / "invalid_normalized.json",
            qualification_snapshot_path=tmp_path / "invalid_qualified.json",
            export_path=export_path,
        )

    assert not export_path.exists()
