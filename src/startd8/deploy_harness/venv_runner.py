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

    ``RLIMIT_AS`` (memory) backstops a memory balloon and is per-process, so it's safe to default on.
    ``RLIMIT_NPROC`` is **off by default**: it counts *all* of the real-user's processes, not just the
    job's children, so any fixed cap either false-trips on a busy machine (a dev box with hundreds of
    existing processes fails the next ``fork()`` with EAGAIN — e.g. pip's build-isolation subprocess)
    or sits above the system ``ulimit -u`` and does nothing. The fork-bomb backstop is instead the OS
    per-user limit plus the harness's wall-clock timeouts and process-group teardown. Set
    ``max_processes`` explicitly only on a dedicated/CI box. CPU is left unbounded so a legitimately
    long-lived server isn't reaped. All best-effort: a platform that refuses a limit is skipped.
    """

    address_space_bytes: Optional[int] = 4 * 1024 * 1024 * 1024  # 4 GiB
    max_processes: Optional[int] = (
        None  # see docstring — per-user-total semantics make a cap unsafe
    )
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


def _pip_base(python: str, build_isolation: bool) -> list[str]:
    cmd = [python, "-m", "pip", "install", "--disable-pip-version-check", "--no-input"]
    if not build_isolation:
        cmd.append("--no-build-isolation")
    return cmd


def _build_pip_cmd(
    python: str,
    packages: Sequence[str],
    editable_installs: Sequence[str],
    *,
    build_isolation: bool,
) -> list[str]:
    """Construct a pip-install argv: ``-e <path>`` entries then the named requirements (+ runner)."""
    cmd = _pip_base(python, build_isolation)
    for path in editable_installs:
        cmd += ["-e", str(path)]
    cmd.extend(dict.fromkeys([*packages, *_RUNNER_DEPS]))  # dedup, preserve order
    return cmd


def install_deps(
    venv_obj: Venv,
    packages: Sequence[str],
    *,
    timeout_s: float = 600.0,
    log_path: Optional[Path] = None,
    limits: Optional[ResourceLimits] = None,
    build_isolation: bool = True,
    editable_installs: Optional[Sequence[str]] = None,
) -> InstallOutcome:
    """pip-install ``packages`` (+ the uvicorn runner) into ``venv_obj`` with hardening + rlimits.

    ``editable_installs`` — local project paths installed ``-e`` **in a prior, separate pip call**, so
    an app that depends on an unpublished local package (e.g. the ``startd8`` SDK itself) is deployable
    from a clean-room venv: once the editable is installed, the bare ``startd8`` requirement is
    already-satisfied and pip skips the index lookup that would otherwise fail. (Installing both in one
    call doesn't work — pip still resolves the named requirement against the index.) Returns a graded
    :class:`InstallOutcome`; never raises on a non-zero pip exit.
    """
    limits = limits or ResourceLimits()
    index_url = os.environ.get("PIP_INDEX_URL", "https://pypi.org/simple")
    python = str(venv_obj.python)
    editables = list(editable_installs or ())
    log_chunks: List[str] = []

    # Phase 1 (optional): editables first, as their own resolve.
    if editables:
        ed_cmd = _pip_base(python, build_isolation)
        for path in editables:
            ed_cmd += ["-e", str(path)]
        ed = _run_pip(ed_cmd, timeout_s, limits)
        log_chunks.append("$ " + " ".join(ed_cmd) + "\n" + ed.combined_log())
        if not ed.ok:
            _write_log(log_path, log_chunks)
            return InstallOutcome(
                ok=False,
                returncode=ed.returncode,
                duration_s=ed.duration_s,
                reason=ed.reason("editable"),
                stdout_tail=_tail(ed.stdout),
                stderr_tail=_tail(ed.stderr),
                log_path=str(log_path) if log_path else None,
                index_url=index_url,
                build_isolation=build_isolation,
            )

    # Phase 2: the app's requirements (+ runner). Local deps are now already-satisfied.
    cmd = _build_pip_cmd(python, packages, [], build_isolation=build_isolation)
    res = _run_pip(cmd, timeout_s, limits)
    log_chunks.append("$ " + " ".join(cmd) + "\n" + res.combined_log())
    _write_log(log_path, log_chunks)
    if not res.ok:
        return InstallOutcome(
            ok=False,
            returncode=res.returncode,
            duration_s=res.duration_s,
            reason=res.reason("install"),
            stdout_tail=_tail(res.stdout),
            stderr_tail=_tail(res.stderr),
            log_path=str(log_path) if log_path else None,
            index_url=index_url,
            build_isolation=build_isolation,
        )

    return InstallOutcome(
        ok=True,
        returncode=0,
        duration_s=res.duration_s,
        stdout_tail=_tail(res.stdout),
        stderr_tail=_tail(res.stderr),
        log_path=str(log_path) if log_path else None,
        freeze=_freeze(venv_obj),
        index_url=index_url,
        build_isolation=build_isolation,
    )


@dataclass
class _PipRun:
    ok: bool
    returncode: Optional[int]
    duration_s: float
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    timeout_s: float = 0.0

    def reason(self, phase: str) -> str:
        if self.timed_out:
            return f"{phase}-timeout:{int(self.timeout_s)}s"
        return (
            f"{phase}-pip-exit-{self.returncode}"
            if phase == "editable"
            else f"pip-exit-{self.returncode}"
        )

    def combined_log(self) -> str:
        return (self.stdout or "") + "\n--- STDERR ---\n" + (self.stderr or "")


def _run_pip(cmd: list[str], timeout_s: float, limits: "ResourceLimits") -> _PipRun:
    import time as _time  # module-level time is monkeypatch-sensitive in tests

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
        tail = (
            (exc.stderr or b"").decode("utf-8", "replace")
            if isinstance(exc.stderr, bytes)
            else (exc.stderr or "")
        )
        return _PipRun(
            ok=False,
            returncode=None,
            duration_s=_time.monotonic() - start,
            stderr=tail,
            timed_out=True,
            timeout_s=timeout_s,
        )
    return _PipRun(
        ok=(proc.returncode == 0),
        returncode=proc.returncode,
        duration_s=_time.monotonic() - start,
        stdout=proc.stdout or "",
        stderr=proc.stderr or "",
    )


def _write_log(log_path: Optional[Path], chunks: List[str]) -> None:
    if log_path is None:
        return
    try:
        log_path.write_text("\n\n".join(chunks), encoding="utf-8")
    except OSError:
        pass


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
