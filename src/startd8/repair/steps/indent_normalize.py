"""Indent normalization repair step (REQ-RPL-101).

Normalizes indentation to 4-space using multiple strategies.
Level-specific: uses ``element_context.parent_class`` when present
(micro-prime), falls back to file-level ``ast.parse()`` when None
(contractor).
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult
from ..protocol import AstParseValidator

# Stateless singleton — safe for concurrent use (no mutable state).
_validator = AstParseValidator()


class IndentNormalizeStep:
    """Normalize indentation to 4-space."""

    name: str = "indent_normalize"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        is_method = bool(
            element_context and element_context.parent_class
        )

        # If already valid, skip
        if _validator.validate(code, is_method):
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        strategies: list[tuple[str, str]] = []
        lines = code.split("\n")

        # Strategy 1: Straight dedent
        dedented = textwrap.dedent(code).strip()
        strategies.append(("dedent", dedented))

        # Strategy 2: Strip first line + dedent
        if len(lines) > 2:
            without_first = "\n".join(lines[1:])
            strategies.append(("strip_first+dedent", textwrap.dedent(without_first).strip()))

        # Strategy 3: Strip last line + dedent
        if len(lines) > 2:
            without_last = "\n".join(lines[:-1])
            strategies.append(("strip_last+dedent", textwrap.dedent(without_last).strip()))

        # Strategy 4: Strip both + dedent
        if len(lines) > 3:
            middle = "\n".join(lines[1:-1])
            strategies.append(("strip_both+dedent", textwrap.dedent(middle).strip()))

        # Strategy 5: Tab → 4 spaces + dedent
        if "\t" in code:
            tab_fixed = code.expandtabs(4)
            strategies.append(("tabs_to_spaces+dedent", textwrap.dedent(tab_fixed).strip()))

        for name, candidate in strategies:
            if not candidate:
                continue
            if _validator.validate(candidate, is_method):
                return RepairStepResult(
                    step_name=self.name,
                    modified=True,
                    code=candidate,
                    metrics={"strategy": name},
                )

        return RepairStepResult(
            step_name=self.name,
            modified=False,
            code=code,
            metrics={"all_strategies_failed": True},
        )
