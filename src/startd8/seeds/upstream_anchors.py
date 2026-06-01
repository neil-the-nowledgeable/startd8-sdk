"""Parse plan-declared upstream anchors from plan markdown — RUN-009 Gap A (FR-1).

A plan marks pre-existing, immutable upstream files (the prior-milestone ship set)
with an explicit marker block so the seed-emitter can list them as
``upstream_anchors`` (consumed by ``clean-prior-run.sh`` for do-not-wipe, FR-3,
and by Gap-B Mode-B inheritance). Explicit-marker is the chosen source (OQ-2):
LLM extraction of the prose Non-Goals yields categories, not paths.

Marker format (HTML comments survive markdown rendering)::

    <!-- cap-dev-pipe: upstream-anchors -->
    - `package.json`
    - prisma/schema.prisma
    - lib/db.ts
    <!-- /cap-dev-pipe -->

Closing marker is optional — the block ends at ``<!-- /cap-dev-pipe`` , the next
``<!--`` comment, a markdown heading (``#``), or end of text. Each line is
stripped of bullets/backticks/whitespace; only tokens that look like file paths
(contain ``/`` or a filename extension) are kept.
"""

from __future__ import annotations

import re
from typing import List

_OPEN_RE = re.compile(r"<!--\s*cap-dev-pipe:\s*upstream-anchors\s*-->", re.IGNORECASE)
# A token is path-like if it has a directory separator or a trailing .ext.
# Allow Next.js dynamic/group segments: [id], [...slug], (group).
_PATH_RE = re.compile(r"^[\w.\[\]()@+-]+(?:/[\w.\[\]()@+-]+)*$")
_EXT_RE = re.compile(r"\.[A-Za-z0-9]+$")


def _clean_line(line: str) -> str:
    s = line.strip()
    s = re.sub(r"^[-*+]\s+", "", s)          # markdown bullet
    s = s.strip().strip("`").strip()          # surrounding backticks
    s = re.sub(r"\s+#.*$", "", s)             # trailing inline comment
    return s.strip()


def parse_upstream_anchors(plan_text: str) -> List[str]:
    """Return the list of project-relative anchor paths declared in *plan_text*.

    Empty list when there is no marker block (default behavior: full cleanup).
    """
    if not plan_text:
        return []
    m = _OPEN_RE.search(plan_text)
    if not m:
        return []
    rest = plan_text[m.end():]
    anchors: List[str] = []
    seen: set[str] = set()
    for raw in rest.splitlines():
        stripped = raw.strip()
        # Block terminators.
        if stripped.startswith("<!--") or stripped.startswith("#"):
            break
        token = _clean_line(raw)
        if not token or token.startswith("#"):
            continue
        # Keep only path-like tokens (has a separator or a file extension).
        if not _PATH_RE.match(token):
            continue
        if "/" not in token and not _EXT_RE.search(token):
            continue
        if token not in seen:
            seen.add(token)
            anchors.append(token)
    return anchors
