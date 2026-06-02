"""Owned skeleton planning (Inc 7 / FR-6, FR-7).

Decides — from the project's *detected* conventions — which mechanical artifacts to emit
as **owned** (deterministic, LLM never touches), and records the artifacts the project does
**not** use as an explicit anti-invention signal. v1 is **owned-only**; seeded route/page
shells are deferred (FR-7).

The one always-owned artifact is the Prisma→Zod schema-types file (the RUN-011 fix). The
directory skeleton is derived from the plan's file manifest (prevents the RUN-013
sub-namespace invention). Barrels / CSS-module stubs are **gated on convention detection**:
strtd8 uses neither, so the plan records "project does not use …" — which both avoids
generating them and signals the LLM not to invent them (the RUN-012 anti-invention).

Note: the design docs assumed reusable ``scaffold_barrel``/``scaffold_cofile`` helpers; those
do not exist in this repo, so the minimal deterministic emitters live here
(:func:`render_barrel`, :func:`render_css_module_stub`). A richer barrel-from-disk resolver
(which needs the sibling files' exports) is a follow-on; v1 emits the gating *decision* and
the schema-types artifact.
"""

from __future__ import annotations

import os
import posixpath
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple

from .conventions import ProjectConventions, detect_project_conventions
from .schema_renderer import UnrenderableField, render_zod_schema

# Artifact ownership/kind vocabularies (kept small + explicit).
OWNED = "owned"


@dataclass(frozen=True)
class SkeletonArtifact:
    """One planned output. ``content is None`` for a directory (a mkdir, not a file)."""

    path: str
    ownership: str  # currently always OWNED (seeded is v1-deferred)
    kind: str  # "schema" | "barrel" | "css" | "dir"
    content: Optional[str] = None


@dataclass(frozen=True)
class SkeletonPlan:
    """The owned-artifact plan plus the gating decisions and any flagged fields."""

    artifacts: Tuple[SkeletonArtifact, ...]
    conventions: ProjectConventions
    notes: Tuple[str, ...]  # explicit "project does not use X" anti-invention signals
    unrenderable: Tuple[UnrenderableField, ...]

    def files(self) -> Tuple[SkeletonArtifact, ...]:
        return tuple(a for a in self.artifacts if a.content is not None)

    def directories(self) -> Tuple[SkeletonArtifact, ...]:
        return tuple(a for a in self.artifacts if a.kind == "dir")


def render_barrel(module_stems: Sequence[str]) -> str:
    """A deterministic barrel: ``export * from "./<stem>";`` per stem, in given order."""
    return "".join(f'export * from "./{stem}";\n' for stem in module_stems)


def render_css_module_stub() -> str:
    """A minimal, deterministic CSS-module stub (empty `.root` rule)."""
    return ".root {\n}\n"


def _canonical_dirs(target_modules: Iterable[str]) -> Tuple[str, ...]:
    """Every ancestor directory implied by the file manifest, deduped + sorted.

    ``["lib/export/markdown.ts", "lib/export/json.ts"]`` → ``("lib", "lib/export")``. This is
    the deterministic directory skeleton that removes the RUN-013 sub-namespace invention:
    the LLM fills files into canonical dirs instead of inventing ``/renderers/``.
    """
    dirs: set[str] = set()
    for mod in target_modules:
        d = posixpath.dirname(mod.replace(os.sep, "/").lstrip("/"))
        while d:
            dirs.add(d)
            d = posixpath.dirname(d)
    return tuple(sorted(dirs))


def plan_frontend_skeleton(
    project_root: str | os.PathLike,
    schema_text: str,
    *,
    schema_out: str = "lib/value-model.ts",
    source_file: str = "prisma/schema.prisma",
    conventions: Optional[ProjectConventions] = None,
    target_modules: Sequence[str] = (),
) -> SkeletonPlan:
    """Plan the owned mechanical skeleton for a project (FR-6/FR-7, owned-only v1).

    Always includes the Prisma→Zod schema-types file (owned). Adds the directory skeleton
    from ``target_modules`` (RUN-013 prevention). Barrels/CSS are gated on detected
    conventions: when the project doesn't use them, the plan records an explicit
    anti-invention note rather than emitting anything (RUN-012).
    """
    conv = conventions or detect_project_conventions(project_root)

    artifacts: List[SkeletonArtifact] = []
    notes: List[str] = []

    rendered = render_zod_schema(schema_text, source_file=source_file)
    artifacts.append(
        SkeletonArtifact(
            path=schema_out, ownership=OWNED, kind="schema", content=rendered.text
        )
    )

    for directory in _canonical_dirs(target_modules):
        artifacts.append(
            SkeletonArtifact(path=directory, ownership=OWNED, kind="dir", content=None)
        )

    if not conv.uses_barrels:
        notes.append(
            "project does not use barrels — none generated; the LLM must not invent "
            "index re-export files (RUN-012 anti-invention)"
        )
    if not conv.uses_css_modules:
        notes.append(
            "project does not use CSS modules — none generated; the LLM must not invent "
            "*.module.css imports (RUN-012 anti-invention)"
        )

    return SkeletonPlan(
        artifacts=tuple(artifacts),
        conventions=conv,
        notes=tuple(notes),
        unrenderable=rendered.unrenderable,
    )
