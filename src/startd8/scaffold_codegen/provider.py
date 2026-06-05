"""Scaffold deterministic-file provider — the third owned-file provider (class-2 plumbing).

Registers on the ``startd8.contractors.deterministic_providers`` entry-point group exactly like
``PydanticSQLModelProvider`` (schema-derived) and ``PrismaZodFileProvider`` (TS), so the prime
contractor's owned-file skip-hook recognizes in-sync scaffold files ($0.00) without the core knowing
anything scaffold-specific. The source it resolves is ``app.yaml`` (not the schema).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..contractors.deterministic_providers import ProviderContext
from .drift import is_owned_scaffold_file, scaffold_in_sync


class ScaffoldFileProvider:
    """Recognizes our generated plumbing files and judges them in-sync against ``app.yaml``."""

    name = "scaffold"

    def owns(self, path: Path, content: str) -> bool:
        return is_owned_scaffold_file(content)

    def is_in_sync(self, path: Path, content: str, context: ProviderContext) -> bool:
        manifest_text = self._read_manifest(context)
        if not manifest_text:
            # Owned file present but no app.yaml resolved → cannot verify → not in-sync (safe).
            return False
        return scaffold_in_sync(manifest_text, content)

    @staticmethod
    def _read_manifest(context: ProviderContext) -> Optional[str]:
        """Find + read ``app.yaml`` from the context anchors, else the conventional path."""
        root = Path(context.project_root)
        for anchor in context.source_anchors:
            if not str(anchor).endswith("app.yaml"):
                continue
            ap = Path(anchor) if Path(anchor).is_absolute() else root / anchor
            if ap.is_file():
                try:
                    return ap.read_text(encoding="utf-8")
                except OSError:
                    return None
        for conventional in (root / "app.yaml", root / "prisma" / "app.yaml"):
            if conventional.is_file():
                try:
                    return conventional.read_text(encoding="utf-8")
                except OSError:
                    return None
        return None
