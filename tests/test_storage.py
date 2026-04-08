from pathlib import Path

import pytest

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
    assert user_version == 3
