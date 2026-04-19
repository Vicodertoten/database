from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen

from database_core.pack import validate_compiled_pack, validate_pack_materialization
from database_core.playable import validate_playable_corpus
from database_core.runtime_read.http_server import RuntimeReadHTTPServer
from database_core.runtime_read.service import build_runtime_read_owner_service
from database_core.storage.services import build_storage_services
from database_core.versioning import (
    ENRICHMENT_VERSION,
    EXPORT_VERSION,
    QUALIFICATION_VERSION,
    SCHEMA_VERSION_LABEL,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "runtime"


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _seed_owner_runtime_read_data(database_url: str) -> dict[str, object]:
    playable_fixture = _load_fixture("playable_corpus.sample.json")
    compiled_fixture = _load_fixture("pack_compiled.sample.json")
    materialization_fixture = _load_fixture("pack_materialization.sample.json")

    storage = build_storage_services(database_url)
    storage.database.initialize()

    first_playable = playable_fixture["items"][0]
    run_id = str(playable_fixture["run_id"])
    generated_at = datetime.fromisoformat(
        str(playable_fixture["generated_at"]).replace("Z", "+00:00")
    )

    with storage.database.connect() as connection:
        connection.execute(
            """
            INSERT INTO pipeline_runs (
                run_id,
                source_mode,
                dataset_id,
                snapshot_id,
                schema_version,
                qualification_version,
                enrichment_version,
                export_version,
                started_at,
                completed_at,
                run_status
            ) VALUES (%s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                "fixture",
                "fixture:runtime-read-owner",
                SCHEMA_VERSION_LABEL,
                QUALIFICATION_VERSION,
                ENRICHMENT_VERSION,
                EXPORT_VERSION,
                generated_at,
                generated_at,
                "completed",
            ),
        )

        source_observation_uid = str(
            first_playable.get(
                "source_observation_uid",
                f"{first_playable['source_name']}:{first_playable['source_observation_id']}",
            )
        )

        connection.execute(
            """
            INSERT INTO canonical_taxa (
                canonical_taxon_id,
                accepted_scientific_name,
                canonical_rank,
                taxon_group,
                taxon_status,
                authority_source,
                display_slug,
                synonyms_json,
                common_names_json,
                key_identification_features_json,
                source_enrichment_status,
                bird_scope_compatible,
                external_source_mappings_json,
                external_similarity_hints_json,
                similar_taxa_json,
                similar_taxon_ids_json,
                split_into_json,
                merged_into,
                replaced_by,
                derived_from,
                authority_taxonomy_profile_json
            ) VALUES (
                %s, %s, 'species', 'birds', 'active', 'fixture', %s, %s, %s, %s, 'ready', %s,
                %s, %s, %s, %s, %s, NULL, NULL, NULL, %s
            )
            """,
            (
                first_playable["canonical_taxon_id"],
                first_playable["scientific_name"],
                str(first_playable["scientific_name"]).lower().replace(" ", "-"),
                json.dumps([], ensure_ascii=True),
                json.dumps(first_playable["common_names_i18n"], ensure_ascii=True),
                json.dumps([], ensure_ascii=True),
                True,
                json.dumps([], ensure_ascii=True),
                json.dumps([], ensure_ascii=True),
                json.dumps([], ensure_ascii=True),
                json.dumps(first_playable["similar_taxon_ids"], ensure_ascii=True),
                json.dumps([], ensure_ascii=True),
                json.dumps({}, ensure_ascii=True),
            ),
        )

        connection.execute(
            """
            INSERT INTO source_observations (
                observation_uid,
                source_name,
                source_observation_id,
                source_taxon_id,
                observed_at,
                location_json,
                source_quality_json,
                raw_payload_ref,
                canonical_taxon_id,
                country_code,
                location_point,
                location_bbox,
                location_radius_meters
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, %s)
            """,
            (
                source_observation_uid,
                first_playable["source_name"],
                first_playable["source_observation_id"],
                f"taxon:{first_playable['canonical_taxon_id']}",
                (
                    datetime.fromisoformat(
                        str(first_playable["observed_at"]).replace("Z", "+00:00")
                    )
                    if first_playable["observed_at"]
                    else None
                ),
                json.dumps({}, ensure_ascii=True),
                json.dumps({}, ensure_ascii=True),
                "fixture:raw-observation",
                first_playable["canonical_taxon_id"],
                first_playable["country_code"],
                first_playable["location_radius_meters"],
            ),
        )

        connection.execute(
            """
            INSERT INTO media_assets (
                media_id,
                source_name,
                source_media_id,
                media_type,
                source_url,
                attribution,
                author,
                license,
                mime_type,
                file_extension,
                width,
                height,
                checksum,
                source_observation_uid,
                canonical_taxon_id,
                raw_payload_ref
            ) VALUES (
                %s, %s, %s, 'image', %s, 'fixture', NULL, NULL, NULL, NULL, NULL, NULL, NULL, %s,
                %s, %s
            )
            """,
            (
                first_playable["media_asset_id"],
                first_playable["source_name"],
                first_playable["source_media_id"],
                "https://example.org/fixture.jpg",
                source_observation_uid,
                first_playable["canonical_taxon_id"],
                "fixture:raw-media",
            ),
        )

        connection.execute(
            """
            INSERT INTO qualified_resources (
                qualified_resource_id,
                canonical_taxon_id,
                source_observation_uid,
                source_observation_id,
                media_asset_id,
                qualification_status,
                qualification_version,
                technical_quality,
                pedagogical_quality,
                life_stage,
                sex,
                visible_parts_json,
                view_angle,
                difficulty_level,
                media_role,
                confusion_relevance,
                diagnostic_feature_visibility,
                learning_suitability,
                uncertainty_reason,
                qualification_notes,
                qualification_flags_json,
                provenance_summary_json,
                license_safety_result,
                export_eligible,
                ai_confidence
            ) VALUES (
                %s, %s, %s, %s, %s, 'qualified', %s, 'good', 'good', 'unknown', 'unknown', %s,
                'unknown', %s, %s, %s, %s, %s, 'none', NULL, %s, %s, 'safe', %s, NULL
            )
            """,
            (
                first_playable["qualified_resource_id"],
                first_playable["canonical_taxon_id"],
                source_observation_uid,
                first_playable["source_observation_id"],
                first_playable["media_asset_id"],
                QUALIFICATION_VERSION,
                json.dumps([], ensure_ascii=True),
                first_playable["difficulty_level"],
                first_playable["media_role"],
                first_playable["confusion_relevance"],
                first_playable["diagnostic_feature_visibility"],
                first_playable["learning_suitability"],
                json.dumps([], ensure_ascii=True),
                json.dumps({}, ensure_ascii=True),
                True,
            ),
        )

        connection.execute(
            """
            INSERT INTO playable_items (
                playable_item_id,
                run_id,
                qualified_resource_id,
                canonical_taxon_id,
                media_asset_id,
                source_observation_uid,
                source_name,
                source_observation_id,
                source_media_id,
                scientific_name,
                common_names_i18n_json,
                difficulty_level,
                media_role,
                learning_suitability,
                confusion_relevance,
                diagnostic_feature_visibility,
                similar_taxon_ids_json,
                what_to_look_at_specific_json,
                what_to_look_at_general_json,
                confusion_hint,
                country_code,
                observed_at,
                location_point,
                location_bbox,
                location_radius_meters
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                NULL,
                NULL,
                %s
            )
            """,
            (
                first_playable["playable_item_id"],
                run_id,
                first_playable["qualified_resource_id"],
                first_playable["canonical_taxon_id"],
                first_playable["media_asset_id"],
                source_observation_uid,
                first_playable["source_name"],
                first_playable["source_observation_id"],
                first_playable["source_media_id"],
                first_playable["scientific_name"],
                json.dumps(first_playable["common_names_i18n"], ensure_ascii=True),
                first_playable["difficulty_level"],
                first_playable["media_role"],
                first_playable["learning_suitability"],
                first_playable["confusion_relevance"],
                first_playable["diagnostic_feature_visibility"],
                json.dumps(first_playable["similar_taxon_ids"], ensure_ascii=True),
                json.dumps(first_playable["what_to_look_at_specific"], ensure_ascii=True),
                json.dumps(first_playable["what_to_look_at_general"], ensure_ascii=True),
                first_playable["confusion_hint"],
                first_playable["country_code"],
                (
                    datetime.fromisoformat(
                        str(first_playable["observed_at"]).replace("Z", "+00:00")
                    )
                    if first_playable["observed_at"]
                    else None
                ),
                first_playable["location_radius_meters"],
            ),
        )

        connection.execute(
            """
            INSERT INTO playable_item_lifecycle (
                playable_item_id,
                qualified_resource_id,
                lifecycle_status,
                created_run_id,
                last_seen_run_id,
                invalidated_run_id,
                invalidation_reason,
                created_at,
                updated_at
            ) VALUES (%s, %s, 'active', %s, %s, NULL, NULL, %s, %s)
            """,
            (
                first_playable["playable_item_id"],
                first_playable["qualified_resource_id"],
                run_id,
                run_id,
                generated_at,
                generated_at,
            ),
        )

        pack_id = str(compiled_fixture["pack_id"])
        revision = int(compiled_fixture["revision"])
        built_at = datetime.fromisoformat(str(compiled_fixture["built_at"]).replace("Z", "+00:00"))
        next_revision = revision + 1
        next_built_at = built_at + timedelta(minutes=1)
        next_build_id = f"{compiled_fixture['build_id']}:next"

        connection.execute(
            """
            INSERT INTO pack_specs (pack_id, latest_revision, created_at, updated_at)
            VALUES (%s, %s, %s, %s)
            """,
            (pack_id, revision, built_at, built_at),
        )

        connection.execute(
            """
            INSERT INTO pack_revisions (
                pack_id,
                revision,
                canonical_taxon_ids_json,
                difficulty_policy,
                country_code,
                location_bbox,
                location_point,
                location_radius_meters,
                observed_from,
                observed_to,
                owner_id,
                org_id,
                visibility,
                intended_use,
                created_at
            ) VALUES (%s, %s, %s, %s, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, %s, %s, %s)
            """,
            (
                pack_id,
                revision,
                json.dumps([str(first_playable["canonical_taxon_id"])], ensure_ascii=True),
                "balanced",
                "private",
                "training",
                built_at,
            ),
        )

        connection.execute(
            """
            INSERT INTO pack_revisions (
                pack_id,
                revision,
                canonical_taxon_ids_json,
                difficulty_policy,
                country_code,
                location_bbox,
                location_point,
                location_radius_meters,
                observed_from,
                observed_to,
                owner_id,
                org_id,
                visibility,
                intended_use,
                created_at
            ) VALUES (%s, %s, %s, %s, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, %s, %s, %s)
            """,
            (
                pack_id,
                next_revision,
                json.dumps([str(first_playable["canonical_taxon_id"])], ensure_ascii=True),
                "balanced",
                "private",
                "training",
                next_built_at,
            ),
        )

        connection.execute(
            """
            INSERT INTO compiled_pack_builds (
                build_id,
                pack_id,
                revision,
                built_at,
                schema_version,
                pack_compiled_version,
                question_count_requested,
                question_count_built,
                distractor_count,
                source_run_id,
                payload_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                compiled_fixture["build_id"],
                pack_id,
                revision,
                built_at,
                compiled_fixture["schema_version"],
                compiled_fixture["pack_compiled_version"],
                compiled_fixture["question_count_requested"],
                compiled_fixture["question_count_built"],
                compiled_fixture["distractor_count"],
                run_id,
                json.dumps(compiled_fixture, ensure_ascii=True),
            ),
        )

        compiled_fixture_next = {
            **compiled_fixture,
            "build_id": next_build_id,
            "revision": next_revision,
            "built_at": next_built_at.isoformat().replace("+00:00", "Z"),
        }
        connection.execute(
            """
            INSERT INTO compiled_pack_builds (
                build_id,
                pack_id,
                revision,
                built_at,
                schema_version,
                pack_compiled_version,
                question_count_requested,
                question_count_built,
                distractor_count,
                source_run_id,
                payload_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                compiled_fixture_next["build_id"],
                pack_id,
                compiled_fixture_next["revision"],
                next_built_at,
                compiled_fixture_next["schema_version"],
                compiled_fixture_next["pack_compiled_version"],
                compiled_fixture_next["question_count_requested"],
                compiled_fixture_next["question_count_built"],
                compiled_fixture_next["distractor_count"],
                run_id,
                json.dumps(compiled_fixture_next, ensure_ascii=True),
            ),
        )

        created_at = datetime.fromisoformat(
            str(materialization_fixture["created_at"]).replace("Z", "+00:00")
        )
        expires_at = datetime.fromisoformat(
            str(materialization_fixture["expires_at"]).replace("Z", "+00:00")
        )

        connection.execute(
            """
            INSERT INTO pack_materializations (
                materialization_id,
                pack_id,
                revision,
                source_build_id,
                created_at,
                purpose,
                ttl_hours,
                expires_at,
                schema_version,
                pack_materialization_version,
                question_count,
                payload_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                materialization_fixture["materialization_id"],
                pack_id,
                revision,
                materialization_fixture["source_build_id"],
                created_at,
                materialization_fixture["purpose"],
                materialization_fixture["ttl_hours"],
                expires_at,
                materialization_fixture["schema_version"],
                materialization_fixture["pack_materialization_version"],
                materialization_fixture["question_count"],
                json.dumps(materialization_fixture, ensure_ascii=True),
            ),
        )

        materialization_fixture_next = {
            **materialization_fixture,
            "materialization_id": f"{materialization_fixture['materialization_id']}:next",
            "revision": next_revision,
            "source_build_id": next_build_id,
            "created_at": (created_at + timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
            "expires_at": (expires_at + timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        }
        connection.execute(
            """
            INSERT INTO pack_materializations (
                materialization_id,
                pack_id,
                revision,
                source_build_id,
                created_at,
                purpose,
                ttl_hours,
                expires_at,
                schema_version,
                pack_materialization_version,
                question_count,
                payload_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                materialization_fixture_next["materialization_id"],
                pack_id,
                next_revision,
                materialization_fixture_next["source_build_id"],
                created_at + timedelta(minutes=1),
                materialization_fixture_next["purpose"],
                materialization_fixture_next["ttl_hours"],
                expires_at + timedelta(minutes=1),
                materialization_fixture_next["schema_version"],
                materialization_fixture_next["pack_materialization_version"],
                materialization_fixture_next["question_count"],
                json.dumps(materialization_fixture_next, ensure_ascii=True),
            ),
        )

        connection.execute(
            "UPDATE pack_specs SET latest_revision = %s, updated_at = %s WHERE pack_id = %s",
            (next_revision, next_built_at, pack_id),
        )

    return {
        "pack_id": pack_id,
        "revision": revision,
        "next_revision": next_revision,
        "materialization_id": str(materialization_fixture["materialization_id"]),
        "next_materialization_id": f"{materialization_fixture['materialization_id']}:next",
    }


def _http_get_json(url: str) -> tuple[int, dict[str, object]]:
    try:
        with urlopen(url) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
            return int(response.status), payload
    except HTTPError as error:
        payload = json.loads(error.read().decode("utf-8"))
        return int(error.code), payload


def test_runtime_read_owner_service_reads_official_surfaces(database_url: str) -> None:
    seeded = _seed_owner_runtime_read_data(database_url)
    service = build_runtime_read_owner_service(database_url, default_playable_limit=200)

    playable_payload = service.read_playable_corpus()
    compiled_payload = service.find_compiled_pack(
        pack_id=str(seeded["pack_id"]),
        revision=int(seeded["revision"]),
    )
    latest_compiled_payload = service.find_compiled_pack(pack_id=str(seeded["pack_id"]))
    materialization_payload = service.find_pack_materialization(
        materialization_id=str(seeded["materialization_id"])
    )
    latest_materialization_payload = service.find_pack_materialization(
        materialization_id=str(seeded["next_materialization_id"])
    )

    assert playable_payload["playable_corpus_version"] == "playable_corpus.v1"
    validate_playable_corpus(playable_payload)

    assert compiled_payload is not None
    assert compiled_payload["pack_compiled_version"] == "pack.compiled.v1"
    validate_compiled_pack(compiled_payload)
    assert latest_compiled_payload is not None
    assert int(latest_compiled_payload["revision"]) == int(seeded["next_revision"])
    validate_compiled_pack(latest_compiled_payload)

    assert materialization_payload is not None
    assert materialization_payload["pack_materialization_version"] == "pack.materialization.v1"
    validate_pack_materialization(materialization_payload)
    assert latest_materialization_payload is not None
    assert int(latest_materialization_payload["revision"]) == int(seeded["next_revision"])
    validate_pack_materialization(latest_materialization_payload)

    assert service.find_compiled_pack(pack_id="pack:unknown") is None
    assert service.find_pack_materialization(materialization_id="packmat:unknown") is None


def test_runtime_read_owner_http_server_serves_runtime_surfaces(database_url: str) -> None:
    seeded = _seed_owner_runtime_read_data(database_url)
    service = build_runtime_read_owner_service(database_url, default_playable_limit=200)

    server = RuntimeReadHTTPServer(("127.0.0.1", 0), service)
    host, port = server.server_address

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        status, health_payload = _http_get_json(f"http://{host}:{port}/health")
        assert status == 200
        assert health_payload["status"] == "ok"
        assert health_payload["service"] == "database-runtime-read-owner"
        assert health_payload["service_version"] == "v1"
        assert health_payload["ready"] is True
        assert health_payload["limits"]["default_playable_limit"] == 200

        status, playable_payload = _http_get_json(f"http://{host}:{port}/playable-corpus")
        assert status == 200
        assert playable_payload["playable_corpus_version"] == "playable_corpus.v1"

        encoded_pack_id = quote(str(seeded["pack_id"]), safe="")
        status, compiled_payload = _http_get_json(
            f"http://{host}:{port}/packs/{encoded_pack_id}/compiled/{seeded['revision']}"
        )
        assert status == 200
        assert compiled_payload["pack_compiled_version"] == "pack.compiled.v1"
        assert int(compiled_payload["revision"]) == int(seeded["revision"])

        status, latest_compiled_payload = _http_get_json(
            f"http://{host}:{port}/packs/{encoded_pack_id}/compiled"
        )
        assert status == 200
        assert int(latest_compiled_payload["revision"]) == int(seeded["next_revision"])

        encoded_materialization_id = quote(str(seeded["materialization_id"]), safe="")
        status, materialization_payload = _http_get_json(
            f"http://{host}:{port}/materializations/{encoded_materialization_id}"
        )
        assert status == 200
        assert materialization_payload["pack_materialization_version"] == "pack.materialization.v1"

        status, invalid_limit_payload = _http_get_json(
            f"http://{host}:{port}/playable-corpus?limit=invalid"
        )
        assert status == 400
        assert invalid_limit_payload == {"error": "invalid_limit"}

        status, invalid_revision_payload = _http_get_json(
            f"http://{host}:{port}/packs/{encoded_pack_id}/compiled/not-a-number"
        )
        assert status == 400
        assert invalid_revision_payload == {"error": "invalid_revision"}

        status, invalid_revision_zero_payload = _http_get_json(
            f"http://{host}:{port}/packs/{encoded_pack_id}/compiled/0"
        )
        assert status == 400
        assert invalid_revision_zero_payload == {"error": "invalid_revision"}

        status, not_found_payload = _http_get_json(
            f"http://{host}:{port}/materializations/{quote('packmat:unknown', safe='')}"
        )
        assert status == 404
        assert not_found_payload == {"error": "not_found"}
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_runtime_read_owner_http_server_handles_internal_errors() -> None:
    class _FailingRuntimeReadService:
        def read_playable_corpus(self, *, limit: int | None = None) -> dict[str, object]:
            raise RuntimeError("boom")

        def find_compiled_pack(
            self,
            *,
            pack_id: str,
            revision: int | None = None,
        ) -> dict[str, object] | None:
            raise RuntimeError("boom")

        def find_pack_materialization(
            self,
            *,
            materialization_id: str,
        ) -> dict[str, object] | None:
            raise RuntimeError("boom")

    server = RuntimeReadHTTPServer(("127.0.0.1", 0), _FailingRuntimeReadService())  # type: ignore[arg-type]
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        status, playable_payload = _http_get_json(f"http://{host}:{port}/playable-corpus")
        assert status == 500
        assert playable_payload == {"error": "internal_error"}

        status, compiled_payload = _http_get_json(
            f"http://{host}:{port}/packs/{quote('pack:demo', safe='')}/compiled"
        )
        assert status == 500
        assert compiled_payload == {"error": "internal_error"}

        status, materialization_payload = _http_get_json(
            f"http://{host}:{port}/materializations/{quote('packmat:demo', safe='')}"
        )
        assert status == 500
        assert materialization_payload == {"error": "internal_error"}
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
