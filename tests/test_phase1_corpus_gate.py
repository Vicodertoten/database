from __future__ import annotations

from pathlib import Path

from database_core.adapters.inaturalist_snapshot import (
    SnapshotMediaDownload,
    SnapshotTaxonSeed,
    _infer_country_code,
)
from database_core.ops.phase1_corpus_gate import (
    PHASE1_BUDGET_CAP_EUR,
    Phase1Candidate,
    assert_gemini_budget,
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
