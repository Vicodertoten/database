from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _bootstrap_src_path() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    src_path = str(src)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build and audit PedagogicalImageProfile v1 payloads from qualified/export/"
            "playable JSON inputs."
        )
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input-qualified", type=Path, help="Path to qualification snapshot JSON")
    group.add_argument("--input-export", type=Path, help="Path to export.bundle.v4 JSON")
    group.add_argument("--input-playable", type=Path, help="Path to playable_corpus.v1 JSON")
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("data/exports/pedagogical_image_profiles_audit.json"),
        help="Audit report output path",
    )
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def _safe_percentile(values: list[int], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = (len(sorted_values) - 1) * percentile
    low = math.floor(index)
    high = math.ceil(index)
    if low == high:
        return float(sorted_values[low])
    weight = index - low
    return float(sorted_values[low] * (1 - weight) + sorted_values[high] * weight)


def _average(values: list[int]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _input_fidelity(input_mode: str) -> dict[str, object]:
    if input_mode == "qualified":
        return {
            "level": "high",
            "score": 1.0,
            "source_contract": "qualification.staged.v1",
            "notes": [
                "Direct qualified resources payload with richest pedagogical "
                "and provenance fields.",
            ],
        }
    if input_mode == "export":
        return {
            "level": "medium",
            "score": 0.7,
            "source_contract": "export.bundle.v4",
            "notes": [
                "Some qualification fields are reconstructed for profiling.",
            ],
        }
    return {
        "level": "low",
        "score": 0.45,
        "source_contract": "playable_corpus.v1",
        "notes": [
            "Profile input is heavily reconstructed from runtime-facing payloads.",
        ],
    }


def main() -> int:
    _bootstrap_src_path()

    from database_core.domain.enums import PedagogicalProfileStatus, TaxonGroup
    from database_core.qualification.pedagogical_image_profile import (
        build_pedagogical_image_profile,
    )

    args = _parse_args()

    input_mode = "qualified"
    input_path = args.input_qualified
    if args.input_export is not None:
        input_mode = "export"
        input_path = args.input_export
    if args.input_playable is not None:
        input_mode = "playable"
        input_path = args.input_playable

    if input_path is None:
        raise ValueError("One input path must be provided")

    payload = _load_json(input_path)

    resources_and_assets: list[tuple[Any, Any]] = []
    if input_mode == "qualified":
        resources_and_assets = _from_qualified_snapshot(payload)
    elif input_mode == "export":
        resources_and_assets = _from_export_bundle(payload)
    else:
        resources_and_assets = _from_playable_corpus(payload)

    profiles = [
        build_pedagogical_image_profile(
            resource,
            media_asset=media_asset,
            taxon_group=TaxonGroup.BIRDS,
        )
        for resource, media_asset in resources_and_assets
    ]

    counts_by_status = Counter(profile.profile_status.value for profile in profiles)
    counts_by_band = Counter(profile.score_band.value for profile in profiles)
    counts_by_usage = Counter(
        usage.value
        for profile in profiles
        for usage in profile.recommended_usages
    )
    counts_by_warning = Counter(
        warning
        for profile in profiles
        for warning in profile.warnings
    )
    reason_counts = Counter(
        reason
        for profile in profiles
        for reason in profile.reason_codes
    )

    scores = [profile.overall_score for profile in profiles]

    per_taxon: dict[str, dict[str, int]] = {}
    for profile in profiles:
        taxon = profile.canonical_taxon_id
        if taxon not in per_taxon:
            per_taxon[taxon] = {
                "profiled_items": 0,
                "preferred_items_score_gte_85": 0,
                "beginner_suitable_items": 0,
                "feedback_suitable_items": 0,
            }

        if profile.profile_status in {
            PedagogicalProfileStatus.PROFILED,
            PedagogicalProfileStatus.PROFILED_WITH_WARNINGS,
        }:
            per_taxon[taxon]["profiled_items"] += 1
        if profile.overall_score >= 85:
            per_taxon[taxon]["preferred_items_score_gte_85"] += 1
        if profile.usage_scores.primary_question_beginner >= 70:
            per_taxon[taxon]["beginner_suitable_items"] += 1
        if profile.usage_scores.feedback_explanation >= 70:
            per_taxon[taxon]["feedback_suitable_items"] += 1

    count_missing_ai = sum(
        1
        for profile in profiles
        if profile.profile_status == PedagogicalProfileStatus.PENDING_AI
        or "hard_gate_missing_or_invalid_ai_qualification" in profile.reason_codes
    )

    report = {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "profile_version": "pedagogical_image_profile.v1",
        "input_fidelity": _input_fidelity(input_mode),
        "input": {
            "mode": input_mode,
            "path": str(input_path),
        },
        "total_resources": len(profiles),
        "counts_by_profile_status": dict(sorted(counts_by_status.items())),
        "distribution_by_score_band": dict(sorted(counts_by_band.items())),
        "overall_score_stats": {
            "average": _average(scores),
            "min": min(scores) if scores else 0,
            "max": max(scores) if scores else 0,
            "p10": round(_safe_percentile(scores, 0.10), 2),
            "median": round(_safe_percentile(scores, 0.50), 2),
            "p90": round(_safe_percentile(scores, 0.90), 2),
        },
        "counts_by_recommended_usage": dict(sorted(counts_by_usage.items())),
        "counts_by_warning": dict(sorted(counts_by_warning.items())),
        "top_reason_codes": [
            {"reason_code": code, "count": count}
            for code, count in reason_counts.most_common(20)
        ],
        "count_missing_ai": count_missing_ai,
        "count_manual_review_required": counts_by_status.get(
            PedagogicalProfileStatus.MANUAL_REVIEW_REQUIRED.value,
            0,
        ),
        "per_taxon_coverage": dict(sorted(per_taxon.items())),
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        "Pedagogical profile audit generated | "
        f"mode={input_mode} | "
        f"total_resources={report['total_resources']} | "
        f"output={args.output_json}"
    )
    return 0


def _from_qualified_snapshot(payload: dict[str, Any]) -> list[tuple[Any, Any]]:
    from database_core.domain.models import MediaAsset, QualifiedResource

    items = payload.get("qualified_resources")
    if not isinstance(items, list):
        raise ValueError("qualification snapshot must contain a qualified_resources list")

    output: list[tuple[QualifiedResource, MediaAsset]] = []
    for item in items:
        resource = QualifiedResource(**item)
        output.append((resource, _media_asset_from_resource(resource)))
    return output


def _from_export_bundle(payload: dict[str, Any]) -> list[tuple[Any, Any]]:
    from database_core.domain.enums import (
        ConfusionRelevance,
        DiagnosticFeatureVisibility,
        DifficultyLevel,
        LearningSuitability,
        LicenseSafetyResult,
        MediaRole,
        MediaType,
        PedagogicalQuality,
        QualificationStatus,
        Sex,
        SourceName,
        TechnicalQuality,
        UncertaintyReason,
        ViewAngle,
    )
    from database_core.domain.models import MediaAsset, ProvenanceSummary, QualifiedResource

    items = payload.get("qualified_resources")
    if not isinstance(items, list):
        raise ValueError("export bundle must contain a qualified_resources list")

    output: list[tuple[QualifiedResource, MediaAsset]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        source = item.get("provenance", {}).get("source", {})
        trace = item.get("provenance", {}).get("qualification_trace", {})
        pedagogy = item.get("pedagogy", {})
        uncertainty = item.get("uncertainty", {})

        source_name = SourceName(str(source.get("source_name") or "inaturalist"))
        observation_id = str(source.get("source_observation_id") or "unknown")
        source_media_id = str(source.get("source_media_id") or "unknown")

        source_observation_key = str(
            source.get("source_observation_key")
            or f"{source_name}::{observation_id}"
        )
        source_media_key = str(
            source.get("source_media_key")
            or f"{source_name}::{source_media_id}"
        )

        provenance = ProvenanceSummary(
            source_name=source_name,
            source_observation_key=source_observation_key,
            source_media_key=source_media_key,
            source_observation_id=observation_id,
            source_media_id=source_media_id,
            raw_payload_ref=str(source.get("raw_payload_ref") or "export.bundle.v4"),
            run_id=str(item.get("provenance", {}).get("run_id") or "run:unknown"),
            observation_license=(
                str(source["observation_license"])
                if source.get("observation_license") is not None
                else None
            ),
            media_license=(
                str(source["media_license"])
                if source.get("media_license") is not None
                else None
            ),
            qualification_method=str(trace.get("method") or "gemini_plus_rules"),
            ai_model=(str(trace["ai_model"]) if trace.get("ai_model") is not None else None),
            ai_prompt_version=(
                str(trace["ai_prompt_version"])
                if trace.get("ai_prompt_version") is not None
                else None
            ),
            ai_task_name=(
                str(trace["ai_task_name"]) if trace.get("ai_task_name") is not None else None
            ),
            ai_status=(str(trace["ai_status"]) if trace.get("ai_status") is not None else None),
        )

        resource = QualifiedResource(
            qualified_resource_id=str(item.get("qualified_resource_id") or "qr:unknown"),
            canonical_taxon_id=str(item.get("canonical_taxon_id") or "taxon:birds:unknown"),
            source_observation_uid=f"obs:{source_name}:{observation_id}",
            source_observation_id=observation_id,
            media_asset_id=str(item.get("media_asset_id") or "media:unknown"),
            qualification_status=QualificationStatus(
                str(item.get("qualification_status") or "accepted")
            ),
            qualification_version=str(
                item.get("qualification_version") or "qualification.staged.v1"
            ),
            technical_quality=TechnicalQuality(str(item.get("technical_quality") or "unknown")),
            pedagogical_quality=PedagogicalQuality(
                str(item.get("pedagogical_quality") or "unknown")
            ),
            life_stage=str(item.get("life_stage") or "unknown"),
            sex=Sex(str(item.get("sex") or "unknown")),
            visible_parts=[str(part) for part in item.get("visible_parts") or []],
            view_angle=ViewAngle(str(item.get("view_angle") or "unknown")),
            difficulty_level=DifficultyLevel(str(pedagogy.get("difficulty_level") or "unknown")),
            media_role=MediaRole(str(pedagogy.get("media_role") or "context")),
            confusion_relevance=ConfusionRelevance(
                str(pedagogy.get("confusion_relevance") or "none")
            ),
            diagnostic_feature_visibility=DiagnosticFeatureVisibility.UNKNOWN,
            learning_suitability=LearningSuitability.UNKNOWN,
            uncertainty_reason=UncertaintyReason(
                str(pedagogy.get("uncertainty_reason") or uncertainty.get("type") or "none")
            ),
            qualification_notes=(
                str(item["qualification_notes"])
                if item.get("qualification_notes") is not None
                else None
            ),
            qualification_flags=[str(flag) for flag in item.get("qualification_flags") or []],
            provenance_summary=provenance,
            license_safety_result=LicenseSafetyResult(
                str(
                    item.get("license_safety_result")
                    or _infer_license_safety(source.get("media_license"))
                )
            ),
            export_eligible=bool(item.get("export_eligible", True)),
            ai_confidence=(
                float(uncertainty["confidence"])
                if uncertainty.get("confidence") is not None
                else None
            ),
            derived_classification=None,
        )

        media_asset = MediaAsset(
            media_id=resource.media_asset_id,
            source_name=source_name,
            source_media_id=source_media_id,
            media_type=MediaType.IMAGE,
            source_url=f"source://{source_media_id}",
            attribution="from_export_bundle",
            author=None,
            license=provenance.media_license,
            mime_type=None,
            file_extension=None,
            width=None,
            height=None,
            checksum=None,
            source_observation_uid=resource.source_observation_uid,
            canonical_taxon_id=resource.canonical_taxon_id,
            raw_payload_ref=provenance.raw_payload_ref,
        )
        output.append((resource, media_asset))

    return output


def _from_playable_corpus(payload: dict[str, Any]) -> list[tuple[Any, Any]]:
    from database_core.domain.enums import (
        ConfusionRelevance,
        DiagnosticFeatureVisibility,
        DifficultyLevel,
        LearningSuitability,
        LicenseSafetyResult,
        MediaRole,
        MediaType,
        PedagogicalQuality,
        QualificationStatus,
        Sex,
        SourceName,
        TechnicalQuality,
        UncertaintyReason,
        ViewAngle,
    )
    from database_core.domain.models import MediaAsset, ProvenanceSummary, QualifiedResource

    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("playable corpus must contain an items list")

    output: list[tuple[QualifiedResource, MediaAsset]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        source_name = SourceName(str(item.get("source_name") or "inaturalist"))
        source_observation_id = str(item.get("source_observation_id") or "unknown")
        source_media_id = str(item.get("source_media_id") or "unknown")

        media_license = item.get("media_license")
        license_safety = LicenseSafetyResult(str(_infer_license_safety(media_license)))

        provenance = ProvenanceSummary(
            source_name=source_name,
            source_observation_key=f"{source_name}::{source_observation_id}",
            source_media_key=f"{source_name}::{source_media_id}",
            source_observation_id=source_observation_id,
            source_media_id=source_media_id,
            raw_payload_ref="playable_corpus.v1",
            run_id=str(payload.get("run_id") or "run:unknown"),
            observation_license=None,
            media_license=(str(media_license) if media_license is not None else None),
            qualification_method="derived_from_playable_corpus",
            ai_model=None,
            ai_prompt_version=None,
            ai_task_name=None,
            ai_status="rules_only",
        )

        resource = QualifiedResource(
            qualified_resource_id=str(item.get("qualified_resource_id") or "qr:unknown"),
            canonical_taxon_id=str(item.get("canonical_taxon_id") or "taxon:birds:unknown"),
            source_observation_uid=f"obs:{source_name}:{source_observation_id}",
            source_observation_id=source_observation_id,
            media_asset_id=str(item.get("media_asset_id") or "media:unknown"),
            qualification_status=QualificationStatus.ACCEPTED,
            qualification_version="derived_from_playable_corpus.v1",
            technical_quality=TechnicalQuality.UNKNOWN,
            pedagogical_quality=PedagogicalQuality.UNKNOWN,
            life_stage="unknown",
            sex=Sex.UNKNOWN,
            visible_parts=[str(part) for part in item.get("what_to_look_at_specific") or []],
            view_angle=ViewAngle.UNKNOWN,
            difficulty_level=DifficultyLevel(str(item.get("difficulty_level") or "unknown")),
            media_role=MediaRole(str(item.get("media_role") or "context")),
            confusion_relevance=ConfusionRelevance(str(item.get("confusion_relevance") or "none")),
            diagnostic_feature_visibility=DiagnosticFeatureVisibility(
                str(item.get("diagnostic_feature_visibility") or "unknown")
            ),
            learning_suitability=LearningSuitability(
                str(item.get("learning_suitability") or "unknown")
            ),
            uncertainty_reason=UncertaintyReason.NONE,
            qualification_notes=(
                str(item["feedback_short"]) if item.get("feedback_short") is not None else None
            ),
            qualification_flags=[],
            provenance_summary=provenance,
            license_safety_result=license_safety,
            export_eligible=True,
            ai_confidence=None,
            derived_classification=None,
        )

        media_asset = MediaAsset(
            media_id=resource.media_asset_id,
            source_name=source_name,
            source_media_id=source_media_id,
            media_type=MediaType.IMAGE,
            source_url=str(item.get("media_render_url") or f"source://{source_media_id}"),
            attribution=str(item.get("media_attribution") or "from_playable_corpus"),
            author=None,
            license=(str(media_license) if media_license is not None else None),
            mime_type=None,
            file_extension=None,
            width=None,
            height=None,
            checksum=None,
            source_observation_uid=resource.source_observation_uid,
            canonical_taxon_id=resource.canonical_taxon_id,
            raw_payload_ref="playable_corpus.v1",
        )
        output.append((resource, media_asset))

    return output


def _media_asset_from_resource(resource: Any) -> Any:
    from database_core.domain.enums import MediaType
    from database_core.domain.models import MediaAsset

    source_name = resource.provenance_summary.source_name
    source_media_id = resource.provenance_summary.source_media_id
    return MediaAsset(
        media_id=resource.media_asset_id,
        source_name=source_name,
        source_media_id=source_media_id,
        media_type=MediaType.IMAGE,
        source_url=f"source://{source_media_id}",
        attribution="from_qualification_snapshot",
        author=None,
        license=resource.provenance_summary.media_license,
        mime_type=None,
        file_extension=None,
        width=None,
        height=None,
        checksum=None,
        source_observation_uid=resource.source_observation_uid,
        canonical_taxon_id=resource.canonical_taxon_id,
        raw_payload_ref=resource.provenance_summary.raw_payload_ref,
    )


def _infer_license_safety(license_code: object) -> str:
    if license_code is None:
        return "review_required"
    normalized = str(license_code).strip().lower()
    if not normalized:
        return "review_required"
    if "nc" in normalized or "nd" in normalized or "all rights reserved" in normalized:
        return "unsafe"
    return "safe"


if __name__ == "__main__":
    raise SystemExit(main())
