from __future__ import annotations

import csv
from pathlib import Path

from scripts.prepare_pmp_policy_human_review_sheet import prepare_human_review_sheet


def _write_input(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "review_item_id",
        "local_image_path",
        "scientific_name",
        "common_name_en",
        "evidence_type",
        "policy_status",
        "eligible_database_uses",
        "borderline_database_uses",
        "not_recommended_database_uses",
        "visible_field_marks_summary",
        "limitations_summary",
        "basic_identification_policy",
        "field_observation_policy",
        "species_card_policy",
    ]
    rows = [
        {
            "review_item_id": "r1",
            "local_image_path": "/tmp/r1.jpg",
            "scientific_name": "Test indirect",
            "common_name_en": "Indirect Bird",
            "evidence_type": "feather",
            "policy_status": "profile_valid",
            "eligible_database_uses": "field_observation|indirect_evidence_learning",
            "borderline_database_uses": "",
            "not_recommended_database_uses": "basic_identification",
            "visible_field_marks_summary": "wing: white patch",
            "limitations_summary": "some blur",
            "basic_identification_policy": "not_recommended",
            "field_observation_policy": "eligible",
            "species_card_policy": "not_recommended",
        },
        {
            "review_item_id": "r2",
            "local_image_path": "/tmp/r2.jpg",
            "scientific_name": "Test failed",
            "common_name_en": "Failed Bird",
            "evidence_type": "",
            "policy_status": "profile_failed",
            "eligible_database_uses": "",
            "borderline_database_uses": "",
            "not_recommended_database_uses": "",
            "visible_field_marks_summary": "",
            "limitations_summary": "",
            "basic_identification_policy": "not_applicable",
            "field_observation_policy": "not_applicable",
            "species_card_policy": "not_applicable",
        },
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_prepare_human_review_sheet_creates_compact_review_and_adjudication(tmp_path: Path) -> None:
    input_csv = tmp_path / "input.csv"
    review_csv = tmp_path / "review.csv"
    adjudication_csv = tmp_path / "adjudication.csv"
    _write_input(input_csv)

    count, _, _ = prepare_human_review_sheet(
        input_csv=input_csv,
        output_review_csv=review_csv,
        output_adjudication_csv=adjudication_csv,
    )

    assert count == 2

    with review_csv.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["review_priority"] == "high"
    assert rows[0]["review_focus"] == "indirect_evidence"
    assert rows[1]["review_focus"] == "schema_or_profile_failure"
    assert rows[0]["recommended_uses"] == "field_observation|indirect_evidence_learning"
    assert rows[0]["reviewer_overall_judgment"] == ""

    with adjudication_csv.open(encoding="utf-8", newline="") as handle:
        adjudication_rows = list(csv.DictReader(handle))

    assert adjudication_rows[0]["review_item_id"] == "r1"
    assert adjudication_rows[0]["adjudication_decision"] == ""
    assert adjudication_rows[1]["review_focus"] == "schema_or_profile_failure"