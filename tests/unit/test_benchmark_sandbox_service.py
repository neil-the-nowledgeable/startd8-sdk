"""M-T2.1 — behavioral sandbox primitive (run_service_sandboxed).

Hermetic: a tiny local socket server stands in for a generated service (no LLM, no external
network, loopback only). Validates the lifecycle the Track 2 plan requires — readiness detection,
the client window, GUARANTEED process-group teardown, and honest degradation on env failure.

Network isolation is disabled here (cfg.no_network=False) so these tests exercise pure process
lifecycle without depending on host seatbelt/netns availability; the loopback-vs-egress profile
itself is validated on the real benchmark host (M-T2.4).
"""
from __future__ import annotations

import socket
import sys

from startd8.benchmark_matrix.sandbox import (
    SandboxConfig,
    _port_ready,
    run_service_sandboxed,
)

# A loopback echo server: bind 127.0.0.1:<argv[1]>, reply "hello" to each connection, loop forever
# (so the harness — not the server — decides when it stops).
_SERVER_SRC = """
import socket, sys
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("127.0.0.1", int(sys.argv[1])))
s.listen()
while True:
    try:
        conn, _ = s.accept()
        conn.sendall(b"hello")
        conn.close()
    except OSError:
        break
"""

_NO_NET = SandboxConfig(no_network=False)  # skip seatbelt wrap → test pure lifecycle


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _connect_client(port: int) -> str:
    with socket.create_connection(("127.0.0.1", port), timeout=2.0) as c:
        return c.recv(16).decode()


def test_server_starts_client_runs_and_is_torn_down(tmp_path):
    port = _free_port()
    res = run_service_sandboxed(
        [sys.executable, "-c", _SERVER_SRC, str(port)],
        tmp_path, port, _connect_client, cfg=_NO_NET, readiness_timeout_s=8.0,
    )
    assert res.ready is True
    assert res.violation is None
    assert res.client_outcome == "hello"      # client talked to the live server
    assert not _port_ready(port)              # server fully torn down — no orphan holding the port


def test_never_ready_server_degrades(tmp_path):
    # A server that exits immediately must be recorded as a violation (degrade, FR-T2-2), not scored.
    port = _free_port()
    res = run_service_sandboxed(
        [sys.executable, "-c", "import sys; sys.exit(0)"],
        tmp_path, port, _connect_client, cfg=_NO_NET, readiness_timeout_s=5.0,
    )
    assert res.ready is False
    assert res.client_outcome is None
    assert res.violation is not None and ("exited" in res.violation or "never became ready" in res.violation)


def test_client_error_sets_violation_and_still_tears_down(tmp_path):
    port = _free_port()

    def _bad_client(_port: int):
        raise ValueError("boom")

    res = run_service_sandboxed(
        [sys.executable, "-c", _SERVER_SRC, str(port)],
        tmp_path, port, _bad_client, cfg=_NO_NET, readiness_timeout_s=8.0,
    )
    assert res.ready is True                   # server came up...
    assert res.violation is not None and res.violation.startswith("client error")  # ...but client failed
    assert not _port_ready(port)               # teardown still guaranteed after a client exception


def test_loopback_profile_allows_localhost_denies_egress():
    # FR-T2-SEC: the loopback wrap must permit 127.0.0.1 while marking egress denied (when a
    # mechanism exists). Structural check on the wrap, independent of host caps.
    from startd8.benchmark_matrix.sandbox import _wrap_loopback_only

    cmd, egress_denied, label = _wrap_loopback_only(["echo", "hi"], {"sandbox_exec": True, "unshare": False})
    assert egress_denied is True and label == "seatbelt-loopback"
    joined = " ".join(cmd)
    assert "localhost" in joined and "deny network*" in joined  # loopback re-allowed, remote denied
    # No mechanism available → honest best-effort, never a silent claim of isolation.
    cmd2, egress2, label2 = _wrap_loopback_only(["echo", "hi"], {"sandbox_exec": False, "unshare": False})
    assert egress2 is False and label2 == "none(best-effort)" and cmd2 == ["echo", "hi"]
