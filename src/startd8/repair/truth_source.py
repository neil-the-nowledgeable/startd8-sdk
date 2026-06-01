"""Authoritative contract-surface truth source for name repair (Inc 1, FR-2, FR-10).

The name-repair steps (``prisma_field_rename`` / ``import_path_rename``) need to
know the *correct* names — the real Prisma field set per model, and the canonical
on-disk module-import paths — so they can rewrite an invented name to its nearest
real counterpart. The classifier signals (``prisma_unknown_field`` /
``unresolvable_import``) only carry the *invented* token; this module re-derives
the truth deterministically (no LLM) from artifacts already on disk.

The producer sits behind the :class:`TruthSource` protocol so the v1
``LiveDiskTruthSource`` (live schema + on-disk lib tree) can later be swapped for
an Approach-A ``forward_project_knowledge.json`` backend without touching the
repair steps (FR-10). Degrades loudly-but-safely: a missing schema yields an
empty field set (the step then abstains via ``no_candidates``), never an error.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping, Optional, Protocol, Set, Union, runtime_checkable

from ..languages.prisma_parser import PrismaSchema, parse_prisma_schema
from ..logging_config import get_logger

logger = get_logger(__name__)

_TS_EXTS = (".ts", ".tsx")

# Seeded negative→canonical map for the recurring run-008/009/011 inventions
# (RUN_011 §3 Gap B). These are the canonical-name priors the LLM keeps emitting;
# the map is extended as new recurrences surface. A seeded rewrite is only applied
# by the step when the canonical target actually resolves on disk (NFR-3).
_KNOWN_INVENTIONS: dict[str, str] = {
    "@/lib/prisma": "@/lib/db",
    "@/lib/ai/client": "@/lib/ai/service",
}


@runtime_checkable
class TruthSource(Protocol):
    """The authoritative contract surface a name-repair step resolves against."""

    def prisma_fields(self, model: str) -> frozenset[str]:
        """Valid field names for *model*; empty frozenset if unknown/absent."""
        ...

    def module_paths(self) -> Mapping[str, str]:
        """Seeded invented-specifier → canonical-specifier map (explicit negatives)."""
        ...

    def resolvable_specifiers(self) -> frozenset[str]:
        """The set of `@/`-aliased import specifiers that resolve on disk."""
        ...


class LiveDiskTruthSource:
    """v1 ``TruthSource``: derives truth from the live schema + on-disk lib tree.

    Lazy + cached per instance: the Prisma schema is parsed once on first
    ``prisma_fields`` call; the resolvable-specifier set is enumerated once on
    first ``resolvable_specifiers`` call. A project missing ``prisma/schema.prisma``
    or a ``lib/`` tree degrades to empty results (never raises).
    """

    def __init__(self, project_root: Union[str, Path]):
        self._root = Path(project_root)
        self._schema: Optional[PrismaSchema] = None
        self._schema_loaded = False
        self._specifiers: Optional[frozenset[str]] = None

    def _schema_or_none(self) -> Optional[PrismaSchema]:
        if not self._schema_loaded:
            self._schema_loaded = True
            path = self._root / "prisma" / "schema.prisma"
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                logger.debug("No prisma schema at %s; prisma truth is empty", path)
                self._schema = None
            else:
                schema = parse_prisma_schema(text)
                self._schema = schema if schema.models else None
        return self._schema

    def prisma_fields(self, model: str) -> frozenset[str]:
        schema = self._schema_or_none()
        if schema is None:
            return frozenset()
        m = schema.model(model)
        return m.field_names if m is not None else frozenset()

    def module_paths(self) -> Mapping[str, str]:
        return dict(_KNOWN_INVENTIONS)

    def resolvable_specifiers(self) -> frozenset[str]:
        if self._specifiers is None:
            self._specifiers = frozenset(self._enumerate_specifiers())
        return self._specifiers

    def _enumerate_specifiers(self) -> Set[str]:
        """Map on-disk `lib/**/*.{ts,tsx}` files to their `@/lib/...` specifiers.

        Mirrors the `@/` alias resolution used by
        ``cross_file_imports._resolves_on_disk`` (root and ``src/`` bases). An
        ``index`` file contributes both its full path and the directory form.
        """
        out: Set[str] = set()
        for ab in ("", "src"):
            base = (self._root / ab) if ab else self._root
            lib_dir = base / "lib"
            if not lib_dir.is_dir():
                continue
            for f in lib_dir.rglob("*"):
                if f.suffix not in _TS_EXTS or not f.is_file():
                    continue
                try:
                    rel = f.relative_to(base)
                except ValueError:
                    continue
                spec = "@/" + rel.with_suffix("").as_posix()
                if spec.endswith("/index"):
                    out.add(spec[: -len("/index")])
                out.add(spec)
        return out


class ArtifactTruthSource:
    """FR-10 swap point: an Approach-A ``forward_project_knowledge.json`` backend.

    Interface-only until Approach A ships; documents the seam so the repair steps
    depend on the :class:`TruthSource` protocol rather than the live producer.
    """

    def __init__(self, artifact_path: Union[str, Path]):
        self._artifact_path = Path(artifact_path)

    def prisma_fields(self, model: str) -> frozenset[str]:
        raise NotImplementedError(
            "ArtifactTruthSource: Approach-A forward_project_knowledge.json backend "
            "is not yet shipped (FR-10)."
        )

    def module_paths(self) -> Mapping[str, str]:
        raise NotImplementedError(
            "ArtifactTruthSource: Approach-A forward_project_knowledge.json backend "
            "is not yet shipped (FR-10)."
        )

    def resolvable_specifiers(self) -> frozenset[str]:
        raise NotImplementedError(
            "ArtifactTruthSource: Approach-A forward_project_knowledge.json backend "
            "is not yet shipped (FR-10)."
        )
