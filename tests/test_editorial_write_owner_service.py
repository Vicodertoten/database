from __future__ import annotations

import json
import os
import threading
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from database_core.editorial_write.http_server import EditorialWriteHTTPServer
from database_core.editorial_write.service import build_editorial_write_owner_service
from tests.test_runtime_read_owner_service import _seed_owner_runtime_read_data


def _http_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    request = Request(url, method="GET", headers=headers or {})
    try:
        with urlopen(request) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
            return int(response.status), payload
    except HTTPError as error:
        payload = json.loads(error.read().decode("utf-8"))
        return int(error.code), payload


def _http_post_json(
    url: str,
    payload: dict[str, object] | list[object],
    *,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, object]]:
    merged_headers = {"content-type": "application/json", **(headers or {})}
    request = Request(
        url,
        method="POST",
        data=json.dumps(payload, ensure_ascii=True).encode("utf-8"),
        headers=merged_headers,
    )
    try:
        with urlopen(request) as response:  # noqa: S310
            body = json.loads(response.read().decode("utf-8"))
            return int(response.status), body
    except HTTPError as error:
        body = json.loads(error.read().decode("utf-8"))
        return int(error.code), body


def test_editorial_write_owner_service_operations(database_url: str) -> None:
    seeded = _seed_owner_runtime_read_data(database_url)
    service = build_editorial_write_owner_service(database_url)

    created = service.create_pack(
        payload={
            "pack_id": "pack:int019:create-service",
            "parameters": {
                "canonical_taxon_ids": ["taxon:int019:create"],
                "difficulty_policy": "balanced",
                "visibility": "private",
                "intended_use": "training",
            },
        }
    )
    assert created["operation_version"] == "pack.create.v1"
    assert created["payload"]["pack_spec_version"] == "pack.spec.v1"

    diagnosed = service.diagnose_pack(
        pack_id=str(seeded["pack_id"]),
        revision=int(seeded["revision"]),
    )
    assert diagnosed["operation_version"] == "pack.diagnose.v1"
    assert diagnosed["payload"]["pack_diagnostic_version"] == "pack.diagnostic.v1"

    try:
        service.compile_pack(
            pack_id="pack:int019:create-service",
            revision=1,
            question_count=20,
        )
    except ValueError as exc:
        assert "not compilable" in str(exc)
    else:
        raise AssertionError("compile_pack must fail on non compilable pack")

    materialized = service.materialize_pack(
        pack_id=str(seeded["pack_id"]),
        revision=int(seeded["revision"]),
        question_count=1,
        purpose="assignment",
    )
    assert materialized["operation_version"] == "pack.materialize.v1"
    assert materialized["payload"]["pack_materialization_version"] == "pack.materialization.v1"

    enqueue = service.enqueue_enrichment(
        pack_id="pack:int019:create-service",
        revision=1,
        question_count=20,
    )
    assert enqueue["operation_version"] == "enrichment.enqueue.v1"
    assert enqueue["payload"]["enqueued"] is True

    request_id = str(enqueue["payload"]["request"]["request"]["enrichment_request_id"])

    status = service.get_enrichment_request_status(enrichment_request_id=request_id)
    assert status["operation_version"] == "enrichment.request.status.v1"
    assert status["payload"]["enrichment_request_id"] == request_id

    executed = service.execute_enrichment(
        enrichment_request_id=request_id,
        execution_status="success",
        trigger_recompile=False,
    )
    assert executed["operation_version"] == "enrichment.execute.v1"
    assert executed["payload"]["enrichment_request_id"] == request_id


def test_editorial_write_owner_http_server_flow(database_url: str) -> None:
    seeded = _seed_owner_runtime_read_data(database_url)
    service = build_editorial_write_owner_service(database_url)

    server = EditorialWriteHTTPServer(("127.0.0.1", 0), service)
    host, port = server.server_address

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        status, health_payload = _http_get_json(f"http://{host}:{port}/health")
        assert status == 200
        assert health_payload["status"] == "ok"
        assert health_payload["service"] == "database-editorial-write-owner"
        assert health_payload["service_version"] == "v1"
        assert health_payload["ready"] is True

        status, invalid_create_payload = _http_post_json(
            f"http://{host}:{port}/editorial/packs",
            ["invalid"],
        )
        assert status == 400
        assert invalid_create_payload == {"error": "invalid_request"}

        status, create_payload = _http_post_json(
            f"http://{host}:{port}/editorial/packs",
            {
                "payload": {
                    "pack_id": "pack:int019:create-http",
                    "parameters": {
                        "canonical_taxon_ids": ["taxon:int019:http"],
                        "difficulty_policy": "balanced",
                        "visibility": "private",
                        "intended_use": "training",
                    },
                }
            },
        )
        assert status == 200
        assert create_payload["operation_version"] == "pack.create.v1"

        encoded_pack_id = quote(str(seeded["pack_id"]), safe="")

        status, diagnose_payload = _http_post_json(
            f"http://{host}:{port}/editorial/packs/{encoded_pack_id}/diagnose",
            {"revision": int(seeded["revision"])}
        )
        assert status == 200
        assert diagnose_payload["operation_version"] == "pack.diagnose.v1"

        status, invalid_diagnose_payload = _http_post_json(
            f"http://{host}:{port}/editorial/packs/{encoded_pack_id}/diagnose",
            {"revision": 0},
        )
        assert status == 400
        assert invalid_diagnose_payload == {"error": "invalid_request"}

        status, compile_conflict = _http_post_json(
            (
                f"http://{host}:{port}/editorial/packs/"
                f"{quote('pack:int019:create-http', safe='')}/compile"
            ),
            {"revision": 1, "question_count": 20},
        )
        assert status == 409
        assert compile_conflict == {"error": "conflict"}

        status, invalid_compile_payload = _http_post_json(
            (
                f"http://{host}:{port}/editorial/packs/"
                f"{quote('pack:int019:create-http', safe='')}/compile"
            ),
            {"question_count": 0},
        )
        assert status == 400
        assert invalid_compile_payload == {"error": "invalid_request"}

        status, materialize_payload = _http_post_json(
            f"http://{host}:{port}/editorial/packs/{encoded_pack_id}/materialize",
            {
                "revision": int(seeded["revision"]),
                "question_count": 1,
                "purpose": "assignment",
            },
        )
        assert status == 200
        assert materialize_payload["operation_version"] == "pack.materialize.v1"

        status, invalid_materialize_payload = _http_post_json(
            f"http://{host}:{port}/editorial/packs/{encoded_pack_id}/materialize",
            {"purpose": "invalid"},
        )
        assert status == 400
        assert invalid_materialize_payload == {"error": "invalid_request"}

        status, enqueue_payload = _http_post_json(
            (
                f"http://{host}:{port}/editorial/packs/"
                f"{quote('pack:int019:create-http', safe='')}/enrichment/enqueue"
            ),
            {"revision": 1, "question_count": 20},
        )
        assert status == 200
        assert enqueue_payload["operation_version"] == "enrichment.enqueue.v1"
        request_id = str(enqueue_payload["payload"]["request"]["request"]["enrichment_request_id"])

        status, invalid_enqueue_payload = _http_post_json(
            (
                f"http://{host}:{port}/editorial/packs/"
                f"{quote('pack:int019:create-http', safe='')}/enrichment/enqueue"
            ),
            {"question_count": -1},
        )
        assert status == 400
        assert invalid_enqueue_payload == {"error": "invalid_request"}

        status, enrichment_status_payload = _http_get_json(
            f"http://{host}:{port}/editorial/enrichment-requests/{quote(request_id, safe='')}"
        )
        assert status == 200
        assert enrichment_status_payload["operation_version"] == "enrichment.request.status.v1"

        status, execute_payload = _http_post_json(
            (
                f"http://{host}:{port}/editorial/enrichment-requests/"
                f"{quote(request_id, safe='')}/execute"
            ),
            {
                "execution_status": "success",
                "trigger_recompile": False,
                "execution_context": {"operator": "test"},
            },
        )
        assert status == 200
        assert execute_payload["operation_version"] == "enrichment.execute.v1"

        status, missing_status_payload = _http_get_json(
            f"http://{host}:{port}/editorial/enrichment-requests/{quote('enrreq:missing', safe='')}"
        )
        assert status == 404
        assert missing_status_payload == {"error": "not_found"}

        status, invalid_execute_payload = _http_post_json(
            (
                f"http://{host}:{port}/editorial/enrichment-requests/"
                f"{quote(request_id, safe='')}/execute"
            ),
            {"execution_status": "not-valid"},
        )
        assert status == 400
        assert invalid_execute_payload == {"error": "invalid_request"}

        status, invalid_execute_type_payload = _http_post_json(
            (
                f"http://{host}:{port}/editorial/enrichment-requests/"
                f"{quote(request_id, safe='')}/execute"
            ),
            {"trigger_recompile": "yes"},
        )
        assert status == 400
        assert invalid_execute_type_payload == {"error": "invalid_request"}
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_editorial_write_owner_http_server_optional_token_auth(database_url: str) -> None:
    seeded = _seed_owner_runtime_read_data(database_url)
    service = build_editorial_write_owner_service(database_url)
    previous_token = os.environ.get("OWNER_SERVICE_TOKEN")
    os.environ["OWNER_SERVICE_TOKEN"] = "owner-shared-token"

    server = EditorialWriteHTTPServer(("127.0.0.1", 0), service)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        status, unauthorized_health = _http_get_json(f"http://{host}:{port}/health")
        assert status == 401
        assert unauthorized_health == {"error": "unauthorized"}

        status, authorized_health = _http_get_json(
            f"http://{host}:{port}/health",
            headers={"X-Owner-Service-Token": "owner-shared-token"},
        )
        assert status == 200
        assert authorized_health["status"] == "ok"

        encoded_pack_id = quote(str(seeded["pack_id"]), safe="")
        status, diagnose_payload = _http_post_json(
            f"http://{host}:{port}/editorial/packs/{encoded_pack_id}/diagnose",
            {"revision": int(seeded["revision"])},
            headers={"X-Owner-Service-Token": "owner-shared-token"},
        )
        assert status == 200
        assert diagnose_payload["operation_version"] == "pack.diagnose.v1"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        if previous_token is None:
            del os.environ["OWNER_SERVICE_TOKEN"]
        else:
            os.environ["OWNER_SERVICE_TOKEN"] = previous_token
