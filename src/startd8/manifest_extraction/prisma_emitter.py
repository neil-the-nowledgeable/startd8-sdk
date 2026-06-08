"""§2.1 Prisma emitter (DRAFT mode) — render an :class:`EntityGraph` back out as ``schema.prisma``.

The deferred half of FR-WPI-8: the *writer* that makes ``schema.prisma`` a **derived** artifact
(today the doc-derived graph is only DIFF'd against the live contract — see
``entities.diff_against_live``). Slice 1 covers **FR-PE-1/2/3**:

- **FR-PE-1** — one ``model`` block per entity + per join, with the verbatim datasource/generator
  header, in stable declaration order; round-trips through ``parse_prisma_schema``.
- **FR-PE-2** — inject the six implicit bookkeeping fields (never authored in the doc tables) with
  exact attributes, on **every** model (entity *and* join — the live join tables carry them too).
- **FR-PE-3** — relationships by convention from ``graph.joins`` + ``graph.fk_parents``: join
  models (FK scalars + ``@relation(... onDelete: Cascade)`` + compound ``@@unique``), the
  reverse-relation list fields on each side, and ``belongs to`` / ``has`` parent FKs + their
  reverse lists.

Out of slice 1 (FR-PE-5, needs the OQ-PE-1/2/3 grammar decisions): non-bookkeeping ``@default``,
explicit ``@@index`` / compound ``@@unique`` on non-join entities, and the loose-reference (no-FK)
marker. Fields whose ``prisma_type`` is ``None`` (outside the plain-type vocabulary) are flagged,
never emitted wrong (the FR-WPI ``not_extracted`` discipline).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from ..backend_codegen._headers import header_standard
from ..frontend_codegen.schema_renderer import schema_sha256
from .entities import DocEntity, EntityGraph, JoinModel, _lower_camel

# The datasource/generator block — verbatim from the live strtd8 contract (FR-PE-1). SQLite, the
# locked target (no native JSON/enum reliance); url from the DATABASE_URL env var.
_PRISMA_PREAMBLE = (
    "generator client {\n"
    '  provider = "prisma-client-js"\n'
    "}\n\n"
    "datasource db {\n"
    '  provider = "sqlite"\n'
    '  url      = env("DATABASE_URL")\n'
    "}"
)

# The six implicit bookkeeping fields (FR-PE-2) — never sourced from the doc tables, identical on
# every model. Order + attributes match the live contract exactly.
_BOOKKEEPING: Tuple[Tuple[str, str], ...] = (
    ("id", "String   @id @default(cuid())"),
    ("ownerId", "String   @default(\"local\")"),
    ("source", "String   @default(\"user\")"),
    ("confirmed", "Boolean  @default(true)"),
    ("createdAt", "DateTime @default(now())"),
    ("updatedAt", "DateTime @updatedAt"),
)


@dataclass(frozen=True)
class UnrenderableField:
    """A field flagged out (type outside the plain-type vocabulary) — never emitted wrong."""

    entity: str
    field: str
    reason: str


@dataclass(frozen=True)
class PrismaSchemaResult:
    text: str
    schema_sha256: str
    models_rendered: int
    unrenderable: Tuple[UnrenderableField, ...]


def _plural(name: str) -> str:
    """A reverse-relation list field name: lowerCamel plural (``Capability`` → ``capabilities``)."""
    base = _lower_camel(name)
    return base[:-1] + "ies" if base.endswith("y") else base + "s"


def _relation_attr(fk: str) -> str:
    return f"@relation(fields: [{fk}], references: [id], onDelete: Cascade)"


def _field_line(name: str, body: str) -> str:
    return f"  {name} {body}"


def _model_block(name: str, lines: List[str]) -> str:
    return f"model {name} {{\n" + "\n".join(lines) + "\n}"


def render_prisma_schema(
    graph: EntityGraph, source_file: str = "prisma/schema.prisma"
) -> PrismaSchemaResult:
    """Render ``schema.prisma`` from the doc-derived :class:`EntityGraph` (FR-PE-1/2/3, $0)."""
    unrenderable: List[UnrenderableField] = []

    # --- precompute relationship-derived members keyed by entity name (FR-PE-3) -----------------
    rev_lists: Dict[str, List[Tuple[str, str]]] = {n: [] for n in graph.entities}
    fk_blocks: Dict[str, List[Tuple[str, str]]] = {n: [] for n in graph.entities}

    # belongs-to / has: child carries `<parent>Id` + a relation object; parent gets a reverse list.
    for child, parents in graph.fk_parents.items():
        for parent in parents:
            fk = f"{_lower_camel(parent)}Id"
            fk_blocks.setdefault(child, []).append((fk, "String"))
            fk_blocks[child].append((_lower_camel(parent), f"{parent} {_relation_attr(fk)}"))
            rev_lists.setdefault(parent, []).append((_plural(child), f"{child}[]"))

    # M2M join: each side gets a reverse list typed by the join model.
    for j in graph.joins:
        rev_lists.setdefault(j.left, []).append((_plural(j.right), f"{j.name}[]"))
        rev_lists.setdefault(j.right, []).append((_plural(j.left), f"{j.name}[]"))

    blocks: List[str] = []

    # --- entity models -------------------------------------------------------------------------
    for name, ent in graph.entities.items():
        lines = [_field_line(fn, body) for fn, body in _BOOKKEEPING]
        lines.append("")  # readability gap between bookkeeping and domain fields
        for f in ent.fields:
            if f.prisma_type is None:
                unrenderable.append(UnrenderableField(name, f.name, "type outside plain-type vocabulary"))
                continue
            opt = "" if f.required else "?"
            lines.append(_field_line(f.name, f"{f.prisma_type}{opt}"))
        for fk, body in fk_blocks.get(name, []):
            lines.append(_field_line(fk, body))
        for lf, body in rev_lists.get(name, []):
            lines.append(_field_line(lf, body))
        blocks.append(_model_block(name, lines))

    # --- join models (FR-PE-3): bookkeeping + two FK + two relation objects + compound @@unique --
    for j in graph.joins:
        lines = [_field_line(fn, body) for fn, body in _BOOKKEEPING]
        lines.append("")
        lines.append(_field_line(j.fk_left, "String"))
        lines.append(_field_line(j.fk_right, "String"))
        lines.append(_field_line(_lower_camel(j.left), f"{j.left} {_relation_attr(j.fk_left)}"))
        lines.append(_field_line(_lower_camel(j.right), f"{j.right} {_relation_attr(j.fk_right)}"))
        lines.append(f"  @@unique([{j.fk_left}, {j.fk_right}])")
        blocks.append(_model_block(j.name, lines))

    body = _PRISMA_PREAMBLE + "\n\n" + "\n\n".join(blocks) + "\n"
    sha = schema_sha256(body)
    header = header_standard(source_file, sha, "prisma-schema")
    text = header + "\n\n" + body
    return PrismaSchemaResult(
        text=text,
        schema_sha256=sha,
        models_rendered=len(graph.entities) + len(graph.joins),
        unrenderable=tuple(unrenderable),
    )
