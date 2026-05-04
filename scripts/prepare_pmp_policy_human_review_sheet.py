#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
from pathlib import Path

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
    "multiple_organisms",
    "partial_organism",
}

REVIEW_SHEET_COLUMNS = [
    "review_item_id",
    "review_priority",
    "review_focus",
    "local_image_path",
    "scientific_name",
    "common_name_en",
    "evidence_type",
    "policy_status",
    "recommended_uses",
    "borderline_uses",
    "blocked_uses",
    "visible_field_marks",
    "limitations",
    "reviewer_overall_judgment",
    "reviewer_notes",
    "reviewer_name",
    "reviewed_at",
]

ADJUDICATION_SHEET_COLUMNS = [
    "review_item_id",
    "review_priority",
    "review_focus",
    "local_image_path",
    "scientific_name",
    "common_name_en",
    "evidence_type",
    "policy_status",
    "recommended_uses",
    "borderline_uses",
    "blocked_uses",
    "reviewer_overall_judgment",
    "reviewer_notes",
    "adjudication_decision",
    "adjudication_rationale",
    "follow_up_bucket",
    "follow_up_detail",
    "adjudicator_name",
    "adjudicated_at",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare a compact PMP human review sheet and a matching adjudication "
            "sheet from a broader human review sample CSV."
        )
    )
    parser.add_argument("--input-csv", type=Path, required=True)
    parser.add_argument("--output-review-csv", type=Path, required=True)
    parser.add_argument("--output-adjudication-csv", type=Path, required=True)
    return parser.parse_args()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def _review_focus(row: dict[str, str]) -> tuple[str, str]:
    policy_status = str(row.get("policy_status") or "").strip()
    evidence_type = str(row.get("evidence_type") or "").strip()
    basic_identification_policy = str(row.get("basic_identification_policy") or "").strip()
    field_observation_policy = str(row.get("field_observation_policy") or "").strip()
    species_card_policy = str(row.get("species_card_policy") or "").strip()

    if policy_status == "profile_failed":
        return "high", "schema_or_profile_failure"
    if policy_status == "pre_ai_rejected":
        return "high", "pre_ai_rejected"
    if evidence_type in INDIRECT_EVIDENCE_TYPES:
        return "high", "indirect_evidence"
    if evidence_type in COMPLEX_EVIDENCE_TYPES:
        return "high", "complex_evidence"
    if field_observation_policy == "eligible" and basic_identification_policy in {
        "borderline",
        "not_recommended",
    }:
        return "medium", "field_observation_vs_identification"
    if species_card_policy == "not_recommended" and field_observation_policy == "eligible":
        return "medium", "species_card_strictness"
    return "low", "general_policy_check"


def _compact_text(value: str) -> str:
    return " ".join(value.split())


def _build_review_row(row: dict[str, str]) -> dict[str, str]:
    priority, focus = _review_focus(row)
    return {
        "review_item_id": str(row.get("review_item_id") or ""),
        "review_priority": priority,
        "review_focus": focus,
        "local_image_path": str(row.get("local_image_path") or ""),
        "scientific_name": str(row.get("scientific_name") or ""),
        "common_name_en": str(row.get("common_name_en") or ""),
        "evidence_type": str(row.get("evidence_type") or ""),
        "policy_status": str(row.get("policy_status") or ""),
        "recommended_uses": str(row.get("eligible_database_uses") or ""),
        "borderline_uses": str(row.get("borderline_database_uses") or ""),
        "blocked_uses": str(row.get("not_recommended_database_uses") or ""),
        "visible_field_marks": _compact_text(str(row.get("visible_field_marks_summary") or "")),
        "limitations": _compact_text(str(row.get("limitations_summary") or "")),
        "reviewer_overall_judgment": "",
        "reviewer_notes": "",
        "reviewer_name": "",
        "reviewed_at": "",
    }


def _build_adjudication_row(review_row: dict[str, str]) -> dict[str, str]:
    return {
        "review_item_id": review_row["review_item_id"],
        "review_priority": review_row["review_priority"],
        "review_focus": review_row["review_focus"],
        "local_image_path": review_row["local_image_path"],
        "scientific_name": review_row["scientific_name"],
        "common_name_en": review_row["common_name_en"],
        "evidence_type": review_row["evidence_type"],
        "policy_status": review_row["policy_status"],
        "recommended_uses": review_row["recommended_uses"],
        "borderline_uses": review_row["borderline_uses"],
        "blocked_uses": review_row["blocked_uses"],
        "reviewer_overall_judgment": "",
        "reviewer_notes": "",
        "adjudication_decision": "",
        "adjudication_rationale": "",
        "follow_up_bucket": "",
        "follow_up_detail": "",
        "adjudicator_name": "",
        "adjudicated_at": "",
    }


def prepare_human_review_sheet(
    *,
    input_csv: Path,
    output_review_csv: Path,
    output_adjudication_csv: Path,
) -> tuple[int, Path, Path]:
    rows = _read_csv(input_csv)
    review_rows = [_build_review_row(row) for row in rows]
    adjudication_rows = [_build_adjudication_row(row) for row in review_rows]
    _write_csv(output_review_csv, review_rows, REVIEW_SHEET_COLUMNS)
    _write_csv(output_adjudication_csv, adjudication_rows, ADJUDICATION_SHEET_COLUMNS)
    return len(review_rows), output_review_csv, output_adjudication_csv


def main() -> None:
    args = _parse_args()
    count, review_path, adjudication_path = prepare_human_review_sheet(
        input_csv=args.input_csv,
        output_review_csv=args.output_review_csv,
        output_adjudication_csv=args.output_adjudication_csv,
    )
    print(
        "Prepared compact PMP human review package"
        f" | rows={count}"
        f" | review_csv={review_path}"
        f" | adjudication_csv={adjudication_path}"
    )


if __name__ == "__main__":
    main()