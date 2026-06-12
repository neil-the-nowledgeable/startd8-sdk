"""Composite-view deterministic-file provider — the fourth owned-file provider (class-3 views).

Registers on the shared ``startd8.contractors.deterministic_providers`` group. Resolves BOTH the
``.prisma`` schema and ``views.yaml`` from the context anchors (a view is a two-input artifact), and
judges a view file in-sync against a fresh whole-set render.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..contractors.deterministic_providers import ProviderContext
from .drift import is_owned_view_file, views_in_sync


class CompositeViewProvider:
    """Recognizes our generated composite-view files and verifies them against schema + views.yaml."""

    name = "composite-view"

    def owns(self, path: Path, content: str) -> bool:
        return is_owned_view_file(content)

    def is_in_sync(self, path: Path, content: str, context: ProviderContext) -> bool:
        schema_text = self._read(context, suffix=".prisma", conventional="prisma/schema.prisma")
        views_text = self._read(context, suffix="views.yaml", conventional="views.yaml")
        if not schema_text or not views_text:
            return False  # cannot verify without both inputs → not in-sync (safe)
        # FR-DRC-4: thread BOTH optional view inputs the generator consumes, or the re-render
        # diverges from a display-/prose-configured on-disk file → not-in-sync → the clean $0 file
        # silently falls through to the LLM. ``display.yaml`` drives FR-DM-6 composite-view label
        # resolution; ``view_prose.yaml`` drives title/intro/empty/outcome/control chrome. Each is
        # optional (None ⇒ today's literal/id render); a view that uses neither is unaffected.
        display_text = self._read(
            context, suffix="display.yaml", conventional="display.yaml"
        )
        view_prose_text = self._read(
            context, suffix="view_prose.yaml", conventional="view_prose.yaml"
        )
        return views_in_sync(
            schema_text, views_text, path, content,
            display_text=display_text, view_prose_text=view_prose_text,
        )

    @staticmethod
    def _read(context: ProviderContext, *, suffix: str, conventional: str) -> Optional[str]:
        root = Path(context.project_root)
        for anchor in context.source_anchors:
            if not str(anchor).endswith(suffix):
                continue
            ap = Path(anchor) if Path(anchor).is_absolute() else root / anchor
            if ap.is_file():
                try:
                    return ap.read_text(encoding="utf-8")
                except OSError:
                    return None
        for cand in (root / conventional, root / "prisma" / Path(conventional).name):
            if cand.is_file():
                try:
                    return cand.read_text(encoding="utf-8")
                except OSError:
                    return None
        return None
