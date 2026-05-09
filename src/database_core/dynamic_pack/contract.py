from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import FormatChecker, ValidationError, validate

DEFAULT_PACK_POOL_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "pack_pool_v1.schema.json"
)
DEFAULT_SESSION_SNAPSHOT_SCHEMA_PATH = (
    Path(__file__).resolve().parents[3] / "schemas" / "session_snapshot_v1.schema.json"
)


def validate_pack_pool(
    payload: dict[str, object],
    *,
    schema_path: Path | None = None,
) -> None:
    resolved_schema_path = schema_path or DEFAULT_PACK_POOL_SCHEMA_PATH
    try:
        validate(
            instance=payload,
            schema=_load_schema(resolved_schema_path),
            format_checker=FormatChecker(),
        )
    except ValidationError as exc:
        location = ".".join(str(item) for item in exc.absolute_path) or "<root>"
        raise ValueError(f"Pack pool validation failed at {location}: {exc.message}") from exc


def validate_session_snapshot(
    payload: dict[str, object],
    *,
    schema_path: Path | None = None,
) -> None:
    resolved_schema_path = schema_path or DEFAULT_SESSION_SNAPSHOT_SCHEMA_PATH
    try:
        validate(
            instance=payload,
            schema=_load_schema(resolved_schema_path),
            format_checker=FormatChecker(),
        )
    except ValidationError as exc:
        location = ".".join(str(item) for item in exc.absolute_path) or "<root>"
        raise ValueError(
            f"Session snapshot validation failed at {location}: {exc.message}"
        ) from exc


@lru_cache(maxsize=4)
def _load_schema(schema_path: Path) -> dict[str, object]:
    return json.loads(schema_path.read_text(encoding="utf-8"))
