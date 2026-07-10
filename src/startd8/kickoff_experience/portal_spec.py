"""Kickoff Workbook — shared primitives (post-M4 convergence).

The classic Era-1 board builders (``build_kickoff_portal_spec`` + its section builders + the jsonnet
compile path) were **RETIRED** in the Workbook↔cockpit convergence (M4): the agentic cockpit
(``portal_spec_v2``) is now the one Digital Project Workbook, and the portfolio index is a pure-Python
v2 dashlist (``portal_spec_v2.build_index_v2``). This module keeps only the primitives BOTH the cockpit
and the index share — the tag, the UIDs, the slug, the canonical attention display/sort, the
domain↔manifest maps, and the markdown value snippet. No jsonnet, no board building here anymore.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Tuple

# --- UID / slug (FR-5) -----------------------------------------------------------------------------
WORKBOOK_TAG = "workbook"  # FR-11 contract: every Workbook carries this tag (the index dashlist filters on it)
INDEX_UID = "cc-portal-kickoff-index"
INDEX_TITLE = "Digital Project Workbooks — Index"


def slugify_project(project: str) -> str:
    """Deterministic slug: lowercase, ``_``/space → ``-``, drop other chars, collapse/trim ``-``."""
    s = (project or "").strip().lower().replace("_", "-").replace(" ", "-")
    s = re.sub(r"[^a-z0-9-]", "", s)
    return re.sub(r"-+", "-", s).strip("-")


# canonical attention -> (emoji, short label). Attention is derived once in state.py; we never
# re-derive it here (parity guarantee). Shared by the cockpit's field tables.
_ATTENTION_DISPLAY: Dict[str, Tuple[str, str]] = {
    "ok": ("✅", "confirmed"),
    "review": ("🟡", "review — SDK-defaulted"),
    "blocked": ("🔴", "gap — author action needed"),
    "backlog": ("⚪", "backlog"),
}
# gaps first when listing a manifest's fields
_ATTENTION_SORT: Dict[str, int] = {"blocked": 0, "review": 1, "backlog": 2, "ok": 3}

# domain ↔ manifest maps (the cockpit orders domains canonically via _manifest_sort_key).
_DOMAIN_MANIFEST: Dict[str, str] = {
    "business-targets": "business-targets.yaml",
    "observability": "observability.yaml",
    "conventions": "conventions.yaml",
    "build-preferences": "build-preferences.yaml",
}
_MANIFEST_DOMAIN: Dict[str, str] = {v: k for k, v in _DOMAIN_MANIFEST.items()}

_VALUE_SNIPPET_LEN = 48


def _md_escape(value: Any) -> str:
    """Escape a short cell value for a Markdown table (no truncation)."""
    return str(value).replace("\n", " ").replace("|", "\\|")


def _value_snippet(value: Any, limit: int = _VALUE_SNIPPET_LEN) -> str:
    s = _md_escape(value)
    return (s[:limit] + "…") if len(s) > limit else s


def _manifest_sort_key(manifest: str):
    """Canonical domains first (in declared order), then any other manifests alphabetically."""
    if manifest in _MANIFEST_DOMAIN:
        return (0, list(_DOMAIN_MANIFEST.values()).index(manifest))
    return (1, manifest)
