"""Inc 1 — Prisma→Zod field model + scalar/optionality/enum/list mapping.

Covers the FR-2 fidelity-matrix base layer, the FR-4 source-order/no-set-iteration
determinism, the FR-1 field-completeness guard, the per-field flagged-unrenderable
failure policy (FR-2/R4-S5/R4-S11), and the FR-13 single-source-of-truth invariant
(renderer field set ≡ the CKG injection path's field set).
"""

from __future__ import annotations

import pytest

from startd8.contractors.project_knowledge.models import FieldSpec
from startd8.contractors.project_knowledge.producer import DraftModeProducer
from startd8.frontend_codegen import (
    SCALAR_MAP,
    field_completeness_issues,
    model_field_sets,
    render_field_base,
    unrenderable_fields,
)
from startd8.languages.prisma_parser import PrismaField, parse_prisma_schema

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

SCHEMA = """
enum Role {
  ADMIN
  USER
}

model Profile {
  id        String   @id @default(cuid())
  name      String
  bio       String?
  age       Int
  rank      Int?
  score     Float
  active    Boolean
  role      Role
  tags      String[]
  createdAt DateTime @default(now())
  posts     Post[]
}

model Post {
  id       String  @id @default(cuid())
  title    String
  author   Profile @relation(fields: [authorId], references: [id])
  authorId String
}
"""


def _field(schema, model, name):
    return schema.model(model).field(name)


def _render(schema, model, name):
    return render_field_base(_field(schema, model, name), schema)


# --------------------------------------------------------------------------- #
# Scalar mapping + decorator layering
# --------------------------------------------------------------------------- #


def test_every_scalar_maps_to_a_concrete_zod_base():
    # Each entry renders a non-empty base on a required field of that type.
    assert SCALAR_MAP["String"] == "z.string()"
    assert SCALAR_MAP["Int"] == "z.number().int()"
    assert SCALAR_MAP["Decimal"] == "z.string()"
    assert SCALAR_MAP["DateTime"] == "z.string().datetime()"
    assert SCALAR_MAP["Json"] == "z.unknown()"


def test_required_scalars():
    s = parse_prisma_schema(SCHEMA)
    assert _render(s, "Profile", "name") == "z.string()"
    assert _render(s, "Profile", "age") == "z.number().int()"
    assert _render(s, "Profile", "score") == "z.number()"
    assert _render(s, "Profile", "active") == "z.boolean()"
    assert _render(s, "Profile", "createdAt") == "z.string().datetime()"


def test_optionality_appends_nullable():
    s = parse_prisma_schema(SCHEMA)
    assert _render(s, "Profile", "bio") == "z.string().nullable()"
    # Int? keeps .int() *before* .nullable() — the gate is blind to .int() (R2-F12),
    # so the exact ordering is load-bearing.
    assert _render(s, "Profile", "rank") == "z.number().int().nullable()"


def test_enum_renders_exact_values():
    s = parse_prisma_schema(SCHEMA)
    assert _render(s, "Profile", "role") == 'z.enum(["ADMIN", "USER"])'


def test_scalar_list_wraps_in_array():
    s = parse_prisma_schema(SCHEMA)
    assert _render(s, "Profile", "tags") == "z.array(z.string())"


def test_nullable_list_layers_array_then_nullable():
    # `String[]?` is not valid Prisma (scalar lists can't be nullable), so test the
    # decorator layering directly: base -> array wrap -> nullable.
    s = parse_prisma_schema(SCHEMA)
    f = PrismaField(
        name="x", type="String", is_optional=True, is_list=True, attributes=()
    )
    assert render_field_base(f, s) == "z.array(z.string()).nullable()"


def test_id_field_renders_as_string():
    s = parse_prisma_schema(SCHEMA)
    assert _render(s, "Profile", "id") == "z.string()"


def test_relation_object_is_not_a_scalar_but_its_fk_is():
    s = parse_prisma_schema(SCHEMA)
    # The relation object field is excluded from the scalar set...
    scalar_names = {f.name for f in s.scalar_fields("Post")}
    assert "author" not in scalar_names
    # ...but the FK scalar is a real, rendered column.
    assert "authorId" in scalar_names
    assert _render(s, "Post", "authorId") == "z.string()"


def test_unknown_type_returns_none_not_raise():
    s = parse_prisma_schema("model M {\n  id String @id\n  geom Unsupported\n}")
    # `Unsupported` parses as a scalar-typed field but has no Zod mapping -> None (flagged).
    assert _render(s, "M", "geom") is None
    assert _render(s, "M", "id") == "z.string()"


# --------------------------------------------------------------------------- #
# Field-set projection: source order, join tables kept, no set iteration
# --------------------------------------------------------------------------- #


def test_model_field_sets_preserve_source_order():
    s = parse_prisma_schema(SCHEMA)
    sets = model_field_sets(s, "prisma/schema.prisma")
    # Source order: Profile then Post (NOT alphabetical).
    assert [fs.entity for fs in sets] == ["Profile", "Post"]
    # Within Profile, fields are in declaration order with relations excluded.
    profile = next(fs for fs in sets if fs.entity == "Profile")
    assert [f.name for f in profile.fields] == [
        "id",
        "name",
        "bio",
        "age",
        "rank",
        "score",
        "active",
        "role",
        "tags",
        "createdAt",
    ]
    assert "posts" not in {f.name for f in profile.fields}  # list-relation excluded


def test_field_set_carries_optional_and_list_flags():
    s = parse_prisma_schema(SCHEMA)
    profile = next(fs for fs in model_field_sets(s) if fs.entity == "Profile")
    by_name = {f.name: f for f in profile.fields}
    assert by_name["bio"].optional is True
    assert by_name["tags"].is_list is True
    assert by_name["name"].optional is False


# --------------------------------------------------------------------------- #
# FR-13: single source of truth vs the CKG injection path
# --------------------------------------------------------------------------- #


def test_field_set_matches_injection_path_projection():
    """render path field set ≡ DraftModeProducer field set, per entity (FR-13/R3-S10)."""
    s = parse_prisma_schema(SCHEMA)
    mine = {
        fs.entity: tuple(fs.fields)
        for fs in model_field_sets(s, "prisma/schema.prisma")
    }
    producer = {
        fs.entity: tuple(fs.fields)
        for fs in DraftModeProducer._field_sets(SCHEMA, "prisma/schema.prisma")
    }
    # The producer drops models with zero scalar fields and sorts alphabetically; compare
    # on the shared entities, field-for-field (same FieldSpec values => no drift).
    for entity, fields in producer.items():
        assert entity in mine, f"{entity} missing from renderer projection"
        assert mine[entity] == fields, f"field-set drift for {entity}"


def test_field_specs_are_the_shared_dataclass():
    s = parse_prisma_schema(SCHEMA)
    profile = next(fs for fs in model_field_sets(s) if fs.entity == "Profile")
    assert all(isinstance(f, FieldSpec) for f in profile.fields)


# --------------------------------------------------------------------------- #
# Unrenderable flagging + completeness guard
# --------------------------------------------------------------------------- #


def test_unrenderable_fields_are_aggregated_not_raised():
    s = parse_prisma_schema(
        "model M {\n  id String @id\n  a Unsupported\n  b AlsoUnknown\n}"
    )
    flagged = unrenderable_fields(s)
    names = {u.field for u in flagged}
    assert names == {"a", "b"}  # both reported in one pass, no exception
    assert all(u.entity == "M" for u in flagged)


def test_completeness_guard_clean_schema_has_no_issues():
    assert field_completeness_issues(SCHEMA) == ()


def test_completeness_guard_flags_a_dropped_field():
    # A lowercase-typed line the parser's PascalCase field regex won't match -> dropped.
    schema_text = "model M {\n  id String @id\n  weird notAType\n}"
    issues = field_completeness_issues(schema_text)
    assert len(issues) == 1
    assert issues[0].startswith("M:")
    assert "dropped" in issues[0]
