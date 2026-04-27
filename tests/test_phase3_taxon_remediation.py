from __future__ import annotations

import json
import shutil
from pathlib import Path

from database_core.ops.phase3_taxon_remediation import (
    build_remediation_selection,
    collect_known_source_ids,
    evaluate_preflight_gate,
    extract_min_media_missing_from_diagnostic,
    filter_snapshot_media_for_idempotence,
)

SNAPSHOT_FIXTURE_DIR = Path("tests/fixtures/inaturalist_snapshot_smoke")


def _copy_snapshot_fixture(snapshot_root: Path, snapshot_id: str) -> Path:
    destination = snapshot_root / snapshot_id
    shutil.copytree(SNAPSHOT_FIXTURE_DIR, destination)
    return destination


def test_build_remediation_selection_prioritizes_blocking_taxa_by_impact() -> None:
    diagnostic = {
        "reason_code": "insufficient_media_per_taxon",
        "deficits": [{"code": "min_media_per_taxon", "current": 0, "required": 2, "missing": 2}],
        "blocking_taxa": [
            {
                "canonical_taxon_id": "taxon:birds:000003",
                "media_count": 1,
                "missing_media_count": 1,
            },
            {
                "canonical_taxon_id": "taxon:birds:000001",
                "media_count": 0,
                "missing_media_count": 2,
            },
            {
                "canonical_taxon_id": "taxon:birds:000002",
                "media_count": 0,
                "missing_media_count": 2,
            },
        ],
    }

    selection = build_remediation_selection(diagnostic)

    assert selection.reason_code == "insufficient_media_per_taxon"
    assert selection.prioritized_taxon_ids == [
        "taxon:birds:000001",
        "taxon:birds:000002",
        "taxon:birds:000003",
    ]


def test_filter_snapshot_media_for_idempotence_applies_observation_and_media_guards(
    tmp_path: Path,
) -> None:
    snapshot_root = tmp_path / "raw"
    snapshot_id = "snapshot-idem"
    snapshot_dir = _copy_snapshot_fixture(snapshot_root, snapshot_id)
    manifest_path = snapshot_dir / "manifest.json"
    assert json.loads(manifest_path.read_text(encoding="utf-8"))

    known_observation_ids = {"910001"}
    known_media_ids = {"810002"}
    stats = filter_snapshot_media_for_idempotence(
        snapshot_id=snapshot_id,
        snapshot_root=snapshot_root,
        known_observation_ids=known_observation_ids,
        known_media_ids=known_media_ids,
    )

    updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    total_results = 0
    for response_path in [seed["response_path"] for seed in updated_manifest["taxon_seeds"]]:
        payload = json.loads((snapshot_dir / response_path).read_text(encoding="utf-8"))
        total_results += len(payload.get("results", []))

    assert stats == {
        "ignored_existing_observation": 1,
        "ignored_existing_media": 1,
        "accepted_new_observation_media": 1,
    }
    assert len(updated_manifest["media_downloads"]) == 1
    assert total_results == 1
    assert known_observation_ids == {"910001", "910003"}
    assert known_media_ids == {"810002", "810003"}


def test_filter_snapshot_media_for_idempotence_is_idempotent_on_second_snapshot(
    tmp_path: Path,
) -> None:
    snapshot_root = tmp_path / "raw"
    first_snapshot = _copy_snapshot_fixture(snapshot_root, "snapshot-first")
    _copy_snapshot_fixture(snapshot_root, "snapshot-second")
    assert first_snapshot.exists()

    known_observation_ids, known_media_ids = collect_known_source_ids(
        snapshot_root=snapshot_root,
        exclude_snapshot_ids={"snapshot-second"},
    )
    stats = filter_snapshot_media_for_idempotence(
        snapshot_id="snapshot-second",
        snapshot_root=snapshot_root,
        known_observation_ids=known_observation_ids,
        known_media_ids=known_media_ids,
    )

    assert stats["accepted_new_observation_media"] == 0
    assert stats["ignored_existing_observation"] == 3
    assert stats["ignored_existing_media"] == 0


def test_evaluate_preflight_gate_behaviors() -> None:
    go, expected_signal, reason = evaluate_preflight_gate(
        is_compilable_before=False,
        insufficient_media_before=2,
        accepted_new_observation_media_probe=5,
    )
    assert go is True
    assert expected_signal is True
    assert reason == "signal_positive"

    go, expected_signal, reason = evaluate_preflight_gate(
        is_compilable_before=False,
        insufficient_media_before=2,
        accepted_new_observation_media_probe=0,
    )
    assert go is False
    assert expected_signal is False
    assert reason == "signal_absent_on_blocking_taxa"

    go, expected_signal, reason = evaluate_preflight_gate(
        is_compilable_before=True,
        insufficient_media_before=2,
        accepted_new_observation_media_probe=10,
    )
    assert go is False
    assert expected_signal is False
    assert reason == "pack_already_compilable"


def test_extract_min_media_missing_from_diagnostic() -> None:
    diagnostic = {
        "deficits": [
            {"code": "min_taxa_served", "missing": 10},
            {"code": "min_media_per_taxon", "missing": 2},
        ]
    }
    assert extract_min_media_missing_from_diagnostic(diagnostic) == 2
    assert extract_min_media_missing_from_diagnostic({"deficits": []}) == 0
