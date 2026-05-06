from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.materialize_golden_pack_belgian_birds_mvp_v1 import (
    ContractError,
    build_golden_pack,
)
from scripts.synthesize_sprint14b_final_runtime_handoff_readiness import build_synthesis


def test_14c1_synthesis_contracts_pass() -> None:
    payload = build_synthesis()
    assert payload["decision"] == "READY_FOR_RUNTIME_CONTRACTS_WITH_WARNINGS"
    assert payload["names_gate"]["observed_safe_target_count"] >= 30
    assert payload["cross_artifact_invariants"]["plan_hash_match"] is True
    assert payload["cross_artifact_invariants"]["emergency_fallback_count"] == 0


def _build_fake_materializer_inputs(include_canonical_in_top3: bool = False) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    safe_targets = [f"taxon:birds:{idx:06d}" for idx in range(1, 31)]

    plan_items: list[dict[str, Any]] = []
    for idx, target_id in enumerate(safe_targets, start=1):
        plan_items.append(
            {
                "taxon_kind": "canonical_taxon",
                "taxon_id": target_id,
                "locale": "fr",
                "decision": "auto_accept",
                "chosen_value": f"Target FR {idx}",
            }
        )
    for rid, label in [
        ("ref:birds:d1", "Distracteur FR A"),
        ("ref:birds:d2", "Distracteur FR B"),
        ("ref:birds:d3", "Distracteur FR C"),
    ]:
        plan_items.append(
            {
                "taxon_kind": "referenced_taxon",
                "taxon_id": rid,
                "locale": "fr",
                "decision": "auto_accept",
                "chosen_value": label,
            }
        )

    plan_payload = {
        "plan_hash": "test-plan-hash",
        "metrics": {"safe_ready_targets_from_plan": safe_targets},
        "items": plan_items,
    }

    materialization_payload = {
        "questions": [
            {
                "target_canonical_taxon_id": target_id,
                "target_playable_item_id": f"playable:qr:media:inaturalist:{idx}",
                "options": [
                    {
                        "is_correct": True,
                        "canonical_taxon_id": target_id,
                        "playable_item_id": f"playable:qr:media:inaturalist:{idx}",
                        "source": "playable_corpus.v1",
                        "score": 1.0,
                        "reason_codes": ["seed"],
                        "referenced_only": False,
                    }
                ],
            }
            for idx, target_id in enumerate(safe_targets, start=1)
        ]
    }

    projected_records: list[dict[str, Any]] = []
    for idx, target_id in enumerate(safe_targets, start=1):
        base_candidates = [
            {
                "status": "candidate",
                "target_canonical_taxon_id": target_id,
                "candidate_taxon_ref_type": "referenced_taxon",
                "candidate_taxon_ref_id": "ref:birds:d1",
                "source_rank": 1,
            },
            {
                "status": "candidate",
                "target_canonical_taxon_id": target_id,
                "candidate_taxon_ref_type": "referenced_taxon",
                "candidate_taxon_ref_id": "ref:birds:d2",
                "source_rank": 2,
            },
            {
                "status": "candidate",
                "target_canonical_taxon_id": target_id,
                "candidate_taxon_ref_type": "referenced_taxon",
                "candidate_taxon_ref_id": "ref:birds:d3",
                "source_rank": 3,
            },
            {
                "status": "candidate",
                "target_canonical_taxon_id": target_id,
                "candidate_taxon_ref_type": "canonical_taxon",
                "candidate_taxon_ref_id": safe_targets[idx % len(safe_targets)],
                "source_rank": 4,
            },
        ]
        if include_canonical_in_top3:
            base_candidates[1] = {
                "status": "candidate",
                "target_canonical_taxon_id": target_id,
                "candidate_taxon_ref_type": "canonical_taxon",
                "candidate_taxon_ref_id": safe_targets[idx % len(safe_targets)],
                "source_rank": 2,
            }
        projected_records.extend(base_candidates)

    distractor_payload = {"projected_records": projected_records}
    return plan_payload, materialization_payload, distractor_payload


def _patch_fake_load_json(monkeypatch: pytest.MonkeyPatch, include_canonical_in_top3: bool = False) -> None:
    from scripts import materialize_golden_pack_belgian_birds_mvp_v1 as mod

    plan_payload, materialization_payload, distractor_payload = _build_fake_materializer_inputs(
        include_canonical_in_top3=include_canonical_in_top3
    )
    qualified_export_payload = {
        "qualified_resources": [
            {
                "provenance": {
                    "source": {
                        "source_media_id": f"{idx}",
                        "raw_payload_ref": f"responses/taxon_birds_{idx:06d}.json#/results/0",
                        "media_license": "cc-by",
                    }
                }
            }
            for idx in range(1, 31)
        ]
    }
    inat_manifest_payload = {
        "media_downloads": [
            {
                "source_media_id": f"{idx}",
                "image_path": "images/fake.jpg",
                "source_url": f"https://example.org/media/{idx}.jpg",
            }
            for idx in range(1, 31)
        ]
    }
    ai_outputs_payload = {
        f"inaturalist::{idx}": {
            "pedagogical_media_profile": {
                "review_status": "valid",
                "evidence_type": "whole_organism",
                "scores": {
                    "global_quality_score": 90,
                    "usage_scores": {
                        "basic_identification": 90,
                        "field_observation": 90,
                        "confusion_learning": 90,
                        "morphology_learning": 90,
                        "species_card": 90,
                        "indirect_evidence_learning": 90,
                    },
                },
            }
        }
        for idx in range(1, 31)
    }

    def fake_load(path: Path):
        if path == mod.PLAN_PATH:
            return plan_payload
        if path == mod.MATERIALIZATION_SOURCE_PATH:
            return materialization_payload
        if path == mod.DISTRACTOR_PATH:
            return distractor_payload
        if path == mod.QUALIFIED_EXPORT_PATH:
            return qualified_export_payload
        if path == mod.INAT_MANIFEST_PATH:
            return inat_manifest_payload
        if path == mod.INAT_AI_OUTPUTS_PATH:
            return ai_outputs_payload
        raise AssertionError(f"Unexpected load path: {path}")

    monkeypatch.setattr(mod, "_load_json", fake_load)
    monkeypatch.setattr(mod, "_find_media_choice", lambda *_args, **_kwargs: mod.MediaChoice(
        source_media_id="1",
        source_url="https://example.org/media/1.jpg",
        image_rel_path="images/fake.jpg",
        image_abs_path=Path(__file__),
        source_name="inaturalist",
        creator="unit-test",
        license_name="cc-by",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        attribution_text="unit-test attribution",
    ))
    monkeypatch.setattr(mod, "OUTPUT_MEDIA_DIR", Path("/tmp/inaturaquizz-test-media"))
    monkeypatch.setattr(mod, "OUTPUT_DIR", Path("/tmp/inaturaquizz-test-pack"))
    monkeypatch.setattr(
        mod.shutil,
        "copy2",
        lambda _src, dst: Path(dst).write_bytes(b"unit-test-image"),
    )
    monkeypatch.setattr(mod, "_sha256_file", lambda _path: "a" * 64)


def test_referenced_taxon_label_safe_distractors_are_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fake_load_json(monkeypatch)
    payload = build_golden_pack()

    assert payload["schema_version"] == "golden_pack.v1"
    assert len(payload["questions"]) == 30
    for question in payload["questions"]:
        distractors = [opt for opt in question["options"] if not opt["is_correct"]]
        assert len(distractors) == 3
        assert all(opt["taxon_ref"]["id"].startswith("ref:birds:") for opt in distractors)
        assert all(opt["referenced_only"] is True for opt in distractors)


def test_distractor_can_be_target_in_another_question(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fake_load_json(monkeypatch, include_canonical_in_top3=True)
    payload = build_golden_pack()

    targets = {
        next(opt["taxon_ref"]["id"] for opt in q["options"] if opt["is_correct"])
        for q in payload["questions"]
    }
    appears_as_distractor = any(
        (not opt["is_correct"]) and opt["taxon_ref"]["id"] in targets
        for question in payload["questions"]
        for opt in question["options"]
    )
    assert appears_as_distractor is True


def test_14c2_fails_when_plan_has_duplicate_safe_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import materialize_golden_pack_belgian_birds_mvp_v1 as mod

    original_load = mod._load_json

    def fake_load(path: Path):
        payload = original_load(path)
        if path == mod.PLAN_PATH:
            payload = dict(payload)
            payload["metrics"] = dict(payload.get("metrics") or {})
            payload["metrics"]["safe_ready_targets_from_plan"] = [
                "taxon:birds:000001",
                "taxon:birds:000001",
            ]
        return payload

    monkeypatch.setattr(mod, "_load_json", fake_load)
    with pytest.raises(ContractError, match="duplicates"):
        mod.build_golden_pack()


def test_architecture_guard_no_csv_patch_snapshot_safe_ready_logic() -> None:
    paths = [
        Path("scripts/synthesize_sprint14b_final_runtime_handoff_readiness.py"),
        Path("scripts/materialize_golden_pack_belgian_birds_mvp_v1.py"),
    ]
    forbidden = [
        "taxon_localized_name_source_attested_patches_sprint14.csv",
        "taxon_localized_name_multisource_review_queue_sprint14.csv",
        "canonical_taxa_patched.json",
        "referenced_taxa_patched.json",
        "database_snapshot",
    ]
    required_plan_ref = "localized_name_apply_plan_v1.json"

    for path in paths:
        content = path.read_text(encoding="utf-8")
        assert required_plan_ref in content
        for token in forbidden:
            assert token not in content
