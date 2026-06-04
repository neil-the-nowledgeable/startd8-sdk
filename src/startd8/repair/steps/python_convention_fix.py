"""Python convention safe-fix step (Phase B / FR-CAR-4).

Applies the **deterministically safe** house-style rewrites only, and **only within the authority's
governed scope** (generator-owned spine artifacts per ``CANONICAL_LAYOUT``). Hand-written integration
files (``app/ai/*``) and bespoke views (``app/jobs.py``) are **out of scope → detect-and-advise, never
auto-fixed** (CRP R1-F6): revert-on-break catches *breakage*, not a *false* rewrite of a legitimately
dual-pattern file (e.g. ``app/ai/extract.py`` that uses both ``session.query`` and ``select``).

Safe rewrite implemented here:
- ``<s>.query(<Model>).get(<id>)`` → ``<s>.get(<Model>, <id>)`` (single-symbol, AST-local, revert-on-break).

Wholesale-wrong code (a Flask app, a ``session.query(...).all()`` with no single-symbol rewrite) is left
untouched → it escalates via the unrepaired residual (FR-CAR-6), not silenced.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult

# `<s>.query(<Model>).get(<id>)` → `<s>.get(<Model>, <id>)`
_QUERY_GET_RE = re.compile(r"\b(\w+)\.query\(\s*(\w+)\s*\)\.get\(\s*([^())]+?)\s*\)")


def _governed_scope() -> tuple[str, ...]:
    """Generator-owned artifact relative-paths the safe-fixer is allowed to rewrite."""
    from ...backend_codegen.crud_generator import CANONICAL_LAYOUT

    return tuple(v for v in CANONICAL_LAYOUT.values() if v.endswith(".py"))


def _is_governed(file_path: Path) -> bool:
    p = str(file_path).replace("\\", "/")
    return any(p.endswith(rel) for rel in _governed_scope())


class PythonConventionFixStep:
    """Deterministic, scope-guarded safe-fixer for Python house-style violations."""

    name: str = "python_convention_fix"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        # Authority-governed-scope guard (R1-F6): never auto-fix a non-generator-owned file.
        if not _is_governed(file_path):
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
                metrics={"in_scope": False, "reason": "out_of_governed_scope"},
            )

        fixed, n = _QUERY_GET_RE.subn(r"\1.get(\2, \3)", code)
        if n == 0 or fixed == code:
            return RepairStepResult(step_name=self.name, modified=False, code=code, metrics={"fixes": 0})

        # Revert-on-break: the rewrite must keep the file parseable.
        try:
            ast.parse(fixed)
        except SyntaxError:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
                metrics={"fixes": 0, "reverted": True},
            )

        return RepairStepResult(
            step_name=self.name, modified=True, code=fixed,
            metrics={"in_scope": True, "fixes": n, "rule": "query_get_to_session_get"},
        )


__all__ = ["PythonConventionFixStep"]
