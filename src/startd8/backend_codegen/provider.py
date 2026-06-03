"""Prisma→Pydantic deterministic-file provider (Python contract-codegen path).

Implements the language-agnostic ``DeterministicFileProvider`` protocol so the prime contractor's
owned-file skip-hook recognizes an in-sync generated Pydantic-models file (marking the feature
``GENERATED`` at $0.00) **without the core importing anything Python/Prisma-specific** — all the
stack knowledge lives here, behind the registry, exactly as ``PrismaZodFileProvider`` does for TS.

Registered via the ``startd8.contractors.deterministic_providers`` entry-point group.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..contractors.deterministic_providers import ProviderContext
from .drift import is_owned_generated_file, owned_file_in_sync


class PydanticSQLModelProvider:
    """Recognizes our generated Prisma→Pydantic files and judges them in-sync against the schema."""

    name = "pydantic-sqlmodel"

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
        """Find + read the ``.prisma`` schema from the context's anchors, else the conventional path.

        The ``.prisma`` schema is the neutral contract IDL (OQ-7); this anchor logic deliberately
        lives in the provider, not the core orchestrator.
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

    @staticmethod
    def _read_anchored(
        context: ProviderContext, *, suffix: str, conventional_relpath: str
    ) -> Optional[str]:
        """Read the first anchor ending in *suffix*, else the conventional path. Raw text or None.

        The shared finder behind the AI-layer's second/third inputs (``ai_passes.yaml`` /
        ``human_inputs.yaml``) — same anchor-then-convention discipline as :meth:`_read_schema`.
        """
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
        conventional = root / conventional_relpath
        if conventional.is_file():
            try:
                return conventional.read_text(encoding="utf-8")
            except OSError:
                return None
        return None

    @classmethod
    def _read_manifest(cls, context: ProviderContext) -> Optional[str]:
        """The AI-passes manifest (FR-MA-5), raw YAML text or ``None`` if absent."""
        return cls._read_anchored(
            context, suffix="ai_passes.yaml", conventional_relpath="prisma/ai_passes.yaml"
        )

    @classmethod
    def _read_human_inputs(cls, context: ProviderContext) -> Optional[str]:
        """The human-provided inputs file (C-4), raw YAML text or ``None`` if absent."""
        return cls._read_anchored(
            context, suffix="human_inputs.yaml", conventional_relpath="prisma/human_inputs.yaml"
        )
