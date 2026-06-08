"""``DeterministicFileProvider`` for polish-owned files (FR-21).

Registered at the ``startd8.contractors.deterministic_providers`` entry point — exactly like
``PydanticSQLModelProvider`` / ``PrismaZodFileProvider``. Two effects:

1. The prime-contractor skip-hook recognizes the polished stylesheet / static-setup module as
   deterministically provided and **in-sync**, so an LLM pass never regenerates them ($0.00).
2. Polish gets its own idempotency check: "is this on-disk file what the recorded theme would
   produce today?" — answered by re-render + byte-compare against the polish manifest's theme.

Backend ``generate backend`` is unaffected regardless: ``--check`` only inspects files carrying the
``# GENERATED`` marker, and these carry ``# STARTD8-POLISH`` instead.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..contractors.deterministic_providers import ProviderContext
from .components import (
    render_components_macros,
    render_footer_partial,
    render_head_extra,
    render_header_partial,
)
from .css import POLISH_MARKER, render_static_setup, render_stylesheet
from .engine import (
    MANIFEST_RELPATH,
    STATIC_SETUP_RELPATH,
    STYLESHEET_RELPATH,
    THEME_COMPONENTS_RELPATH,
    THEME_FOOTER_RELPATH,
    THEME_HEAD_EXTRA_RELPATH,
    THEME_HEADER_RELPATH,
)
from .themes import get_theme

# Theme partials are theme-independent → resolved by path suffix, no theme needed.
_CONSTANT_PARTIALS = {
    THEME_COMPONENTS_RELPATH: render_components_macros,
    THEME_HEADER_RELPATH: render_header_partial,
    THEME_FOOTER_RELPATH: render_footer_partial,
    THEME_HEAD_EXTRA_RELPATH: render_head_extra,
}


class PresentationPolishFileProvider:
    """Recognizes polish-owned files and judges them in-sync against the recorded theme."""

    name = "presentation-polish"

    def owns(self, path: Path, content: str) -> bool:
        # One of ours iff it carries the polish marker. Cheap; no source read.
        return POLISH_MARKER in content

    def is_in_sync(self, path: Path, content: str, context: ProviderContext) -> bool:
        theme_name = self._read_manifest_theme(context)
        if not theme_name:
            # Owned file present but no manifest/theme resolved → cannot verify → not in-sync
            # (safe: the caller falls through rather than skipping a possibly-stale file).
            return False
        expected = self._render_for(path, theme_name)
        if expected is None:
            return False
        return content == expected

    @staticmethod
    def _render_for(path: Path, theme_name: str) -> Optional[str]:
        """Re-render the artifact *path* represents for *theme_name*, or None if unrecognized."""
        p = str(path).replace("\\", "/")
        # Theme-independent partials: resolved by suffix, no theme needed.
        for relpath, render in _CONSTANT_PARTIALS.items():
            if p.endswith(relpath):
                return render()
        try:
            theme = get_theme(theme_name)
        except KeyError:
            return None
        if p.endswith(STYLESHEET_RELPATH) or p.endswith("static/css/app.css"):
            return render_stylesheet(theme)
        if p.endswith(STATIC_SETUP_RELPATH) or p.endswith("static_setup.py"):
            return render_static_setup()
        return None

    @staticmethod
    def _read_manifest_theme(context: ProviderContext) -> Optional[str]:
        """The theme name recorded in the polish manifest at the project root, or None."""
        manifest = Path(context.project_root) / MANIFEST_RELPATH
        if not manifest.is_file():
            return None
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        theme = data.get("theme")
        return theme if isinstance(theme, str) else None
