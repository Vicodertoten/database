from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import FormatChecker, ValidationError, validate

DEFAULT_PACK_CREATE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "pack_create_v1.schema.json"
)
DEFAULT_PACK_DIAGNOSE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "pack_diagnose_operation_v1.schema.json"
)
DEFAULT_PACK_COMPILE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "pack_compile_operation_v1.schema.json"
)
DEFAULT_PACK_MATERIALIZE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "pack_materialize_operation_v1.schema.json"
)
DEFAULT_ENRICHMENT_STATUS_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "enrichment_request_status_v1.schema.json"
)
DEFAULT_ENRICHMENT_ENQUEUE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "enrichment_enqueue_v1.schema.json"
)
DEFAULT_ENRICHMENT_EXECUTE_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "enrichment_execute_v1.schema.json"
)


def validate_pack_create_operation(
    payload: dict[str, object],
    *,
    schema_path: Path | None = None,
) -> None:
    _validate_with_schema(
        payload,
        schema_path or DEFAULT_PACK_CREATE_SCHEMA_PATH,
        "pack create operation",
    )


def validate_pack_diagnose_operation(
    payload: dict[str, object],
    *,
    schema_path: Path | None = None,
) -> None:
    _validate_with_schema(
        payload,
        schema_path or DEFAULT_PACK_DIAGNOSE_SCHEMA_PATH,
        "pack diagnose operation",
    )


def validate_pack_compile_operation(
    payload: dict[str, object],
    *,
    schema_path: Path | None = None,
) -> None:
    _validate_with_schema(
        payload,
        schema_path or DEFAULT_PACK_COMPILE_SCHEMA_PATH,
        "pack compile operation",
    )


def validate_pack_materialize_operation(
    payload: dict[str, object],
    *,
    schema_path: Path | None = None,
) -> None:
    _validate_with_schema(
        payload,
        schema_path or DEFAULT_PACK_MATERIALIZE_SCHEMA_PATH,
        "pack materialize operation",
    )


def validate_enrichment_status_operation(
    payload: dict[str, object],
    *,
    schema_path: Path | None = None,
) -> None:
    _validate_with_schema(
        payload,
        schema_path or DEFAULT_ENRICHMENT_STATUS_SCHEMA_PATH,
        "enrichment status operation",
    )


def validate_enrichment_enqueue_operation(
    payload: dict[str, object],
    *,
    schema_path: Path | None = None,
) -> None:
    _validate_with_schema(
        payload,
        schema_path or DEFAULT_ENRICHMENT_ENQUEUE_SCHEMA_PATH,
        "enrichment enqueue operation",
    )


def validate_enrichment_execute_operation(
    payload: dict[str, object],
    *,
    schema_path: Path | None = None,
) -> None:
    _validate_with_schema(
        payload,
        schema_path or DEFAULT_ENRICHMENT_EXECUTE_SCHEMA_PATH,
        "enrichment execute operation",
    )


def _validate_with_schema(
    payload: dict[str, object],
    schema_path: Path,
    label: str,
) -> None:
    try:
        validate(
            instance=payload,
            schema=_load_schema(schema_path),
            format_checker=FormatChecker(),
        )
    except ValidationError as exc:
        location = ".".join(str(item) for item in exc.absolute_path) or "<root>"
        raise ValueError(f"{label} validation failed at {location}: {exc.message}") from exc


@lru_cache(maxsize=8)
def _load_schema(schema_path: Path) -> dict[str, object]:
    return json.loads(schema_path.read_text(encoding="utf-8"))
