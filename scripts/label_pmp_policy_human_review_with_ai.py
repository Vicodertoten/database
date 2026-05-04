#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import unicodedata
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

INPUT_CSV = Path("docs/audits/human_review/pmp_policy_v1_human_review_sample.csv")
OUTPUT_CSV = Path("docs/audits/human_review/pmp_policy_v1_human_review_ai_labeled.csv")
OUTPUT_JSONL = Path("docs/audits/human_review/pmp_policy_v1_human_review_ai_labeled.jsonl")
OUTPUT_AUDIT = Path("docs/audits/evidence/pmp_policy_v1_human_review_ai_labeling_audit.json")

GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
GEMINI_TIMEOUT_SECONDS = 20

OVERALL_ALLOWED = {"accept", "too_permissive", "too_strict", "unclear", "reject", "blank"}
PER_USAGE_ALLOWED = {"agree", "too_permissive", "too_strict", "not_sure", "blank"}
EVIDENCE_TYPE_ALLOWED = {"correct", "wrong", "too_specific", "too_generic", "not_sure", "blank"}
FIELD_MARKS_ALLOWED = {"useful", "partially_useful", "generic", "wrong", "not_sure", "blank"}
OVERALL_HUMAN_VALUES = {"accept", "too_permissive", "too_strict", "unclear", "reject"}

ISSUE_CATEGORIES_ALLOWED = {
    "accept",
    "too_strict",
    "too_permissive",
    "schema_false_negative",
    "pre_ai_false_negative",
    "target_taxon_mismatch",
    "habitat_too_permissive",
    "global_score_uncertainty",
    "field_observation_too_permissive",
    "species_card_too_permissive",
    "evidence_type_error",
    "field_marks_error",
    "needs_second_review",
}

CALIBRATION_PRIORITY_ALLOWED = {"high", "medium", "low"}
CONFIDENCE_ALLOWED = {"high", "medium", "low"}

INFERRED_COLUMNS = [
    "human_overall_judgment_inferred",
    "human_basic_identification_judgment_inferred",
    "human_field_observation_judgment_inferred",
    "human_confusion_learning_judgment_inferred",
    "human_morphology_learning_judgment_inferred",
    "human_species_card_judgment_inferred",
    "human_indirect_evidence_learning_judgment_inferred",
    "human_evidence_type_judgment_inferred",
    "human_field_marks_judgment_inferred",
    "human_issue_categories",
    "calibration_priority",
    "ai_inference_confidence",
    "ai_inference_rationale",
    "labeling_source",
]

PER_USAGE_INFERRED_COLUMNS = [
    "human_basic_identification_judgment_inferred",
    "human_field_observation_judgment_inferred",
    "human_confusion_learning_judgment_inferred",
    "human_morphology_learning_judgment_inferred",
    "human_species_card_judgment_inferred",
    "human_indirect_evidence_learning_judgment_inferred",
]

RECOGNIZABLE_PATTERNS = (
    "recognizable",
    "reconnaissable",
    "identifiable",
    "on reconnait",
    "on reconnait",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Infer structured calibration labels from PMP policy human review notes "
            "using optional AI + deterministic fallback rules."
        )
    )
    parser.add_argument("--input-csv", type=Path, default=INPUT_CSV)
    parser.add_argument("--output-csv", type=Path, default=OUTPUT_CSV)
    parser.add_argument("--output-jsonl", type=Path, default=OUTPUT_JSONL)
    parser.add_argument("--output-audit", type=Path, default=OUTPUT_AUDIT)
    parser.add_argument("--enable-ai", action="store_true")
    parser.add_argument("--ai-api-key-env", default="GEMINI_API_KEY")
    parser.add_argument("--ai-model", default=GEMINI_MODEL)
    parser.add_argument("--ai-timeout-seconds", type=int, default=GEMINI_TIMEOUT_SECONDS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--second-pass",
        action="store_true",
        help=(
            "Re-run AI inference only on rows where labeling_source==none, "
            "using policy/score data (no human notes required). "
            "Reads output-csv as input and overwrites it in place."
        ),
    )
    return parser.parse_args()


def _normalized_text(value: str) -> str:
    lowered = value.strip().lower()
    normalized = unicodedata.normalize("NFKD", lowered)
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", ascii_only)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _extract_note_text(row: dict[str, str]) -> str:
    human_notes = str(row.get("human_notes") or "").strip()
    if human_notes:
        return human_notes

    # Some manually completed sheets place free text in human_overall_judgment.
    overall_value = str(row.get("human_overall_judgment") or "").strip()
    if overall_value and _normalized_text(overall_value) not in OVERALL_HUMAN_VALUES:
        return overall_value

    return ""


def _blank_inference(review_item_id: str, rationale: str) -> dict[str, Any]:
    return {
        "review_item_id": review_item_id,
        "human_overall_judgment_inferred": "blank",
        "human_basic_identification_judgment_inferred": "blank",
        "human_field_observation_judgment_inferred": "blank",
        "human_confusion_learning_judgment_inferred": "blank",
        "human_morphology_learning_judgment_inferred": "blank",
        "human_species_card_judgment_inferred": "blank",
        "human_indirect_evidence_learning_judgment_inferred": "blank",
        "human_evidence_type_judgment_inferred": "blank",
        "human_field_marks_judgment_inferred": "blank",
        "human_issue_categories": [],
        "calibration_priority": "low",
        "ai_inference_confidence": "low",
        "ai_inference_rationale": rationale,
    }


def _default_unclear_inference(review_item_id: str, rationale: str) -> dict[str, Any]:
    inferred = _blank_inference(review_item_id, rationale)
    inferred["human_overall_judgment_inferred"] = "unclear"
    for field in PER_USAGE_INFERRED_COLUMNS:
        inferred[field] = "not_sure"
    inferred["human_evidence_type_judgment_inferred"] = "not_sure"
    inferred["human_field_marks_judgment_inferred"] = "not_sure"
    inferred["human_issue_categories"] = ["needs_second_review"]
    inferred["calibration_priority"] = "medium"
    return inferred


def _validate_inference(inferred: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    if inferred.get("human_overall_judgment_inferred") not in OVERALL_ALLOWED:
        errors.append("invalid human_overall_judgment_inferred")

    for field in PER_USAGE_INFERRED_COLUMNS:
        if inferred.get(field) not in PER_USAGE_ALLOWED:
            errors.append(f"invalid {field}")

    if inferred.get("human_evidence_type_judgment_inferred") not in EVIDENCE_TYPE_ALLOWED:
        errors.append("invalid human_evidence_type_judgment_inferred")
    if inferred.get("human_field_marks_judgment_inferred") not in FIELD_MARKS_ALLOWED:
        errors.append("invalid human_field_marks_judgment_inferred")

    raw_categories = inferred.get("human_issue_categories")
    if not isinstance(raw_categories, list):
        errors.append("human_issue_categories must be list")
    else:
        for item in raw_categories:
            if str(item) not in ISSUE_CATEGORIES_ALLOWED:
                errors.append(f"invalid issue category: {item}")

    if inferred.get("calibration_priority") not in CALIBRATION_PRIORITY_ALLOWED:
        errors.append("invalid calibration_priority")
    if inferred.get("ai_inference_confidence") not in CONFIDENCE_ALLOWED:
        errors.append("invalid ai_inference_confidence")

    rationale = inferred.get("ai_inference_rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        errors.append("ai_inference_rationale must be non-empty")

    return errors


def _build_prompt(row: dict[str, str]) -> str:
    review_item_id = str(row.get("review_item_id") or "")
    note = _extract_note_text(row)

    payload = {
        "review_item_id": review_item_id,
        "human_notes": note,
        "policy_status": str(row.get("policy_status") or ""),
        "evidence_type": str(row.get("evidence_type") or ""),
        "review_status": str(row.get("review_status") or ""),
        "failure_reason": str(row.get("failure_reason") or ""),
        "global_quality_score": str(row.get("global_quality_score") or ""),
        "basic_identification_score": str(row.get("basic_identification_score") or ""),
        "field_observation_score": str(row.get("field_observation_score") or ""),
        "confusion_learning_score": str(row.get("confusion_learning_score") or ""),
        "morphology_learning_score": str(row.get("morphology_learning_score") or ""),
        "species_card_score": str(row.get("species_card_score") or ""),
        "indirect_evidence_learning_score": str(row.get("indirect_evidence_learning_score") or ""),
        "policy_notes": str(row.get("policy_notes") or ""),
        "visible_field_marks_summary": str(row.get("visible_field_marks_summary") or ""),
        "limitations_summary": str(row.get("limitations_summary") or ""),
    }

    schema_hint = {
        "review_item_id": "string",
        "human_overall_judgment_inferred": sorted(OVERALL_ALLOWED),
        "human_basic_identification_judgment_inferred": sorted(PER_USAGE_ALLOWED),
        "human_field_observation_judgment_inferred": sorted(PER_USAGE_ALLOWED),
        "human_confusion_learning_judgment_inferred": sorted(PER_USAGE_ALLOWED),
        "human_morphology_learning_judgment_inferred": sorted(PER_USAGE_ALLOWED),
        "human_species_card_judgment_inferred": sorted(PER_USAGE_ALLOWED),
        "human_indirect_evidence_learning_judgment_inferred": sorted(PER_USAGE_ALLOWED),
        "human_evidence_type_judgment_inferred": sorted(EVIDENCE_TYPE_ALLOWED),
        "human_field_marks_judgment_inferred": sorted(FIELD_MARKS_ALLOWED),
        "human_issue_categories": sorted(ISSUE_CATEGORIES_ALLOWED),
        "calibration_priority": sorted(CALIBRATION_PRIORITY_ALLOWED),
        "ai_inference_confidence": sorted(CONFIDENCE_ALLOWED),
        "ai_inference_rationale": "short explanation",
    }

    return (
        "You are labeling calibration metadata from human-written review notes.\n"
        "Rules:\n"
        "- Human notes are source of truth.\n"
        "- Do not invent judgments not supported by notes.\n"
        "- If ambiguous, use unclear or not_sure.\n"
        "- If note empty, use blank labels.\n"
        "- Never change taxonomy, profile, policy thresholds, runtime, or materialization.\n"
        "Return strict JSON object only with this schema and allowed values:\n"
        f"{json.dumps(schema_hint, ensure_ascii=True, indent=2)}\n"
        "Input row:\n"
        f"{json.dumps(payload, ensure_ascii=True)}"
    )


def _build_policy_only_prompt(row: dict[str, str]) -> str:
    """Prompt for rows with no human notes: infer solely from policy and quality data."""
    review_item_id = str(row.get("review_item_id") or "")

    payload = {
        "review_item_id": review_item_id,
        "human_notes": "(none — reviewer left no notes)",
        "policy_status": str(row.get("policy_status") or ""),
        "evidence_type": str(row.get("evidence_type") or ""),
        "review_status": str(row.get("review_status") or ""),
        "failure_reason": str(row.get("failure_reason") or ""),
        "global_quality_score": str(row.get("global_quality_score") or ""),
        "basic_identification_score": str(row.get("basic_identification_score") or ""),
        "field_observation_score": str(row.get("field_observation_score") or ""),
        "confusion_learning_score": str(row.get("confusion_learning_score") or ""),
        "morphology_learning_score": str(row.get("morphology_learning_score") or ""),
        "species_card_score": str(row.get("species_card_score") or ""),
        "basic_identification_policy": str(row.get("basic_identification_policy") or ""),
        "field_observation_policy": str(row.get("field_observation_policy") or ""),
        "confusion_learning_policy": str(row.get("confusion_learning_policy") or ""),
        "morphology_learning_policy": str(row.get("morphology_learning_policy") or ""),
        "species_card_policy": str(row.get("species_card_policy") or ""),
        "policy_notes": str(row.get("policy_notes") or ""),
        "visible_field_marks_summary": str(row.get("visible_field_marks_summary") or ""),
        "limitations_summary": str(row.get("limitations_summary") or ""),
        "technical_quality": str(row.get("technical_quality") or ""),
        "subject_visibility": str(row.get("subject_visibility") or ""),
        "diagnostic_feature_visibility": str(row.get("diagnostic_feature_visibility") or ""),
    }

    schema_hint = {
        "review_item_id": "string",
        "human_overall_judgment_inferred": sorted(OVERALL_ALLOWED),
        "human_basic_identification_judgment_inferred": sorted(PER_USAGE_ALLOWED),
        "human_field_observation_judgment_inferred": sorted(PER_USAGE_ALLOWED),
        "human_confusion_learning_judgment_inferred": sorted(PER_USAGE_ALLOWED),
        "human_morphology_learning_judgment_inferred": sorted(PER_USAGE_ALLOWED),
        "human_species_card_judgment_inferred": sorted(PER_USAGE_ALLOWED),
        "human_indirect_evidence_learning_judgment_inferred": sorted(PER_USAGE_ALLOWED),
        "human_evidence_type_judgment_inferred": sorted(EVIDENCE_TYPE_ALLOWED),
        "human_field_marks_judgment_inferred": sorted(FIELD_MARKS_ALLOWED),
        "human_issue_categories": sorted(ISSUE_CATEGORIES_ALLOWED),
        "calibration_priority": sorted(CALIBRATION_PRIORITY_ALLOWED),
        "ai_inference_confidence": sorted(CONFIDENCE_ALLOWED),
        "ai_inference_rationale": "short explanation",
    }

    return (
        "You are inferring calibration labels for a PMP policy review row where the human "
        "reviewer left NO notes. Infer solely from policy_status, quality scores, "
        "per-usage policies, visible field marks, limitations, and technical quality.\n"
        "Rules:\n"
        "- If policy_status is profile_valid and scores are consistently high (>=70) across "
        "all relevant uses, set human_overall_judgment_inferred=accept.\n"
        "- If profile_valid but some scores are very low (<40) or technical_quality=unusable, "
        "set human_overall_judgment_inferred=too_strict and include too_strict in "
        "human_issue_categories.\n"
        "- Set ai_inference_confidence to low or medium — this is a policy-only inference.\n"
        "- Use blank for per-usage judgments unless scores clearly indicate a problem.\n"
        "- Do not invent information not present in the policy data.\n"
        "- Never change taxonomy, profile, policy thresholds, runtime, or materialization.\n"
        "Return strict JSON object only with this schema and allowed values:\n"
        f"{json.dumps(schema_hint, ensure_ascii=True, indent=2)}\n"
        "Input row:\n"
        f"{json.dumps(payload, ensure_ascii=True)}"
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
        if stripped.endswith("```"):
            stripped = stripped[:-3].strip()
    return json.loads(stripped)


def _label_with_gemini(
    *,
    prompt: str,
    api_key: str,
    model: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
        },
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        raw = json.loads(response.read().decode("utf-8"))

    candidates = raw.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("Gemini response missing candidates")

    first = candidates[0]
    content = first.get("content") if isinstance(first, dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list) or not parts:
        raise ValueError("Gemini response missing text part")

    text = parts[0].get("text") if isinstance(parts[0], dict) else None
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Gemini response text is empty")

    return _extract_json_object(text)


def _add_issue(inferred: dict[str, Any], issue: str) -> None:
    categories = inferred.get("human_issue_categories")
    if not isinstance(categories, list):
        categories = []
        inferred["human_issue_categories"] = categories
    if issue not in categories:
        categories.append(issue)


def _infer_with_rules(row: dict[str, str]) -> dict[str, Any] | None:
    review_item_id = str(row.get("review_item_id") or "")
    note = _extract_note_text(row)
    if not note:
        return None

    norm = _normalized_text(note)
    policy_status = _normalized_text(str(row.get("policy_status") or ""))
    evidence_type = _normalized_text(str(row.get("evidence_type") or ""))

    inferred = _blank_inference(review_item_id, "rule_based_inference")
    matched = False

    if (
        _contains_any(
            norm, ("photo parfaite", "tres bonne photo", "tr\u00e8s bonne photo", "bonne photo")
        )
        and policy_status == "profile_failed"
    ):
        inferred["human_overall_judgment_inferred"] = "too_strict"
        inferred["calibration_priority"] = "high"
        inferred["ai_inference_confidence"] = "high"
        inferred["ai_inference_rationale"] = (
            "Note describes strong image quality while policy_status is profile_failed."
        )
        _add_issue(inferred, "schema_false_negative")
        _add_issue(inferred, "too_strict")
        matched = True

    if (
        policy_status == "pre_ai_rejected" or _contains_any(norm, ("pre-ai", "pre ai", "preai"))
    ) and _contains_any(norm, RECOGNIZABLE_PATTERNS):
        inferred["human_overall_judgment_inferred"] = "too_strict"
        inferred["calibration_priority"] = "high"
        inferred["ai_inference_confidence"] = "high"
        inferred["ai_inference_rationale"] = (
            "Note indicates recognizable media despite pre_ai_rejected status."
        )
        _add_issue(inferred, "pre_ai_false_negative")
        _add_issue(inferred, "too_strict")
        matched = True

    if "erreur ici" in norm and _contains_any(
        norm,
        (
            "autre espece",
            "autre esp\u00e8ce",
            "another species",
            "espece dominante",
            "esp\u00e8ce dominante",
            "multiple species",
            "plusieurs especes",
            "plusieurs esp\u00e8ces",
        ),
    ):
        inferred["human_overall_judgment_inferred"] = "reject"
        inferred["human_evidence_type_judgment_inferred"] = "wrong"
        inferred["calibration_priority"] = "high"
        inferred["ai_inference_confidence"] = "high"
        inferred["ai_inference_rationale"] = (
            "Note reports target mismatch or another dominant species."
        )
        _add_issue(inferred, "target_taxon_mismatch")
        _add_issue(inferred, "evidence_type_error")
        matched = True

    if evidence_type == "habitat" and _contains_any(
        norm,
        ("mauvaise observation", "impossible de savoir", "impossible to know", "not useful"),
    ):
        inferred["human_overall_judgment_inferred"] = "too_permissive"
        inferred["human_field_observation_judgment_inferred"] = "too_permissive"
        inferred["calibration_priority"] = "high"
        inferred["ai_inference_confidence"] = "medium"
        inferred["ai_inference_rationale"] = (
            "Habitat evidence is described as not informative for target species."
        )
        _add_issue(inferred, "habitat_too_permissive")
        _add_issue(inferred, "field_observation_too_permissive")
        _add_issue(inferred, "too_permissive")
        matched = True

    if "trop critique" in norm:
        if inferred["human_overall_judgment_inferred"] == "blank":
            inferred["human_overall_judgment_inferred"] = "too_strict"
        inferred["calibration_priority"] = "medium"
        inferred["ai_inference_confidence"] = "medium"
        inferred["ai_inference_rationale"] = "Note explicitly states the analysis is too critical."
        _add_issue(inferred, "too_strict")
        matched = True

    if "bonne analyse" in norm:
        if inferred["human_overall_judgment_inferred"] == "blank":
            inferred["human_overall_judgment_inferred"] = "accept"
        inferred["calibration_priority"] = "low"
        inferred["ai_inference_confidence"] = "medium"
        inferred["ai_inference_rationale"] = "Note explicitly indicates good analysis."
        _add_issue(inferred, "accept")
        matched = True

    if _contains_any(
        norm,
        (
            "score global je ne sais pas",
            "score global: je ne sais pas",
            "global score i dont know",
            "global score unsure",
        ),
    ):
        if inferred["human_overall_judgment_inferred"] == "blank":
            inferred["human_overall_judgment_inferred"] = "unclear"
        if inferred["calibration_priority"] == "low":
            inferred["calibration_priority"] = "medium"
        inferred["ai_inference_confidence"] = "low"
        inferred["ai_inference_rationale"] = (
            "Note explicitly questions global score interpretation."
        )
        _add_issue(inferred, "global_score_uncertainty")
        _add_issue(inferred, "needs_second_review")
        matched = True

    if not matched:
        return None

    categories = inferred["human_issue_categories"]
    if isinstance(categories, list) and not categories:
        _add_issue(inferred, "needs_second_review")

    return inferred


def _finalize_inference(inferred: dict[str, Any], review_item_id: str) -> dict[str, Any]:
    inferred = dict(inferred)
    inferred["review_item_id"] = review_item_id
    categories = inferred.get("human_issue_categories")
    if isinstance(categories, list):
        inferred["human_issue_categories"] = sorted({str(item) for item in categories})
    else:
        inferred["human_issue_categories"] = []
    return inferred


def _inferred_has_signal(inferred: dict[str, Any]) -> bool:
    if inferred.get("human_overall_judgment_inferred") not in {"blank", None}:
        return True
    for field in PER_USAGE_INFERRED_COLUMNS:
        if inferred.get(field) not in {"blank", None}:
            return True
    if inferred.get("human_evidence_type_judgment_inferred") not in {"blank", None}:
        return True
    if inferred.get("human_field_marks_judgment_inferred") not in {"blank", None}:
        return True
    categories = inferred.get("human_issue_categories")
    return isinstance(categories, list) and len(categories) > 0


def _compute_audit(rows: list[dict[str, str]], enriched: list[dict[str, str]]) -> dict[str, Any]:
    input_rows = len(rows)
    rows_with_human_notes = sum(1 for row in rows if _extract_note_text(row))
    rows_without_human_notes = input_rows - rows_with_human_notes

    rows_ai_labeled = sum(1 for row in enriched if row.get("labeling_source") == "ai")
    rows_rule_labeled = sum(1 for row in enriched if row.get("labeling_source") == "rule")

    rows_unlabeled = sum(
        1
        for row in enriched
        if row.get("labeling_source") == "none" and not _inferred_has_signal(row)
    )

    issue_counter = Counter[str]()
    overall_counter = Counter[str]()
    per_usage_counters = {field: Counter[str]() for field in PER_USAGE_INFERRED_COLUMNS}
    calibration_counter = Counter[str]()

    high_priority_items: list[str] = []
    target_taxon_mismatch_items: list[str] = []
    schema_false_negative_items: list[str] = []
    pre_ai_false_negative_items: list[str] = []
    habitat_too_permissive_items: list[str] = []
    needs_second_review_items: list[str] = []

    for row in enriched:
        review_item_id = str(row.get("review_item_id") or "")
        overall_counter[str(row.get("human_overall_judgment_inferred") or "blank")] += 1
        calibration_counter[str(row.get("calibration_priority") or "low")] += 1

        for field in PER_USAGE_INFERRED_COLUMNS:
            per_usage_counters[field][str(row.get(field) or "blank")] += 1

        raw_issues = str(row.get("human_issue_categories") or "")
        issues: list[str]
        if raw_issues.strip():
            issues = [item for item in raw_issues.split("|") if item]
        else:
            issues = []

        for issue in issues:
            issue_counter[issue] += 1
            if issue == "target_taxon_mismatch":
                target_taxon_mismatch_items.append(review_item_id)
            if issue == "schema_false_negative":
                schema_false_negative_items.append(review_item_id)
            if issue == "pre_ai_false_negative":
                pre_ai_false_negative_items.append(review_item_id)
            if issue == "habitat_too_permissive":
                habitat_too_permissive_items.append(review_item_id)
            if issue == "needs_second_review":
                needs_second_review_items.append(review_item_id)

        if str(row.get("calibration_priority") or "") == "high":
            high_priority_items.append(review_item_id)

    return {
        "input_rows": input_rows,
        "rows_with_human_notes": rows_with_human_notes,
        "rows_without_human_notes": rows_without_human_notes,
        "rows_ai_labeled": rows_ai_labeled,
        "rows_rule_labeled": rows_rule_labeled,
        "rows_unlabeled": rows_unlabeled,
        "issue_category_distribution": dict(sorted(issue_counter.items())),
        "overall_judgment_distribution": dict(sorted(overall_counter.items())),
        "per_usage_judgment_distributions": {
            field: dict(sorted(counter.items())) for field, counter in per_usage_counters.items()
        },
        "calibration_priority_distribution": dict(sorted(calibration_counter.items())),
        "high_priority_items": sorted(set(high_priority_items)),
        "target_taxon_mismatch_items": sorted(set(target_taxon_mismatch_items)),
        "schema_false_negative_items": sorted(set(schema_false_negative_items)),
        "pre_ai_false_negative_items": sorted(set(pre_ai_false_negative_items)),
        "habitat_too_permissive_items": sorted(set(habitat_too_permissive_items)),
        "needs_second_review_items": sorted(set(needs_second_review_items)),
    }


def label_human_review_rows(
    rows: list[dict[str, str]],
    *,
    enable_ai: bool,
    ai_api_key: str | None,
    ai_model: str,
    ai_timeout_seconds: int,
) -> list[dict[str, str]]:
    enriched: list[dict[str, str]] = []

    ai_enabled = enable_ai and bool(ai_api_key)

    for row in rows:
        review_item_id = str(row.get("review_item_id") or "")
        note = _extract_note_text(row)

        inferred: dict[str, Any]
        source = "none"

        if not note:
            inferred = _blank_inference(review_item_id, "no_human_note")
        else:
            rule_inference = _infer_with_rules(row)
            if rule_inference is not None:
                inferred = rule_inference
                source = "rule"
            elif ai_enabled:
                prompt = _build_prompt(row)
                try:
                    ai_inference = _label_with_gemini(
                        prompt=prompt,
                        api_key=str(ai_api_key),
                        model=ai_model,
                        timeout_seconds=ai_timeout_seconds,
                    )
                    inferred = ai_inference
                    source = "ai"
                except (
                    json.JSONDecodeError,
                    TimeoutError,
                    urllib.error.URLError,
                    urllib.error.HTTPError,
                    ValueError,
                ):
                    inferred = _default_unclear_inference(
                        review_item_id,
                        "ai_labeling_failed_or_invalid_json",
                    )
                    source = "rule"
            else:
                inferred = _default_unclear_inference(
                    review_item_id,
                    "no_rule_match_and_ai_disabled",
                )
                source = "rule"

        inferred = _finalize_inference(inferred, review_item_id)
        errors = _validate_inference(inferred)
        if errors:
            inferred = _default_unclear_inference(
                review_item_id,
                "validation_failed:" + ";".join(errors),
            )
            inferred = _finalize_inference(inferred, review_item_id)
            source = "rule"

        enriched_row = dict(row)
        for field in INFERRED_COLUMNS:
            if field == "human_issue_categories":
                issues = inferred.get(field)
                if isinstance(issues, list):
                    enriched_row[field] = "|".join(str(item) for item in issues)
                else:
                    enriched_row[field] = ""
                continue
            if field == "labeling_source":
                enriched_row[field] = source
                continue
            enriched_row[field] = str(inferred.get(field) or "")

        enriched.append(enriched_row)

    return enriched


def _read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    return rows, fieldnames


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def _write_jsonl(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = {name: row.get(name, "") for name in fieldnames}
            handle.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_second_pass_workflow(
    *,
    labeled_csv: Path,
    output_jsonl: Path,
    output_audit: Path,
    ai_api_key: str | None,
    ai_model: str,
    ai_timeout_seconds: int,
    dry_run: bool,
) -> dict[str, Any]:
    """Re-run AI inference on rows with labeling_source==none using policy-only prompt."""
    if not ai_api_key:
        raise ValueError("--second-pass requires --enable-ai with a valid API key")

    rows, fieldnames = _read_csv(labeled_csv)
    updated = 0
    second_pass_ids: list[str] = []

    for row in rows:
        if row.get("labeling_source") != "none":
            continue

        review_item_id = str(row.get("review_item_id") or "")
        prompt = _build_policy_only_prompt(row)
        source = "ai"
        try:
            ai_inference = _label_with_gemini(
                prompt=prompt,
                api_key=str(ai_api_key),
                model=ai_model,
                timeout_seconds=ai_timeout_seconds,
            )
            inferred: dict[str, Any] = ai_inference
        except (
            json.JSONDecodeError,
            TimeoutError,
            urllib.error.URLError,
            urllib.error.HTTPError,
            ValueError,
        ):
            inferred = _default_unclear_inference(review_item_id, "second_pass_ai_failed")
            source = "rule"

        inferred = _finalize_inference(inferred, review_item_id)
        errors = _validate_inference(inferred)
        if errors:
            inferred = _default_unclear_inference(
                review_item_id, "second_pass_validation_failed:" + ";".join(errors)
            )
            inferred = _finalize_inference(inferred, review_item_id)
            source = "rule"

        for field in INFERRED_COLUMNS:
            if field == "human_issue_categories":
                issues = inferred.get(field)
                if isinstance(issues, list):
                    row[field] = "|".join(str(item) for item in issues)
                else:
                    row[field] = ""
                continue
            if field == "labeling_source":
                row[field] = source
                continue
            row[field] = str(inferred.get(field) or "")

        second_pass_ids.append(review_item_id)
        updated += 1

    audit_payload = _compute_audit(rows, rows)  # rows are already enriched in-place
    audit_payload["input_csv"] = str(labeled_csv)
    audit_payload["output_csv"] = str(labeled_csv)
    audit_payload["output_jsonl"] = str(output_jsonl)
    audit_payload["ai_enabled"] = True
    audit_payload["dry_run"] = dry_run
    audit_payload["second_pass_applied"] = True
    audit_payload["second_pass_ids"] = sorted(second_pass_ids)

    if not dry_run:
        _write_csv(labeled_csv, rows, fieldnames)
        _write_jsonl(output_jsonl, rows, fieldnames)
        _write_json(output_audit, audit_payload)

    return audit_payload


def run_labeling_workflow(
    *,
    input_csv: Path,
    output_csv: Path,
    output_jsonl: Path,
    output_audit: Path,
    enable_ai: bool,
    ai_api_key: str | None,
    ai_model: str,
    ai_timeout_seconds: int,
    dry_run: bool,
) -> dict[str, Any]:
    rows, fieldnames = _read_csv(input_csv)

    enriched_rows = label_human_review_rows(
        rows,
        enable_ai=enable_ai,
        ai_api_key=ai_api_key,
        ai_model=ai_model,
        ai_timeout_seconds=ai_timeout_seconds,
    )

    output_fieldnames = list(fieldnames)
    for column in INFERRED_COLUMNS:
        if column not in output_fieldnames:
            output_fieldnames.append(column)

    audit_payload = _compute_audit(rows, enriched_rows)
    audit_payload["input_csv"] = str(input_csv)
    audit_payload["output_csv"] = str(output_csv)
    audit_payload["output_jsonl"] = str(output_jsonl)
    audit_payload["ai_enabled"] = bool(enable_ai and ai_api_key)
    audit_payload["dry_run"] = dry_run

    if not dry_run:
        _write_csv(output_csv, enriched_rows, output_fieldnames)
        _write_jsonl(output_jsonl, enriched_rows, output_fieldnames)
        _write_json(output_audit, audit_payload)

    return audit_payload


def main() -> None:
    args = _parse_args()
    api_key = None
    if args.enable_ai or args.second_pass:
        api_key = str(os.environ.get(args.ai_api_key_env) or "").strip() or None

    if args.second_pass:
        summary = run_second_pass_workflow(
            labeled_csv=args.output_csv,
            output_jsonl=args.output_jsonl,
            output_audit=args.output_audit,
            ai_api_key=api_key,
            ai_model=args.ai_model,
            ai_timeout_seconds=args.ai_timeout_seconds,
            dry_run=args.dry_run,
        )
        print(
            "PMP human review second AI pass"
            f" | second_pass_ids={summary.get('second_pass_ids')}"
            f" | rows_ai_labeled={summary['rows_ai_labeled']}"
            f" | rows_unlabeled={summary['rows_unlabeled']}"
            f" | dry_run={summary['dry_run']}"
        )
        return

    summary = run_labeling_workflow(
        input_csv=args.input_csv,
        output_csv=args.output_csv,
        output_jsonl=args.output_jsonl,
        output_audit=args.output_audit,
        enable_ai=args.enable_ai,
        ai_api_key=api_key,
        ai_model=args.ai_model,
        ai_timeout_seconds=args.ai_timeout_seconds,
        dry_run=args.dry_run,
    )

    print(
        "PMP human review AI labeling"
        f" | input_rows={summary['input_rows']}"
        f" | rows_with_human_notes={summary['rows_with_human_notes']}"
        f" | rows_ai_labeled={summary['rows_ai_labeled']}"
        f" | rows_rule_labeled={summary['rows_rule_labeled']}"
        f" | rows_unlabeled={summary['rows_unlabeled']}"
        f" | dry_run={summary['dry_run']}"
    )


if __name__ == "__main__":
    main()
