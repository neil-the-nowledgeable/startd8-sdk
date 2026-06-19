"""Deterministic static API contract renderer (OpenAPI Role 1 — M0+M1).

Projects the ``.prisma`` schema into ``app/openapi_contract.py``: an owned, drift-checkable,
$0-LLM **offline** contract layer (``ROUTE_MANIFEST`` + minimal ``OPENAPI_SPEC``). Runtime
``GET /openapi.json`` remains a conformance check (boot-smoke); this module is the drift source
of truth.

v1 scope: schema-derived CRUD paths (mirrors ``crud_generator._entity_block``) + default-on
health paths. Optional manifest surfaces (pages/AI/flows) are deferred — they require the same
multi-input drift threading as forms/AI kinds.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from ..frontend_codegen.schema_renderer import composite_type_names, schema_sha256
from ..languages.prisma_parser import PrismaField, PrismaSchema, parse_prisma_schema
from ._headers import header_standard as _header
from .crud_generator import _pk_field
from .pydantic_renderer import _PY_SCALAR

OPENAPI_CONTRACT_PATH = "app/openapi_contract.py"

# Prisma scalar → OpenAPI 3.0 JSON Schema fragment (hand-built subset — no runtime model import).
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


def _server_set(field: PrismaField) -> bool:
    return any(
        a.startswith("@default") or a.startswith("@updatedAt") or a == "@updatedAt"
        for a in field.attributes
    )


def _field_schema(field: PrismaField, schema: PrismaSchema) -> Dict[str, Any]:
    if field.type in schema.enums:
        base: Dict[str, Any] = {"type": "string", "enum": list(schema.enums[field.type])}
    else:
        base = dict(_OAS_SCALAR.get(field.type, {}))
    if field.is_list:
        return {"type": "array", "items": base}
    return base


def _object_schema(
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


def _crud_routes(schema: PrismaSchema, schema_text: str) -> List[Tuple[str, str]]:
    """``(method, path)`` pairs mirroring ``render_routers`` / ``_entity_block``."""
    routes: List[Tuple[str, str]] = []
    for name in _model_names(schema, schema_text):
        prefix = f"/{name.lower()}/"
        routes.append(("GET", prefix))
        routes.append(("POST", prefix))
        if _pk_field(schema, name) is not None:
            item = f"/{name.lower()}/{{item_id}}"
            routes.extend(
                [
                    ("GET", item),
                    ("PATCH", item),
                    ("DELETE", item),
                ]
            )
    return routes


def _health_routes() -> List[Tuple[str, str]]:
    return [("GET", "/health"), ("GET", "/health/live")]


def _path_item_parameters(
    path: str, schema: PrismaSchema, schema_text: str
) -> List[Dict[str, Any]]:
    """OpenAPI path params for ``/{entity}/{item_id}`` routes (validator requires resolution)."""
    if "{item_id}" not in path:
        return []
    segments = [s for s in path.split("/") if s and not s.startswith("{")]
    entity = next(
        (n for n in _model_names(schema, schema_text) if n.lower() == (segments[0] if segments else "")),
        None,
    )
    pk_type = "string"
    if entity is not None:
        pk = _pk_field(schema, entity)
        if pk is not None and pk.type in ("Int", "BigInt"):
            pk_type = "integer"
    return [
        {
            "name": "item_id",
            "in": "path",
            "required": True,
            "schema": {"type": pk_type},
        }
    ]


def _build_openapi_spec(
    routes: List[Tuple[str, str]], schema: PrismaSchema, schema_text: str
) -> Dict[str, Any]:
    paths: Dict[str, Any] = {}
    schemas: Dict[str, Any] = {}

    for name in _model_names(schema, schema_text):
        scalars = schema.scalar_fields(name)
        create_fields = [f for f in scalars if not _server_set(f)]
        update_fields = [f for f in scalars if not f.is_id]
        schemas[f"{name}Create"] = _object_schema(create_fields, schema)
        schemas[f"{name}Read"] = _object_schema(list(scalars), schema)
        schemas[f"{name}Update"] = _object_schema(update_fields, schema, force_optional=True)

    for method, path in routes:
        entry = paths.setdefault(path, {})
        op: Dict[str, Any] = {"responses": {"200": {"description": "OK"}}}
        if method == "POST":
            match = next(
                (n for n in _model_names(schema, schema_text) if n.lower() == path.strip("/").split("/")[0]),
                None,
            )
            if match:
                op["requestBody"] = {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{match}Create"}
                        }
                    },
                }
                op["responses"] = {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": f"#/components/schemas/{match}Read"}
                            }
                        },
                    }
                }
        elif method in ("GET", "PATCH"):
            segments = [s for s in path.split("/") if s and not s.startswith("{")]
            if segments:
                match = next(
                    (n for n in _model_names(schema, schema_text) if n.lower() == segments[0]),
                    None,
                )
                if match:
                    ref = f"{match}Read" if method == "GET" else f"{match}Update"
                    if method == "PATCH":
                        op["requestBody"] = {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": f"#/components/schemas/{ref}"}
                                }
                            }
                        }
                    op["responses"] = {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": f"#/components/schemas/{match}Read"}
                                }
                            },
                        }
                    }
        elif method == "DELETE":
            op["responses"] = {"204": {"description": "No Content"}}
        params = _path_item_parameters(path, schema, schema_text)
        if params:
            op["parameters"] = params
        entry[method.lower()] = op

    names = _model_names(schema, schema_text)
    title = names[0] if names else "App"
    return {
        "openapi": "3.0.3",
        "info": {"title": title, "version": "0.0.0"},
        "paths": paths,
        "components": {"schemas": schemas},
    }


def _format_route_manifest(routes: List[Tuple[str, str]]) -> str:
    lines = ["ROUTE_MANIFEST: tuple[tuple[str, str], ...] = ("]
    for method, path in sorted(routes):
        lines.append(f'    ("{method}", "{path}"),')
    lines.append(")")
    return "\n".join(lines)


def render_openapi_contract(
    schema_text: str, source_file: str = "prisma/schema.prisma"
) -> str:
    """Render ``app/openapi_contract.py`` — static ``ROUTE_MANIFEST`` + ``OPENAPI_SPEC``."""
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    routes = sorted(_crud_routes(schema, schema_text) + _health_routes())
    spec = _build_openapi_spec(routes, schema, schema_text)
    spec_json = json.dumps(spec, indent=2, sort_keys=True)

    header = _header(source_file, sha, "python-openapi-contract")
    body = (
        "from __future__ import annotations\n\n"
        "import json\n"
        "from typing import Any\n\n"
        + _format_route_manifest(routes)
        + "\n\n\n"
        "OPENAPI_SPEC: dict[str, Any] = json.loads(\n"
        + "    '''" + spec_json + "'''\n"
        + ")\n\n\n"
        "def route_paths() -> list[str]:\n"
        '    """Sorted unique paths from :data:`ROUTE_MANIFEST` (for boot-smoke)."""\n'
        "    return sorted({path for _, path in ROUTE_MANIFEST})\n"
    )
    return header + "\n\n" + body
