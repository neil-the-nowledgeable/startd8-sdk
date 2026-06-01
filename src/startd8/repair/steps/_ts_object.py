"""Bounded TS object-literal helpers for name-repair steps (Inc 4, R1-S9/R4-S3).

Brace-matched, string-aware scanning of TypeScript object literals. Deliberately
*bounded*: only depth-1 identifier keys of a given object are surfaced. Keys
nested deeper, spread elements (``...obj``), and computed/template keys (``[k]:``)
are intentionally invisible, so the rename steps never blind-rewrite a key inside
an unrelated nested object (the corruption risk R1-S9 flags).
"""

from __future__ import annotations

from typing import List, Tuple

_OPENERS = "{[("
_CLOSERS = "}])"
_QUOTES = "\"'`"


def find_object_close(code: str, open_idx: int) -> int:
    """Given *open_idx* at a ``{``, return the index of the matching ``}`` (or -1).

    String-aware so a ``}`` inside a quote does not unbalance the match.
    """
    depth = 0
    i = open_idx
    n = len(code)
    in_str = ""
    while i < n:
        c = code[i]
        if in_str:
            if c == in_str and code[i - 1] != "\\":
                in_str = ""
        elif c in _QUOTES:
            in_str = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def top_level_key_spans(
    code: str, obj_open: int, obj_close: int
) -> List[Tuple[str, int, int]]:
    """Return ``(name, start, end)`` for each depth-1 identifier key of an object.

    *obj_open* indexes the object's ``{`` and *obj_close* its matching ``}``. Only
    bare-identifier keys immediately followed by ``:`` at brace-depth 1 are
    returned; spreads, computed keys, quoted keys, and anything nested deeper are
    skipped (the step abstains on them rather than guessing).
    """
    spans: List[Tuple[str, int, int]] = []
    i = obj_open + 1
    depth = 1
    in_str = ""
    n = obj_close
    while i < n:
        c = code[i]
        if in_str:
            if c == in_str and code[i - 1] != "\\":
                in_str = ""
            i += 1
            continue
        if c in _QUOTES:
            in_str = c
            i += 1
            continue
        if c in _OPENERS:
            depth += 1
            i += 1
            continue
        if c in _CLOSERS:
            depth -= 1
            i += 1
            continue
        if depth == 1 and (c.isalpha() or c in "_$"):
            j = i
            while j < n and (code[j].isalnum() or code[j] in "_$"):
                j += 1
            k = j
            while k < n and code[k].isspace():
                k += 1
            if k < n and code[k] == ":":
                spans.append((code[i:j], i, j))
                i = k + 1
                continue
            i = j
            continue
        i += 1
    return spans
