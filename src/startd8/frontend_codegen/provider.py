"""Prisma→Zod deterministic-file provider.

Implements the language-agnostic ``DeterministicFileProvider`` protocol so the prime
contractor's owned-file skip-hook can recognize an in-sync generated `value-model.ts`
**without the core importing anything TS/Prisma-specific** (the decoupling — all Prisma/Zod
knowledge lives here, behind the registry).

Registered via the ``startd8.contractors.deterministic_providers`` entry-point group.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..contractors.deterministic_providers import ProviderContext
from .drift import is_owned_generated_file, owned_file_in_sync


class PrismaZodFileProvider:
    """Recognizes our generated Prisma→Zod files and judges them in-sync against the schema."""

    name = "prisma-zod"

    def owns(self, path: Path, content: str) -> bool:
        # One of ours iff it carries the GENERATED header we emit. Cheap; no source read.
        return is_owned_generated_file(content)

    def is_in_sync(self, path: Path, content: str, context: ProviderContext) -> bool:
        schema_text = self._read_schema(context)
        if not schema_text:
            # Owned file present but no Prisma schema resolved → cannot verify → not in-sync
            # (safe: the caller falls through to the LLM rather than skipping a stale file).
            return False
        return owned_file_in_sync(schema_text, content)

    @staticmethod
    def _read_schema(context: ProviderContext) -> Optional[str]:
        """Find + read the Prisma schema from the context's anchors, else the conventional path.

        This Prisma-specific anchor logic deliberately lives in the provider, not the core
        orchestrator.
        """
        root = Path(context.project_root)
        for anchor in context.source_anchors:
            if not str(anchor).endswith(".prisma"):
                continue
            ap = Path(anchor) if Path(anchor).is_absolute() else root / anchor
            if ap.is_file():
                try:
                    return ap.read_text(encoding="utf-8")
                except OSError:
                    return None
        conventional = root / "prisma" / "schema.prisma"
        if conventional.is_file():
            try:
                return conventional.read_text(encoding="utf-8")
            except OSError:
                return None
        return None
