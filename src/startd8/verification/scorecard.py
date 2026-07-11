# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""A small, shared inverted-pyramid scorecard renderer.

Leads with the headline (BLUF), then supporting sections — the journalistic ordering the
benchmark scorecard (``benchmark_matrix/scorecard.py``) established. Domain code (fidelity,
benchmark) builds its own dimensions and hands them here as pre-rendered sections, so the
*ordering + shape* is shared without coupling to any one domain's schema. Degrade-honest:
a section marked absent should still be rendered (say "not computed"), never dropped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence


@dataclass
class Section:
    """One scorecard section: a title and pre-rendered markdown body."""

    title: str
    body: str


def table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    """Render a GitHub-flavored markdown table (empty rows ⇒ an italic placeholder)."""
    if not rows:
        return "_(none)_"
    head = "| " + " | ".join(str(h) for h in headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = "\n".join("| " + " | ".join(str(c) for c in row) + " |" for row in rows)
    return "\n".join([head, sep, body])


def render_scorecard(
    *,
    title: str,
    headline: List[str],
    sections: List[Section],
    footer: str = "",
) -> str:
    """Assemble a scorecard: title → headline (BLUF) → sections → footer."""
    parts: List[str] = [f"# {title}\n"]
    if headline:
        parts.append("\n".join(headline) + "\n")
    for s in sections:
        parts.append(f"## {s.title}\n\n{s.body}\n")
    if footer:
        parts.append("---\n\n" + footer)
    return "\n".join(parts).rstrip() + "\n"
