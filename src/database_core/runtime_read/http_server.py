from __future__ import annotations

import argparse
import json
import os
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from database_core.pipeline.runner import DEFAULT_DATABASE_URL
from database_core.runtime_read.service import (
    RuntimeReadOwnerService,
    build_runtime_read_owner_service,
)

PLAYABLE_CORPUS_PATH = "/playable-corpus"
SERVICE_NAME = "database-runtime-read-owner"
SERVICE_VERSION = os.environ.get("DATABASE_RUNTIME_READ_SERVICE_VERSION", "v1")


class RuntimeReadRequestHandler(BaseHTTPRequestHandler):
    server: RuntimeReadHTTPServer

    def do_GET(self) -> None:  # noqa: N802
        self._request_started_at = time.perf_counter()
        parsed = urlsplit(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": SERVICE_NAME,
                    "service_version": SERVICE_VERSION,
                    "ready": True,
                    "limits": {
                        "default_playable_limit": self.server.service.default_playable_limit,
                    },
                    "surfaces": [
                        "playable_corpus.v1",
                        "pack.compiled.v1",
                        "pack.materialization.v1",
                    ],
                },
            )
            return

        if path == PLAYABLE_CORPUS_PATH:
            self._handle_playable_corpus(query)
            return

        if path.startswith("/packs/") and "/compiled" in path:
            self._handle_compiled_pack(path)
            return

        if path.startswith("/materializations/"):
            self._handle_materialization(path)
            return

        self._send_error(HTTPStatus.NOT_FOUND, "not_found")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        # Disable default text access logs; we emit JSON logs in _send_json.
        return

    def _handle_playable_corpus(self, query: dict[str, list[str]]) -> None:
        limit = None
        if "limit" in query:
            raw_limit = query["limit"][0]
            try:
                limit = int(raw_limit)
            except ValueError:
                self._send_error(HTTPStatus.BAD_REQUEST, "invalid_limit")
                return

        try:
            payload = self.server.service.read_playable_corpus(limit=limit)
        except ValueError:
            self._send_error(HTTPStatus.BAD_REQUEST, "invalid_limit")
            return
        except Exception:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error")
            return

        self._send_json(HTTPStatus.OK, payload)

    def _handle_compiled_pack(self, path: str) -> None:
        parts = [segment for segment in path.split("/") if segment]
        # /packs/{pack_id}/compiled
        # /packs/{pack_id}/compiled/{revision}
        if len(parts) not in (3, 4) or parts[0] != "packs" or parts[2] != "compiled":
            self._send_error(HTTPStatus.NOT_FOUND, "not_found")
            return

        pack_id = unquote(parts[1])
        revision = None
        if len(parts) == 4:
            try:
                revision = int(parts[3])
            except ValueError:
                self._send_error(HTTPStatus.BAD_REQUEST, "invalid_revision")
                return
            if revision <= 0:
                self._send_error(HTTPStatus.BAD_REQUEST, "invalid_revision")
                return

        try:
            payload = self.server.service.find_compiled_pack(pack_id=pack_id, revision=revision)
        except Exception:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error")
            return

        if payload is None:
            self._send_error(HTTPStatus.NOT_FOUND, "not_found")
            return

        self._send_json(HTTPStatus.OK, payload)

    def _handle_materialization(self, path: str) -> None:
        parts = [segment for segment in path.split("/") if segment]
        # /materializations/{materialization_id}
        if len(parts) != 2 or parts[0] != "materializations":
            self._send_error(HTTPStatus.NOT_FOUND, "not_found")
            return

        materialization_id = unquote(parts[1])

        try:
            payload = self.server.service.find_pack_materialization(
                materialization_id=materialization_id
            )
        except Exception:
            self._send_error(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error")
            return

        if payload is None:
            self._send_error(HTTPStatus.NOT_FOUND, "not_found")
            return

        self._send_json(HTTPStatus.OK, payload)

    def _send_error(self, status: HTTPStatus, code: str) -> None:
        self._send_json(status, {"error": code})

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


class RuntimeReadHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        service: RuntimeReadOwnerService,
    ) -> None:
        super().__init__(server_address, RuntimeReadRequestHandler)
        self.service = service


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="database-runtime-read-owner",
        description=(
            "Minimal owner-side read service for official runtime surfaces only "
            "(playable_corpus.v1, pack.compiled.v1, pack.materialization.v1)."
        ),
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
    )
    parser.add_argument("--host", default=os.environ.get("DATABASE_RUNTIME_READ_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("DATABASE_RUNTIME_READ_PORT", "8081")),
    )
    parser.add_argument(
        "--playable-limit",
        type=int,
        default=int(os.environ.get("DATABASE_RUNTIME_PLAYABLE_LIMIT", "1000")),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    service = build_runtime_read_owner_service(
        args.database_url,
        default_playable_limit=args.playable_limit,
    )
    server = RuntimeReadHTTPServer((args.host, args.port), service)
    print(
        json.dumps(
            {
                "status": "listening",
                "service": SERVICE_NAME,
                "service_version": SERVICE_VERSION,
                "host": args.host,
                "port": args.port,
                "ready": True,
                "limits": {
                    "default_playable_limit": args.playable_limit,
                },
                "surfaces": [
                    "playable_corpus.v1",
                    "pack.compiled.v1",
                    "pack.materialization.v1",
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
