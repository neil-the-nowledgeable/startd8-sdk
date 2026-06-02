"""Re-validation + scoped rollback for repair-retry (Inc 5, FR-7).

After the engine applies rewrites/scaffolds, this module answers *did each fix
hold?* — re-scanning ``unresolvable_import`` over the working sources **and** the
generated artifacts, plus a syntax gate (R4-F2). Rollback is **pre-image +
kept-subset replay** (R2-S1/R3-S1): there are no offsets (the rewrite primitive
is a token replace), so a file is reconstructed by re-applying only the kept
substitutions to its captured pre-image.

Violation identity is the **`{source_file, specifier}` multiset** (R5-S3): a fix
is rolled back only when a *new* key appears (``post − pre``) or syntax newly
breaks — an unchanged, co-located abstained violation never triggers rollback.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from ...logging_config import get_logger
from ...validators.cross_file_imports import scan_unresolvable_imports
from .rewriter import Rewrite, apply_rewrite

logger = get_logger(__name__)

_OPEN = {"(": ")", "[": "]", "{": "}"}
_CLOSE = {v: k for k, v in _OPEN.items()}
_QUOTES = "\"'`"


def unresolvable_index(
    sources: Dict[str, str], project_root: str
) -> Set[Tuple[str, str]]:
    """The ``{(source_file, specifier)}`` set of unresolvable imports over *sources*."""
    return {
        (v.source_file, v.specifier)
        for v in scan_unresolvable_imports(sources, project_root)
        if v.kind == "unresolvable_import"
    }


def balanced_syntax_ok(content: str) -> bool:
    """String/comment-aware delimiter balance — a cheap, deterministic syntax gate.

    Catches the gross breakage a botched string-replace could cause (R4-F2) without
    a TypeScript toolchain. Ignores ``//``/``/* */`` comments and string/template
    bodies so braces inside them don't unbalance the count.
    """
    stack: List[str] = []
    i, n = 0, len(content)
    in_str = ""
    while i < n:
        c = content[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = ""
            i += 1
            continue
        if c in _QUOTES:
            in_str = c
            i += 1
            continue
        if c == "/" and i + 1 < n and content[i + 1] == "/":
            j = content.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "/" and i + 1 < n and content[i + 1] == "*":
            j = content.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if c in _OPEN:
            stack.append(c)
        elif c in _CLOSE:
            if not stack or stack[-1] != _CLOSE[c]:
                return False
            stack.pop()
        i += 1
    return not stack and not in_str


def replay_kept(pre_image: str, rewrites: List[Rewrite], dropped: Set[str]) -> str:
    """Reconstruct file content = *pre_image* + every rewrite not in *dropped*."""
    out = pre_image
    for rw in rewrites:
        if rw.specifier in dropped:
            continue
        out, _ = apply_rewrite(out, rw)
    return out
