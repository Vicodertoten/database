from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TextIO
from urllib.error import HTTPError, URLError

from database_core.adapters.inaturalist_snapshot import (
    DEFAULT_INAT_SNAPSHOT_ROOT,
    InaturalistSnapshotManifest,
    load_snapshot_dataset,
    load_snapshot_manifest,
    write_snapshot_manifest,
)
from database_core.export.json_exporter import write_json
from database_core.qualification.ai import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GEMINI_PROMPT_VERSION,
    MIN_AI_IMAGE_HEIGHT,
    MIN_AI_IMAGE_WIDTH,
    AIQualificationOutcome,
    AIQualifier,
    GeminiRequestError,
    GeminiVisionQualifier,
    build_ai_outputs_payload,
    collect_ai_qualification_outcomes,
    inspect_image_dimensions,
    source_external_key_for_media,
)

DEFAULT_REQUEST_INTERVAL_SECONDS = 0.5
DEFAULT_MAX_RETRIES = 2
DEFAULT_INITIAL_BACKOFF_SECONDS = 1.0
DEFAULT_MAX_BACKOFF_SECONDS = 8.0
MIN_PRE_AI_BLUR_SCORE = 10.0
PRE_AI_REJECTION_REASONS = {
    "insufficient_resolution_pre_ai",
    "decode_error_pre_ai",
    "blur_pre_ai",
    "duplicate_pre_ai",
}


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
    pre_ai_rejection_count: int = 0


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
    progress_stream: TextIO | None = None,
) -> SnapshotQualificationResult:
    manifest, snapshot_dir = load_snapshot_manifest(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
    )
    dataset = load_snapshot_dataset(snapshot_id=snapshot_id, snapshot_root=snapshot_root)
    if qualifier is None:
        qualifier = PacingRetryQualifier(
            base_qualifier=GeminiVisionQualifier(api_key=gemini_api_key, model_name=gemini_model),
            request_interval_seconds=request_interval_seconds,
            max_retries=max_retries,
            initial_backoff_seconds=initial_backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
        )

    resolved_progress_stream = sys.stdout if progress_stream is None else progress_stream
    pre_ai_rejections_by_source_media_id = _compute_pre_ai_rejections(
        manifest=manifest,
        snapshot_dir=snapshot_dir,
    )
    eligible_media_assets = [
        media for media in dataset.media_assets
        if media.source_media_id not in pre_ai_rejections_by_source_media_id
    ]

    if resolved_progress_stream is not None:
        print(
            "Starting Gemini qualification | "
            f"snapshot_id={manifest.snapshot_id} | "
            f"media={len(dataset.media_assets)} | "
            f"pre_ai_filtered={len(pre_ai_rejections_by_source_media_id)} | "
            f"request_interval_seconds={request_interval_seconds}",
            file=resolved_progress_stream,
            flush=True,
        )

    gemini_outcomes = collect_ai_qualification_outcomes(
        eligible_media_assets,
        qualifier_mode="gemini",
        cached_image_paths_by_source_media_key=dataset.cached_image_paths_by_source_media_key,
        gemini_api_key=gemini_api_key,
        gemini_model=gemini_model,
        prompt_version=prompt_version,
        qualifier=qualifier,
        progress_callback=_build_progress_callback(resolved_progress_stream),
    )
    outcomes: dict[object, AIQualificationOutcome] = dict(gemini_outcomes)
    media_by_source_media_id = {media.source_media_id: media for media in dataset.media_assets}
    for source_media_id, reason in pre_ai_rejections_by_source_media_id.items():
        media_asset = media_by_source_media_id[source_media_id]
        media_key = source_external_key_for_media(media_asset)
        outcomes[media_key] = AIQualificationOutcome(
            status=reason,
            qualification=None,
            flags=(reason,),
            note=f"pre-ai filtered ({reason}) for {source_media_id}",
            prompt_version=prompt_version,
        )

    ai_outputs_path = snapshot_dir / "ai_outputs.json"
    write_json(ai_outputs_path, build_ai_outputs_payload(outcomes))
    updated_media_downloads = []
    for item in manifest.media_downloads:
        updated_media_downloads.append(
            item.model_copy(
                update={
                    "pre_ai_rejection_reason": pre_ai_rejections_by_source_media_id.get(
                        item.source_media_id
                    )
                }
            )
        )
    write_snapshot_manifest(
        snapshot_dir,
        manifest.model_copy(
            update={
                "ai_outputs_path": ai_outputs_path.name,
                "media_downloads": updated_media_downloads,
            }
        ),
    )

    images_sent_to_gemini_count = len(
        [
            item
            for item in outcomes.values()
            if item.status
            not in {"missing_cached_image", "insufficient_resolution", *PRE_AI_REJECTION_REASONS}
        ]
    )
    ai_valid_output_count = len([item for item in outcomes.values() if item.status == "ok"])
    insufficient_resolution_count = len(
        [item for item in outcomes.values() if item.status == "insufficient_resolution"]
    )
    pre_ai_rejection_count = len(
        [item for item in outcomes.values() if item.status in PRE_AI_REJECTION_REASONS]
    )

    return SnapshotQualificationResult(
        snapshot_id=manifest.snapshot_id,
        snapshot_dir=snapshot_dir,
        ai_outputs_path=ai_outputs_path,
        processed_media_count=len(outcomes),
        images_sent_to_gemini_count=images_sent_to_gemini_count,
        ai_valid_output_count=ai_valid_output_count,
        insufficient_resolution_count=insufficient_resolution_count,
        pre_ai_rejection_count=pre_ai_rejection_count,
    )


def _compute_pre_ai_rejections(
    *,
    manifest: InaturalistSnapshotManifest,
    snapshot_dir: Path,
) -> dict[str, str]:
    rejections: dict[str, str] = {}
    seen_hashes: set[str] = set()
    for item in sorted(manifest.media_downloads, key=lambda entry: entry.source_media_id):
        if item.download_status != "downloaded":
            continue
        image_path = snapshot_dir / item.image_path
        if not image_path.exists():
            continue

        width = item.downloaded_width
        height = item.downloaded_height
        if width is None or height is None:
            width, height = inspect_image_dimensions(image_path)
            if width is None or height is None:
                rejections[item.source_media_id] = "decode_error_pre_ai"
                continue

        if width < MIN_AI_IMAGE_WIDTH or height < MIN_AI_IMAGE_HEIGHT:
            rejections[item.source_media_id] = "insufficient_resolution_pre_ai"
            continue

        if item.blur_score is not None and item.blur_score < MIN_PRE_AI_BLUR_SCORE:
            rejections[item.source_media_id] = "blur_pre_ai"
            continue

        image_hash = str(item.sha256 or "").strip()
        if image_hash:
            if image_hash in seen_hashes:
                rejections[item.source_media_id] = "duplicate_pre_ai"
                continue
            seen_hashes.add(image_hash)

    return rejections


def _build_progress_callback(
    progress_stream: TextIO | None,
) -> Callable[[int, int, object, object], None] | None:
    if progress_stream is None:
        return None

    def log_progress(index: int, total: int, media_asset, outcome) -> None:
        note = f" | note={outcome.note}" if getattr(outcome, "note", None) else ""
        print(
            "Gemini qualification progress | "
            f"{index}/{total} | "
            f"source_media_id={media_asset.source_media_id} | "
            f"status={outcome.status}{note}",
            file=progress_stream,
            flush=True,
        )

    return log_progress


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
            except (GeminiRequestError, HTTPError, TimeoutError, URLError, OSError) as exc:
                if not _is_retryable_gemini_error(exc) or retry_count >= self.max_retries:
                    raise
                self._sleep(_retry_delay_seconds(exc, backoff_seconds, self.max_backoff_seconds))
                backoff_seconds = min(
                    max(backoff_seconds * 2, self.initial_backoff_seconds),
                    self.max_backoff_seconds,
                )
                retry_count += 1

    def _sleep_for_pacing(self) -> None:
        if self._last_request_started_at is None or self.request_interval_seconds <= 0:
            return
        elapsed = self._clock() - self._last_request_started_at
        remaining = self.request_interval_seconds - elapsed
        if remaining > 0:
            self._sleep(remaining)


def _is_retryable_gemini_error(exc: Exception) -> bool:
    if isinstance(exc, GeminiRequestError):
        if exc.retryable:
            return True
        return exc.status_code in {408, 429, 500, 502, 503, 504}
    if isinstance(exc, HTTPError):
        return exc.code in {408, 429, 500, 502, 503, 504}
    return isinstance(exc, (TimeoutError, URLError))


def _retry_delay_seconds(
    exc: Exception,
    fallback_seconds: float,
    max_backoff_seconds: float,
) -> float:
    retry_after_seconds = _parse_retry_after_seconds(exc)
    if retry_after_seconds is not None:
        return min(retry_after_seconds, max_backoff_seconds)
    return min(fallback_seconds, max_backoff_seconds)


def _parse_retry_after_seconds(exc: Exception) -> float | None:
    if isinstance(exc, GeminiRequestError):
        return exc.retry_after_seconds
    if not isinstance(exc, HTTPError) or exc.headers is None:
        return None
    retry_after = exc.headers.get("Retry-After")
    if retry_after is None:
        return None
    try:
        return max(0.0, float(retry_after))
    except ValueError:
        return None
