import json
from pathlib import Path

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
                canonical_taxon_id="bird:turdus-merula",
                scientific_name="Turdus merula",
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
                        "similar_species": [],
                    }
                ]
            }
        requested_params.append(dict(params))
        if params["order_by"] == "votes":
            raise RuntimeError("votes unsupported in fake test")
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
    assert seed["taxon_payload_path"] == "taxa/bird_turdus_merula.json"
