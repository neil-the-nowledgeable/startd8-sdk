"""Deterministic violation classifier (Inc 2, FR-3).

Routes each ``RetryViolation`` to exactly one repair class via the
``TargetExistenceSearch`` predicate (Inc 2 — **no Inc 3 dependency**, R1-S1):

* **rewritable-path** — the intended module exists at exactly one location; the
  rewrite lever (FR-4) will point the import there. **>1 location → ambiguous →
  needs-regen** (never a guessed rewrite, R1-F4).
* **scaffoldable-barrel** — the specifier resolves to an existing directory with
  sibling modules but no ``index.*`` (FR-6).
* **scaffoldable-cofile** — a style/asset specifier whose file is missing (FR-5).
* **needs-regen** — unparseable, absent, or ambiguous.

A style/asset specifier is classified ``scaffoldable-cofile`` by **extension**,
so it never mis-classifies as a module rewrite even if a stray same-named file
exists elsewhere (FR-3 precedence note).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from .models import RetryViolation
from .search import TargetExistenceSearch, resolve_relative_target

# Style/asset extensions a missing co-file can be scaffolded for (FR-5).
_STYLE_ASSET_EXTS = (".css", ".scss", ".sass", ".less")


class RetryClass(str, Enum):
    REWRITABLE_PATH = "rewritable_path"
    SCAFFOLDABLE_COFILE = "scaffoldable_cofile"
    SCAFFOLDABLE_BARREL = "scaffoldable_barrel"
    NEEDS_REGEN = "needs_regen"


@dataclass(frozen=True)
class ClassifyResult:
    """Classification outcome with the resolved target and (for residue) a reason."""

    retry_class: RetryClass
    target: Optional[Path] = (
        None  # rewritable: the module; barrel: the dir; cofile: path to create
    )
    reason: str = (
        ""  # needs_regen only: unparseable_message | absent | ambiguous_target
    )
    candidates: tuple = field(default_factory=tuple)  # >1 locations, for debugging


def _is_style_asset(specifier: str) -> bool:
    return any(specifier.endswith(ext) for ext in _STYLE_ASSET_EXTS)


def classify(
    violation: RetryViolation, search: TargetExistenceSearch
) -> ClassifyResult:
    """Classify one violation against the on-disk resolvable surface."""
    if not violation.parse_ok or not violation.specifier:
        return ClassifyResult(RetryClass.NEEDS_REGEN, reason="unparseable_message")

    spec = violation.specifier
    importer_rel = violation.file_path

    # 1. Style/asset co-file — authoritative by extension (FR-5).
    if _is_style_asset(spec):
        target = resolve_relative_target(search.generated_root, importer_rel, spec)
        return ClassifyResult(RetryClass.SCAFFOLDABLE_COFILE, target=target)

    # 2. Barrel — the specifier points at an existing dir with siblings, no index (FR-6).
    directory = search.resolves_to_directory(spec, importer_rel)
    if (
        directory is not None
        and search.sibling_modules(directory)
        and not search.has_index(directory)
    ):
        return ClassifyResult(RetryClass.SCAFFOLDABLE_BARREL, target=directory)

    # 3. Rewritable — the intended module resolves at exactly one location, via
    #    the shared predicate (collapse for sub-namespace invention, else
    #    token-match). >1 ⇒ ambiguous → needs-regen (R1-F4). (FR-4)
    resolved = search.resolve_target(spec, importer_rel)
    if resolved.target is not None:
        return ClassifyResult(RetryClass.REWRITABLE_PATH, target=resolved.target)
    if resolved.strategy == "ambiguous":
        return ClassifyResult(
            RetryClass.NEEDS_REGEN,
            reason="ambiguous_target",
            candidates=resolved.candidates,
        )

    # 4. No target anywhere.
    return ClassifyResult(RetryClass.NEEDS_REGEN, reason="absent")
