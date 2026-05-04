from __future__ import annotations

from collections.abc import Mapping

PMP_POLICY_VERSION = "pmp_qualification_policy.v1"

USAGE_NAMES = (
    "basic_identification",
    "field_observation",
    "confusion_learning",
    "morphology_learning",
    "species_card",
    "indirect_evidence_learning",
)

USAGE_STATUS_ELIGIBLE = "eligible"
USAGE_STATUS_BORDERLINE = "borderline"
USAGE_STATUS_NOT_RECOMMENDED = "not_recommended"
USAGE_STATUS_NOT_APPLICABLE = "not_applicable"

PMP_POLICY_STATUS_PROFILE_VALID = "profile_valid"
PMP_POLICY_STATUS_PROFILE_FAILED = "profile_failed"
PMP_POLICY_STATUS_PRE_AI_REJECTED = "pre_ai_rejected"
PMP_POLICY_STATUS_POLICY_NOT_APPLICABLE = "policy_not_applicable"
PMP_POLICY_STATUS_POLICY_ERROR = "policy_error"

ELIGIBLE_THRESHOLD = 70.0
BORDERLINE_THRESHOLD = 50.0
STRICT_ELIGIBLE_THRESHOLD = 80.0
STRICT_BORDERLINE_THRESHOLD = 60.0
VERY_STRICT_ELIGIBLE_THRESHOLD = 85.0

PRE_AI_STATUSES = {
    "missing_cached_image",
    "insufficient_resolution",
    "insufficient_resolution_pre_ai",
    "decode_error_pre_ai",
    "blur_pre_ai",
    "duplicate_pre_ai",
}

INDIRECT_EVIDENCE_TYPES = {
    "feather",
    "egg",
    "nest",
    "track",
    "scat",
    "burrow",
    "habitat",
    "dead_organism",
}

COMPLEX_EVIDENCE_TYPES = {
    "partial_organism",
    "multiple_organisms",
}


def is_indirect_evidence_type(evidence_type: str) -> bool:
    return evidence_type in INDIRECT_EVIDENCE_TYPES


def is_complex_evidence_type(evidence_type: str) -> bool:
    return evidence_type in COMPLEX_EVIDENCE_TYPES


def classify_usage_score(score: float | int | None, evidence_type: str, usage_name: str) -> str:
    normalized_evidence = _normalize_text(evidence_type)
    normalized_usage = _normalize_text(usage_name)
    score_value = _safe_float(score)

    if normalized_usage not in USAGE_NAMES:
        return USAGE_STATUS_NOT_APPLICABLE

    if score_value is None:
        return USAGE_STATUS_NOT_APPLICABLE

    if is_indirect_evidence_type(normalized_evidence):
        if normalized_usage == "basic_identification":
            return USAGE_STATUS_NOT_RECOMMENDED
        if normalized_usage == "indirect_evidence_learning":
            return _classify_by_thresholds(score_value)
        if normalized_usage == "species_card":
            return _classify_by_thresholds(
                score_value,
                eligible=VERY_STRICT_ELIGIBLE_THRESHOLD,
                borderline=STRICT_ELIGIBLE_THRESHOLD,
            )
        return _classify_by_thresholds(score_value)

    if normalized_evidence == "whole_organism":
        if normalized_usage == "indirect_evidence_learning":
            if score_value >= VERY_STRICT_ELIGIBLE_THRESHOLD:
                return USAGE_STATUS_ELIGIBLE
            if score_value >= ELIGIBLE_THRESHOLD:
                return USAGE_STATUS_BORDERLINE
            return USAGE_STATUS_NOT_APPLICABLE
        return _classify_by_thresholds(score_value)

    if normalized_evidence == "partial_organism" and normalized_usage in {
        "basic_identification",
        "species_card",
    }:
        return _classify_by_thresholds(
            score_value,
            eligible=STRICT_ELIGIBLE_THRESHOLD,
            borderline=STRICT_BORDERLINE_THRESHOLD,
        )

    if normalized_evidence == "multiple_organisms" and normalized_usage == "species_card":
        return _classify_by_thresholds(
            score_value,
            eligible=STRICT_ELIGIBLE_THRESHOLD,
            borderline=STRICT_BORDERLINE_THRESHOLD,
        )

    return _classify_by_thresholds(score_value)


def evaluate_pmp_profile_policy(
    profile: Mapping[str, object],
    source_status: str | None = None,
) -> dict[str, object]:
    normalized_source_status = _normalize_text(source_status)
    if normalized_source_status in PRE_AI_STATUSES:
        return _pre_ai_policy_decision(source_status=normalized_source_status)

    review_status = _normalize_text(profile.get("review_status"))
    evidence_type = _normalize_text(profile.get("evidence_type"))
    scores = profile.get("scores") if isinstance(profile.get("scores"), Mapping) else {}
    usage_scores = (
        scores.get("usage_scores") if isinstance(scores.get("usage_scores"), Mapping) else {}
    )

    if review_status == "failed":
        return _failed_profile_policy_decision(
            evidence_type=evidence_type,
            policy_notes=["pmp_review_status_failed"],
        )

    if review_status != "valid":
        return {
            "policy_version": PMP_POLICY_VERSION,
            "policy_status": PMP_POLICY_STATUS_POLICY_ERROR,
            "review_status": review_status or None,
            "evidence_type": evidence_type or None,
            "global_quality_score": _safe_float(scores.get("global_quality_score")),
            "usage_statuses": _all_usage_not_applicable(),
            "eligible_database_uses": [],
            "not_recommended_database_uses": [],
            "usage_policy_summary": {},
            "policy_notes": ["invalid_or_missing_review_status"],
        }

    usage_statuses: dict[str, dict[str, object]] = {}
    eligible_database_uses: list[str] = []
    not_recommended_database_uses: list[str] = []

    for usage_name in USAGE_NAMES:
        score_value = _safe_float(usage_scores.get(usage_name))
        usage_status = classify_usage_score(score_value, evidence_type, usage_name)
        reason = _usage_reason(
            usage_status=usage_status,
            score=score_value,
            evidence_type=evidence_type,
            usage_name=usage_name,
        )
        usage_statuses[usage_name] = {
            "status": usage_status,
            "score": score_value,
            "reason": reason,
        }
        if usage_status == USAGE_STATUS_ELIGIBLE:
            eligible_database_uses.append(usage_name)
        elif usage_status == USAGE_STATUS_NOT_RECOMMENDED:
            not_recommended_database_uses.append(usage_name)

    policy_notes: list[str] = []
    if evidence_type and is_indirect_evidence_type(evidence_type):
        policy_notes.append("indirect_evidence_interpretation_applied")
    if evidence_type == "partial_organism":
        policy_notes.append("partial_organism_stricter_basic_and_species_card")
    if evidence_type == "multiple_organisms":
        policy_notes.append("multiple_organisms_stricter_species_card")

    if _safe_float(scores.get("global_quality_score")) is not None:
        policy_notes.append("global_quality_is_broad_signal_not_selection")

    return {
        "policy_version": PMP_POLICY_VERSION,
        "policy_status": PMP_POLICY_STATUS_PROFILE_VALID,
        "review_status": review_status,
        "evidence_type": evidence_type or None,
        "global_quality_score": _safe_float(scores.get("global_quality_score")),
        "usage_statuses": usage_statuses,
        "eligible_database_uses": eligible_database_uses,
        "not_recommended_database_uses": not_recommended_database_uses,
        "usage_policy_summary": _usage_policy_summary(usage_statuses),
        "policy_notes": policy_notes,
    }


def evaluate_pmp_outcome_policy(outcome: Mapping[str, object]) -> dict[str, object]:
    source_status = _normalize_text(outcome.get("status"))
    if source_status in PRE_AI_STATUSES:
        return _pre_ai_policy_decision(source_status=source_status)

    profile_raw = outcome.get("pedagogical_media_profile")
    if not isinstance(profile_raw, Mapping):
        review_contract_version = _normalize_text(outcome.get("review_contract_version"))
        if review_contract_version and review_contract_version != "pedagogical_media_profile_v1":
            return {
                "policy_version": PMP_POLICY_VERSION,
                "policy_status": PMP_POLICY_STATUS_POLICY_NOT_APPLICABLE,
                "review_status": None,
                "evidence_type": None,
                "global_quality_score": None,
                "usage_statuses": _all_usage_not_applicable(),
                "eligible_database_uses": [],
                "not_recommended_database_uses": [],
                "usage_policy_summary": {},
                "policy_notes": ["non_pmp_review_contract"],
            }
        return {
            "policy_version": PMP_POLICY_VERSION,
            "policy_status": PMP_POLICY_STATUS_POLICY_ERROR,
            "review_status": None,
            "evidence_type": None,
            "global_quality_score": None,
            "usage_statuses": _all_usage_not_applicable(),
            "eligible_database_uses": [],
            "not_recommended_database_uses": [],
            "usage_policy_summary": {},
            "policy_notes": ["missing_pedagogical_media_profile"],
        }

    decision = evaluate_pmp_profile_policy(profile_raw, source_status=source_status)
    if (
        decision["policy_status"] == PMP_POLICY_STATUS_PROFILE_FAILED
        and source_status == "pedagogical_media_profile_failed"
    ):
        decision["policy_notes"] = list(decision.get("policy_notes", [])) + [
            "outcome_status_pedagogical_media_profile_failed"
        ]
    return decision


def _usage_policy_summary(usage_statuses: Mapping[str, Mapping[str, object]]) -> dict[str, int]:
    summary = {
        USAGE_STATUS_ELIGIBLE: 0,
        USAGE_STATUS_BORDERLINE: 0,
        USAGE_STATUS_NOT_RECOMMENDED: 0,
        USAGE_STATUS_NOT_APPLICABLE: 0,
    }
    for usage in usage_statuses.values():
        status = _normalize_text(usage.get("status"))
        if status in summary:
            summary[status] += 1
    return summary


def _usage_reason(
    *,
    usage_status: str,
    score: float | None,
    evidence_type: str,
    usage_name: str,
) -> str:
    if usage_status == USAGE_STATUS_NOT_APPLICABLE:
        if score is None:
            return "missing_usage_score"
        if usage_name == "indirect_evidence_learning" and evidence_type == "whole_organism":
            return "whole_organism_indirect_learning_not_primary"
        return "usage_not_applicable_for_evidence_type"

    if usage_status == USAGE_STATUS_NOT_RECOMMENDED:
        if usage_name == "basic_identification" and is_indirect_evidence_type(evidence_type):
            return "indirect_evidence_basic_identification_not_recommended"
        return "score_below_threshold"

    if usage_status == USAGE_STATUS_BORDERLINE:
        return "score_in_borderline_range"

    return "score_above_threshold"


def _failed_profile_policy_decision(
    *,
    evidence_type: str,
    policy_notes: list[str],
) -> dict[str, object]:
    usage_statuses = _all_usage_not_applicable()
    return {
        "policy_version": PMP_POLICY_VERSION,
        "policy_status": PMP_POLICY_STATUS_PROFILE_FAILED,
        "review_status": "failed",
        "evidence_type": evidence_type or None,
        "global_quality_score": None,
        "usage_statuses": usage_statuses,
        "eligible_database_uses": [],
        "not_recommended_database_uses": [],
        "usage_policy_summary": _usage_policy_summary(usage_statuses),
        "policy_notes": policy_notes,
    }


def _pre_ai_policy_decision(*, source_status: str | None) -> dict[str, object]:
    usage_statuses = _all_usage_not_applicable()
    return {
        "policy_version": PMP_POLICY_VERSION,
        "policy_status": PMP_POLICY_STATUS_PRE_AI_REJECTED,
        "review_status": None,
        "evidence_type": None,
        "global_quality_score": None,
        "usage_statuses": usage_statuses,
        "eligible_database_uses": [],
        "not_recommended_database_uses": [],
        "usage_policy_summary": _usage_policy_summary(usage_statuses),
        "policy_notes": [f"pre_ai_status:{source_status or 'unknown'}"],
    }


def _all_usage_not_applicable() -> dict[str, dict[str, object]]:
    return {
        usage_name: {
            "status": USAGE_STATUS_NOT_APPLICABLE,
            "score": None,
            "reason": "not_evaluated",
        }
        for usage_name in USAGE_NAMES
    }


def _classify_by_thresholds(
    score: float,
    *,
    eligible: float = ELIGIBLE_THRESHOLD,
    borderline: float = BORDERLINE_THRESHOLD,
) -> str:
    if score >= eligible:
        return USAGE_STATUS_ELIGIBLE
    if score >= borderline:
        return USAGE_STATUS_BORDERLINE
    return USAGE_STATUS_NOT_RECOMMENDED


def _safe_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")
