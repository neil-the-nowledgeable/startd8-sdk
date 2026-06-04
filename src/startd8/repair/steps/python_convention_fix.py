"""Python convention safe-fix step (Phase B / FR-CAR-4, extended by FR-CAR-12).

Applies the **deterministically safe** house-style rewrites. Two rewrites with **different safe
scopes** (FR-CAR-12b reconciles them with the R1-F6 governed-scope guard):

1. **Module-source repoint** — ``from app.models import <Table>`` → ``from app.tables import
   <Table>`` (SQLModel tables live in ``app.tables``; ``app.models`` is Pydantic ``*Schema`` only).
   This is **unambiguous** — importing a table from the schemas module is wrong regardless of any
   dual-pattern usage — so it applies to **any generated app-package file**, including bespoke
   views (``app/jobs.py``). This closes RUN-038 #5: the ``safe_fixable=True`` ``module_source``
   diagnostic previously had **no implementing transform** here.
2. **Query→`session.get`** — ``<s>.query(<Model>).get(<id>)`` → ``<s>.get(<Model>, <id>)``. This
   *does* carry a dual-pattern false-rewrite risk (``app/ai/extract.py``), so it stays scoped to
   the generator-owned spine (``CANONICAL_LAYOUT``) per CRP R1-F6.

Wholesale-wrong code (a Flask app) is left untouched → it escalates via the unrepaired residual
(FR-CAR-6), not silenced.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import List, Optional, Tuple

from ..models import ElementContext, RepairContext, RepairStepResult

# `<s>.query(<Model>).get(<id>)` → `<s>.get(<Model>, <id>)`. The id arg excludes parens, so only
# simple identifiers/literals are rewritten (a nested call is left for escalation, never mis-fixed).
_QUERY_GET_RE = re.compile(r"\b(\w+)\.query\(\s*(\w+)\s*\)\.get\(\s*([^()]+?)\s*\)")

# Single-line `from <module> import <names>` (mirrors the detector's `_MODELS_IMPORT_RE`).
_FROM_IMPORT_RE = re.compile(r"^(\s*)from\s+([\w.]+)\s+import\s+(.+?)\s*$")


def _governed_scope() -> tuple[str, ...]:
    """Generator-owned spine relative-paths the *query-rewrite* is allowed to touch (R1-F6)."""
    from ...backend_codegen.crud_generator import CANONICAL_LAYOUT

    return tuple(v for v in CANONICAL_LAYOUT.values() if v.endswith(".py"))


def _is_governed(file_path: Path) -> bool:
    """Spine-only scope for the dual-pattern-risky query rewrite (R1-F6)."""
    p = str(file_path).replace("\\", "/")
    return any(p.endswith(rel) for rel in _governed_scope())


def _is_app_package_file(file_path: Path) -> bool:
    """Wider scope for the *unambiguous* module-source repoint (FR-CAR-12b).

    Any generated FastAPI app-package ``.py`` file — including bespoke routers (``app/jobs.py``)
    the spine guard excludes. Safe because the repoint only fires on an actual wrong-module table
    import, which is never a legitimate pattern. Excludes test files (their convention authority
    is the FR-CAR-12c prompt, not this fixer).
    """
    p = str(file_path).replace("\\", "/")
    if not p.endswith(".py"):
        return False
    parts = Path(p).parts
    if "tests" in parts or any(part.startswith("test_") for part in parts):
        return False
    return "app" in parts


def _imported_base(name: str) -> str:
    """The bound/source symbol of an import fragment: ``Foo as Bar`` → ``Foo``."""
    return name.split(" as ")[0].strip()


def _repoint_module_source(code: str, auth) -> Tuple[str, int]:
    """Move SQLModel table symbols off the schemas module onto the tables module.

    For ``from {schemas_module} import A, BSchema, C`` where A/C are tables (names not ending in
    ``Schema``/``Config``) and BSchema is a schema, emit:
        ``from {tables_module} import A, C``
        ``from {schemas_module} import BSchema``
    Mirrors the detector's offender rule (`repair/convention.py` `module_source`). Line-based, like
    the detector. Returns (new_code, repoint_count).
    """
    out_lines: List[str] = []
    n = 0
    for line in code.splitlines():
        m = _FROM_IMPORT_RE.match(line)
        if m and m.group(2) == auth.schemas_module:
            indent, names_str = m.group(1), m.group(3)
            names_part = names_str.split("#")[0].strip()
            paren = names_part.startswith("(") and names_part.endswith(")")
            if paren:
                names_part = names_part[1:-1].strip()
            names = [x.strip() for x in names_part.split(",") if x.strip()]
            tables = [
                x for x in names
                if _imported_base(x) != "*"
                and not _imported_base(x).endswith(("Schema", "Config"))
            ]
            schemas = [x for x in names if x not in tables]
            if tables:
                rewritten = f"{indent}from {auth.tables_module} import {', '.join(tables)}"
                if schemas:
                    rewritten += f"\n{indent}from {auth.schemas_module} import {', '.join(schemas)}"
                out_lines.append(rewritten)
                n += 1
                continue
        out_lines.append(line)
    if n == 0:
        return code, 0
    new_code = "\n".join(out_lines)
    if code.endswith("\n"):
        new_code += "\n"
    return new_code, n


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
        fixed = code
        fixes = 0
        rules: List[str] = []

        # (1) Module-source repoint — unambiguous, wider scope (FR-CAR-12b): generated app files.
        if _is_app_package_file(file_path):
            from ..convention import build_python_convention_authority

            auth = build_python_convention_authority()
            repointed, m = _repoint_module_source(fixed, auth)
            if m:
                fixed = repointed
                fixes += m
                rules.append("module_source_repoint")

        # (2) Query→session.get — dual-pattern risk, spine-only (R1-F6).
        if _is_governed(file_path):
            q, n = _QUERY_GET_RE.subn(r"\1.get(\2, \3)", fixed)
            if n and q != fixed:
                fixed = q
                fixes += n
                rules.append("query_get_to_session_get")

        in_scope = _is_app_package_file(file_path) or _is_governed(file_path)
        if fixes == 0 or fixed == code:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
                metrics={"in_scope": in_scope, "fixes": 0},
            )

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
            metrics={"in_scope": True, "fixes": fixes, "rules": rules},
        )


__all__ = ["PythonConventionFixStep"]
