from __future__ import annotations

import argparse
import json
import os
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlsplit

from database_core.editorial_write.service import (
    EditorialWriteOwnerService,
    build_editorial_write_owner_service,
)
from database_core.pipeline.runner import DEFAULT_DATABASE_URL

SERVICE_NAME = "database-editorial-write-owner"
SERVICE_VERSION = os.environ.get("DATABASE_EDITORIAL_WRITE_SERVICE_VERSION", "v1")
OWNER_SERVICE_TOKEN_ENV = "OWNER_SERVICE_TOKEN"
OWNER_SERVICE_TOKEN_HEADER = "X-Owner-Service-Token"


class EditorialWriteRequestHandler(BaseHTTPRequestHandler):
    server: EditorialWriteHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        self._request_started_at = time.perf_counter()
        if not self._authorize_owner_request():
            return
        parsed = urlsplit(self.path)
        path = parsed.path

        if path == "/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": SERVICE_NAME,
                    "service_version": SERVICE_VERSION,
                    "ready": True,
                    "operations": [
                        "create_pack",
                        "diagnose_pack",
                        "compile_pack",
                        "materialize_pack",
                        "enrichment_request_status",
                        "enqueue_enrichment",
                        "execute_enrichment",
                    ],
                },
            )
            return

        if path.startswith("/editorial/enrichment-requests/"):
            self._handle_read_enrichment_status(path)
            return

        self._send_error(HTTPStatus.NOT_FOUND, "not_found")

    def do_POST(self) -> None:  # noqa: N802
        self._request_started_at = time.perf_counter()
        if not self._authorize_owner_request():
            return
        parsed = urlsplit(self.path)
        path = parsed.path

        if path == "/editorial/packs":
            self._handle_create_pack()
            return

        if path.startswith("/editorial/packs/"):
            if path.endswith("/diagnose"):
                self._handle_diagnose_pack(path)
                return
            if path.endswith("/compile"):
                self._handle_compile_pack(path)
                return
            if path.endswith("/materialize"):
                self._handle_materialize_pack(path)
                return
            if path.endswith("/enrichment/enqueue"):
                self._handle_enqueue_enrichment(path)
                return

        if path.startswith("/editorial/enrichment-requests/") and path.endswith("/execute"):
            self._handle_execute_enrichment(path)
            return

        self._send_error(HTTPStatus.NOT_FOUND, "not_found")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _handle_create_pack(self) -> None:
        body = self._read_json_object_body(required=True)
        if body is None:
            return

        payload = body.get("payload")
        if not isinstance(payload, dict):
            self._send_error(HTTPStatus.BAD_REQUEST, "invalid_request")
            return

        try:
            response_payload = self.server.service.create_pack(payload=payload)
        except ValueError as exc:
            self._handle_value_error(exc)
            return
        except Exception:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error")
            return

        self._send_json(HTTPStatus.OK, response_payload)

    def _handle_diagnose_pack(self, path: str) -> None:
        pack_id = self._extract_pack_id(path, suffix="/diagnose")
        if pack_id is None:
            return

        body = self._read_json_object_body(required=False)
        if body is None:
            return

        revision = self._parse_optional_positive_int(body.get("revision"))
        if revision is None and body.get("revision") is not None:
            return

        try:
            payload = self.server.service.diagnose_pack(pack_id=pack_id, revision=revision)
        except ValueError as exc:
            self._handle_value_error(exc)
            return
        except Exception:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error")
            return

        self._send_json(HTTPStatus.OK, payload)

    def _handle_compile_pack(self, path: str) -> None:
        pack_id = self._extract_pack_id(path, suffix="/compile")
        if pack_id is None:
            return

        body = self._read_json_object_body(required=False)
        if body is None:
            return

        revision = self._parse_optional_positive_int(body.get("revision"))
        if revision is None and body.get("revision") is not None:
            return

        question_count = self._parse_optional_positive_int(
            body.get("question_count"),
        )
        if question_count is None and body.get("question_count") is not None:
            return

        try:
            payload = self.server.service.compile_pack(
                pack_id=pack_id,
                revision=revision,
                question_count=question_count or 20,
            )
        except ValueError as exc:
            self._handle_value_error(exc)
            return
        except Exception:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error")
            return

        self._send_json(HTTPStatus.OK, payload)

    def _handle_materialize_pack(self, path: str) -> None:
        pack_id = self._extract_pack_id(path, suffix="/materialize")
        if pack_id is None:
            return

        body = self._read_json_object_body(required=False)
        if body is None:
            return

        revision = self._parse_optional_positive_int(body.get("revision"))
        if revision is None and body.get("revision") is not None:
            return

        question_count = self._parse_optional_positive_int(
            body.get("question_count"),
        )
        if question_count is None and body.get("question_count") is not None:
            return

        purpose = body.get("purpose")
        if purpose is not None and purpose not in {"assignment", "daily_challenge"}:
            self._send_error(HTTPStatus.BAD_REQUEST, "invalid_request")
            return

        ttl_hours = self._parse_optional_positive_int(body.get("ttl_hours"))
        if ttl_hours is None and body.get("ttl_hours") is not None:
            return

        try:
            payload = self.server.service.materialize_pack(
                pack_id=pack_id,
                revision=revision,
                question_count=question_count or 20,
                purpose=str(purpose or "assignment"),
                ttl_hours=ttl_hours,
            )
        except ValueError as exc:
            self._handle_value_error(exc)
            return
        except Exception:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error")
            return

        self._send_json(HTTPStatus.OK, payload)

    def _handle_enqueue_enrichment(self, path: str) -> None:
        pack_id = self._extract_pack_id(path, suffix="/enrichment/enqueue")
        if pack_id is None:
            return

        body = self._read_json_object_body(required=False)
        if body is None:
            return

        revision = self._parse_optional_positive_int(body.get("revision"))
        if revision is None and body.get("revision") is not None:
            return

        question_count = self._parse_optional_positive_int(
            body.get("question_count"),
        )
        if question_count is None and body.get("question_count") is not None:
            return

        try:
            payload = self.server.service.enqueue_enrichment(
                pack_id=pack_id,
                revision=revision,
                question_count=question_count or 20,
            )
        except ValueError as exc:
            self._handle_value_error(exc)
            return
        except Exception:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error")
            return

        self._send_json(HTTPStatus.OK, payload)

    def _handle_read_enrichment_status(self, path: str) -> None:
        prefix = "/editorial/enrichment-requests/"
        if not path.startswith(prefix):
            self._send_error(HTTPStatus.NOT_FOUND, "not_found")
            return

        enrichment_request_id = unquote(path[len(prefix) :]).strip()
        if not enrichment_request_id or "/" in enrichment_request_id:
            self._send_error(HTTPStatus.NOT_FOUND, "not_found")
            return

        try:
            payload = self.server.service.get_enrichment_request_status(
                enrichment_request_id=enrichment_request_id
            )
        except ValueError as exc:
            self._handle_value_error(exc)
            return
        except Exception:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error")
            return

        self._send_json(HTTPStatus.OK, payload)

    def _handle_execute_enrichment(self, path: str) -> None:
        suffix = "/execute"
        prefix = "/editorial/enrichment-requests/"
        if not path.startswith(prefix) or not path.endswith(suffix):
            self._send_error(HTTPStatus.NOT_FOUND, "not_found")
            return

        enrichment_request_id = unquote(path[len(prefix) : -len(suffix)]).strip()
        if not enrichment_request_id or "/" in enrichment_request_id:
            self._send_error(HTTPStatus.NOT_FOUND, "not_found")
            return

        body = self._read_json_object_body(required=False)
        if body is None:
            return

        execution_status = body.get("execution_status")
        if execution_status is not None and not isinstance(execution_status, str):
            self._send_error(HTTPStatus.BAD_REQUEST, "invalid_request")
            return

        execution_context = body.get("execution_context")
        if execution_context is not None and not isinstance(execution_context, dict):
            self._send_error(HTTPStatus.BAD_REQUEST, "invalid_request")
            return

        error_info = body.get("error_info")
        if error_info is not None and not isinstance(error_info, str):
            self._send_error(HTTPStatus.BAD_REQUEST, "invalid_request")
            return

        trigger_recompile = body.get("trigger_recompile", False)
        if not isinstance(trigger_recompile, bool):
            self._send_error(HTTPStatus.BAD_REQUEST, "invalid_request")
            return

        try:
            payload = self.server.service.execute_enrichment(
                enrichment_request_id=enrichment_request_id,
                execution_status=execution_status or "success",
                execution_context=execution_context,
                error_info=error_info,
                trigger_recompile=trigger_recompile,
            )
        except ValueError as exc:
            self._handle_value_error(exc)
            return
        except Exception:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error")
            return

        self._send_json(HTTPStatus.OK, payload)

    def _read_json_object_body(self, *, required: bool) -> dict[str, object] | None:
        content_length_header = self.headers.get("content-length")
        if not content_length_header:
            if required:
                self._send_error(HTTPStatus.BAD_REQUEST, "invalid_request")
                return None
            return {}

        try:
            content_length = int(content_length_header)
        except ValueError:
            self._send_error(HTTPStatus.BAD_REQUEST, "invalid_request")
            return None

        if content_length <= 0:
            if required:
                self._send_error(HTTPStatus.BAD_REQUEST, "invalid_request")
                return None
            return {}

        raw = self.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send_error(HTTPStatus.BAD_REQUEST, "invalid_request")
            return None

        if not isinstance(payload, dict):
            self._send_error(HTTPStatus.BAD_REQUEST, "invalid_request")
            return None

        return payload

    def _extract_pack_id(self, path: str, *, suffix: str) -> str | None:
        prefix = "/editorial/packs/"
        if not path.startswith(prefix) or not path.endswith(suffix):
            self._send_error(HTTPStatus.NOT_FOUND, "not_found")
            return None

        pack_id = unquote(path[len(prefix) : -len(suffix)]).strip()
        if not pack_id or "/" in pack_id:
            self._send_error(HTTPStatus.NOT_FOUND, "not_found")
            return None

        return pack_id

    def _parse_optional_positive_int(self, value: object) -> int | None:
        if value is None:
            return None
        if not isinstance(value, int) or value <= 0:
            self._send_error(HTTPStatus.BAD_REQUEST, "invalid_request")
            return None
        return value

    def _handle_value_error(self, error: ValueError) -> None:
        message = str(error)
        if (
            "Unknown pack_id" in message
            or "Unknown enrichment_request_id" in message
        ):
            self._send_error(HTTPStatus.NOT_FOUND, "not_found")
            return

        if (
            "not compilable" in message
            or "No compiled build found" in message
            or "exceeds available compiled questions" in message
            or "Pack already exists" in message
        ):
            self._send_error(HTTPStatus.CONFLICT, "conflict")
            return

        self._send_error(HTTPStatus.BAD_REQUEST, "invalid_request")

    def _send_error(self, status: HTTPStatus, code: str) -> None:
        self._send_json(status, {"error": code})

    def _authorize_owner_request(self) -> bool:
        expected_token = os.environ.get(OWNER_SERVICE_TOKEN_ENV)
        if not expected_token:
            return True

        received_token = self.headers.get(OWNER_SERVICE_TOKEN_HEADER)
        if received_token != expected_token:
            self._send_error(HTTPStatus.UNAUTHORIZED, "unauthorized")
            return False
        return True

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload, ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)
        self._log_request(status=status, payload=payload)

    def _log_request(self, *, status: HTTPStatus, payload: dict[str, object]) -> None:
        started_at = getattr(self, "_request_started_at", None)
        if started_at is None:
            latency_ms = 0.0
        else:
            latency_ms = round((time.perf_counter() - started_at) * 1000.0, 3)

        error = payload.get("error") if isinstance(payload, dict) else None
        if int(status) >= 500:
            category = "server_error"
        elif int(status) >= 400:
            category = "client_error"
        else:
            category = "success"

        print(
            json.dumps(
                {
                    "service": SERVICE_NAME,
                    "service_version": SERVICE_VERSION,
                    "method": self.command,
                    "path": self.path,
                    "status": int(status),
                    "error": error,
                    "error_category": category,
                    "latency_ms": latency_ms,
                },
                ensure_ascii=True,
            )
        )


class EditorialWriteHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        service: EditorialWriteOwnerService,
    ) -> None:
        super().__init__(server_address, EditorialWriteRequestHandler)
        self.service = service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="database-editorial-write-owner",
        description=(
            "Minimal owner-side write service for editorial pack/enrichment operations."
        ),
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("DATABASE_EDITORIAL_WRITE_HOST", "127.0.0.1"),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("DATABASE_EDITORIAL_WRITE_PORT", "8082")),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    service = build_editorial_write_owner_service(args.database_url)
    server = EditorialWriteHTTPServer((args.host, args.port), service)
    print(
        json.dumps(
            {
                "status": "listening",
                "service": SERVICE_NAME,
                "service_version": SERVICE_VERSION,
                "host": args.host,
                "port": args.port,
                "ready": True,
                "operations": [
                    "create_pack",
                    "diagnose_pack",
                    "compile_pack",
                    "materialize_pack",
                    "enrichment_request_status",
                    "enqueue_enrichment",
                    "execute_enrichment",
                ],
            },
            ensure_ascii=True,
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
