"""Tests for export_pmp_policy_v1_1_second_review.py."""
from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.export_pmp_policy_v1_1_second_review import (
    OUTPUT_COLUMNS,
    _classify_item_categories,
    _field_marks_summary,
    _format_usage_statuses_brief,
    _limitations_summary,
    run_export,
)

# ── helpers ───────────────────────────────────────────────────────────────────

def _make_labeled_csv(tmp_path: Path, rows: list[dict]) -> Path:
    if not rows:
        p = tmp_path / "labeled.csv"
        p.write_text("")
        return p
    fieldnames = list(rows[0].keys())
    p = tmp_path / "labeled.csv"
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return p


def _make_ai_outputs(tmp_path: Path, entries: dict) -> Path:
    p = tmp_path / "ai_outputs.json"
    p.write_text(json.dumps(entries))
    return p


def _pmp_valid(
    *,
    evidence_type: str = "whole_organism",
    basic_identification: float = 80,
    field_observation: float = 80,
    confusion_learning: float = 75,
    morphology_learning: float = 75,
    species_card: float = 82,
    indirect_evidence_learning: float = 10,
    limitations: list[str] | None = None,
    id_limitations: list[str] | None = None,
    field_marks: list[dict] | None = None,
) -> dict:
    return {
        "review_status": "valid",
        "evidence_type": evidence_type,
        "scores": {
            "global_quality_score": 80,
            "usage_scores": {
                "basic_identification": basic_identification,
                "field_observation": field_observation,
                "confusion_learning": confusion_learning,
                "morphology_learning": morphology_learning,
                "species_card": species_card,
                "indirect_evidence_learning": indirect_evidence_learning,
            },
        },
        "identification_profile": {
            "identification_limitations": id_limitations or [],
            "visible_field_marks": field_marks or [],
        },
        "limitations": limitations or [],
    }


def _row(
    review_item_id: str,
    media_id: str,
    *,
    policy_status: str = "profile_valid",
    recommended_uses: str = "basic_identification|field_observation",
    evidence_type: str = "whole_organism",
    human_judgment: str = "accept",
    human_issue_category: str = "policy_accept",
    scientific_name: str = "Testus testus",
    common_name: str = "Test Bird",
) -> dict:
    return {
        "review_item_id": review_item_id,
        "local_image_path": f"/some/path/images/{media_id}.jpg",
        "scientific_name": scientific_name,
        "common_name_en": common_name,
        "evidence_type": evidence_type,
        "policy_status": policy_status,
        "recommended_uses": recommended_uses,
        "borderline_uses": "",
        "blocked_uses": "",
        "reviewer_overall_judgment_normalized": human_judgment,
        "human_issue_category": human_issue_category,
    }


# ── unit tests ────────────────────────────────────────────────────────────────

def test_output_columns_include_required_fields() -> None:
    required = {
        "review_item_id",
        "media_key",
        "scientific_name",
        "policy_status_current",
        "recommended_uses_current",
        "why_selected_for_second_review",
        "second_review_decision",
        "second_review_main_issue",
        "second_review_notes",
    }
    assert required.issubset(set(OUTPUT_COLUMNS))


def test_output_columns_no_runtime_fields() -> None:
    runtime_fields = {
        "selected_for_quiz",
        "runtime_ready",
        "playable",
        "selectedoptionid",
        "post_answer_feedback",
    }
    assert not runtime_fields.intersection(set(OUTPUT_COLUMNS))


def test_field_marks_summary_empty() -> None:
    assert _field_marks_summary({}) == ""
    assert _field_marks_summary({"identification_profile": {}}) == ""


def test_field_marks_summary_with_marks() -> None:
    pmp = {
        "identification_profile": {
            "visible_field_marks": [
                {"feature": "yellow bill", "body_part": "beak"},
                {"feature": "white neck patch"},
            ]
        }
    }
    result = _field_marks_summary(pmp)
    assert "yellow bill" in result
    assert "beak" in result


def test_limitations_summary_empty() -> None:
    assert _limitations_summary({}) == ""


def test_limitations_summary_with_limitations() -> None:
    pmp = {
        "limitations": ["subject is distant", "low resolution"],
        "identification_profile": {
            "identification_limitations": ["difficult to ID from this angle"]
        },
    }
    result = _limitations_summary(pmp)
    assert "distant" in result


def test_format_usage_statuses_brief_excludes_not_applicable() -> None:
    policy_result = {
        "usage_statuses": {
            "basic_identification": {"status": "eligible"},
            "species_card": {"status": "not_applicable"},
            "field_observation": {"status": "borderline"},
        }
    }
    result = _format_usage_statuses_brief(policy_result)
    assert "basic_identification:eligible" in result
    assert "field_observation:borderline" in result
    assert "not_applicable" not in result


def test_classify_schema_false_negative() -> None:
    row = _row(
        "r001", "123", policy_status="profile_failed",
        human_issue_category="schema_false_negative", human_judgment="too_strict"
    )
    cats = _classify_item_categories(
        row,
        None,
        {},
        {"policy_status": "profile_failed", "eligible_database_uses": [], "usage_statuses": {}},
    )
    assert "schema_false_negative" in cats


def test_classify_multiple_species_target_unclear() -> None:
    row = _row(
        "r002", "124", evidence_type="multiple_organisms",
        human_issue_category="multiple_species_target_unclear",
    )
    cats = _classify_item_categories(
        row,
        None,
        {},
        {"policy_status": "profile_valid", "eligible_database_uses": [], "usage_statuses": {}},
    )
    assert "multiple_species_target_unclear" in cats


def test_classify_same_species_multiple_individuals() -> None:
    row = _row(
        "r003", "125", evidence_type="multiple_organisms",
        human_issue_category="same_species_multiple_individuals_ok",
    )
    cats = _classify_item_categories(
        row,
        None,
        {},
        {"policy_status": "profile_valid", "eligible_database_uses": [], "usage_statuses": {}},
    )
    assert "same_species_multiple_individuals_ok" in cats


def test_classify_species_card_eligible() -> None:
    row = _row("r004", "126", recommended_uses="basic_identification|species_card")
    cats = _classify_item_categories(
        row,
        None,
        {},
        {
            "policy_status": "profile_valid",
            "eligible_database_uses": ["basic_identification", "species_card"],
            "usage_statuses": {},
        },
    )
    assert "species_card_eligible" in cats


# ── integration tests ──────────────────────────────────────────────────────────

def test_run_export_creates_all_outputs(tmp_path: Path) -> None:
    """Export should create CSV, JSONL, README."""
    media_id = "11111111"
    media_key = f"inaturalist::{media_id}"
    labeled_rows = [_row("review-0001", media_id)]
    ai_entries = {media_key: {"pedagogical_media_profile": _pmp_valid()}}
    labeled_csv = _make_labeled_csv(tmp_path, labeled_rows)
    ai_path = _make_ai_outputs(tmp_path, ai_entries)

    out_csv = tmp_path / "review.csv"
    out_jsonl = tmp_path / "review.jsonl"
    out_readme = tmp_path / "readme.md"

    result = run_export(
        input_labeled_csv=labeled_csv,
        input_ai_outputs=ai_path,
        input_delta_audit=tmp_path / "no_delta.json",
        input_optional_signals=tmp_path / "no_signals.csv",
        input_manifest=tmp_path / "no_manifest.json",
        output_csv=out_csv,
        output_jsonl=out_jsonl,
        output_readme=out_readme,
    )
    assert out_csv.exists()
    assert out_jsonl.exists()
    assert out_readme.exists()
    assert result["total_rows"] >= 1


def test_run_export_is_deterministic(tmp_path: Path) -> None:
    """Running export twice produces identical CSV output."""
    rows = [_row(f"review-{i:04d}", str(10000000 + i)) for i in range(10)]
    ai_entries = {}
    for i in range(10):
        media_key = f"inaturalist::{10000000 + i}"
        ai_entries[media_key] = {"pedagogical_media_profile": _pmp_valid()}

    labeled_csv = _make_labeled_csv(tmp_path, rows)
    ai_path = _make_ai_outputs(tmp_path, ai_entries)

    out1 = tmp_path / "run1.csv"
    out2 = tmp_path / "run2.csv"

    run_export(
        input_labeled_csv=labeled_csv,
        input_ai_outputs=ai_path,
        input_delta_audit=tmp_path / "no_delta.json",
        input_optional_signals=tmp_path / "no_signals.csv",
        input_manifest=tmp_path / "no_manifest.json",
        output_csv=out1,
        output_jsonl=tmp_path / "r1.jsonl",
        output_readme=tmp_path / "r1.md",
    )
    run_export(
        input_labeled_csv=labeled_csv,
        input_ai_outputs=ai_path,
        input_delta_audit=tmp_path / "no_delta.json",
        input_optional_signals=tmp_path / "no_signals.csv",
        input_manifest=tmp_path / "no_manifest.json",
        output_csv=out2,
        output_jsonl=tmp_path / "r2.jsonl",
        output_readme=tmp_path / "r2.md",
    )
    assert out1.read_text() == out2.read_text()


def test_run_export_csv_has_correct_columns(tmp_path: Path) -> None:
    media_id = "22222222"
    media_key = f"inaturalist::{media_id}"
    labeled_rows = [_row("review-0002", media_id)]
    ai_entries = {media_key: {"pedagogical_media_profile": _pmp_valid()}}
    labeled_csv = _make_labeled_csv(tmp_path, labeled_rows)
    ai_path = _make_ai_outputs(tmp_path, ai_entries)

    out_csv = tmp_path / "review.csv"
    run_export(
        input_labeled_csv=labeled_csv,
        input_ai_outputs=ai_path,
        input_delta_audit=tmp_path / "no_delta.json",
        input_optional_signals=tmp_path / "no_signals.csv",
        input_manifest=tmp_path / "no_manifest.json",
        output_csv=out_csv,
        output_jsonl=tmp_path / "review.jsonl",
        output_readme=tmp_path / "readme.md",
    )
    with out_csv.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert set(reader.fieldnames or []) == set(OUTPUT_COLUMNS)


def test_run_export_labeled_items_always_included(tmp_path: Path) -> None:
    """All labeled CSV items must appear in the export."""
    n = 5
    rows = [
        _row(
            f"review-{i:04d}",
            str(30000000 + i),
            human_issue_category="schema_false_negative",
            policy_status="profile_failed",
            recommended_uses="",
        )
        for i in range(n)
    ]
    ai_entries = {}
    for i in range(n):
        media_key = f"inaturalist::{30000000 + i}"
        ai_entries[media_key] = {
            "pedagogical_media_profile": {
                "review_status": "failed",
                "failure_reason": "schema_validation_failed",
            }
        }

    labeled_csv = _make_labeled_csv(tmp_path, rows)
    ai_path = _make_ai_outputs(tmp_path, ai_entries)
    out_csv = tmp_path / "review.csv"

    run_export(
        input_labeled_csv=labeled_csv,
        input_ai_outputs=ai_path,
        input_delta_audit=tmp_path / "no_delta.json",
        input_optional_signals=tmp_path / "no_signals.csv",
        input_manifest=tmp_path / "no_manifest.json",
        output_csv=out_csv,
        output_jsonl=tmp_path / "review.jsonl",
        output_readme=tmp_path / "readme.md",
    )
    with out_csv.open(encoding="utf-8") as f:
        output_rows = list(csv.DictReader(f))
    output_ids = {r["review_item_id"] for r in output_rows}
    for row in rows:
        assert row["review_item_id"] in output_ids, (
            f"Labeled item {row['review_item_id']} missing from export"
        )


def test_run_export_includes_targeted_categories(tmp_path: Path) -> None:
    """Export should cover multiple categories."""
    # Create items for different categories
    rows = [
        _row("r-schema-001", "41000001", policy_status="profile_failed",
             human_issue_category="schema_false_negative", human_judgment="too_strict"),
        _row("r-multi-001", "41000002", evidence_type="multiple_organisms",
             human_issue_category="multiple_species_target_unclear", human_judgment="accept"),
        _row("r-habit-001", "41000003", evidence_type="habitat",
             recommended_uses="indirect_evidence_learning",
             human_issue_category="habitat_too_permissive", human_judgment="accept"),
        _row(
            "r-ctrl-001",
            "41000004",
            recommended_uses=(
                "basic_identification|field_observation|"
                "confusion_learning|morphology_learning|species_card"
            ),
            human_issue_category="policy_accept",
            human_judgment="accept",
        ),
    ]
    ai_entries: dict = {}
    ai_entries["inaturalist::41000001"] = {
        "pedagogical_media_profile": {
            "review_status": "failed",
            "failure_reason": "schema_validation_failed",
        }
    }
    ai_entries["inaturalist::41000002"] = {
        "pedagogical_media_profile": _pmp_valid(evidence_type="multiple_organisms")
    }
    ai_entries["inaturalist::41000003"] = {
        "pedagogical_media_profile": _pmp_valid(
            evidence_type="habitat", indirect_evidence_learning=75
        )
    }
    ai_entries["inaturalist::41000004"] = {"pedagogical_media_profile": _pmp_valid()}

    labeled_csv = _make_labeled_csv(tmp_path, rows)
    ai_path = _make_ai_outputs(tmp_path, ai_entries)
    out_csv = tmp_path / "review.csv"

    run_export(
        input_labeled_csv=labeled_csv,
        input_ai_outputs=ai_path,
        input_delta_audit=tmp_path / "no_delta.json",
        input_optional_signals=tmp_path / "no_signals.csv",
        input_manifest=tmp_path / "no_manifest.json",
        output_csv=out_csv,
        output_jsonl=tmp_path / "review.jsonl",
        output_readme=tmp_path / "readme.md",
    )
    with out_csv.open(encoding="utf-8") as f:
        output_rows = list(csv.DictReader(f))

    all_why = " ".join(r.get("why_selected_for_second_review", "") for r in output_rows)
    assert "schema_false_negative" in all_why
    assert "multiple_species_target_unclear" in all_why
