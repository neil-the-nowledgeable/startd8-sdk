"""Duplicate import removal repair step (REQ-RPL-104).

Removes semantically duplicate imports — imports that bind the same
Python name into scope — keeping the first occurrence.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional

from ...logging_config import get_logger
from ..models import ElementContext, RepairContext, RepairStepResult

logger = get_logger(__name__)


class DuplicateRemovalStep:
    """Remove duplicate imports that bind the same Python name."""

    name: str = "duplicate_removal"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        lines = code.splitlines(keepends=True)
        removals: set[int] = set()
        rewrites: dict[int, str] = {}

        seen: dict[str, ast.stmt] = {}
        imports_removed = 0

        for node in tree.body:
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue

            # __future__ imports are compiler directives — skip entirely,
            # and don't register their names (so regular imports aren't blocked).
            if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                continue

            bound_names = _compute_bound_names_ast(node)
            dup_names: list[str] = []
            new_names: list[str] = []

            for bname, _alias in bound_names:
                if bname in seen:
                    dup_names.append(bname)
                else:
                    new_names.append(bname)
                    seen[bname] = node

            if not dup_names:
                continue

            # end_lineno can technically be None on some AST implementations
            end_lineno = node.end_lineno or node.lineno

            if not new_names:
                # All names are duplicates — remove entire node
                for ln in range(node.lineno - 1, end_lineno):
                    removals.add(ln)
                imports_removed += len(dup_names)
            else:
                # Partial removal — only for ImportFrom with multiple names
                if isinstance(node, ast.ImportFrom):
                    new_name_set = set(new_names)
                    kept_aliases = [
                        a for a in node.names
                        if (a.asname or a.name) in new_name_set
                    ]
                    if kept_aliases:
                        alias_strs = []
                        for a in kept_aliases:
                            if a.asname:
                                alias_strs.append(f"{a.name} as {a.asname}")
                            else:
                                alias_strs.append(a.name)
                        orig_line = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                        indent = orig_line[: len(orig_line) - len(orig_line.lstrip())]
                        new_line = f"{indent}from {node.module} import {', '.join(alias_strs)}\n"
                        for ln in range(node.lineno - 1, end_lineno):
                            removals.add(ln)
                        rewrites[node.lineno - 1] = new_line
                        imports_removed += len(dup_names)

        if imports_removed == 0:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        new_lines: list[str] = []
        for i, line in enumerate(lines):
            if i in rewrites:
                new_lines.append(rewrites[i])
            elif i not in removals:
                new_lines.append(line)

        result_code = "".join(new_lines)
        # Collapse runs of 3+ blank lines down to 2
        result_code = re.sub(r"\n{3,}", "\n\n", result_code)

        logger.debug("Removed %d duplicate import(s) from %s", imports_removed, file_path)

        return RepairStepResult(
            step_name=self.name,
            modified=True,
            code=result_code,
            metrics={"imports_removed": imports_removed},
        )


def _compute_bound_names_ast(
    node: ast.Import | ast.ImportFrom,
) -> list[tuple[str, ast.alias]]:
    """Compute (bound_name, alias_node) pairs for an import AST node.

    For bare imports, ``import X.Y.Z`` binds only ``X`` into scope
    (the top-level package name), unless an alias is used.
    """
    results: list[tuple[str, ast.alias]] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.asname:
                results.append((alias.asname, alias))
            else:
                # `import X.Y.Z` binds `X` into the local namespace
                results.append((alias.name.split(".")[0], alias))
    elif isinstance(node, ast.ImportFrom):
        for alias in node.names:
            bound = alias.asname or alias.name
            results.append((bound, alias))
    return results
