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
        # FR-ED-16: thread EVERY manifest a generated kind can derive from, or manifest-derived files
        # (forms/pages/AI/flows/editors) drift-check with their input unset → ERROR → False → fall
        # through to the LLM despite being clean $0 files. Each read is best-effort (None when absent),
        # and a schema-only kind ignores all of them — so passing them is always safe.
        return owned_file_in_sync(
            schema_text,
            content,
            views_text=self._read_views(context),
            pages_text=self._read_pages(context),
            manifest_text=self._read_manifest(context),
            human_inputs_text=self._read_human_inputs(context),
            completeness_text=self._read_completeness(context),
            display_text=self._read_display(context),
            imports_text=self._read_imports(context),
            api_text=self._read_api(context),
            contexts_text=self._read_contexts(context),
            form_prose_text=self._read_form_prose(context),
            project_root=str(Path(context.project_root).resolve()),
        )

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

    @classmethod
    def _read_views(cls, context: ProviderContext) -> Optional[str]:
        """``views.yaml`` (``forms:``/``flows:``/``editors:``/``filters:`` sections), raw text or None."""
        return cls._read_anchored(
            context, suffix="views.yaml", conventional_relpath="prisma/views.yaml"
        )

    @classmethod
    def _read_pages(cls, context: ProviderContext) -> Optional[str]:
        """``pages.yaml`` (content-pages manifest), raw text or ``None`` if absent."""
        return cls._read_anchored(
            context, suffix="pages.yaml", conventional_relpath="prisma/pages.yaml"
        )

    @classmethod
    def _read_completeness(cls, context: ProviderContext) -> Optional[str]:
        """``completeness.yaml`` (domain-weighted thresholds), raw text or ``None`` if absent."""
        return cls._read_anchored(
            context, suffix="completeness.yaml", conventional_relpath="prisma/completeness.yaml"
        )

    @classmethod
    def _read_display(cls, context: ProviderContext) -> Optional[str]:
        """``display.yaml`` (presentation-structure layer, FR-DM), raw text or ``None`` if absent."""
        return cls._read_anchored(
            context, suffix="display.yaml", conventional_relpath="prisma/display.yaml"
        )

    @classmethod
    def _read_form_prose(cls, context: ProviderContext) -> Optional[str]:
        """``form_prose.yaml`` (the form WORDS layer, FR-FH-1/2), raw text or ``None`` if absent.

        Threaded into the skip-hook so a freshly-generated ``<e>/form.html`` carrying form-help include
        lines is recognized as a ``$0``-owned file (without it the htmx-form re-render omits the includes
        → drift → falls through to the LLM)."""
        return cls._read_anchored(
            context, suffix="form_prose.yaml", conventional_relpath="prisma/form_prose.yaml"
        )

    @classmethod
    def _read_imports(cls, context: ProviderContext) -> Optional[str]:
        """``imports.yaml`` (FR-IMP-3 import declarations), raw text or ``None`` if absent.

        Threaded into the skip-hook so a freshly-generated ``app/importer.py`` is recognized as a
        ``$0``-owned file (without it the two-hash check ERRORs → falls through to the LLM)."""
        return cls._read_anchored(
            context, suffix="imports.yaml", conventional_relpath="prisma/imports.yaml"
        )

    @classmethod
    def _read_api(cls, context: ProviderContext) -> Optional[str]:
        """``api.yaml`` (Role 2 surface overlay), raw text or ``None`` if absent."""
        return cls._read_anchored(
            context, suffix="api.yaml", conventional_relpath="prisma/api.yaml"
        )

    @classmethod
    def _read_contexts(cls, context: ProviderContext) -> Optional[str]:
        """``contexts.yaml`` (Role 3 outbound producers), raw text or ``None`` if absent."""
        return cls._read_anchored(
            context, suffix="contexts.yaml", conventional_relpath="prisma/contexts.yaml"
        )
