import json
from pathlib import Path

import pytest
from jsonschema import validate

from database_core.pipeline.runner import run_pipeline
from database_core.storage.postgres import PostgresRepository


def test_pipeline_produces_reproducible_output(
    tmp_path: Path,
    database_url_factory,
) -> None:
    fixture_path = Path("data/fixtures/birds_pilot.json")
    fixed_run_id = "run:20260408T000000Z:aaaaaaaa"

    first_database_url = database_url_factory()
    first_normalized = tmp_path / "first_normalized.json"
    first_qualified = tmp_path / "first_qualified.json"
    first_export = tmp_path / "first_export.json"
    second_database_url = database_url_factory()
    second_normalized = tmp_path / "second_normalized.json"
    second_qualified = tmp_path / "second_qualified.json"
    second_export = tmp_path / "second_export.json"

    first_result = run_pipeline(
        fixture_path=fixture_path,
        database_url=first_database_url,
        normalized_snapshot_path=first_normalized,
        qualification_snapshot_path=first_qualified,
        export_path=first_export,
        run_id=fixed_run_id,
    )
    second_result = run_pipeline(
        fixture_path=fixture_path,
        database_url=second_database_url,
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
        database_url=second_database_url,
        normalized_snapshot_path=second_normalized,
        qualification_snapshot_path=second_qualified,
        export_path=second_export,
        legacy_export_path=None,
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
        Path("schemas/qualified_resources_bundle_v4.schema.json").read_text(encoding="utf-8")
    )
    validate(instance=export_payload, schema=export_schema)

    assert export_payload["schema_version"] == "database.schema.v12"
    assert export_payload["export_version"] == "export.bundle.v4"
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
    assert "qualification_flags" in export_payload["qualified_resources"][0]
    assert "pedagogy" in export_payload["qualified_resources"][0]
    assert "uncertainty" in export_payload["qualified_resources"][0]
    assert "review_context" in export_payload["qualified_resources"][0]
    assert export_payload["qualified_resources"][0]["provenance"]["run_id"] == fixed_run_id

    normalized_payload = json.loads(first_normalized.read_text(encoding="utf-8"))
    assert normalized_payload["schema_version"] == "database.schema.v12"
    assert normalized_payload["normalized_snapshot_version"] == "normalized.snapshot.v3"
    assert normalized_payload["enrichment_version"] == "canonical.enrichment.v2"
    assert not first_export.with_name(f"{first_export.stem}.v3{first_export.suffix}").exists()


def test_pipeline_can_emit_v3_sidecar_when_opted_in(tmp_path: Path, database_url: str) -> None:
    export_path = tmp_path / "optin_export.json"
    run_pipeline(
        fixture_path=Path("data/fixtures/birds_pilot.json"),
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "optin_normalized.json",
        qualification_snapshot_path=tmp_path / "optin_qualified.json",
        export_path=export_path,
        write_sidecar_export_v3=True,
    )

    legacy_export_path = export_path.with_name(f"{export_path.stem}.v3{export_path.suffix}")
    legacy_export_payload = json.loads(legacy_export_path.read_text(encoding="utf-8"))
    legacy_schema = json.loads(
        Path("schemas/qualified_resources_bundle_v3.schema.json").read_text(encoding="utf-8")
    )
    validate(instance=legacy_export_payload, schema=legacy_schema)
    assert legacy_export_payload["export_version"] == "export.bundle.v3"


def test_export_v4_matches_internal_golden_snapshot(tmp_path: Path, database_url: str) -> None:
    export_path = tmp_path / "golden_export.json"
    run_pipeline(
        fixture_path=Path("data/fixtures/birds_pilot.json"),
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "golden_normalized.json",
        qualification_snapshot_path=tmp_path / "golden_qualified.json",
        export_path=export_path,
        run_id="run:20260408T000000Z:aaaaaaaa",
        write_sidecar_export_v3=False,
    )

    payload = json.loads(export_path.read_text(encoding="utf-8"))
    golden_payload = json.loads(
        Path("tests/fixtures/export_bundle_v4.golden.json").read_text(encoding="utf-8")
    )
    assert payload == golden_payload


def test_pipeline_rejects_invalid_export_bundle(
    monkeypatch,
    tmp_path: Path,
    database_url: str,
) -> None:
    def fake_build_export_bundle(**kwargs):
        del kwargs
        return {
            "schema_version": "database.schema.v12",
            "export_version": "export.bundle.v4",
        }

    monkeypatch.setattr(
        "database_core.pipeline.runner.build_export_bundle", fake_build_export_bundle
    )

    export_path = tmp_path / "invalid_export.json"
    with pytest.raises(ValueError, match="Export bundle validation failed"):
        run_pipeline(
            fixture_path=Path("data/fixtures/birds_pilot.json"),
            database_url=database_url,
            normalized_snapshot_path=tmp_path / "invalid_normalized.json",
            qualification_snapshot_path=tmp_path / "invalid_qualified.json",
            export_path=export_path,
        )

    assert not export_path.exists()


def test_pipeline_overwrites_previous_run_outputs_on_same_database(
    tmp_path: Path,
    database_url: str,
) -> None:
    run_pipeline(
        fixture_path=Path("data/fixtures/birds_pilot.json"),
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "overwrite.normalized.json",
        qualification_snapshot_path=tmp_path / "overwrite.qualified.json",
        export_path=tmp_path / "overwrite.export.json",
        uncertain_policy="review",
    )
    repository = PostgresRepository(database_url)
    repository.initialize()
    first_summary = repository.fetch_summary()
    assert first_summary["review_queue"] == 1
    assert first_summary["qualified_resources"] == 4

    run_pipeline(
        fixture_path=Path("data/fixtures/birds_pilot.json"),
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "overwrite.normalized.json",
        qualification_snapshot_path=tmp_path / "overwrite.qualified.json",
        export_path=tmp_path / "overwrite.export.json",
        uncertain_policy="reject",
    )
    repository = PostgresRepository(database_url)
    repository.initialize()
    second_summary = repository.fetch_summary()
    assert second_summary["review_queue"] == 0
    assert second_summary["qualified_resources"] == 4
    assert second_summary["playable_items"] == 2

    with repository.connect() as connection:
        run_count = connection.execute("SELECT COUNT(*) AS count FROM pipeline_runs").fetchone()[
            "count"
        ]
        governance_count = connection.execute(
            "SELECT COUNT(*) AS count FROM canonical_governance_events"
        ).fetchone()["count"]
    assert run_count == 2
    assert governance_count > 0


def test_run_metrics_support_run_scope(tmp_path: Path, database_url: str) -> None:
    first_run_id = "run:20260408T000000Z:aaaaaaaa"
    second_run_id = "run:20260408T000100Z:bbbbbbbb"

    run_pipeline(
        fixture_path=Path("data/fixtures/birds_pilot.json"),
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "metrics_1.normalized.json",
        qualification_snapshot_path=tmp_path / "metrics_1.qualified.json",
        export_path=tmp_path / "metrics_1.export.json",
        uncertain_policy="review",
        run_id=first_run_id,
    )
    run_pipeline(
        fixture_path=Path("data/fixtures/birds_pilot.json"),
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "metrics_2.normalized.json",
        qualification_snapshot_path=tmp_path / "metrics_2.qualified.json",
        export_path=tmp_path / "metrics_2.export.json",
        uncertain_policy="reject",
        run_id=second_run_id,
    )

    repository = PostgresRepository(database_url)
    repository.initialize()
    first_metrics = repository.fetch_run_level_metrics(run_id=first_run_id)
    second_metrics = repository.fetch_run_level_metrics(run_id=second_run_id)

    assert first_metrics["run_id"] == first_run_id
    assert second_metrics["run_id"] == second_run_id
    assert first_metrics["quality"]["review_required_resources"] == 1
    assert second_metrics["quality"]["review_required_resources"] == 0


def test_pipeline_rolls_back_database_on_artifact_write_failure(
    monkeypatch,
    tmp_path: Path,
    database_url: str,
) -> None:
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
            database_url=database_url,
            normalized_snapshot_path=tmp_path / "rollback.normalized.json",
            qualification_snapshot_path=tmp_path / "rollback.qualified.json",
            export_path=tmp_path / "rollback.export.json",
        )

    repository = PostgresRepository(database_url)
    repository.initialize()
    summary = repository.fetch_summary()
    assert summary == {
        "canonical_taxa": 0,
        "source_observations": 0,
        "media_assets": 0,
        "qualified_resources": 0,
        "review_queue": 0,
        "playable_items": 0,
        "compiled_pack_builds": 0,
        "pack_materializations": 0,
        "enrichment_requests": 0,
        "enrichment_executions": 0,
    }
    assert not (tmp_path / "rollback.normalized.json").exists()
    assert not (tmp_path / "rollback.qualified.json").exists()
    assert not (tmp_path / "rollback.export.json").exists()
    assert not (tmp_path / "rollback.export.v3.json").exists()


def test_pipeline_populates_playable_corpus_with_exportable_resources(
    tmp_path: Path,
    database_url: str,
) -> None:
    run_pipeline(
        fixture_path=Path("data/fixtures/birds_pilot.json"),
        database_url=database_url,
        normalized_snapshot_path=tmp_path / "playable.normalized.json",
        qualification_snapshot_path=tmp_path / "playable.qualified.json",
        export_path=tmp_path / "playable.export.json",
        run_id="run:20260408T000000Z:aaaaaaaa",
    )
    repository = PostgresRepository(database_url)
    payload = repository.fetch_playable_corpus_payload(limit=100)

    assert payload["playable_corpus_version"] == "playable_corpus.v1"
    assert len(payload["items"]) == 2
    assert [item["media_asset_id"] for item in payload["items"]] == [
        "media:inaturalist:fixture-media-blackbird-001",
        "media:inaturalist:fixture-media-sparrow-001",
    ]
