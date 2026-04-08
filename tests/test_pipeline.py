import json
from pathlib import Path

import pytest
from jsonschema import validate

from database_core.pipeline.runner import run_pipeline
from database_core.storage.sqlite import SQLiteRepository


def test_pipeline_produces_reproducible_output(tmp_path: Path) -> None:
    fixture_path = Path("data/fixtures/birds_pilot.json")
    fixed_run_id = "run:20260408T000000Z:aaaaaaaa"

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
        run_id=fixed_run_id,
    )
    second_result = run_pipeline(
        fixture_path=fixture_path,
        db_path=second_db,
        normalized_snapshot_path=second_normalized,
        qualification_snapshot_path=second_qualified,
        export_path=second_export,
        run_id=fixed_run_id,
    )

    assert first_result.qualified_resource_count == 4
    assert first_result.exportable_resource_count == 2
    assert first_result.review_queue_count == 1
    assert second_result == first_result.__class__(
        run_id=fixed_run_id,
        database_path=second_db,
        normalized_snapshot_path=second_normalized,
        qualification_snapshot_path=second_qualified,
        export_path=second_export,
        legacy_export_path=second_export.with_name(f"{second_export.stem}.v2{second_export.suffix}"),
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
        Path("schemas/qualified_resources_bundle_v3.schema.json").read_text(encoding="utf-8")
    )
    validate(instance=export_payload, schema=export_schema)
    legacy_export_path = first_export.with_name(f"{first_export.stem}.v2{first_export.suffix}")
    legacy_export_payload = json.loads(legacy_export_path.read_text(encoding="utf-8"))
    legacy_schema = json.loads(
        Path("schemas/qualified_resources_bundle.schema.json").read_text(encoding="utf-8")
    )
    validate(instance=legacy_export_payload, schema=legacy_schema)

    assert export_payload["schema_version"] == "database.schema.v5"
    assert export_payload["export_version"] == "export.bundle.v3"
    assert export_payload["qualification_version"] == "qualification.staged.v1"
    assert export_payload["enrichment_version"] == "canonical.enrichment.v2"
    assert [item["canonical_taxon_id"] for item in export_payload["canonical_taxa"]] == [
        "taxon:birds:000009",
        "taxon:birds:000014",
    ]
    assert export_payload["canonical_taxa"][0]["taxon_group"] == "birds"
    assert [item["media_asset_id"] for item in export_payload["qualified_resources"]] == [
        "media:inaturalist:fixture-media-blackbird-001",
        "media:inaturalist:fixture-media-sparrow-001",
    ]
    assert export_payload["qualified_resources"][0]["provenance"]["run_id"] == fixed_run_id
    assert legacy_export_payload["export_version"] == "export.bundle.v2"

    normalized_payload = json.loads(first_normalized.read_text(encoding="utf-8"))
    assert normalized_payload["schema_version"] == "database.schema.v5"
    assert normalized_payload["normalized_snapshot_version"] == "normalized.snapshot.v3"
    assert normalized_payload["enrichment_version"] == "canonical.enrichment.v2"


def test_pipeline_rejects_invalid_export_bundle(monkeypatch, tmp_path: Path) -> None:
    def fake_build_export_bundle(**kwargs):
        del kwargs
        return {
            "schema_version": "database.schema.v5",
            "export_version": "export.bundle.v3",
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


def test_pipeline_overwrites_previous_run_outputs_on_same_database(tmp_path: Path) -> None:
    db_path = tmp_path / "overwrite.sqlite"
    run_pipeline(
        fixture_path=Path("data/fixtures/birds_pilot.json"),
        db_path=db_path,
        normalized_snapshot_path=tmp_path / "overwrite.normalized.json",
        qualification_snapshot_path=tmp_path / "overwrite.qualified.json",
        export_path=tmp_path / "overwrite.export.json",
        uncertain_policy="review",
    )
    repository = SQLiteRepository(db_path)
    repository.initialize()
    first_summary = repository.fetch_summary()
    assert first_summary["review_queue"] == 1
    assert first_summary["qualified_resources"] == 4

    run_pipeline(
        fixture_path=Path("data/fixtures/birds_pilot.json"),
        db_path=db_path,
        normalized_snapshot_path=tmp_path / "overwrite.normalized.json",
        qualification_snapshot_path=tmp_path / "overwrite.qualified.json",
        export_path=tmp_path / "overwrite.export.json",
        uncertain_policy="reject",
    )
    repository = SQLiteRepository(db_path)
    repository.initialize()
    second_summary = repository.fetch_summary()
    assert second_summary["review_queue"] == 0
    assert second_summary["qualified_resources"] == 4

    with repository.connect() as connection:
        run_count = connection.execute("SELECT COUNT(*) AS count FROM pipeline_runs").fetchone()[
            "count"
        ]
        governance_count = connection.execute(
            "SELECT COUNT(*) AS count FROM canonical_governance_events"
        ).fetchone()["count"]
    assert run_count == 2
    assert governance_count > 0


def test_pipeline_rolls_back_database_on_artifact_write_failure(
    monkeypatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "rollback.sqlite"

    def fail_export_write(path, payload):  # noqa: ANN001
        del path, payload
        raise RuntimeError("synthetic export write failure")

    monkeypatch.setattr(
        "database_core.pipeline.runner.write_export_bundle",
        fail_export_write,
    )

    with pytest.raises(RuntimeError, match="synthetic export write failure"):
        run_pipeline(
            fixture_path=Path("data/fixtures/birds_pilot.json"),
            db_path=db_path,
            normalized_snapshot_path=tmp_path / "rollback.normalized.json",
            qualification_snapshot_path=tmp_path / "rollback.qualified.json",
            export_path=tmp_path / "rollback.export.json",
        )

    repository = SQLiteRepository(db_path)
    repository.initialize()
    summary = repository.fetch_summary()
    assert summary == {
        "canonical_taxa": 0,
        "source_observations": 0,
        "media_assets": 0,
        "qualified_resources": 0,
        "review_queue": 0,
    }
    assert not (tmp_path / "rollback.normalized.json").exists()
    assert not (tmp_path / "rollback.qualified.json").exists()
    assert not (tmp_path / "rollback.export.json").exists()
    assert not (tmp_path / "rollback.export.v2.json").exists()
