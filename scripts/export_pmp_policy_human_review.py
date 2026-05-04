#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
import random
from collections.abc import Mapping, Sequence
from pathlib import Path

from database_core.qualification.pmp_policy_v1 import (
    PMP_POLICY_STATUS_PRE_AI_REJECTED,
    PMP_POLICY_STATUS_PROFILE_FAILED,
    PMP_POLICY_STATUS_PROFILE_VALID,
    USAGE_NAMES,
    evaluate_pmp_outcome_policy,
    is_complex_evidence_type,
    is_indirect_evidence_type,
)

DEFAULT_SNAPSHOT_ROOT = Path("data/raw/inaturalist")
DEFAULT_OUTPUT_CSV = Path("docs/audits/human_review/pmp_policy_v1_human_review_sample.csv")
DEFAULT_OUTPUT_JSONL = Path("docs/audits/human_review/pmp_policy_v1_human_review_sample.jsonl")

HUMAN_REVIEW_COLUMNS = [
    "human_overall_judgment",
    "human_basic_identification_judgment",
    "human_field_observation_judgment",
    "human_confusion_learning_judgment",
    "human_morphology_learning_judgment",
    "human_species_card_judgment",
    "human_indirect_evidence_learning_judgment",
    "human_evidence_type_judgment",
    "human_field_marks_judgment",
    "human_notes",
    "reviewer_name",
    "reviewed_at",
]

CSV_COLUMNS = [
    "review_item_id",
    "media_key",
    "source_media_id",
    "observation_id",
    "image_url",
    "local_image_path",
    "scientific_name",
    "common_name_fr",
    "common_name_en",
    "common_name_nl",
    "canonical_taxon_id",
    "source_taxon_id",
    "metadata_join_status",
    "organism_group",
    "evidence_type",
    "review_status",
    "failure_reason",
    "global_quality_score",
    "basic_identification_score",
    "field_observation_score",
    "confusion_learning_score",
    "morphology_learning_score",
    "species_card_score",
    "indirect_evidence_learning_score",
    "policy_status",
    "eligible_database_uses",
    "borderline_database_uses",
    "not_recommended_database_uses",
    "basic_identification_policy",
    "field_observation_policy",
    "confusion_learning_policy",
    "morphology_learning_policy",
    "species_card_policy",
    "indirect_evidence_learning_policy",
    "policy_notes",
    "visible_field_marks_summary",
    "limitations_summary",
    "technical_quality",
    "subject_visibility",
    "diagnostic_feature_visibility",
    "biological_sex_value",
    "biological_life_stage_value",
    "biological_plumage_state_value",
    "biological_seasonal_state_value",
] + HUMAN_REVIEW_COLUMNS


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a deterministic PMP policy human review sample to CSV/JSONL."
    )
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_SNAPSHOT_ROOT)
    parser.add_argument("--manifest-path", type=Path)
    parser.add_argument("--ai-outputs-path", type=Path)
    parser.add_argument("--sample-size", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--include-failed", action="store_true")
    parser.add_argument("--include-pre-ai", action="store_true")
    parser.add_argument("--min-per-evidence-type", type=int, default=1)
    parser.add_argument("--min-per-policy-use", type=int, default=1)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--output-jsonl", type=Path, default=DEFAULT_OUTPUT_JSONL)
    return parser.parse_args()


def _load_snapshot_metadata(
    *,
    snapshot_id: str,
    snapshot_root: Path,
    manifest_path: Path | None,
) -> tuple[str, dict[str, dict[str, str]]]:
    resolved_manifest = (
        manifest_path
        if manifest_path is not None
        else snapshot_root / snapshot_id / "manifest.json"
    )
    if not resolved_manifest.exists():
        return "not_available", {}

    try:
        manifest = json.loads(resolved_manifest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "invalid_manifest", {}

    snapshot_dir = resolved_manifest.parent
    media_by_id: dict[str, dict[str, str]] = {}
    for item in manifest.get("media_downloads", []):
        if not isinstance(item, dict):
            continue
        media_id = str(item.get("source_media_id") or "").strip()
        if not media_id:
            continue
        media_by_id[media_id] = {
            "observation_id": str(item.get("source_observation_id") or "").strip(),
            "image_url": str(item.get("source_url") or "").strip(),
            "local_image_path": str((snapshot_dir / str(item.get("image_path") or "")).resolve())
            if item.get("image_path")
            else "",
        }

    taxon_payloads_by_canonical_taxon_id: dict[str, dict[str, object]] = {}
    for seed in manifest.get("taxon_seeds", []):
        if not isinstance(seed, dict):
            continue
        canonical_taxon_id = str(seed.get("canonical_taxon_id") or "").strip()
        taxon_payload_path = str(seed.get("taxon_payload_path") or "").strip()
        if not canonical_taxon_id or not taxon_payload_path:
            continue
        path = snapshot_dir / taxon_payload_path
        if not path.exists():
            continue
        try:
            taxon_payloads_by_canonical_taxon_id[canonical_taxon_id] = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            continue

    metadata_by_media_key: dict[str, dict[str, str]] = {}
    for seed in manifest.get("taxon_seeds", []):
        if not isinstance(seed, dict):
            continue
        response_path_raw = str(seed.get("response_path") or "").strip()
        if not response_path_raw:
            continue
        response_path = snapshot_dir / response_path_raw
        if not response_path.exists():
            continue
        try:
            payload = json.loads(response_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        canonical_taxon_id = str(seed.get("canonical_taxon_id") or "").strip()
        taxon_payload = taxon_payloads_by_canonical_taxon_id.get(canonical_taxon_id, {})
        fallback_common_names = (
            seed.get("common_names") if isinstance(seed.get("common_names"), list) else []
        )
        default_common_name = str(
            taxon_payload.get("preferred_common_name")
            or taxon_payload.get("english_common_name")
            or (fallback_common_names[0] if fallback_common_names else "")
        ).strip()

        for result in payload.get("results", []):
            if not isinstance(result, dict):
                continue
            photos = result.get("photos")
            if not isinstance(photos, list) or not photos:
                continue
            primary = photos[0]
            if not isinstance(primary, dict):
                continue
            media_id = str(primary.get("id") or "").strip()
            if not media_id:
                continue
            taxon = result.get("taxon") if isinstance(result.get("taxon"), dict) else {}
            metadata_by_media_key[f"inaturalist::{media_id}"] = {
                "scientific_name": str(
                    taxon.get("name")
                    or result.get("species_guess")
                    or seed.get("accepted_scientific_name")
                    or ""
                ).strip(),
                "canonical_taxon_id": canonical_taxon_id,
                "source_taxon_id": str(
                    taxon.get("id") or seed.get("source_taxon_id") or ""
                ).strip(),
                "observation_id": str(
                    result.get("id") or media_by_id.get(media_id, {}).get("observation_id") or ""
                ).strip(),
                "image_url": media_by_id.get(media_id, {}).get("image_url", ""),
                "local_image_path": media_by_id.get(media_id, {}).get("local_image_path", ""),
                "common_name_en": str(
                    taxon.get("preferred_common_name") or default_common_name or ""
                ).strip(),
                "common_name_fr": "",
                "common_name_nl": "",
            }
    if not metadata_by_media_key:
        return "not_available", {}
    return "joined_from_manifest", metadata_by_media_key


def _load_ai_outputs(ai_outputs_path: Path) -> dict[str, dict[str, object]]:
    payload = json.loads(ai_outputs_path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _join_texts(value: object) -> str:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        parts = [str(item).strip() for item in value if str(item).strip()]
        return " | ".join(parts[:5])
    text = str(value or "").strip()
    return text


def _visible_field_marks_summary(profile: Mapping[str, object]) -> str:
    identification = (
        profile.get("identification_profile")
        if isinstance(profile.get("identification_profile"), Mapping)
        else {}
    )
    marks = identification.get("visible_field_marks")
    if not isinstance(marks, Sequence) or isinstance(marks, (str, bytes)):
        return ""
    parts: list[str] = []
    for mark in marks[:5]:
        if not isinstance(mark, Mapping):
            continue
        feature = str(mark.get("feature") or "").strip()
        body_part = str(mark.get("body_part") or "").strip()
        if feature and body_part:
            parts.append(f"{body_part}:{feature}")
        elif feature:
            parts.append(feature)
    return " | ".join(parts)


def _limitations_summary(profile: Mapping[str, object]) -> str:
    parts = []
    limitations = profile.get("limitations")
    if isinstance(limitations, Sequence) and not isinstance(limitations, (str, bytes)):
        parts.extend(str(item).strip() for item in limitations if str(item).strip())
    identification = (
        profile.get("identification_profile")
        if isinstance(profile.get("identification_profile"), Mapping)
        else {}
    )
    more = identification.get("identification_limitations")
    if isinstance(more, Sequence) and not isinstance(more, (str, bytes)):
        parts.extend(str(item).strip() for item in more if str(item).strip())
    return " | ".join(parts[:6])


def _value_from_path(mapping: Mapping[str, object], *keys: str) -> object:
    current: object = mapping
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _policy_use_lists(policy: Mapping[str, object]) -> tuple[str, str, str]:
    usage_statuses_raw = policy.get("usage_statuses")
    usage_statuses = usage_statuses_raw if isinstance(usage_statuses_raw, Mapping) else {}
    borderline: list[str] = []
    not_recommended: list[str] = []
    for usage_name in USAGE_NAMES:
        usage_payload = usage_statuses.get(usage_name)
        if not isinstance(usage_payload, Mapping):
            continue
        status = str(usage_payload.get("status") or "")
        if status == "borderline":
            borderline.append(usage_name)
        elif status == "not_recommended":
            not_recommended.append(usage_name)
    eligible_raw = policy.get("eligible_database_uses")
    eligible = eligible_raw if isinstance(eligible_raw, list) else []
    return (
        "|".join(str(item) for item in eligible),
        "|".join(borderline),
        "|".join(not_recommended),
    )


def build_human_review_rows(
    *,
    snapshot_id: str,
    snapshot_root: Path = DEFAULT_SNAPSHOT_ROOT,
    manifest_path: Path | None = None,
    ai_outputs_path: Path | None = None,
) -> tuple[str, list[dict[str, object]]]:
    resolved_ai_outputs_path = (
        ai_outputs_path
        if ai_outputs_path is not None
        else snapshot_root / snapshot_id / "ai_outputs.json"
    )
    metadata_join_status, metadata_by_media_key = _load_snapshot_metadata(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        manifest_path=manifest_path,
    )
    outcomes = _load_ai_outputs(resolved_ai_outputs_path)
    rows: list[dict[str, object]] = []
    for index, media_key in enumerate(sorted(outcomes), start=1):
        outcome = outcomes[media_key]
        if not isinstance(outcome, Mapping):
            continue
        policy = evaluate_pmp_outcome_policy(outcome)
        profile = (
            outcome.get("pedagogical_media_profile")
            if isinstance(outcome.get("pedagogical_media_profile"), Mapping)
            else {}
        )
        scores = profile.get("scores") if isinstance(profile.get("scores"), Mapping) else {}
        usage_scores_raw = scores.get("usage_scores") if isinstance(scores, Mapping) else {}
        usage_scores = usage_scores_raw if isinstance(usage_scores_raw, Mapping) else {}
        metadata = metadata_by_media_key.get(media_key, {})
        eligible, borderline, not_recommended = _policy_use_lists(policy)
        usage_statuses_raw = policy.get("usage_statuses")
        usage_statuses = usage_statuses_raw if isinstance(usage_statuses_raw, Mapping) else {}
        biological = (
            profile.get("biological_profile_visible")
            if isinstance(profile.get("biological_profile_visible"), Mapping)
            else {}
        )
        technical = (
            profile.get("technical_profile")
            if isinstance(profile.get("technical_profile"), Mapping)
            else {}
        )
        observation = (
            profile.get("observation_profile")
            if isinstance(profile.get("observation_profile"), Mapping)
            else {}
        )
        identification = (
            profile.get("identification_profile")
            if isinstance(profile.get("identification_profile"), Mapping)
            else {}
        )
        row = {
            "review_item_id": f"pmp-policy-review-{index:04d}",
            "media_key": media_key,
            "source_media_id": media_key.split("::", 1)[1] if "::" in media_key else media_key,
            "observation_id": metadata.get("observation_id", ""),
            "image_url": metadata.get("image_url", ""),
            "local_image_path": metadata.get("local_image_path", ""),
            "scientific_name": metadata.get("scientific_name", ""),
            "common_name_fr": metadata.get("common_name_fr", ""),
            "common_name_en": metadata.get("common_name_en", ""),
            "common_name_nl": metadata.get("common_name_nl", ""),
            "canonical_taxon_id": metadata.get("canonical_taxon_id", ""),
            "source_taxon_id": metadata.get("source_taxon_id", ""),
            "metadata_join_status": metadata_join_status,
            "organism_group": profile.get("organism_group") or "",
            "evidence_type": profile.get("evidence_type") or policy.get("evidence_type") or "",
            "review_status": profile.get("review_status") or policy.get("review_status") or "",
            "failure_reason": profile.get("failure_reason") or "",
            "global_quality_score": scores.get("global_quality_score") or "",
            "basic_identification_score": usage_scores.get("basic_identification") or "",
            "field_observation_score": usage_scores.get("field_observation") or "",
            "confusion_learning_score": usage_scores.get("confusion_learning") or "",
            "morphology_learning_score": usage_scores.get("morphology_learning") or "",
            "species_card_score": usage_scores.get("species_card") or "",
            "indirect_evidence_learning_score": (
                usage_scores.get("indirect_evidence_learning") or ""
            ),
            "policy_status": policy.get("policy_status") or "",
            "eligible_database_uses": eligible,
            "borderline_database_uses": borderline,
            "not_recommended_database_uses": not_recommended,
            "basic_identification_policy": _value_from_path(
                usage_statuses, "basic_identification", "status"
            )
            or "",
            "field_observation_policy": _value_from_path(
                usage_statuses, "field_observation", "status"
            )
            or "",
            "confusion_learning_policy": _value_from_path(
                usage_statuses, "confusion_learning", "status"
            )
            or "",
            "morphology_learning_policy": _value_from_path(
                usage_statuses, "morphology_learning", "status"
            )
            or "",
            "species_card_policy": _value_from_path(usage_statuses, "species_card", "status") or "",
            "indirect_evidence_learning_policy": _value_from_path(
                usage_statuses, "indirect_evidence_learning", "status"
            )
            or "",
            "policy_notes": _join_texts(policy.get("policy_notes") or []),
            "visible_field_marks_summary": _visible_field_marks_summary(profile),
            "limitations_summary": _limitations_summary(profile),
            "technical_quality": technical.get("technical_quality") or "",
            "subject_visibility": observation.get("subject_visibility") or "",
            "diagnostic_feature_visibility": identification.get("diagnostic_feature_visibility")
            or "",
            "biological_sex_value": _value_from_path(biological, "sex", "value") or "",
            "biological_life_stage_value": _value_from_path(biological, "life_stage", "value")
            or "",
            "biological_plumage_state_value": _value_from_path(biological, "plumage_state", "value")
            or "",
            "biological_seasonal_state_value": _value_from_path(
                biological, "seasonal_state", "value"
            )
            or "",
        }
        for column in HUMAN_REVIEW_COLUMNS:
            row[column] = ""
        rows.append(row)
    return metadata_join_status, rows


def _select_rows(
    rows: list[dict[str, object]],
    *,
    sample_size: int,
    seed: int,
    include_failed: bool,
    include_pre_ai: bool,
    min_per_evidence_type: int,
    min_per_policy_use: int,
) -> list[dict[str, object]]:
    rng = random.Random(seed)
    by_key = {str(row["media_key"]): row for row in rows}
    selected_keys: list[str] = []

    def select_from(candidates: list[dict[str, object]], count: int) -> None:
        pool = sorted(candidates, key=lambda item: str(item["media_key"]))
        rng.shuffle(pool)
        for candidate in pool:
            if len(selected_keys) >= sample_size:
                break
            media_key = str(candidate["media_key"])
            if media_key in selected_keys:
                continue
            selected_keys.append(media_key)
            if count <= 1:
                count -= 1
                if count <= 0:
                    break
            else:
                count -= 1
                if count <= 0:
                    break

    valid_rows = [
        row for row in rows if row.get("policy_status") == PMP_POLICY_STATUS_PROFILE_VALID
    ]
    failed_rows = [
        row for row in rows if row.get("policy_status") == PMP_POLICY_STATUS_PROFILE_FAILED
    ]
    pre_ai_rows = [
        row for row in rows if row.get("policy_status") == PMP_POLICY_STATUS_PRE_AI_REJECTED
    ]

    high_basic = [
        row
        for row in valid_rows
        if row.get("basic_identification_policy") == "eligible"
        and isinstance(row.get("basic_identification_score"), (int, float))
        and float(row["basic_identification_score"]) >= 80.0
    ]
    borderline_basic = [
        row for row in valid_rows if row.get("basic_identification_policy") == "borderline"
    ]
    not_basic_but_field = [
        row
        for row in valid_rows
        if row.get("basic_identification_policy") in {"borderline", "not_recommended"}
        and row.get("field_observation_policy") == "eligible"
    ]
    species_card_eligible = [
        row for row in valid_rows if row.get("species_card_policy") == "eligible"
    ]
    species_card_questionable = [
        row
        for row in valid_rows
        if row.get("species_card_policy") in {"borderline", "not_recommended"}
        and row.get("evidence_type") in {"whole_organism", "multiple_organisms", "partial_organism"}
    ]
    confusion_eligible = [
        row for row in valid_rows if row.get("confusion_learning_policy") == "eligible"
    ]
    indirect_eligible = [
        row for row in valid_rows if row.get("indirect_evidence_learning_policy") == "eligible"
    ]
    indirect_or_complex = [
        row
        for row in valid_rows
        if is_indirect_evidence_type(str(row.get("evidence_type") or ""))
        or is_complex_evidence_type(str(row.get("evidence_type") or ""))
    ]

    if include_failed or include_pre_ai:
        combined_target = min(5, len(failed_rows) + len(pre_ai_rows))
        if include_failed:
            failed_target = min(4, len(failed_rows), combined_target)
            select_from(failed_rows, failed_target)
        if include_pre_ai:
            remaining_combined = combined_target - len(
                [
                    key
                    for key in selected_keys
                    if by_key[key].get("policy_status") == PMP_POLICY_STATUS_PROFILE_FAILED
                ]
            )
            pre_ai_target = min(max(1, remaining_combined), len(pre_ai_rows)) if pre_ai_rows else 0
            select_from(pre_ai_rows, pre_ai_target)

    select_from(indirect_or_complex, 5)
    select_from(high_basic, 5)
    select_from(borderline_basic, 5)
    select_from(not_basic_but_field, 5)
    select_from(species_card_eligible, 4)
    select_from(species_card_questionable, 4)
    select_from(confusion_eligible, 4)
    select_from(indirect_eligible, 4)

    evidence_types = sorted(
        {
            str(row.get("evidence_type") or "")
            for row in valid_rows
            if str(row.get("evidence_type") or "")
        }
    )
    for evidence_type in evidence_types:
        candidates = [row for row in valid_rows if row.get("evidence_type") == evidence_type]
        select_from(candidates, min_per_evidence_type)

    for usage_name in USAGE_NAMES:
        candidates = [
            row
            for row in valid_rows
            if usage_name in str(row.get("eligible_database_uses") or "").split("|")
        ]
        select_from(candidates, min_per_policy_use)

    seen_taxa: set[str] = set()
    diverse_taxa_rows = []
    for row in sorted(valid_rows, key=lambda item: str(item["media_key"])):
        taxon = str(row.get("canonical_taxon_id") or row.get("scientific_name") or "")
        if not taxon or taxon in seen_taxa:
            continue
        seen_taxa.add(taxon)
        diverse_taxa_rows.append(row)
    select_from(diverse_taxa_rows, min(10, len(diverse_taxa_rows)))

    whole_rows = [row for row in valid_rows if row.get("evidence_type") == "whole_organism"]
    select_from(whole_rows, 20)

    remaining = sorted(rows, key=lambda item: str(item["media_key"]))
    rng.shuffle(remaining)
    for row in remaining:
        if len(selected_keys) >= sample_size:
            break
        media_key = str(row["media_key"])
        if media_key not in selected_keys:
            selected_keys.append(media_key)

    return [by_key[key] for key in selected_keys[:sample_size]]


def export_pmp_policy_human_review(
    *,
    snapshot_id: str,
    snapshot_root: Path = DEFAULT_SNAPSHOT_ROOT,
    manifest_path: Path | None = None,
    ai_outputs_path: Path | None = None,
    sample_size: int = 40,
    seed: int = 42,
    include_failed: bool = True,
    include_pre_ai: bool = True,
    min_per_evidence_type: int = 1,
    min_per_policy_use: int = 1,
    output_csv: Path = DEFAULT_OUTPUT_CSV,
    output_jsonl: Path | None = DEFAULT_OUTPUT_JSONL,
) -> dict[str, object]:
    metadata_join_status, rows = build_human_review_rows(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        manifest_path=manifest_path,
        ai_outputs_path=ai_outputs_path,
    )
    sample = _select_rows(
        rows,
        sample_size=sample_size,
        seed=seed,
        include_failed=include_failed,
        include_pre_ai=include_pre_ai,
        min_per_evidence_type=min_per_evidence_type,
        min_per_policy_use=min_per_policy_use,
    )

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in sample:
            writer.writerow({key: row.get(key, "") for key in CSV_COLUMNS})

    if output_jsonl is not None:
        output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with output_jsonl.open("w", encoding="utf-8") as handle:
            for row in sample:
                handle.write(
                    json.dumps({key: row.get(key, "") for key in CSV_COLUMNS}, ensure_ascii=True)
                    + "\n"
                )

    return {
        "snapshot_id": snapshot_id,
        "metadata_join_status": metadata_join_status,
        "review_item_count": len(sample),
        "output_csv": str(output_csv),
        "output_jsonl": str(output_jsonl) if output_jsonl is not None else None,
    }


def main() -> None:
    args = _parse_args()
    summary = export_pmp_policy_human_review(
        snapshot_id=args.snapshot_id,
        snapshot_root=args.snapshot_root,
        manifest_path=args.manifest_path,
        ai_outputs_path=args.ai_outputs_path,
        sample_size=args.sample_size,
        seed=args.seed,
        include_failed=args.include_failed,
        include_pre_ai=args.include_pre_ai,
        min_per_evidence_type=args.min_per_evidence_type,
        min_per_policy_use=args.min_per_policy_use,
        output_csv=args.output_csv,
        output_jsonl=args.output_jsonl,
    )
    print(
        "Exported PMP policy human review sample"
        f" | snapshot_id={summary['snapshot_id']}"
        f" | review_item_count={summary['review_item_count']}"
        f" | metadata_join_status={summary['metadata_join_status']}"
        f" | output_csv={summary['output_csv']}"
    )


if __name__ == "__main__":
    main()
