"""Vue SFC script extraction and re-injection (REQ-VUE-B-002, REQ-VUE-B-003).

Precedence for the primary editable script block:

1. The first ``<script setup …>`` block that does **not** use ``src=``.
2. Otherwise the first non-``setup`` ``<script>`` block without ``src=``.

``<script src="…">`` blocks are skipped (external scripts are not logical
edit units for MicroPrime in the basic tier).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List, Optional

_SCRIPT_BLOCK = re.compile(
    r"<script(?P<attrs>[^>]*?)>(?P<body>.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


def _lang_from_attrs(attrs: str) -> str:
    m = re.search(r'\blang\s*=\s*["\']?(?P<lang>[^"\'\s>]+)', attrs, re.IGNORECASE)
    if not m:
        return "js"
    raw = m.group("lang").lower()
    if raw in ("ts", "tsx"):
        return "ts"
    return "js"


@dataclass(frozen=True)
class VueScriptExtract:
    """Primary ``<script>`` / ``<script setup>`` block inside an SFC."""

    script: str
    lang: str  # "js" or "ts"
    setup: bool
    content_start: int
    content_end: int


def extract_vue_script(source: str) -> Optional[VueScriptExtract]:
    """Return the primary script block text and slice offsets, or ``None``."""
    if not source or "<script" not in source.lower():
        return None

    setup_hits: List[Any] = []
    plain_hits: List[Any] = []
    for m in _SCRIPT_BLOCK.finditer(source):
        attrs = m.group("attrs")
        if "src=" in attrs.lower():
            continue
        astrip = attrs.lstrip()
        is_setup = astrip.startswith("setup")
        if is_setup:
            setup_hits.append(m)
        else:
            plain_hits.append(m)

    chosen = setup_hits[0] if setup_hits else (plain_hits[0] if plain_hits else None)
    if chosen is None:
        return None

    attrs = chosen.group("attrs")
    body = chosen.group("body")
    astrip = attrs.lstrip()
    is_setup = astrip.startswith("setup")
    lang = _lang_from_attrs(attrs)
    # Keep *body* exactly as captured so ``content_start``/``content_end``
    # match ``reinject_vue_script`` replacement span (REQ-VUE-B-003).
    return VueScriptExtract(
        script=body,
        lang=lang,
        setup=is_setup,
        content_start=chosen.start("body"),
        content_end=chosen.end("body"),
    )


def reinject_vue_script(original: str, new_script: str) -> str:
    """Replace the primary script block body; return *original* if none found."""
    ext = extract_vue_script(original)
    if ext is None:
        return original
    return (
        original[: ext.content_start]
        + new_script
        + original[ext.content_end :]
    )
