from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import psycopg

from database_core.domain.models import (
    ConfusionAggregateGlobal,
    ConfusionBatch,
    ConfusionEvent,
    ConfusionEventInput,
)


class PostgresConfusionStore:
    def __init__(self, *, connect: Callable[[], object]) -> None:
        self._connect = connect

    # ------------------------------------------------------------------
    # Confusion batch ingestion and queries
    # ------------------------------------------------------------------

    def ingest_confusion_batch(
        self,
        *,
        batch_id: str,
        events: Sequence[dict[str, object]],
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        if connection is None:
            with self._connect() as owned_connection:
                return self.ingest_confusion_batch(
                    batch_id=batch_id,
                    events=events,
                    connection=owned_connection,
                )

        if connection.execute(
            "SELECT 1 FROM confusion_batches WHERE batch_id = %s",
            (batch_id,),
        ).fetchone() is not None:
            return {
                "ingested": False,
                "reason": "duplicate_batch",
                "batch_id": batch_id,
            }

        created_at = datetime.now(UTC)
        event_inputs = [ConfusionEventInput(**item) for item in events]
        batch = ConfusionBatch(
            batch_id=batch_id,
            created_at=created_at,
            event_count=len(event_inputs),
        )
        connection.execute(
            """
            INSERT INTO confusion_batches (
                batch_id,
                created_at,
                event_count
            ) VALUES (%s, %s, %s)
            """,
            (
                batch.batch_id,
                batch.created_at.isoformat(),
                batch.event_count,
            ),
        )

        event_payload: list[ConfusionEvent] = []
        for index, event in enumerate(event_inputs, start=1):
            event_payload.append(
                ConfusionEvent(
                    confusion_event_id=f"{batch.batch_id}:{index}",
                    batch_id=batch.batch_id,
                    taxon_confused_for_id=event.taxon_confused_for_id,
                    taxon_correct_id=event.taxon_correct_id,
                    occurred_at=event.occurred_at,
                    created_at=created_at,
                )
            )

        if event_payload:
            _executemany(
                connection,
                """
                INSERT INTO confusion_events (
                    confusion_event_id,
                    batch_id,
                    taxon_confused_for_id,
                    taxon_correct_id,
                    occurred_at,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        item.confusion_event_id,
                        item.batch_id,
                        item.taxon_confused_for_id,
                        item.taxon_correct_id,
                        item.occurred_at.isoformat(),
                        item.created_at.isoformat(),
                    )
                    for item in event_payload
                ],
            )

        return {
            "ingested": True,
            "batch_id": batch.batch_id,
            "created_at": batch.created_at.isoformat(),
            "event_count": batch.event_count,
        }

    def fetch_confusion_events(
        self,
        *,
        batch_id: str | None = None,
        limit: int = 100,
        connection: psycopg.Connection | None = None,
    ) -> list[dict[str, object]]:
        if connection is None:
            with self._connect() as owned_connection:
                return self.fetch_confusion_events(
                    batch_id=batch_id,
                    limit=limit,
                    connection=owned_connection,
                )

        clauses: list[str] = []
        params: list[object] = []
        if batch_id:
            clauses.append("batch_id = %s")
            params.append(batch_id)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = connection.execute(
            f"""
            SELECT
                confusion_event_id,
                batch_id,
                taxon_confused_for_id,
                taxon_correct_id,
                occurred_at,
                created_at
            FROM confusion_events
            {where_clause}
            ORDER BY occurred_at DESC, confusion_event_id
            LIMIT %s
            """,
            [*params, limit],
        ).fetchall()
        return [
            {
                "confusion_event_id": str(row["confusion_event_id"]),
                "batch_id": str(row["batch_id"]),
                "taxon_confused_for_id": str(row["taxon_confused_for_id"]),
                "taxon_correct_id": str(row["taxon_correct_id"]),
                "occurred_at": row["occurred_at"].isoformat(),
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ]

    def recompute_confusion_aggregates_global(
        self,
        *,
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        if connection is None:
            with self._connect() as owned_connection:
                return self.recompute_confusion_aggregates_global(connection=owned_connection)

        aggregated_at = datetime.now(UTC)
        connection.execute("DELETE FROM confusion_aggregates_global")
        connection.execute(
            """
            INSERT INTO confusion_aggregates_global (
                taxon_confused_for_id,
                taxon_correct_id,
                event_count,
                latest_occurred_at,
                aggregated_at
            )
            SELECT
                taxon_confused_for_id,
                taxon_correct_id,
                COUNT(*) AS event_count,
                MAX(occurred_at) AS latest_occurred_at,
                %s
            FROM confusion_events
            GROUP BY taxon_confused_for_id, taxon_correct_id
            """,
            (aggregated_at.isoformat(),),
        )
        pair_count = int(
            connection.execute(
                "SELECT COUNT(*) AS count FROM confusion_aggregates_global"
            ).fetchone()["count"]
        )
        return {
            "recomputed": True,
            "pair_count": pair_count,
            "aggregated_at": aggregated_at.isoformat(),
        }

    def fetch_confusion_aggregates_global(
        self,
        *,
        taxon_confused_for_id: str | None = None,
        limit: int = 100,
        connection: psycopg.Connection | None = None,
    ) -> list[dict[str, object]]:
        if connection is None:
            with self._connect() as owned_connection:
                return self.fetch_confusion_aggregates_global(
                    taxon_confused_for_id=taxon_confused_for_id,
                    limit=limit,
                    connection=owned_connection,
                )

        clauses: list[str] = []
        params: list[object] = []
        if taxon_confused_for_id:
            clauses.append("taxon_confused_for_id = %s")
            params.append(taxon_confused_for_id)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = connection.execute(
            f"""
            SELECT
                taxon_confused_for_id,
                taxon_correct_id,
                event_count,
                latest_occurred_at,
                aggregated_at
            FROM confusion_aggregates_global
            {where_clause}
            ORDER BY event_count DESC, taxon_confused_for_id, taxon_correct_id
            LIMIT %s
            """,
            [*params, limit],
        ).fetchall()
        payload: list[dict[str, object]] = []
        for row in rows:
            aggregate = ConfusionAggregateGlobal(
                taxon_confused_for_id=str(row["taxon_confused_for_id"]),
                taxon_correct_id=str(row["taxon_correct_id"]),
                event_count=int(row["event_count"]),
                latest_occurred_at=row["latest_occurred_at"],
                aggregated_at=row["aggregated_at"],
            )
            payload.append(aggregate.model_dump(mode="json"))
        return payload

    def fetch_confusion_metrics(self, *, top_pair_limit: int = 5) -> dict[str, object]:
        with self._connect() as connection:
            counts_row = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM confusion_batches) AS batches_total,
                    (SELECT COUNT(*) FROM confusion_events) AS events_total,
                    (SELECT COUNT(*) FROM confusion_aggregates_global) AS aggregates_total
                """
            ).fetchone()
            freshest_row = connection.execute(
                "SELECT MAX(aggregated_at) AS aggregated_at FROM confusion_aggregates_global"
            ).fetchone()
            top_rows = connection.execute(
                """
                SELECT taxon_confused_for_id, taxon_correct_id, event_count
                FROM confusion_aggregates_global
                ORDER BY event_count DESC, taxon_confused_for_id, taxon_correct_id
                LIMIT %s
                """,
                (top_pair_limit,),
            ).fetchall()

            return {
                "batches_total": int(counts_row["batches_total"]),
                "events_total": int(counts_row["events_total"]),
                "aggregates_total": int(counts_row["aggregates_total"]),
                "last_aggregated_at": (
                    freshest_row["aggregated_at"].isoformat()
                    if freshest_row["aggregated_at"] is not None
                    else None
                ),
                "top_pairs": [
                    {
                        "taxon_confused_for_id": str(row["taxon_confused_for_id"]),
                        "taxon_correct_id": str(row["taxon_correct_id"]),
                        "event_count": int(row["event_count"]),
                    }
                    for row in top_rows
                ],
            }


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _executemany(
    connection: psycopg.Connection,
    query: str,
    params_seq: Sequence[tuple[object, ...]],
) -> None:
    if not params_seq:
        return
    with connection.cursor() as cursor:
        cursor.executemany(query, params_seq)
