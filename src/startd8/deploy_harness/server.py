"""Live uvicorn subprocess: free-port + bind-retry, health-poll, process-group teardown.

Implements FR-6/7/8 and FR-13. The app under test is untrusted, so the server is launched in its
own session/process group (``start_new_session=True``) bound to loopback, with ``cwd=app_root`` (the
generated ``sqlite:///./app.db`` is CWD-relative) and ``HOME``/``TMPDIR`` redirected to throwaway
space (FR-18 partial mitigation), under resource limits (FR-16). Teardown signals the whole group so
grandchildren (multi-worker uvicorn, app-spawned subprocesses) are reaped (CRP R1-F7/S4).

Health probing uses only the stdlib (``urllib``) so the harness process needs no HTTP client and the
probe never imports the untrusted app. ``/openapi.json`` is framework liveness, **not** app
readiness (CRP R1-F10): when it is the only answering probe the rung is graded ``pass:liveness-only``.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from startd8.logging_config import get_logger

from .venv_runner import ResourceLimits, _tail

logger = get_logger("startd8.deploy_harness.server")

# uvicorn stderr signatures that mean "the port was taken", i.e. a harness retry, not a model fault.
_BIND_ERROR_SIGNATURES = (
    "address already in use",
    "error while attempting to bind",
    "only one usage of each socket address",  # Windows
)

# Probe order (CRP R1-F10): app-defined readiness first, then framework liveness, then root.
_PROBES = (
    ("/health", "app-health"),
    ("/openapi.json", "liveness-only"),
    ("/", "liveness-only"),
)


def free_port() -> int:
    """Bind ``127.0.0.1:0``, read the assigned port, release it. Inherently racy — see bind-retry."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class BootOutcome:
    """Result of bringing the server up and probing it. Maps to the boot + health ladder rungs."""

    booted: bool
    health_ok: bool
    port: Optional[int] = None
    probe: Optional[str] = None  # which path answered 2xx
    quality: Optional[str] = None  # app-health | liveness-only
    boot_reason: Optional[str] = None  # typed reason when booted is False
    health_reason: Optional[str] = None  # typed reason when health_ok is False
    returncode: Optional[int] = None
    stderr_tail: str = ""
    log_path: Optional[str] = None
    port_retries: int = 0


def _probe(url: str, *, timeout: float = 2.0) -> str:
    """Return ``ok`` (2xx) | ``http`` (connected, non-2xx) | ``down`` (no connection)."""
    try:
        with urllib.request.urlopen(
            url, timeout=timeout
        ) as resp:  # noqa: S310 - loopback only
            return "ok" if 200 <= resp.status < 300 else "http"
    except urllib.error.HTTPError:
        return "http"  # the server answered, just not 2xx (e.g. 404 on /health)
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError):
        return "down"


class LiveServer:
    """Context manager that runs the app under uvicorn and tears the whole group down on exit."""

    def __init__(
        self,
        python: Path,
        target: str,
        app_root: Path,
        *,
        boot_timeout_s: float = 60.0,
        limits: Optional[ResourceLimits] = None,
        throwaway_home: Optional[Path] = None,
        log_path: Optional[Path] = None,
        max_port_retries: int = 3,
    ) -> None:
        self.python = python
        self.target = target
        self.app_root = app_root
        self.boot_timeout_s = boot_timeout_s
        self.limits = limits or ResourceLimits()
        self.throwaway_home = throwaway_home
        self.log_path = log_path
        self.max_port_retries = max_port_retries
        self._proc: Optional[subprocess.Popen] = None
        self._log_fh = None

    # -- lifecycle -----------------------------------------------------------------

    def _spawn(self, port: int) -> subprocess.Popen:
        env = dict(os.environ)
        if self.throwaway_home is not None:
            env["HOME"] = str(self.throwaway_home)
            env["TMPDIR"] = str(self.throwaway_home)
        cmd = [
            str(self.python),
            "-m",
            "uvicorn",
            self.target,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-access-log",
        ]
        stdout = self._log_fh if self._log_fh else subprocess.DEVNULL
        return subprocess.Popen(
            cmd,
            cwd=str(self.app_root),
            env=env,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            start_new_session=True,  # own process group → group teardown (FR-13)
            preexec_fn=self.limits.preexec(),
        )

    def __enter__(self) -> BootOutcome:
        if self.log_path is not None:
            try:
                self._log_fh = open(
                    self.log_path, "w", encoding="utf-8"
                )  # noqa: SIM115
            except OSError:
                self._log_fh = None

        retries = 0
        while True:
            port = free_port()
            self._proc = self._spawn(port)
            outcome = self._wait_until_ready(port)
            outcome.port_retries = retries
            outcome.log_path = str(self.log_path) if self.log_path else None
            # Port-bind race (CRP R1-S8): early exit with a bind signature → retry a fresh port.
            if (
                not outcome.booted
                and outcome.returncode is not None
                and _is_bind_error(outcome.stderr_tail)
                and retries < self.max_port_retries
            ):
                logger.debug(
                    "port %s bind race; retrying (%s/%s)",
                    port,
                    retries + 1,
                    self.max_port_retries,
                )
                self._reap()
                retries += 1
                continue
            self._outcome = outcome
            return outcome

    def __exit__(self, *exc) -> None:
        self._reap()
        if self._log_fh:
            try:
                self._log_fh.close()
            except OSError:
                pass

    # -- internals -----------------------------------------------------------------

    def _wait_until_ready(self, port: int) -> BootOutcome:
        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + self.boot_timeout_s
        connected = False
        while time.monotonic() < deadline:
            rc = self._proc.poll()
            if rc is not None:  # process exited before becoming ready
                return BootOutcome(
                    booted=False,
                    health_ok=False,
                    port=port,
                    returncode=rc,
                    boot_reason=f"early-exit:rc={rc}",
                    stderr_tail=self._read_log_tail(),
                )
            for path, quality in _PROBES:
                state = _probe(base + path)
                if state == "ok":
                    return BootOutcome(
                        booted=True,
                        health_ok=True,
                        port=port,
                        probe=path,
                        quality=quality,
                    )
                if state == "http":
                    connected = True
            time.sleep(0.15)

        # timed out
        if connected:  # port came up but no probe returned 2xx
            return BootOutcome(
                booted=True,
                health_ok=False,
                port=port,
                health_reason="no-2xx-probe",
                stderr_tail=self._read_log_tail(),
            )
        return BootOutcome(
            booted=False,
            health_ok=False,
            port=port,
            boot_reason=f"boot-timeout:{int(self.boot_timeout_s)}s",
            stderr_tail=self._read_log_tail(),
        )

    def _reap(self) -> None:
        """SIGTERM→wait→SIGKILL the whole process group; never raise."""
        proc = self._proc
        if proc is None:
            return
        if proc.poll() is not None:
            return
        try:
            pgid = os.getpgid(proc.pid)
        except (ProcessLookupError, OSError):
            pgid = None
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                if pgid is not None and os.name == "posix":
                    os.killpg(pgid, sig)
                else:  # pragma: no cover - non-POSIX fallback
                    proc.send_signal(sig)
            except (ProcessLookupError, OSError):
                return
            try:
                proc.wait(timeout=5)
                return
            except subprocess.TimeoutExpired:
                continue

    def _read_log_tail(self) -> str:
        if self._log_fh:
            try:
                self._log_fh.flush()
            except OSError:
                pass
        if self.log_path and Path(self.log_path).is_file():
            try:
                return _tail(
                    Path(self.log_path).read_text(encoding="utf-8", errors="replace")
                )
            except OSError:
                return ""
        return ""


def _is_bind_error(stderr_tail: str) -> bool:
    low = (stderr_tail or "").lower()
    return any(sig in low for sig in _BIND_ERROR_SIGNATURES)
