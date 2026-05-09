from __future__ import annotations

import json
from collections.abc import Callable

import psycopg


class PostgresDynamicPackStore:
    def __init__(self, *, connect: Callable[[], object]) -> None:
        self._connect = connect

    def save_pack_pool(
        self,
        payload: dict[str, object],
        *,
        connection: psycopg.Connection | None = None,
    ) -> None:
        if connection is None:
            with self._connect() as owned_connection:
                self.save_pack_pool(payload, connection=owned_connection)
            return

        metrics = payload["metrics"]
        if not isinstance(metrics, dict):
            raise ValueError("pack_pool payload metrics must be an object")
        connection.execute(
            """
            INSERT INTO pack_pools (
                pool_id,
                pack_pool_version,
                source_run_id,
                generated_at,
                item_count,
                taxon_count,
                metrics_json,
                payload_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (pool_id)
            DO UPDATE SET
                pack_pool_version = EXCLUDED.pack_pool_version,
                source_run_id = EXCLUDED.source_run_id,
                generated_at = EXCLUDED.generated_at,
                item_count = EXCLUDED.item_count,
                taxon_count = EXCLUDED.taxon_count,
                metrics_json = EXCLUDED.metrics_json,
                payload_json = EXCLUDED.payload_json
            """,
            (
                payload["pool_id"],
                payload["pack_pool_version"],
                payload["source_run_id"],
                payload["generated_at"],
                metrics["item_count"],
                metrics["taxon_count"],
                _json(metrics),
                _json(payload),
            ),
        )

    def fetch_pack_pool(self, *, pool_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM pack_pools
                WHERE pool_id = %s
                """,
                (pool_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(str(row["payload_json"]))

    def save_session_snapshot(
        self,
        payload: dict[str, object],
        *,
        connection: psycopg.Connection | None = None,
    ) -> None:
        if connection is None:
            with self._connect() as owned_connection:
                self.save_session_snapshot(payload, connection=owned_connection)
            return

        connection.execute(
            """
            INSERT INTO session_snapshots (
                session_snapshot_id,
                pool_id,
                session_snapshot_version,
                locale,
                seed,
                question_count,
                generated_at,
                payload_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (session_snapshot_id)
            DO UPDATE SET
                pool_id = EXCLUDED.pool_id,
                session_snapshot_version = EXCLUDED.session_snapshot_version,
                locale = EXCLUDED.locale,
                seed = EXCLUDED.seed,
                question_count = EXCLUDED.question_count,
                generated_at = EXCLUDED.generated_at,
                payload_json = EXCLUDED.payload_json
            """,
            (
                payload["session_snapshot_id"],
                payload["pool_id"],
                payload["session_snapshot_version"],
                payload["locale"],
                payload["seed"],
                payload["question_count"],
                payload["generated_at"],
                _json(payload),
            ),
        )

    def fetch_session_snapshot(
        self,
        *,
        session_snapshot_id: str,
    ) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM session_snapshots
                WHERE session_snapshot_id = %s
                """,
                (session_snapshot_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(str(row["payload_json"]))


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)
