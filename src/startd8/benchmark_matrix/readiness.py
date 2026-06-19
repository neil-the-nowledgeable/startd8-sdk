"""Shared readiness probes for launched services (FR-11 — Track 2 REST/HTTP lane).

Single source of truth for "is the server ready to serve?", protocol-keyed so the behavioral lane can
host gRPC and HTTP services through one waiter. Stdlib-only — no HTTP-client dependency, and it never
imports the untrusted server. Two modes:

  - ``"tcp"``  — the port accepts a TCP connection (protocol-agnostic; the gRPC default).
  - ``"http"`` — the server answers an HTTP request on ``health_path``: ``2xx`` is app-health, any other
                 HTTP response is liveness (the server is up and routing) — either is enough for the
                 suite to run. This closes the gap that a port can be TCP-open before an HTTP framework
                 is actually accepting requests.

``http_probe`` mirrors ``deploy_harness/server.py``'s probe semantics (CRP R1-F10); that harness can
converge onto this module in a follow-up so the two never diverge.
"""
from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request
from typing import Optional


def tcp_probe(port: int, host: str = "127.0.0.1") -> bool:
    """True if something accepts a TCP connection on ``host:port`` right now."""
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def http_probe(url: str, *, timeout: float = 2.0) -> str:
    """Return ``ok`` (2xx) | ``http`` (connected, non-2xx) | ``down`` (no connection)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - loopback only
            return "ok" if 200 <= resp.status < 300 else "http"
    except urllib.error.HTTPError:
        return "http"  # the server answered, just not 2xx (e.g. 404 on /health)
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError):
        return "down"


def wait_ready(
    port: int,
    timeout_s: float,
    proc=None,
    *,
    mode: str = "tcp",
    health_path: str = "/health",
    host: str = "127.0.0.1",
    poll_s: float = 0.1,
) -> Optional[str]:
    """Poll until the server is ready. Returns ``None`` when ready, else a violation string.

    ``mode="tcp"``: ready when the port accepts a connection.
    ``mode="http"``: ready when ``health_path`` returns *any* HTTP response (``ok`` 2xx = app-health,
    ``http`` non-2xx = liveness — the TCP-connected fallback). A server that only TCP-accepts but never
    answers HTTP within the window degrades honestly (that is exactly what TCP-mode would have missed).
    If ``proc`` is given and exits early, returns immediately with that reason rather than waiting out
    the clock.
    """
    deadline = time.monotonic() + timeout_s
    base = f"http://{host}:{port}{health_path}"
    while time.monotonic() < deadline:
        if proc is not None and proc.poll() is not None:
            return f"server exited before readiness (rc={proc.returncode})"
        if mode == "http":
            if http_probe(base) in ("ok", "http"):
                return None
        elif tcp_probe(port, host):
            return None
        time.sleep(poll_s)
    return f"server never became ready on {host}:{port} within {timeout_s}s"
