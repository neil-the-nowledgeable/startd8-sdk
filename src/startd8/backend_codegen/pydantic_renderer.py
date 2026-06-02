"""Deterministic Prisma→Pydantic field rendering (Python contract-codegen, Step 1).

Pure, no-LLM projection of a ``.prisma`` schema to a Pydantic v2 models file — the Python
sibling of ``frontend_codegen.schema_renderer`` (Prisma→Zod). Reuses, deliberately:

- ``languages/prisma_parser`` for the parse (the source-ordered ``PrismaField`` tuple), so the
  ``.prisma`` schema stays the **single neutral contract IDL** (OQ-7); Pydantic is a *projection*
  of it, exactly as Zod is.
- the **stack-neutral** helpers from ``frontend_codegen.schema_renderer`` —
  ``schema_sha256`` (header staleness hash), ``composite_type_names`` /
  ``field_completeness_issues`` (parser-level guards), and the ``UnrenderableField`` flag type —
  so there is no second source of truth for "what scalar fields an entity has" or how the schema
  is hashed.

What is **new** here (the only Python-specific surface): the Prisma→Python scalar map, the
annotation layering (base → ``list[...]`` → ``Optional[...]``), the import-block synthesis, and a
``#``-comment GENERATED header (a ``.py`` file cannot carry the TS ``//`` header, which is why
drift is mirrored, not reused — see ``drift.py``).

Scope (Step 1): Pydantic ``BaseModel`` classes only. SQLModel table emission (FR-2), CRUD, and
HTMX templates land in later steps. Enums render inline as ``Literal[...]`` (mirroring the Zod
inline ``z.enum([...])``) rather than generating separate ``Enum`` classes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from ..frontend_codegen.schema_renderer import (
    UnrenderableField,
    composite_type_names,
    schema_sha256,
)
from ..languages.prisma_parser import PrismaField, PrismaSchema, parse_prisma_schema

# Prisma scalar -> Python/Pydantic base type. The money-safe choice differs from the Zod path
# (which uses a string): Pydantic's native ``Decimal`` is the money-safe type in Python.
_PY_SCALAR: Dict[str, str] = {
    "String": "str",
    "Boolean": "bool",
    "Int": "int",
    "BigInt": "int",
    "Float": "float",
    "Decimal": "Decimal",
    "DateTime": "datetime",
    "Json": "Any",
    "Bytes": "bytes",
}

# A base type token -> the import it requires (only the non-builtins).
_IMPORT_FOR: Dict[str, Tuple[str, str]] = {
    "Decimal": ("decimal", "Decimal"),
    "datetime": ("datetime", "datetime"),
    "Any": ("typing", "Any"),
    "Literal": ("typing", "Literal"),
    "Optional": ("typing", "Optional"),
}


@dataclass(frozen=True)
class PydanticRenderResult:
    """The rendered Pydantic-models file plus provenance, flagged fields, and stats.

    The integer stats are deterministic counts (telemetry, NFR-6); they do not affect ``text``.
    """

    text: str
    schema_sha256: str
    unrenderable: Tuple[UnrenderableField, ...]
    models_rendered: int = 0
    fields_rendered: int = 0


def _py_base_type(
    field: PrismaField, schema: PrismaSchema, needs: Set[str]
) -> Optional[str]:
    """The bare Python type for a field — **no** list wrap or optionality. ``None`` if unmappable.

    Records any non-builtin token it uses in *needs* so the caller can synthesize imports.
    """
    if field.type in _PY_SCALAR:
        base = _PY_SCALAR[field.type]
        if base in _IMPORT_FOR:
            needs.add(base)
        return base
    if field.type in schema.enums:
        needs.add("Literal")
        inner = ", ".join(f'"{v}"' for v in schema.enums[field.type])
        return f"Literal[{inner}]"
    return None


def render_field_annotation(
    field: PrismaField, schema: PrismaSchema, needs: Set[str]
) -> Optional[str]:
    """Render a field's full Python type annotation, or ``None`` if unmappable.

    Layering is fixed and deterministic: **base type → list wrap (``list[...]``) → optionality
    (``Optional[...]``)**. So ``Int?`` → ``Optional[int]`` and a ``String[]`` → ``list[str]``.
    Nullability is driven **only** by the Prisma ``?`` modifier (never by ``@default``).
    """
    base = _py_base_type(field, schema, needs)
    if base is None:
        return None
    if field.is_list:
        base = f"list[{base}]"
    if field.is_optional:
        needs.add("Optional")
        base = f"Optional[{base}]"
    return base


def _render_class_block(
    name: str, schema: PrismaSchema, needs: Set[str]
) -> Tuple[str, List[UnrenderableField]]:
    """Render one ``class <Name>Schema(BaseModel):`` block.

    An unmappable field is emitted as ``<name>: Any  # UNRENDERABLE: ...`` (never silently
    dropped — FR-1) and reported in the returned list. An empty model emits ``pass``.
    """
    lines = [f"class {name}Schema(BaseModel):"]
    flagged: List[UnrenderableField] = []
    scalars = schema.scalar_fields(name)
    if not scalars:
        lines.append("    pass")
        return "\n".join(lines), flagged
    for f in scalars:
        ann = render_field_annotation(f, schema, needs)
        if ann is None:
            needs.add("Any")
            lines.append(
                f"    {f.name}: Any  # UNRENDERABLE: Prisma type "
                f"'{f.type}' has no deterministic Python mapping"
            )
            flagged.append(
                UnrenderableField(
                    entity=name,
                    field=f.name,
                    prisma_type=f.type,
                    reason="no Python mapping for Prisma type",
                )
            )
        else:
            default = " = None" if f.is_optional else ""
            lines.append(f"    {f.name}: {ann}{default}")
    return "\n".join(lines), flagged


def _import_block(needs: Set[str]) -> str:
    """Synthesize the deterministic import block from the set of used tokens.

    Grouped per isort convention: ``__future__`` / stdlib (datetime, decimal, typing) / pydantic.
    """
    groups: List[List[str]] = [["from __future__ import annotations"]]

    stdlib: List[str] = []
    if "datetime" in needs:
        stdlib.append("from datetime import datetime")
    if "Decimal" in needs:
        stdlib.append("from decimal import Decimal")
    typing_names = sorted(n for n in ("Any", "Literal", "Optional") if n in needs)
    if typing_names:
        stdlib.append(f"from typing import {', '.join(typing_names)}")
    if stdlib:
        groups.append(stdlib)

    groups.append(["from pydantic import BaseModel"])
    return "\n\n".join("\n".join(g) for g in groups)


_HEADER_TEMPLATE = (
    "# GENERATED from {source_file} — do not edit by hand; "
    "regenerate via `startd8 generate backend`.\n"
    "# Source of truth: the Prisma schema.\n"
    "# schema-sha256: {sha}"
)


def render_pydantic_models(
    schema_text: str,
    source_file: str = "prisma/schema.prisma",
) -> PydanticRenderResult:
    """Assemble the full Pydantic-models file from a ``.prisma`` schema (FR-1).

    Emits, in **schema source order** (deterministic, byte-stable): a ``#`` GENERATED header with
    an embedded ``schema-sha256``; the synthesized import block; and one
    ``class <Model>Schema(BaseModel)`` per model (join tables **included**, composite ``type``
    blocks **excluded** — they are not top-level schemas). Unmappable fields are flagged in the
    result, never raised (FR-1). The ``schema-sha256`` is taken over the **verbatim**
    ``schema_text`` bytes — pass the same bytes to ``--check`` (so a re-normalized schema hashes
    differently and reads as stale).
    """
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    composites = composite_type_names(schema_text)

    needs: Set[str] = set()
    flagged: List[UnrenderableField] = []
    blocks: List[str] = []
    model_names = [n for n in schema.models if n not in composites]
    for name in model_names:  # source/declaration order, composites excluded
        block, block_flagged = _render_class_block(name, schema, needs)
        blocks.append(block)
        flagged.extend(block_flagged)

    header = _HEADER_TEMPLATE.format(source_file=source_file, sha=sha)
    imports = _import_block(needs)
    classes = "\n\n\n".join(blocks)

    if blocks:
        text = header + "\n\n" + imports + "\n\n\n" + classes + "\n"
    else:
        text = header + "\n\n" + imports + "\n"

    fields_rendered = sum(len(schema.scalar_fields(n)) for n in model_names)
    return PydanticRenderResult(
        text=text,
        schema_sha256=sha,
        unrenderable=tuple(flagged),
        models_rendered=len(model_names),
        fields_rendered=fields_rendered,
    )
