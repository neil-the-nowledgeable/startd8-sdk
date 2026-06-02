"""Inc 2 — convention layer (format hints, type-guarded, @default-required).

Covers the FR-2 convention rules: `.email()`/`.url()` hints applied only to plain `String`
fields (R4-S3 type guard), the bare-`url` match (R4-F2), correct hint-before-`.nullable()`
layering, `@default` fields staying required (R2-F9), and determinism.
"""

from __future__ import annotations

import re

import pytest

from startd8.frontend_codegen import (
    DEFAULT_CONVENTIONS,
    FieldConventions,
    render_field,
)
from startd8.frontend_codegen.conventions import FieldConventions as FC
from startd8.languages.prisma_parser import PrismaField, parse_prisma_schema

pytestmark = pytest.mark.unit


SCHEMA = """
model Artifact {
  id                 String   @id @default(cuid())
  url                String?
  avatarUrl          String?
  email              String
  contactEmail       String?
  bio                String?
  emailVerified      Boolean
  thumbnailUrlExpiry DateTime?
  ownerId            String   @default("local")
  source             String   @default("manual")
  confirmed          Boolean  @default(false)
  createdAt          DateTime @default(now())
  links              String[]
}
"""


def _r(schema, name, conventions=DEFAULT_CONVENTIONS):
    return render_field(schema.model("Artifact").field(name), schema, conventions)


# --------------------------------------------------------------------------- #
# Format hints — positive
# --------------------------------------------------------------------------- #


def test_email_field_gets_email_hint():
    s = parse_prisma_schema(SCHEMA)
    assert _r(s, "email") == "z.string().email()"


def test_suffix_email_field_gets_email_hint():
    s = parse_prisma_schema(SCHEMA)
    # `contactEmail` is optional → hint before nullable.
    assert _r(s, "contactEmail") == "z.string().email().nullable()"


def test_bare_url_field_gets_url_hint():
    # R4-F2: a field named exactly `url` (strtd8's Artifact.url) must get `.url()`.
    s = parse_prisma_schema(SCHEMA)
    assert _r(s, "url") == "z.string().url().nullable()"


def test_suffix_url_field_gets_url_hint():
    s = parse_prisma_schema(SCHEMA)
    assert _r(s, "avatarUrl") == "z.string().url().nullable()"


# --------------------------------------------------------------------------- #
# Type guard — negatives (R4-S3 false-positive prevention)
# --------------------------------------------------------------------------- #


def test_boolean_named_like_email_gets_no_hint():
    s = parse_prisma_schema(SCHEMA)
    # `emailVerified Boolean` must NOT get `.email()` chained onto z.boolean().
    assert _r(s, "emailVerified") == "z.boolean()"


def test_datetime_named_like_url_gets_no_hint():
    s = parse_prisma_schema(SCHEMA)
    # `thumbnailUrlExpiry DateTime?` must NOT get `.url()`.
    assert _r(s, "thumbnailUrlExpiry") == "z.string().datetime().nullable()"


def test_plain_string_without_matching_name_gets_no_hint():
    s = parse_prisma_schema(SCHEMA)
    assert _r(s, "bio") == "z.string().nullable()"


def test_string_list_named_like_url_gets_no_hint():
    # A `String[]` is not eligible for a scalar-string hint (is_list guard).
    s = parse_prisma_schema(SCHEMA)
    assert _r(s, "links") == "z.array(z.string())"


# --------------------------------------------------------------------------- #
# @default stays required (R2-F9 / R2-S12)
# --------------------------------------------------------------------------- #


def test_defaulted_fields_stay_required_not_optional():
    s = parse_prisma_schema(SCHEMA)
    assert (
        _r(s, "ownerId") == "z.string()"
    )  # @default("local"), no .nullable()/.optional()
    assert _r(s, "source") == "z.string()"
    assert _r(s, "confirmed") == "z.boolean()"
    assert _r(s, "createdAt") == "z.string().datetime()"
    assert _r(s, "id") == "z.string()"  # @id @default(cuid())


# --------------------------------------------------------------------------- #
# Layering + determinism + overridability
# --------------------------------------------------------------------------- #


def test_hint_comes_before_nullable():
    # Explicit ordering check: base → hint → nullable.
    s = parse_prisma_schema(SCHEMA)
    out = _r(s, "url")
    assert out.index(".url()") < out.index(".nullable()")


def test_render_is_deterministic():
    s = parse_prisma_schema(SCHEMA)
    assert _r(s, "email") == _r(s, "email")
    assert _r(s, "url") == _r(s, "url")


def test_conventions_are_overridable():
    # A custom rule set that only recognizes a `link` name for urls.
    s = parse_prisma_schema(SCHEMA)
    custom = FC(email_pattern=re.compile(r"^email$"), url_pattern=re.compile(r"^link$"))
    # `url` no longer matches the custom url pattern → plain string.
    assert (
        render_field(s.model("Artifact").field("url"), s, custom)
        == "z.string().nullable()"
    )
    # `email` still matches the custom email pattern.
    assert (
        render_field(s.model("Artifact").field("email"), s, custom)
        == "z.string().email()"
    )


def test_format_hint_returns_none_for_ineligible_types():
    convs = FieldConventions()
    assert (
        convs.format_hint(PrismaField("emailVerified", "Boolean", False, False, ()))
        is None
    )
    assert (
        convs.format_hint(PrismaField("links", "String", False, True, ())) is None
    )  # list
    assert (
        convs.format_hint(PrismaField("email", "String", False, False, ()))
        == ".email()"
    )
