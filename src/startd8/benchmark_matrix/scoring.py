"""Composite quality scoring — compile gate + structural + optional lint (FR-11 / FR-29).

The flagships-round1 partial run proved structural-compliance saturates (all frontier models
1.000). The discriminating signal is *functional*: does the generated code actually compile?
M4 adds a **required compile gate** (run the language's syntax/compile check on the generated
file, inside the FR-44 sandbox) and folds it into a composite:

  - compile gate FAILS  → quality floored to COMPILE_FLOOR (a structurally-perfect file that
    doesn't compile cannot top the leaderboard — CRP R1-F2).
  - compile gate PASSES → quality = structural score (+ optional lint adjustment).
  - toolchain ABSENT    → degraded coverage (FR-32): fall back to structural, do NOT penalize
    the model for a missing runner toolchain; record the gap.

Test execution is intentionally NOT a primary term here (OQ-11: model-written tests are
self-grading; a fixed per-service suite is deferred past Round 1). Lint is optional enrichment.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .sandbox import SandboxConfig, run_sandboxed

COMPILE_FLOOR = 0.15  # quality cap for code that fails the compile gate (CRP R1-F2)


# Sandbox-safe single-file syntax fallbacks for languages whose LanguageProfile leaves
# syntax_check_command = None but where a safe, dependency-free, parse-only check exists.
# Node: `node --check` parses (does NOT execute or resolve requires) — scoped to plain JS
# extensions only, since the nodejs profile intentionally returns None to avoid `node --check`
# breaking on .ts/.tsx (REQ-NODE-MP-305). Keyed by language_id -> {ext: command}.
_FALLBACK_SYNTAX_COMMANDS = {
    "nodejs": {
        ".js": ["node", "--check", "{file}"],
        ".cjs": ["node", "--check", "{file}"],
        ".mjs": ["node", "--check", "{file}"],
    },
}


def fallback_syntax_command(profile, file_path) -> Optional[List[str]]:
    """A sandbox-safe single-file syntax command when the profile has none (e.g. Node .js)."""
    lang = getattr(profile, "language_id", "") or ""
    ext = Path(file_path).suffix.lower()
    return _FALLBACK_SYNTAX_COMMANDS.get(lang, {}).get(ext)


@dataclass
class GateResult:
    name: str                       # "compile" / "lint"
    available: bool                 # False -> toolchain absent (FR-32 degraded)
    passed: Optional[bool]          # None when not available
    detail: str = ""
    sandbox_violation: Optional[str] = None
    isolation_level: str = ""


@dataclass
class CompositeScore:
    value: float
    structural: Optional[float]
    compile_ok: Optional[bool]      # None when compile toolchain absent
    degraded: bool                  # some term unavailable (FR-32)
    terms_available: List[str] = field(default_factory=list)
    terms_missing: List[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> Dict:
        return {
            "value": self.value, "structural": self.structural, "compile_ok": self.compile_ok,
            "degraded": self.degraded, "terms_available": self.terms_available,
            "terms_missing": self.terms_missing, "note": self.note,
        }


def _toolchain_absent(rc: int, stderr: str) -> bool:
    """Heuristic: the command itself isn't installed (vs the code failing to compile)."""
    if rc == 127:
        return True
    low = stderr.lower()
    return ("command not found" in low or "no such file or directory" in low
            or "not recognized as" in low or "executable file not found" in low)


def run_gate(name: str, command: Optional[List[str]], file_path: Path,
             cfg: Optional[SandboxConfig] = None) -> GateResult:
    """Run one tool command (compile or lint) on a generated file, inside the sandbox."""
    if not command:
        return GateResult(name=name, available=False, passed=None, detail="no command for language")
    workspace = Path(file_path).resolve().parent
    res = run_sandboxed(list(command), workspace, cfg, file_path=Path(file_path).resolve())
    if res.violation and not res.timed_out and res.returncode != 0 and _toolchain_absent(res.returncode, res.stderr):
        # ambiguous; treat explicit toolchain-absent below
        pass
    if _toolchain_absent(res.returncode, res.stderr):
        return GateResult(name=name, available=False, passed=None,
                          detail=f"toolchain absent (rc={res.returncode})",
                          isolation_level=res.isolation_level)
    if res.violation:
        # Sandbox guardrail tripped (timeout/resource) — not a clean pass/fail signal.
        return GateResult(name=name, available=True, passed=False,
                          detail=res.violation, sandbox_violation=res.violation,
                          isolation_level=res.isolation_level)
    passed = res.returncode == 0
    return GateResult(name=name, available=True, passed=passed,
                      detail=(res.stderr or res.stdout or "")[-400:],
                      isolation_level=res.isolation_level)


def compute_composite(structural: Optional[float], compile_gate: GateResult,
                      lint_gate: Optional[GateResult] = None) -> CompositeScore:
    """Combine the structural score with the compile gate (+ optional lint) per FR-11."""
    s = structural if structural is not None else 0.0
    available, missing = [], []

    if compile_gate.available:
        available.append("compile")
        if compile_gate.passed is False:
            return CompositeScore(
                value=min(s, COMPILE_FLOOR), structural=structural, compile_ok=False,
                degraded=False, terms_available=available, terms_missing=missing,
                note=f"compile FAILED → floored to {COMPILE_FLOOR}; {compile_gate.detail[:80]}",
            )
        compile_ok = True
    else:
        missing.append("compile")
        compile_ok = None  # FR-32: degraded — don't penalize for missing toolchain

    value = s  # compile passed (or degraded): structural is the base
    note = ""
    if lint_gate is not None:
        if lint_gate.available:
            available.append("lint")
            if lint_gate.passed is False:
                value = max(0.0, value - 0.05)  # small lint penalty, doesn't dominate
                note = "lint issues (-0.05)"
        else:
            missing.append("lint")

    degraded = bool(missing)
    if degraded and not note:
        note = f"degraded coverage — missing: {', '.join(missing)} (FR-32, not penalized)"
    return CompositeScore(value=round(value, 4), structural=structural, compile_ok=compile_ok,
                          degraded=degraded, terms_available=available, terms_missing=missing,
                          note=note)


def score_file(file_path: Path, profile, *, cfg: Optional[SandboxConfig] = None,
               structural: Optional[float] = None, run_lint: bool = True) -> CompositeScore:
    """Convenience: compile-gate (+ optional lint) a generated file via its LanguageProfile."""
    fp = Path(file_path)
    if not fp.exists():
        return CompositeScore(value=min(structural or 0.0, COMPILE_FLOOR), structural=structural,
                              compile_ok=False, degraded=False, terms_available=["compile"],
                              note="generated file not found → floored")
    compile_cmd = getattr(profile, "syntax_check_command", None)
    if not compile_cmd:
        # Profile exposes no syntax command (e.g. nodejs) — use a sandbox-safe single-file
        # fallback where one exists (Node `node --check` for .js). Keeps the check INSIDE the
        # FR-44 sandbox and degrades (not pass) when the toolchain is absent — unlike the
        # profile's own validate_syntax(), which runs unsandboxed and treats absent as pass.
        compile_cmd = fallback_syntax_command(profile, fp)
    lint_cmd = getattr(profile, "lint_command", None) if run_lint else None
    gate = run_gate("compile", compile_cmd, fp, cfg)
    lint = run_gate("lint", lint_cmd, fp, cfg) if lint_cmd else None
    return compute_composite(structural, gate, lint)
