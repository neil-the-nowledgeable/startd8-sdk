"""Rewrite lever for rewritable-path violations (Inc 3, FR-4).

Resolves a violation's intended module via the shared ``TargetExistenceSearch``
predicate (sub-namespace collapse for RUN-013, token-match relocation for
RUN-012), selects a specifier form that resolves under the project's
``tsconfig``-blind resolver (R3-F2: prefer the ``@/`` alias, else a correct
relative path), and applies it with the **import-anchored** rewrite primitive
(``import_path_rename._rewrite_specifier`` — the post-bug-fix version that never
touches a matching token inside a string literal/comment, R4-S3).

Returns the applied ``{specifier → target}`` substitution (R3-S1) so the
re-validation/rollback step can replay the kept subset on a pre-image.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ...logging_config import get_logger
from ..steps.import_path_rename import _rewrite_specifier
from .models import RetryViolation
from .search import TargetExistenceSearch

logger = get_logger(__name__)


@dataclass(frozen=True)
class Rewrite:
    """One applied import-specifier substitution."""

    specifier: str  # the invented specifier that was replaced
    target_specifier: str  # the canonical specifier it now points at
    strategy: str  # how the target was resolved ("collapse" | "token_match")


def _alias_form(target: Path, generated_root: Path) -> Optional[str]:
    """``@/<rel-without-ext>`` for a target under *generated_root*, else None."""
    try:
        rel = target.resolve(strict=False).relative_to(
            generated_root.resolve(strict=False)
        )
    except ValueError:
        return None
    return "@/" + rel.with_suffix("").as_posix()


def _relative_form(
    target: Path, generated_root: Path, importer_rel: str
) -> Optional[str]:
    """A POSIX ``./``/``../`` specifier from the importer to *target* (no ext)."""
    importer_dir = (generated_root / importer_rel).resolve(strict=False).parent
    try:
        rel = os.path.relpath(
            target.resolve(strict=False).with_suffix(""), importer_dir
        )
    except ValueError:
        return None
    rel = Path(rel).as_posix()
    if not rel.startswith("."):
        rel = "./" + rel
    return rel


def compute_rewrite(
    violation: RetryViolation, search: TargetExistenceSearch
) -> Optional[Rewrite]:
    """Resolve *violation* to a canonical specifier form, or None if not rewritable."""
    resolved = search.resolve_target(violation.specifier, violation.file_path)
    if resolved.target is None:
        return None

    importer_rel = violation.file_path
    # R3-F2: pick the form that resolves under the blind resolver; alias first.
    alias = _alias_form(resolved.target, search.generated_root)
    if (
        alias
        and alias != violation.specifier
        and search.module_resolves(alias, importer_rel)
    ):
        return Rewrite(violation.specifier, alias, resolved.strategy)

    relative = _relative_form(resolved.target, search.generated_root, importer_rel)
    if (
        relative
        and relative != violation.specifier
        and search.module_resolves(relative, importer_rel)
    ):
        return Rewrite(violation.specifier, relative, resolved.strategy)

    # Neither form verified — abstain rather than emit an unresolvable specifier.
    logger.debug(
        "compute_rewrite: resolved target %s but no blind-resolvable form for %s",
        resolved.target,
        violation.specifier,
    )
    return None


def apply_rewrite(code: str, rewrite: Rewrite) -> "tuple[str, bool]":
    """Apply *rewrite* to *code* using the import-anchored primitive (R4-S3)."""
    return _rewrite_specifier(code, rewrite.specifier, rewrite.target_specifier)
