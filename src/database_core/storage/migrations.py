from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from database_core.versioning import SCHEMA_VERSION


@dataclass(frozen=True)
class MigrationResult:
    db_path: Path
    initial_version: int
    target_version: int
    applied_versions: tuple[int, ...]


_MIGRATION_SQL: dict[int, str] = {
    4: """
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        run_id TEXT PRIMARY KEY,
        source_mode TEXT NOT NULL,
        dataset_id TEXT NOT NULL,
        snapshot_id TEXT,
        schema_version TEXT NOT NULL,
        qualification_version TEXT NOT NULL,
        enrichment_version TEXT NOT NULL,
        export_version TEXT NOT NULL,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        run_status TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS canonical_taxa_history (
        run_id TEXT NOT NULL,
        canonical_taxon_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        PRIMARY KEY (run_id, canonical_taxon_id),
        FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
    );

    CREATE TABLE IF NOT EXISTS source_observations_history (
        run_id TEXT NOT NULL,
        observation_uid TEXT NOT NULL,
        source_name TEXT NOT NULL,
        source_observation_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        PRIMARY KEY (run_id, observation_uid),
        FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
    );

    CREATE TABLE IF NOT EXISTS media_assets_history (
        run_id TEXT NOT NULL,
        media_id TEXT NOT NULL,
        source_name TEXT NOT NULL,
        source_media_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        PRIMARY KEY (run_id, media_id),
        FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
    );

    CREATE TABLE IF NOT EXISTS qualified_resources_history (
        run_id TEXT NOT NULL,
        qualified_resource_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        PRIMARY KEY (run_id, qualified_resource_id),
        FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
    );

    CREATE TABLE IF NOT EXISTS review_queue_history (
        run_id TEXT NOT NULL,
        review_item_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        PRIMARY KEY (run_id, review_item_id),
        FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
    );

    CREATE TABLE IF NOT EXISTS canonical_governance_events (
        governance_event_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        canonical_taxon_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        source_name TEXT NOT NULL,
        effective_at TEXT NOT NULL,
        decision_status TEXT NOT NULL,
        decision_reason TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id)
    );

    CREATE UNIQUE INDEX IF NOT EXISTS idx_source_observations_source_external
        ON source_observations (source_name, source_observation_id);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_media_assets_source_external
        ON media_assets (source_name, source_media_id);

    PRAGMA user_version = 4;
    """,
    5: """
    CREATE TABLE IF NOT EXISTS canonical_governance_review_queue (
        governance_review_item_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        governance_event_id TEXT NOT NULL,
        canonical_taxon_id TEXT NOT NULL,
        reason_code TEXT NOT NULL,
        review_note TEXT NOT NULL,
        review_status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY (run_id) REFERENCES pipeline_runs (run_id),
        FOREIGN KEY (governance_event_id)
            REFERENCES canonical_governance_events (governance_event_id)
    );

    CREATE INDEX IF NOT EXISTS idx_canonical_governance_review_queue_status
        ON canonical_governance_review_queue (review_status, created_at);

    PRAGMA user_version = 5;
    """,
}


def read_user_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def has_user_tables(connection: sqlite3.Connection) -> bool:
    count = int(
        connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        ).fetchone()[0]
    )
    return count > 0


def apply_migrations(
    connection: sqlite3.Connection,
    *,
    target_version: int = SCHEMA_VERSION,
) -> tuple[int, ...]:
    current_version = read_user_version(connection)
    if current_version >= target_version:
        return ()

    applied: list[int] = []
    for version in range(current_version + 1, target_version + 1):
        migration_sql = _MIGRATION_SQL.get(version)
        if migration_sql is None:
            raise ValueError(
                "Missing SQL migration step for schema version "
                f"{version} (current={current_version}, target={target_version})"
            )
        connection.executescript(migration_sql)
        applied.append(version)
    return tuple(applied)


def migrate_database_file(
    db_path: Path,
    *,
    target_version: int = SCHEMA_VERSION,
) -> MigrationResult:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        initial_version = read_user_version(connection)
        applied = apply_migrations(connection, target_version=target_version)
        final_version = read_user_version(connection)
    return MigrationResult(
        db_path=db_path,
        initial_version=initial_version,
        target_version=final_version,
        applied_versions=applied,
    )
