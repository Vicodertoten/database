from __future__ import annotations

import json

from database_core.ops.phase2b_audit import (
    build_name_repair_report,
    build_referenced_only_report,
    classify_locale_label,
    classify_pool_item_names,
    classify_referenced_taxon,
    load_localized_name_plan,
)


def test_fr_name_present_in_playable_but_pool_fallback_is_wrong_projection() -> None:
    pool_item = {
        "playable_item_id": "playable:1",
        "canonical_taxon_id": "taxon:birds:1",
        "scientific_name": "Columba palumbus",
        "labels": {
            "fr": "Columba palumbus",
            "en": "Common Wood Pigeon",
            "nl": "Houtduif",
        },
        "label_sources": {
            "fr": "scientific_name",
            "en": "common_name",
            "nl": "common_name",
        },
    }
    db_row = {
        "item_run_id": "run:phase1",
        "corpus_run_id": "run:phase1",
        "playable_scientific_name": "Columba palumbus",
        "playable_corpus_names_json": json.dumps(
            {"fr": ["Pigeon ramier"], "en": ["Common Wood Pigeon"], "nl": ["Houtduif"]}
        ),
        "playable_item_names_json": json.dumps(
            {"fr": ["Pigeon ramier"], "en": ["Common Wood Pigeon"], "nl": ["Houtduif"]}
        ),
        "canonical_common_names_json": json.dumps(["Common Wood Pigeon"]),
    }

    report = classify_pool_item_names(
        pool_item=pool_item,
        db_row=db_row,
        source_run_id="run:phase1",
        localized_evidence_names={},
    )

    fr_report = [item for item in report["locale_reports"] if item["locale"] == "fr"][0]
    assert "wrong_pool_projection" in fr_report["issues"]


def test_playable_item_name_absent_from_playable_corpus_is_stale_playable_item() -> None:
    issues = classify_locale_label(
        locale="nl",
        pool_label="Columba palumbus",
        pool_label_source="scientific_name",
        playable_names={"fr": [], "en": [], "nl": []},
        item_names={"fr": [], "en": [], "nl": ["Houtduif"]},
        localized_evidence_names={},
        canonical_common_names=[],
        scientific_name="Columba palumbus",
    )

    assert "stale_playable_item" in issues


def test_en_label_matching_fr_source_name_is_wrong_locale_mapping() -> None:
    issues = classify_locale_label(
        locale="en",
        pool_label="Pigeon ramier",
        pool_label_source="common_name",
        playable_names={
            "fr": ["Pigeon ramier"],
            "en": ["Common Wood Pigeon"],
            "nl": ["Houtduif"],
        },
        item_names={"fr": [], "en": [], "nl": []},
        localized_evidence_names={},
        canonical_common_names=["Common Wood Pigeon"],
        scientific_name="Columba palumbus",
    )

    assert "wrong_locale_mapping" in issues


def test_en_label_matching_fr_evidence_name_is_wrong_locale_mapping() -> None:
    issues = classify_locale_label(
        locale="en",
        pool_label="Pigeon ramier",
        pool_label_source="common_name",
        playable_names={"fr": [], "en": ["Pigeon ramier"], "nl": []},
        item_names={"fr": [], "en": ["Pigeon ramier"], "nl": []},
        localized_evidence_names={
            "fr": ["Pigeon ramier"],
            "en": ["Common Wood-Pigeon"],
            "nl": ["Houtduif"],
        },
        canonical_common_names=["Pigeon ramier"],
        scientific_name="Columba palumbus",
    )

    assert "wrong_locale_mapping" in issues


def test_name_repair_report_blocks_wrong_locale_mapping() -> None:
    report = build_name_repair_report(
        pool={"pool_id": "pack-pool:test", "source_run_id": "run:test"},
        item_reports=[
            {
                "playable_item_id": "playable:1",
                "canonical_taxon_id": "taxon:birds:1",
                "scientific_name": "Columba palumbus",
                "issues": ["wrong_locale_mapping"],
                "locale_reports": [
                    {
                        "locale": "fr",
                        "pool_label": "Columba palumbus",
                        "pool_label_source": "scientific_name",
                        "playable_corpus_names": [],
                        "playable_item_names": [],
                        "issues": [],
                    },
                    {
                        "locale": "en",
                        "pool_label": "Pigeon ramier",
                        "pool_label_source": "common_name",
                        "playable_corpus_names": ["Pigeon ramier"],
                        "playable_item_names": ["Pigeon ramier"],
                        "issues": ["wrong_locale_mapping"],
                    },
                    {
                        "locale": "nl",
                        "pool_label": "Columba palumbus",
                        "pool_label_source": "scientific_name",
                        "playable_corpus_names": [],
                        "playable_item_names": [],
                        "issues": [],
                    },
                ],
            }
        ],
    )

    assert report["decision"] == "BLOCKED_BY_UNKNOWN_SOURCE"


def test_localized_name_plan_names_make_missing_db_projection_stale(tmp_path) -> None:
    plan_path = tmp_path / "localized_name_apply_plan_v1.json"
    plan_path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "taxon_kind": "canonical_taxon",
                        "taxon_id": "taxon:birds:1",
                        "locale": "fr",
                        "chosen_value": "Pigeon ramier",
                        "evidence_refs": [{"value": "Palombe"}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    evidence_names = load_localized_name_plan(plan_path)

    issues = classify_locale_label(
        locale="fr",
        pool_label="Columba palumbus",
        pool_label_source="scientific_name",
        playable_names={"fr": [], "en": [], "nl": []},
        item_names={"fr": [], "en": [], "nl": []},
        localized_evidence_names=evidence_names["taxon:birds:1"],
        canonical_common_names=[],
        scientific_name="Columba palumbus",
    )

    assert "stale_playable_item" in issues


def test_name_repair_report_decision_ready_for_correction() -> None:
    report = build_name_repair_report(
        pool={"pool_id": "pack-pool:test", "source_run_id": "run:test"},
        item_reports=[
            {
                "playable_item_id": "playable:1",
                "canonical_taxon_id": "taxon:birds:1",
                "scientific_name": "Columba palumbus",
                "issues": ["wrong_pool_projection"],
                "locale_reports": [
                    {
                        "locale": "fr",
                        "pool_label": "Columba palumbus",
                        "pool_label_source": "scientific_name",
                        "playable_corpus_names": ["Pigeon ramier"],
                        "playable_item_names": ["Pigeon ramier"],
                        "issues": ["wrong_pool_projection"],
                    },
                    {
                        "locale": "en",
                        "pool_label": "Common Wood Pigeon",
                        "pool_label_source": "common_name",
                        "playable_corpus_names": ["Common Wood Pigeon"],
                        "playable_item_names": ["Common Wood Pigeon"],
                        "issues": [],
                    },
                    {
                        "locale": "nl",
                        "pool_label": "Houtduif",
                        "pool_label_source": "common_name",
                        "playable_corpus_names": ["Houtduif"],
                        "playable_item_names": ["Houtduif"],
                        "issues": [],
                    },
                ],
            }
        ],
    )

    assert report["decision"] == "READY_FOR_CORRECTION"
    assert report["metrics"]["locale_metrics"]["fr"]["pool_scientific_fallback_count"] == 1


def test_referenced_only_scientific_name_only_is_internal_not_public() -> None:
    item = classify_referenced_taxon(
        {
            "referenced_taxon_id": "reftaxon:inaturalist:1",
            "source": "inaturalist",
            "source_taxon_id": "1",
            "scientific_name": "Streptopelia decaocto",
            "preferred_common_name": None,
            "common_names_i18n_json": json.dumps({"fr": [], "en": [], "nl": []}),
            "mapping_status": "auto_referenced_high_confidence",
            "mapped_canonical_taxon_id": None,
            "reason_codes_json": json.dumps(["inat_similar_species"]),
        }
    )

    assert item["internal_eligible"] is True
    assert item["public_eligible_by_locale"] == {"fr": False, "en": False, "nl": False}


def test_referenced_only_with_locale_names_is_public_eligible_by_locale() -> None:
    item = classify_referenced_taxon(
        {
            "referenced_taxon_id": "reftaxon:inaturalist:2",
            "source": "inaturalist",
            "source_taxon_id": "2",
            "scientific_name": "Streptopelia decaocto",
            "preferred_common_name": "Eurasian Collared-Dove",
            "common_names_i18n_json": json.dumps(
                {
                    "fr": ["Tourterelle turque"],
                    "en": ["Eurasian Collared-Dove"],
                    "nl": ["Turkse tortel"],
                }
            ),
            "mapping_status": "auto_referenced_high_confidence",
            "mapped_canonical_taxon_id": None,
            "reason_codes_json": json.dumps(["inat_similar_species"]),
        }
    )

    assert item["internal_eligible"] is True
    assert item["public_eligible_by_locale"] == {"fr": True, "en": True, "nl": True}


def test_referenced_low_ambiguous_ignored_are_not_public_eligible() -> None:
    statuses = ["auto_referenced_low_confidence", "ambiguous", "ignored"]

    items = [
        classify_referenced_taxon(
            {
                "referenced_taxon_id": f"reftaxon:inaturalist:{status}",
                "source": "inaturalist",
                "source_taxon_id": status,
                "scientific_name": "Species test",
                "preferred_common_name": "Test",
                "common_names_i18n_json": json.dumps(
                    {"fr": ["Nom"], "en": ["Name"], "nl": ["Naam"]}
                ),
                "mapping_status": status,
                "mapped_canonical_taxon_id": None,
                "reason_codes_json": json.dumps(["inat_similar_species"]),
            }
        )
        for status in statuses
    ]

    assert all(not item["public_eligible_by_locale"]["fr"] for item in items)


def test_referenced_only_report_counts_public_eligibility() -> None:
    items = [
        classify_referenced_taxon(
            {
                "referenced_taxon_id": "reftaxon:inaturalist:1",
                "source": "inaturalist",
                "source_taxon_id": "1",
                "scientific_name": "Species one",
                "preferred_common_name": None,
                "common_names_i18n_json": json.dumps({"fr": ["Nom"], "en": [], "nl": []}),
                "mapping_status": "mapped",
                "mapped_canonical_taxon_id": "taxon:birds:1",
                "reason_codes_json": json.dumps(["inat_similar_species"]),
            }
        )
    ]

    report = build_referenced_only_report(items)

    assert report["decision"] == "READY_FOR_CORRECTION"
    assert report["metrics"]["internal_eligible_count"] == 1
    assert report["metrics"]["public_eligible_by_locale"] == {
        "fr": 1,
        "en": 0,
        "nl": 0,
    }
