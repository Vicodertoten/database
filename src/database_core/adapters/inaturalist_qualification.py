from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Protocol
from urllib.error import HTTPError, URLError

from database_core.adapters.inaturalist_snapshot import (
    DEFAULT_INAT_SNAPSHOT_ROOT,
    load_snapshot_dataset,
    load_snapshot_manifest,
    write_snapshot_manifest,
)
from database_core.export.json_exporter import write_json
from database_core.qualification.ai import (
    AIQualifier,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GEMINI_PROMPT_VERSION,
    GeminiVisionQualifier,
    build_ai_outputs_payload,
    collect_ai_qualification_outcomes,
)

DEFAULT_REQUEST_INTERVAL_SECONDS = 4.5
DEFAULT_MAX_RETRIES = 4
DEFAULT_INITIAL_BACKOFF_SECONDS = 5.0
DEFAULT_MAX_BACKOFF_SECONDS = 60.0


class SleepFunc(Protocol):
    def __call__(self, delay_seconds: float, /) -> None: ...


class ClockFunc(Protocol):
    def __call__(self) -> float: ...


@dataclass(frozen=True)
class SnapshotQualificationResult:
    snapshot_id: str
    snapshot_dir: Path
    ai_outputs_path: Path
    processed_media_count: int
    images_sent_to_gemini_count: int
    ai_valid_output_count: int
    insufficient_resolution_count: int


def qualify_inat_snapshot(
    *,
    snapshot_id: str,
    snapshot_root: Path = DEFAULT_INAT_SNAPSHOT_ROOT,
    gemini_api_key: str,
    gemini_model: str = DEFAULT_GEMINI_MODEL,
    prompt_version: str = DEFAULT_GEMINI_PROMPT_VERSION,
    request_interval_seconds: float = DEFAULT_REQUEST_INTERVAL_SECONDS,
    max_retries: int = DEFAULT_MAX_RETRIES,
    initial_backoff_seconds: float = DEFAULT_INITIAL_BACKOFF_SECONDS,
    max_backoff_seconds: float = DEFAULT_MAX_BACKOFF_SECONDS,
    qualifier: AIQualifier | None = None,
) -> SnapshotQualificationResult:
    manifest, snapshot_dir = load_snapshot_manifest(snapshot_id=snapshot_id, snapshot_root=snapshot_root)
    dataset = load_snapshot_dataset(snapshot_id=snapshot_id, snapshot_root=snapshot_root)
    if qualifier is None:
        qualifier = PacingRetryQualifier(
            base_qualifier=GeminiVisionQualifier(api_key=gemini_api_key, model_name=gemini_model),
            request_interval_seconds=request_interval_seconds,
            max_retries=max_retries,
            initial_backoff_seconds=initial_backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
        )

    outcomes = collect_ai_qualification_outcomes(
        dataset.media_assets,
        qualifier_mode="gemini",
        cached_image_paths_by_source_media_id=dataset.cached_image_paths_by_source_media_id,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        prompt_version=prompt_version,
        qualifier=qualifier,
    )

    ai_outputs_path = snapshot_dir / "ai_outputs.json"
    write_json(ai_outputs_path, build_ai_outputs_payload(outcomes))
    write_snapshot_manifest(
        snapshot_dir,
        manifest.model_copy(update={"ai_outputs_path": ai_outputs_path.name}),
    )

    images_sent_to_gemini_count = len(
        [
            item
            for item in outcomes.values()
            if item.status not in {"missing_cached_image", "insufficient_resolution"}
        ]
    )
    ai_valid_output_count = len([item for item in outcomes.values() if item.status == "ok"])
    insufficient_resolution_count = len(
        [item for item in outcomes.values() if item.status == "insufficient_resolution"]
    )

    return SnapshotQualificationResult(
        snapshot_id=manifest.snapshot_id,
        snapshot_dir=snapshot_dir,
        ai_outputs_path=ai_outputs_path,
        processed_media_count=len(outcomes),
        images_sent_to_gemini_count=images_sent_to_gemini_count,
        ai_valid_output_count=ai_valid_output_count,
        insufficient_resolution_count=insufficient_resolution_count,
    )


class PacingRetryQualifier:
    def __init__(
        self,
        *,
        base_qualifier: AIQualifier,
        request_interval_seconds: float = DEFAULT_REQUEST_INTERVAL_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_backoff_seconds: float = DEFAULT_INITIAL_BACKOFF_SECONDS,
        max_backoff_seconds: float = DEFAULT_MAX_BACKOFF_SECONDS,
        sleep_func: SleepFunc = time.sleep,
        clock_func: ClockFunc = time.monotonic,
    ) -> None:
        self.base_qualifier = base_qualifier
        self.request_interval_seconds = max(0.0, request_interval_seconds)
        self.max_retries = max(0, max_retries)
        self.initial_backoff_seconds = max(0.0, initial_backoff_seconds)
        self.max_backoff_seconds = max(self.initial_backoff_seconds, max_backoff_seconds)
        self._sleep = sleep_func
        self._clock = clock_func
        self._last_request_started_at: float | None = None

    def qualify(self, media_asset, *, image_bytes: bytes | None = None):
        retry_count = 0
        backoff_seconds = self.initial_backoff_seconds

        while True:
            self._sleep_for_pacing()
            self._last_request_started_at = self._clock()
            try:
                return self.base_qualifier.qualify(media_asset, image_bytes=image_bytes)
            except Exception as exc:  # noqa: BLE001
                if not _is_retryable_gemini_error(exc) or retry_count >= self.max_retries:
                    raise
                self._sleep(_retry_delay_seconds(exc, backoff_seconds, self.max_backoff_seconds))
                backoff_seconds = min(max(backoff_seconds * 2, self.initial_backoff_seconds), self.max_backoff_seconds)
                retry_count += 1

    def _sleep_for_pacing(self) -> None:
        if self._last_request_started_at is None or self.request_interval_seconds <= 0:
            return
        elapsed = self._clock() - self._last_request_started_at
        remaining = self.request_interval_seconds - elapsed
        if remaining > 0:
            self._sleep(remaining)


def _is_retryable_gemini_error(exc: Exception) -> bool:
    if isinstance(exc, HTTPError):
        return exc.code in {408, 429, 500, 502, 503, 504}
    return isinstance(exc, (TimeoutError, URLError))


def _retry_delay_seconds(exc: Exception, fallback_seconds: float, max_backoff_seconds: float) -> float:
    retry_after_seconds = _parse_retry_after_seconds(exc)
    if retry_after_seconds is not None:
        return min(retry_after_seconds, max_backoff_seconds)
    return min(fallback_seconds, max_backoff_seconds)


def _parse_retry_after_seconds(exc: Exception) -> float | None:
    if not isinstance(exc, HTTPError) or exc.headers is None:
        return None
    retry_after = exc.headers.get("Retry-After")
    if retry_after is None:
        return None
    try:
        return max(0.0, float(retry_after))
    except ValueError:
        return None
