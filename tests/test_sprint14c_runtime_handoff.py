from __future__ import annotations

from pathlib import Path

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


def test_14c2_fails_fast_when_30_contract_cannot_be_met() -> None:
    with pytest.raises(
        ContractError,
        match="Unable to select 30 deterministic targets with 3 label-safe distractors",
    ):
        build_golden_pack()


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
        Path("database/scripts/synthesize_sprint14b_final_runtime_handoff_readiness.py"),
        Path("database/scripts/materialize_golden_pack_belgian_birds_mvp_v1.py"),
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
