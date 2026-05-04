from __future__ import annotations

import json
from pathlib import Path

from scripts.prepare_pmp_policy_broader_run import prepare_pmp_policy_broader_run


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_source_snapshot(root: Path, snapshot_id: str) -> None:
    snapshot_dir = root / snapshot_id
    for media_id in ("1001", "1002", "1003", "1004"):
        image_path = snapshot_dir / "images" / f"{media_id}.jpg"
        image_path.parent.mkdir(parents=True, exist_ok=True)
        image_path.write_bytes(b"fixture")

    _write_json(
        snapshot_dir / "responses" / "taxon_1.json",
        {
            "results": [
                {"id": 1, "photos": [{"id": 1001}]},
                {"id": 2, "photos": [{"id": 1002}]},
            ]
        },
    )
    _write_json(
        snapshot_dir / "responses" / "taxon_2.json",
        {
            "results": [
                {"id": 3, "photos": [{"id": 1003}]},
                {"id": 4, "photos": [{"id": 1004}]},
            ]
        },
    )
    _write_json(snapshot_dir / "taxa" / "taxon_birds_000001.json", {"id": 101})
    _write_json(snapshot_dir / "taxa" / "taxon_birds_000002.json", {"id": 102})
    _write_json(
        snapshot_dir / "manifest.json",
        {
            "snapshot_id": snapshot_id,
            "manifest_version": "inaturalist.snapshot.v3",
            "source_name": "inaturalist",
            "created_at": "2026-05-04T00:00:00Z",
            "taxon_seeds": [
                {
                    "canonical_taxon_id": "taxon:birds:000001",
                    "source_taxon_id": "101",
                    "accepted_scientific_name": "Taxon One",
                    "common_names": [],
                    "query_params": {},
                    "response_path": "responses/taxon_1.json",
                    "taxon_payload_path": "taxa/taxon_birds_000001.json",
                },
                {
                    "canonical_taxon_id": "taxon:birds:000002",
                    "source_taxon_id": "102",
                    "accepted_scientific_name": "Taxon Two",
                    "common_names": [],
                    "query_params": {},
                    "response_path": "responses/taxon_2.json",
                    "taxon_payload_path": "taxa/taxon_birds_000002.json",
                },
            ],
            "media_downloads": [
                {
                    "source_media_id": "1001",
                    "source_observation_id": "1",
                    "image_path": "images/1001.jpg",
                    "download_status": "downloaded",
                    "source_url": "https://example.test/1001.jpg",
                },
                {
                    "source_media_id": "1002",
                    "source_observation_id": "2",
                    "image_path": "images/1002.jpg",
                    "download_status": "downloaded",
                    "source_url": "https://example.test/1002.jpg",
                },
                {
                    "source_media_id": "1003",
                    "source_observation_id": "3",
                    "image_path": "images/1003.jpg",
                    "download_status": "downloaded",
                    "source_url": "https://example.test/1003.jpg",
                },
                {
                    "source_media_id": "1004",
                    "source_observation_id": "4",
                    "image_path": "images/1004.jpg",
                    "download_status": "downloaded",
                    "source_url": "https://example.test/1004.jpg",
                },
            ],
        },
    )


def test_prepare_pmp_policy_broader_run_builds_subset_and_returns_command(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "data/raw/inaturalist"
    _build_source_snapshot(snapshot_root, "source")

    audit, command = prepare_pmp_policy_broader_run(
        snapshot_id="source",
        output_snapshot_id="broader-subset",
        max_media_count=3,
        max_media_per_taxon=2,
        snapshot_root=snapshot_root,
        gemini_model="gemini-test-model",
        gemini_concurrency=2,
        gemini_api_key_env="TEST_GEMINI_KEY",
    )

    assert audit["source_snapshot_id"] == "source"
    assert audit["output_snapshot_id"] == "broader-subset"
    assert audit["selected_media_count"] == 3
    assert "qualify-inat-snapshot" in command
    assert "--snapshot-id broader-subset" in command
    assert "--gemini-model gemini-test-model" in command
    assert "--gemini-concurrency 2" in command
    assert "--gemini-api-key-env TEST_GEMINI_KEY" in command
    assert (snapshot_root / "broader-subset" / "manifest.json").exists()
    assert (snapshot_root / "broader-subset" / "subset_audit.json").exists()
