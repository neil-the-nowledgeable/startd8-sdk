"""FR-SAP-4 — the deterministic skeleton "pilot bore" (lead mechanism, $0-LLM).

Overlay ALL sibling skeletons together on top of the real project tree (correctness, not
just speed — requirements §0.9/§6.1), run the project toolchain once, and map intra-project
typecheck diagnostics to ``REFUTED`` *existence* findings. The bore is structurally blind to
conformance (a valid-but-wrong import typechecks clean) — that is the convention route's job
(``sapper.convention_route``).

Robustness (spike §0.6 + CRP R3/R4/R5):
- isolation: unique per-run temp dir, secrets/`.env`/VCS excluded, no symlink deref, guaranteed cleanup;
- non-Python skeletons filtered out (tagged unavailable);
- syntax-invalid skeleton → ``REFUTED`` (not a crashed stage);
- oversized skeleton / subprocess timeout → ``UNRESOLVED(bore_degraded)``;
- mypy absent → loud degradation (``bore_status='degraded'``), never a silent ``VALIDATED``.

Third-party "cannot find module" noise (which the spike silenced with
``--ignore-missing-imports``) is dropped here by *post-filtering*: a missing module is kept as a
genuine ``IMPORT_AVAILABILITY`` miss only when it is an **intra-project** package.
"""

from __future__ import annotations

import ast
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from startd8.logging_config import get_logger
from startd8.validators.python_toolchain import PyDiagnostic, run_project_check

from .models import (
    AssumptionKind,
    AssumptionVerdict,
    AvoidableCostStage,
    FrictionFinding,
    Severity,
    UnresolvedReason,
    ValidatorClass,
    avoidable_cost_stage,
    finding_fingerprint,
)

logger = get_logger(__name__)

DEFAULT_MAX_SKELETON_BYTES = 256_000
DEFAULT_TIMEOUT_S = 120

# Excluded from the overlay copy (secrets, VCS, caches, heavy/irrelevant build trees).
# Build-output dirs (.next/build/dist/target) added after a field test on a 1.8 GB repo (OQ-1).
_IGNORE = shutil.ignore_patterns(
    ".env", ".env.*", "*.env", ".git", ".hg", ".svn", "__pycache__", "*.pyc",
    ".venv", "venv", "node_modules", ".mypy_cache", ".pytest_cache", "*.key",
    "*.pem", "secrets", ".secrets", ".aws", ".ssh",
    ".next", "build", "dist", "*.egg-info", ".tox", "target",
)

# mypy/compileall diagnostic patterns.
_HAS_NO_ATTR = re.compile(r'has no attribute "([^"]+)"')
_MODULE_NAME = re.compile(r'Module "([^"]+)"')
_MAYBE = re.compile(r'maybe "([^"]+)"')
_CANNOT_FIND = re.compile(r'Cannot find implementation or library stub for module named "([^"]+)"')
_NAME_NOT_DEFINED = re.compile(r'Name "([^"]+)" is not defined')

_NOISE_CODES = {"import-untyped", "import-not-found", "import"}


@dataclass
class BoreResult:
    """Outcome of a pilot-bore run."""

    findings: List[FrictionFinding] = field(default_factory=list)
    bore_status: str = "checked"          # checked | degraded | unavailable
    notes: List[str] = field(default_factory=list)
    stages_run: Tuple[str, ...] = ()
    stages_skipped: Tuple[str, ...] = ()


def _local_packages(root: Optional[Path], skeleton_paths: List[str]) -> Set[str]:
    """Top-level package names that count as *intra-project* (vs third-party).

    With no project root, only the skeletons' own top-level segments are local — we must
    NOT scan the process cwd (it would mis-classify the SDK's own packages as project-local).
    """
    pkgs: Set[str] = set()
    if root is not None and root.is_dir():
        for child in root.iterdir():
            if child.is_dir() and (child / "__init__.py").exists():
                pkgs.add(child.name)
            elif child.is_dir() and any(child.glob("*.py")):
                pkgs.add(child.name)
            elif child.suffix == ".py":
                pkgs.add(child.stem)
    for p in skeleton_paths:
        first = Path(p).parts[0] if Path(p).parts else ""
        if first and first.endswith(".py"):
            pkgs.add(first[:-3])
        elif first:
            pkgs.add(first)
    return pkgs


def _is_local_module(module: str, local_packages: Set[str]) -> bool:
    return module.split(".", 1)[0] in local_packages


def _classify(
    diag: PyDiagnostic, local_packages: Set[str]
) -> Optional[Tuple[AssumptionKind, str, str, str, Optional[str]]]:
    """(kind, symbol, expected, found, suggested_fix) or None to drop as third-party noise."""
    msg = diag.message

    if diag.stage == "compileall":
        # Syntax error in a skeleton — the declared code isn't even parseable.
        return (AssumptionKind.DECOMPOSITION_INTEGRITY, "", "parseable element", diag.code, None)

    m = _HAS_NO_ATTR.search(msg)
    if m:
        symbol = m.group(1)
        mod = _MODULE_NAME.search(msg)
        module = mod.group(1) if mod else ""
        maybe = _MAYBE.search(msg)
        fix = f"use `{maybe.group(1)}`" if maybe else None
        # Module exists but the name doesn't → wrong module-source / invented entity.
        return (AssumptionKind.MODULE_SOURCE, symbol, f"{symbol} in {module}", "absent", fix)

    m = _CANNOT_FIND.search(msg)
    if m:
        module = m.group(1)
        if not _is_local_module(module, local_packages):
            return None  # third-party missing stub → noise (spike silenced via --ignore-missing-imports)
        return (AssumptionKind.IMPORT_AVAILABILITY, module, f"module {module}", "absent", None)

    if diag.code in _NOISE_CODES:
        return None

    m = _NAME_NOT_DEFINED.search(msg)
    if m:
        return (AssumptionKind.IMPORT_AVAILABILITY, m.group(1), f"name {m.group(1)}", "undefined", None)

    # Any other in-scope mypy error on a skeleton signature surface.
    return (AssumptionKind.INTERFACE_SIGNATURE, "", "type-consistent declaration", diag.code, None)


def _python_skeletons(skeleton_sources: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    py = {p: s for p, s in skeleton_sources.items() if p.endswith(".py")}
    non_py = sorted(p for p in skeleton_sources if not p.endswith(".py"))
    return py, non_py


def run_pilot_bore(
    skeleton_sources: Dict[str, str],
    project_root: Optional[str] = None,
    *,
    shared_files: Optional[Set[str]] = None,
    max_skeleton_bytes: int = DEFAULT_MAX_SKELETON_BYTES,
    timeout: int = DEFAULT_TIMEOUT_S,
) -> BoreResult:
    """Run the bore over all skeletons overlaid on the real project tree.

    ``skeleton_sources``: path → rendered skeleton text (imports+signatures, no bodies).
    ``project_root``: the real codebase the skeletons bore into (ground truth). When ``None``
    the bore sees only the skeletons + stdlib.
    """
    shared = shared_files or set()
    result = BoreResult()
    py_skeletons, non_py = _python_skeletons(skeleton_sources)
    if non_py:
        result.notes.append(f"bore unavailable for {len(non_py)} non-Python skeleton(s): {non_py}")

    if not py_skeletons:
        result.bore_status = "unavailable"
        result.notes.append("no Python skeletons to bore")
        return result

    root = Path(project_root) if project_root else None
    local_pkgs = _local_packages(root, list(py_skeletons))

    # --- pre-overlay per-skeleton guards: size + syntax ---
    valid: Dict[str, str] = {}
    for path, src in sorted(py_skeletons.items()):
        if len(src.encode("utf-8", "ignore")) > max_skeleton_bytes:
            result.findings.append(
                _degraded_finding(path, "skeleton exceeds size bound", shared)
            )
            continue
        try:
            ast.parse(src)
        except SyntaxError as exc:
            result.findings.append(
                _refuted_syntax_finding(path, exc, shared)
            )
            continue
        valid[path] = src

    if not valid:
        result.notes.append("no valid skeletons survived size/syntax guards")
        return result

    overlay = Path(tempfile.mkdtemp(prefix="sapper_bore_"))
    try:
        if root and root.is_dir():
            # symlinks=True copies links as links (no deref → no secret-target capture).
            shutil.copytree(root, overlay, symlinks=True, ignore=_IGNORE, dirs_exist_ok=True)
        for path, src in valid.items():
            dest = overlay / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(src, encoding="utf-8")

        try:
            check = run_project_check(str(overlay), run_mypy=True, run_pytest=False, timeout=timeout)
        except Exception as exc:  # defensive: never crash the preflight stage
            result.bore_status = "unavailable"
            result.notes.append(f"toolchain raised: {exc}")
            return result

        result.stages_run = check.stages_run
        result.stages_skipped = check.stages_skipped

        if check.status == "timeout":
            result.bore_status = "unavailable"
            result.notes.append("bore timed out → assumptions UNRESOLVED(bore_degraded)")
            for path in valid:
                result.findings.append(_degraded_finding(path, "bore timed out", shared))
            return result
        if check.status != "checked":
            result.bore_status = "unavailable"
            result.notes.append(f"bore unavailable (toolchain status={check.status})")
            return result

        if "mypy" in check.stages_skipped:
            # Loud degradation: only the compileall floor ran; cannot assert existence alignment.
            result.bore_status = "degraded"
            result.notes.append(
                "mypy unavailable — bore ran at syntax-only fidelity; existence assumptions UNRESOLVED"
            )

        skeleton_paths = set(valid)
        for diag in check.diagnostics:
            if not _in_scope(diag.file, skeleton_paths):
                continue
            classified = _classify(diag, local_pkgs)
            if classified is None:
                continue
            kind, symbol, expected, found, fix = classified
            rel = _normalize(diag.file, skeleton_paths)
            is_shared = rel in shared
            result.findings.append(
                FrictionFinding(
                    id=f"bore::{rel}:{diag.line}:{symbol or kind.value}",
                    kind=kind,
                    verdict=AssumptionVerdict.REFUTED,
                    severity=Severity.HIGH if is_shared else Severity.MEDIUM,
                    avoidable_cost_stage=avoidable_cost_stage(kind, shared_file=is_shared),
                    fingerprint=finding_fingerprint(kind, rel, symbol or str(diag.line)),
                    file=rel,
                    line=diag.line,
                    expected=expected,
                    found=found,
                    symbol=symbol,
                    suggested_fix=fix,
                    context_snippet=_snippet(valid.get(rel, ""), diag.line),
                    validator_class=ValidatorClass.PILOT_BORE,
                )
            )
        return result
    finally:
        shutil.rmtree(overlay, ignore_errors=True)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _in_scope(diag_file: str, skeleton_paths: Set[str]) -> bool:
    return _normalize(diag_file, skeleton_paths) in skeleton_paths


def _normalize(diag_file: str, skeleton_paths: Set[str]) -> str:
    """Map a (possibly overlay-absolute) diagnostic path to a skeleton-relative path."""
    df = diag_file.replace("\\", "/")
    for p in skeleton_paths:
        if df == p or df.endswith("/" + p):
            return p
    return df


def _snippet(src: str, line: int, ctx: int = 0) -> Optional[str]:
    if not src or line <= 0:
        return None
    lines = src.splitlines()
    if line > len(lines):
        return None
    lo, hi = max(0, line - 1 - ctx), min(len(lines), line + ctx)
    return "\n".join(lines[lo:hi]).strip() or None


def _degraded_finding(path: str, why: str, shared: Set[str]) -> FrictionFinding:
    is_shared = path in shared
    return FrictionFinding(
        id=f"bore::degraded::{path}",
        kind=AssumptionKind.DECOMPOSITION_INTEGRITY,
        verdict=AssumptionVerdict.UNRESOLVED,
        severity=Severity.MEDIUM,
        avoidable_cost_stage=avoidable_cost_stage(
            AssumptionKind.DECOMPOSITION_INTEGRITY, shared_file=is_shared
        ),
        fingerprint=finding_fingerprint(AssumptionKind.DECOMPOSITION_INTEGRITY, path, "bore"),
        file=path,
        reason=UnresolvedReason.BORE_DEGRADED,
        found=why,
        validator_class=ValidatorClass.PILOT_BORE,
    )


def _refuted_syntax_finding(path: str, exc: SyntaxError, shared: Set[str]) -> FrictionFinding:
    is_shared = path in shared
    return FrictionFinding(
        id=f"bore::syntax::{path}",
        kind=AssumptionKind.DECOMPOSITION_INTEGRITY,
        verdict=AssumptionVerdict.REFUTED,
        severity=Severity.HIGH if is_shared else Severity.MEDIUM,
        avoidable_cost_stage=avoidable_cost_stage(
            AssumptionKind.DECOMPOSITION_INTEGRITY, shared_file=is_shared
        ),
        fingerprint=finding_fingerprint(AssumptionKind.DECOMPOSITION_INTEGRITY, path, "syntax"),
        file=path,
        line=exc.lineno or 0,
        expected="parseable skeleton",
        found=f"SyntaxError: {exc.msg}",
        validator_class=ValidatorClass.PILOT_BORE,
    )
