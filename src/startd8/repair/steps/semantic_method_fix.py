"""Semantic method repair step (Kaizen run-042 P1).

Fixes semantic defects that pass AST validation but fail at runtime:

1. Missing ``self``/``cls`` parameter on methods (email_server.py Grade D)
2. ``datetime.utcfromtimestamp`` → ``datetime.datetime.utcfromtimestamp``
   (logger.py Grade B- — common Ollama confusion pattern)
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional

from ...logging_config import get_logger
from ..models import ElementContext, RepairContext, RepairStepResult

logger = get_logger(__name__)

# Pattern: datetime.<method> where datetime is the module, not the class.
# Matches datetime.utcfromtimestamp, datetime.utcnow, datetime.fromtimestamp, etc.
_DATETIME_CLASS_METHODS = {
    "utcfromtimestamp",
    "fromtimestamp",
    "utcnow",
    "now",
    "combine",
    "fromisoformat",
    "fromordinal",
    "strptime",
    "today",
    "fromisocalendar",
}

_DATETIME_METHOD_RE = re.compile(
    r"\bdatetime\.(" + "|".join(_DATETIME_CLASS_METHODS) + r")\b"
)


class SemanticMethodFixStep:
    """Fix semantic method and module-resolution defects."""

    name: str = "semantic_method_fix"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        modified_code = code
        fixes: list[str] = []

        # Fix 1: Insert missing self/cls on methods.
        modified_code, self_fixes = _fix_missing_self(
            modified_code, element_context,
        )
        fixes.extend(self_fixes)

        # Fix 2: datetime module/class disambiguation.
        modified_code, dt_fixes = _fix_datetime_confusion(modified_code)
        fixes.extend(dt_fixes)

        modified = modified_code != code
        if modified:
            logger.info(
                "semantic_method_fix applied %d fix(es) to %s: %s",
                len(fixes), file_path.name, "; ".join(fixes),
            )

        return RepairStepResult(
            step_name=self.name,
            modified=modified,
            code=modified_code,
            metrics={"fixes": fixes},
        )


def _fix_missing_self(
    code: str,
    element_context: Optional[ElementContext],
) -> tuple[str, list[str]]:
    """Insert ``self`` as first parameter on methods that lack it.

    Only runs when element_context indicates we're repairing a method
    (parent_class is set).
    """
    if element_context is None or not element_context.parent_class:
        return code, []

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code, []

    fixes: list[str] = []
    lines = code.splitlines(keepends=True)

    # Walk in reverse line order so insertions don't shift later line numbers.
    targets: list[tuple[int, str, str]] = []  # (line_idx, func_name, expected_param)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # Determine expected first param.
        is_staticmethod = any(
            (isinstance(d, ast.Name) and d.id == "staticmethod")
            or (isinstance(d, ast.Attribute) and d.attr == "staticmethod")
            for d in node.decorator_list
        )
        if is_staticmethod:
            continue

        is_classmethod = any(
            (isinstance(d, ast.Name) and d.id == "classmethod")
            or (isinstance(d, ast.Attribute) and d.attr == "classmethod")
            for d in node.decorator_list
        )
        expected = "cls" if is_classmethod else "self"
        first_arg = node.args.args[0].arg if node.args.args else None

        if first_arg != expected:
            targets.append((node.lineno - 1, node.name, expected))

    # Apply fixes in reverse order.
    for line_idx, func_name, expected in sorted(targets, reverse=True):
        if line_idx >= len(lines):
            continue
        line = lines[line_idx]
        # Insert self/cls after the opening paren.
        # Pattern: def name( or async def name(
        pattern = re.compile(
            r"((?:async\s+)?def\s+" + re.escape(func_name) + r"\s*\()"
        )
        match = pattern.search(line)
        if match:
            insert_pos = match.end()
            # Check if there are existing params after the paren.
            rest = line[insert_pos:].lstrip()
            if rest.startswith(")"):
                # No params: def foo() → def foo(self)
                new_line = line[:insert_pos] + expected + line[insert_pos:]
            else:
                # Has params: def foo(x, y) → def foo(self, x, y)
                new_line = line[:insert_pos] + expected + ", " + line[insert_pos:]
            lines[line_idx] = new_line
            fixes.append(f"inserted '{expected}' in {func_name}()")

    return "".join(lines), fixes


def _fix_datetime_confusion(code: str) -> tuple[str, list[str]]:
    """Fix ``datetime.method()`` → ``datetime.datetime.method()``.

    Only applies when ``import datetime`` (module import) is present and
    ``from datetime import datetime`` (class import) is NOT present.
    """
    # Check import style.
    has_module_import = bool(
        re.search(r"^\s*import\s+datetime\b", code, re.MULTILINE)
    )
    has_class_import = bool(
        re.search(r"^\s*from\s+datetime\s+import\s+.*\bdatetime\b", code, re.MULTILINE)
    )

    if not has_module_import or has_class_import:
        return code, []

    fixes: list[str] = []

    def _replace(m: re.Match) -> str:
        method = m.group(1)
        fixes.append(f"datetime.{method} → datetime.datetime.{method}")
        return f"datetime.datetime.{method}"

    new_code = _DATETIME_METHOD_RE.sub(_replace, code)
    return new_code, fixes
