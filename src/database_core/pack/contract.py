from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import FormatChecker, ValidationError, validate

DEFAULT_PACK_SPEC_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "pack_spec_v1.schema.json"
)
DEFAULT_PACK_DIAGNOSTIC_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "pack_diagnostic_v1.schema.json"
)
DEFAULT_COMPILED_PACK_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "pack_compiled_v1.schema.json"
)
DEFAULT_PACK_MATERIALIZATION_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "pack_materialization_v1.schema.json"
)
DEFAULT_COMPILED_PACK_V2_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "pack_compiled_v2.schema.json"
)
DEFAULT_PACK_MATERIALIZATION_V2_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "pack_materialization_v2.schema.json"
)


def validate_pack_spec(
    payload: dict[str, object],
    *,
    schema_path: Path | None = None,
) -> None:
    resolved_schema_path = schema_path or DEFAULT_PACK_SPEC_SCHEMA_PATH
    try:
        validate(
            instance=payload,
            schema=_load_schema(resolved_schema_path),
            format_checker=FormatChecker(),
        )
    except ValidationError as exc:
        location = ".".join(str(item) for item in exc.absolute_path) or "<root>"
        raise ValueError(f"Pack spec validation failed at {location}: {exc.message}") from exc


def validate_pack_diagnostic(
    payload: dict[str, object],
    *,
    schema_path: Path | None = None,
) -> None:
    resolved_schema_path = schema_path or DEFAULT_PACK_DIAGNOSTIC_SCHEMA_PATH
    try:
        validate(
            instance=payload,
            schema=_load_schema(resolved_schema_path),
            format_checker=FormatChecker(),
        )
    except ValidationError as exc:
        location = ".".join(str(item) for item in exc.absolute_path) or "<root>"
        raise ValueError(f"Pack diagnostic validation failed at {location}: {exc.message}") from exc


def validate_compiled_pack(
    payload: dict[str, object],
    *,
    schema_path: Path | None = None,
) -> None:
    resolved_schema_path = schema_path or _compiled_pack_schema_path(payload)
    try:
        validate(
            instance=payload,
            schema=_load_schema(resolved_schema_path),
            format_checker=FormatChecker(),
        )
    except ValidationError as exc:
        location = ".".join(str(item) for item in exc.absolute_path) or "<root>"
        raise ValueError(f"Compiled pack validation failed at {location}: {exc.message}") from exc


def validate_pack_materialization(
    payload: dict[str, object],
    *,
    schema_path: Path | None = None,
) -> None:
    resolved_schema_path = schema_path or _pack_materialization_schema_path(payload)
    try:
        validate(
            instance=payload,
            schema=_load_schema(resolved_schema_path),
            format_checker=FormatChecker(),
        )
    except ValidationError as exc:
        location = ".".join(str(item) for item in exc.absolute_path) or "<root>"
        raise ValueError(
            f"Pack materialization validation failed at {location}: {exc.message}"
        ) from exc


def _compiled_pack_schema_path(payload: dict[str, object]) -> Path:
    version = payload.get("pack_compiled_version")
    if version == "pack.compiled.v2":
        return DEFAULT_COMPILED_PACK_V2_SCHEMA_PATH
    return DEFAULT_COMPILED_PACK_SCHEMA_PATH


def _pack_materialization_schema_path(payload: dict[str, object]) -> Path:
    version = payload.get("pack_materialization_version")
    if version == "pack.materialization.v2":
        return DEFAULT_PACK_MATERIALIZATION_V2_SCHEMA_PATH
    return DEFAULT_PACK_MATERIALIZATION_SCHEMA_PATH


@lru_cache(maxsize=8)
def _load_schema(schema_path: Path) -> dict[str, object]:
    return json.loads(schema_path.read_text(encoding="utf-8"))
