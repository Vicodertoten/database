from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path

from database_core.qualification.ai import AIQualificationOutcome
from scripts import materialize_golden_pack_belgian_birds_mvp_v1 as materializer
from scripts import run_golden_pack_v1_clean_room_pipeline as clean_room


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_clean_room_seed_has_exact_minimal_50_taxa() -> None:
    seed = json.loads(clean_room.SEED_PATH.read_text(encoding="utf-8"))
    assert len(seed) == 50
    assert {key for row in seed for key in row} == {
        "accepted_scientific_name",
        "canonical_rank",
        "canonical_taxon_id",
        "common_names",
        "source_taxon_id",
    }
    assert len({row["canonical_taxon_id"] for row in seed}) == 50
    assert len({row["source_taxon_id"] for row in seed}) == 50


def test_clean_room_dry_run_and_skip_external(tmp_path: Path) -> None:
    dry_dir = clean_room.run_pipeline(mode="dry-run", output_root=tmp_path)
    assert (dry_dir / "run_manifest.json").exists()
    assert _load(dry_dir / "run_manifest.json")["status"] == "planned_only"
    dry_steps = {row["step"]: row for row in _load(dry_dir / "pipeline_plan.json")["steps"]}
    fetch_command = dry_steps["source_inat_refresh"]["next_command"]
    pmp_command = dry_steps["pmp_gemini"]["next_command"]
    materialization_command = dry_steps["materialization"]["next_command"]
    assert "--country-code BE" in fetch_command
    assert "--max-observations-per-taxon 20" in fetch_command
    assert "--ai-review-contract-version pedagogical_media_profile_v1" in pmp_command
    assert "--ai-review-contract-version pedagogical_media_profile_v1" in dry_steps["normalization"]["next_command"]
    assert "--selection-path" in materialization_command
    assert "--materialization-source-path" not in materialization_command
    assert not (dry_dir / "golden_pack" / "pack.json").exists()

    apply_dir = clean_room.run_pipeline(mode="apply", output_root=tmp_path, skip_external=True)
    manifest = _load(apply_dir / "run_manifest.json")
    steps = {row["step"]: row for row in _load(apply_dir / "pipeline_plan.json")["steps"]}
    assert manifest["status"] == "applied_with_skips"
    assert steps["seed_validation"]["status"] == "completed"
    assert steps["source_inat_refresh"]["status"] == "skipped"
    assert not (apply_dir / "golden_pack" / "pack.json").exists()


def test_clean_room_run_artifacts_redact_database_url(tmp_path: Path) -> None:
    database_url = "postgresql://postgres:secret-password@example.org:5432/postgres?sslmode=require"

    run_dir = clean_room.run_pipeline(
        mode="dry-run",
        output_root=tmp_path,
        database_url=database_url,
    )
    manifest_text = (run_dir / "run_manifest.json").read_text(encoding="utf-8")
    plan_text = (run_dir / "pipeline_plan.json").read_text(encoding="utf-8")

    assert "secret-password" not in manifest_text
    assert "secret-password" not in plan_text
    assert "postgres:***@example.org:5432" in manifest_text
    manifest = _load(run_dir / "run_manifest.json")
    assert manifest["normalization"]["database_host"] == "example.org"
    assert manifest["normalization"]["database_port"] == 5432


def test_clean_room_resume_can_reset_from_stage(tmp_path: Path) -> None:
    run_dir = clean_room.run_pipeline(mode="dry-run", output_root=tmp_path)
    plan_path = run_dir / "pipeline_plan.json"
    plan = _load(plan_path)
    for row in plan["steps"]:
        row["status"] = "completed"
        row["message"] = "old"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    clean_room.run_pipeline(
        mode="dry-run",
        output_root=tmp_path,
        resume_run_id=run_dir.name,
        reset_from_stage="normalization",
    )

    steps = {row["step"]: row for row in _load(plan_path)["steps"]}
    assert steps["pmp_gemini"]["status"] == "completed"
    assert steps["normalization"]["status"] == "planned"
    assert "message" not in steps["normalization"]
    assert steps["promotion_check"]["status"] == "planned"


def test_clean_room_blocks_gemini_without_explicit_allow_flag(tmp_path: Path, monkeypatch) -> None:
    def fake_run(cmd, cwd, check, capture_output, text):  # type: ignore[no-untyped-def]
        if cmd[1] == "scripts/fetch_inat_snapshot.py":
            snapshot_id = cmd[cmd.index("--snapshot-id") + 1]
            snapshot_root = Path(cmd[cmd.index("--snapshot-root") + 1])
            snapshot_dir = snapshot_root / snapshot_id
            (snapshot_dir / "responses").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "taxa").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "images").mkdir(parents=True, exist_ok=True)
            (snapshot_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "manifest_version": "inaturalist.snapshot.v3",
                        "snapshot_id": snapshot_id,
                        "created_at": "2026-05-06T00:00:00Z",
                        "taxon_seeds": [],
                        "media_downloads": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="fetch-ok", stderr="")
        if cmd[1] == "scripts/run_pipeline.py":
            for flag in ("--normalized-path", "--qualified-path", "--export-path"):
                out = Path(cmd[cmd.index(flag) + 1])
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text("{}\n", encoding="utf-8")
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="pipeline-ok", stderr="")
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(clean_room.subprocess, "run", fake_run)
    run_dir = clean_room.run_pipeline(mode="apply", output_root=tmp_path)

    steps = {row["step"]: row for row in _load(run_dir / "pipeline_plan.json")["steps"]}
    assert steps["source_inat_refresh"]["status"] == "completed"
    assert steps["pmp_gemini"]["status"] == "blocked"
    assert steps["pmp_gemini"]["message"] == "requires_allow_full_gemini_run"
    assert steps["normalization"]["status"] == "planned"


def _selection_fixture(tmp_path: Path) -> materializer.MaterializerConfig:
    snapshot_dir = tmp_path / "snapshot"
    (snapshot_dir / "images").mkdir(parents=True)
    entries = []
    ai_outputs = {}
    for idx in range(1, 31):
        media_id = str(idx)
        image_path = snapshot_dir / "images" / f"{media_id}.jpg"
        image_path.write_bytes(f"img-{idx}".encode("utf-8"))
        target_id = f"taxon:birds:{idx:06d}"
        entries.append(
            {
                "target_canonical_taxon_id": target_id,
                "target_label_fr": f"Nom FR {idx}",
                "primary_media": {
                    "source_media_id": media_id,
                    "image_path": f"images/{media_id}.jpg",
                    "source_url": f"https://example.org/media/{idx}.jpg",
                    "source": "inaturalist",
                    "creator": "unit-test",
                    "license": "cc-by",
                    "license_url": "https://creativecommons.org/licenses/by/4.0/",
                    "attribution_text": f"Photo {idx}",
                    "basic_identification_status": "eligible",
                    "basic_identification_score": 95,
                },
                "distractors": [
                    {
                        "taxon_ref": {"type": "referenced_taxon", "id": f"ref:birds:{idx:06d}_{didx}"},
                        "display_label": f"Distracteur {idx}-{didx}",
                        "referenced_only": True,
                        "provenance": {"source": "unit-test"},
                    }
                    for didx in range(1, 4)
                ],
            }
        )
        ai_outputs[f"inaturalist::{media_id}"] = {
            "pedagogical_media_profile": {
                "review_status": "valid",
                "evidence_type": "whole_organism",
                "scores": {"usage_scores": {"basic_identification": 95}},
            }
        }

    selection_path = tmp_path / "selection.json"
    selection_path.write_text(
        json.dumps(
            {
                "schema_version": "golden_pack_selection.v1",
                "target_candidates_considered": 50,
                "entries": entries,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    ai_path = snapshot_dir / "ai_outputs.json"
    ai_path.write_text(json.dumps(ai_outputs, indent=2) + "\n", encoding="utf-8")
    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text("{}\n", encoding="utf-8")
    return materializer.MaterializerConfig(
        plan_path=materializer.PLAN_PATH,
        materialization_source_path=materializer.MATERIALIZATION_SOURCE_PATH,
        distractor_path=materializer.DISTRACTOR_PATH,
        qualified_export_path=materializer.QUALIFIED_EXPORT_PATH,
        inat_manifest_path=manifest_path,
        inat_ai_outputs_path=ai_path,
        schema_pack_path=materializer.SCHEMA_PACK_PATH,
        schema_manifest_path=materializer.SCHEMA_MANIFEST_PATH,
        schema_validation_report_path=materializer.SCHEMA_VALIDATION_REPORT_PATH,
        output_dir=tmp_path / "out",
        selection_path=selection_path,
    )


def test_materializer_selection_path_writes_pack_without_legacy_source(tmp_path: Path) -> None:
    config = _selection_fixture(tmp_path)

    pack, manifest, report = materializer.write_outputs(config=config)

    assert report["status"] == "passed"
    assert report["schema_validity"]["pack_schema_valid"] is True
    assert len(pack["questions"]) == 30
    assert (config.output_dir / "pack.json").exists()
    assert manifest["checksums"]["pack.json"]["sha256"] == _sha256(config.output_pack_path)
    assert manifest["checksums"]["validation_report.json"]["sha256"] == _sha256(config.output_validation_report_path)
    assert manifest["scope"] == "golden_pack_v1_clean_room_selection"


def test_materializer_selection_path_rejects_ineligible_primary(tmp_path: Path) -> None:
    config = _selection_fixture(tmp_path)
    ai_outputs = _load(config.inat_ai_outputs_path)
    ai_outputs["inaturalist::1"]["pedagogical_media_profile"]["scores"]["usage_scores"]["basic_identification"] = 40
    config.inat_ai_outputs_path.write_text(json.dumps(ai_outputs, indent=2) + "\n", encoding="utf-8")

    try:
        materializer.write_outputs(config=config)
    except materializer.ContractError:
        pass

    report = _load(config.output_validation_report_path)
    assert report["status"] == "failed"
    assert any("primary_media_basic_identification_not_eligible" in " ".join(row["reason_codes"]) for row in report["rejected_targets"])


def _valid_pmp_profile() -> dict:
    return {
        "schema_version": "pedagogical_media_profile.v1",
        "review_status": "valid",
        "review_confidence": 0.91,
        "evidence_type": "whole_organism",
        "technical_profile": {"technical_quality": "high"},
        "observation_profile": {
            "visible_parts": ["head", "beak", "wing"],
            "view_angle": "lateral",
            "occlusion": "none",
        },
        "biological_profile_visible": {
            "sex": {"value": "unknown"},
            "life_stage": {"value": "adult"},
        },
        "identification_profile": {
            "diagnostic_feature_visibility": "high",
            "ambiguity_level": "low",
            "visible_field_marks": [{"feature": "beak"}],
        },
        "pedagogical_profile": {"learning_value": "high", "difficulty": "easy"},
        "scores": {"usage_scores": {"basic_identification": 95, "confusion_learning": 80}},
    }


def test_cached_pmp_v1_outcome_maps_to_ai_qualification() -> None:
    outcome = AIQualificationOutcome.from_snapshot_payload(
        {
            "status": "ok",
            "model_name": "gemini-test",
            "prompt_version": "pedagogical_media_profile_prompt.v1",
            "review_contract_version": "pedagogical_media_profile_v1",
            "pedagogical_media_profile": _valid_pmp_profile(),
        }
    )

    assert outcome.qualification is not None
    assert outcome.qualification.technical_quality == "high"
    assert outcome.qualification.visible_parts == ["head", "beak", "wing"]
    assert outcome.qualification.view_angle == "lateral"
    assert outcome.qualification.diagnostic_feature_visibility == "high"
    assert outcome.qualification.learning_suitability == "high"


def test_fr_labels_prefers_legacy_then_inat_fr(tmp_path: Path, monkeypatch) -> None:
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir()
    (snapshot_dir / "manifest.json").write_text(
        json.dumps(
            {
                "taxon_seeds": [
                    {
                        "canonical_taxon_id": "taxon:birds:000001",
                        "source_taxon_id": "1",
                    },
                    {
                        "canonical_taxon_id": "taxon:birds:000002",
                        "source_taxon_id": "2",
                    },
                    {
                        "canonical_taxon_id": "taxon:birds:000003",
                        "source_taxon_id": "3",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (snapshot_dir / "taxa").mkdir()
    (snapshot_dir / "taxa" / "target1.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "id": 1,
                        "preferred_common_name": "Bad preferred",
                        "names": [
                            {"name": "Merle noir", "locale": "fr", "lexicon": "French", "position": 3}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest["taxon_seeds"][0]["taxon_payload_path"] = "taxa/target1.json"
    (snapshot_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(
        clean_room,
        "_fetch_inat_taxon_fr_record",
        lambda source_taxon_id: {
            "id": int(source_taxon_id),
            "preferred_common_name": "Rougegorge familier" if source_taxon_id == "2" else "",
        },
    )

    payload = clean_room._build_fr_label_artifact(
        tmp_path,
        {"snapshot_dir": str(snapshot_dir)},
    )

    assert payload["target_labels"]["taxon:birds:000001"] == "Merle noir"
    assert payload["target_labels"]["taxon:birds:000002"] == "Rougegorge familier"
    assert "taxon:birds:000003" in payload["missing_target_labels"]


def test_label_from_taxon_record_uses_inat_all_names_french_locale() -> None:
    label = clean_room._label_from_taxon_record(
        {
            "preferred_common_name": "",
            "names": [
                {"name": "Common Blackbird", "locale": "en", "lexicon": "English"},
                {"name": "Merle noir", "locale": "fr", "lexicon": "French"},
            ],
        }
    )

    assert label == "Merle noir"


def test_label_overrides_support_curated_runtime_label(tmp_path: Path, monkeypatch) -> None:
    override_path = tmp_path / "overrides.json"
    override_path.write_text(
        json.dumps({"labels": {"taxon:birds:000021": {"fr": "Canard colvert"}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(clean_room, "LABEL_OVERRIDES_PATH", override_path)

    assert clean_room._label_overrides()["taxon:birds:000021"]["fr"] == "Canard colvert"


def test_label_from_taxon_record_prefers_valid_language_name_over_preferred_common_name() -> None:
    label = clean_room._label_from_taxon_record(
        {
            "preferred_common_name": "Bourre",
            "names": [
                {"name": "Mallard", "locale": "en", "lexicon": "English", "position": 0},
                {
                    "name": "Canard colvert",
                    "locale": "fr",
                    "lexicon": "French",
                    "is_valid": True,
                    "position": 19,
                },
            ],
        },
        language="fr",
    )

    assert label == "Canard colvert"


def test_label_from_taxon_record_falls_back_to_preferred_common_name_without_valid_language_name() -> None:
    label = clean_room._label_from_taxon_record(
        {
            "preferred_common_name": "Merle noir",
            "names": [
                {"name": "Common Blackbird", "locale": "en", "lexicon": "English"},
            ],
        },
        language="fr",
    )

    assert label == "Merle noir"


def test_available_common_names_groups_all_valid_languages() -> None:
    names = clean_room._available_common_names_by_language(
        {
            "names": [
                {"name": "Canard colvert", "locale": "fr", "is_valid": True, "position": 2},
                {"name": "Mallard", "locale": "en", "is_valid": True, "position": 1},
                {"name": "Wilde Eend", "locale": "nl", "is_valid": True, "position": 3},
                {"name": "Invalid", "locale": "fr", "is_valid": False, "position": 0},
            ]
        }
    )

    assert names["fr"] == ["Canard colvert"]
    assert names["en"] == ["Mallard"]
    assert names["nl"] == ["Wilde Eend"]


def test_localized_labels_from_snapshot_taxon_payload_collects_fr_en_nl() -> None:
    labels = clean_room._localized_labels_from_taxon_record(
        {
            "localized_taxa": {
                "fr": {"results": [{"preferred_common_name": "Merle noir"}]},
                "en": {"results": [{"preferred_common_name": "Common Blackbird"}]},
                "nl": {"results": [{"preferred_common_name": "Merel"}]},
            }
        }
    )

    assert labels == {
        "fr": "Merle noir",
        "en": "Common Blackbird",
        "nl": "Merel",
    }


def test_distractors_use_taxonomic_fallback_without_self_or_duplicate_labels(tmp_path: Path, monkeypatch) -> None:
    snapshot_dir = tmp_path / "snapshot"
    (snapshot_dir / "taxa").mkdir(parents=True)
    seeds = []
    labels = {}
    for idx, label in enumerate(("A", "B", "C", "D"), start=1):
        target_id = f"taxon:birds:{idx:06d}"
        seeds.append(
            {
                "canonical_taxon_id": target_id,
                "source_taxon_id": str(idx),
                "accepted_scientific_name": f"Genus species{idx}",
                "canonical_rank": "species",
                "taxon_payload_path": f"taxa/{idx}.json",
            }
        )
        labels[target_id] = label
        (snapshot_dir / "taxa" / f"{idx}.json").write_text(
            json.dumps(
                {
                    "results": [
                        {
                            "id": idx,
                            "name": f"Genus species{idx}",
                            "rank": "species",
                            "ancestors": [
                                {"rank": "order", "name": "Passeriformes"},
                                {"rank": "family", "name": "Family"},
                                {"rank": "genus", "name": "Genus"},
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
    (snapshot_dir / "manifest.json").write_text(json.dumps({"taxon_seeds": seeds}), encoding="utf-8")
    clean_room._write_json(
        tmp_path / "localized_names" / "fr_labels.json",
        {
            "target_labels": labels,
            "option_labels": labels,
            "fetched_inat_taxa_locale_fr": {},
        },
    )
    monkeypatch.setattr(clean_room, "_seed_rows", lambda: seeds)
    monkeypatch.setattr(clean_room, "_legacy_distractors", lambda: {})
    monkeypatch.setattr(
        clean_room,
        "_load_or_fetch_similar_species",
        lambda *args, **kwargs: {"status": "ok", "raw_payload": {"results": []}},
    )

    payload = clean_room._build_distractor_artifact(tmp_path, {"snapshot_dir": str(snapshot_dir)})
    projected = payload["projected_records"]
    target_rows = [row for row in projected if row["target_canonical_taxon_id"] == "taxon:birds:000001"]

    assert len(target_rows) == 3
    assert {row["source"] for row in target_rows} == {"taxonomic_neighbor_same_genus"}
    assert all(row["candidate_taxon_ref_id"] != "taxon:birds:000001" for row in target_rows)
    assert len({row["display_label"] for row in target_rows}) == 3


def test_distractors_fetch_external_inat_taxa_when_seed_neighbors_are_insufficient(
    tmp_path: Path,
    monkeypatch,
) -> None:
    snapshot_dir = tmp_path / "snapshot"
    (snapshot_dir / "taxa").mkdir(parents=True)
    seeds = [
        {
            "canonical_taxon_id": "taxon:birds:000001",
            "source_taxon_id": "1",
            "accepted_scientific_name": "Solo bird",
            "canonical_rank": "species",
            "taxon_payload_path": "taxa/1.json",
        }
    ]
    (snapshot_dir / "taxa" / "1.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "id": 1,
                        "name": "Solo bird",
                        "rank": "species",
                        "ancestors": [
                            {"id": 10, "rank": "order", "name": "Order"},
                            {"id": 11, "rank": "family", "name": "Family"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (snapshot_dir / "manifest.json").write_text(json.dumps({"taxon_seeds": seeds}), encoding="utf-8")
    clean_room._write_json(
        tmp_path / "localized_names" / "fr_labels.json",
        {
            "target_labels": {"taxon:birds:000001": "Oiseau cible"},
            "option_labels": {"taxon:birds:000001": "Oiseau cible"},
            "fetched_inat_taxa_locale_fr": {},
        },
    )
    monkeypatch.setattr(clean_room, "_seed_rows", lambda: seeds)
    monkeypatch.setattr(
        clean_room,
        "_load_or_fetch_similar_species",
        lambda *args, **kwargs: {"status": "ok", "raw_payload": {"results": []}},
    )
    monkeypatch.setattr(
        clean_room,
        "_fetch_inat_observed_taxa_for_parent",
        lambda parent_taxon_id: [
            {
                "id": 2,
                "preferred_common_name": "Espèce A",
                "names": [
                    {"name": "Species A", "locale": "en"},
                    {"name": "Soort A", "locale": "nl"},
                ],
            },
            {"id": 3, "preferred_common_name": "Espèce B"},
            {"id": 4, "preferred_common_name": "Espèce C"},
        ],
    )

    payload = clean_room._build_distractor_artifact(tmp_path, {"snapshot_dir": str(snapshot_dir)})
    target_rows = [
        row
        for row in payload["projected_records"]
        if row["target_canonical_taxon_id"] == "taxon:birds:000001"
    ]

    assert len(target_rows) == 3
    assert {row["source"] for row in target_rows} == {"inat_observed_same_family"}
    assert {row["display_label"] for row in target_rows} == {"Espèce A", "Espèce B", "Espèce C"}
    first = next(row for row in target_rows if row["display_label"] == "Espèce A")
    assert first["localized_labels"] == {
        "fr": "Espèce A",
        "en": "Species A",
        "nl": "Soort A",
    }


def test_fetch_inat_similar_species_uses_global_endpoint_without_place_filter(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def fake_fetch_json(url, *, params, timeout_seconds):
        del timeout_seconds
        calls.append((url, dict(params)))
        return {"results": []}

    monkeypatch.setattr("database_core.adapters.inaturalist_harvest._fetch_json", fake_fetch_json)

    payload = clean_room._fetch_inat_similar_species("12716")

    assert payload == {"results": []}
    assert calls == [
        (
            "https://api.inaturalist.org/v1/identifications/similar_species",
            {"taxon_id": "12716"},
        )
    ]


def test_distractors_prioritize_cached_global_inat_similar_species(
    tmp_path: Path,
    monkeypatch,
) -> None:
    snapshot_dir = tmp_path / "snapshot"
    (snapshot_dir / "taxa").mkdir(parents=True)
    seeds = [
        {
            "canonical_taxon_id": "taxon:birds:000001",
            "source_taxon_id": "1",
            "accepted_scientific_name": "Target bird",
            "canonical_rank": "species",
            "taxon_payload_path": "taxa/1.json",
        }
    ]
    (snapshot_dir / "taxa" / "1.json").write_text(
        json.dumps({"results": [{"id": 1, "name": "Target bird", "rank": "species"}]}),
        encoding="utf-8",
    )
    (snapshot_dir / "manifest.json").write_text(json.dumps({"taxon_seeds": seeds}), encoding="utf-8")
    clean_room._write_json(
        tmp_path / "localized_names" / "fr_labels.json",
        {
            "target_labels": {"taxon:birds:000001": "Oiseau cible"},
            "option_labels": {"taxon:birds:000001": "Oiseau cible"},
            "target_labels_by_language": {"fr": {"taxon:birds:000001": "Oiseau cible"}},
            "option_labels_by_language": {"fr": {"taxon:birds:000001": "Oiseau cible"}},
            "fetched_inat_taxa_locale_fr": {},
        },
    )
    monkeypatch.setattr(clean_room, "_seed_rows", lambda: seeds)
    monkeypatch.setattr(
        clean_room,
        "_fetch_inat_similar_species",
        lambda source_taxon_id, **kwargs: {
            "results": [
                {"taxon": {"id": 1, "name": "Target bird", "rank": "species"}, "count": 99},
                {"taxon": {"id": 2, "name": "Bird a", "rank": "species"}, "count": 8},
                {"taxon": {"id": 3, "name": "Bird b", "rank": "species"}, "count": 7},
                {"taxon": {"id": 4, "name": "Bird c", "rank": "species"}, "count": 6},
                {"taxon": {"id": 5, "name": "Genus only", "rank": "genus"}, "count": 5},
            ]
        },
    )
    monkeypatch.setattr(
        clean_room,
        "_fetch_localized_taxon_labels",
        lambda source_taxon_id: {
            "fr": f"Espèce {source_taxon_id}",
            "en": f"Species {source_taxon_id}",
            "nl": f"Soort {source_taxon_id}",
        },
    )
    monkeypatch.setattr(clean_room, "_fetch_inat_observed_taxa_for_parent", lambda parent: [])

    payload = clean_room._build_distractor_artifact(tmp_path, {"snapshot_dir": str(snapshot_dir)})
    target_rows = [
        row
        for row in payload["projected_records"]
        if row["target_canonical_taxon_id"] == "taxon:birds:000001"
    ]

    assert [row["candidate_taxon_ref_id"] for row in target_rows] == ["inat:2", "inat:3", "inat:4"]
    assert {row["source"] for row in target_rows} == {"inaturalist_similar_species"}
    assert all(row["candidate_taxon_ref_type"] == "referenced_taxon" for row in target_rows)
    assert (tmp_path / "distractors" / "similar_species_raw" / "taxon_birds_000001.json").exists()


def test_candidate_pool_builds_attribution_from_raw_inat_when_export_bundle_empty(tmp_path: Path, monkeypatch) -> None:
    snapshot_dir = tmp_path / "snapshot"
    (snapshot_dir / "responses").mkdir(parents=True)
    (snapshot_dir / "images").mkdir()
    (snapshot_dir / "responses" / "target.json").write_text(
        json.dumps(
            {
                "results": [
                    {
                        "id": 42,
                        "uri": "https://www.inaturalist.org/observations/42",
                        "license_code": "cc-by",
                        "user": {"login": "inat-user", "name": "Inat User"},
                        "photos": [
                            {
                                "id": 100,
                                "license_code": "cc-by",
                                "attribution": "© Inat User, some rights reserved",
                                "url": "https://example.org/photo.jpg",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    manifest = {
        "taxon_seeds": [
            {
                "canonical_taxon_id": "taxon:birds:000001",
                "response_path": "responses/target.json",
            }
        ],
        "media_downloads": [
            {
                "source_media_id": "100",
                "source_observation_id": "42",
                "source_url": "https://example.org/photo.jpg",
                "image_path": "images/100.jpg",
                "download_status": "downloaded",
            }
        ],
    }
    (snapshot_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (snapshot_dir / "ai_outputs.json").write_text(
        json.dumps(
            {
                "inaturalist::100": {
                    "status": "ok",
                    "pedagogical_media_profile": _valid_pmp_profile(),
                }
            }
        ),
        encoding="utf-8",
    )
    clean_room._write_json(
        tmp_path / "localized_names" / "fr_labels.json",
        {
            "target_labels": {"taxon:birds:000001": "Merle noir"},
            "option_labels": {
                "taxon:birds:000001": "Merle noir",
                "ref:1": "Pie bavarde",
                "ref:2": "Corneille noire",
                "ref:3": "Étourneau sansonnet",
            },
        },
    )
    clean_room._write_json(
        tmp_path / "distractors" / "distractors.json",
        {
            "projected_records": [
                {
                    "status": "candidate",
                    "target_canonical_taxon_id": "taxon:birds:000001",
                    "candidate_taxon_ref_type": "referenced_taxon",
                    "candidate_taxon_ref_id": f"ref:{idx}",
                    "display_label": label,
                    "source_rank": idx,
                }
                for idx, label in enumerate(("Pie bavarde", "Corneille noire", "Étourneau sansonnet"), start=1)
            ]
        },
    )
    (tmp_path / "qualified").mkdir()
    (tmp_path / "qualified" / "export_bundle.json").write_text(
        json.dumps({"qualified_resources": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        clean_room,
        "_seed_rows",
        lambda: [{"canonical_taxon_id": "taxon:birds:000001"}],
    )

    payload = clean_room._build_candidate_pool(
        tmp_path,
        {"snapshot_dir": str(snapshot_dir)},
        {"export_path": str(tmp_path / "qualified" / "export_bundle.json")},
        {"ai_outputs_path": str(snapshot_dir / "ai_outputs.json")},
    )

    row = payload["rows"][0]
    assert row["ready"] is True
    media = row["eligible_media"][0]
    assert media["attribution_complete"] is True
    assert media["creator"] == "Inat User"
    assert media["license"] == "cc-by"
    assert media["raw_payload_ref"] == "responses/target.json#/results/0/photos/0"
