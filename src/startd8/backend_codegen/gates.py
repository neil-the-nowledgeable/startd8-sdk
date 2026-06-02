"""Render-fidelity gate for the Prisma→Pydantic path (FR-9b).

The Python analog of ``frontend_codegen.gates.verify_render_fidelity``: re-extract each rendered
class's fields from the emitted text and assert they agree with the schema's scalar projection on
**field set + source order + optionality + list-ness**. This catches a renderer regression that a
byte-hash can't explain (it tells you *what* diverged, not just *that* it did). Returns a tuple of
human-readable issues — empty means the render is faithful.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from ..languages.prisma_parser import parse_prisma_schema
from .pydantic_renderer import composite_type_names

_CLASS_RE = re.compile(r"^class (\w+)Schema\(BaseModel\):$")
_FIELD_RE = re.compile(r"^    (\w+): (.+)$")


def _extract_rendered_fields(text: str) -> dict:
    """Map ``<EntityName> -> [(field_name, annotation), ...]`` from the rendered models file."""
    out: dict = {}
    current = None
    for line in (text or "").splitlines():
        cm = _CLASS_RE.match(line)
        if cm:
            current = cm.group(1)
            out[current] = []
            continue
        if current is None:
            continue
        if line.strip() == "pass":
            continue
        fm = _FIELD_RE.match(line)
        if fm:
            out[current].append((fm.group(1), fm.group(2)))
        elif line and not line.startswith(" "):
            current = None  # left the class body
    return out


def verify_pydantic_fidelity(schema_text: str, rendered_text: str) -> Tuple[str, ...]:
    """Check the rendered Pydantic file faithfully reflects the schema's scalar projection.

    Asserts, per model (composites excluded): same field **names in source order**; each optional
    Prisma field renders ``Optional[...] = None``; each list field renders ``list[...]``. Returns
    a tuple of issues (empty = faithful).
    """
    schema = parse_prisma_schema(schema_text)
    composites = composite_type_names(schema_text)
    rendered = _extract_rendered_fields(rendered_text)
    issues: List[str] = []

    for name in schema.models:
        if name in composites:
            continue
        expected = schema.scalar_fields(name)
        if name not in rendered:
            issues.append(f"{name}: missing from rendered output")
            continue
        got = rendered[name]
        exp_names = [f.name for f in expected]
        got_names = [g[0] for g in got]
        if exp_names != got_names:
            issues.append(
                f"{name}: field set/order mismatch — schema {exp_names} != rendered {got_names}"
            )
            continue
        ann_by_name = {g[0]: g[1] for g in got}
        for f in expected:
            ann = ann_by_name[f.name]
            if f.is_optional and ("Optional[" not in ann or "= None" not in ann):
                issues.append(
                    f"{name}.{f.name}: optional in schema but rendered '{ann}' "
                    f"(expected Optional[...] = None)"
                )
            if not f.is_optional and "= None" in ann:
                issues.append(
                    f"{name}.{f.name}: required in schema but rendered with a default ('{ann}')"
                )
            if f.is_list and "list[" not in ann:
                issues.append(
                    f"{name}.{f.name}: list in schema but rendered '{ann}' (expected list[...])"
                )
    return tuple(issues)
