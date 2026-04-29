from __future__ import annotations

from psycopg import Connection, sql

from database_core.storage.postgres_schema import (
    POSTGRES_CONFUSION_V13_SQL,
    POSTGRES_ENRICHMENT_QUEUE_V12_SQL,
    POSTGRES_PACK_COMPILATION_V11_SQL,
    POSTGRES_PACK_V10_SQL,
    POSTGRES_PLAYABLE_INCREMENTAL_V14_SQL,
    POSTGRES_PLAYABLE_INVALIDATION_REASONS_V15_SQL,
    POSTGRES_PLAYABLE_V9_SQL,
    POSTGRES_REFERENCED_TAXA_V16_SQL,
    POSTGRES_SCHEMA_SQL,
)
from database_core.versioning import SCHEMA_VERSION

_MIGRATION_SQL: dict[int, str] = {
    8: POSTGRES_SCHEMA_SQL,
    9: POSTGRES_PLAYABLE_V9_SQL,
    10: POSTGRES_PACK_V10_SQL,
    11: POSTGRES_PACK_COMPILATION_V11_SQL,
    12: POSTGRES_ENRICHMENT_QUEUE_V12_SQL,
    13: POSTGRES_CONFUSION_V13_SQL,
    14: POSTGRES_PLAYABLE_INCREMENTAL_V14_SQL,
    15: POSTGRES_PLAYABLE_INVALIDATION_REASONS_V15_SQL,
    16: POSTGRES_REFERENCED_TAXA_V16_SQL,
}


def ensure_migrations_table(connection: Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def read_applied_versions(connection: Connection) -> tuple[int, ...]:
    ensure_migrations_table(connection)
    rows = connection.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    return tuple(int(row["version"]) for row in rows)


def current_schema_version(connection: Connection) -> int:
    versions = read_applied_versions(connection)
    if not versions:
        return 0
    return max(versions)


def has_user_tables(connection: Connection) -> bool:
    row = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM information_schema.tables
        WHERE table_schema = current_schema()
          AND table_type = 'BASE TABLE'
          AND table_name <> 'schema_migrations'
        """
    ).fetchone()
    return int(row["count"]) > 0


def apply_migrations(
    connection: Connection,
    *,
    target_version: int = SCHEMA_VERSION,
) -> tuple[int, ...]:
    if target_version != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported target_version={target_version}; expected {SCHEMA_VERSION}"
        )

    ensure_migrations_table(connection)
    applied_versions = set(read_applied_versions(connection))
    pending = [
        version
        for version in sorted(_MIGRATION_SQL)
        if version <= target_version and version not in applied_versions
    ]

    executed: list[int] = []
    for version in pending:
        _execute_sql_script(connection, _MIGRATION_SQL[version])
        connection.execute(
            "INSERT INTO schema_migrations (version) VALUES (%s)",
            (version,),
        )
        executed.append(version)
    return tuple(executed)


def reset_schema(connection: Connection) -> None:
    tables = connection.execute(
        """
        SELECT c.relname AS tablename
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = current_schema()
          AND c.relkind IN ('r', 'p')
          AND NOT EXISTS (
              SELECT 1
              FROM pg_depend d
              JOIN pg_extension e ON e.oid = d.refobjid
              WHERE d.classid = 'pg_class'::regclass
                AND d.objid = c.oid
                AND d.deptype = 'e'
          )
        """
    ).fetchall()
    for row in tables:
        table_name = str(row["tablename"])
        connection.execute(
            sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(sql.Identifier(table_name))
        )


def _execute_sql_script(connection: Connection, sql_script: str) -> None:
    statements = [statement.strip() for statement in sql_script.split(";") if statement.strip()]
    for statement in statements:
        connection.execute(statement)
