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
  - missing DEPENDENCY  → degraded coverage (FR-J2/FR-C3): a single-file compile (Java `javac`,
    C# Roslyn `csc`) that fails only because legitimately-absent libraries (gRPC/protobuf stubs)
    can't be resolved in the no-network sandbox is NOT a model fault — degrade, don't floor. A
    *genuine* syntax error in the file still floors. Tier-2 (vendored deps) lifts these to real
    compiles; until then this distinction is what keeps Tier-1 honest.

Gates by language: Python `py_compile`, Go `gofmt -e`, Node `node --check` (.js), Java single-file
`javac`, C# offline Roslyn `csc` driven against the SDK's framework ref assemblies (no project /
no NuGet restore — `dotnet build` needs both and fails in the no-network sandbox, so we invoke csc
directly). Java/C# are Tier-1 (syntax + missing-dep classification); Tier-2 vendored deps deferred.

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
    # Java Tier-1 (FR-J1): single-file `javac` syntax/type check. `-proc:none` avoids needing
    # annotation processors on the classpath; output goes to the disposable sandbox workspace.
    # No classpath ⇒ gRPC/protobuf imports fail as "missing deps" and are *degraded* (FR-J2),
    # not floored — see classify_compile_failure(). Tier-2 adds `-cp <vendored bundle>`.
    "java": {
        ".java": ["javac", "-proc:none", "-d", ".", "{file}"],
    },
}

# javac / csc (and similar single-file compiles) report a legitimately-absent library the same
# way every time. In Tier-1 (no vendored deps) these are NOT model faults — classify them so the
# scorer degrades instead of flooring. Keyed by language_id -> failure-marker substrings.
# NOTE the Tier-1 trade-off (OQ-J3/OQ-C4): "cannot find symbol" / CS0246 can also be a real error,
# but without the deps present we cannot tell them apart, so we conservatively degrade rather than
# unfairly floor a model for absent gRPC stubs. Tier-2's real classpath removes the ambiguity.
_MISSING_DEP_MARKERS = {
    "java": ("does not exist", "cannot find symbol", "cannot access"),
    # C# (FR-C3): missing type/namespace/name resolution from absent assemblies.
    # CS0246 type-or-namespace-not-found, CS0234 namespace-missing-in-namespace, CS0103 name-not-found.
    "csharp": ("cs0246", "cs0234", "cs0103"),
}

# Genuine in-file syntax errors. When present, the failure is the model's fault even if a
# missing-dep marker also appears — so we floor, never degrade. C# separates these cleanly:
# CS1xxx are parser/syntax diagnostics, CS0xxx are semantic/binding (incl. missing deps).
_SYNTAX_ERROR_MARKERS = {
    "csharp": ("error cs1",),
}


def fallback_syntax_command(profile, file_path) -> Optional[List[str]]:
    """A sandbox-safe single-file syntax command when the profile has none (e.g. Node .js,
    Java javac, or C# Roslyn csc). Returns None when no offline single-file check applies or
    its toolchain can't be located (caller then degrades, FR-32)."""
    lang = getattr(profile, "language_id", "") or ""
    ext = Path(file_path).suffix.lower()
    if lang == "csharp" and ext == ".cs":
        return _csharp_csc_command()
    return _FALLBACK_SYNTAX_COMMANDS.get(lang, {}).get(ext)


def classify_compile_failure(language_id: Optional[str], output: str) -> Optional[str]:
    """Classify a *failed* single-file compile (FR-J2/FR-C3). Returns ``"missing_deps"`` when the
    failure is attributable to absent dependencies (so the caller degrades instead of flooring),
    else ``None`` (treat as a genuine compile failure). A genuine in-file syntax error always wins
    (returns None) even if a missing-dep marker is also present."""
    lang = language_id or ""
    low = (output or "").lower()
    syntax_markers = _SYNTAX_ERROR_MARKERS.get(lang, ())
    if any(m in low for m in syntax_markers):
        return None  # real syntax error in the file — floor, don't degrade
    markers = _MISSING_DEP_MARKERS.get(lang)
    if not markers:
        return None
    return "missing_deps" if any(m in low for m in markers) else None


def _csharp_csc_command() -> Optional[List[str]]:
    """Build an offline single-file Roslyn (csc) syntax/type check (FR-C1), driving the csc.dll +
    framework reference assemblies that ship inside an installed .NET SDK — no project, no NuGet
    restore, no network (unlike `dotnet build`, which needs a .csproj + restore and fails in the
    no-network sandbox). gRPC/protobuf `using`s resolve to CS0246 (→ missing-deps degrade);
    in-file syntax errors are CS1xxx (→ floor). Returns None if no SDK is found (→ degraded, FR-C8).
    """
    found = _discover_dotnet_csc()
    if found is None:
        return None
    csc, refs = found
    return [
        "dotnet", csc, "-nologo", "-nostdlib", "-t:library", "-out:/dev/null",
        *(f"-r:{r}" for r in refs), "{file}",
    ]


def _discover_dotnet_csc():
    """Locate (csc.dll, [framework ref-assembly dlls]) from an installed .NET SDK, for an offline
    single-file check. Searches DOTNET_ROOT, the resolved `dotnet` location, and common install
    dirs. Returns None when no SDK + ref pack pair is found."""
    import glob
    import os
    import shutil

    roots: List[str] = []
    if os.environ.get("DOTNET_ROOT"):
        roots.append(os.environ["DOTNET_ROOT"])
    dn = shutil.which("dotnet")
    if dn:
        roots.append(os.path.dirname(os.path.realpath(dn)))
    roots += ["/usr/local/share/dotnet", "/usr/share/dotnet",
              os.path.expanduser("~/.dotnet")]

    for root in roots:
        cscs = sorted(glob.glob(os.path.join(root, "sdk", "*", "Roslyn", "bincore", "csc.dll")))
        ref_dirs = sorted(glob.glob(
            os.path.join(root, "packs", "Microsoft.NETCore.App.Ref", "*", "ref", "net*")))
        if cscs and ref_dirs:
            refs = sorted(glob.glob(os.path.join(ref_dirs[-1], "*.dll")))
            if refs:
                return cscs[-1], refs
    return None


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
        compile_ok = None  # FR-32/FR-J2: degraded — don't penalize for missing toolchain/deps

    compile_missing_reason = "" if compile_gate.available else (compile_gate.detail or "")
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
        if compile_missing_reason:
            note = f"{note}; {compile_missing_reason[:120]}"
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
    # FR-J2: a compile that failed only on absent dependencies (no classpath in Tier-1) is not a
    # model fault — re-flavor it as degraded (compile_ok=None) so compute_composite won't floor it.
    if gate.available and gate.passed is False and not gate.sandbox_violation:
        lang = getattr(profile, "language_id", "") or ""
        if classify_compile_failure(lang, gate.detail) == "missing_deps":
            gate = GateResult(
                name=gate.name, available=False, passed=None,
                detail=f"missing deps — Tier-1 degraded (FR-J2): {gate.detail[:160]}",
                isolation_level=gate.isolation_level,
            )
    lint = run_gate("lint", lint_cmd, fp, cfg) if lint_cmd else None
    return compute_composite(structural, gate, lint)
