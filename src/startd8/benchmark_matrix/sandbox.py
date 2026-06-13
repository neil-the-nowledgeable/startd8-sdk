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
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

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
