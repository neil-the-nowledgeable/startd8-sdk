"""Tolerant discovery over a generated app root (FR-0/1/2/3).

These are *pure*, process-free functions — the cheap M0 layer that the live stages (M1+) consume.
They never assume the canonical ``app/main.py`` + ``requirements.txt`` layout: with deterministic
generation OFF (the benchmark setting) the input is raw LLM output, so every probe degrades through
fallbacks and records non-conformance as a graded :class:`Deviation` instead of raising.

Reuses two existing primitives rather than reinventing them:
- :func:`startd8.validators.boot_smoke.resolve_app_target` — canonical entry-point fast path.
- :func:`startd8.backend_codegen.drift.embedded_mode` — the self-embedded ``# startd8-mode:`` header.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from startd8.logging_config import get_logger

from .ladder import (
    MODE_DEPLOYED,
    MODE_INSTALLED,
    MODE_UNKNOWN,
    Deviation,
    EntryPoint,
)

logger = get_logger("startd8.deploy_harness.discovery")

# The minimal runtime floor when an app ships no declared dependencies (FR-2). Load-bearing:
# deterministic OFF ⇒ raw LLM output may omit requirements.txt entirely.
DEP_FLOOR: Tuple[str, ...] = (
    "fastapi",
    "uvicorn[standard]",
    "sqlmodel",
    "jinja2",
    "python-multipart",
    "pydantic-settings",
)

# Bounded scan budget — never walk an unbounded tree of attacker-influenced files.
_SCAN_MAX_FILES = 200
_FASTAPI_CTOR_RE = re.compile(r"\bFastAPI\s*\(")
# A module-level ``app = ...`` or ``app: FastAPI`` binding (not indented → top level).
_APP_BINDING_RE = re.compile(
    r"(?m)^(?P<name>\w+)\s*(?::\s*FastAPI)?\s*=\s*FastAPI\s*\("
)


# --------------------------------------------------------------------------- entry point (FR-1)


def detect_entrypoint(root: Path) -> Tuple[EntryPoint, List[Deviation]]:
    """Detect the ASGI ``module:attr`` target, layered fast-path → candidates → bounded scan.

    Returns the :class:`EntryPoint` plus any deviations (e.g. non-canonical location, scan
    ambiguity). A ``target`` of ``None`` means nothing bootable was found.
    """
    deviations: List[Deviation] = []
    has_manifest = (root / "app.yaml").is_file() or (
        root / "prisma" / "app.yaml"
    ).is_file()

    # (a) canonical fast path — reuse boot_smoke (reads app.yaml package, else default "app",
    #     probing app/server.py then app/main.py).
    try:
        from startd8.validators.boot_smoke import resolve_app_target

        target = resolve_app_target(str(root))
    except Exception as exc:  # never let reuse failure crash discovery
        logger.debug("resolve_app_target failed on %s: %s", root, exc)
        target = None

    if target:
        matched_by = "manifest" if has_manifest else "app-package-default"
        if target != "app.main:app":
            deviations.append(
                Deviation(
                    code="entrypoint-noncanonical",
                    detail=f"resolved {target!r} (matched_by={matched_by})",
                )
            )
        return EntryPoint(target=target, matched_by=matched_by), deviations

    # (b) ordered candidates at the repo root (non-package layouts the canonical probe misses).
    for rel, attr in (("main.py", "app"), ("server.py", "app"), ("asgi.py", "app")):
        if (root / rel).is_file():
            module = rel[:-3]  # strip .py
            deviations.append(
                Deviation(code="entrypoint-noncanonical", detail=f"root-level {rel}")
            )
            return (
                EntryPoint(target=f"{module}:{attr}", matched_by="candidate"),
                deviations,
            )

    # (c) bounded scan for a module-level FastAPI() binding.
    ep, scan_devs = _scan_for_asgi_app(root)
    deviations.extend(scan_devs)
    if ep.target is None:
        deviations.append(
            Deviation(code="entrypoint-missing", detail="no ASGI app found")
        )
    return ep, deviations


def _scan_for_asgi_app(root: Path) -> Tuple[EntryPoint, List[Deviation]]:
    """Scan ≤``_SCAN_MAX_FILES`` ``.py`` files for a top-level ``<name> = FastAPI(...)`` binding."""
    deviations: List[Deviation] = []
    matches: List[Tuple[str, str]] = []  # (dotted_module, attr)
    seen = 0
    for path in sorted(root.rglob("*.py")):
        # skip venvs / hidden / migration noise to keep the budget meaningful
        parts = set(path.relative_to(root).parts)
        if parts & {".venv", "venv", "__pycache__", "alembic", "migrations", "tests"}:
            continue
        seen += 1
        if seen > _SCAN_MAX_FILES:
            deviations.append(
                Deviation(
                    code="entrypoint-scan-truncated",
                    detail=f"stopped after {_SCAN_MAX_FILES} files",
                )
            )
            break
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not _FASTAPI_CTOR_RE.search(text):
            continue
        m = _APP_BINDING_RE.search(text)
        if not m:
            continue
        module = ".".join(path.relative_to(root).with_suffix("").parts)
        matches.append((module, m.group("name")))

    if not matches:
        return EntryPoint(target=None, matched_by="none"), deviations
    if len(matches) > 1:
        deviations.append(
            Deviation(
                code="entrypoint-ambiguous",
                detail="multiple module-level FastAPI bindings: "
                + ", ".join(f"{mod}:{attr}" for mod, attr in matches),
            )
        )
    module, attr = matches[0]  # deterministic: sorted-path first
    return EntryPoint(target=f"{module}:{attr}", matched_by="scan"), deviations


# --------------------------------------------------------------------------- dependencies (FR-2)


class DepDetection:
    """Detected dependency set + provenance. Plain object — not serialized into LadderResult."""

    __slots__ = ("packages", "source", "pinned", "path")

    def __init__(
        self, packages: List[str], source: str, pinned: bool, path: Optional[Path]
    ):
        self.packages = packages
        self.source = source  # requirements.txt | pyproject:project | pyproject:poetry | dep_floor
        self.pinned = (
            pinned  # all requirements pinned (==/hash) → eligible for --require-hashes
        )
        self.path = path


def detect_deps(root: Path) -> Tuple[DepDetection, List[Deviation]]:
    """Prefer ``requirements.txt`` → ``pyproject.toml`` → dep floor (with a deviation)."""
    deviations: List[Deviation] = []

    req = root / "requirements.txt"
    if req.is_file():
        pkgs, pinned = _parse_requirements(
            req.read_text(encoding="utf-8", errors="replace")
        )
        if pkgs:
            return DepDetection(pkgs, "requirements.txt", pinned, req), deviations

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        pkgs, source = _parse_pyproject(
            pyproject.read_text(encoding="utf-8", errors="replace")
        )
        if pkgs:
            # pyproject deps are rarely fully hash-pinned; treat as unpinned.
            return DepDetection(pkgs, source, False, pyproject), deviations

    deviations.append(
        Deviation(
            code="deps-missing",
            detail="no requirements.txt or pyproject deps; using dep floor",
        )
    )
    return DepDetection(list(DEP_FLOOR), "dep_floor", False, None), deviations


def _parse_requirements(text: str) -> Tuple[List[str], bool]:
    pkgs: List[str] = []
    pinned = True
    any_req = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue  # skip comments, blank, and -r/-e/--flag includes
        any_req = True
        pkgs.append(line)
        if "==" not in line and "--hash" not in line:
            pinned = False
    return pkgs, (pinned and any_req)


def _parse_pyproject(text: str) -> Tuple[List[str], str]:
    """Extract dependencies from PEP 621 ``[project]`` or poetry ``[tool.poetry.dependencies]``."""
    data = _load_toml(text)
    if not data:
        return [], "pyproject:none"
    project = data.get("project") or {}
    deps = project.get("dependencies")
    if isinstance(deps, list) and deps:
        return [str(d) for d in deps], "pyproject:project"
    poetry = (((data.get("tool") or {}).get("poetry")) or {}).get("dependencies") or {}
    if isinstance(poetry, dict):
        names = [name for name in poetry if name.lower() != "python"]
        if names:
            return names, "pyproject:poetry"
    return [], "pyproject:none"


def _load_toml(text: str):
    try:
        import tomllib  # py3.11+

        return tomllib.loads(text)
    except ModuleNotFoundError:
        try:
            import tomli  # backport

            return tomli.loads(text)
        except Exception:
            return None
    except Exception:
        return None


# --------------------------------------------------------------------------- deployment mode (FR-3)


def detect_mode(
    root: Path, *, package: str = "app"
) -> Tuple[str, str, List[Deviation]]:
    """Return ``(mode, derivation, deviations)``.

    Crucial nuance from deployment-mode M0: **installed mode emits no ``settings.py``** (the
    byte-identical-when-absent property). So an *absent* ``settings.py`` legitimately means
    ``installed`` (derivation=``default``); a *present-but-headerless/garbled* one is genuinely
    ambiguous → ``unknown`` + deviation, never a silent ``installed`` (CRP R1-F8/S5), because a
    ``deployed`` app mis-booted as ``installed`` would hang on absent Postgres and the failure would
    be wrongly pinned on the model.
    """
    deviations: List[Deviation] = []
    settings = root.joinpath(*package.split("."), "settings.py")
    if not settings.is_file():
        return MODE_INSTALLED, "default", deviations

    try:
        from startd8.backend_codegen.drift import embedded_mode

        mode = embedded_mode(settings.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        logger.debug("embedded_mode failed on %s: %s", settings, exc)
        mode = None

    if mode in (MODE_INSTALLED, MODE_DEPLOYED):
        return mode, "header", deviations

    deviations.append(
        Deviation(
            code="mode-ambiguous",
            detail="settings.py present but no parseable '# startd8-mode:' header",
        )
    )
    return MODE_UNKNOWN, "ambiguous", deviations
