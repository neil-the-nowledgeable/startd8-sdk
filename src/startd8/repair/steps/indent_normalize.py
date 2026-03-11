"""Indent normalization repair step (REQ-RPL-101).

Normalizes indentation to 4-space using multiple strategies.
Level-specific: uses ``element_context.parent_class`` when present
(micro-prime), falls back to file-level ``ast.parse()`` when None
(contractor).
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from typing import Optional

from ..models import ElementContext, RepairContext, RepairStepResult
from ..protocol import AstParseValidator

# Stateless singleton — safe for concurrent use (no mutable state).
_validator = AstParseValidator()

# Patterns that signal a block indent increase (line ends with ':')
_BLOCK_START_RE = re.compile(
    r"^\s*(if|elif|else|for|while|with|try|except|finally|def|async\s+def|class)\b.*:\s*$"
)
# Patterns that signal a block indent decrease
_BLOCK_DEDENT_RE = re.compile(
    r"^\s*(elif|else|except|finally)\b"
)


def _structural_reindent(code: str, base_indent: int = 0) -> str:
    """Re-indent code based on Python block structure.

    Handles non-uniform indentation where ``textwrap.dedent()`` fails
    (e.g. Ollama returning body with mixed 4/8/12/16-space indents).

    Walks lines and infers indent level from block-opening colons
    (``if/for/while/with/try/def/class ...:``) and block-continuing
    keywords (``elif/else/except/finally``).

    Args:
        code: Code with potentially corrupted indentation.
        base_indent: Number of spaces for the outermost indentation level.

    Returns:
        Re-indented code string.
    """
    lines = code.splitlines()
    result: list[str] = []
    current_level = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            result.append("")
            continue

        # Dedent before rendering for block-continuing keywords
        if _BLOCK_DEDENT_RE.match(stripped):
            current_level = max(0, current_level - 1)

        indent = " " * (base_indent + current_level * 4)
        result.append(f"{indent}{stripped}")

        # Indent after rendering for block-opening statements
        if _BLOCK_START_RE.match(stripped):
            current_level += 1

    return "\n".join(result)


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

        # Strategy 6: Structural re-indent (Fix 2 — handles non-uniform
        # indentation from Ollama, e.g. mixed 4/8/12/16-space indent where
        # textwrap.dedent() is a no-op because there's no common prefix).
        # Determine base indent: methods need 4 spaces (inside class),
        # top-level functions need 0.
        first_line = lines[0].strip() if lines else ""
        starts_with_def = first_line.startswith(("def ", "async def ", "class "))
        if starts_with_def:
            # Whole function — re-indent with base 0 (def line at col 0)
            # or 4 if inside a class
            base = 4 if is_method else 0
            reindented = _structural_reindent(code, base_indent=base)
            strategies.append(("structural_reindent", reindented.strip()))
        else:
            # Body-only lines — try base_indent=4 (one level inside def)
            # and base_indent=8 (one level inside method in class)
            reindented_4 = _structural_reindent(code, base_indent=4)
            strategies.append(("structural_reindent_4", reindented_4.strip()))
            if is_method:
                reindented_8 = _structural_reindent(code, base_indent=8)
                strategies.append(("structural_reindent_8", reindented_8.strip()))

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
