"""Project-level TypeScript/Prisma toolchain verification — RUN-008 FR-4/5/9.

The RUN-008 spike proved that a real, project-level ``tsc --noEmit`` (with
``prisma generate`` run first so the generated client types exist) catches the
**compile-class** of the run-008 failure: unresolvable ``@/`` imports (TS2307)
and invalid Prisma ``where`` usage on non-``@unique`` columns (TS2322). This is
the complement to the bespoke FR-7 Prisma↔Zod symmetry check (which catches the
*semantic* class `tsc` cannot see).

FR-9 (loud degradation) is the load-bearing safety property: when the toolchain
is absent (no ``node_modules``, no ``tsc``/``prisma``), the result is
``status="unavailable"`` which callers MUST treat as **non-pass** — never a
silent PASS (the exact deflection that let run-008 score 0.99). This inverts the
per-file ``nodejs.py`` behavior, which best-effort-passes when tsc is missing.

Subprocess execution is intentionally separate from parsing so the parser and
result interpretation are unit-testable without a Node toolchain.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# tsc non-pretty diagnostic line:
#   path/to/file.ts(LINE,COL): error TS####: message
_TSC_LINE_RE = re.compile(
    r"^(?P<file>[^()\n]+)\((?P<line>\d+),(?P<col>\d+)\):\s+error\s+(?P<code>TS\d+):\s+(?P<msg>.*)$"
)


@dataclass(frozen=True)
class TscDiagnostic:
    file: str
    line: int
    col: int
    code: str  # e.g. "TS2307"
    message: str


@dataclass
class ToolchainResult:
    """Outcome of a project typecheck.

    ``status``:
      - ``checked``     — tsc ran; ``diagnostics`` is authoritative.
      - ``unavailable`` — toolchain/deps missing; **NOT a pass** (FR-9).
      - ``timeout`` / ``error`` — ran but failed to complete; **NOT a pass**.
    """

    status: str
    diagnostics: List[TscDiagnostic] = field(default_factory=list)
    message: str = ""
    prisma_generated: bool = False

    @property
    def verdict(self) -> str:
        """``pass`` | ``fail`` | ``unavailable`` — the FR-9 contract."""
        if self.status != "checked":
            return "unavailable"
        return "fail" if self.diagnostics else "pass"

    @property
    def is_pass(self) -> bool:
        return self.verdict == "pass"


def parse_tsc_output(text: str) -> List[TscDiagnostic]:
    """Parse ``tsc --noEmit`` stdout into structured diagnostics (pure)."""
    diags: List[TscDiagnostic] = []
    for line in (text or "").splitlines():
        m = _TSC_LINE_RE.match(line.rstrip())
        if not m:
            continue  # continuation/indented detail lines are skipped
        diags.append(TscDiagnostic(
            file=m.group("file").strip(),
            line=int(m.group("line")),
            col=int(m.group("col")),
            code=m.group("code"),
            message=m.group("msg").strip(),
        ))
    return diags


def _is_real_tsc_output(text: str) -> bool:
    """True if output carries real ``error TS####`` diagnostics (not toolchain noise)."""
    return bool(re.search(r"error TS\d+", text or ""))


def _resolve_tsc(project_root: Path) -> Optional[List[str]]:
    """Locate a usable tsc invocation, preferring the project-local binary."""
    local = project_root / "node_modules" / ".bin" / "tsc"
    if local.is_file():
        return [str(local)]
    which = shutil.which("tsc")
    if which:
        return [which]
    npx = shutil.which("npx")
    if npx:
        return [npx, "--no-install", "tsc"]
    return None


def _resolve_prisma(project_root: Path) -> Optional[List[str]]:
    local = project_root / "node_modules" / ".bin" / "prisma"
    if local.is_file():
        return [str(local)]
    which = shutil.which("prisma")
    if which:
        return [which]
    npx = shutil.which("npx")
    if npx:
        return [npx, "--no-install", "prisma"]
    return None


def run_project_typecheck(
    project_root: str,
    *,
    run_prisma_generate: bool = True,
    timeout: int = 180,
) -> ToolchainResult:
    """Run ``prisma generate`` (if applicable) then project-level ``tsc --noEmit``.

    Returns ``status="unavailable"`` (FR-9 non-pass) when ``node_modules`` or the
    ``tsc`` binary is absent — the pipeline must *provision* the toolchain
    (OQ-3); we never silently pass an unverifiable TS project.
    """
    root = Path(project_root)
    if not (root / "node_modules").is_dir():
        return ToolchainResult(status="unavailable", message="node_modules not installed")
    tsc_cmd = _resolve_tsc(root)
    if tsc_cmd is None:
        return ToolchainResult(status="unavailable", message="tsc not found")

    prisma_generated = False
    if run_prisma_generate:
        schema = root / "prisma" / "schema.prisma"
        if schema.is_file():
            prisma_cmd = _resolve_prisma(root)
            if prisma_cmd is not None:
                try:
                    pr = subprocess.run(
                        [*prisma_cmd, "generate", "--schema", str(schema)],
                        cwd=str(root), capture_output=True, text=True, timeout=timeout,
                    )
                    prisma_generated = pr.returncode == 0
                except (OSError, subprocess.TimeoutExpired):
                    prisma_generated = False

    try:
        result = subprocess.run(
            [*tsc_cmd, "--noEmit", "-p", str(root)],
            cwd=str(root), capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return ToolchainResult(status="timeout", message="tsc --noEmit timed out",
                               prisma_generated=prisma_generated)
    except OSError as exc:
        return ToolchainResult(status="error", message=str(exc),
                               prisma_generated=prisma_generated)

    output = result.stdout.strip() or result.stderr.strip()
    if result.returncode == 0:
        return ToolchainResult(status="checked", diagnostics=[], prisma_generated=prisma_generated)
    if not _is_real_tsc_output(output):
        # Non-zero exit without real diagnostics = toolchain noise → unavailable,
        # NOT a pass and NOT a fail we can attribute.
        return ToolchainResult(status="unavailable",
                               message="tsc produced no parseable diagnostics",
                               prisma_generated=prisma_generated)
    return ToolchainResult(status="checked", diagnostics=parse_tsc_output(output),
                           prisma_generated=prisma_generated)


def diagnostics_by_file(diagnostics: List[TscDiagnostic]) -> Dict[str, List[TscDiagnostic]]:
    """Group diagnostics by their (normalized) file path for feature attribution."""
    out: Dict[str, List[TscDiagnostic]] = {}
    for d in diagnostics:
        out.setdefault(Path(d.file).as_posix(), []).append(d)
    return out


def typecheck_enabled() -> bool:
    """FR-9 / OQ-3 gate: project typecheck runs only when explicitly enabled.

    Off by default so existing runs (and CI without a Node toolchain) are
    unaffected; the pipeline host opts in via ``STARTD8_TS_TYPECHECK`` once it
    provisions ``npm install`` + ``prisma generate`` (the OQ-3 deployment decision).
    """
    return os.environ.get("STARTD8_TS_TYPECHECK", "").strip().lower() in ("1", "true", "yes", "on")
