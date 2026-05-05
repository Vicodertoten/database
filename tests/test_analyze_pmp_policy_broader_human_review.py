"""Tests for analyze_pmp_policy_broader_human_review.py"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from analyze_pmp_policy_broader_human_review import (  # noqa: E402
    infer_issue_category,
    normalize_judgment,
    run,
)

# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def test_normalize_accept():
    assert normalize_judgment("accept") == "accept"
    assert normalize_judgment("ACCEPT") == "accept"
    assert normalize_judgment("Accept") == "accept"


def test_normalize_too_strict_variants():
    assert normalize_judgment("too_strict") == "too_strict"
    assert normalize_judgment("too_Strict") == "too_strict"
    assert normalize_judgment("TOO__strict") == "too_strict"
    assert normalize_judgment("TOO_STRICT") == "too_strict"


def test_normalize_too_permissive_variants():
    assert normalize_judgment("too_permissive") == "too_permissive"
    assert normalize_judgment("too_permisive") == "too_permissive"
    assert normalize_judgment("TOO_PERMISSIVE") == "too_permissive"


def test_normalize_blank():
    assert normalize_judgment("") == "blank"
    assert normalize_judgment("  ") == "blank"
    assert normalize_judgment(None) == "blank"


def test_normalize_reject():
    assert normalize_judgment("reject") == "reject"
    assert normalize_judgment("REJECT") == "reject"


def test_normalize_unclear():
    assert normalize_judgment("unclear") == "unclear"


# ---------------------------------------------------------------------------
# Issue category inference
# ---------------------------------------------------------------------------


def _row(**kwargs) -> dict:
    """Build a minimal row dict for inference tests."""
    base = {
        "review_focus": "general_policy_check",
        "policy_status": "profile_valid",
        "evidence_type": "whole_organism",
        "reviewer_overall_judgment_normalized": "accept",
        "reviewer_notes_cleaned": "",
        "recommended_uses": "",
        "borderline_uses": "",
        "blocked_uses": "",
    }
    base.update(kwargs)
    return base


def test_infer_schema_false_negative_too_strict():
    row = _row(
        review_focus="schema_or_profile_failure",
        policy_status="profile_failed",
        reviewer_overall_judgment_normalized="too_strict",
        reviewer_notes_cleaned="image moyenne mais clairement utilisable",
    )
    assert infer_issue_category(row) == "schema_false_negative"


def test_infer_schema_false_negative_blank_judgment_with_good_note():
    row = _row(
        review_focus="schema_or_profile_failure",
        policy_status="profile_failed",
        reviewer_overall_judgment_normalized="blank",
        reviewer_notes_cleaned="très bonne image a voir pourquoi elle ne passe pas",
    )
    assert infer_issue_category(row) == "schema_false_negative"


def test_infer_pre_ai_borderline():
    row = _row(
        review_focus="pre_ai_rejected",
        policy_status="pre_ai_rejected",
        reviewer_overall_judgment_normalized="blank",
        reviewer_notes_cleaned="image globalement ok mais probablement trop petite",
    )
    assert infer_issue_category(row) == "pre_ai_borderline"


def test_infer_text_overlay():
    row = _row(
        reviewer_overall_judgment_normalized="too_permissive",
        reviewer_notes_cleaned=(
            "screenshot d'un écran d'identification par le son avec le nom de l'espèce en clair"
        ),
    )
    assert infer_issue_category(row) == "text_overlay_or_answer_visible"


def test_infer_same_species_multiple_individuals_ok():
    row = _row(
        evidence_type="multiple_organisms",
        reviewer_overall_judgment_normalized="accept",
        reviewer_notes_cleaned=(
            "plusieurs individus mais pas un problème car meme espèce. c'est plutot riche"
        ),
    )
    assert infer_issue_category(row) == "same_species_multiple_individuals_ok"


def test_infer_same_species_too_strict():
    row = _row(
        evidence_type="multiple_organisms",
        reviewer_overall_judgment_normalized="too_strict",
        reviewer_notes_cleaned=(
            "très bonne photo avec deux individus de la meme espèce sur la photo"
        ),
    )
    assert infer_issue_category(row) == "same_species_multiple_individuals_ok"


def test_infer_multiple_species_target_unclear():
    row = _row(
        evidence_type="multiple_organisms",
        reviewer_overall_judgment_normalized="unclear",
        reviewer_notes_cleaned=(
            "on doit préciser le comportement lorsqu'il y a plusieurs individus "
            "d'espèces DIFFérentes sur la photo"
        ),
    )
    assert infer_issue_category(row) == "multiple_species_target_unclear"


def test_infer_multiple_species_bordel():
    row = _row(
        evidence_type="multiple_organisms",
        reviewer_overall_judgment_normalized="accept",
        reviewer_notes_cleaned="trop de bordel dans la photo. multi espèces, mauvaise qualité",
    )
    assert infer_issue_category(row) == "multiple_species_target_unclear"


def test_infer_habitat_too_permissive():
    row = _row(
        evidence_type="habitat",
        reviewer_overall_judgment_normalized="accept",
        reviewer_notes_cleaned=(
            "score horrible car globalement impossible de savoir de quelle espèce on parle"
        ),
    )
    assert infer_issue_category(row) == "habitat_too_permissive"


def test_infer_species_card_too_permissive():
    row = _row(
        evidence_type="whole_organism",
        recommended_uses="field_observation|species_card",
        reviewer_overall_judgment_normalized="accept",
        reviewer_notes_cleaned="quand meme bizzare de dire oui a species card",
    )
    assert infer_issue_category(row) == "species_card_too_permissive"


def test_infer_rare_model_subject_miss():
    row = _row(
        evidence_type="unknown",
        reviewer_overall_judgment_normalized="unclear",
        reviewer_notes_cleaned=(
            "very distant shot of a peregrine falcon. extremly hard but challenging and possible"
        ),
    )
    assert infer_issue_category(row) == "rare_model_subject_miss"


def test_infer_policy_accept_clean():
    row = _row(
        evidence_type="whole_organism",
        reviewer_overall_judgment_normalized="accept",
        reviewer_notes_cleaned="parfait",
    )
    assert infer_issue_category(row) == "policy_accept"


# ---------------------------------------------------------------------------
# Full run: output files existence
# ---------------------------------------------------------------------------


def test_full_run_produces_outputs(tmp_path):
    """Run the full pipeline on the real input file and verify outputs exist."""
    real_input = (
        REPO_ROOT
        / "docs/audits/human_review"
        / "pmp_policy_v1_broader_400_20260504_human_review_sheet.csv"
    )
    if not real_input.exists():
        pytest.skip("Input CSV not found")

    out_json = tmp_path / "analysis.json"
    out_md = tmp_path / "analysis.md"
    out_csv = tmp_path / "labeled.csv"

    run(
        input_csv=real_input,
        output_json=out_json,
        output_md=out_md,
        output_labeled_csv=out_csv,
    )

    assert out_json.exists(), "JSON evidence file not created"
    assert out_md.exists(), "Markdown report not created"
    assert out_csv.exists(), "Labeled CSV not created"

    with open(out_json) as f:
        data = json.load(f)
    assert data["total_rows"] == 60
    assert "normalized_judgment_distribution" in data
    assert "issue_category_distribution" in data
    assert "schema_false_negative_items" in data


def test_labeled_csv_preserves_input_rows(tmp_path):
    real_input = (
        REPO_ROOT
        / "docs/audits/human_review"
        / "pmp_policy_v1_broader_400_20260504_human_review_sheet.csv"
    )
    if not real_input.exists():
        pytest.skip("Input CSV not found")

    out_csv = tmp_path / "labeled.csv"
    run(
        input_csv=real_input,
        output_json=tmp_path / "ev.json",
        output_md=tmp_path / "report.md",
        output_labeled_csv=out_csv,
    )

    with open(out_csv, newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 60
    # new columns are present
    assert "reviewer_overall_judgment_normalized" in rows[0]
    assert "human_issue_category" in rows[0]
    assert "calibration_priority" in rows[0]


def test_markdown_report_is_written(tmp_path):
    real_input = (
        REPO_ROOT
        / "docs/audits/human_review"
        / "pmp_policy_v1_broader_400_20260504_human_review_sheet.csv"
    )
    if not real_input.exists():
        pytest.skip("Input CSV not found")

    out_md = tmp_path / "report.md"
    run(
        input_csv=real_input,
        output_json=tmp_path / "ev.json",
        output_md=out_md,
        output_labeled_csv=tmp_path / "labeled.csv",
    )

    content = out_md.read_text()
    assert "## Final decision" in content
    assert "READY_FOR_PMP_POLICY_V1_1_PATCHES" in content or "NEEDS_MORE_REVIEW" in content
