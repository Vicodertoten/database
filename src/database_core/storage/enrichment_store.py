from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from uuid import uuid4

import psycopg

from database_core.domain.enums import (
    EnrichmentExecutionStatus,
    EnrichmentRequestReasonCode,
    EnrichmentRequestStatus,
    EnrichmentTargetResourceType,
)
from database_core.domain.models import (
    EnrichmentExecution,
    EnrichmentRequest,
    EnrichmentRequestTarget,
)
from database_core.storage.pack_store import MIN_PACK_TOTAL_QUESTIONS, PostgresPackStore


class PostgresEnrichmentStore:
    def __init__(
        self,
        *,
        connect: Callable[[], object],
        pack_store: PostgresPackStore,
    ) -> None:
        self._connect = connect
        self._pack_store = pack_store

    # ------------------------------------------------------------------
    # Enrichment queue operations
    # ------------------------------------------------------------------

    def enqueue_enrichment_for_pack(
        self,
        *,
        pack_id: str,
        revision: int | None = None,
        question_count: int = MIN_PACK_TOTAL_QUESTIONS,
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        if connection is None:
            with self._connect() as owned_connection:
                return self.enqueue_enrichment_for_pack(
                    pack_id=pack_id,
                    revision=revision,
                    question_count=question_count,
                    connection=owned_connection,
                )

        context = self._pack_store.compute_pack_compilation_context(
            connection,
            pack_id=pack_id,
            revision=revision,
            question_count_requested=max(question_count, MIN_PACK_TOTAL_QUESTIONS),
        )
        if context["compilable"]:
            return {
                "enqueued": False,
                "reason": "pack_compilable",
                "pack_id": pack_id,
                "revision": int(context["revision"]),
            }

        targets = [
            {
                "resource_type": EnrichmentTargetResourceType.CANONICAL_TAXON,
                "resource_id": str(item.canonical_taxon_id),
                "target_attribute": "similar_taxon_ids",
            }
            for item in context["blocking_taxa"]
        ]
        if not targets:
            targets = [
                {
                    "resource_type": EnrichmentTargetResourceType.PACK,
                    "resource_id": pack_id,
                    "target_attribute": "playable_availability",
                }
            ]

        request_payload = self.create_or_merge_enrichment_request(
            pack_id=pack_id,
            revision=int(context["revision"]),
            reason_code=str(context["reason_code"]),
            targets=targets,
            connection=connection,
        )
        return {
            "enqueued": True,
            "pack_id": pack_id,
            "revision": int(context["revision"]),
            "compilation_reason_code": str(context["reason_code"]),
            "request": request_payload,
        }

    def create_or_merge_enrichment_request(
        self,
        *,
        pack_id: str,
        revision: int,
        reason_code: str,
        targets: Sequence[dict[str, object]],
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        if connection is None:
            with self._connect() as owned_connection:
                return self.create_or_merge_enrichment_request(
                    pack_id=pack_id,
                    revision=revision,
                    reason_code=reason_code,
                    targets=targets,
                    connection=owned_connection,
                )

        reason = EnrichmentRequestReasonCode(reason_code)
        normalized_targets = self._normalize_enrichment_targets(targets)
        if not normalized_targets:
            raise ValueError("targets must contain at least one item")

        existing_requests = connection.execute(
            """
            SELECT enrichment_request_id
            FROM enrichment_requests
            WHERE pack_id = %s
              AND revision = %s
              AND reason_code = %s
              AND request_status IN ('pending', 'in_progress')
            ORDER BY created_at DESC, enrichment_request_id
            """,
            (pack_id, revision, reason),
        ).fetchall()
        requested_signature = tuple(normalized_targets)
        for row in existing_requests:
            enrichment_request_id = str(row["enrichment_request_id"])
            current_signature = self._fetch_enrichment_target_signature(
                connection,
                enrichment_request_id=enrichment_request_id,
            )
            if current_signature == requested_signature:
                return {
                    "merged": True,
                    "request": self.fetch_enrichment_requests(
                        enrichment_request_id=enrichment_request_id,
                        limit=1,
                        connection=connection,
                    )[0],
                    "targets": self.fetch_enrichment_request_targets(
                        enrichment_request_id=enrichment_request_id,
                        connection=connection,
                    ),
                }

        created_at = datetime.now(UTC)
        request = EnrichmentRequest(
            enrichment_request_id=f"enrreq:{pack_id}:{revision}:{uuid4().hex[:8]}",
            pack_id=pack_id,
            revision=revision,
            reason_code=reason,
            request_status=EnrichmentRequestStatus.PENDING,
            created_at=created_at,
            completed_at=None,
            execution_attempt_count=0,
        )
        connection.execute(
            """
            INSERT INTO enrichment_requests (
                enrichment_request_id,
                pack_id,
                revision,
                reason_code,
                request_status,
                created_at,
                completed_at,
                execution_attempt_count
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                request.enrichment_request_id,
                request.pack_id,
                request.revision,
                request.reason_code,
                request.request_status,
                request.created_at.isoformat(),
                None,
                request.execution_attempt_count,
            ),
        )
        targets_payload: list[EnrichmentRequestTarget] = []
        for resource_type, resource_id, target_attribute in normalized_targets:
            targets_payload.append(
                EnrichmentRequestTarget(
                    enrichment_request_target_id=f"enrtgt:{uuid4().hex[:12]}",
                    enrichment_request_id=request.enrichment_request_id,
                    resource_type=EnrichmentTargetResourceType(resource_type),
                    resource_id=resource_id,
                    target_attribute=target_attribute,
                    created_at=created_at,
                )
            )

        _executemany(
            connection,
            """
            INSERT INTO enrichment_request_targets (
                enrichment_request_target_id,
                enrichment_request_id,
                resource_type,
                resource_id,
                target_attribute,
                created_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    target.enrichment_request_target_id,
                    target.enrichment_request_id,
                    target.resource_type,
                    target.resource_id,
                    target.target_attribute,
                    target.created_at.isoformat(),
                )
                for target in targets_payload
            ],
        )
        return {
            "merged": False,
            "request": {
                "enrichment_request_id": request.enrichment_request_id,
                "pack_id": request.pack_id,
                "revision": request.revision,
                "reason_code": str(request.reason_code),
                "request_status": str(request.request_status),
                "created_at": request.created_at.isoformat(),
                "completed_at": None,
                "execution_attempt_count": request.execution_attempt_count,
            },
            "targets": [item.model_dump(mode="json") for item in targets_payload],
        }

    def fetch_enrichment_requests(
        self,
        *,
        enrichment_request_id: str | None = None,
        request_status: str | None = None,
        pack_id: str | None = None,
        revision: int | None = None,
        limit: int = 100,
        connection: psycopg.Connection | None = None,
    ) -> list[dict[str, object]]:
        if connection is None:
            with self._connect() as owned_connection:
                return self.fetch_enrichment_requests(
                    enrichment_request_id=enrichment_request_id,
                    request_status=request_status,
                    pack_id=pack_id,
                    revision=revision,
                    limit=limit,
                    connection=owned_connection,
                )

        clauses: list[str] = []
        params: list[object] = []
        if enrichment_request_id:
            clauses.append("enrichment_request_id = %s")
            params.append(enrichment_request_id)
        if request_status:
            clauses.append("request_status = %s")
            params.append(request_status)
        if pack_id:
            clauses.append("pack_id = %s")
            params.append(pack_id)
        if revision is not None:
            clauses.append("revision = %s")
            params.append(revision)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = connection.execute(
            f"""
            SELECT
                enrichment_request_id,
                pack_id,
                revision,
                reason_code,
                request_status,
                created_at,
                completed_at,
                execution_attempt_count
            FROM enrichment_requests
            {where_clause}
            ORDER BY created_at DESC, enrichment_request_id
            LIMIT %s
            """,
            [*params, limit],
        ).fetchall()
        return [
            {
                "enrichment_request_id": str(row["enrichment_request_id"]),
                "pack_id": str(row["pack_id"]),
                "revision": int(row["revision"]),
                "reason_code": str(row["reason_code"]),
                "request_status": str(row["request_status"]),
                "created_at": row["created_at"].isoformat(),
                "completed_at": row["completed_at"].isoformat()
                if row["completed_at"] is not None
                else None,
                "execution_attempt_count": int(row["execution_attempt_count"]),
            }
            for row in rows
        ]

    def fetch_enrichment_request_targets(
        self,
        *,
        enrichment_request_id: str,
        connection: psycopg.Connection | None = None,
    ) -> list[dict[str, object]]:
        if connection is None:
            with self._connect() as owned_connection:
                return self.fetch_enrichment_request_targets(
                    enrichment_request_id=enrichment_request_id,
                    connection=owned_connection,
                )

        rows = connection.execute(
            """
            SELECT
                enrichment_request_target_id,
                enrichment_request_id,
                resource_type,
                resource_id,
                target_attribute,
                created_at
            FROM enrichment_request_targets
            WHERE enrichment_request_id = %s
            ORDER BY resource_type, resource_id, target_attribute, enrichment_request_target_id
            """,
            (enrichment_request_id,),
        ).fetchall()
        return [
            {
                "enrichment_request_target_id": str(row["enrichment_request_target_id"]),
                "enrichment_request_id": str(row["enrichment_request_id"]),
                "resource_type": str(row["resource_type"]),
                "resource_id": str(row["resource_id"]),
                "target_attribute": str(row["target_attribute"]),
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ]

    def fetch_enrichment_executions(
        self,
        *,
        enrichment_request_id: str | None = None,
        limit: int = 100,
        connection: psycopg.Connection | None = None,
    ) -> list[dict[str, object]]:
        if connection is None:
            with self._connect() as owned_connection:
                return self.fetch_enrichment_executions(
                    enrichment_request_id=enrichment_request_id,
                    limit=limit,
                    connection=owned_connection,
                )

        clauses: list[str] = []
        params: list[object] = []
        if enrichment_request_id:
            clauses.append("enrichment_request_id = %s")
            params.append(enrichment_request_id)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = connection.execute(
            f"""
            SELECT
                enrichment_execution_id,
                enrichment_request_id,
                execution_status,
                executed_at,
                execution_context_json,
                error_info
            FROM enrichment_executions
            {where_clause}
            ORDER BY executed_at DESC, enrichment_execution_id
            LIMIT %s
            """,
            [*params, limit],
        ).fetchall()
        return [
            {
                "enrichment_execution_id": str(row["enrichment_execution_id"]),
                "enrichment_request_id": str(row["enrichment_request_id"]),
                "execution_status": str(row["execution_status"]),
                "executed_at": row["executed_at"].isoformat(),
                "execution_context": json.loads(str(row["execution_context_json"])),
                "error_info": row["error_info"],
            }
            for row in rows
        ]

    def record_enrichment_execution(
        self,
        *,
        enrichment_request_id: str,
        execution_status: str,
        execution_context: dict[str, object] | None = None,
        error_info: str | None = None,
        trigger_recompile: bool = False,
        connection: psycopg.Connection | None = None,
    ) -> dict[str, object]:
        if connection is None:
            with self._connect() as owned_connection:
                return self.record_enrichment_execution(
                    enrichment_request_id=enrichment_request_id,
                    execution_status=execution_status,
                    execution_context=execution_context,
                    error_info=error_info,
                    trigger_recompile=trigger_recompile,
                    connection=owned_connection,
                )

        request_row = connection.execute(
            """
            SELECT pack_id, revision
            FROM enrichment_requests
            WHERE enrichment_request_id = %s
            """,
            (enrichment_request_id,),
        ).fetchone()
        if request_row is None:
            raise ValueError(f"Unknown enrichment_request_id: {enrichment_request_id}")

        status = EnrichmentExecutionStatus(execution_status)
        executed_at = datetime.now(UTC)
        execution = EnrichmentExecution(
            enrichment_execution_id=f"enrexec:{enrichment_request_id}:{uuid4().hex[:8]}",
            enrichment_request_id=enrichment_request_id,
            execution_status=status,
            executed_at=executed_at,
            execution_context=execution_context or {},
            error_info=error_info,
        )
        connection.execute(
            """
            INSERT INTO enrichment_executions (
                enrichment_execution_id,
                enrichment_request_id,
                execution_status,
                executed_at,
                execution_context_json,
                error_info
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                execution.enrichment_execution_id,
                execution.enrichment_request_id,
                execution.execution_status,
                execution.executed_at.isoformat(),
                _json(execution.execution_context),
                execution.error_info,
            ),
        )

        next_status = (
            EnrichmentRequestStatus.COMPLETED
            if status in (EnrichmentExecutionStatus.SUCCESS, EnrichmentExecutionStatus.PARTIAL)
            else EnrichmentRequestStatus.FAILED
        )
        completed_at = executed_at if next_status == EnrichmentRequestStatus.COMPLETED else None
        connection.execute(
            """
            UPDATE enrichment_requests
            SET request_status = %s,
                completed_at = %s,
                execution_attempt_count = execution_attempt_count + 1
            WHERE enrichment_request_id = %s
            """,
            (
                next_status,
                completed_at.isoformat() if completed_at else None,
                enrichment_request_id,
            ),
        )

        recompilation_result: dict[str, object] | None = None
        if trigger_recompile and status in (
            EnrichmentExecutionStatus.SUCCESS,
            EnrichmentExecutionStatus.PARTIAL,
        ):
            pack_id = str(request_row["pack_id"])
            revision = int(request_row["revision"])
            diagnostic = self._pack_store.diagnose_pack(
                pack_id=pack_id,
                revision=revision,
                connection=connection,
            )
            recompilation_result = {
                "attempted": True,
                "pack_id": pack_id,
                "revision": revision,
                "diagnostic_reason_code": diagnostic["reason_code"],
                "compiled_build_id": None,
            }
            if diagnostic["compilable"]:
                compiled = self._pack_store.compile_pack(
                    pack_id=pack_id,
                    revision=revision,
                    question_count=MIN_PACK_TOTAL_QUESTIONS,
                    connection=connection,
                )
                recompilation_result["compiled_build_id"] = compiled["build_id"]

        return {
            "enrichment_execution_id": execution.enrichment_execution_id,
            "enrichment_request_id": execution.enrichment_request_id,
            "execution_status": str(execution.execution_status),
            "executed_at": execution.executed_at.isoformat(),
            "request_status": str(next_status),
            "trigger_recompile": trigger_recompile,
            "recompilation": recompilation_result,
        }

    def fetch_enrichment_queue_metrics(self) -> dict[str, object]:
        with self._connect() as connection:
            status_rows = connection.execute(
                """
                SELECT request_status, COUNT(*) AS count
                FROM enrichment_requests
                GROUP BY request_status
                """
            ).fetchall()
            status_counts: dict[str, int] = {
                "pending": 0,
                "in_progress": 0,
                "completed": 0,
                "failed": 0,
            }
            for row in status_rows:
                status_counts[str(row["request_status"])] = int(row["count"])

            totals_row = connection.execute(
                """
                SELECT
                    COUNT(*) AS requests_total,
                    COALESCE(SUM(execution_attempt_count), 0) AS attempts_total
                FROM enrichment_requests
                """
            ).fetchone()
            executions_total = int(
                connection.execute(
                    "SELECT COUNT(*) AS count FROM enrichment_executions"
                ).fetchone()["count"]
            )
            oldest_pending_row = connection.execute(
                """
                SELECT created_at
                FROM enrichment_requests
                WHERE request_status = 'pending'
                ORDER BY created_at ASC
                LIMIT 1
                """
            ).fetchone()
            oldest_pending_age_hours = 0.0
            if oldest_pending_row is not None:
                created_at = oldest_pending_row["created_at"]
                oldest_pending_age_hours = round(
                    (datetime.now(UTC) - created_at).total_seconds() / 3600.0,
                    2,
                )

            return {
                "requests_total": int(totals_row["requests_total"]),
                "executions_total": executions_total,
                "attempts_total": int(totals_row["attempts_total"]),
                "status_counts": status_counts,
                "oldest_pending_age_hours": oldest_pending_age_hours,
            }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _normalize_enrichment_targets(
        self,
        targets: Sequence[dict[str, object]],
    ) -> list[tuple[str, str, str]]:
        normalized: set[tuple[str, str, str]] = set()
        for target in targets:
            resource_type = str(target.get("resource_type") or "").strip()
            resource_id = str(target.get("resource_id") or "").strip()
            target_attribute = str(target.get("target_attribute") or "").strip()
            if not resource_type or not resource_id or not target_attribute:
                continue
            normalized.add((resource_type, resource_id, target_attribute))
        return sorted(normalized)

    def _fetch_enrichment_target_signature(
        self,
        connection: psycopg.Connection,
        *,
        enrichment_request_id: str,
    ) -> tuple[tuple[str, str, str], ...]:
        rows = connection.execute(
            """
            SELECT resource_type, resource_id, target_attribute
            FROM enrichment_request_targets
            WHERE enrichment_request_id = %s
            ORDER BY resource_type, resource_id, target_attribute
            """,
            (enrichment_request_id,),
        ).fetchall()
        return tuple(
            (
                str(row["resource_type"]),
                str(row["resource_id"]),
                str(row["target_attribute"]),
            )
            for row in rows
        )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _executemany(
    connection: psycopg.Connection,
    query: str,
    params_seq: Sequence[tuple[object, ...]],
) -> None:
    if not params_seq:
        return
    with connection.cursor() as cursor:
        cursor.executemany(query, params_seq)
