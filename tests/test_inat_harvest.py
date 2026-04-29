import json
from pathlib import Path
from urllib.error import URLError

import pytest

from database_core.adapters.inaturalist_harvest import DownloadedPhoto, fetch_inat_snapshot
from database_core.adapters.inaturalist_snapshot import PilotTaxonSeed


def test_fetch_inat_snapshot_uses_safe_filters_and_votes_fallback(
    monkeypatch, tmp_path: Path
) -> None:
    requested_params: list[dict[str, str]] = []

    def fake_load_pilot_taxa(path):
        del path
        return [
            PilotTaxonSeed(
                canonical_taxon_id="taxon:birds:000014",
                accepted_scientific_name="Turdus merula",
                source_taxon_id="12716",
                common_names=["Common Blackbird"],
            )
        ]

    def fake_fetch_json(url, *, params, timeout_seconds):
        del url, timeout_seconds
        if not params:
            return {
                "results": [
                    {
                        "id": 12716,
                        "name": "Turdus merula",
                        "preferred_common_name": "Eurasian Blackbird",
                        "similar_taxa": [],
                    }
                ]
            }
        requested_params.append(dict(params))
        if params["order_by"] == "votes":
            raise URLError("votes unsupported in fake test")
        return {
            "results": [
                {
                    "id": 910001,
                    "quality_grade": "research",
                    "license_code": "cc-by",
                    "captive": None,
                    "photos": [
                        {
                            "id": 810001,
                            "license_code": "cc-by",
                            "original_url": "https://static.inaturalist.org/photos/810001/original.jpg",
                            "url": "https://static.inaturalist.org/photos/810001/square.jpg",
                        }
                    ],
                    "taxon": {"id": 12716, "ancestor_ids": [12716]},
                }
            ]
        }

    def fake_download_best_candidate(candidate_urls, *, timeout_seconds):
        del candidate_urls, timeout_seconds
        return DownloadedPhoto(
            source_url="https://static.inaturalist.org/photos/810001/original.jpg",
            variant="original",
            image_bytes=b"fake-jpeg",
            mime_type="image/jpeg",
            width=1600,
            height=1200,
        )

    monkeypatch.setattr(
        "database_core.adapters.inaturalist_harvest.load_pilot_taxa", fake_load_pilot_taxa
    )
    monkeypatch.setattr("database_core.adapters.inaturalist_harvest._fetch_json", fake_fetch_json)
    monkeypatch.setattr(
        "database_core.adapters.inaturalist_harvest._download_best_candidate",
        fake_download_best_candidate,
    )

    result = fetch_inat_snapshot(
        snapshot_id="harvest-smoke",
        snapshot_root=tmp_path,
        max_observations_per_taxon=1,
    )

    manifest_payload = json.loads(
        (result.snapshot_dir / "manifest.json").read_text(encoding="utf-8")
    )
    seed = manifest_payload["taxon_seeds"][0]
    assert requested_params[0]["license"] == "cc0,cc-by,cc-by-sa"
    assert requested_params[0]["photo_license"] == "cc0,cc-by,cc-by-sa"
    assert requested_params[0]["captive"] == "false"
    assert requested_params[0]["order_by"] == "votes"
    assert requested_params[1]["order_by"] == "observed_on"
    assert seed["requested_order_by"] == "votes"
    assert seed["effective_order_by"] == "observed_on"
    assert seed["fallback_applied"] is True
    assert seed["query_params"]["order_by"] == "observed_on"
    assert seed["taxon_payload_path"] == "taxa/taxon_birds_000014.json"


def test_fetch_inat_snapshot_applies_optional_geo_temporal_filters(
    monkeypatch, tmp_path: Path
) -> None:
    requested_params: list[dict[str, str]] = []

    def fake_load_pilot_taxa(path):
        del path
        return [
            PilotTaxonSeed(
                canonical_taxon_id="taxon:birds:000014",
                accepted_scientific_name="Turdus merula",
                source_taxon_id="12716",
                common_names=["Common Blackbird"],
            )
        ]

    def fake_fetch_json(url, *, params, timeout_seconds):
        del url, timeout_seconds
        if not params:
            return {
                "results": [
                    {
                        "id": 12716,
                        "name": "Turdus merula",
                        "preferred_common_name": "Eurasian Blackbird",
                        "similar_taxa": [],
                    }
                ]
            }
        requested_params.append(dict(params))
        return {
            "results": [
                {
                    "id": 910001,
                    "quality_grade": "research",
                    "license_code": "cc-by",
                    "captive": None,
                    "photos": [
                        {
                            "id": 810001,
                            "license_code": "cc-by",
                            "original_url": "https://static.inaturalist.org/photos/810001/original.jpg",
                            "url": "https://static.inaturalist.org/photos/810001/square.jpg",
                        }
                    ],
                    "taxon": {"id": 12716, "ancestor_ids": [12716]},
                }
            ]
        }

    def fake_download_best_candidate(candidate_urls, *, timeout_seconds):
        del candidate_urls, timeout_seconds
        return DownloadedPhoto(
            source_url="https://static.inaturalist.org/photos/810001/original.jpg",
            variant="original",
            image_bytes=b"fake-jpeg",
            mime_type="image/jpeg",
            width=1600,
            height=1200,
        )

    monkeypatch.setattr(
        "database_core.adapters.inaturalist_harvest.load_pilot_taxa", fake_load_pilot_taxa
    )
    monkeypatch.setattr("database_core.adapters.inaturalist_harvest._fetch_json", fake_fetch_json)
    monkeypatch.setattr(
        "database_core.adapters.inaturalist_harvest._download_best_candidate",
        fake_download_best_candidate,
    )

    result = fetch_inat_snapshot(
        snapshot_id="harvest-smoke-filters",
        snapshot_root=tmp_path,
        max_observations_per_taxon=1,
        bbox="2.50,49.45,6.40,51.60",
        place_id="80500",
        observed_from="2025-01-01",
        observed_to="2025-12-31",
    )

    manifest_payload = json.loads(
        (result.snapshot_dir / "manifest.json").read_text(encoding="utf-8")
    )
    seed = manifest_payload["taxon_seeds"][0]
    params = requested_params[0]
    assert params["swlng"] == "2.50"
    assert params["swlat"] == "49.45"
    assert params["nelng"] == "6.40"
    assert params["nelat"] == "51.60"
    assert params["place_id"] == "80500"
    assert params["d1"] == "2025-01-01"
    assert params["d2"] == "2025-12-31"
    assert seed["query_params"]["swlng"] == "2.50"
    assert seed["query_params"]["d2"] == "2025-12-31"


def test_fetch_inat_snapshot_country_code_be_maps_to_place_id(
    monkeypatch, tmp_path: Path
) -> None:
    requested_params: list[dict[str, str]] = []

    def fake_load_pilot_taxa(path):
        del path
        return [
            PilotTaxonSeed(
                canonical_taxon_id="taxon:birds:000014",
                accepted_scientific_name="Turdus merula",
                source_taxon_id="12716",
                common_names=["Common Blackbird"],
            )
        ]

    def fake_fetch_json(url, *, params, timeout_seconds):
        del url, timeout_seconds
        if not params:
            return {
                "results": [
                    {
                        "id": 12716,
                        "name": "Turdus merula",
                        "preferred_common_name": "Eurasian Blackbird",
                        "similar_taxa": [],
                    }
                ]
            }
        requested_params.append(dict(params))
        return {
            "results": [
                {
                    "id": 910001,
                    "quality_grade": "research",
                    "license_code": "cc-by",
                    "captive": None,
                    "photos": [
                        {
                            "id": 810001,
                            "license_code": "cc-by",
                            "original_url": "https://static.inaturalist.org/photos/810001/original.jpg",
                            "url": "https://static.inaturalist.org/photos/810001/square.jpg",
                        }
                    ],
                    "taxon": {"id": 12716, "ancestor_ids": [12716]},
                }
            ]
        }

    def fake_download_best_candidate(candidate_urls, *, timeout_seconds):
        del candidate_urls, timeout_seconds
        return DownloadedPhoto(
            source_url="https://static.inaturalist.org/photos/810001/original.jpg",
            variant="original",
            image_bytes=b"fake-jpeg",
            mime_type="image/jpeg",
            width=1600,
            height=1200,
        )

    monkeypatch.setattr(
        "database_core.adapters.inaturalist_harvest.load_pilot_taxa", fake_load_pilot_taxa
    )
    monkeypatch.setattr("database_core.adapters.inaturalist_harvest._fetch_json", fake_fetch_json)
    monkeypatch.setattr(
        "database_core.adapters.inaturalist_harvest._download_best_candidate",
        fake_download_best_candidate,
    )

    result = fetch_inat_snapshot(
        snapshot_id="harvest-smoke-country",
        snapshot_root=tmp_path,
        max_observations_per_taxon=1,
        country_code="be",
    )

    manifest_payload = json.loads(
        (result.snapshot_dir / "manifest.json").read_text(encoding="utf-8")
    )
    seed = manifest_payload["taxon_seeds"][0]
    params = requested_params[0]
    assert params["place_id"] == "7083"
    assert seed["query_params"]["place_id"] == "7083"
    assert seed["query_params"]["country_code"] == "BE"


def test_fetch_inat_snapshot_rejects_unsupported_country_code(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "database_core.adapters.inaturalist_harvest.load_pilot_taxa",
        lambda _path: [],
    )

    with pytest.raises(ValueError, match="Unsupported country_code filter"):
        fetch_inat_snapshot(
            snapshot_id="harvest-smoke-unsupported-country",
            snapshot_root=tmp_path,
            country_code="FR",
        )


def test_fetch_inat_snapshot_rejects_conflicting_country_and_place_id(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "database_core.adapters.inaturalist_harvest.load_pilot_taxa",
        lambda _path: [],
    )

    with pytest.raises(ValueError, match="Conflicting geo filters"):
        fetch_inat_snapshot(
            snapshot_id="harvest-smoke-conflict-country",
            snapshot_root=tmp_path,
            place_id="80500",
            country_code="BE",
        )
