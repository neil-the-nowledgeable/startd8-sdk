"""CKG Phase 2 — Knowledge Provider output model (REQ-CKG-520/521/523).

The ``ProjectKnowledge`` artifact is the deterministic, read-only contract surface
injected into a feature's spec prompt *before* generation. It is a structured
**view over the Phase-1 resolver** (`prisma_parser`, `upstream_interface`,
`tsconfig_paths`) — not a new scanner (CROSS_FILE §11).

Design note (REQ-CKG-523, D3): availability is modelled at the **artifact level**
via the explicit ``omissions`` tuple — mirroring the Phase-1 split where
availability lives on ``CrossFileResult.availability``, not on each ``Finding``.
An unavailable section is *stated*, never rendered as an empty authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ..upstream_interface import UpstreamInterface

__all__ = [
    "FieldSpec",
    "FieldSetAuthority",
    "EnumAuthority",
    "Negative",
    "ProjectKnowledge",
]


@dataclass(frozen=True)
class FieldSpec:
    """One scalar field of a Prisma entity (relations/list-relations excluded)."""

    name: str
    type: str  # Prisma base type, e.g. "String", "Float"
    optional: bool  # trailing ``?``
    is_list: bool  # trailing ``[]`` (scalar list, e.g. ``String[]``)

    def render(self) -> str:
        """``name: Type?`` — matches ``upstream_interface.render_prisma_field_sets``."""
        return f"{self.name}: {self.type}{'?' if self.optional else ''}"


@dataclass(frozen=True)
class FieldSetAuthority:
    """The authoritative field set for one entity a feature touches (REQ-CKG-521)."""

    entity: str
    fields: Tuple[FieldSpec, ...]
    source_file: str  # the schema.prisma the fields came from


@dataclass(frozen=True)
class EnumAuthority:
    """The authoritative value set for one Prisma enum (REQ-CKG-525).

    Retires hand-authored "use exactly these enum values" discipline blocks
    (e.g. ``subjectType`` ∈ {capability, outcome, …}; a P3 pipeline ``Stage`` enum).
    Sourced from the contract — the schema's ``enum`` blocks are the single truth.
    """

    name: str
    values: Tuple[str, ...]
    source_file: str


@dataclass(frozen=True)
class Negative:
    """An explicit negative: a recurring invention and its real replacement (D2)."""

    invented: str  # e.g. "@/lib/prisma"
    correct: str  # e.g. "@/lib/db"
    note: str = ""  # optional qualifier, e.g. "the Prisma client"


@dataclass(frozen=True)
class ProjectKnowledge:
    """The injectable contract surface for a project (or a feature-scoped subset).

    ``omissions`` is first-class (REQ-CKG-523): a missing schema/config is *stated*
    here, and the corresponding authority is simply absent — never rendered as
    ``use only these fields: (none)``.
    """

    project_root: str
    field_sets: Tuple[FieldSetAuthority, ...] = ()
    interfaces: Tuple[UpstreamInterface, ...] = ()
    negatives: Tuple[Negative, ...] = ()
    enums: Tuple[EnumAuthority, ...] = ()
    omissions: Tuple[str, ...] = ()

    @property
    def has_field_authority(self) -> bool:
        return bool(self.field_sets)

    def entities(self) -> Tuple[str, ...]:
        return tuple(fs.entity for fs in self.field_sets)
