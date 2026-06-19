"""Prisma → JSON Schema projection tests (Tier-1 PR4)."""

from __future__ import annotations

import pytest

from startd8.schema_contract import entity_read_schema, entity_read_schemas

pytestmark = pytest.mark.unit

ORDER_SCHEMA = """
model Order {
  id String @id
  total Float
  paid Boolean @default(false)
}
""".strip()


def test_entity_read_schema_required_fields():
    schema = entity_read_schema(ORDER_SCHEMA, "Order")
    assert schema["type"] == "object"
    assert set(schema["properties"]) == {"id", "total", "paid"}
    assert schema["required"] == ["id", "total", "paid"]


def test_entity_read_schema_unknown_model():
    with pytest.raises(ValueError, match="model 'Missing' not in schema"):
        entity_read_schema(ORDER_SCHEMA, "Missing")


def test_entity_read_schemas_all_models():
    schemas = entity_read_schemas(ORDER_SCHEMA)
    assert "Order" in schemas
    assert schemas["Order"]["properties"]["total"]["type"] == "number"
