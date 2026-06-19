"""Prisma → JSON Schema projection for event payloads and shared contract tooling."""

from __future__ import annotations

from typing import Any, Dict, List

from ..frontend_codegen.schema_renderer import composite_type_names
from ..languages.prisma_parser import PrismaField, PrismaSchema, parse_prisma_schema

_OAS_SCALAR: Dict[str, Dict[str, Any]] = {
    "String": {"type": "string"},
    "Boolean": {"type": "boolean"},
    "Int": {"type": "integer"},
    "BigInt": {"type": "integer"},
    "Float": {"type": "number"},
    "Decimal": {"type": "number"},
    "DateTime": {"type": "string", "format": "date-time"},
    "Json": {},
    "Bytes": {"type": "string", "format": "byte"},
}


def _model_names(schema: PrismaSchema, schema_text: str) -> List[str]:
    composites = composite_type_names(schema_text)
    return [n for n in schema.models if n not in composites]


def _field_schema(field: PrismaField, schema: PrismaSchema) -> Dict[str, Any]:
    if field.type in schema.enums:
        base: Dict[str, Any] = {"type": "string", "enum": list(schema.enums[field.type])}
    else:
        base = dict(_OAS_SCALAR.get(field.type, {"type": "string"}))
    if field.is_list:
        return {"type": "array", "items": base}
    return base


def object_schema(
    fields: List[PrismaField], schema: PrismaSchema, *, force_optional: bool = False
) -> Dict[str, Any]:
    props: Dict[str, Any] = {}
    required: List[str] = []
    for f in fields:
        props[f.name] = _field_schema(f, schema)
        if not force_optional and not f.is_optional:
            required.append(f.name)
    out: Dict[str, Any] = {"type": "object", "properties": props}
    if required:
        out["required"] = required
    return out


def entity_read_schema(schema_text: str, model_name: str) -> Dict[str, Any]:
    """JSON Schema for a Prisma model's persisted scalar fields (Read shape)."""
    schema = parse_prisma_schema(schema_text)
    if model_name not in schema.models:
        available = ", ".join(_model_names(schema, schema_text)) or "(none)"
        raise ValueError(f"model {model_name!r} not in schema; available: {available}")
    scalars = list(schema.scalar_fields(model_name))
    return object_schema(scalars, schema)


def entity_read_schemas(schema_text: str) -> Dict[str, Dict[str, Any]]:
    """Map ``ModelName`` → JSON Schema Read dict for every entity."""
    schema = parse_prisma_schema(schema_text)
    out: Dict[str, Dict[str, Any]] = {}
    for name in _model_names(schema, schema_text):
        out[name] = object_schema(list(schema.scalar_fields(name)), schema)
    return out
