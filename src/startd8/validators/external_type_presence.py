"""Signature (f): external-type-presence (CKG Phase 1, REQ-CKG-610).

Catches RUN_009 #4/#11 — code that references a member an external package does NOT
export (e.g. ``Anthropic.ContentBlockParam`` when only ``TextBlockParam`` exists;
``import { defineConfig } from 'next'`` which `next` doesn't export).

**Strategy (a)** (OQ-1, resolved): we do NOT enumerate a package's full export set. We
read the **referenced** external members out of the generated source, then check each
against the set of external members the TS compiler actually **resolved** in the SCIP
index. A referenced member with no resolved occurrence for its package is a violation.

False-positive guard: a package is only judged when SCIP resolved *some* member of it
(``pkgs_with_members``). If a package produced zero resolved members (not installed /
not indexable), we cannot conclude membership and **skip it** — that case is the
strategy-(b) ``.d.ts``-indexing fallback, deliberately out of Phase 1 default. Relative
/ ``@/`` alias imports are not external and are ignored.

This check is standalone and SCIP-gated; Inc-4 wires it into the unified verifier
(`cross_file_verifier.py`) and plumbs the per-batch `ScipReader`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from startd8.code_observability.scip_reader import ScipReader

# import { A, B as C } from 'pkg'   /   export { A } from 'pkg'   (incl. `type`)
_NAMED_RE = re.compile(
    r"""(?:import|export)\s+(?:type\s+)?\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]""", re.MULTILINE
)
# import * as NS from 'pkg'
_NAMESPACE_RE = re.compile(r"""import\s+\*\s+as\s+(\w+)\s+from\s*['"]([^'"]+)['"]""")
# import Def from 'pkg'   (default; optionally followed by `, { ... }`)
_DEFAULT_RE = re.compile(
    r"""import\s+([A-Za-z_$][\w$]*)\s*(?:,\s*\{[^}]*\})?\s*from\s*['"]([^'"]+)['"]"""
)


@dataclass(frozen=True)
class ExternalTypeViolation:
    kind: str          # "external_type_unresolved"
    source_file: str
    specifier: str     # "<pkg>.<member>"
    detail: str
    severity: str      # "error"


def _is_external(module: str) -> bool:
    # Relative ("./", "../") and the project alias ("@/") are not external packages.
    return not module.startswith(".") and not module.startswith("@/")


def _pkg_of_module(module: str) -> str:
    """Top-level package for an import specifier ('next/server' -> 'next', '@scope/p/x' -> '@scope/p')."""
    parts = module.split("/")
    if module.startswith("@"):
        return "/".join(parts[:2])
    return parts[0]


def _leaf(descriptor: str) -> Optional[str]:
    """Terminal member identifier of a SCIP descriptor (…/ZodObject#extend(). -> 'extend')."""
    tail = descriptor.rsplit("/", 1)[-1]
    ids = re.findall(r"[A-Za-z_$][\w$]*", tail)
    return ids[-1] if ids else None


def _named_members(name_list: str) -> List[str]:
    """Exported names from a `{ A, B as C }` import/export clause (the left side of `as`)."""
    out: List[str] = []
    for raw in name_list.split(","):
        tok = raw.strip()
        if not tok:
            continue
        out.append(tok.split(" as ")[0].strip())
    return out


def _referenced_external_members(source: str) -> Set[Tuple[str, str]]:
    """(package, member) pairs referenced from external packages in one TS source."""
    refs: Set[Tuple[str, str]] = set()

    # Named / export-from clauses: each name is a referenced member of the package.
    for names, module in _NAMED_RE.findall(source):
        if not _is_external(module):
            continue
        pkg = _pkg_of_module(module)
        for member in _named_members(names):
            if member and member != "*":
                refs.add((pkg, member))

    # Default + namespace bindings -> alias.member accesses are referenced members.
    alias_to_pkg: Dict[str, str] = {}
    for alias, module in _NAMESPACE_RE.findall(source):
        if _is_external(module):
            alias_to_pkg[alias] = _pkg_of_module(module)
    for alias, module in _DEFAULT_RE.findall(source):
        # _DEFAULT_RE also matches `import * as X` ('*' is not \w, so safe) — but guard anyway.
        if alias != "as" and _is_external(module):
            alias_to_pkg.setdefault(alias, _pkg_of_module(module))
    for alias, pkg in alias_to_pkg.items():
        for member in re.findall(rf"(?<![\w.]){re.escape(alias)}\.([A-Za-z_$][\w$]*)", source):
            refs.add((pkg, member))

    return refs


def scan(sources: Dict[str, str], scip: Optional[ScipReader]) -> List[ExternalTypeViolation]:
    """Flag referenced external members that the TS compiler did not resolve (REQ-CKG-610).

    Returns ``[]`` when ``scip`` is None (advisory degrade — the surface gates on SCIP
    availability, REQ-CKG-230).
    """
    if scip is None:
        return []

    by_pkg = scip.external_symbols_by_package()
    pkgs_with_members: Set[str] = set(by_pkg)
    resolved: Set[Tuple[str, str]] = {
        (pkg, leaf)
        for pkg, descs in by_pkg.items()
        for leaf in (_leaf(d) for d in descs)
        if leaf is not None
    }

    violations: List[ExternalTypeViolation] = []
    for path, src in sources.items():
        if not path.endswith((".ts", ".tsx")):
            continue
        for pkg, member in sorted(_referenced_external_members(src)):
            if pkg not in pkgs_with_members:
                continue  # FP guard: package unresolved by SCIP -> strategy-(b) territory, skip
            if (pkg, member) in resolved:
                continue
            violations.append(
                ExternalTypeViolation(
                    kind="external_type_unresolved",
                    source_file=path,
                    specifier=f"{pkg}.{member}",
                    detail=(f"'{member}' is not an exported member of '{pkg}' that the TypeScript "
                            f"compiler could resolve (SCIP); likely a hallucinated SDK type/export."),
                    severity="error",
                )
            )
    return violations
