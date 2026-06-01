"""String-aware JSONC (JSON-with-comments) parsing.

tsconfig.json is JSONC: it allows ``//`` and ``/* */`` comments and trailing commas.
A naive regex comment-stripper is WRONG because tsconfig path globs contain ``/*``
inside string literals (e.g. ``"./src/*"``); a regex would treat that as the start of a
block comment and eat valid JSON up to the next ``*/``. This scanner removes comments
only outside string literals, then drops trailing commas.
"""

from __future__ import annotations

import json
import re
from typing import Any

_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def strip_jsonc(text: str) -> str:
    """Return ``text`` with comments removed (string-aware) and trailing commas dropped."""
    out: list[str] = []
    i, n = 0, len(text)
    in_str = False
    quote = ""
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:  # keep escaped char verbatim
                out.append(text[i + 1])
                i += 2
                continue
            if c == quote:
                in_str = False
            i += 1
            continue
        if c == '"' or c == "'":
            in_str = True
            quote = c
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2  # skip the closing */
            continue
        out.append(c)
        i += 1
    return _TRAILING_COMMA.sub(r"\1", "".join(out))


def loads_jsonc(text: str) -> Any:
    """Parse a JSONC string. Raises ``json.JSONDecodeError`` on genuinely invalid JSON."""
    return json.loads(strip_jsonc(text))
