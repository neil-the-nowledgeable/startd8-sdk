"""Tests for shared Prisma → JSON Schema projection (schema_contract)."""

from __future__ import annotations

import pytest

from startd8.schema_contract.prisma_json_schema import object_schema
from startd8.languages.prisma_parser import parse_prisma_schema

pytestmark = pytest.mark.unit

SCHEMA_UNKNOWN_SCALAR = """\
model Weird {
  id   String @id
  meta UnknownType
}
"""


def test_unknown_scalar_type_defaults_to_empty_schema() -> None:
    schema = parse_prisma_schema(SCHEMA_UNKNOWN_SCALAR)
    fields = list(schema.scalar_fields("Weird"))
    out = object_schema(fields, schema)
    assert out["properties"]["meta"] == {}
