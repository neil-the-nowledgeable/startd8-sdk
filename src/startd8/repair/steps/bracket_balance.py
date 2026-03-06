"""Bracket balance repair step (REQ-RPL-103).

Fixes unclosed delimiters (``(``, ``[``, ``{``) from truncated LLM
generation by scanning tokens while respecting string literals and
comments.

AST analysis is not possible for code with unclosed delimiters, so
this step uses manual character-level scanning with scope tracking.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ...logging_config import get_logger
from ..models import ElementContext, RepairContext, RepairStepResult

logger = get_logger(__name__)

_OPEN_TO_CLOSE = {"(": ")", "[": "]", "{": "}"}
_CLOSE_SET = set(_OPEN_TO_CLOSE.values())


class BracketBalanceStep:
    """Append missing closing delimiters for unclosed brackets."""

    name: str = "bracket_balance"

    def __call__(
        self,
        code: str,
        context: RepairContext,
        file_path: Path,
        element_context: Optional[ElementContext] = None,
    ) -> RepairStepResult:
        stack = _scan_delimiters(code)

        if not stack:
            return RepairStepResult(
                step_name=self.name, modified=False, code=code,
            )

        # Build closing sequence: close in reverse order (LIFO)
        closers = "".join(_OPEN_TO_CLOSE[ch] for ch in reversed(stack))
        repaired = code.rstrip() + closers + "\n"

        logger.debug(
            "Appended %d closing delimiter(s) to %s: %r",
            len(stack), file_path, closers,
        )

        return RepairStepResult(
            step_name=self.name,
            modified=True,
            code=repaired,
            metrics={
                "unclosed_count": len(stack),
                "appended": closers,
            },
        )


def _scan_delimiters(code: str) -> list[str]:
    """Scan *code* and return a list of unclosed opening delimiters.

    Skips delimiters inside string literals (single, double, triple-
    quoted) and ``#`` comments.  Returns an empty list when balanced.
    """
    stack: list[str] = []
    i = 0
    length = len(code)

    while i < length:
        ch = code[i]

        # --- Comments -----------------------------------------------
        if ch == "#":
            # Skip to end of line
            while i < length and code[i] != "\n":
                i += 1
            continue

        # --- String literals ----------------------------------------
        if ch in ('"', "'"):
            i = _skip_string(code, i, length)
            continue

        # --- Delimiters ---------------------------------------------
        if ch in _OPEN_TO_CLOSE:
            stack.append(ch)
            i += 1
            continue

        if ch in _CLOSE_SET:
            # Pop matching opener if present; ignore unexpected closers
            # (those are a different class of error).
            expected_open = {")" : "(", "]": "[", "}": "{"}[ch]
            if stack and stack[-1] == expected_open:
                stack.pop()
            i += 1
            continue

        i += 1

    return stack


def _skip_string(code: str, start: int, length: int) -> int:
    """Advance past a string literal starting at *start*.

    Handles single, double, and triple-quoted strings with backslash
    escapes.  Returns the index immediately after the closing quote.
    """
    quote_char = code[start]

    # Check for triple-quote
    if start + 2 < length and code[start + 1] == quote_char and code[start + 2] == quote_char:
        # Triple-quoted string
        end_seq = quote_char * 3
        i = start + 3
        while i < length:
            if code[i] == "\\" and i + 1 < length:
                i += 2  # skip escaped character
                continue
            if code[i:i + 3] == end_seq:
                return i + 3
            i += 1
        # Unterminated triple-quote — advance to end
        return length

    # Single-quoted string
    i = start + 1
    while i < length:
        if code[i] == "\\" and i + 1 < length:
            i += 2
            continue
        if code[i] == quote_char:
            return i + 1
        if code[i] == "\n":
            # Unterminated single-line string — stop at newline
            return i
        i += 1
    return length
