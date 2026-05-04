from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.label_pmp_policy_human_review_with_ai import (
    INFERRED_COLUMNS,
    OVERALL_ALLOWED,
    _validate_inference,
    run_labeling_workflow,
)


def _write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _base_row(
    *, review_item_id: str, note: str, policy_status: str, evidence_type: str
) -> dict[str, str]:
    return {
        "review_item_id": review_item_id,
        "human_notes": note,
        "policy_status": policy_status,
        "evidence_type": evidence_type,
        "review_status": "valid",
        "failure_reason": "",
        "global_quality_score": "80",
        "basic_identification_score": "70",
        "field_observation_score": "70",
        "confusion_learning_score": "70",
        "morphology_learning_score": "70",
        "species_card_score": "70",
        "indirect_evidence_learning_score": "",
        "policy_notes": "",
        "visible_field_marks_summary": "",
        "limitations_summary": "",
    }


def _run(
    tmp_path: Path, rows: list[dict[str, str]]
) -> tuple[list[dict[str, str]], dict[str, object]]:
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"
    output_jsonl = tmp_path / "output.jsonl"
    output_audit = tmp_path / "audit.json"

    fieldnames = list(rows[0].keys())
    _write_csv(input_csv, rows, fieldnames)

    summary = run_labeling_workflow(
        input_csv=input_csv,
        output_csv=output_csv,
        output_jsonl=output_jsonl,
        output_audit=output_audit,
        enable_ai=False,
        ai_api_key=None,
        ai_model="gemini-3.1-flash-lite-preview",
        ai_timeout_seconds=1,
        dry_run=False,
    )

    output_rows = _read_csv(output_csv)
    assert output_jsonl.exists()
    assert output_audit.exists()
    assert summary["input_rows"] == len(rows)
    return output_rows, json.loads(output_audit.read_text(encoding="utf-8"))


def test_csv_read_write_and_inferred_columns_present(tmp_path: Path) -> None:
    rows = [
        _base_row(
            review_item_id="r1",
            note="",
            policy_status="profile_valid",
            evidence_type="whole_organism",
        )
    ]
    output_rows, _ = _run(tmp_path, rows)

    assert len(output_rows) == 1
    for column in INFERRED_COLUMNS:
        assert column in output_rows[0]


def test_allowed_label_validation() -> None:
    sample = {
        "human_overall_judgment_inferred": "accept",
        "human_basic_identification_judgment_inferred": "agree",
        "human_field_observation_judgment_inferred": "agree",
        "human_confusion_learning_judgment_inferred": "agree",
        "human_morphology_learning_judgment_inferred": "agree",
        "human_species_card_judgment_inferred": "agree",
        "human_indirect_evidence_learning_judgment_inferred": "not_sure",
        "human_evidence_type_judgment_inferred": "correct",
        "human_field_marks_judgment_inferred": "useful",
        "human_issue_categories": ["accept"],
        "calibration_priority": "low",
        "ai_inference_confidence": "medium",
        "ai_inference_rationale": "supported by note",
    }
    assert not _validate_inference(sample)


def test_empty_note_stays_blank(tmp_path: Path) -> None:
    rows = [
        _base_row(
            review_item_id="r1",
            note="",
            policy_status="profile_valid",
            evidence_type="whole_organism",
        )
    ]
    output_rows, _ = _run(tmp_path, rows)
    row = output_rows[0]

    assert row["human_overall_judgment_inferred"] == "blank"
    assert row["human_issue_categories"] == ""
    assert row["labeling_source"] == "none"


def test_profile_failed_photo_parfaite_schema_false_negative(tmp_path: Path) -> None:
    rows = [
        _base_row(
            review_item_id="r1",
            note="photo parfaite, tres bonne photo",
            policy_status="profile_failed",
            evidence_type="whole_organism",
        )
    ]
    output_rows, audit = _run(tmp_path, rows)
    row = output_rows[0]

    assert row["human_overall_judgment_inferred"] == "too_strict"
    assert "schema_false_negative" in row["human_issue_categories"].split("|")
    assert row["calibration_priority"] == "high"
    assert "r1" in audit["schema_false_negative_items"]


def test_pre_ai_rejected_recognizable_becomes_pre_ai_false_negative(tmp_path: Path) -> None:
    rows = [
        _base_row(
            review_item_id="r1",
            note="pre-AI rejected but recognizable",
            policy_status="pre_ai_rejected",
            evidence_type="whole_organism",
        )
    ]
    output_rows, audit = _run(tmp_path, rows)
    row = output_rows[0]

    assert "pre_ai_false_negative" in row["human_issue_categories"].split("|")
    assert row["human_overall_judgment_inferred"] in OVERALL_ALLOWED
    assert "r1" in audit["pre_ai_false_negative_items"]


def test_habitat_impossible_de_savoir_becomes_habitat_too_permissive(tmp_path: Path) -> None:
    rows = [
        _base_row(
            review_item_id="r1",
            note="impossible de savoir sur cette image",
            policy_status="profile_valid",
            evidence_type="habitat",
        )
    ]
    output_rows, audit = _run(tmp_path, rows)
    row = output_rows[0]

    issues = row["human_issue_categories"].split("|")
    assert "habitat_too_permissive" in issues
    assert row["human_field_observation_judgment_inferred"] == "too_permissive"
    assert "r1" in audit["habitat_too_permissive_items"]


def test_erreur_ici_multiple_species_becomes_target_taxon_mismatch(tmp_path: Path) -> None:
    rows = [
        _base_row(
            review_item_id="r1",
            note="erreur ici, autre espece dominante, multiple species",
            policy_status="profile_valid",
            evidence_type="whole_organism",
        )
    ]
    output_rows, audit = _run(tmp_path, rows)
    row = output_rows[0]

    assert "target_taxon_mismatch" in row["human_issue_categories"].split("|")
    assert row["human_evidence_type_judgment_inferred"] == "wrong"
    assert "r1" in audit["target_taxon_mismatch_items"]


def test_trop_critique_becomes_too_strict(tmp_path: Path) -> None:
    rows = [
        _base_row(
            review_item_id="r1",
            note="analyse trop critique",
            policy_status="profile_valid",
            evidence_type="whole_organism",
        )
    ]
    output_rows, _ = _run(tmp_path, rows)

    assert output_rows[0]["human_overall_judgment_inferred"] == "too_strict"


def test_audit_distributions_are_produced(tmp_path: Path) -> None:
    rows = [
        _base_row(
            review_item_id="r1",
            note="bonne analyse",
            policy_status="profile_valid",
            evidence_type="whole_organism",
        ),
        _base_row(
            review_item_id="r2",
            note="",
            policy_status="profile_valid",
            evidence_type="whole_organism",
        ),
    ]
    _, audit = _run(tmp_path, rows)

    assert "issue_category_distribution" in audit
    assert "overall_judgment_distribution" in audit
    assert "per_usage_judgment_distributions" in audit
    assert "calibration_priority_distribution" in audit


def test_no_image_fetching_when_ai_disabled(tmp_path: Path, monkeypatch) -> None:
    import urllib.request

    rows = [
        _base_row(
            review_item_id="r1",
            note="bonne analyse",
            policy_status="profile_valid",
            evidence_type="whole_organism",
        )
    ]

    called = {"value": False}

    def _forbidden(*args, **kwargs):
        called["value"] = True
        raise AssertionError("network call should not happen")

    monkeypatch.setattr(urllib.request, "urlopen", _forbidden)
    _run(tmp_path, rows)

    assert called["value"] is False


def test_no_runtime_or_materialization_side_effects(tmp_path: Path) -> None:
    rows = [
        _base_row(
            review_item_id="r1",
            note="bonne analyse",
            policy_status="profile_valid",
            evidence_type="whole_organism",
        )
    ]
    output_rows, _ = _run(tmp_path, rows)

    row = output_rows[0]
    assert "runtime_ready" not in row
    assert "materialization" not in row


def test_free_text_in_overall_column_is_used_as_note(tmp_path: Path) -> None:
    row = _base_row(
        review_item_id="r1",
        note="",
        policy_status="profile_failed",
        evidence_type="whole_organism",
    )
    row["human_overall_judgment"] = "photo parfaite"

    output_rows, audit = _run(tmp_path, [row])

    assert output_rows[0]["human_overall_judgment_inferred"] == "too_strict"
    assert "schema_false_negative" in output_rows[0]["human_issue_categories"].split("|")
    assert audit["rows_with_human_notes"] == 1
