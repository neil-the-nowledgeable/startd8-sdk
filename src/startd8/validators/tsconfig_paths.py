"""tsconfig path-alias target existence (CKG Phase 1, REQ-CKG-630).

Catches RUN_009 #5 — a `compilerOptions.paths` alias pointing at a directory/file that
does not exist (e.g. ``"@/*": ["./src/*"]`` in a project with no ``src/``).

This is **real tsconfig parsing**, not a heuristic: it reads ``tsconfig.json`` (JSONC),
follows ``extends`` chains, merges ``compilerOptions`` (child wins), and resolves each
``paths`` target against ``baseUrl``. It validates the *alias definition* — `@/`-import
resolution stays with the existing unresolvable-import signature.

Toolchain-free (no Node, no SCIP). Known simplification: ``baseUrl``/``paths`` are
resolved relative to the scanned tsconfig dir, not (TS 5.x) the file that *defines* them
— adequate for single-file and simple `extends` setups; revisit if multi-package
monorepo configs need it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set

from startd8.logging_config import get_logger
from startd8.utils.jsonc import loads_jsonc

logger = get_logger(__name__)

# Extensions/index forms a non-wildcard alias target may resolve to.
_EXTS = (".ts", ".tsx", ".d.ts", ".js", ".jsx", ".json")
_INDEX = ("index.ts", "index.tsx", "index.d.ts", "index.js")


@dataclass(frozen=True)
class TsconfigAliasViolation:
    kind: str          # "tsconfig_alias_unresolved"
    source_file: str   # the tsconfig path
    specifier: str     # the alias pattern, e.g. "@/*"
    detail: str
    severity: str      # "error"


def _load_jsonc(path: Path) -> Dict[str, Any]:
    obj = loads_jsonc(path.read_text(encoding="utf-8", errors="replace"))
    return obj if isinstance(obj, dict) else {}


def _merged_compiler_options(path: Path, seen: Set[Path]) -> Dict[str, Any]:
    """compilerOptions merged across the `extends` chain (parents first, child overrides)."""
    try:
        cfg = _load_jsonc(path)
    except (OSError, json.JSONDecodeError, ValueError):
        logger.warning("tsconfig: %s is not parseable — skipping", path)
        return {}
    merged: Dict[str, Any] = {}
    ext = cfg.get("extends")
    parents = [ext] if isinstance(ext, str) else (ext or [])
    for pe in parents:
        if not isinstance(pe, str) or not (pe.startswith(".") or pe.startswith("/")):
            continue  # bare package extends (e.g. @tsconfig/next) — not on local disk; skip
        ppath = (path.parent / pe).resolve()
        if not ppath.suffix:
            ppath = ppath.with_suffix(".json")
        if ppath.is_file() and ppath not in seen:
            seen.add(ppath)
            merged.update(_merged_compiler_options(ppath, seen))
    co = cfg.get("compilerOptions") or {}
    if isinstance(co, dict):
        merged.update(co)
    return merged


def _target_exists(base_dir: Path, target: str) -> bool:
    t = target.replace("\\", "/")
    if "*" in t:
        # Wildcard: the directory portion before the first '*' must exist.
        prefix = t.split("*", 1)[0].rstrip("/")
        cand = (base_dir / prefix) if prefix not in ("", ".") else base_dir
        return cand.exists()
    p = base_dir / t
    if p.exists():
        return True
    if any((base_dir / (t + ext)).exists() for ext in _EXTS):
        return True
    return any((p / idx).exists() for idx in _INDEX)


def scan(project_root: str | Path, *, tsconfig_name: str = "tsconfig.json") -> List[TsconfigAliasViolation]:
    """Flag tsconfig `paths` aliases whose targets do not exist on disk (REQ-CKG-630).

    Returns ``[]`` (no error) when there is no tsconfig or no `paths`. Never raises.
    """
    root = Path(project_root)
    tsconfig = root / tsconfig_name
    if not tsconfig.is_file():
        return []

    co = _merged_compiler_options(tsconfig, seen={tsconfig.resolve()})
    paths = co.get("paths")
    if not isinstance(paths, dict) or not paths:
        return []
    base_url = co.get("baseUrl") if isinstance(co.get("baseUrl"), str) else "."
    base_dir = (root / base_url).resolve()

    violations: List[TsconfigAliasViolation] = []
    for alias, targets in paths.items():
        if not isinstance(targets, list) or not targets:
            continue
        # An alias is broken only if NONE of its targets resolve (TS tries them in order).
        if any(_target_exists(base_dir, t) for t in targets if isinstance(t, str)):
            continue
        violations.append(
            TsconfigAliasViolation(
                kind="tsconfig_alias_unresolved",
                source_file=str(tsconfig.relative_to(root)) if tsconfig.is_relative_to(root) else str(tsconfig),
                specifier=alias,
                detail=(f"tsconfig path alias '{alias}' -> {targets} resolves to no existing "
                        f"file/directory under baseUrl '{base_url}'."),
                severity="error",
            )
        )
    return violations
