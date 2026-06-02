"""Repair step: rewrite invented module-import paths (Inc 4, FR-6).

Consumes ``WrongImportPathDiagnostic``s and rewrites an unresolvable specifier to
its canonical on-disk path. Resolution order:

1. **Seeded negatives** (``@/lib/prisma → @/lib/db``, ``@/lib/ai/client →
   @/lib/ai/service``) — applied only when the canonical target resolves on disk.
2. **Sub-path collapse** (``@/lib/db/<x> → @/lib/db``) — only when the parent
   resolves (OQ-6: no speculative collapse).
3. **Nearest-match** against the resolvable-specifier set (catches typos).

Anything else abstains. The rewrite only touches the exact quoted specifier in
``import … from '…'`` / ``require('…')`` statements.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

from ...logging_config import get_logger
from ...validators.cross_file_imports import _resolves_on_disk
from ..models import (
    ElementContext,
    RepairContext,
    RepairStepResult,
    WrongImportPathDiagnostic,
)
from ..name_resolution import best_match
from ._name_repair_common import diagnostic_targets_file, resolve_truth_source

logger = get_logger(__name__)

# Import specifiers share a long `@/lib/` prefix, which inflates difflib ratios
# (an unrelated `@/lib/foo` vs `@/lib/bar` already scores ~0.5 from the prefix
# alone). A genuine path typo (`@/lib/loggr`→`@/lib/logger`) scores ~0.9, so the
# nearest-match bar for imports is set well above the field-rename default to
# avoid prefix-driven false rewrites (implementation finding, Inc 4).
_IMPORT_MATCH_CUTOFF = 0.8


class ImportPathRenameStep:
    """Rewrite invented/unresolvable import specifiers to their canonical path."""

    name: str = "import_path_rename"

    def __init__(self, truth_source=None):
        self._truth_source = truth_source

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        diags = [
            d
            for d in context.diagnostics
            if isinstance(d, WrongImportPathDiagnostic)
            and diagnostic_targets_file(d, file_path)
        ]
        if not diags:
            return RepairStepResult(
                self.name, False, code, {"rewrites": [], "abstains": []}
            )

        truth = resolve_truth_source(self._truth_source, context.project_root)
        negatives = truth.module_paths()
        resolvable = truth.resolvable_specifiers()
        root = str(context.project_root) if context.project_root is not None else "."

        modified = code
        rewrites: List[dict] = []
        abstains: List[dict] = []

        for d in diags:
            target = _resolve_specifier(d.specifier, negatives, resolvable, root)
            if target is None:
                abstains.append({"specifier": d.specifier, "reason": "no_candidates"})
                continue
            new_code, changed = _rewrite_specifier(modified, d.specifier, target)
            if changed:
                modified = new_code
                rewrites.append({"from": d.specifier, "to": target})
            else:
                abstains.append(
                    {"specifier": d.specifier, "reason": "not_found_in_source"}
                )

        if rewrites:
            logger.info(
                "import_path_rename: %d rewrite(s) in %s: %s",
                len(rewrites),
                file_path.name,
                "; ".join(f"{r['from']}->{r['to']}" for r in rewrites),
            )

        return RepairStepResult(
            self.name,
            modified != code,
            modified,
            {"rewrites": rewrites, "abstains": abstains},
        )


def _resolvable(spec: str, resolvable, root: str) -> bool:
    return spec in resolvable or _resolves_on_disk(spec, root, "")


def _resolve_specifier(spec: str, negatives, resolvable, root: str) -> Optional[str]:
    # 1. seeded negative → canonical (only if the canonical resolves)
    cand = negatives.get(spec)
    if cand and _resolvable(cand, resolvable, root):
        return cand

    # 2. sub-path collapse to a resolvable parent (no speculative collapse)
    if spec.startswith("@/") and spec.count("/") >= 2:
        parent = spec.rsplit("/", 1)[0]
        if parent.startswith("@/") and _resolvable(parent, resolvable, root):
            return parent

    # 3. nearest-match against the resolvable set (typo class) — stricter cutoff
    decision = best_match(spec, resolvable, cutoff=_IMPORT_MATCH_CUTOFF)
    if decision.is_rewrite:
        return decision.target
    return None


def _rewrite_specifier(code: str, spec: str, target: str) -> Tuple[str, bool]:
    """Replace the quoted *spec* with *target* — only in module-specifier positions.

    Anchored to ``from '…'`` / ``import '…'`` / ``require('…')`` / ``import('…')``
    so the same quoted token appearing in an unrelated string literal or comment
    is **not** rewritten (a global replace would corrupt it — non-destructive).
    """
    # pre-context that legitimately precedes a module specifier
    pattern = re.compile(
        r"(?P<pre>\bfrom\s+|\bimport\s+|\brequire\s*\(\s*|\bimport\s*\(\s*)"
        r"(?P<q>['\"`])" + re.escape(spec) + r"(?P=q)"
    )
    changed = False

    def _sub(m: "re.Match[str]") -> str:
        nonlocal changed
        changed = True
        return f"{m.group('pre')}{m.group('q')}{target}{m.group('q')}"

    out = pattern.sub(_sub, code)
    return out, changed
