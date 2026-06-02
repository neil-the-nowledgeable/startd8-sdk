"""Inc 4 — acceptance gates: symmetry-by-construction + independent fidelity self-check.

Covers FR-3 (`assert_symmetric` with the real checker signature, R1-S1; Decimal→string
passes the widened gate, R2-S1) and FR-3b (`verify_render_fidelity` catches exactly what
the symmetry gate is blind to: optionality, `.int()`, list shape, enum values, order).
"""

from __future__ import annotations

import pytest

from startd8.frontend_codegen import (
    assert_symmetric,
    render_zod_schema,
    verify_render_fidelity,
)
from startd8.validators.prisma_zod_symmetry import has_errors

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


# --------------------------------------------------------------------------- #
# assert_symmetric (FR-3)
# --------------------------------------------------------------------------- #


def test_clean_render_passes_symmetry():
    rendered = render_zod_schema(SCHEMA).text
    assert assert_symmetric(rendered, SCHEMA) == []


def test_decimal_string_passes_widened_gate():
    # Post.price is Decimal → rendered z.string(); the checker now accepts string for
    # Decimal (R2-S1), so no field_type_mismatch.
    rendered = render_zod_schema(SCHEMA).text
    violations = assert_symmetric(rendered, SCHEMA)
    assert not any(v.field == "price" for v in violations)


def test_symmetry_catches_invented_field():
    schema = "model Profile {\n  id String @id\n  name String\n}"
    rendered = (
        'import { z } from "zod";\n'
        "export const ProfileSchema = z.object({\n"
        "  id: z.string(),\n"
        "  name: z.string(),\n"
        "  bogusField: z.string(),\n"
        "});\n"
    )
    violations = assert_symmetric(rendered, schema)
    assert has_errors(violations)
    assert any(
        v.kind == "field_missing_in_prisma" and v.field == "bogusField"
        for v in violations
    )


def test_symmetry_catches_type_mismatch():
    schema = "model Profile {\n  id String @id\n  age Int\n}"
    rendered = (
        'import { z } from "zod";\n'
        "export const ProfileSchema = z.object({\n"
        "  id: z.string(),\n"
        "  age: z.string(),\n"  # Int rendered as string — concrete mismatch
        "});\n"
    )
    violations = assert_symmetric(rendered, schema)
    assert any(v.kind == "field_type_mismatch" and v.field == "age" for v in violations)


# --------------------------------------------------------------------------- #
# verify_render_fidelity (FR-3b) — the dimensions the symmetry gate ignores
# --------------------------------------------------------------------------- #


def test_clean_render_passes_fidelity():
    rendered = render_zod_schema(SCHEMA).text
    assert verify_render_fidelity(rendered, SCHEMA) == []


def test_fidelity_catches_dropped_int():
    rendered = render_zod_schema(SCHEMA).text
    # The symmetry gate treats z.number() ≡ z.number().int() — fidelity must catch this.
    mutated = rendered.replace("age: z.number().int(),", "age: z.number(),")
    assert assert_symmetric(mutated, SCHEMA) == []  # gate is blind...
    issues = verify_render_fidelity(mutated, SCHEMA)
    assert any("age" in i and ".int()" in i for i in issues)  # ...fidelity is not


def test_fidelity_catches_flipped_nullable():
    rendered = render_zod_schema(SCHEMA).text
    mutated = rendered.replace("bio: z.string().nullable(),", "bio: z.string(),")
    issues = verify_render_fidelity(mutated, SCHEMA)
    assert any("bio" in i and ".nullable()" in i for i in issues)


def test_fidelity_catches_wrong_enum_value():
    rendered = render_zod_schema(SCHEMA).text
    mutated = rendered.replace(
        'z.enum(["ADMIN", "USER"])', 'z.enum(["ADMIN", "SUPER"])'
    )
    issues = verify_render_fidelity(mutated, SCHEMA)
    assert any("role" in i and "USER" in i for i in issues)


def test_fidelity_catches_dropped_list_wrap():
    rendered = render_zod_schema(SCHEMA).text
    mutated = rendered.replace("tags: z.array(z.string()),", "tags: z.string(),")
    issues = verify_render_fidelity(mutated, SCHEMA)
    assert any("tags" in i and "z.array(" in i for i in issues)


def test_fidelity_catches_field_count_mismatch():
    rendered = render_zod_schema(SCHEMA).text
    # Drop the `bio` line entirely.
    mutated = "\n".join(line for line in rendered.splitlines() if "bio:" not in line)
    issues = verify_render_fidelity(mutated, SCHEMA)
    assert any("Profile" in i and "mismatch" in i for i in issues)


# --------------------------------------------------------------------------- #
# Landmine regressions
# --------------------------------------------------------------------------- #


def test_extract_field_exprs_preserves_slashes_in_string_literals():
    # F1: a `//` inside a string literal must NOT be treated as a comment / truncate the expr.
    from startd8.frontend_codegen.gates import _extract_field_exprs

    rendered = (
        "export const MSchema = z.object({\n"
        '  site: z.string().url().default("https://example.com"),\n'
        "  name: z.string(),\n"
        "});\n"
    )
    got = _extract_field_exprs(rendered)
    assert got["M"] == [
        ("site", 'z.string().url().default("https://example.com")'),
        ("name", "z.string()"),
    ]


def test_decimal_string_is_strict_by_default_but_opt_in_for_generator():
    # F3: the global default must still flag Decimal→string (protects postmortem/verifier);
    # only frontend_codegen's assert_symmetric opts in.
    from startd8.languages.prisma_parser import parse_prisma_schema
    from startd8.validators.prisma_zod_symmetry import (
        check_prisma_zod_symmetry,
        extract_zod_objects,
    )

    schema = "model M {\n  id String @id\n  price Decimal\n}"
    rendered = (
        "export const MSchema = z.object({\n"
        "  id: z.string(),\n"
        "  price: z.string(),\n"
        "});"
    )
    prisma = parse_prisma_schema(schema)
    zod = extract_zod_objects(rendered)
    strict = check_prisma_zod_symmetry(prisma, zod)  # default: strict
    assert any(v.field == "price" and v.kind == "field_type_mismatch" for v in strict)
    # frontend_codegen opts in → no violation
    assert assert_symmetric(rendered, schema) == []
