#!/usr/bin/env python
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv

LIVE_MINI_RUN_SCHEMA_VERSION = "pedagogical_media_profile_live_mini_run.v1"
DEFAULT_OUTPUT_PATH = Path(
    "docs/audits/evidence/pedagogical_media_profile_v1_live_mini_run.json"
)
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash-lite"
DEFAULT_SAMPLE_SIZE = 5
MIN_SAMPLE_SIZE = 5
MAX_SAMPLE_SIZE = 10

DECISION_READY = "READY_FOR_OPT_IN_PIPELINE_INTEGRATION"
DECISION_ADJUST = "ADJUST_PROMPT_OR_SCHEMA"
DECISION_INVESTIGATE = "INVESTIGATE_LIVE_FAILURES"
DECISION_SKIPPED = "SKIPPED_MISSING_CREDENTIALS"

REQUIRED_USAGE_SCORES = (
    "basic_identification",
    "field_observation",
    "confusion_learning",
    "morphology_learning",
    "species_card",
    "indirect_evidence_learning",
)

LOW_BASIC_IDENTIFICATION_THRESHOLD = 50
HIGH_INDIRECT_EVIDENCE_THRESHOLD = 80

_GEMINI_API_BASE = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
)


# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------


def _bootstrap_src_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    src_path = str(src)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a controlled live mini-run audit for pedagogical_media_profile.v1. "
            "Calls a live Gemini model on a small media sample, parses results, "
            "and produces a JSON evidence report."
        )
    )
    # Sample source (mutually exclusive modes)
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--snapshot-id",
        type=str,
        help="Snapshot id under data/raw/inaturalist to sample from.",
    )
    source_group.add_argument(
        "--sample-file",
        type=Path,
        help=(
            "Explicit JSON sample file: list of objects with media_url, "
            "expected_scientific_name, organism_group, optional mime_type, "
            "common_names, source_metadata, observation_context, locale_notes."
        ),
    )
    parser.add_argument(
        "--snapshot-root",
        type=Path,
        default=Path("data/raw/inaturalist"),
        help="Root directory for cached iNaturalist snapshots.",
    )
    parser.add_argument(
        "--snapshot-manifest-path",
        type=Path,
        help="Optional explicit manifest path (overrides --snapshot-id resolution).",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help=f"Live mini-run sample size ({MIN_SAMPLE_SIZE}-{MAX_SAMPLE_SIZE}).",
    )
    parser.add_argument(
        "--gemini-model",
        default=DEFAULT_GEMINI_MODEL,
    )
    parser.add_argument(
        "--gemini-api-key-env",
        default="GEMINI_API_KEY",
        help="Name of environment variable holding the Gemini API key.",
    )
    parser.add_argument(
        "--gemini-concurrency",
        type=int,
        default=1,
        help="Worker count for live Gemini requests (currently unused; reserved for future use).",
    )
    parser.add_argument(
        "--output-path",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="JSON evidence output path.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _to_int(value: object, *, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _usage_score(payload: dict[str, Any], key: str) -> int:
    usage = (payload.get("scores") or {}).get("usage_scores") or {}
    if not isinstance(usage, dict):
        return 0
    return _to_int(usage.get(key))


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _excerpt(text: str, *, max_length: int = 300) -> str:
    return text[:max_length] if len(text) > max_length else text


# ---------------------------------------------------------------------------
# Gemini HTTP call (isolated, no dependency on ai.py internals)
# ---------------------------------------------------------------------------


def _call_gemini_with_image(
    *,
    api_key: str,
    model_name: str,
    prompt_text: str,
    image_bytes: bytes,
    mime_type: str,
) -> str:
    """Send a Gemini generateContent request with text + inline image.

    Returns the raw text of the first candidate part.
    Raises GeminiLiveCallError on HTTP or parse failures.
    """
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt_text},
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": base64.b64encode(image_bytes).decode("ascii"),
                        }
                    },
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "mediaResolution": "MEDIA_RESOLUTION_HIGH",
        },
    }
    url = f"{_GEMINI_API_BASE}{model_name}:generateContent"
    request = urllib.request.Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            response_body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise GeminiLiveCallError(
            f"Gemini HTTP {exc.code}: {body[:400]}"
        ) from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise GeminiLiveCallError(f"Gemini network error: {exc}") from exc

    try:
        text = response_body["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GeminiLiveCallError(
            f"Unexpected Gemini response structure: {str(response_body)[:400]}"
        ) from exc
    return str(text)


class GeminiLiveCallError(RuntimeError):
    """Raised when the live Gemini call fails at the HTTP or parse level."""


# ---------------------------------------------------------------------------
# Image fetching
# ---------------------------------------------------------------------------


def _fetch_image_bytes(url: str, *, timeout: int = 30) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "database-media-audit/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _mime_type_from_url(url: str) -> str:
    url_lower = url.lower()
    if url_lower.endswith(".png"):
        return "image/png"
    if url_lower.endswith(".gif"):
        return "image/gif"
    if url_lower.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


# ---------------------------------------------------------------------------
# Sample item dataclass (plain dict contract)
# ---------------------------------------------------------------------------

# Each sample item dict has these keys:
#   media_id: str
#   media_url: str
#   mime_type: str
#   expected_scientific_name: str
#   organism_group: str
#   common_names: dict[str, str]
#   source_metadata: dict[str, object]
#   observation_context: dict[str, object]
#   locale_notes: str


def _load_sample_file(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"--sample-file must be a JSON array, got: {type(raw).__name__}")
    items: list[dict[str, Any]] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"Sample item {i} must be a JSON object")
        if not entry.get("media_url"):
            raise ValueError(f"Sample item {i} missing 'media_url'")
        if not entry.get("expected_scientific_name"):
            raise ValueError(f"Sample item {i} missing 'expected_scientific_name'")
        if not entry.get("organism_group"):
            raise ValueError(f"Sample item {i} missing 'organism_group'")
        items.append(
            {
                "media_id": str(entry.get("media_id") or f"sample_{i}"),
                "media_url": str(entry["media_url"]),
                "mime_type": str(
                    entry.get("mime_type") or _mime_type_from_url(str(entry["media_url"]))
                ),
                "expected_scientific_name": str(entry["expected_scientific_name"]),
                "organism_group": str(entry["organism_group"]),
                "common_names": dict(entry.get("common_names") or {}),
                "source_metadata": dict(entry.get("source_metadata") or {}),
                "observation_context": dict(entry.get("observation_context") or {}),
                "locale_notes": str(entry.get("locale_notes") or ""),
            }
        )
    return items


def _load_sample_from_snapshot(
    *,
    snapshot_id: str | None,
    snapshot_root: Path,
    snapshot_manifest_path: Path | None,
    sample_size: int,
) -> list[dict[str, Any]]:
    from database_core.adapters import load_snapshot_dataset
    from database_core.adapters.common import SourceExternalKey
    from database_core.domain.models import CanonicalTaxon

    dataset = load_snapshot_dataset(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        manifest_path=snapshot_manifest_path,
    )
    canonical_by_id: dict[str, CanonicalTaxon] = {
        taxon.canonical_taxon_id: taxon for taxon in dataset.canonical_taxa
    }
    source_key_for = dataset.cached_image_paths_by_source_media_key

    media_assets = sorted(dataset.media_assets, key=lambda m: m.source_media_id)
    sample_assets = media_assets[:sample_size]

    items: list[dict[str, Any]] = []
    for media in sample_assets:
        taxon = canonical_by_id.get(media.canonical_taxon_id or "")
        scientific_name = (
            taxon.accepted_scientific_name if taxon else (media.canonical_taxon_id or "unknown")
        )
        taxon_group_str = taxon.taxon_group.value if taxon else "unknown"

        # Resolve image source: prefer cached path, fall back to source_url
        from database_core.domain.enums import SourceName
        source_key: SourceExternalKey = (SourceName.INATURALIST, media.source_media_id)
        cached_path = source_key_for.get(source_key)
        media_url = (
            str(cached_path.as_uri()) if cached_path and cached_path.exists() else media.source_url
        )

        items.append(
            {
                "media_id": media.media_id,
                "media_url": media_url,
                "_cached_path": str(cached_path) if cached_path else None,
                "mime_type": media.mime_type or _mime_type_from_url(media.source_url),
                "expected_scientific_name": scientific_name,
                "organism_group": taxon_group_str,
                "common_names": {},
                "source_metadata": {
                    "source": "inaturalist",
                    "source_media_id": media.source_media_id,
                    "source_observation_uid": media.source_observation_uid,
                },
                "observation_context": {},
                "locale_notes": "",
            }
        )
    return items


# ---------------------------------------------------------------------------
# Per-item live run
# ---------------------------------------------------------------------------


def _run_single_item(
    item: dict[str, Any],
    *,
    api_key: str,
    model_name: str,
) -> dict[str, Any]:
    """Call the live model for one media item. Returns a per-item summary dict."""
    from database_core.qualification.pedagogical_media_profile_prompt_v1 import (
        build_pedagogical_media_profile_prompt_v1,
    )
    from database_core.qualification.pedagogical_media_profile_v1 import (
        parse_pedagogical_media_profile_v1,
    )

    media_id = item["media_id"]
    media_url = item["media_url"]
    mime_type = item["mime_type"]

    # Fetch image bytes
    cached_path_str = item.get("_cached_path")
    try:
        if cached_path_str and Path(cached_path_str).exists():
            image_bytes = Path(cached_path_str).read_bytes()
        else:
            image_bytes = _fetch_image_bytes(media_url)
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        return _item_error_summary(item, error=f"image_fetch_failed: {exc}")

    raw_output_sha256 = _sha256_hex(image_bytes)

    # Build prompt
    prompt_text = build_pedagogical_media_profile_prompt_v1(
        expected_scientific_name=item["expected_scientific_name"],
        organism_group=item["organism_group"],
        media_reference=media_url,
        common_names=item.get("common_names") or {},
        source_metadata=item.get("source_metadata") or {},
        observation_context=item.get("observation_context") or {},
        locale_notes=item.get("locale_notes") or "",
    )

    # Live model call
    try:
        raw_text = _call_gemini_with_image(
            api_key=api_key,
            model_name=model_name,
            prompt_text=prompt_text,
            image_bytes=image_bytes,
            mime_type=mime_type,
        )
    except GeminiLiveCallError as exc:
        return _item_error_summary(item, error=f"gemini_call_failed: {exc}")

    raw_model_output_sha256 = _sha256_hex(raw_text.encode("utf-8"))
    raw_model_output_excerpt = _excerpt(raw_text)

    # Parse
    parsed = parse_pedagogical_media_profile_v1(raw_text, media_id=media_id)

    review_status = str(parsed.get("review_status") or "")
    failure_reason = str(parsed.get("failure_reason") or "") or None
    evidence_type = str(parsed.get("evidence_type") or "") or None
    organism_group_out = str(parsed.get("organism_group") or "") or None
    scores = parsed.get("scores") if isinstance(parsed.get("scores"), dict) else {}

    # Rejection detection from diagnostics
    diagnostics = parsed.get("diagnostics") if isinstance(parsed.get("diagnostics"), dict) else {}
    schema_errors = diagnostics.get("schema_errors") if isinstance(diagnostics, dict) else []
    if not isinstance(schema_errors, list):
        schema_errors = []

    feedback_rejection = False
    selection_field_rejection = False
    biological_basis_rejection = False

    feedback_keys = {"post_answer_feedback", "identification_tips", "feedback"}
    selection_keys = {
        "selected_for_quiz",
        "palier_1_core_eligible",
        "recommended_use",
        "runtime_ready",
        "playable",
        "scores",
    }

    for error in schema_errors:
        if not isinstance(error, dict):
            continue
        path = str(error.get("path") or "").lower()
        cause = str(error.get("cause") or "")
        if any(k in path for k in feedback_keys):
            feedback_rejection = True
        if any(k in path for k in selection_keys):
            selection_field_rejection = True
        if cause == "invalid_biological_basis":
            biological_basis_rejection = True

    return {
        "media_id": media_id,
        "expected_scientific_name": item["expected_scientific_name"],
        "organism_group_input": item["organism_group"],
        "organism_group_output": organism_group_out,
        "evidence_type": evidence_type,
        "review_status": review_status,
        "failure_reason": failure_reason,
        "global_quality_score": (
            _to_int(scores.get("global_quality_score")) if scores else None
        ),
        "usage_scores": (
            {k: _to_int(scores["usage_scores"].get(k)) for k in REQUIRED_USAGE_SCORES}
            if scores and isinstance(scores.get("usage_scores"), dict)
            else None
        ),
        "schema_failure_cause": (
            str(diagnostics.get("schema_failure_cause") or "") or None
            if diagnostics
            else None
        ),
        "schema_error_count": (
            _to_int(diagnostics.get("schema_error_count"))
            if diagnostics
            else 0
        ),
        "feedback_rejection": feedback_rejection,
        "selection_field_rejection": selection_field_rejection,
        "biological_basis_rejection": biological_basis_rejection,
        "raw_model_output_sha256": raw_model_output_sha256,
        "raw_model_output_excerpt": raw_model_output_excerpt,
        "image_sha256": raw_output_sha256,
    }


def _item_error_summary(item: dict[str, Any], *, error: str) -> dict[str, Any]:
    return {
        "media_id": item["media_id"],
        "expected_scientific_name": item["expected_scientific_name"],
        "organism_group_input": item["organism_group"],
        "organism_group_output": None,
        "evidence_type": None,
        "review_status": "failed",
        "failure_reason": "model_output_invalid",
        "global_quality_score": None,
        "usage_scores": None,
        "schema_failure_cause": None,
        "schema_error_count": 0,
        "feedback_rejection": False,
        "selection_field_rejection": False,
        "biological_basis_rejection": False,
        "raw_model_output_sha256": None,
        "raw_model_output_excerpt": None,
        "image_sha256": None,
        "error": error,
    }


# ---------------------------------------------------------------------------
# Metrics aggregation
# ---------------------------------------------------------------------------


def _compute_summary(
    per_item_results: list[dict[str, Any]],
    *,
    sample_size: int,
    model: str,
    gemini_api_key_env: str,
    gemini_concurrency: int,
) -> dict[str, Any]:
    valid_items = [r for r in per_item_results if r["review_status"] == "valid"]
    failed_items = [r for r in per_item_results if r["review_status"] != "valid"]

    valid_count = len(valid_items)
    failed_count = len(failed_items)

    failure_reason_distribution = dict(
        sorted(
            Counter(
                str(r.get("failure_reason") or "unknown_failure") for r in failed_items
            ).items()
        )
    )
    schema_failure_cause_distribution = dict(
        sorted(
            Counter(
                str(r.get("schema_failure_cause") or "none")
                for r in failed_items
                if r.get("schema_failure_cause")
            ).items()
        )
    )
    evidence_type_distribution = dict(
        sorted(
            Counter(
                str(r.get("evidence_type") or "unknown")
                for r in valid_items
            ).items()
        )
    )
    organism_group_distribution = dict(
        sorted(
            Counter(
                str(r.get("organism_group_output") or "unknown")
                for r in valid_items
            ).items()
        )
    )

    global_scores = [
        float(r["global_quality_score"])
        for r in valid_items
        if r.get("global_quality_score") is not None
    ]
    average_global_quality_score = _average(global_scores)

    usage_score_totals: dict[str, list[float]] = {k: [] for k in REQUIRED_USAGE_SCORES}
    for r in valid_items:
        usage = r.get("usage_scores")
        if not isinstance(usage, dict):
            continue
        for k in REQUIRED_USAGE_SCORES:
            usage_score_totals[k].append(float(_to_int(usage.get(k))))
    average_usage_scores = {k: _average(vs) for k, vs in usage_score_totals.items()}

    low_basic_identification_valid_count = sum(
        1 for r in valid_items
        if (r.get("usage_scores") or {}).get("basic_identification", 100)
        < LOW_BASIC_IDENTIFICATION_THRESHOLD
    )
    high_indirect_evidence_valid_count = sum(
        1 for r in valid_items
        if (r.get("usage_scores") or {}).get("indirect_evidence_learning", 0)
        >= HIGH_INDIRECT_EVIDENCE_THRESHOLD
    )

    feedback_rejection_count = sum(1 for r in per_item_results if r.get("feedback_rejection"))
    selection_field_rejection_count = sum(
        1 for r in per_item_results if r.get("selection_field_rejection")
    )
    biological_basis_rejection_count = sum(
        1 for r in per_item_results if r.get("biological_basis_rejection")
    )

    # Qualitative examples
    qualitative_examples: dict[str, Any] = {
        "valid_items": [
            {
                "media_id": r["media_id"],
                "evidence_type": r["evidence_type"],
                "organism_group": r["organism_group_output"],
                "global_quality_score": r["global_quality_score"],
                "raw_model_output_excerpt": r.get("raw_model_output_excerpt"),
            }
            for r in valid_items[:3]
        ],
        "failed_items": [
            {
                "media_id": r["media_id"],
                "failure_reason": r.get("failure_reason"),
                "schema_failure_cause": r.get("schema_failure_cause"),
                "raw_model_output_excerpt": r.get("raw_model_output_excerpt"),
            }
            for r in failed_items[:3]
        ],
    }

    return {
        "sample_size": sample_size,
        "model": model,
        "credential_env_name": gemini_api_key_env,
        "concurrency": gemini_concurrency,
        "valid_count": valid_count,
        "failed_count": failed_count,
        "failure_reason_distribution": failure_reason_distribution,
        "schema_failure_cause_distribution": schema_failure_cause_distribution,
        "evidence_type_distribution": evidence_type_distribution,
        "organism_group_distribution": organism_group_distribution,
        "average_global_quality_score": average_global_quality_score,
        "average_usage_scores": average_usage_scores,
        "low_basic_identification_valid_count": low_basic_identification_valid_count,
        "high_indirect_evidence_valid_count": high_indirect_evidence_valid_count,
        "feedback_rejection_count": feedback_rejection_count,
        "selection_field_rejection_count": selection_field_rejection_count,
        "biological_basis_rejection_count": biological_basis_rejection_count,
        "qualitative_examples": qualitative_examples,
    }


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------


def decide_live_mini_run_outcome(summary: dict[str, Any]) -> str:
    sample_size = int(summary.get("sample_size") or 0)
    if sample_size <= 0:
        return DECISION_INVESTIGATE

    valid_count = int(summary.get("valid_count") or 0)
    failed_count = int(summary.get("failed_count") or 0)
    valid_rate = valid_count / sample_size
    failed_rate = failed_count / sample_size

    feedback_rejection_count = int(summary.get("feedback_rejection_count") or 0)
    selection_field_rejection_count = int(summary.get("selection_field_rejection_count") or 0)

    failure_dist = summary.get("failure_reason_distribution") or {}
    model_output_invalid = int(failure_dist.get("model_output_invalid", 0))

    # Investigate conditions
    if valid_rate < 0.4:
        return DECISION_INVESTIGATE
    if model_output_invalid > 0:
        return DECISION_INVESTIGATE

    # Ready conditions
    if (
        sample_size >= MIN_SAMPLE_SIZE
        and valid_rate >= 0.8
        and failed_rate <= 0.2
        and feedback_rejection_count == 0
        and selection_field_rejection_count == 0
    ):
        return DECISION_READY

    # Adjust conditions: mostly schema/prompt misalignment
    if 0.4 <= valid_rate < 0.8:
        schema_fails = int(failure_dist.get("schema_validation_failed", 0))
        if failed_count > 0 and schema_fails / failed_count >= 0.5:
            return DECISION_ADJUST

    return DECISION_ADJUST


# ---------------------------------------------------------------------------
# Skipped report
# ---------------------------------------------------------------------------


def _skipped_report(
    *,
    run_id: str,
    gemini_api_key_env: str,
    gemini_model: str,
    gemini_concurrency: int,
    output_path: Path,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "sample_size": 0,
        "model": gemini_model,
        "credential_env_name": gemini_api_key_env,
        "concurrency": gemini_concurrency,
        "valid_count": 0,
        "failed_count": 0,
        "failure_reason_distribution": {},
        "schema_failure_cause_distribution": {},
        "evidence_type_distribution": {},
        "organism_group_distribution": {},
        "average_global_quality_score": 0.0,
        "average_usage_scores": {k: 0.0 for k in REQUIRED_USAGE_SCORES},
        "low_basic_identification_valid_count": 0,
        "high_indirect_evidence_valid_count": 0,
        "feedback_rejection_count": 0,
        "selection_field_rejection_count": 0,
        "biological_basis_rejection_count": 0,
        "qualitative_examples": {"valid_items": [], "failed_items": []},
        "skip_reason": "missing_live_credentials",
    }
    return {
        "schema_version": LIVE_MINI_RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "execution_status": "skipped_missing_credentials",
        "sample_size": 0,
        "model": gemini_model,
        "credential_env_name": gemini_api_key_env,
        "summary": summary,
        "per_item_results": [],
        "decision": DECISION_SKIPPED,
        "decision_thresholds": _decision_thresholds(),
        "notes": {
            "message": "Live mini-run skipped: Gemini credentials are missing.",
            "gemini_api_key_env": gemini_api_key_env,
            "output_path": str(output_path),
        },
    }


def _decision_thresholds() -> dict[str, Any]:
    return {
        DECISION_READY: {
            "sample_size_gte": MIN_SAMPLE_SIZE,
            "valid_rate_gte": 0.8,
            "failed_rate_lte": 0.2,
            "feedback_rejection_count_eq": 0,
            "selection_field_rejection_count_eq": 0,
            "model_output_invalid_count_eq": 0,
        },
        DECISION_ADJUST: {
            "valid_rate_gte": 0.4,
            "valid_rate_lt": 0.8,
            "dominant_schema_failures": True,
        },
        DECISION_INVESTIGATE: {
            "valid_rate_lt": 0.4,
            "or": [
                "frequent_model_output_invalid",
                "model_output_invalid_count_gt_0",
            ],
        },
    }


# ---------------------------------------------------------------------------
# Report validation
# ---------------------------------------------------------------------------


def validate_live_mini_run_report_schema(report: dict[str, Any]) -> bool:
    required_top = {
        "schema_version",
        "run_id",
        "generated_at",
        "execution_status",
        "sample_size",
        "model",
        "credential_env_name",
        "summary",
        "per_item_results",
        "decision",
        "decision_thresholds",
    }
    missing = sorted(required_top - set(report))
    if missing:
        raise ValueError(f"Missing required report keys: {missing}")
    if not isinstance(report.get("summary"), dict):
        raise ValueError("summary must be an object")
    if not isinstance(report.get("per_item_results"), list):
        raise ValueError("per_item_results must be a list")
    return True


# ---------------------------------------------------------------------------
# Main run function
# ---------------------------------------------------------------------------


def run_live_mini_audit(
    *,
    snapshot_id: str | None,
    snapshot_root: Path,
    snapshot_manifest_path: Path | None,
    sample_file: Path | None,
    sample_size: int,
    gemini_api_key: str | None,
    gemini_api_key_env: str,
    gemini_model: str,
    gemini_concurrency: int,
    output_path: Path,
) -> dict[str, Any]:
    run_id = f"audit:pedagogical-media-profile-v1-live-mini:{uuid4().hex[:8]}"

    if not gemini_api_key:
        return _skipped_report(
            run_id=run_id,
            gemini_api_key_env=gemini_api_key_env,
            gemini_model=gemini_model,
            gemini_concurrency=gemini_concurrency,
            output_path=output_path,
        )

    if sample_size < MIN_SAMPLE_SIZE or sample_size > MAX_SAMPLE_SIZE:
        raise ValueError(
            f"--sample-size must be between {MIN_SAMPLE_SIZE} and {MAX_SAMPLE_SIZE}."
        )

    if sample_file is not None:
        sample_items = _load_sample_file(sample_file)[:sample_size]
    elif snapshot_id is not None or snapshot_manifest_path is not None:
        sample_items = _load_sample_from_snapshot(
            snapshot_id=snapshot_id,
            snapshot_root=snapshot_root,
            snapshot_manifest_path=snapshot_manifest_path,
            sample_size=sample_size,
        )
    else:
        raise ValueError(
            "One of --sample-file, --snapshot-id, or --snapshot-manifest-path is required "
            "for a live run."
        )

    actual_sample_size = len(sample_items)
    per_item_results: list[dict[str, Any]] = []
    for item in sample_items:
        result = _run_single_item(item, api_key=gemini_api_key, model_name=gemini_model)
        per_item_results.append(result)

    summary = _compute_summary(
        per_item_results,
        sample_size=actual_sample_size,
        model=gemini_model,
        gemini_api_key_env=gemini_api_key_env,
        gemini_concurrency=gemini_concurrency,
    )
    decision = decide_live_mini_run_outcome(summary)

    report: dict[str, Any] = {
        "schema_version": LIVE_MINI_RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "execution_status": "completed",
        "sample_size": actual_sample_size,
        "model": gemini_model,
        "credential_env_name": gemini_api_key_env,
        "requested_sample_size": sample_size,
        "summary": summary,
        "per_item_results": per_item_results,
        "decision": decision,
        "decision_thresholds": _decision_thresholds(),
    }
    validate_live_mini_run_report_schema(report)
    return report


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    load_dotenv(dotenv_path=Path(".env"))
    _bootstrap_src_path()
    args = _parse_args()

    gemini_api_key = os.environ.get(args.gemini_api_key_env)
    report = run_live_mini_audit(
        snapshot_id=args.snapshot_id if hasattr(args, "snapshot_id") else None,
        snapshot_root=args.snapshot_root,
        snapshot_manifest_path=args.snapshot_manifest_path,
        sample_file=args.sample_file if hasattr(args, "sample_file") else None,
        sample_size=args.sample_size,
        gemini_api_key=gemini_api_key,
        gemini_api_key_env=args.gemini_api_key_env,
        gemini_model=args.gemini_model,
        gemini_concurrency=args.gemini_concurrency,
        output_path=args.output_path,
    )

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "pedagogical_media_profile.v1 live mini-run audit | "
        f"execution_status={report['execution_status']} | "
        f"sample_size={report['sample_size']} | "
        f"decision={report['decision']} | "
        f"output={args.output_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
