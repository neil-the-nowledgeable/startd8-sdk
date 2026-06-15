"""M1 unit tests for server.py — network-free coverage of the risky live-server logic.

Covers free-port, the tristate probe (against a stdlib http.server, no uvicorn/fastapi needed),
bind-error classification (CRP R1-S8), and — the FR-13 risk — process-group teardown.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from startd8.deploy_harness import LiveServer, free_port
from startd8.deploy_harness.server import _is_bind_error, _probe

pytestmark = pytest.mark.unit


def test_free_port_is_loopback_bindable() -> None:
    port = free_port()
    assert 1024 < port < 65536
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))  # must be immediately bindable


def test_is_bind_error_matches_known_signatures() -> None:
    assert _is_bind_error("ERROR: [Errno 48] Address already in use")
    assert _is_bind_error("error while attempting to bind on address")
    assert not _is_bind_error("ImportError: no module named app")
    assert not _is_bind_error("")


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_a) -> None:  # silence
        pass


def test_probe_tristate_ok_http_down() -> None:
    port = free_port()
    srv = HTTPServer(("127.0.0.1", port), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{port}"
        # poll briefly until the thread server is accepting
        deadline = time.monotonic() + 5
        while _probe(base + "/health") == "down" and time.monotonic() < deadline:
            time.sleep(0.05)
        assert _probe(base + "/health") == "ok"
        assert _probe(base + "/missing") == "http"  # connected, 404
    finally:
        srv.shutdown()
    # after shutdown the port is no longer served
    assert _probe(f"http://127.0.0.1:{port}/health") == "down"


def test_reap_kills_process_group(tmp_path) -> None:
    """A spawned session leader (and its sleep) must be fully reaped on teardown (FR-13)."""
    srv = LiveServer(python=sys.executable, target="x:y", app_root=tmp_path)
    # bypass boot: directly attach a long-lived process-group leader
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        start_new_session=True,
    )
    srv._proc = proc
    assert proc.poll() is None
    srv._reap()
    assert proc.poll() is not None  # terminated, not orphaned
