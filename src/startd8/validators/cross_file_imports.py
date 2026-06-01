"""Toolchain-free unresolvable-import detector — RUN-009 Fix 3 (re-scoped).

The RUN-008 `tsc` gate (`ts_toolchain`, FR-4) catches unresolvable `@/` imports
only when the Node toolchain is **provisioned**. RUN-009 wiped its own
foundation (no `node_modules` / `tsconfig.json` / `package.json`), so that gate
could not run — and the pipeline reported PASS on **7 unresolvable imports**
(5× invented `@/lib/prisma`, 1× `@/lib/logger`, 1× wiped `@/lib/db`).

This is the complementary check the RUN-009 postmortem (Fix 3) calls for: a
pure-Python, **toolchain-free** resolver that flags `@/`-aliased and relative
imports resolving to neither the generated batch nor an on-disk project file.
It fires regardless of provisioning, so it catches the failure class even on a
self-wiped run. Bare package imports (`pino`, `next`, `react`) are out of scope
here — that is the (separate) missing-dependency signature, which needs a
`package.json`.

Reuses the import-resolution utilities already built for FR-1 cross-feature
inheritance (`contractors.upstream_interface`) — same parsing, opposite use.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

_TS_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
# Suffixes/index forms a bare specifier may resolve to on disk.
_RESOLVE_FORMS = (
    "", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".d.ts",
    "/index.ts", "/index.tsx", "/index.js", "/index.jsx",
)


@dataclass(frozen=True)
class ImportViolation:
    """Shape-compatible with the postmortem's cross-file attribution loop."""

    kind: str  # "unresolvable_import"
    source_file: str
    specifier: str
    detail: str
    severity: str = "error"


def _resolves_on_disk(
    specifier: str, project_root: str, importer_path: str,
    *, alias_bases=("", "src"),
) -> bool:
    """True if a relative or ``@/``-aliased specifier resolves to an on-disk file.

    Without a `tsconfig` (often wiped), `@/` is resolved against both the project
    root and `src/` — the two conventional Next.js layouts.
    """
    root = Path(project_root)
    bases: List[Path] = []
    if specifier.startswith("."):
        importer_dir = (root / importer_path).parent if importer_path else root
        bases.append((importer_dir / specifier))
    elif specifier.startswith("@/"):
        rest = specifier[2:]
        for ab in alias_bases:
            bases.append((root / ab / rest) if ab else (root / rest))
    else:
        return True  # bare package import — not handled here
    for b in bases:
        try:
            stem = b.resolve(strict=False)
        except (OSError, RuntimeError):
            stem = b
        for form in _RESOLVE_FORMS:
            if Path(str(stem) + form).is_file():
                return True
    return False


def scan_unresolvable_imports(
    sources: Dict[str, str], project_root: str,
) -> List[ImportViolation]:
    """Flag `@/`-aliased / relative imports that resolve to nothing.

    *sources* is the ``{path: content}`` map of the generated batch (the same one
    the postmortem already builds). An import resolves if it matches a file in
    the generated batch (by stem) OR an on-disk project file; otherwise it is an
    ``unresolvable_import`` violation attributed to the importing file.
    """
    from ..contractors.upstream_interface import (
        extract_import_specifiers,
        resolve_specifier_to_paths,
    )

    gen_paths = [p for p in sources if p.endswith(_TS_EXTS)]
    out: List[ImportViolation] = []
    for path, content in sources.items():
        if not path.endswith(_TS_EXTS):
            continue
        seen: set[str] = set()
        for spec in extract_import_specifiers(content):
            if spec in seen:
                continue
            seen.add(spec)
            if not (spec.startswith("@/") or spec.startswith(".")):
                continue  # bare package import — separate missing-dependency signature
            # Resolve against the generated batch (by stem) first, then on disk.
            if resolve_specifier_to_paths(spec, gen_paths, importer_path=path):
                continue
            if _resolves_on_disk(spec, project_root, path):
                continue
            out.append(ImportViolation(
                kind="unresolvable_import",
                source_file=path,
                specifier=spec,
                detail=(f"`{path}` imports `{spec}` which resolves to neither the "
                        f"generated batch nor an on-disk project file"),
            ))
    return out
