"""Deterministic Prisma→SQLModel table rendering (Python contract-codegen, Step 2 / FR-2).

Co-projects the same ``.prisma`` contract (the neutral IDL) into **SQLModel table classes** — the
persistence layer — alongside the Step 1 pure-Pydantic ``models.py`` (the API/validation/AI-tool
contract). Both are generated from one schema, so "nothing is hand-typed twice". Reuses the
Step 1 scalar map / import machinery and the stack-neutral ``schema_sha256`` /
``composite_type_names`` helpers.

**OQ-3 decision (v1):** one ``class X(SQLModel, table=True)`` per entity, serving as both the table
and the canonical persisted contract. The ``Base``/``Create``/``Read`` DTO hierarchy is **deferred**
(a documented refinement for when the CRUD edge must hide server-set fields).

Scope (Step 2): primary keys (``@id`` → ``Field(primary_key=True)``), scalar columns, enum classes
(``str, Enum``), and list scalars as JSON columns. **Deferred (flagged, not silent):** foreign-key
constraints + ``Relationship()`` — FK scalars render as plain columns for v1 (they function on
SQLite); proper FK wiring needs the ``@relation(fields:…, references:…)`` cross-field parse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Set, Tuple

from ..frontend_codegen.schema_renderer import (
    UnrenderableField,
    composite_type_names,
    schema_sha256,
)
from ..languages.prisma_parser import PrismaField, PrismaSchema, parse_prisma_schema
from .pydantic_renderer import _PY_SCALAR


@dataclass(frozen=True)
class SQLModelRenderResult:
    """The rendered SQLModel-tables file plus provenance, flagged fields, and stats."""

    text: str
    schema_sha256: str
    unrenderable: Tuple[UnrenderableField, ...]
    models_rendered: int = 0
    fields_rendered: int = 0
    enums_rendered: int = 0


def _base_type(
    field: PrismaField, schema: PrismaSchema, needs: Set[str], enums_used: Set[str]
) -> str:
    """Bare column type: a Python scalar, an enum **class name**, or ``Any`` (flagged) if unknown."""
    if field.type in _PY_SCALAR:
        base = _PY_SCALAR[field.type]
        if base in ("Decimal", "datetime", "Any"):
            needs.add(base)
        return base
    if field.type in schema.enums:
        enums_used.add(field.type)
        needs.add("Enum")
        return field.type
    needs.add("Any")
    return "Any"


def _render_table_field(
    field: PrismaField, schema: PrismaSchema, needs: Set[str], enums_used: Set[str]
) -> Tuple[str, bool]:
    """Render one ``    <name>: <ann>[ = ...]`` line. Returns (line, was_unrenderable)."""
    base = _base_type(field, schema, needs, enums_used)
    unrenderable = base == "Any" and field.type not in ("Json",)

    if field.is_list:
        needs.add("sqlalchemy")
        return (
            f"    {field.name}: list[{base}] = "
            f"Field(default_factory=list, sa_column=Column(JSON))",
            unrenderable,
        )
    if field.is_id:
        if field.is_optional:
            needs.add("Optional")
            return (
                f"    {field.name}: Optional[{base}] = Field(default=None, primary_key=True)",
                unrenderable,
            )
        return f"    {field.name}: {base} = Field(primary_key=True)", unrenderable
    if field.is_optional:
        needs.add("Optional")
        return f"    {field.name}: Optional[{base}] = None", unrenderable
    return f"    {field.name}: {base}", unrenderable


def _import_block(needs: Set[str]) -> str:
    """Synthesize the import block: __future__ / stdlib (datetime, decimal, enum, typing) /
    third-party (sqlalchemy, sqlmodel)."""
    groups: List[List[str]] = [["from __future__ import annotations"]]

    stdlib: List[str] = []
    if "datetime" in needs:
        stdlib.append("from datetime import datetime")
    if "Decimal" in needs:
        stdlib.append("from decimal import Decimal")
    if "Enum" in needs:
        stdlib.append("from enum import Enum")
    typing_names = sorted(n for n in ("Any", "Optional") if n in needs)
    if typing_names:
        stdlib.append(f"from typing import {', '.join(typing_names)}")
    if stdlib:
        groups.append(stdlib)

    third: List[str] = []
    if "sqlalchemy" in needs:
        third.append("from sqlalchemy import JSON, Column")
    third.append("from sqlmodel import Field, SQLModel")
    groups.append(third)

    return "\n\n".join("\n".join(g) for g in groups)


def _render_enum_class(name: str, values: Tuple[str, ...]) -> str:
    lines = [f"class {name}(str, Enum):"]
    for v in values:
        lines.append(f'    {v} = "{v}"')
    return "\n".join(lines)


_HEADER_TEMPLATE = (
    "# GENERATED from {source_file} — do not edit by hand; "
    "regenerate via `startd8 generate backend`.\n"
    "# startd8-artifact: sqlmodel-tables\n"
    "# Source of truth: the Prisma schema.\n"
    "# schema-sha256: {sha}"
)


def render_sqlmodel_tables(
    schema_text: str,
    source_file: str = "prisma/schema.prisma",
) -> SQLModelRenderResult:
    """Assemble the SQLModel-tables file from a ``.prisma`` schema (FR-2).

    Emits, in **schema source order**: a ``#`` GENERATED header (artifact ``sqlmodel-tables``) with
    the embedded ``schema-sha256``; the synthesized imports; one ``str, Enum`` class per **used**
    enum (declaration order); and one ``class <Model>(SQLModel, table=True)`` per model (composites
    excluded). List scalars become JSON columns; ``@id`` fields become primary keys. Unmappable
    scalar types are flagged in the result, never raised.
    """
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    composites = composite_type_names(schema_text)

    needs: Set[str] = set()
    enums_used: Set[str] = set()
    flagged: List[UnrenderableField] = []
    blocks: List[str] = []
    model_names = [n for n in schema.models if n not in composites]

    for name in model_names:
        scalars = schema.scalar_fields(name)
        lines = [f"class {name}(SQLModel, table=True):"]
        if not scalars:
            lines.append("    pass")
        for f in scalars:
            line, bad = _render_table_field(f, schema, needs, enums_used)
            lines.append(line)
            if bad:
                flagged.append(
                    UnrenderableField(
                        entity=name,
                        field=f.name,
                        prisma_type=f.type,
                        reason="no SQLModel column mapping for Prisma type",
                    )
                )
        blocks.append("\n".join(lines))

    # Enum classes, in schema declaration order, only those actually used.
    enum_blocks = [
        _render_enum_class(name, vals)
        for name, vals in schema.enums.items()
        if name in enums_used
    ]

    header = _HEADER_TEMPLATE.format(source_file=source_file, sha=sha)
    imports = _import_block(needs)
    body_blocks = enum_blocks + blocks
    body = "\n\n\n".join(body_blocks)

    if body_blocks:
        text = header + "\n\n" + imports + "\n\n\n" + body + "\n"
    else:
        text = header + "\n\n" + imports + "\n"

    fields_rendered = sum(len(schema.scalar_fields(n)) for n in model_names)
    return SQLModelRenderResult(
        text=text,
        schema_sha256=sha,
        unrenderable=tuple(flagged),
        models_rendered=len(model_names),
        fields_rendered=fields_rendered,
        enums_rendered=len(enum_blocks),
    )
