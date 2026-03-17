"""Semantic method resolution repair step (REQ-SR-100).

Fixes ``self.<name>()`` calls where ``<name>`` is a module-level function,
not a method on the enclosing class.  Rewrites to ``<name>(self, ...)``.

Common in Locust TaskSet code where the LLM confuses module-level task
functions with instance methods::

    def index(l):
        l.client.get("/")

    class UserBehavior(TaskSet):
        def on_start(self):
            self.index()       # BUG → index(self)
        tasks = {index: 1}    # CORRECT — not touched
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from ...logging_config import get_logger
from ..models import ElementContext, RepairContext, RepairStepResult, SemanticDiagnostic

logger = get_logger(__name__)


class SemanticMethodResolutionFixStep:
    """Rewrite self.<func>() → <func>(self) for module-level functions."""

    name: str = "semantic_method_resolution_fix"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        diagnostics = [
            d for d in context.diagnostics
            if isinstance(d, SemanticDiagnostic)
            and d.semantic_category == "method_resolution"
        ]
        if not diagnostics:
            return RepairStepResult(step_name=self.name, modified=False, code=code)

        lines = code.splitlines(keepends=True)
        fixes: list[str] = []

        # Process in reverse line order so earlier fixes don't shift later lines
        sorted_diags = sorted(diagnostics, key=lambda d: d.line, reverse=True)

        for diag in sorted_diags:
            symbol = diag.symbol  # e.g., "index"
            target_line_idx = diag.line - 1
            if target_line_idx < 0 or target_line_idx >= len(lines):
                continue

            line = lines[target_line_idx]

            # Match self.<symbol>( with optional args
            pattern = re.compile(
                r"\bself\." + re.escape(symbol) + r"\s*\("
            )
            match = pattern.search(line)
            if not match:
                continue

            call_start = match.start()
            # match ends right after the '(' — guaranteed by regex r"\("
            paren_start = match.end() - 1

            # Find matching close paren, skipping parens inside string literals
            depth = 1
            i = paren_start + 1
            in_single = False
            in_double = False
            while i < len(line) and depth > 0:
                ch = line[i]
                # Toggle string state (single-char quotes only; triple-quotes
                # are rare in single-line call args and not worth the complexity)
                if ch == "'" and not in_double:
                    in_single = not in_single
                elif ch == '"' and not in_single:
                    in_double = not in_double
                elif not in_single and not in_double:
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                i += 1

            if depth != 0:
                # Unbalanced parens — skip (multi-line call or syntax issue)
                continue

            inner_args = line[paren_start + 1: i - 1].strip()

            if inner_args:
                replacement = f"{symbol}(self, {inner_args})"
            else:
                replacement = f"{symbol}(self)"

            new_line = line[:call_start] + replacement + line[i:]
            lines[target_line_idx] = new_line
            fixes.append(f"self.{symbol}() → {symbol}(self)")

        modified = len(fixes) > 0
        if modified:
            logger.info(
                "semantic_method_resolution_fix applied %d fix(es) to %s: %s",
                len(fixes), file_path.name, "; ".join(fixes),
            )

        return RepairStepResult(
            step_name=self.name,
            modified=modified,
            code="".join(lines),
            metrics={"fixes": fixes},
        )
