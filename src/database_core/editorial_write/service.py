from __future__ import annotations

from dataclasses import dataclass

from database_core.domain.enums import EnrichmentExecutionStatus, PackMaterializationPurpose
from database_core.domain.models import PackRevisionParameters
from database_core.editorial_write.contract import (
    validate_enrichment_enqueue_operation,
    validate_enrichment_execute_operation,
    validate_enrichment_status_operation,
    validate_pack_compile_operation,
    validate_pack_create_operation,
    validate_pack_diagnose_operation,
    validate_pack_materialize_operation,
)
from database_core.pack import (
    validate_compiled_pack,
    validate_pack_diagnostic,
    validate_pack_materialization,
    validate_pack_spec,
)
from database_core.storage.enrichment_store import PostgresEnrichmentStore
from database_core.storage.pack_store import MIN_PACK_TOTAL_QUESTIONS, PostgresPackStore
from database_core.storage.services import build_storage_services
from database_core.versioning import SCHEMA_VERSION_LABEL


@dataclass(frozen=True)
class EditorialWriteOwnerService:
    """Owner-side write facade limited to editorial pack/enrichment operations."""

    pack_store: PostgresPackStore
    enrichment_store: PostgresEnrichmentStore

    def create_pack(self, *, payload: dict[str, object]) -> dict[str, object]:
        pack_id = payload.get("pack_id")
        if pack_id is not None and not isinstance(pack_id, str):
            raise ValueError("pack_id must be a string when provided")

        raw_parameters = payload.get("parameters")
        if not isinstance(raw_parameters, dict):
            raise ValueError("parameters object is required")

        parameters = PackRevisionParameters(**raw_parameters)
        result = self.pack_store.create_pack(
            pack_id=pack_id,
            parameters=parameters,
        )
        validate_pack_spec(result)
        envelope = _build_envelope(
            operation_version="pack.create.v1",
            operation="create_pack",
            payload=result,
        )
        validate_pack_create_operation(envelope)
        return envelope

    def diagnose_pack(self, *, pack_id: str, revision: int | None = None) -> dict[str, object]:
        result = self.pack_store.diagnose_pack(pack_id=pack_id, revision=revision)
        validate_pack_diagnostic(result)
        envelope = _build_envelope(
            operation_version="pack.diagnose.v1",
            operation="diagnose_pack",
            payload=result,
        )
        validate_pack_diagnose_operation(envelope)
        return envelope

    def compile_pack(
        self,
        *,
        pack_id: str,
        revision: int | None = None,
        question_count: int = MIN_PACK_TOTAL_QUESTIONS,
    ) -> dict[str, object]:
        result = self.pack_store.compile_pack(
            pack_id=pack_id,
            revision=revision,
            question_count=question_count,
        )
        validate_compiled_pack(result)
        envelope = _build_envelope(
            operation_version="pack.compile.v1",
            operation="compile_pack",
            payload=result,
        )
        validate_pack_compile_operation(envelope)
        return envelope

    def materialize_pack(
        self,
        *,
        pack_id: str,
        revision: int | None = None,
        question_count: int = MIN_PACK_TOTAL_QUESTIONS,
        purpose: str = "assignment",
        ttl_hours: int | None = None,
    ) -> dict[str, object]:
        resolved_purpose = str(PackMaterializationPurpose(purpose))
        result = self.pack_store.materialize_pack(
            pack_id=pack_id,
            revision=revision,
            question_count=question_count,
            purpose=resolved_purpose,
            ttl_hours=ttl_hours,
        )
        validate_pack_materialization(result)
        envelope = _build_envelope(
            operation_version="pack.materialize.v1",
            operation="materialize_pack",
            payload=result,
        )
        validate_pack_materialize_operation(envelope)
        return envelope

    def get_enrichment_request_status(self, *, enrichment_request_id: str) -> dict[str, object]:
        requests = self.enrichment_store.fetch_enrichment_requests(
            enrichment_request_id=enrichment_request_id,
            limit=1,
        )
        if not requests:
            raise ValueError(f"Unknown enrichment_request_id: {enrichment_request_id}")

        envelope = _build_envelope(
            operation_version="enrichment.request.status.v1",
            operation="enrichment_request_status",
            payload=requests[0],
        )
        validate_enrichment_status_operation(envelope)
        return envelope

    def enqueue_enrichment(
        self,
        *,
        pack_id: str,
        revision: int | None = None,
        question_count: int = MIN_PACK_TOTAL_QUESTIONS,
    ) -> dict[str, object]:
        result = self.enrichment_store.enqueue_enrichment_for_pack(
            pack_id=pack_id,
            revision=revision,
            question_count=question_count,
        )
        envelope = _build_envelope(
            operation_version="enrichment.enqueue.v1",
            operation="enqueue_enrichment",
            payload=result,
        )
        validate_enrichment_enqueue_operation(envelope)
        return envelope

    def execute_enrichment(
        self,
        *,
        enrichment_request_id: str,
        execution_status: str = str(EnrichmentExecutionStatus.SUCCESS),
        execution_context: dict[str, object] | None = None,
        error_info: str | None = None,
        trigger_recompile: bool = False,
    ) -> dict[str, object]:
        resolved_status = str(EnrichmentExecutionStatus(execution_status))
        result = self.enrichment_store.record_enrichment_execution(
            enrichment_request_id=enrichment_request_id,
            execution_status=resolved_status,
            execution_context=execution_context,
            error_info=error_info,
            trigger_recompile=trigger_recompile,
        )
        envelope = _build_envelope(
            operation_version="enrichment.execute.v1",
            operation="execute_enrichment",
            payload=result,
        )
        validate_enrichment_execute_operation(envelope)
        return envelope


def build_editorial_write_owner_service(database_url: str) -> EditorialWriteOwnerService:
    storage_services = build_storage_services(database_url)
    return EditorialWriteOwnerService(
        pack_store=storage_services.pack_store,
        enrichment_store=storage_services.enrichment_store,
    )


def _build_envelope(
    *,
    operation_version: str,
    operation: str,
    payload: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION_LABEL,
        "operation_version": operation_version,
        "operation": operation,
        "status": "succeeded",
        "payload": payload,
    }
