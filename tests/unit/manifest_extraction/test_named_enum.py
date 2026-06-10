"""Named / shared enum grammar — FR-PE-8…12.

A named enum is declared once under ``## Enums`` and referenced by ``enum: <Name>`` in a field's
Type cell; the emitter renders one ``enum`` block shared by every referencing field. The inline
``choice of: a|b|c`` per-field form still works and now actually emits its enum block (the latent
value-capture gap, FR-PE-10). Parity (FR-PE-11) compares enum value sets, not just models.
"""

from __future__ import annotations

import pytest

from startd8.languages.prisma_parser import parse_prisma_schema
from startd8.manifest_extraction.entities import (
    DocEntity,
    DocField,
    EntityGraph,
    extract_enums,
)
from startd8.manifest_extraction.extract import build_entity_graph
from startd8.manifest_extraction.grammar import find_section, parse_sections
from startd8.manifest_extraction.prisma_emitter import render_prisma_schema, semantic_diff

pytestmark = pytest.mark.unit

_PREAMBLE = (
    'generator client {\n  provider = "prisma-client-js"\n}\n\n'
    'datasource db {\n  provider = "sqlite"\n  url      = env("DATABASE_URL")\n}\n\n'
)

_APP_STATUS = (
    "discovered | applied | screening | interview | offer | "
    "accepted | rejected | withdrawn | on_hold"
)

# A doc that declares ApplicationStatus once and references it from two entities (the strtd8 case).
_DOC = (
    "## Enums\n\n"
    "### Enum: ApplicationStatus\n"
    f"{_APP_STATUS}\n\n"
    "## Entities\n\n"
    "### JobDescription\n"
    "| Field | Type | Required | Notes |\n"
    "|-------|------|----------|-------|\n"
    "| title | text | yes | |\n"
    "| status | enum: ApplicationStatus | yes | default: discovered |\n\n"
    "### JobStatusEntry\n"
    "| Field | Type | Required | Notes |\n"
    "|-------|------|----------|-------|\n"
    "| status | enum: ApplicationStatus | yes | |\n"
)


def _enum_sections(doc: str):
    secs = parse_sections(doc)
    root = find_section(secs, "Enums")
    return [
        s for s in secs
        if s.level == root.level + 1 and len(s.heading_path) >= 2
        and s.heading_path[-2] == root.title
    ]


# --------------------------------------------------------------------------- #
# FR-PE-8 — declare a named enum once
# --------------------------------------------------------------------------- #

def test_extract_enums_parses_ordered_values():
    enums = extract_enums("D", _enum_sections(_DOC), [])
    assert "ApplicationStatus" in enums
    assert enums["ApplicationStatus"] == (
        "discovered", "applied", "screening", "interview", "offer",
        "accepted", "rejected", "withdrawn", "on_hold",
    )


def test_named_enum_lands_on_graph_and_merges_first_wins():
    g = build_entity_graph({"a.md": _DOC, "b.md": _DOC.replace("on_hold", "ghosted")})
    # later doc never overrides the earlier declaration
    assert g.enums["ApplicationStatus"][-1] == "on_hold"


# --------------------------------------------------------------------------- #
# FR-PE-9 — reference a named enum; raw-cell parse (the lowercasing trap)
# --------------------------------------------------------------------------- #

def test_reference_preserves_enum_name_case():
    g = build_entity_graph({"d.md": _DOC})
    jd_status = next(f for f in g.entities["JobDescription"].fields if f.name == "status")
    # NOT "applicationstatus" — the type cell is lowercased internally, the ref must survive
    assert jd_status.prisma_type == "ApplicationStatus"


def test_two_fields_share_one_type():
    g = build_entity_graph({"d.md": _DOC})
    a = next(f for f in g.entities["JobDescription"].fields if f.name == "status")
    b = next(f for f in g.entities["JobStatusEntry"].fields if f.name == "status")
    assert a.prisma_type == b.prisma_type == "ApplicationStatus"


def test_undeclared_reference_is_not_extracted():
    doc = (
        "## Entities\n\n### Thing\n"
        "| Field | Type | Required | Notes |\n"
        "|-------|------|----------|-------|\n"
        "| status | enum: NoSuchEnum | yes | |\n"
    )
    g = build_entity_graph({"d.md": doc})
    status = next(f for f in g.entities["Thing"].fields if f.name == "status")
    assert status.prisma_type is None       # flagged, never a dangling type


# --------------------------------------------------------------------------- #
# FR-PE-10 — capture inline choice values + emit every enum block
# --------------------------------------------------------------------------- #

def test_inline_choice_values_captured():
    doc = (
        "## Entities\n\n### Item\n"
        "| Field | Type | Required | Notes |\n"
        "|-------|------|----------|-------|\n"
        "| kind | choice of: red\\|green\\|blue | yes | |\n"
    )
    g = build_entity_graph({"d.md": doc})
    kind = next(f for f in g.entities["Item"].fields if f.name == "kind")
    assert kind.prisma_type == "ItemKind"
    assert kind.enum_values == ("red", "green", "blue")


def test_named_and_inline_enums_both_emit_and_round_trip():
    doc = _DOC + (
        "\n### Item\n"
        "| Field | Type | Required | Notes |\n"
        "|-------|------|----------|-------|\n"
        "| kind | choice of: red\\|green\\|blue | yes | |\n"
    )
    g = build_entity_graph({"d.md": doc})
    schema = parse_prisma_schema(render_prisma_schema(g).text)
    assert schema.enums["ApplicationStatus"][0] == "discovered"   # named block emitted
    assert schema.enums["ItemKind"] == ("red", "green", "blue")   # per-field block emitted
    # the referencing fields are typed by their enums and round-trip as scalars/enums
    assert schema.model("JobDescription").field("status").type == "ApplicationStatus"
    assert schema.model("Item").field("kind").type == "ItemKind"


def test_enum_name_collision_flagged():
    # an inline choice synthesizes <Entity><Field>; declaring a named enum of that exact name collides
    doc = (
        "## Enums\n\n### Enum: ItemKind\nx | y\n\n"
        "## Entities\n\n### Item\n"
        "| Field | Type | Required | Notes |\n"
        "|-------|------|----------|-------|\n"
        "| kind | choice of: red\\|green | yes | |\n"
    )
    g = build_entity_graph({"d.md": doc})
    res = render_prisma_schema(g)
    assert any(u.field == "kind" and "collision" in u.reason for u in res.unrenderable)


# --------------------------------------------------------------------------- #
# FR-PE-11 — enum-aware semantic parity
# --------------------------------------------------------------------------- #

def test_semantic_diff_flags_differing_enum_values():
    left = _PREAMBLE + "enum S {\n  a\n  b\n}"
    right = _PREAMBLE + "enum S {\n  a\n  b\n  c\n}"
    drift = semantic_diff(left, right)
    assert any(d.startswith("enum S: values") for d in drift)


def test_semantic_diff_flags_missing_and_extra_enums():
    left = _PREAMBLE + "enum A {\n  x\n}"
    right = _PREAMBLE + "enum B {\n  y\n}"
    drift = semantic_diff(left, right)
    assert "enum A: emitted, absent from live" in drift
    assert "enum B: in live, not emitted" in drift


def test_enum_parity_clean_on_match():
    g = build_entity_graph({"d.md": _DOC})
    emitted = render_prisma_schema(g).text
    assert semantic_diff(emitted, emitted) == []


# --------------------------------------------------------------------------- #
# FR-PE-12 — compose with @default
# --------------------------------------------------------------------------- #

def test_named_enum_field_composes_with_default():
    g = build_entity_graph({"d.md": _DOC})
    f = parse_prisma_schema(render_prisma_schema(g).text).model("JobDescription").field("status")
    assert f.type == "ApplicationStatus"
    assert "@default(discovered)" in f.attributes
    assert not f.is_optional                       # defaulted ⇒ non-optional (FR-PE-5a)
