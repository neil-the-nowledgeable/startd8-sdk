"""Shared validation utilities for language profiles."""
from __future__ import annotations


def check_balanced_braces(code: str) -> tuple[bool, str]:
    """Check that braces are balanced in source code.

    Used by Java and C# text-based validators.

    Returns:
        ``(True, '')`` if balanced, ``(False, error_message)`` otherwise.
    """
    depth = 0
    for ch in code:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                return False, "unbalanced braces (extra closing brace)"
    if depth != 0:
        return False, f"unbalanced braces (depth={depth})"
    return True, ""
