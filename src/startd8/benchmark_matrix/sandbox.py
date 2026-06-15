"""Untrusted-code execution sandbox (FR-44 — CRITICAL).

M4 executes model-generated code (compile/lint/test). Model output is untrusted: it may
try to read API keys, write outside its workspace, fork-bomb, or exfiltrate over the
network. This module runs such commands under defense-in-depth controls achievable on a
POSIX/macOS dev host:

  - **Scrubbed environment** — every secret-shaped var (*_API_KEY/_TOKEN/_SECRET, vendor
    keys, AWS_/DOPPLER_) is stripped; HOME is redirected into the disposable workspace so
    dotfiles/credentials are unreachable.
  - **Resource limits** — CPU seconds, address space, process count, file size via
    setrlimit (preexec) — bounds fork-bombs / runaway memory / disk.
  - **No network egress** — on macOS via a `sandbox-exec` (Seatbelt) deny-network profile;
    this also doubles as dependency quarantine (R3 plan-S1: model-declared deps can't be
    fetched at build time). On Linux, `unshare -rn` when available.
  - **Wall-clock timeout** and bounded output capture.

PRODUCTION HARDENING (deferred, R3-S2): kernel-level isolation (gVisor / Firecracker) or a
no-network Docker container is the strong path for an untrusted multi-tenant runner. It is
not available on this macOS dev host; revisit when runs move to Linux/containers (ADR-style
trigger). ``isolation_level`` records which controls were actually applied so results are
honest about coverage.
"""
from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Env var name markers whose values must never reach untrusted code.
_SECRET_MARKERS = ("API_KEY", "_TOKEN", "TOKEN_", "_SECRET", "SECRET_", "PASSWORD",
                   "ANTHROPIC", "OPENAI", "GOOGLE", "GEMINI", "MISTRAL", "NVIDIA",
                   "AWS_", "DOPPLER", "_KEY", "CREDENTIAL")


@dataclass
class SandboxConfig:
    no_network: bool = True
    cpu_seconds: int = 60
    mem_mb: int = 2048
    max_processes: int = 256
    max_file_mb: int = 64
    wall_timeout_s: float = 120.0
    max_output_bytes: int = 64 * 1024


@dataclass
class SandboxResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    duration_s: float
    isolation_level: str                 # which controls actually applied
    violation: Optional[str] = None      # set when a guardrail tripped
    network_isolated: bool = False


def scrub_env(workspace: Path, base: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Return an environment with secrets removed and HOME redirected into the workspace."""
    src = dict(base if base is not None else os.environ)
    clean = {
        k: v for k, v in src.items()
        if not any(m in k.upper() for m in _SECRET_MARKERS)
    }
    # Keep PATH so toolchains resolve; redirect HOME so ~/.dotfiles/creds are unreachable.
    clean["HOME"] = str(workspace)
    clean["TMPDIR"] = str(workspace)
    clean.pop("PYTHONPATH", None)  # don't leak the harness's import path into untrusted code
    return clean


def sandbox_caps() -> Dict[str, bool]:
    """Detect available isolation mechanisms on this host."""
    return {
        "rlimits": hasattr(__import__("resource"), "setrlimit"),
        "sandbox_exec": sys.platform == "darwin" and shutil.which("sandbox-exec") is not None,
        "unshare": sys.platform.startswith("linux") and shutil.which("unshare") is not None,
        "docker": shutil.which("docker") is not None,
    }


def _rlimit_preexec(cfg: SandboxConfig):
    import resource

    def _apply():
        os.setsid()  # own process group → fork-bomb / cleanup containment
        def _set(res, soft):
            try:
                resource.setrlimit(res, (soft, soft))
            except (ValueError, OSError):
                pass
        _set(resource.RLIMIT_CPU, cfg.cpu_seconds)
        _set(resource.RLIMIT_NPROC, cfg.max_processes)
        _set(resource.RLIMIT_FSIZE, cfg.max_file_mb * 1024 * 1024)
        # Address space (memory). RLIMIT_AS is unreliable on macOS; try DATA too.
        for res_name in ("RLIMIT_AS", "RLIMIT_DATA"):
            res = getattr(resource, res_name, None)
            if res is not None:
                _set(res, cfg.mem_mb * 1024 * 1024)
    return _apply


def _wrap_no_network(cmd: List[str], caps: Dict[str, bool]) -> tuple[List[str], bool]:
    """Wrap cmd to deny network egress where the OS supports it. Returns (cmd, isolated?)."""
    if caps["sandbox_exec"]:
        # Seatbelt: allow everything except network (lets compilers/fs work; blocks egress
        # AND blocks build-time dependency fetches — dependency quarantine, R3 plan-S1).
        profile = "(version 1)(allow default)(deny network*)"
        return (["sandbox-exec", "-p", profile, *cmd], True)
    if caps["unshare"]:
        return (["unshare", "-rn", *cmd], True)
    return (cmd, False)  # best-effort: no OS network isolation available


def run_sandboxed(cmd: List[str], workspace: Path, cfg: Optional[SandboxConfig] = None,
                  *, file_path: Optional[Path] = None) -> SandboxResult:
    """Run ``cmd`` against untrusted code under the available sandbox controls.

    ``{file}`` tokens in cmd are replaced with ``file_path``. Returns a SandboxResult; a
    resource/timeout/network breach sets ``violation`` (the caller must NOT score a sandbox
    violation as model quality — it is an environment outcome, like FR-32).
    """
    cfg = cfg or SandboxConfig()
    caps = sandbox_caps()
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    if file_path is not None:
        cmd = [str(file_path) if tok == "{file}" else tok.replace("{file}", str(file_path))
               for tok in cmd]

    run_cmd, net_isolated = (_wrap_no_network(cmd, caps) if cfg.no_network else (cmd, False))
    levels = ["rlimits"] if caps["rlimits"] else []
    if net_isolated:
        levels.append("seatbelt" if caps["sandbox_exec"] else "netns")
    isolation_level = "+".join(levels) if levels else "none(best-effort)"

    env = scrub_env(workspace)
    started = time.monotonic()
    violation: Optional[str] = None
    try:
        proc = subprocess.run(
            run_cmd, cwd=str(workspace), env=env,
            capture_output=True, text=True, check=False,
            timeout=cfg.wall_timeout_s,
            preexec_fn=_rlimit_preexec(cfg) if caps["rlimits"] else None,
        )
        rc, out, err, timed_out = proc.returncode, proc.stdout, proc.stderr, False
        # Negative rc = killed by signal (e.g. SIGXCPU/SIGKILL from rlimits) → violation.
        if rc < 0:
            violation = f"killed by signal {-rc} (likely resource limit: cpu/mem/procs)"
    except subprocess.TimeoutExpired as e:
        rc, timed_out = 124, True
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        err = (e.stderr or "") if isinstance(e.stderr, str) else ""
        violation = f"wall-clock timeout after {cfg.wall_timeout_s}s"
    except Exception as e:  # noqa: BLE001 — sandbox must never crash the harness
        rc, out, err, timed_out = 1, "", f"sandbox error: {e}", False
        violation = f"sandbox launch error: {type(e).__name__}"

    return SandboxResult(
        returncode=rc,
        stdout=out[-cfg.max_output_bytes:],
        stderr=err[-cfg.max_output_bytes:],
        timed_out=timed_out,
        duration_s=time.monotonic() - started,
        isolation_level=isolation_level,
        violation=violation,
        network_isolated=net_isolated,
    )


# --------------------------------------------------------------------------- behavioral (Track 2 / M-T2.1)
#
# The one-shot run_sandboxed above can't execute a *service*: behavioral scoring (FR-T2-1) needs a
# long-lived server, a readiness wait, a loopback client window, and a GUARANTEED teardown. This
# section adds that primitive. Two grounded constraints from the Track 2 plan:
#   - G2/FR-T2-SEC: loopback must be ALLOWED while external egress stays denied — the one-shot
#     `(deny network*)` profile blocks loopback too, so a server+client over 127.0.0.1 can't run.
#   - FR-T2-2: an environment failure (never-ready / launch error / client raised) sets ``violation``
#     so the caller DEGRADES the cell — it must never be scored as model quality.


@dataclass
class ServiceResult:
    ready: bool                          # server accepted a loopback connection within the window
    client_outcome: Any = None           # whatever client(port) returned; None if never ready
    server_returncode: Optional[int] = None
    server_stdout: str = ""
    server_stderr: str = ""
    duration_s: float = 0.0
    isolation_level: str = "none(best-effort)"
    violation: Optional[str] = None      # env outcome (degrade, FR-T2-2) — NOT model quality
    network_isolated: bool = False       # external egress denied (loopback still allowed)


def _port_ready(port: int, host: str = "127.0.0.1") -> bool:
    """True if something accepts a TCP connection on host:port right now."""
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _wait_ready(port: int, timeout_s: float, proc: "subprocess.Popen",
                poll_s: float = 0.1) -> Optional[str]:
    """Poll until the server accepts loopback connections. Returns None when ready, else a
    violation string (server exited early, or readiness timed out)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return f"server exited before readiness (rc={proc.returncode})"
        if _port_ready(port):
            return None
        time.sleep(poll_s)
    return f"server never became ready on 127.0.0.1:{port} within {timeout_s}s"


def _wrap_loopback_only(cmd: List[str], caps: Dict[str, bool]) -> tuple[List[str], bool, str]:
    """Allow loopback bind/connect, deny external egress (FR-T2-SEC). Returns (cmd, egress_denied, label).

    Unlike ``_wrap_no_network`` (which denies ALL network), this permits 127.0.0.1 so a behavioral
    server+client can talk, while still blocking egress to remote hosts (and build-time dep fetches).
    """
    if caps["sandbox_exec"]:
        # Seatbelt evaluates top→bottom, last match wins: deny all network, then re-allow localhost.
        profile = (
            "(version 1)(allow default)(deny network*)"
            '(allow network* (remote ip "localhost:*"))'
            '(allow network-bind (local ip "localhost:*"))'
        )
        return (["sandbox-exec", "-p", profile, *cmd], True, "seatbelt-loopback")
    if caps["unshare"]:
        # A fresh net namespace has only loopback → egress is impossible. (If `lo` is down, the
        # readiness probe will fail and the cell degrades honestly rather than scoring wrong.)
        return (["unshare", "-rn", *cmd], True, "netns-loopback")
    return (cmd, False, "none(best-effort)")


def _terminate_group(proc: "subprocess.Popen") -> None:
    """Guaranteed teardown: SIGTERM the whole process group, brief grace, then SIGKILL; reap.

    The server runs as its own session/group leader (setsid via _rlimit_preexec or
    start_new_session), so killing the group reaps double-forked children too — no orphans."""
    if proc.poll() is not None:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:                       # group gone/unavailable → fall back to the lone process
                proc.send_signal(sig)
            except (ProcessLookupError, OSError):
                return
        try:
            proc.wait(timeout=3.0)
            return
        except subprocess.TimeoutExpired:
            continue  # escalate to SIGKILL


def run_service_sandboxed(
    server_cmd: List[str],
    workspace: Path,
    port: int,
    client: Callable[[int], Any],
    cfg: Optional[SandboxConfig] = None,
    *,
    readiness_timeout_s: float = 15.0,
) -> ServiceResult:
    """Run an untrusted long-lived server, drive it with a loopback client, ALWAYS tear it down.

    Starts ``server_cmd`` under the sandbox controls (scrubbed env, rlimits, loopback-only network),
    waits until ``port`` accepts loopback connections, calls ``client(port)`` against the live
    server, then unconditionally kills the whole process group and captures bounded server output.
    Any environment failure (never-ready, launch error, client raised) sets ``violation`` so the
    caller degrades the cell (FR-T2-2) instead of scoring it as model quality.
    """
    cfg = cfg or SandboxConfig()
    caps = sandbox_caps()
    workspace = Path(workspace)
    workspace.mkdir(parents=True, exist_ok=True)

    run_cmd, egress_denied, net_label = (
        _wrap_loopback_only(server_cmd, caps) if cfg.no_network else (server_cmd, False, "none(disabled)")
    )
    levels = (["rlimits"] if caps["rlimits"] else []) + ([net_label] if egress_denied else [])
    isolation_level = "+".join(levels) if levels else "none(best-effort)"

    env = scrub_env(workspace)
    # _rlimit_preexec already calls os.setsid(); only ask Popen to start a new session when it won't,
    # otherwise the double setsid() raises EPERM in the child and exec fails.
    preexec = _rlimit_preexec(cfg) if caps["rlimits"] else None
    started = time.monotonic()
    proc: Optional[subprocess.Popen] = None
    ready = False
    client_outcome: Any = None
    violation: Optional[str] = None
    out, err = "", ""
    try:
        proc = subprocess.Popen(
            run_cmd, cwd=str(workspace), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            preexec_fn=preexec,
            start_new_session=(preexec is None),
        )
        violation = _wait_ready(port, readiness_timeout_s, proc)
        ready = violation is None
        if ready:
            try:
                client_outcome = client(port)
            except Exception as e:  # noqa: BLE001 — client failure is an env outcome, not model quality
                violation = f"client error: {type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001 — the sandbox must never crash the harness
        violation = f"sandbox launch error: {type(e).__name__}: {e}"
    finally:
        if proc is not None:
            _terminate_group(proc)
            try:
                out, err = proc.communicate(timeout=3.0)
            except Exception:  # noqa: BLE001 — output capture is best-effort after teardown
                out, err = out or "", err or ""

    return ServiceResult(
        ready=ready,
        client_outcome=client_outcome,
        server_returncode=proc.returncode if proc is not None else None,
        server_stdout=(out or "")[-cfg.max_output_bytes:],
        server_stderr=(err or "")[-cfg.max_output_bytes:],
        duration_s=time.monotonic() - started,
        isolation_level=isolation_level,
        violation=violation,
        network_isolated=egress_denied,
    )
