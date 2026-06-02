"""Acceptance gates (Inc 4).

Two checks the renderer's output must pass *by construction* (FR-3 / FR-3b):

- :func:`assert_symmetric` — the existing ``prisma_zod_symmetry`` checker, called with its
  **real signature** (parsed objects, order ``(prisma, zod)``). It catches invented fields
  and concrete type mismatches.
- :func:`verify_render_fidelity` — an **independent** check of exactly what the symmetry
  gate is provably blind to (`prisma_zod_symmetry.py:252-348`): per-field optionality,
  ``.int()`` for ``Int``, ``z.array(...)`` for lists, ``z.enum([exact values])`` for enums,
  format hints, and field **count + order**. It re-parses the rendered *text* against the
  schema, so it would catch a renderer regression the symmetry gate waves through.

Together they make FR-3's "by construction" sound: the symmetry gate alone is necessary but
not sufficient.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from ..languages.prisma_parser import parse_prisma_schema
from ..validators.prisma_zod_symmetry import (
    SymmetryViolation,
    check_prisma_zod_symmetry,
    extract_zod_objects,
)
from .conventions import DEFAULT_CONVENTIONS, FieldConventions

_SCHEMA_OPEN = re.compile(r"export const (\w+)Schema = z\.object\(\{")
_FIELD_LINE = re.compile(r"^(\w+):\s*(.+)$")


def assert_symmetric(
    rendered: str,
    schema_text: str,
    entity_map: Optional[Dict[str, str]] = None,
) -> List[SymmetryViolation]:
    """Run the Prisma↔Zod symmetry checker on rendered output (FR-3).

    Calls the checker with its real signature — parsed ``PrismaSchema`` and the extracted
    ``z.object`` map, in ``(prisma, zod)`` order — not raw text (R1-S1).
    """
    prisma = parse_prisma_schema(schema_text)
    zod = extract_zod_objects(rendered)
    return check_prisma_zod_symmetry(prisma, zod, entity_map=entity_map)


def _extract_field_exprs(rendered: str) -> Dict[str, List[Tuple[str, str]]]:
    """Parse the rendered file into ``{EntityName: [(field, zod_expr), ...]}`` in order.

    Independent of the renderer internals — it reads the emitted text, so it can detect a
    render that dropped a decorator the symmetry gate ignores.
    """
    out: Dict[str, List[Tuple[str, str]]] = {}
    lines = rendered.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        m = _SCHEMA_OPEN.search(lines[i])
        if not m:
            i += 1
            continue
        entity = m.group(1)
        fields: List[Tuple[str, str]] = []
        i += 1
        while i < n and not lines[i].strip().startswith("});"):
            raw = lines[i].strip()
            code = raw.split("//", 1)[0].strip().rstrip(",").strip()
            fm = _FIELD_LINE.match(code)
            if fm:
                fields.append((fm.group(1), fm.group(2).strip()))
            i += 1
        out[entity] = fields
    return out


def verify_render_fidelity(
    rendered: str,
    schema_text: str,
    conventions: FieldConventions = DEFAULT_CONVENTIONS,
) -> List[str]:
    """Assert the dimensions the symmetry gate ignores (FR-3b). Returns a list of issues.

    For each model, against the parsed schema: field **count + order** match; optional ⇔
    ``.nullable()``; ``Int`` ⇒ ``.int()``; list ⇒ ``z.array(``; enum ⇒ ``z.enum`` with every
    declared value; convention format hint present when the rule fires.
    """
    schema = parse_prisma_schema(schema_text)
    exprs = _extract_field_exprs(rendered)
    issues: List[str] = []

    for name in schema.models:
        scalars = schema.scalar_fields(name)
        got = exprs.get(name)
        if got is None:
            issues.append(f"{name}: schema absent from rendered output")
            continue
        got_names = [fn for fn, _ in got]
        exp_names = [f.name for f in scalars]
        if got_names != exp_names:
            issues.append(
                f"{name}: field set/order mismatch — expected {exp_names}, got {got_names}"
            )
            continue
        by_name = dict(got)
        for f in scalars:
            expr = by_name[f.name]
            if f.is_optional and ".nullable()" not in expr:
                issues.append(f"{name}.{f.name}: optional field missing .nullable()")
            if not f.is_optional and ".nullable()" in expr:
                issues.append(f"{name}.{f.name}: required field has .nullable()")
            if f.type == "Int" and ".int()" not in expr:
                issues.append(f"{name}.{f.name}: Int field missing .int()")
            if f.is_list and "z.array(" not in expr:
                issues.append(f"{name}.{f.name}: list field missing z.array(")
            if f.type in schema.enums:
                if "z.enum(" not in expr:
                    issues.append(
                        f"{name}.{f.name}: enum not rendered as z.enum([...])"
                    )
                else:
                    for value in schema.enums[f.type]:
                        if f'"{value}"' not in expr:
                            issues.append(
                                f"{name}.{f.name}: enum missing value '{value}'"
                            )
            hint = conventions.format_hint(f)
            if hint and hint not in expr:
                issues.append(f"{name}.{f.name}: missing convention hint {hint}")
    return issues
