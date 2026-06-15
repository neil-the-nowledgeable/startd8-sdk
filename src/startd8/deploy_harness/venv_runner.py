"""Throwaway isolated venv + hardened pip install (FR-4/5, FR-16/17).

The app under test is UNTRUSTED and ``pip install`` is the **first arbitrary-code-execution
surface** — PEP 517 build backends run attacker-influenced code, and the resolver reaches the index
over the network, both *before* any boot timeout (CRP R1-F1/S1). v1 therefore: installs into a venv
that is never the SDK's interpreter (FR-4), makes the build-isolation choice explicit and recorded,
applies resource limits to the child (FR-16/[R1-S2]), and treats install as its own graded rung. Full
containment is the v2/FR-44 Docker line.
"""

from __future__ import annotations

import os
import subprocess
import venv
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

from startd8.logging_config import get_logger

logger = get_logger("startd8.deploy_harness.venv_runner")

# uvicorn is the harness's *runner*, not the app's dependency — ensure it regardless of what the
# app declared (a raw LLM app may omit the dev server). Kept distinct from the app's dep set.
_RUNNER_DEPS = ("uvicorn[standard]",)


@dataclass
class ResourceLimits:
    """Best-effort POSIX rlimits applied to harness child processes (FR-16).

    Defaults backstop the two host-killing failure modes named in the CRP — fork bombs (NPROC) and
    memory balloons (AS) — while leaving CPU unbounded so a legitimately long-lived server is not
    reaped (wall-clock timeouts are the time backstop). All best-effort: a platform that refuses a
    limit (common for ``RLIMIT_AS`` on macOS) is logged and skipped, never fatal.
    """

    address_space_bytes: Optional[int] = 4 * 1024 * 1024 * 1024  # 4 GiB
    max_processes: Optional[int] = 256
    cpu_seconds: Optional[int] = None  # off by default — don't reap a long-lived server

    def preexec(self):
        """Return a ``preexec_fn`` that applies these limits in the child, or ``None`` off-POSIX."""
        if os.name != "posix":
            return None
        try:
            import resource
        except ImportError:  # pragma: no cover - non-POSIX
            return None

        limits = self

        def _apply() -> None:  # runs in the forked child, pre-exec
            for res_name, value in (
                ("RLIMIT_AS", limits.address_space_bytes),
                ("RLIMIT_NPROC", limits.max_processes),
                ("RLIMIT_CPU", limits.cpu_seconds),
            ):
                if value is None:
                    continue
                res = getattr(resource, res_name, None)
                if res is None:
                    continue
                try:
                    soft, hard = resource.getrlimit(res)
                    new_hard = (
                        value if hard == resource.RLIM_INFINITY else min(value, hard)
                    )
                    resource.setrlimit(res, (min(value, new_hard), new_hard))
                except (ValueError, OSError):
                    pass  # best-effort; some platforms reject AS/NPROC

        return _apply


@dataclass
class InstallOutcome:
    ok: bool
    returncode: Optional[int]
    duration_s: float
    reason: Optional[str] = None  # typed failure reason on not-ok
    stdout_tail: str = ""
    stderr_tail: str = ""
    log_path: Optional[str] = None
    freeze: List[str] = field(default_factory=list)
    build_isolation: bool = True
    index_url: str = "https://pypi.org/simple"


@dataclass
class Venv:
    """A throwaway virtualenv. ``python`` is the interpreter to launch the app/pip with."""

    root: Path
    python: Path

    @property
    def python_version(self) -> str:
        try:
            out = subprocess.run(
                [str(self.python), "--version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return (out.stdout or out.stderr).strip()
        except Exception:  # pragma: no cover
            return "unknown"


def create_venv(parent: Path) -> Venv:
    """Create a fresh venv under ``parent`` (a throwaway dir *outside* the app root)."""
    vdir = parent / "venv"
    venv.EnvBuilder(with_pip=True, clear=True).create(str(vdir))
    bindir = "Scripts" if os.name == "nt" else "bin"
    py = vdir / bindir / ("python.exe" if os.name == "nt" else "python")
    return Venv(root=vdir, python=py)


def install_deps(
    venv_obj: Venv,
    packages: Sequence[str],
    *,
    timeout_s: float = 600.0,
    log_path: Optional[Path] = None,
    limits: Optional[ResourceLimits] = None,
    build_isolation: bool = True,
) -> InstallOutcome:
    """pip-install ``packages`` (+ the uvicorn runner) into ``venv_obj`` with hardening + rlimits.

    Returns a graded :class:`InstallOutcome`; never raises on a non-zero pip exit or timeout.
    """
    limits = limits or ResourceLimits()
    index_url = os.environ.get("PIP_INDEX_URL", "https://pypi.org/simple")
    pkgs = list(dict.fromkeys([*packages, *_RUNNER_DEPS]))  # dedup, preserve order

    cmd = [
        str(venv_obj.python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--no-input",
    ]
    if not build_isolation:
        cmd.append("--no-build-isolation")
    cmd.extend(pkgs)

    import time as _time  # local: module-level time is monkeypatch-sensitive in tests

    start = _time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            preexec_fn=limits.preexec(),
        )
    except subprocess.TimeoutExpired as exc:
        dur = _time.monotonic() - start
        tail = (
            (exc.stderr or b"").decode("utf-8", "replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )
        return InstallOutcome(
            ok=False,
            returncode=None,
            duration_s=dur,
            reason=f"install-timeout:{int(timeout_s)}s",
            stderr_tail=_tail(tail),
            index_url=index_url,
            build_isolation=build_isolation,
        )
    dur = _time.monotonic() - start

    if log_path is not None:
        try:
            log_path.write_text(
                (proc.stdout or "") + "\n--- STDERR ---\n" + (proc.stderr or ""),
                encoding="utf-8",
            )
        except OSError:
            pass

    if proc.returncode != 0:
        return InstallOutcome(
            ok=False,
            returncode=proc.returncode,
            duration_s=dur,
            reason=f"pip-exit-{proc.returncode}",
            stdout_tail=_tail(proc.stdout),
            stderr_tail=_tail(proc.stderr),
            log_path=str(log_path) if log_path else None,
            index_url=index_url,
            build_isolation=build_isolation,
        )

    return InstallOutcome(
        ok=True,
        returncode=0,
        duration_s=dur,
        stdout_tail=_tail(proc.stdout),
        stderr_tail=_tail(proc.stderr),
        log_path=str(log_path) if log_path else None,
        freeze=_freeze(venv_obj),
        index_url=index_url,
        build_isolation=build_isolation,
    )


def _freeze(venv_obj: Venv) -> List[str]:
    try:
        out = subprocess.run(
            [str(venv_obj.python), "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return [ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip()]
    except Exception:  # pragma: no cover
        return []


def _tail(text: Optional[str], *, lines: int = 30) -> str:
    if not text:
        return ""
    return "\n".join(text.splitlines()[-lines:])
