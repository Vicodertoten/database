from pathlib import Path

from database_core.storage.sqlite import SQLiteRepository


def test_initialize_resets_legacy_schema_version(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    repository = SQLiteRepository(db_path)
    repository.initialize()

    with repository.connect() as connection:
        connection.execute("PRAGMA user_version = 1")
        connection.execute("CREATE TABLE IF NOT EXISTS legacy_table (id INTEGER PRIMARY KEY)")

    repository.initialize()

    with repository.connect() as connection:
        table_names = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        user_version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert "legacy_table" not in table_names
    assert user_version == 2
