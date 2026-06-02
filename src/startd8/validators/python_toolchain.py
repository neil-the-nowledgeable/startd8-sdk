"""Project-level Python toolchain verification (Python contract-codegen, Step 3 / FR-5).

The Python sibling of ``ts_toolchain`` — a by-construction build gate over a *generated Python
project*. It mirrors that module's **verdict contract** (``checked`` / ``unavailable`` / ``timeout``
/ ``error`` → ``pass`` | ``fail`` | ``unavailable``) and its load-bearing **loud-degradation** rule
(an unverifiable project is never a silent PASS). It does **not** reuse ``ToolchainResult`` itself:
that type is TS-coupled (``prisma_generated`` + ``TscDiagnostic``), so a Python-native result is
clearer than overloading it (corrected from Requirements v0.2 §0, which assumed a literal reuse).

Three stages, in order:
  1. **compileall** — the mandatory syntax floor. ``python -m compileall`` is stdlib, so it is
     *always* available; the project's syntax is always verified.
  2. **mypy** — type check, *if available*. Absent ⇒ the stage is **skipped and recorded** (not a
     silent pass): the compileall floor still holds, and the skip is surfaced in ``stages_skipped``.
  3. **pytest** — test run, *if a tests path and pytest exist*. Absent / no tests ⇒ skipped+recorded.

Subprocess execution is intentionally separate from parsing so the parsers are unit-testable
without mypy/pytest installed.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

# mypy:  path.py:LINE:COL: error: message  [code]   (COL and [code] optional)
_MYPY_LINE_RE = re.compile(
    r"^(?P<file>[^:\n]+):(?P<line>\d+):(?:(?P<col>\d+):)?\s*error:\s*"
    r"(?P<msg>.*?)(?:\s+\[(?P<code>[\w-]+)\])?$"
)
# compileall syntax-error block:  File "path.py", line N   ...   SomeError: message
_COMPILE_FILE_RE = re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+)')
_COMPILE_ERR_RE = re.compile(r"^(?P<code>\w*(?:Error|Exception)): (?P<msg>.*)$")


@dataclass(frozen=True)
class PyDiagnostic:
    file: str
    line: int
    col: int
    code: str  # mypy code (e.g. "name-defined"), or an exception class ("SyntaxError")
    message: str
    stage: str  # "compileall" | "mypy" | "pytest"


@dataclass
class PyToolchainResult:
    """Outcome of a project build/type/test check.

    ``status``: ``checked`` (gate ran), ``unavailable`` (even the compileall floor could not run;
    NOT a pass), ``timeout`` / ``error`` (ran but failed to complete; NOT a pass).
    """

    status: str
    diagnostics: List[PyDiagnostic] = field(default_factory=list)
    message: str = ""
    stages_run: Tuple[str, ...] = ()
    stages_skipped: Tuple[str, ...] = ()

    @property
    def verdict(self) -> str:
        """``pass`` | ``fail`` | ``unavailable`` — mirrors the ts_toolchain contract."""
        if self.status != "checked":
            return "unavailable"
        return "fail" if self.diagnostics else "pass"

    @property
    def is_pass(self) -> bool:
        return self.verdict == "pass"


# --------------------------------------------------------------------------- #
# Pure parsers
# --------------------------------------------------------------------------- #


def parse_mypy_output(text: str) -> List[PyDiagnostic]:
    """Parse ``mypy`` stdout into structured diagnostics (pure)."""
    diags: List[PyDiagnostic] = []
    for line in (text or "").splitlines():
        m = _MYPY_LINE_RE.match(line.rstrip())
        if not m:
            continue
        diags.append(
            PyDiagnostic(
                file=m.group("file").strip(),
                line=int(m.group("line")),
                col=int(m.group("col")) if m.group("col") else 0,
                code=m.group("code") or "",
                message=m.group("msg").strip(),
                stage="mypy",
            )
        )
    return diags


def parse_compileall_output(text: str) -> List[PyDiagnostic]:
    """Parse ``compileall`` error blocks into diagnostics (pure).

    Pairs each ``File "x", line N`` with the following ``SomeError: message`` line.
    """
    diags: List[PyDiagnostic] = []
    pending: Optional[Tuple[str, int]] = None
    for raw in (text or "").splitlines():
        fm = _COMPILE_FILE_RE.search(raw)
        if fm:
            pending = (fm.group("file").strip(), int(fm.group("line")))
            continue
        em = _COMPILE_ERR_RE.match(raw.strip())
        if em and pending is not None:
            diags.append(
                PyDiagnostic(
                    file=pending[0],
                    line=pending[1],
                    col=0,
                    code=em.group("code"),
                    message=em.group("msg").strip(),
                    stage="compileall",
                )
            )
            pending = None
    return diags


# --------------------------------------------------------------------------- #
# Tool resolution
# --------------------------------------------------------------------------- #


def _resolve_tool(name: str) -> Optional[List[str]]:
    """A runnable command for *name*: the binary on PATH, else ``python -m <name>`` if importable."""
    which = shutil.which(name)
    if which:
        return [which]
    if importlib.util.find_spec(name) is not None:
        return [sys.executable, "-m", name]
    return None


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #


def run_project_check(
    project_root: str,
    *,
    run_mypy: bool = True,
    run_pytest: bool = True,
    timeout: int = 180,
) -> PyToolchainResult:
    """Run compileall → mypy → pytest over a generated Python project.

    compileall is the mandatory floor (always available). mypy/pytest run only when present (and
    pytest only when a ``tests`` path exists); when absent they are recorded in ``stages_skipped``
    rather than silently passed. Any stage's diagnostics make the verdict ``fail``.
    """
    root = Path(project_root)
    if not root.exists():
        return PyToolchainResult(status="error", message=f"path not found: {root}")

    diagnostics: List[PyDiagnostic] = []
    ran: List[str] = []
    skipped: List[str] = []

    # 1. compileall — the syntax floor.
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "compileall", "-q", str(root)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return PyToolchainResult(status="timeout", message="compileall timed out")
    except OSError as exc:
        return PyToolchainResult(status="error", message=str(exc))
    ran.append("compileall")
    if proc.returncode != 0:
        out = proc.stdout + "\n" + proc.stderr
        parsed = parse_compileall_output(out)
        diagnostics.extend(
            parsed
            or [
                PyDiagnostic(
                    file=str(root),
                    line=0,
                    col=0,
                    code="CompileError",
                    message=out.strip()[:500] or "compileall failed",
                    stage="compileall",
                )
            ]
        )

    # 2. mypy — type check, if available.
    if run_mypy:
        cmd = _resolve_tool("mypy")
        if cmd is None:
            skipped.append("mypy")
        else:
            try:
                proc = subprocess.run(
                    [*cmd, "--no-error-summary", "--no-color-output", str(root)],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                ran.append("mypy")
                diagnostics.extend(parse_mypy_output(proc.stdout))
            except subprocess.TimeoutExpired:
                return PyToolchainResult(
                    status="timeout",
                    message="mypy timed out",
                    stages_run=tuple(ran),
                    stages_skipped=tuple(skipped),
                )
            except OSError:
                skipped.append("mypy")
    else:
        skipped.append("mypy")

    # 3. pytest — only if enabled, there's a tests path, and pytest is available.
    tests_path = (root / "tests").is_dir() or any(root.glob("test_*.py"))
    if not run_pytest or not tests_path:
        skipped.append("pytest")
    else:
        cmd = _resolve_tool("pytest")
        if cmd is None:
            skipped.append("pytest")
        else:
            try:
                proc = subprocess.run(
                    [*cmd, "-q", str(root)],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                # 0 = pass; 5 = no tests collected (treat as a non-failing skip); else = failures.
                if proc.returncode == 5:
                    skipped.append("pytest")
                else:
                    ran.append("pytest")
                    if proc.returncode != 0:
                        summary = (proc.stdout or proc.stderr).strip().splitlines()
                        diagnostics.append(
                            PyDiagnostic(
                                file=str(root),
                                line=0,
                                col=0,
                                code="TestFailure",
                                message=summary[-1] if summary else "pytest failed",
                                stage="pytest",
                            )
                        )
            except subprocess.TimeoutExpired:
                return PyToolchainResult(
                    status="timeout",
                    message="pytest timed out",
                    stages_run=tuple(ran),
                    stages_skipped=tuple(skipped),
                )
            except OSError:
                skipped.append("pytest")

    return PyToolchainResult(
        status="checked",
        diagnostics=diagnostics,
        stages_run=tuple(ran),
        stages_skipped=tuple(skipped),
    )


def python_typecheck_enabled() -> bool:
    """Gate toggle, mirroring ``ts_toolchain.typecheck_enabled``.

    Off by default; the pipeline host opts in via ``STARTD8_PY_TYPECHECK`` once it provisions the
    toolchain (mypy/pytest). The compileall floor needs nothing beyond a Python interpreter.
    """
    return os.environ.get("STARTD8_PY_TYPECHECK", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
