"""Target-existence search over a run's resolvable surface (Inc 2, FR-3).

The classifier (and, later, the rewrite lever) ask one authoritative question —
*does the module a violation intended exist on disk, and where?* — via the
``TargetExistenceSearch`` protocol. v1 ``DiskTargetSearch`` answers it by walking
the run's ``generated/`` tree first, then the project tree (excluding
``node_modules``), with **no dependency on Inc 3** (R1-S1).

The "intended module" match is a deterministic **token heuristic**: a candidate
module file matches a specifier when **every meaningful segment** of the specifier
(its path parts minus ``.``/``..``/``@``) appears as a path segment of the
candidate (case-insensitive). This resolves the run-012 #4 case
(``../../../types/wizard`` → ``components/wizard/types.ts``) where the basenames
differ but the segments ``{wizard, types}`` both appear in exactly one on-disk
module. This same predicate is shared by the classifier's ambiguity count and the
rewriter's resolvability (R3-F3).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Protocol, runtime_checkable

_MODULE_EXTS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_INDEX_STEMS = (
    "index.ts",
    "index.tsx",
    "index.js",
    "index.jsx",
    "index.mjs",
    "index.cjs",
)
_SKIP_DIRS = frozenset({"node_modules", ".git", ".next", "dist", "build"})


def specifier_tokens(specifier: str) -> List[str]:
    """Meaningful path segments of *specifier* (drop ``.``/``..``/``@`` and ext)."""
    # strip a trailing module extension if the specifier carried one
    spec = specifier
    for ext in _MODULE_EXTS:
        if spec.endswith(ext):
            spec = spec[: -len(ext)]
            break
    parts = re.split(r"[\\/]+", spec)
    return [p for p in parts if p and p not in (".", "..", "@")]


def resolve_relative_target(
    generated_root: Path, importer_rel: str, specifier: str
) -> Path:
    """The literal path *specifier* (relative or ``@/``) points to from an importer.

    Used to locate where a missing co-file/barrel should be created. No extension
    is appended (the caller knows the asset extension).
    """
    if specifier.startswith("@/"):
        return (generated_root / specifier[2:]).resolve(strict=False)
    importer_dir = (generated_root / importer_rel).parent
    return (importer_dir / specifier).resolve(strict=False)


@runtime_checkable
class TargetExistenceSearch(Protocol):
    """The authoritative 'does the intended module exist, and where' predicate."""

    @property
    def generated_root(self) -> Path:
        """The run's ``generated/`` surface root (for locating scaffold targets)."""
        ...

    def locations_for(self, specifier: str, importer_rel: str) -> List[Path]:
        """On-disk module files whose path contains all of *specifier*'s tokens."""
        ...

    def resolves_to_directory(
        self, specifier: str, importer_rel: str
    ) -> Optional[Path]:
        """The literal directory *specifier* points to, if it exists; else None."""
        ...

    def sibling_modules(self, directory: Path) -> List[Path]:
        """Non-index module files directly inside *directory*."""
        ...

    def has_index(self, directory: Path) -> bool:
        """True if *directory* already has a barrel ``index.*``."""
        ...


class DiskTargetSearch:
    """v1 ``TargetExistenceSearch``: walks generated-first, then project, on disk."""

    def __init__(self, generated_root: Path, project_root: Optional[Path] = None):
        self._generated_root = Path(generated_root)
        self._project_root = Path(project_root) if project_root is not None else None
        self._roots: List[Path] = [self._generated_root]
        if (
            self._project_root is not None
            and self._project_root != self._generated_root
        ):
            self._roots.append(self._project_root)
        self._module_cache: Optional[dict] = None  # root -> list[Path]

    @property
    def generated_root(self) -> Path:
        return self._generated_root

    # ── module enumeration ──────────────────────────────────────────────────

    def _modules_under(self, root: Path) -> List[Path]:
        if not root.is_dir():
            return []
        out: List[Path] = []
        for f in root.rglob("*"):
            if not f.is_file() or f.suffix not in _MODULE_EXTS:
                continue
            if _SKIP_DIRS & set(f.relative_to(root).parts):
                continue
            out.append(f)
        return out

    def _modules(self) -> dict:
        if self._module_cache is None:
            self._module_cache = {
                root: self._modules_under(root) for root in self._roots
            }
        return self._module_cache

    # ── protocol ────────────────────────────────────────────────────────────

    def locations_for(self, specifier: str, importer_rel: str) -> List[Path]:
        tokens = [t.lower() for t in specifier_tokens(specifier)]
        if not tokens:
            return []
        importer_name = Path(importer_rel).name.lower()
        # Generated first; only fall to the project tier if generated has no match.
        for root in self._roots:
            matches: List[Path] = []
            for f in self._modules().get(root, []):
                rel = f.relative_to(root)
                if rel.name.lower() == importer_name and str(rel).lower().endswith(
                    importer_rel.lower().lstrip("./")
                ):
                    continue  # never rewrite a file to itself
                segs = {p.lower() for p in rel.with_suffix("").parts}
                if all(tok in segs for tok in tokens):
                    matches.append(f)
            if matches:
                return matches
        return []

    def resolves_to_directory(
        self, specifier: str, importer_rel: str
    ) -> Optional[Path]:
        for base in self._candidate_dirs(specifier, importer_rel):
            if base.is_dir():
                return base
        return None

    def sibling_modules(self, directory: Path) -> List[Path]:
        if not directory.is_dir():
            return []
        return sorted(
            f
            for f in directory.iterdir()
            if f.is_file() and f.suffix in _MODULE_EXTS and f.name not in _INDEX_STEMS
        )

    def has_index(self, directory: Path) -> bool:
        return any((directory / stem).is_file() for stem in _INDEX_STEMS)

    # ── path resolution helpers ─────────────────────────────────────────────

    def _candidate_dirs(self, specifier: str, importer_rel: str) -> List[Path]:
        """Literal directories *specifier* could point at (relative or ``@/``-alias)."""
        out: List[Path] = []
        if specifier.startswith("."):
            importer_dir = (self._generated_root / importer_rel).parent
            out.append((importer_dir / specifier).resolve(strict=False))
        elif specifier.startswith("@/"):
            rest = specifier[2:]
            for root in self._roots:
                out.append((root / rest).resolve(strict=False))
                out.append((root / "src" / rest).resolve(strict=False))
        return out
