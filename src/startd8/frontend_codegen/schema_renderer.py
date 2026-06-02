"""Deterministic Prisma→Zod field rendering (Inc 1).

Pure, no-LLM rendering of a single Prisma field to its Zod base expression, plus the
per-model scalar field-set projection. Reuses:

- `languages/prisma_parser` for the parse (the source-ordered `PrismaField` tuple), and
- `contractors/project_knowledge`'s `FieldSpec`/`FieldSetAuthority` for the field-set
  authority (FR-13) — so the *generation* path and the *injection* (CKG) path share ONE
  projection of "what scalar fields an entity has." No second source of truth.

Scope (Inc 1): the base scalar/enum/list/optionality mapping (the FR-2 fidelity matrix's
base layer) + a field-completeness guard against the lenient parser's silent drops. The
convention layer (format hints, `@default`/`@id` semantics), file assembly, and the
symmetry/fidelity gates land in later increments.

Known gap (deferred): composite ``type`` blocks are stored by `parse_prisma_schema` in
the same ``models`` dict as real models with no kind marker (`prisma_parser.py:291`), so
``model_field_sets`` currently treats a composite ``type`` as a model. strtd8 has none;
composite handling (render inline / flag, never a phantom top-level schema) is a later
increment that needs the parser to expose block kind.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..contractors.project_knowledge.models import FieldSpec, FieldSetAuthority
from ..languages.prisma_parser import (
    PrismaField,
    PrismaSchema,
    parse_prisma_schema,
)
from .conventions import DEFAULT_CONVENTIONS, FieldConventions

# Internal reuse: block-body iteration + comment stripping for the completeness guard.
# These are the exact primitives `parse_prisma_schema` uses, so the guard counts lines
# the same way the parser sees them.
from ..languages.prisma_parser import _iter_blocks, _strip_comments

# Prisma scalar -> Zod base expression (FR-2 fidelity matrix, base layer).
SCALAR_MAP: Dict[str, str] = {
    "String": "z.string()",
    "Boolean": "z.boolean()",
    "Int": "z.number().int()",
    "BigInt": "z.number().int()",
    "Float": "z.number()",
    "Decimal": "z.string()",  # money-safe string (FR-2); the symmetry checker's Decimal
    # acceptance set is widened to include "string" in a later increment.
    "DateTime": "z.string().datetime()",
    "Json": "z.unknown()",
    "Bytes": "z.string()",
}


@dataclass(frozen=True)
class UnrenderableField:
    """A scalar field whose Prisma type has no deterministic Zod rendering.

    Per the FR-1/FR-2 failure policy these are *flagged*, not raised — one exotic field
    must not block rendering the other models.
    """

    entity: str
    field: str
    prisma_type: str
    reason: str


def _enum_base(values: Tuple[str, ...]) -> str:
    inner = ", ".join(f'"{v}"' for v in values)
    return f"z.enum([{inner}])"


def _zod_base_type(field: PrismaField, schema: PrismaSchema) -> Optional[str]:
    """The bare Zod type for a field — **no** list wrap, hint, or optionality.

    ``String``→``z.string()``, ``Int``→``z.number().int()``, an enum→``z.enum([...])``,
    etc. Returns ``None`` for an unknown/unsupported type (caller flags it). This is the
    single place a Prisma type maps to a Zod type; the decorators are layered on top by
    :func:`render_field_base` / :func:`render_field`.
    """
    if field.type in SCALAR_MAP:
        return SCALAR_MAP[field.type]
    if field.type in schema.enums:
        return _enum_base(schema.enums[field.type])
    return None


def render_field_base(field: PrismaField, schema: PrismaSchema) -> Optional[str]:
    """Render a field's Zod expression **without** convention hints, or ``None``.

    Decorator layering is fixed and deterministic: **base type → list wrap
    (``z.array(...)``) → optionality (``.nullable()``)**. So ``Int?`` →
    ``z.number().int().nullable()`` and a string list → ``z.array(z.string())``.

    Relations must be excluded by the caller (use ``schema.scalar_fields``). An unknown /
    unsupported type returns ``None`` so the caller can flag it (no hard-fail, FR-1/FR-2).
    """
    base = _zod_base_type(field, schema)
    if base is None:
        return None
    if field.is_list:
        base = f"z.array({base})"
    if field.is_optional:
        base = f"{base}.nullable()"
    return base


def render_field(
    field: PrismaField,
    schema: PrismaSchema,
    conventions: FieldConventions = DEFAULT_CONVENTIONS,
) -> Optional[str]:
    """Render a field's full Zod expression, including convention format hints, or ``None``.

    Layering (deterministic, and the **order matters** — the symmetry gate is blind to
    most of it): **base type → format hint (`.email()`/`.url()`, String-only) → list wrap
    → optionality (`.nullable()`)**. So ``email String?`` → ``z.string().email().nullable()``
    and ``url String`` → ``z.string().url()``.

    Nullability is driven **only** by the Prisma ``?`` modifier — never by ``@default`` —
    so a defaulted field (``ownerId String @default("local")``) renders required
    ``z.string()`` (R2-F9). Returns ``None`` for an unrenderable type (caller flags it).
    """
    base = _zod_base_type(field, schema)
    if base is None:
        return None
    if not field.is_list:
        hint = conventions.format_hint(field)  # String-only, type-guarded
        if hint:
            base = f"{base}{hint}"
    if field.is_list:
        base = f"z.array({base})"
    if field.is_optional:
        base = f"{base}.nullable()"
    return base


def model_field_sets(
    schema: PrismaSchema, source_file: str = ""
) -> Tuple[FieldSetAuthority, ...]:
    """Per-model scalar field sets in **schema source order** (FR-4 determinism).

    Uses ``schema.scalar_fields`` — the SAME projection the injection path's
    ``DraftModeProducer._field_sets`` uses (FR-13) — so the two never diverge. Unlike the
    producer it preserves **source order** (``schema.models`` is an insertion-ordered
    dict) and keeps **every** model including join tables (their FK columns are real
    scalars); it does not sort alphabetically or drop empties. The renderer must never
    iterate a ``set``/``frozenset`` for ordering (FR-4 / R4-F6).
    """
    out: List[FieldSetAuthority] = []
    for name in schema.models:  # dict preserves source/declaration order
        scalars = schema.scalar_fields(name)
        specs = tuple(
            FieldSpec(
                name=f.name, type=f.type, optional=f.is_optional, is_list=f.is_list
            )
            for f in scalars
        )
        out.append(
            FieldSetAuthority(entity=name, fields=specs, source_file=source_file)
        )
    return tuple(out)


def unrenderable_fields(schema: PrismaSchema) -> Tuple[UnrenderableField, ...]:
    """Every scalar field with no deterministic Zod rendering, across all models.

    Aggregated (not fail-fast) so an operator fixes them in one pass (FR-2 / R4-S11).
    """
    out: List[UnrenderableField] = []
    for name in schema.models:
        for f in schema.scalar_fields(name):
            if render_field_base(f, schema) is None:
                out.append(
                    UnrenderableField(
                        entity=name,
                        field=f.name,
                        prisma_type=f.type,
                        reason="no Zod mapping for Prisma type",
                    )
                )
    return tuple(out)


_HEADER_TEMPLATE = (
    "// GENERATED from {source_file} — do not edit by hand; "
    "regenerate via `startd8 generate frontend`.\n"
    "// Source of truth: the Prisma schema.\n"
    "// schema-sha256: {sha}"
)


@dataclass(frozen=True)
class RenderResult:
    """The rendered Zod-schema file plus its provenance and any flagged fields."""

    text: str
    schema_sha256: str
    unrenderable: Tuple[UnrenderableField, ...]


def schema_sha256(schema_text: str) -> str:
    """Stable content hash of the schema, embedded in the header for FR-11 staleness."""
    return hashlib.sha256((schema_text or "").encode("utf-8")).hexdigest()


def _render_object_block(
    name: str, schema: PrismaSchema, conventions: FieldConventions
) -> Tuple[str, List[UnrenderableField]]:
    """Render one ``export const <Name>Schema = z.object({...})`` block.

    An unrenderable field is emitted as ``z.unknown()`` with an inline ``UNRENDERABLE``
    marker (never silently dropped — FR-1) and reported in the returned list (FR-2/R4-S5).
    """
    lines = [f"export const {name}Schema = z.object({{"]
    flagged: List[UnrenderableField] = []
    for f in schema.scalar_fields(name):
        expr = render_field(f, schema, conventions)
        if expr is None:
            lines.append(
                f"  {f.name}: z.unknown(),  // UNRENDERABLE: Prisma type "
                f"'{f.type}' has no deterministic Zod mapping"
            )
            flagged.append(
                UnrenderableField(
                    entity=name,
                    field=f.name,
                    prisma_type=f.type,
                    reason="no Zod mapping for Prisma type",
                )
            )
        else:
            lines.append(f"  {f.name}: {expr},")
    lines.append("});")
    return "\n".join(lines), flagged


def render_zod_schema(
    schema_text: str,
    source_file: str = "prisma/schema.prisma",
    conventions: FieldConventions = DEFAULT_CONVENTIONS,
    emit_infer: bool = True,
) -> RenderResult:
    """Assemble the full Zod-schema file from a Prisma schema (FR-1, FR-4).

    Emits, in **schema source order** (deterministic, byte-stable): a GENERATED header
    with an embedded ``schema-sha256``; ``import { z } from "zod";``; one
    ``export const <Model>Schema = z.object({...})`` per model (join tables **included**);
    and, when ``emit_infer`` (default), one ``export type <Model> = z.infer<...>`` alias
    per model (the committed file ships these — FR-9 byte-equality needs them, R4-F4).

    The composite ``ValueModelSchema`` aggregate is **not** produced — it is not derivable
    from any single Prisma model and is out of v1 scope (FR-9). Unrenderable fields are
    flagged in the result, never raised (FR-2).
    """
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)

    flagged: List[UnrenderableField] = []
    blocks: List[str] = []
    for name in schema.models:  # source/declaration order
        block, block_flagged = _render_object_block(name, schema, conventions)
        blocks.append(block)
        flagged.extend(block_flagged)

    sections: List[str] = [
        _HEADER_TEMPLATE.format(source_file=source_file, sha=sha),
        'import { z } from "zod";',
    ]
    if blocks:
        sections.append("\n\n".join(blocks))
    if emit_infer and schema.models:
        sections.append(
            "\n".join(
                f"export type {name} = z.infer<typeof {name}Schema>;"
                for name in schema.models
            )
        )

    text = "\n\n".join(sections) + "\n"
    return RenderResult(text=text, schema_sha256=sha, unrenderable=tuple(flagged))


def field_completeness_issues(schema_text: str) -> Tuple[str, ...]:
    """Surface models where the parser dropped a field-shaped line (FR-1 invariant).

    ``parse_prisma_schema`` is lenient and **silently skips** lines its field regex can't
    match (`prisma_parser.py:282`); a render built on the parsed result could then omit a
    column with no error. This guard re-scans each block body (using the parser's own
    comment-stripping + block iteration) and reports any model whose parsed field count is
    **less than** its count of field-shaped lines, so a silent drop is never mistaken for
    a complete render.
    """
    schema = parse_prisma_schema(schema_text)
    issues: List[str] = []
    for kind, name, body in _iter_blocks(_strip_comments(schema_text or "")):
        if kind not in ("model", "type"):
            continue
        shaped = 0
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.startswith("@@") or line.startswith("}"):
                continue
            shaped += 1
        model = schema.models.get(name)
        parsed = len(model.fields) if model is not None else 0
        if parsed < shaped:
            issues.append(
                f"{name}: parsed {parsed} field(s) but body has {shaped} field-shaped "
                f"line(s) — {shaped - parsed} silently dropped"
            )
    return tuple(issues)
