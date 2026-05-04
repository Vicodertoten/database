#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from database_core.qualification.pmp_policy_v1 import (
    PMP_POLICY_STATUS_PRE_AI_REJECTED,
    PMP_POLICY_STATUS_PROFILE_FAILED,
    PMP_POLICY_STATUS_PROFILE_VALID,
    evaluate_pmp_outcome_policy,
)

DEFAULT_SNAPSHOT_ROOT = Path("data/raw/inaturalist")
DEFAULT_OUTPUT_PATH = Path("docs/audits/evidence/pmp_policy_v1_sprint7_snapshot_audit.json")

RUNTIME_POLLUTION_KEYS = {
    "feedback",
    "feedback_short",
    "post_answer_feedback",
    "selected_option_id",
    "selectedoptionid",
    "selected_playable_item_id",
    "selectedplayableitemid",
    "playable",
    "selected_for_quiz",
    "runtime_ready",
}

DECISION_READY = "READY_FOR_BROADER_PROFILED_CORPUS_WITH_POLICY"
DECISION_ADJUST = "ADJUST_POLICY_THRESHOLDS"
DECISION_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW_CALIBRATION"
DECISION_INVESTIGATE = "INVESTIGATE_POLICY_MISMATCH"
DECISION_BLOCKED = "BLOCKED_RUN_FAILED"

USAGE_NAMES = (
    "basic_identification",
    "field_observation",
    "confusion_learning",
    "morphology_learning",
    "species_card",
    "indirect_evidence_learning",
)

TARGET_REVIEW_CONTRACT_VERSION = "pedagogical_media_profile_v1"
TOP_TAXON_LIMIT = 12


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit pmp_qualification_policy.v1 decisions from snapshot ai_outputs.json "
            "without mutating source outputs."
        )
    )
    parser.add_argument("--snapshot-id", required=True)
    parser.add_argument("--snapshot-root", type=Path, default=DEFAULT_SNAPSHOT_ROOT)
    parser.add_argument("--manifest-path", type=Path)
    parser.add_argument("--ai-outputs-path", type=Path)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
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
    media_downloads = manifest.get("media_downloads")
    media_by_id: dict[str, dict[str, str]] = {}
    if isinstance(media_downloads, list):
        for item in media_downloads:
            if not isinstance(item, dict):
                continue
            media_id = str(item.get("source_media_id") or "").strip()
            if not media_id:
                continue
            media_by_id[media_id] = {
                "source_observation_id": str(item.get("source_observation_id") or "").strip(),
                "image_url": str(item.get("source_url") or "").strip(),
                "local_image_path": (
                    str((snapshot_dir / str(item.get("image_path") or "")).resolve())
                    if item.get("image_path")
                    else ""
                ),
            }

    taxon_payloads_by_canonical_taxon_id: dict[str, dict[str, object]] = {}
    taxon_seeds = manifest.get("taxon_seeds")
    if isinstance(taxon_seeds, list):
        for seed in taxon_seeds:
            if not isinstance(seed, dict):
                continue
            canonical_taxon_id = str(seed.get("canonical_taxon_id") or "").strip()
            taxon_payload_path = str(seed.get("taxon_payload_path") or "").strip()
            if not canonical_taxon_id or not taxon_payload_path:
                continue
            resolved_taxon_path = snapshot_dir / taxon_payload_path
            if not resolved_taxon_path.exists():
                continue
            try:
                taxon_payloads_by_canonical_taxon_id[canonical_taxon_id] = json.loads(
                    resolved_taxon_path.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, OSError):
                continue

    metadata_by_media_key: dict[str, dict[str, str]] = {}
    if isinstance(taxon_seeds, list):
        for seed in taxon_seeds:
            if not isinstance(seed, dict):
                continue
            response_path_raw = seed.get("response_path")
            if not isinstance(response_path_raw, str) or not response_path_raw.strip():
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
            preferred_common_name = str(
                taxon_payload.get("preferred_common_name")
                or taxon_payload.get("english_common_name")
                or (seed.get("common_names") or [""])[0]
                or ""
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
                scientific_name = str(
                    taxon.get("name")
                    or result.get("species_guess")
                    or seed.get("accepted_scientific_name")
                    or ""
                ).strip()
                source_taxon_id = str(taxon.get("id") or seed.get("source_taxon_id") or "").strip()

                metadata = {
                    "scientific_name": scientific_name,
                    "canonical_taxon_id": canonical_taxon_id,
                    "source_taxon_id": source_taxon_id,
                    "source_observation_id": str(
                        result.get("id")
                        or media_by_id.get(media_id, {}).get("source_observation_id")
                        or ""
                    ).strip(),
                    "image_url": media_by_id.get(media_id, {}).get("image_url", ""),
                    "local_image_path": media_by_id.get(media_id, {}).get("local_image_path", ""),
                    "common_name_en": preferred_common_name,
                    "common_name_fr": "",
                    "common_name_nl": "",
                    "taxon_name": str(
                        taxon.get("preferred_common_name") or preferred_common_name or ""
                    ).strip(),
                }
                metadata_by_media_key[f"inaturalist::{media_id}"] = metadata

    if not metadata_by_media_key:
        return "not_available", {}
    return "joined_from_manifest", metadata_by_media_key


def _append_taxon_count(
    container: dict[str, Counter[str]],
    taxon_key: str,
    item_key: str,
) -> None:
    container.setdefault(taxon_key, Counter())[item_key] += 1


def _bounded_taxon_items(
    counter: Counter[str],
    *,
    limit: int = TOP_TAXON_LIMIT,
) -> list[dict[str, object]]:
    return [{"taxon": taxon, "count": count} for taxon, count in counter.most_common(limit)]


def _nested_key_count(payload: Any) -> int:
    normalized_runtime_keys = {item.replace("_", "") for item in RUNTIME_POLLUTION_KEYS}
    if isinstance(payload, dict):
        count = 0
        for key, value in payload.items():
            key_norm = str(key).strip().lower().replace("_", "")
            if key_norm in normalized_runtime_keys:
                count += 1
            count += _nested_key_count(value)
        return count
    if isinstance(payload, list):
        return sum(_nested_key_count(item) for item in payload)
    return 0


def _extract_example(rows: list[dict[str, object]], predicate: Any) -> dict[str, object] | None:
    for row in rows:
        if predicate(row):
            return row
    return None


def _resolve_decision(*, report: dict[str, object]) -> str:
    if report.get("ai_outputs_broken"):
        return DECISION_BLOCKED

    doctrine = report.get("doctrine_pollution_checks")
    if isinstance(doctrine, dict) and doctrine.get("doctrine_pollution_detected"):
        return DECISION_INVESTIGATE

    generation = report.get("generation_metrics")
    if not isinstance(generation, dict):
        return DECISION_INVESTIGATE

    processed_media_count = int(generation.get("processed_media_count") or 0)
    pmp_profile_valid_count = int(generation.get("pmp_profile_valid_count") or 0)
    if processed_media_count == 0:
        return DECISION_INVESTIGATE

    valid_ratio = pmp_profile_valid_count / processed_media_count
    if valid_ratio < 0.7:
        return DECISION_INVESTIGATE

    summary = report.get("policy_summary") if isinstance(report.get("policy_summary"), dict) else {}
    global_guardrail_ok = bool(summary.get("global_quality_guardrail_ok"))
    if not global_guardrail_ok:
        return DECISION_ADJUST

    indirect = report.get("indirect_evidence_checks")
    if isinstance(indirect, dict) and not bool(indirect.get("has_indirect_eligible")):
        return DECISION_HUMAN_REVIEW

    return DECISION_READY


def audit_pmp_policy_snapshot(
    *,
    snapshot_id: str,
    snapshot_root: Path = DEFAULT_SNAPSHOT_ROOT,
    manifest_path: Path | None = None,
    ai_outputs_path: Path | None = None,
) -> dict[str, object]:
    resolved_ai_outputs_path = (
        ai_outputs_path
        if ai_outputs_path is not None
        else snapshot_root / snapshot_id / "ai_outputs.json"
    )

    if not resolved_ai_outputs_path.exists():
        report = {
            "snapshot_id": snapshot_id,
            "ai_outputs_path": str(resolved_ai_outputs_path),
            "ai_outputs_broken": True,
            "error": "missing_ai_outputs",
            "generation_metrics": {
                "processed_media_count": 0,
                "pmp_profile_valid_count": 0,
                "pmp_profile_failed_count": 0,
                "pre_ai_rejected_count": 0,
                "policy_status_distribution": {},
                "evidence_type_distribution": {},
            },
            "usage_eligibility_counts": {usage: {} for usage in USAGE_NAMES},
            "eligible_database_uses_distribution": {},
            "top_evidence_type_usage_status_combinations": [],
            "examples": {},
            "doctrine_pollution_checks": {
                "doctrine_pollution_detected": False,
                "runtime_or_feedback_pollution_count": 0,
            },
            "policy_summary": {
                "global_quality_guardrail_ok": True,
            },
            "indirect_evidence_checks": {
                "has_indirect_eligible": False,
            },
        }
        report["decision"] = _resolve_decision(report=report)
        return report

    try:
        payload = json.loads(resolved_ai_outputs_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        report = {
            "snapshot_id": snapshot_id,
            "ai_outputs_path": str(resolved_ai_outputs_path),
            "ai_outputs_broken": True,
            "error": "invalid_ai_outputs_json",
            "generation_metrics": {
                "processed_media_count": 0,
                "pmp_profile_valid_count": 0,
                "pmp_profile_failed_count": 0,
                "pre_ai_rejected_count": 0,
                "policy_status_distribution": {},
                "evidence_type_distribution": {},
            },
            "usage_eligibility_counts": {usage: {} for usage in USAGE_NAMES},
            "eligible_database_uses_distribution": {},
            "top_evidence_type_usage_status_combinations": [],
            "examples": {},
            "doctrine_pollution_checks": {
                "doctrine_pollution_detected": False,
                "runtime_or_feedback_pollution_count": 0,
            },
            "policy_summary": {
                "global_quality_guardrail_ok": True,
            },
            "indirect_evidence_checks": {
                "has_indirect_eligible": False,
            },
        }
        report["decision"] = _resolve_decision(report=report)
        return report

    outcomes = payload if isinstance(payload, dict) else {}
    metadata_join_status, metadata_by_media_key = _load_snapshot_metadata(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        manifest_path=manifest_path,
    )

    policy_status_distribution: Counter[str] = Counter()
    evidence_type_distribution: Counter[str] = Counter()
    eligible_database_uses_distribution: Counter[str] = Counter()
    evidence_usage_status_distribution: Counter[str] = Counter()
    usage_eligibility_counts: dict[str, Counter[str]] = {
        usage_name: Counter() for usage_name in USAGE_NAMES
    }

    processed_media_count = 0
    pmp_profile_valid_count = 0
    pmp_profile_failed_count = 0
    pre_ai_rejected_count = 0
    runtime_or_feedback_pollution_count = 0
    count_by_taxon: Counter[str] = Counter()
    profile_valid_count_by_taxon: Counter[str] = Counter()
    profile_failed_count_by_taxon: Counter[str] = Counter()
    pre_ai_rejected_count_by_taxon: Counter[str] = Counter()
    policy_status_distribution_by_taxon: dict[str, Counter[str]] = {}
    eligible_database_uses_by_taxon: dict[str, Counter[str]] = {}
    usage_eligibility_by_taxon: dict[str, dict[str, Counter[str]]] = {}
    evidence_type_distribution_by_taxon: dict[str, Counter[str]] = {}

    rows: list[dict[str, object]] = []

    for media_key, outcome_raw in outcomes.items():
        if not isinstance(outcome_raw, dict):
            continue
        outcome = outcome_raw
        processed_media_count += 1
        runtime_or_feedback_pollution_count += _nested_key_count(outcome)

        decision = evaluate_pmp_outcome_policy(outcome)
        policy_status = str(decision.get("policy_status") or "unknown")
        evidence_type = str(decision.get("evidence_type") or "unknown")
        metadata = metadata_by_media_key.get(media_key, {})
        taxon_key = str(
            metadata.get("canonical_taxon_id") or metadata.get("scientific_name") or "unknown_taxon"
        )

        policy_status_distribution[policy_status] += 1
        evidence_type_distribution[evidence_type] += 1
        count_by_taxon[taxon_key] += 1
        _append_taxon_count(policy_status_distribution_by_taxon, taxon_key, policy_status)
        _append_taxon_count(evidence_type_distribution_by_taxon, taxon_key, evidence_type)

        if policy_status == PMP_POLICY_STATUS_PROFILE_VALID:
            pmp_profile_valid_count += 1
            profile_valid_count_by_taxon[taxon_key] += 1
        elif policy_status == PMP_POLICY_STATUS_PROFILE_FAILED:
            pmp_profile_failed_count += 1
            profile_failed_count_by_taxon[taxon_key] += 1
        elif policy_status == PMP_POLICY_STATUS_PRE_AI_REJECTED:
            pre_ai_rejected_count += 1
            pre_ai_rejected_count_by_taxon[taxon_key] += 1

        usage_statuses_raw = decision.get("usage_statuses")
        usage_statuses = usage_statuses_raw if isinstance(usage_statuses_raw, dict) else {}
        for usage_name in USAGE_NAMES:
            status_payload = (
                usage_statuses.get(usage_name)
                if isinstance(usage_statuses.get(usage_name), dict)
                else {}
            )
            usage_status = str(status_payload.get("status") or "not_applicable")
            usage_eligibility_counts[usage_name][usage_status] += 1
            evidence_usage_status_distribution[f"{evidence_type}|{usage_name}|{usage_status}"] += 1
            usage_eligibility_by_taxon.setdefault(taxon_key, {}).setdefault(
                usage_name,
                Counter(),
            )[usage_status] += 1

        eligible_database_uses = (
            decision.get("eligible_database_uses")
            if isinstance(decision.get("eligible_database_uses"), list)
            else []
        )
        for usage_name in eligible_database_uses:
            eligible_database_uses_distribution[str(usage_name)] += 1
            _append_taxon_count(eligible_database_uses_by_taxon, taxon_key, str(usage_name))

        rows.append(
            {
                "media_key": media_key,
                "scientific_name": metadata.get("scientific_name") or None,
                "canonical_taxon_id": metadata.get("canonical_taxon_id") or None,
                "source_taxon_id": metadata.get("source_taxon_id") or None,
                "source_observation_id": metadata.get("source_observation_id") or None,
                "taxon_name": metadata.get("taxon_name") or None,
                "source_status": outcome.get("status"),
                "policy_status": policy_status,
                "evidence_type": evidence_type,
                "review_status": decision.get("review_status"),
                "global_quality_score": decision.get("global_quality_score"),
                "usage_statuses": usage_statuses,
                "eligible_database_uses": eligible_database_uses,
                "policy_notes": decision.get("policy_notes") or [],
            }
        )

    rows.sort(key=lambda item: str(item.get("media_key") or ""))

    examples = {
        "whole_organism_basic_identification_eligible": _extract_example(
            rows,
            lambda row: (
                row.get("evidence_type") == "whole_organism"
                and ((row.get("usage_statuses") or {}).get("basic_identification") or {}).get(
                    "status"
                )
                == "eligible"
            ),
        ),
        "whole_organism_basic_not_eligible_field_observation_eligible": _extract_example(
            rows,
            lambda row: (
                row.get("evidence_type") == "whole_organism"
                and ((row.get("usage_statuses") or {}).get("basic_identification") or {}).get(
                    "status"
                )
                != "eligible"
                and ((row.get("usage_statuses") or {}).get("field_observation") or {}).get("status")
                == "eligible"
            ),
        ),
        "indirect_evidence_indirect_learning_eligible": _extract_example(
            rows,
            lambda row: (
                row.get("evidence_type")
                in {"feather", "nest", "habitat", "track", "scat", "burrow", "dead_organism", "egg"}
                and (
                    ((row.get("usage_statuses") or {}).get("indirect_evidence_learning") or {}).get(
                        "status"
                    )
                    == "eligible"
                )
            ),
        ),
        "failed_profile": _extract_example(
            rows,
            lambda row: row.get("policy_status") == PMP_POLICY_STATUS_PROFILE_FAILED,
        ),
        "pre_ai_rejected": _extract_example(
            rows,
            lambda row: row.get("policy_status") == PMP_POLICY_STATUS_PRE_AI_REJECTED,
        ),
    }

    global_quality_guardrail_violations = []
    for row in rows:
        global_quality_score = row.get("global_quality_score")
        basic_payload = (row.get("usage_statuses") or {}).get("basic_identification") or {}
        basic_status = basic_payload.get("status")
        basic_score = basic_payload.get("score")
        if not isinstance(global_quality_score, (int, float)):
            continue
        if not isinstance(basic_score, (int, float)):
            continue
        if (
            float(global_quality_score) >= 85.0
            and float(basic_score) < 70.0
            and basic_status == "eligible"
        ):
            global_quality_guardrail_violations.append(str(row.get("media_key") or ""))

    global_quality_guardrail_ok = len(global_quality_guardrail_violations) == 0

    has_indirect_eligible = any(
        row.get("evidence_type")
        in {"feather", "nest", "habitat", "track", "scat", "burrow", "dead_organism", "egg"}
        and (
            ((row.get("usage_statuses") or {}).get("indirect_evidence_learning") or {}).get(
                "status"
            )
            == "eligible"
        )
        for row in rows
    )

    taxa_without_basic_identification_eligible = []
    taxa_without_species_card_eligible = []
    taxa_with_high_failure_rate = []
    for taxon_key, media_count in count_by_taxon.items():
        usage_counts = usage_eligibility_by_taxon.get(taxon_key, {})
        basic_counts = usage_counts.get("basic_identification", Counter())
        species_card_counts = usage_counts.get("species_card", Counter())
        if basic_counts.get("eligible", 0) == 0:
            taxa_without_basic_identification_eligible.append(
                {"taxon": taxon_key, "media_count": media_count}
            )
        if species_card_counts.get("eligible", 0) == 0:
            taxa_without_species_card_eligible.append(
                {"taxon": taxon_key, "media_count": media_count}
            )
        failure_count = profile_failed_count_by_taxon.get(taxon_key, 0)
        if media_count >= 2 and failure_count / media_count >= 0.4:
            taxa_with_high_failure_rate.append(
                {
                    "taxon": taxon_key,
                    "media_count": media_count,
                    "failed_count": failure_count,
                    "failure_rate": round(failure_count / media_count, 2),
                }
            )

    taxa_without_basic_identification_eligible.sort(
        key=lambda item: (-int(item["media_count"]), str(item["taxon"]))
    )
    taxa_without_species_card_eligible.sort(
        key=lambda item: (-int(item["media_count"]), str(item["taxon"]))
    )
    taxa_with_high_failure_rate.sort(
        key=lambda item: (
            -float(item["failure_rate"]),
            -int(item["media_count"]),
            str(item["taxon"]),
        )
    )

    report = {
        "snapshot_id": snapshot_id,
        "ai_outputs_path": str(resolved_ai_outputs_path),
        "ai_outputs_broken": False,
        "metadata_join_status": metadata_join_status,
        "generation_metrics": {
            "processed_media_count": processed_media_count,
            "pmp_profile_valid_count": pmp_profile_valid_count,
            "pmp_profile_failed_count": pmp_profile_failed_count,
            "pre_ai_rejected_count": pre_ai_rejected_count,
            "policy_status_distribution": dict(sorted(policy_status_distribution.items())),
            "evidence_type_distribution": dict(sorted(evidence_type_distribution.items())),
        },
        "usage_eligibility_counts": {
            usage_name: dict(sorted(counter.items()))
            for usage_name, counter in usage_eligibility_counts.items()
        },
        "eligible_database_uses_distribution": dict(
            sorted(eligible_database_uses_distribution.items())
        ),
        "top_evidence_type_usage_status_combinations": [
            {"combination": key, "count": count}
            for key, count in evidence_usage_status_distribution.most_common(12)
        ],
        "examples": examples,
        "doctrine_pollution_checks": {
            "doctrine_pollution_detected": runtime_or_feedback_pollution_count > 0,
            "runtime_or_feedback_pollution_count": runtime_or_feedback_pollution_count,
        },
        "policy_summary": {
            "global_quality_guardrail_ok": global_quality_guardrail_ok,
            "global_quality_guardrail_violation_count": len(global_quality_guardrail_violations),
            "policy_output_shape": {
                "contains_playable": False,
                "contains_selected_for_quiz": False,
                "contains_runtime_ready": False,
                "contains_selectedOptionId": False,
            },
        },
        "indirect_evidence_checks": {
            "has_indirect_eligible": has_indirect_eligible,
        },
        "taxon_policy_summary": {
            "taxon_count": len(count_by_taxon),
            "count_by_taxon": dict(sorted(count_by_taxon.items())),
            "profile_valid_count_by_taxon": dict(sorted(profile_valid_count_by_taxon.items())),
            "profile_failed_count_by_taxon": dict(sorted(profile_failed_count_by_taxon.items())),
            "pre_ai_rejected_count_by_taxon": dict(sorted(pre_ai_rejected_count_by_taxon.items())),
            "policy_status_distribution_by_taxon": {
                taxon: dict(sorted(counter.items()))
                for taxon, counter in sorted(policy_status_distribution_by_taxon.items())
            },
            "eligible_database_uses_by_taxon": {
                taxon: dict(sorted(counter.items()))
                for taxon, counter in sorted(eligible_database_uses_by_taxon.items())
            },
            "usage_eligibility_by_taxon": {
                taxon: {
                    usage_name: dict(sorted(counter.items()))
                    for usage_name, counter in sorted(usage_counts.items())
                }
                for taxon, usage_counts in sorted(usage_eligibility_by_taxon.items())
            },
            "evidence_type_distribution_by_taxon": {
                taxon: dict(sorted(counter.items()))
                for taxon, counter in sorted(evidence_type_distribution_by_taxon.items())
            },
            "top_taxa_by_media_count": _bounded_taxon_items(count_by_taxon),
            "taxa_without_basic_identification_eligible": (
                taxa_without_basic_identification_eligible[:TOP_TAXON_LIMIT]
            ),
            "taxa_without_species_card_eligible": (
                taxa_without_species_card_eligible[:TOP_TAXON_LIMIT]
            ),
            "taxa_with_high_failure_rate": taxa_with_high_failure_rate[:TOP_TAXON_LIMIT],
        },
    }
    report["decision"] = _resolve_decision(report=report)
    return report


def main() -> None:
    args = _parse_args()
    report = audit_pmp_policy_snapshot(
        snapshot_id=args.snapshot_id,
        snapshot_root=args.snapshot_root,
        manifest_path=args.manifest_path,
        ai_outputs_path=args.ai_outputs_path,
    )

    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        "PMP policy snapshot audit complete"
        f" | snapshot_id={args.snapshot_id}"
        f" | decision={report.get('decision')}"
        f" | output={args.output_path}"
    )


if __name__ == "__main__":
    main()
