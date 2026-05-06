from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import materialize_golden_pack_belgian_birds_mvp_v1 as mod
from scripts.materialize_golden_pack_belgian_birds_mvp_v1 import ContractError


def _build_base_inputs() -> tuple[dict, dict, dict, dict, dict, dict]:
    safe_targets = [f"taxon:birds:{idx:06d}" for idx in range(1, 31)]

    plan_items = []
    for idx, tid in enumerate(safe_targets, start=1):
        plan_items.append(
            {
                "taxon_kind": "canonical_taxon",
                "taxon_id": tid,
                "locale": "fr",
                "decision": "auto_accept",
                "chosen_value": f"Nom FR {idx}",
            }
        )
    for idx in range(1, 91):
        rid = f"ref:birds:{idx:06d}"
        plan_items.append(
            {
                "taxon_kind": "referenced_taxon",
                "taxon_id": rid,
                "locale": "fr",
                "decision": "auto_accept",
                "chosen_value": f"Distracteur FR {idx}",
            }
        )

    plan = {
        "schema_version": "localized_name_apply_plan.v1",
        "metrics": {"safe_ready_targets_from_plan": safe_targets},
        "items": plan_items,
    }

    materialization = {
        "questions": [
            {
                "target_canonical_taxon_id": tid,
                "target_playable_item_id": f"playable:qr:media:inaturalist:{idx}",
                "options": [
                    {
                        "is_correct": True,
                        "canonical_taxon_id": tid,
                        "playable_item_id": f"playable:qr:media:inaturalist:{idx}",
                    }
                ],
            }
            for idx, tid in enumerate(safe_targets, start=1)
        ]
    }

    projected = []
    ref_cursor = 1
    for tid in safe_targets:
        for rank in range(1, 4):
            projected.append(
                {
                    "status": "candidate",
                    "target_canonical_taxon_id": tid,
                    "candidate_taxon_ref_type": "referenced_taxon",
                    "candidate_taxon_ref_id": f"ref:birds:{ref_cursor:06d}",
                    "source_rank": rank,
                }
            )
            ref_cursor += 1
    distractor = {"projected_records": projected}

    qualified = {
        "qualified_resources": [
            {
                "provenance": {
                    "source": {
                        "source_media_id": str(idx),
                        "raw_payload_ref": f"responses/taxon_birds_{idx:06d}.json#/results/0",
                        "media_license": "cc-by",
                    }
                }
            }
            for idx in range(1, 31)
        ]
    }

    inat_manifest = {
        "media_downloads": [
            {
                "source_media_id": str(idx),
                "image_path": f"images/{idx}.jpg",
                "source_url": f"https://example.org/media/{idx}.jpg",
            }
            for idx in range(1, 31)
        ]
    }

    ai_outputs = {
        f"inaturalist::{idx}": {
            "pedagogical_media_profile": {
                "review_status": "valid",
                "evidence_type": "whole_organism",
                "scores": {
                    "global_quality_score": 92,
                    "usage_scores": {
                        "basic_identification": 92,
                        "field_observation": 92,
                        "confusion_learning": 92,
                        "morphology_learning": 92,
                        "species_card": 92,
                        "indirect_evidence_learning": 92,
                    },
                },
            }
        }
        for idx in range(1, 31)
    }

    return plan, materialization, distractor, qualified, inat_manifest, ai_outputs


def _patch_all_inputs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, fail_media_ids: set[str] | None = None, mutate=None) -> None:
    plan, materialization, distractor, qualified, manifest, ai_outputs = _build_base_inputs()

    if fail_media_ids:
        for sid in fail_media_ids:
            key = f"inaturalist::{sid}"
            if key in ai_outputs:
                ai_outputs[key]["pedagogical_media_profile"]["scores"]["usage_scores"]["basic_identification"] = 55

    if mutate:
        mutate(plan, materialization, distractor, qualified, manifest, ai_outputs)

    def fake_load(path: Path):
        if path == mod.PLAN_PATH:
            return plan
        if path == mod.MATERIALIZATION_SOURCE_PATH:
            return materialization
        if path == mod.DISTRACTOR_PATH:
            return distractor
        if path == mod.QUALIFIED_EXPORT_PATH:
            return qualified
        if path == mod.INAT_MANIFEST_PATH:
            return manifest
        if path == mod.INAT_AI_OUTPUTS_PATH:
            return ai_outputs
        raise AssertionError(f"Unexpected load path: {path}")

    monkeypatch.setattr(mod, "_load_json", fake_load)

    src_root = tmp_path / "src_media"
    src_root.mkdir(parents=True, exist_ok=True)

    def fake_find_media_choice(source_media_id: str, *_args, **_kwargs):
        src = src_root / f"{source_media_id}.jpg"
        src.write_bytes(f"img-{source_media_id}".encode("utf-8"))
        return mod.MediaChoice(
            source_media_id=source_media_id,
            source_url=f"https://example.org/media/{source_media_id}.jpg",
            image_rel_path=f"images/{source_media_id}.jpg",
            image_abs_path=src,
            source_name="inaturalist",
            creator="unit-test",
            license_name="cc-by",
            license_url="https://creativecommons.org/licenses/by/4.0/",
            attribution_text=f"Photo {source_media_id}",
        )

    monkeypatch.setattr(mod, "_find_media_choice", fake_find_media_choice)
    monkeypatch.setattr(mod, "OUTPUT_DIR", tmp_path / "out")
    monkeypatch.setattr(mod, "OUTPUT_MEDIA_DIR", tmp_path / "out" / "media")
    monkeypatch.setattr(mod, "OUTPUT_PACK_PATH", tmp_path / "out" / "pack.json")
    monkeypatch.setattr(mod, "OUTPUT_FAILED_PARTIAL_PACK_PATH", tmp_path / "out" / "failed_build" / "partial_pack.json")
    monkeypatch.setattr(mod, "OUTPUT_MANIFEST_PATH", tmp_path / "out" / "manifest.json")
    monkeypatch.setattr(mod, "OUTPUT_VALIDATION_REPORT_PATH", tmp_path / "out" / "validation_report.json")


def test_success_fixture_writes_runtime_pack_and_validates_schemas(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_all_inputs(monkeypatch, tmp_path)
    pack, manifest, report = mod.write_outputs()

    assert report["status"] == "passed"
    assert len(pack["questions"]) == 30
    assert mod.OUTPUT_PACK_PATH.exists()
    assert not mod.OUTPUT_FAILED_PARTIAL_PACK_PATH.exists()

    mod._json_schema_validate(pack, mod.SCHEMA_PACK_PATH, "pack")
    mod._json_schema_validate(manifest, mod.SCHEMA_MANIFEST_PATH, "manifest")
    mod._json_schema_validate(report, mod.SCHEMA_VALIDATION_REPORT_PATH, "report")


def test_failed_mode_writes_report_and_partial_not_runtime_pack(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_all_inputs(monkeypatch, tmp_path, fail_media_ids={str(i) for i in range(8, 31)})

    with pytest.raises(ContractError, match="Materialization failed with blockers"):
        mod.write_outputs()

    assert mod.OUTPUT_VALIDATION_REPORT_PATH.exists()
    assert mod.OUTPUT_MANIFEST_PATH.exists()
    assert mod.OUTPUT_FAILED_PARTIAL_PACK_PATH.exists()
    assert not mod.OUTPUT_PACK_PATH.exists()

    report = json.loads(mod.OUTPUT_VALIDATION_REPORT_PATH.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    blocker_text = " ".join(report["blockers"])
    assert "unable_to_select_30_targets" in blocker_text
    assert "question_count_expected_30_actual" in blocker_text


def test_partial_pack_is_not_golden_pack_v1_schema_valid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")

    _patch_all_inputs(monkeypatch, tmp_path, fail_media_ids={str(i) for i in range(10, 31)})
    with pytest.raises(ContractError):
        mod.write_outputs()

    partial = json.loads(mod.OUTPUT_FAILED_PARTIAL_PACK_PATH.read_text(encoding="utf-8"))
    schema = json.loads(mod.SCHEMA_PACK_PATH.read_text(encoding="utf-8"))
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=partial, schema=schema)


def test_runtime_output_not_in_docs_evidence_path() -> None:
    assert "docs/audits/evidence" not in str(mod.OUTPUT_PACK_PATH)
    assert "docs/audits/evidence" not in str(mod.OUTPUT_FAILED_PARTIAL_PACK_PATH)


def test_cross_file_invariants_on_success_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_all_inputs(monkeypatch, tmp_path)
    pack, _, _ = mod.write_outputs()

    media_ids = {m["media_id"] for m in pack["media"]}
    media_checksums = {m["media_id"]: m["checksum"].removeprefix("sha256:") for m in pack["media"]}

    assert len(pack["questions"]) == 30
    for q in pack["questions"]:
        assert q["correct_option_id"] in {o["option_id"] for o in q["options"]}
        assert q["primary_media_id"] in media_ids
        assert len(q["options"]) == 4
        assert sum(1 for o in q["options"] if o["is_correct"]) == 1
        assert sum(1 for o in q["options"] if not o["is_correct"]) == 3

        refs = {(o["taxon_ref"]["type"], o["taxon_ref"]["id"]) for o in q["options"]}
        assert len(refs) == 4

        norms = {mod.normalize_localized_name_for_compare(o["display_label"]) for o in q["options"]}
        assert len(norms) == 4

    for m in pack["media"]:
        assert m["runtime_uri"].startswith("media/")
        runtime_abs = mod.OUTPUT_DIR / m["runtime_uri"]
        assert runtime_abs.exists()
        assert mod._sha256_file(runtime_abs) == media_checksums[m["media_id"]]

    heavy = mod._collect_heavy_field_violations(pack)
    assert heavy == []


def test_label_empty_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def mutate(plan, *_):
        for item in plan["items"]:
            if item.get("taxon_kind") == "referenced_taxon":
                item["chosen_value"] = ""
                break

    _patch_all_inputs(monkeypatch, tmp_path, mutate=mutate)
    with pytest.raises(ContractError):
        mod.write_outputs()
    report = json.loads(mod.OUTPUT_VALIDATION_REPORT_PATH.read_text(encoding="utf-8"))
    assert any("insufficient_label_safe_distractors" in " ".join(rt["reason_codes"]) for rt in report["rejected_targets"])


def test_referenced_taxon_without_flag_rejected_in_cross_checks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_all_inputs(monkeypatch, tmp_path)
    pack, _, _ = mod.write_outputs()
    # direct contract check: every referenced_taxon must set referenced_only=true
    for q in pack["questions"]:
        for opt in q["options"]:
            if opt["taxon_ref"]["type"] == "referenced_taxon":
                assert opt.get("referenced_only") is True


def test_media_policy_gate_eligible_vs_borderline() -> None:
    eligible = {
        "inaturalist::1": {
            "pedagogical_media_profile": {
                "review_status": "valid",
                "evidence_type": "whole_organism",
                "scores": {"usage_scores": {"basic_identification": 90}},
            }
        }
    }
    borderline = {
        "inaturalist::2": {
            "pedagogical_media_profile": {
                "review_status": "valid",
                "evidence_type": "whole_organism",
                "scores": {"usage_scores": {"basic_identification": 60}},
            }
        }
    }

    assert mod._evaluate_basic_identification_eligible(eligible, "1") is True
    assert mod._evaluate_basic_identification_eligible(borderline, "2") is False


def test_pack_partial_never_marked_runtime_valid(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_all_inputs(monkeypatch, tmp_path, fail_media_ids={str(i) for i in range(2, 31)})

    with pytest.raises(ContractError):
        mod.write_outputs()

    report = json.loads(mod.OUTPUT_VALIDATION_REPORT_PATH.read_text(encoding="utf-8"))
    manifest = json.loads(mod.OUTPUT_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert any(g["status"] == "failed" for g in manifest["gates"])
    assert manifest["PERSIST_DISTRACTOR_RELATIONSHIPS_V1"] is False
    assert manifest["DATABASE_PHASE_CLOSED"] is False
