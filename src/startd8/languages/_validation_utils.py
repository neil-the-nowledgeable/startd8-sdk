"""Shared validation utilities for language profiles."""
from __future__ import annotations


# Python fingerprints — if these appear in non-Python files, it's
# cross-language contamination.  Shared by Java and C# validators.
PYTHON_FINGERPRINTS: tuple[str, ...] = (
    "def ", "import os", "from __future__", "print(", "self.",
    "#!/usr/bin/env python", "#!/usr/bin/python",
)


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
