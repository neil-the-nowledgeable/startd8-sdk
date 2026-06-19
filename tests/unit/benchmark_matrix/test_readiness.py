"""Unit tests for the shared readiness primitive (FR-11, REST lane).

Covers the tcp + http probes and the mode-keyed waiter against a real stdlib HTTP server — no
external deps, no network egress (loopback only).
"""
from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from startd8.benchmark_matrix.readiness import http_probe, tcp_probe, wait_ready


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        code = 200 if self.path == "/health" else 404
        self.send_response(code)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):  # silence
        pass


@pytest.fixture()
def http_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield port
    finally:
        srv.shutdown()


def _closed_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_tcp_probe(http_server):
    assert tcp_probe(http_server) is True
    assert tcp_probe(_closed_port()) is False


def test_http_probe_states(http_server):
    base = f"http://127.0.0.1:{http_server}"
    assert http_probe(base + "/health") == "ok"        # 2xx
    assert http_probe(base + "/nope") == "http"         # connected, non-2xx
    assert http_probe(f"http://127.0.0.1:{_closed_port()}/health") == "down"


def test_wait_ready_http_ok(http_server):
    assert wait_ready(http_server, 3.0, mode="http", health_path="/health") is None


def test_wait_ready_http_liveness_fallback(http_server):
    # No /health route → 404 ("http") still counts as ready (server is up and routing).
    assert wait_ready(http_server, 3.0, mode="http", health_path="/missing") is None


def test_wait_ready_tcp(http_server):
    assert wait_ready(http_server, 3.0, mode="tcp") is None


def test_wait_ready_timeout_on_dead_port():
    v = wait_ready(_closed_port(), 0.5, mode="http")
    assert v is not None and "never became ready" in v


def test_wait_ready_proc_exited_early():
    class _Dead:
        returncode = 1
        def poll(self):
            return 1
    v = wait_ready(_closed_port(), 5.0, _Dead(), mode="http")
    assert v is not None and "exited before readiness" in v
