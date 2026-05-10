from __future__ import annotations

import json
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
                event_count,
                skipped_correct_count
            ) VALUES (%s, %s, %s, %s)
            """,
            (
                batch.batch_id,
                batch.created_at.isoformat(),
                batch.event_count,
                batch.skipped_correct_count,
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
                    created_at,
                    source_signal_id,
                    runtime_session_id,
                    question_position,
                    session_snapshot_id,
                    pool_id,
                    locale,
                    seed,
                    selected_option_id,
                    distractor_source,
                    option_sources_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        item.confusion_event_id,
                        item.batch_id,
                        item.taxon_confused_for_id,
                        item.taxon_correct_id,
                        item.occurred_at.isoformat(),
                        item.created_at.isoformat(),
                        item.source_signal_id,
                        item.runtime_session_id,
                        item.question_position,
                        item.session_snapshot_id,
                        item.pool_id,
                        item.locale,
                        item.seed,
                        item.selected_option_id,
                        item.distractor_source,
                        item.option_sources_json,
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

    def ingest_runtime_answer_signals_batch(
        self,
        *,
        batch_id: str,
        payload: dict[str, object],
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        if connection is None:
            with self._connect() as owned_connection:
                return self.ingest_runtime_answer_signals_batch(
                    batch_id=batch_id,
                    payload=payload,
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

        signals = payload.get("signals")
        if not isinstance(signals, list):
            raise ValueError("runtime_answer_signals.v1 payload must include signals list")

        event_inputs: list[ConfusionEventInput] = []
        skipped_correct_count = 0
        for signal in signals:
            if not isinstance(signal, dict):
                raise ValueError("signal must be an object")
            if bool(signal.get("is_correct")) or signal.get(
                "selected_canonical_taxon_id"
            ) == signal.get("expected_canonical_taxon_id"):
                skipped_correct_count += 1
                continue
            event_inputs.append(_event_input_from_runtime_signal(signal))

        created_at = datetime.now(UTC)
        source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        source_filters = source.get("filters") if isinstance(source, dict) else None
        connection.execute(
            """
            INSERT INTO confusion_batches (
                batch_id,
                created_at,
                event_count,
                source_schema_version,
                source_export_id,
                source_app,
                source_table,
                source_filters_json,
                skipped_correct_count
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                batch_id,
                created_at.isoformat(),
                len(event_inputs),
                str(payload.get("schema_version") or ""),
                str(payload.get("export_id") or ""),
                str(source.get("app") or "") if isinstance(source, dict) else "",
                str(source.get("table") or "") if isinstance(source, dict) else "",
                json.dumps(source_filters, sort_keys=True) if source_filters is not None else None,
                skipped_correct_count,
            ),
        )

        event_payload = [
            ConfusionEvent(
                confusion_event_id=f"{batch_id}:{index}",
                batch_id=batch_id,
                taxon_confused_for_id=event.taxon_confused_for_id,
                taxon_correct_id=event.taxon_correct_id,
                occurred_at=event.occurred_at,
                created_at=created_at,
                source_signal_id=event.source_signal_id,
                runtime_session_id=event.runtime_session_id,
                question_position=event.question_position,
                session_snapshot_id=event.session_snapshot_id,
                pool_id=event.pool_id,
                locale=event.locale,
                seed=event.seed,
                selected_option_id=event.selected_option_id,
                distractor_source=event.distractor_source,
                option_sources_json=event.option_sources_json,
            )
            for index, event in enumerate(event_inputs, start=1)
        ]

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
                    created_at,
                    source_signal_id,
                    runtime_session_id,
                    question_position,
                    session_snapshot_id,
                    pool_id,
                    locale,
                    seed,
                    selected_option_id,
                    distractor_source,
                    option_sources_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        item.confusion_event_id,
                        item.batch_id,
                        item.taxon_confused_for_id,
                        item.taxon_correct_id,
                        item.occurred_at.isoformat(),
                        item.created_at.isoformat(),
                        item.source_signal_id,
                        item.runtime_session_id,
                        item.question_position,
                        item.session_snapshot_id,
                        item.pool_id,
                        item.locale,
                        item.seed,
                        item.selected_option_id,
                        item.distractor_source,
                        item.option_sources_json,
                    )
                    for item in event_payload
                ],
            )

        return {
            "ingested": True,
            "batch_id": batch_id,
            "created_at": created_at.isoformat(),
            "source_export_id": payload.get("export_id"),
            "source_schema_version": payload.get("schema_version"),
            "signal_count": len(signals),
            "event_count": len(event_inputs),
            "skipped_correct_count": skipped_correct_count,
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
                created_at,
                source_signal_id,
                runtime_session_id,
                question_position,
                session_snapshot_id,
                pool_id,
                locale,
                seed,
                selected_option_id,
                distractor_source,
                option_sources_json
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
                "source_signal_id": row["source_signal_id"],
                "runtime_session_id": row["runtime_session_id"],
                "question_position": row["question_position"],
                "session_snapshot_id": row["session_snapshot_id"],
                "pool_id": row["pool_id"],
                "locale": row["locale"],
                "seed": row["seed"],
                "selected_option_id": row["selected_option_id"],
                "distractor_source": row["distractor_source"],
                "option_sources_json": row["option_sources_json"],
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
                locale,
                distractor_source,
                event_count,
                latest_occurred_at,
                aggregated_at
            )
            SELECT
                taxon_confused_for_id,
                taxon_correct_id,
                COALESCE(locale, 'unknown') AS locale,
                COALESCE(distractor_source, 'unknown') AS distractor_source,
                COUNT(*) AS event_count,
                MAX(occurred_at) AS latest_occurred_at,
                %s
            FROM confusion_events
            GROUP BY
                taxon_confused_for_id,
                taxon_correct_id,
                COALESCE(locale, 'unknown'),
                COALESCE(distractor_source, 'unknown')
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
                locale,
                distractor_source,
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
                locale=str(row["locale"]),
                distractor_source=str(row["distractor_source"]),
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
                SELECT
                    taxon_confused_for_id,
                    taxon_correct_id,
                    locale,
                    distractor_source,
                    event_count
                FROM confusion_aggregates_global
                ORDER BY
                    event_count DESC,
                    taxon_confused_for_id,
                    taxon_correct_id,
                    locale,
                    distractor_source
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
                        "locale": str(row["locale"]),
                        "distractor_source": str(row["distractor_source"]),
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


def _event_input_from_runtime_signal(signal: dict[str, object]) -> ConfusionEventInput:
    option_sources = signal.get("option_sources")
    selected_option_id = str(signal.get("selected_option_id") or "")
    return ConfusionEventInput(
        taxon_confused_for_id=str(signal["selected_canonical_taxon_id"]),
        taxon_correct_id=str(signal["expected_canonical_taxon_id"]),
        occurred_at=signal["answered_at"],
        source_signal_id=str(signal.get("signal_id") or ""),
        runtime_session_id=str(signal.get("session_id") or ""),
        question_position=int(signal.get("question_position") or 0),
        session_snapshot_id=(
            str(signal["session_snapshot_id"]) if signal.get("session_snapshot_id") else None
        ),
        pool_id=str(signal.get("pool_id") or ""),
        locale=str(signal["locale"]) if signal.get("locale") else None,
        seed=str(signal["seed"]) if signal.get("seed") else None,
        selected_option_id=selected_option_id,
        distractor_source=_selected_option_source(option_sources, selected_option_id),
        option_sources_json=json.dumps(option_sources, sort_keys=True),
    )


def _selected_option_source(option_sources: object, selected_option_id: str) -> str | None:
    if not isinstance(option_sources, list):
        return None
    for option_source in option_sources:
        if not isinstance(option_source, dict):
            continue
        if option_source.get("optionId") == selected_option_id:
            value = str(option_source.get("source") or "")
            return value or None
    return None
