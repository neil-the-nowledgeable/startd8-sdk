# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Heading-injection sanitization (FR-RP-7 — Manifest-Suggester R3-S1 applied to markdown).

Persona free-text becomes part of a markdown requirements doc that CRP later parses by ``##``/``####``
headings. An injected heading line — accidental or adversarial — would corrupt both the requirements
structure and the ``####``-anchored CRP appendix scaffold. Two CRP corrections baked in:

* **Scan ``^#{1,6}\\s`` (h1–h6) AND setext underlines** (``^=+$`` / ``^-+$`` under a text line) — the
  original ``#{2,4}`` missed h1/h5/h6 + setext (R1-F5).
* **Blockquote-demotion is the neutralize primitive** (``> ## x``) — safe for ``^``-anchored CRP
  parsing, and it **passes** the readiness gate; a *surviving un-demoted* line-start heading is what
  the gate fails on (R2-S5 reconciles neutralize-vs-gate).
"""

from __future__ import annotations

import re

__all__ = ["ATX_HEADING_RE", "SETEXT_RE", "neutralize_headings", "has_unsafe_heading"]

# An ATX heading: up to 3 leading spaces, 1–6 ``#``, then a space (CommonMark). Anchored at line start.
ATX_HEADING_RE = re.compile(r"^ {0,3}#{1,6}\s")
# A setext underline: a run of ``=`` or ``-`` alone on a line (only a heading when it follows text).
SETEXT_RE = re.compile(r"^ {0,3}[=-]{1,}\s*$")
# A line already demoted to a blockquote is safe (``> ## x`` is not a heading to a ^-anchored parser).
_BLOCKQUOTE_RE = re.compile(r"^ {0,3}>")


def _is_atx(line: str) -> bool:
    return bool(ATX_HEADING_RE.match(line)) and not _BLOCKQUOTE_RE.match(line)


def _is_setext_underline(line: str, prev: str) -> bool:
    """A setext underline only forms a heading when the previous line is non-blank text."""
    if not SETEXT_RE.match(line) or _BLOCKQUOTE_RE.match(line):
        return False
    p = prev.strip()
    return bool(p) and not _is_atx(prev) and not _BLOCKQUOTE_RE.match(prev)


def neutralize_headings(text: str) -> str:
    """Demote every heading/setext-underline line to a blockquote (``> …``), leaving all else intact.

    Idempotent: an already-demoted ``> ## x`` is left untouched.
    """
    lines = (text or "").split("\n")
    out = []
    for i, line in enumerate(lines):
        prev = lines[i - 1] if i > 0 else ""
        if _is_atx(line) or _is_setext_underline(line, prev):
            out.append("> " + line)
        else:
            out.append(line)
    return "\n".join(out)


def has_unsafe_heading(text: str) -> bool:
    """True iff any un-demoted line-start ATX/setext heading survives (the readiness-gate check)."""
    lines = (text or "").split("\n")
    for i, line in enumerate(lines):
        prev = lines[i - 1] if i > 0 else ""
        if _is_atx(line) or _is_setext_underline(line, prev):
            return True
    return False
