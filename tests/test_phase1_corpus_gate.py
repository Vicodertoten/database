from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from database_core.adapters import inaturalist_harvest
from database_core.adapters.inaturalist_harvest import (
    _fetch_seed_payload,
    _resolve_geo_country_filters,
)
from database_core.adapters.inaturalist_snapshot import (
    InaturalistSnapshotManifest,
    SnapshotMediaDownload,
    SnapshotTaxonSeed,
    _infer_country_code,
    write_snapshot_manifest,
)
from database_core.ops.phase1_corpus_gate import (
    PHASE1_BUDGET_CAP_EUR,
    Phase1Candidate,
    _collect_candidates,
    assert_gemini_budget,
    build_pre_ai_selection,
    evaluate_phase1_gate,
    has_resolved_locale_labels,
    resolve_locale_label,
    select_pre_ai_candidates,
)


def _candidate(
    *,
    taxon_id: str,
    media_id: str,
    source_url: str | None = None,
    sha256: str | None = None,
) -> Phase1Candidate:
    seed = SnapshotTaxonSeed(
        canonical_taxon_id=taxon_id,
        accepted_scientific_name=f"Species {taxon_id}",
        source_taxon_id=taxon_id.rsplit(":", 1)[-1],
        query_params={"country_code": "BE"},
        response_path=f"responses/{taxon_id}.json",
    )
    download = SnapshotMediaDownload(
        source_observation_id=f"obs-{media_id}",
        source_media_id=media_id,
        image_path=f"images/{media_id}.jpg",
        download_status="downloaded",
        source_url=source_url or f"https://example.test/{media_id}.jpg",
        sha256=sha256,
    )
    return Phase1Candidate(
        canonical_taxon_id=taxon_id,
        accepted_scientific_name=seed.accepted_scientific_name,
        source_snapshot_id="snapshot",
        source_snapshot_dir=Path("data/raw/inaturalist/snapshot"),
        response_path=seed.response_path,
        taxon_payload_path=None,
        country_code="BE",
        source_observation_id=f"obs-{media_id}",
        source_media_id=media_id,
        source_url=download.source_url,
        sha256=sha256,
        image_path=download.image_path,
        response_result={"id": f"obs-{media_id}", "photos": [{"id": media_id}]},
        media_download=download,
        taxon_seed=seed,
    )


def test_pre_ai_selection_deduplicates_by_media_url_and_hash() -> None:
    candidates = [
        _candidate(taxon_id="taxon:birds:000001", media_id="1", source_url="https://x/1.jpg"),
        _candidate(taxon_id="taxon:birds:000001", media_id="2", source_url="https://x/1.jpg"),
        _candidate(taxon_id="taxon:birds:000001", media_id="3", sha256="sha256:abc"),
        _candidate(taxon_id="taxon:birds:000001", media_id="4", sha256="sha256:abc"),
    ]

    result = select_pre_ai_candidates(
        candidates=candidates,
        existing_media_keys=set(),
        max_candidates_per_species=60,
    )

    assert [item.source_media_id for item in result.selected_candidates] == ["1", "3"]
    assert result.report["duplicate_or_blocked_reason_counts"] == {
        "duplicate_sha256": 1,
        "duplicate_source_url": 1,
    }


def test_pre_ai_selection_respects_max_candidates_per_taxon() -> None:
    candidates = [
        _candidate(taxon_id="taxon:birds:000001", media_id=str(index))
        for index in range(1, 5)
    ]

    result = select_pre_ai_candidates(
        candidates=candidates,
        existing_media_keys=set(),
        max_candidates_per_species=2,
    )

    assert [item.source_media_id for item in result.selected_candidates] == ["1", "2"]
    assert result.report["duplicate_or_blocked_reason_counts"] == {
        "per_taxon_candidate_cap": 2
    }


def test_pre_ai_selection_reports_existing_db_exclusions_separately() -> None:
    candidates = [
        _candidate(taxon_id="taxon:birds:000001", media_id="1", source_url="https://x/1.jpg"),
        _candidate(taxon_id="taxon:birds:000001", media_id="2", source_url="https://x/2.jpg"),
    ]

    result = select_pre_ai_candidates(
        candidates=candidates,
        existing_media_keys={("source_url", "https://x/1.jpg")},
        max_candidates_per_species=60,
    )

    assert [item.source_media_id for item in result.selected_candidates] == ["2"]
    assert result.report["duplicate_or_blocked_reason_counts"] == {
        "already_in_current_db": 1
    }
    assert result.report["already_in_current_db_by_country"] == {"BE": 1}
    assert result.report["already_in_current_db_by_taxon"] == {"taxon:birds:000001": 1}


def test_locale_resolution_falls_back_to_scientific_name() -> None:
    names = {"fr": ["Merle noir"], "en": [], "nl": []}

    assert resolve_locale_label(
        common_names_i18n=names,
        locale="fr",
        scientific_name="Turdus merula",
    ) == "Merle noir"
    assert resolve_locale_label(
        common_names_i18n=names,
        locale="nl",
        scientific_name="Turdus merula",
    ) == "Turdus merula"
    assert has_resolved_locale_labels(
        common_names_i18n=names,
        scientific_name="Turdus merula",
    )


def test_gemini_budget_blocks_when_estimate_exceeds_cap() -> None:
    budget = assert_gemini_budget(
        candidate_count=10_000,
        budget_cap_eur=PHASE1_BUDGET_CAP_EUR,
        estimated_cost_per_image_eur=0.002,
    )

    assert budget["estimated_cost_eur"] == 20.0
    assert budget["within_budget"] is False


def test_phase1_gate_requires_product_scoped_density_and_question_success() -> None:
    metrics = {
        "be_fr_exportable_playable_taxa": 50,
        "be_fr_exportable_playable_items": 1000,
        "taxa_with_at_least_20_images": 50,
        "taxa_with_zero_images": [],
        "locale_resolved_counts": {"fr": 1000, "en": 1000, "nl": 1000},
        "attribution_completeness": 1.0,
        "country_code_completeness": 1.0,
    }

    gate = evaluate_phase1_gate(metrics=metrics, question_generation_success_rate=0.5)

    assert gate["status"] == "NO_GO"
    assert gate["checks"]["question_generation_success_rate"]["pass"] is False


def test_inaturalist_snapshot_infers_france_from_place_id_6753() -> None:
    seed = SnapshotTaxonSeed(
        canonical_taxon_id="taxon:birds:000001",
        accepted_scientific_name="Columba palumbus",
        source_taxon_id="3048",
        query_params={"place_id": "6753"},
        response_path="responses/taxon_birds_000001.json",
    )

    assert _infer_country_code(result={}, seed=seed) == "FR"


def test_multi_country_filter_maps_to_be_fr_place_ids() -> None:
    country_code, place_id = _resolve_geo_country_filters(
        country_code="BE,FR",
        place_id=None,
    )

    assert country_code == "BE,FR"
    assert place_id == "7008,6753"


def test_multi_place_fetch_does_not_send_preferred_place_id(monkeypatch) -> None:
    captured_params: dict[str, str] = {}

    def fake_fetch_json(url: str, *, params: dict[str, str], timeout_seconds: int):
        del url, timeout_seconds
        captured_params.update(params)
        return {"results": []}

    monkeypatch.setattr(inaturalist_harvest, "_fetch_json", fake_fetch_json)

    _fetch_seed_payload(
        source_taxon_id="3048",
        max_observations_per_taxon=1,
        timeout_seconds=1,
        place_id="7008,6753",
    )

    assert captured_params["place_id"] == "7008,6753"
    assert "preferred_place_id" not in captured_params


def test_pre_ai_collect_candidates_infers_country_from_observation_place_ids(
    tmp_path: Path,
) -> None:
    snapshot_root = tmp_path / "snapshots"
    snapshot_dir = snapshot_root / "be-fr"
    (snapshot_dir / "responses").mkdir(parents=True)
    (snapshot_dir / "images").mkdir()
    image_path = snapshot_dir / "images" / "1001.jpg"
    image_path.write_bytes(b"image")
    response_path = Path("responses") / "taxon_birds_000001.json"
    (snapshot_dir / response_path).write_text(
        """
{
  "results": [
    {
      "id": 9001,
      "country_code": "",
      "place_ids": [6753],
      "photos": [{"id": 1001, "original_url": "https://example.test/1001.jpg"}]
    }
  ]
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    seed = SnapshotTaxonSeed(
        canonical_taxon_id="taxon:birds:000001",
        accepted_scientific_name="Columba palumbus",
        source_taxon_id="3048",
        query_params={"country_code": "BE,FR", "place_id": "7008,6753"},
        response_path=response_path.as_posix(),
    )
    write_snapshot_manifest(
        snapshot_dir,
        InaturalistSnapshotManifest(
            snapshot_id="be-fr",
            created_at=datetime.now(UTC),
            taxon_seeds=[seed],
            media_downloads=[
                SnapshotMediaDownload(
                    source_observation_id="9001",
                    source_media_id="1001",
                    image_path="images/1001.jpg",
                    download_status="downloaded",
                    source_url="https://example.test/1001.jpg",
                )
            ],
        ),
    )

    candidates = _collect_candidates(snapshot_ids=["be-fr"], snapshot_root=snapshot_root)

    assert len(candidates) == 1
    assert candidates[0].country_code == "FR"
    assert candidates[0].response_result["country_code"] == "FR"


def test_pre_ai_collect_candidates_excludes_missing_local_image(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "snapshots"
    snapshot_dir = snapshot_root / "be-fr"
    (snapshot_dir / "responses").mkdir(parents=True)
    response_path = Path("responses") / "taxon_birds_000001.json"
    (snapshot_dir / response_path).write_text(
        """
{
  "results": [
    {
      "id": 9001,
      "place_ids": [7008],
      "photos": [{"id": 1001, "original_url": "https://example.test/1001.jpg"}]
    }
  ]
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    seed = SnapshotTaxonSeed(
        canonical_taxon_id="taxon:birds:000001",
        accepted_scientific_name="Columba palumbus",
        source_taxon_id="3048",
        query_params={"country_code": "BE,FR", "place_id": "7008,6753"},
        response_path=response_path.as_posix(),
    )
    write_snapshot_manifest(
        snapshot_dir,
        InaturalistSnapshotManifest(
            snapshot_id="be-fr",
            created_at=datetime.now(UTC),
            taxon_seeds=[seed],
            media_downloads=[
                SnapshotMediaDownload(
                    source_observation_id="9001",
                    source_media_id="1001",
                    image_path="images/1001.jpg",
                    download_status="downloaded",
                    source_url="https://example.test/1001.jpg",
                )
            ],
        ),
    )

    candidates = _collect_candidates(snapshot_ids=["be-fr"], snapshot_root=snapshot_root)

    assert candidates == []


def test_build_pre_ai_selection_writes_worklist_and_final_input_snapshots(
    tmp_path: Path,
) -> None:
    snapshot_root = tmp_path / "snapshots"
    source_dir = snapshot_root / "raw"
    (source_dir / "responses").mkdir(parents=True)
    (source_dir / "images").mkdir()
    for media_id in ("1001", "1002"):
        (source_dir / "images" / f"{media_id}.jpg").write_bytes(f"image-{media_id}".encode())
    response_path = Path("responses") / "taxon_birds_000001.json"
    (source_dir / response_path).write_text(
        """
{
  "results": [
    {
      "id": 9001,
      "place_ids": [7008],
      "photos": [{"id": 1001, "original_url": "https://example.test/1001.jpg"}]
    },
    {
      "id": 9002,
      "place_ids": [6753],
      "photos": [{"id": 1002, "original_url": "https://example.test/1002.jpg"}]
    }
  ]
}
""".strip()
        + "\n",
        encoding="utf-8",
    )
    seed = SnapshotTaxonSeed(
        canonical_taxon_id="taxon:birds:000001",
        accepted_scientific_name="Columba palumbus",
        source_taxon_id="3048",
        query_params={"country_code": "BE,FR", "place_id": "7008,6753"},
        response_path=response_path.as_posix(),
    )
    write_snapshot_manifest(
        source_dir,
        InaturalistSnapshotManifest(
            snapshot_id="raw",
            created_at=datetime.now(UTC),
            taxon_seeds=[seed],
            media_downloads=[
                SnapshotMediaDownload(
                    source_observation_id="9001",
                    source_media_id="1001",
                    image_path="images/1001.jpg",
                    download_status="downloaded",
                    source_url="https://example.test/1001.jpg",
                    sha256="sha256:known",
                ),
                SnapshotMediaDownload(
                    source_observation_id="9002",
                    source_media_id="1002",
                    image_path="images/1002.jpg",
                    download_status="downloaded",
                    source_url="https://example.test/1002.jpg",
                    sha256="sha256:new",
                ),
            ],
        ),
    )

    result = build_pre_ai_selection(
        snapshot_ids=["raw"],
        output_snapshot_id="gemini-worklist",
        final_input_snapshot_id="final-input",
        output_dir=tmp_path / "evidence",
        snapshot_root=snapshot_root,
        current_database_url=None,
        max_candidates_per_species=60,
    )

    assert result.report["gemini_worklist_snapshot_id"] == "gemini-worklist"
    assert result.report["final_input_snapshot"]["snapshot_id"] == "final-input"
    assert result.report["final_input_snapshot"]["candidate_count"] == 2
    assert (snapshot_root / "gemini-worklist" / "images" / "1001.jpg").exists()
    assert (snapshot_root / "gemini-worklist" / "images" / "1002.jpg").exists()
    assert (snapshot_root / "final-input" / "images" / "1001.jpg").exists()
    assert (snapshot_root / "final-input" / "images" / "1002.jpg").exists()
