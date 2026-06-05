"""Deterministic contract-test emitter (Python contract-codegen, rung 4 — semantic tests).

The schema-derived half of "tests that verify the semantic validation of the code". Projects the
``.prisma`` contract into an owned, ``$0``-LLM, drift-checked ``tests/test_contract.py`` whose
assertions are **executable semantic guarantees**, not just "it compiles":

- **round-trip** — ``Schema.model_validate(inst.model_dump()) == inst`` per entity (data fidelity).
- **field presence + optionality** — every contract scalar (incl. FK scalars) is a model field with
  the right required/optional shape (no dropped or silently-retyped field).
- **enum domain** — an out-of-domain enum value raises ``ValidationError`` (literal-set integrity).

These are exactly the invariants derivable from the contract alone, so they are deterministic and
byte-identical on regen. The genuinely *behavioral* assertions (AI-pass output quality) stay
LLM-authored (rung 5) — they need real model output and cannot be projected from the schema.

Mirrors the other backend_codegen emitters: a ``#`` GENERATED header (pytest ignores comments), the
``python-tests-contract`` artifact kind, recognized/verified by the shared provider + drift path.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..frontend_codegen.schema_renderer import composite_type_names, schema_sha256
from ..languages.prisma_parser import PrismaField, PrismaSchema, parse_prisma_schema
from ._headers import header_standard as _header

CONTRACT_TESTS_PATH = "tests/test_contract.py"
COMPLETENESS_TESTS_PATH = "tests/test_completeness.py"
_KIND = "python-tests-contract"
_COMPLETENESS_KIND = "python-tests-completeness"

_SHIM = (
    "import sys\n"
    "from pathlib import Path\n\n"
    "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
)

# Prisma scalar -> a valid sample value as Python source. Values are chosen to validate under the
# generated Pydantic models with no constraints (the renderer emits plain types), and to round-trip
# byte-stably. Decimal/DateTime go through Pydantic's lax coercion (str -> Decimal/datetime).
_SCALAR_SAMPLE: Dict[str, str] = {
    "String": '"sample"',
    "Boolean": "False",
    "Int": "0",
    "BigInt": "0",
    "Float": "0.0",
    "Decimal": '"0"',
    "DateTime": '"2020-01-01T00:00:00"',
    "Json": "None",
    "Bytes": 'b"x"',
}


def _model_names(schema: PrismaSchema, schema_text: str) -> List[str]:
    composites = composite_type_names(schema_text)
    return [n for n in schema.models if n not in composites]


def _sample_literal(field: PrismaField, schema: PrismaSchema) -> str:
    """A valid value for *field* as Python source. ``[]`` for lists; first member for enums."""
    if field.is_list:
        return "[]"  # empty list validates for any list[...] and round-trips
    if field.type in schema.enums:
        vals = schema.enums[field.type]
        return f'"{vals[0]}"' if vals else '""'
    return _SCALAR_SAMPLE.get(field.type, "None")  # default None covers Any/unmappable scalars


def _required_kwargs(schema: PrismaSchema, name: str) -> str:
    """A ``{"f": value, ...}`` dict literal of an entity's required scalars (source order)."""
    required = [f for f in schema.scalar_fields(name) if not f.is_optional]
    return "{" + ", ".join(f'"{f.name}": {_sample_literal(f, schema)}' for f in required) + "}"


def _entity_block(schema: PrismaSchema, name: str) -> str:
    """The three semantic test functions for one entity (no trailing newline)."""
    cls = f"{name}Schema"
    low = name.lower()
    scalars = schema.scalar_fields(name)
    kw = _required_kwargs(schema, name)
    lines: List[str] = []

    # 1. round-trip fidelity
    lines += [
        f"def test_{low}_roundtrip():",
        f"    inst = {cls}(**{kw})",
        f"    assert {cls}.model_validate(inst.model_dump()) == inst",
        "",
        "",
    ]

    # 2. field presence + optionality (FK scalars included — they are scalars)
    lines.append(f"def test_{low}_fields():")
    lines.append(f"    f = {cls}.model_fields")
    if scalars:
        for fld in scalars:
            pred = (
                f"not f[{fld.name!r}].is_required()"
                if fld.is_optional
                else f"f[{fld.name!r}].is_required()"
            )
            lines.append(f"    assert {fld.name!r} in f and {pred}")
    else:
        lines.append("    assert set(f) == set()")

    # 3. enum-domain integrity (first non-list enum field, if any)
    enum_fields = [f for f in scalars if f.type in schema.enums and not f.is_list]
    if enum_fields:
        ef = enum_fields[0]
        lines += [
            "",
            "",
            f"def test_{low}_{ef.name}_enum_domain():",
            f"    bad = dict({kw})",
            f'    bad[{ef.name!r}] = "__not_a_valid_enum_member__"',
            "    with pytest.raises(ValidationError):",
            f"        {cls}(**bad)",
        ]
    return "\n".join(lines)


def render_contract_tests(
    schema_text: str, source_file: str = "prisma/schema.prisma"
) -> str:
    """Render ``tests/test_contract.py`` — deterministic semantic tests over the contract.

    Byte-stable: entities in schema source order, scalars in field order, fixed sample values. The
    ``sys.path`` shim makes ``import app`` work regardless of how pytest is invoked.
    """
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    names = _model_names(schema, schema_text)
    header = _header(source_file, sha, _KIND)

    model_imports = (
        "from app.models import " + ", ".join(f"{n}Schema" for n in names)
        if names
        else "# (no models in the contract — nothing to test)"
    )
    preamble = (
        "import sys\n"
        "from pathlib import Path\n\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n\n"
        "import pytest\n"
        "from pydantic import ValidationError\n\n"
        f"{model_imports}"
    )

    sections = [header + "\n\n" + preamble]
    sections.extend(_entity_block(schema, n) for n in names)
    return "\n\n\n".join(sections) + "\n"


def render_completeness_tests(
    schema_text: str,
    source_file: str = "prisma/schema.prisma",
    *,
    manifest: Optional[Dict[str, Any]] = None,
) -> str:
    """Render ``tests/test_completeness.py`` — FR-9: the completeness *formula* as an executable check.

    Pins the generated ``compute_completeness`` at its endpoints, mode-agnostically: a fully-populated
    model scores ``1.0`` with no nudges; an empty model scores ``0.0`` with one nudge per *included*
    entity (the manifest ``exclude`` set drops join/system tables from the denominator). The expected
    values are baked literals computed here, so a bug in the generated function (wrong rounding,
    off-by-one denominator, miscounted nudges) flips the test red.
    """
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    names = _model_names(schema, schema_text)
    excluded = {str(e) for e in (manifest.get("exclude") or [])} if manifest else set()
    included = [n for n in names if n not in excluded]

    header = _header(source_file, sha, _COMPLETENESS_KIND)
    preamble = _SHIM + "\nfrom app.completeness import compute_completeness"

    if not included:
        # Empty/all-excluded contract → the generated function returns 1.0 for any input.
        block = (
            "def test_completeness_trivial():\n"
            "    assert compute_completeness({}).score == 1.0\n"
            "    assert compute_completeness({}).nudges == []"
        )
        return header + "\n\n" + preamble + "\n\n\n" + block + "\n"

    full = "{" + ", ".join(f'"{n}": 99' for n in names) + "}"
    blocks = [
        (
            "def test_completeness_full():\n"
            f"    r = compute_completeness({full})\n"
            "    assert r.score == 1.0\n"
            "    assert r.nudges == []"
        ),
        (
            "def test_completeness_empty():\n"
            "    r = compute_completeness({})\n"
            "    assert r.score == 0.0\n"
            f"    assert len(r.nudges) == {len(included)}"
        ),
    ]
    return header + "\n\n" + preamble + "\n\n\n" + "\n\n\n".join(blocks) + "\n"
