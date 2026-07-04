"""Shared schema contract utilities (Prisma JSON Schema + smoke synthesis re-exports)."""

from __future__ import annotations

from .prisma_json_schema import entity_read_schema, entity_read_schemas, model_names, object_schema

__all__ = [
    "entity_read_schema",
    "entity_read_schemas",
    "model_names",
    "object_schema",
]
