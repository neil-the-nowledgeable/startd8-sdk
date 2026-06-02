"""Inc 3 — file assembly (render_zod_schema): header, schemas, z.infer, determinism.

Covers the GENERATED header + `schema-sha256` (FR-4/FR-11), `import { z }`, per-model
schemas in source order with join tables included (FR-9), the `z.infer` aliases default-on
(R4-F4), byte-idempotence (FR-4), and the flagged-not-dropped unrenderable policy (FR-2).
"""

from __future__ import annotations

import pytest

from startd8.frontend_codegen import render_zod_schema, schema_sha256

pytestmark = pytest.mark.unit


SCHEMA = """
enum Role {
  ADMIN
  USER
}

model Profile {
  id     String @id @default(cuid())
  name   String
  bio    String?
  age    Int
  role   Role
  tags   String[]
  posts  Post[]
}

model Post {
  id       String  @id @default(cuid())
  title    String
  price    Decimal
  author   Profile @relation(fields: [authorId], references: [id])
  authorId String
}
"""


def test_header_has_generated_marker_and_schema_hash():
    r = render_zod_schema(SCHEMA, "prisma/schema.prisma")
    assert r.text.startswith("// GENERATED from prisma/schema.prisma")
    assert "do not edit by hand" in r.text
    assert f"// schema-sha256: {schema_sha256(SCHEMA)}" in r.text
    assert r.schema_sha256 == schema_sha256(SCHEMA)


def test_imports_zod():
    r = render_zod_schema(SCHEMA)
    assert 'import { z } from "zod";' in r.text


def test_per_model_schemas_in_source_order():
    r = render_zod_schema(SCHEMA)
    assert "export const ProfileSchema = z.object({" in r.text
    assert "export const PostSchema = z.object({" in r.text
    # Source order: Profile before Post.
    assert r.text.index("ProfileSchema") < r.text.index("PostSchema")


def test_field_rendering_inside_object():
    r = render_zod_schema(SCHEMA)
    assert "  name: z.string()," in r.text
    assert "  bio: z.string().nullable()," in r.text
    assert "  age: z.number().int()," in r.text
    assert '  role: z.enum(["ADMIN", "USER"]),' in r.text
    assert "  tags: z.array(z.string())," in r.text
    assert "  price: z.string()," in r.text  # Decimal → money-safe string
    assert "  authorId: z.string()," in r.text
    # The relation object field is not emitted.
    assert "author:" not in r.text


def test_zinfer_aliases_default_on():
    r = render_zod_schema(SCHEMA)
    assert "export type Profile = z.infer<typeof ProfileSchema>;" in r.text
    assert "export type Post = z.infer<typeof PostSchema>;" in r.text


def test_emit_infer_false_omits_aliases():
    r = render_zod_schema(SCHEMA, emit_infer=False)
    assert "z.infer" not in r.text


def test_render_is_byte_idempotent():
    a = render_zod_schema(SCHEMA).text
    b = render_zod_schema(SCHEMA).text
    assert a == b


def test_output_ends_with_single_newline():
    r = render_zod_schema(SCHEMA)
    assert r.text.endswith("\n")
    assert not r.text.endswith("\n\n")


def test_unrenderable_field_is_flagged_not_dropped():
    schema = "model M {\n  id String @id\n  geom Unsupported\n}"
    r = render_zod_schema(schema)
    # field is present as z.unknown() with a marker (not silently dropped)...
    assert "geom: z.unknown()" in r.text
    assert "UNRENDERABLE" in r.text
    # ...and reported in the result.
    assert len(r.unrenderable) == 1
    assert r.unrenderable[0].field == "geom"
    assert r.unrenderable[0].prisma_type == "Unsupported"


def test_clean_schema_has_no_unrenderable():
    assert render_zod_schema(SCHEMA).unrenderable == ()


def test_composite_type_block_not_emitted_as_phantom_schema():
    # F4: a composite `type {}` block must NOT become a top-level schema, and a field typed
    # as a composite must be flagged (not silently dropped).
    schema = (
        "type Address {\n  street String\n  city String\n}\n"
        "model User {\n  id String @id\n  name String\n  address Address\n}\n"
    )
    r = render_zod_schema(schema)
    assert "AddressSchema" not in r.text  # no phantom schema
    assert "export type Address =" not in r.text  # no phantom alias
    assert "export const UserSchema = z.object({" in r.text
    # the composite-typed field is surfaced, not silently dropped
    assert any(u.field == "address" and "composite" in u.reason for u in r.unrenderable)
