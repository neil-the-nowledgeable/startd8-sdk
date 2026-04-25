"""Vue SFC script extraction and re-injection (REQ-VUE-B-002, REQ-VUE-B-003).

Precedence for the primary editable script block:

1. The first ``<script setup …>`` block that does **not** use ``src=``.
2. Otherwise the first non-``setup`` ``<script>`` block without ``src=``.

``<script src="…">`` blocks are skipped (external scripts are not logical
edit units for MicroPrime in the basic tier).

**Splice contract (REQ-VUE-P-003):** ``reinject_vue_script`` replaces only the
inner text of the chosen ``<script>`` … ``</script>`` match. Opening tag
attributes, template/style blocks, and block order outside that span are
preserved verbatim (including CRLF vs LF in the rest of the file).

**Compiler macros & ``nodejs_parser`` parity (REQ-VUE-P-002):** Vue 3 macros
(``defineProps``, ``defineEmits``, ``defineExpose``, ``withDefaults``, etc.)
compile away; at the extracted-script text layer they look like ordinary
call expressions. The shared ``parse_vue_sfc_script_elements`` helper delegates
to ``nodejs_parser.parse_nodejs_source``, which is regex-based and shares the
same limitations as for plain ``.ts`` / ``.js`` (see that module's docstring).
Full AST-level macro modeling is out of scope for the basic tier.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from startd8.languages.nodejs_parser import NodeElement, parse_nodejs_source

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

    setup_hits: List[re.Match[str]] = []
    plain_hits: List[re.Match[str]] = []
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


def vue_script_block_checksum(source: str) -> Optional[Tuple[int, int, str]]:
    """Fingerprint primary script inner span for idempotence checks (REQ-VUE-P-013).

    Returns ``(content_start, content_end, sha256_hex)`` of the extracted
    script body text, or ``None`` when no primary block exists.
    """
    ext = extract_vue_script(source)
    if ext is None:
        return None
    digest = hashlib.sha256(ext.script.encode("utf-8")).hexdigest()
    return (ext.content_start, ext.content_end, digest)


def parse_vue_sfc_script_elements(source: str) -> List[NodeElement]:
    """Parse the primary ``<script>`` block with the Node regex extractor (REQ-VUE-P-002)."""
    ext = extract_vue_script(source)
    if ext is None or not ext.script.strip():
        return []
    return parse_nodejs_source(ext.script)
