from datetime import UTC, datetime
from pathlib import Path

import pytest

from database_core.domain.models import CanonicalTaxon, ExternalMapping
from database_core.storage.sqlite import (
    RepositorySchemaVersionMismatchError,
    SQLiteRepository,
)


def test_initialize_rejects_legacy_schema_version_without_explicit_reset(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    repository = SQLiteRepository(db_path)
    repository.initialize()

    with repository.connect() as connection:
        connection.execute("PRAGMA user_version = 1")
        connection.execute("CREATE TABLE IF NOT EXISTS legacy_table (id INTEGER PRIMARY KEY)")

    with pytest.raises(RepositorySchemaVersionMismatchError):
        repository.initialize()


def test_initialize_can_reset_legacy_schema_version_with_explicit_flag(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    repository = SQLiteRepository(db_path)
    repository.initialize()

    with repository.connect() as connection:
        connection.execute("PRAGMA user_version = 1")
        connection.execute("CREATE TABLE IF NOT EXISTS legacy_table (id INTEGER PRIMARY KEY)")

    repository.initialize(allow_schema_reset=True)

    with repository.connect() as connection:
        table_names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert "legacy_table" not in table_names
    assert user_version == 5


def test_migrate_to_latest_upgrades_v3_to_v5(tmp_path: Path) -> None:
    db_path = tmp_path / "migration.sqlite"
    repository = SQLiteRepository(db_path)
    repository.initialize()

    with repository.connect() as connection:
        connection.execute("PRAGMA user_version = 3")

    with pytest.raises(RepositorySchemaVersionMismatchError):
        repository.initialize()

    applied_versions = repository.migrate_to_latest()
    assert applied_versions == (4, 5)
    assert repository.current_schema_version() == 5


def test_append_run_history_creates_governance_review_queue_item_for_ambiguous_transition(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "governance.sqlite"
    repository = SQLiteRepository(db_path)
    repository.initialize()

    first_run_id = "run:20260408T000000Z:aaaaaaaa"
    second_run_id = "run:20260408T000100Z:bbbbbbbb"
    captured_at = datetime(2026, 4, 8, 0, 0, tzinfo=UTC)

    previous_taxa = [
        _canonical_taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Alauda arvensis",
        )
    ]
    current_taxa = [
        _canonical_taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Alauda arvensis",
            taxon_status="deprecated",
            split_into=["taxon:birds:999999"],
        )
    ]

    with repository.connect() as connection:
        repository.start_pipeline_run(
            run_id=first_run_id,
            source_mode="fixture",
            dataset_id="fixture:baseline",
            snapshot_id=None,
            started_at=captured_at,
            connection=connection,
        )
        repository.append_run_history(
            run_id=first_run_id,
            governance_effective_at=captured_at,
            canonical_taxa=previous_taxa,
            observations=[],
            media_assets=[],
            qualified_resources=[],
            review_items=[],
            connection=connection,
        )
        repository.complete_pipeline_run(
            run_id=first_run_id,
            completed_at=captured_at,
            connection=connection,
        )

        repository.start_pipeline_run(
            run_id=second_run_id,
            source_mode="fixture",
            dataset_id="fixture:changed",
            snapshot_id=None,
            started_at=captured_at,
            connection=connection,
        )
        repository.append_run_history(
            run_id=second_run_id,
            governance_effective_at=captured_at,
            canonical_taxa=current_taxa,
            observations=[],
            media_assets=[],
            qualified_resources=[],
            review_items=[],
            connection=connection,
        )
        repository.complete_pipeline_run(
            run_id=second_run_id,
            completed_at=captured_at,
            connection=connection,
        )

    rows = repository.fetch_canonical_governance_review_queue(run_id=second_run_id)
    assert len(rows) == 1
    assert rows[0]["reason_code"] == "ambiguous_transition_missing_target"
    assert rows[0]["review_status"] == "open"


def test_append_run_history_routes_ambiguous_mapping_conflicts_to_governance_review_queue(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "governance-mapping.sqlite"
    repository = SQLiteRepository(db_path)
    repository.initialize()

    first_run_id = "run:20260408T000000Z:aaaaaaaa"
    second_run_id = "run:20260408T000100Z:bbbbbbbb"
    captured_at = datetime(2026, 4, 8, 0, 0, tzinfo=UTC)

    previous_taxa = [
        _canonical_taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
            external_source_mappings=[("inaturalist", "12716")],
        )
    ]
    current_taxa = [
        _canonical_taxon(
            canonical_taxon_id="taxon:birds:000001",
            name="Parus major",
            external_source_mappings=[("inaturalist", "12716")],
        ),
        _canonical_taxon(
            canonical_taxon_id="taxon:birds:000002",
            name="Parus major duplicate",
            external_source_mappings=[("inaturalist", "12716")],
        ),
    ]

    with repository.connect() as connection:
        repository.start_pipeline_run(
            run_id=first_run_id,
            source_mode="fixture",
            dataset_id="fixture:baseline",
            snapshot_id=None,
            started_at=captured_at,
            connection=connection,
        )
        repository.append_run_history(
            run_id=first_run_id,
            governance_effective_at=captured_at,
            canonical_taxa=previous_taxa,
            observations=[],
            media_assets=[],
            qualified_resources=[],
            review_items=[],
            connection=connection,
        )
        repository.complete_pipeline_run(
            run_id=first_run_id,
            completed_at=captured_at,
            connection=connection,
        )

        repository.start_pipeline_run(
            run_id=second_run_id,
            source_mode="fixture",
            dataset_id="fixture:changed",
            snapshot_id=None,
            started_at=captured_at,
            connection=connection,
        )
        repository.append_run_history(
            run_id=second_run_id,
            governance_effective_at=captured_at,
            canonical_taxa=current_taxa,
            observations=[],
            media_assets=[],
            qualified_resources=[],
            review_items=[],
            connection=connection,
        )
        repository.complete_pipeline_run(
            run_id=second_run_id,
            completed_at=captured_at,
            connection=connection,
        )

    rows = repository.fetch_canonical_governance_review_queue(run_id=second_run_id)
    assert len(rows) == 2
    assert {row["reason_code"] for row in rows} == {"ambiguous_source_mapping_conflict"}
    assert {row["review_status"] for row in rows} == {"open"}


def _canonical_taxon(
    *,
    canonical_taxon_id: str,
    name: str,
    taxon_status: str = "active",
    authority_source: str = "inaturalist",
    external_source_mappings: list[tuple[str, str]] | None = None,
    split_into: list[str] | None = None,
) -> CanonicalTaxon:
    return CanonicalTaxon(
        canonical_taxon_id=canonical_taxon_id,
        accepted_scientific_name=name,
        canonical_rank="species",
        taxon_group="birds",
        taxon_status=taxon_status,
        authority_source=authority_source,
        display_slug=name.lower().replace(" ", "-"),
        synonyms=[],
        common_names=[],
        key_identification_features=[],
        source_enrichment_status="seeded",
        bird_scope_compatible=True,
        external_source_mappings=[
            ExternalMapping(source_name=source_name, external_id=external_id)
            for source_name, external_id in (external_source_mappings or [])
        ],
        external_similarity_hints=[],
        similar_taxa=[],
        similar_taxon_ids=[],
        split_into=split_into or [],
        merged_into=None,
        replaced_by=None,
        derived_from=None,
    )
