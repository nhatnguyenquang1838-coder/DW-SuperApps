"""Loopback-only GET API for the semantic-qualification read projection.

No route exposes raw LangGraph checkpoints, raw receipt-store rows, or a write
operation. A host may wrap this service behind its own authenticated internal
transport, but this adapter intentionally binds only to loopback.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import re
from urllib.parse import unquote, urlsplit

from .qualification_projection import QualificationProjectionService

_ROUTE = re.compile(r"^/v1/runs/([^/]+)/qualification$")


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def create_read_only_qualification_server(
    service: QualificationProjectionService,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
) -> ThreadingHTTPServer:
    """Create a test/dev HTTP server on loopback with GET-only semantics."""
    if not _is_loopback_host(host):
        raise ValueError("qualification read API may bind only to localhost/loopback")

    class Handler(BaseHTTPRequestHandler):
        server_version = "DWOQualificationRead/1"
        sys_version = ""

        def log_message(self, format: str, *args) -> None:
            # Keep run identifiers and request data out of default stderr logs.
            return

        def _send_json(self, status: int, body: dict[str, object]) -> None:
            payload = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:
            parsed = urlsplit(self.path)
            match = _ROUTE.fullmatch(parsed.path)
            if match is None or parsed.query or parsed.fragment:
                self._send_json(404, {"error": "NOT_FOUND"})
                return
            run_id = unquote(match.group(1))
            if not run_id or "/" in run_id or "\\" in run_id:
                self._send_json(400, {"error": "INVALID_RUN_ID"})
                return
            try:
                result = service.read(run_id)
            except Exception:
                self._send_json(503, {"error": "QUALIFICATION_READ_UNAVAILABLE"})
                return
            self._send_json(200, result)

        def _method_not_allowed(self) -> None:
            self.send_response(405)
            self.send_header("Allow", "GET")
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def do_POST(self) -> None:
            self._method_not_allowed()

        def do_PUT(self) -> None:
            self._method_not_allowed()

        def do_PATCH(self) -> None:
            self._method_not_allowed()

        def do_DELETE(self) -> None:
            self._method_not_allowed()

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.allow_reuse_address = False
    return server
