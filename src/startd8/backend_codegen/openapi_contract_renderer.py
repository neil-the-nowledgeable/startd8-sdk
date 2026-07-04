"""Deterministic static API contract renderer (OpenAPI Role 1 — M0+M1).

Projects the ``.prisma`` schema into ``app/openapi_contract.py``: an owned, drift-checkable,
$0-LLM **offline** contract layer (``ROUTE_MANIFEST`` + minimal ``OPENAPI_SPEC``). Runtime
``GET /openapi.json`` remains a conformance check (boot-smoke); this module is the drift source
of truth.

v1 scope: schema-derived CRUD paths (mirrors ``crud_generator._entity_block``) + default-on
health paths; conditional manifest surfaces (pages/AI/flows/editors/import) when the same
inputs that trigger ``assembler`` emission are present. Optional ``api.yaml`` overlay (Role 2)
adds net-new / user-declared routes.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from ..frontend_codegen.schema_renderer import schema_sha256
from ..languages.prisma_parser import PrismaField, PrismaSchema, parse_prisma_schema
from ..schema_contract.prisma_json_schema import model_names, object_schema
from .api_overlay_manifest import (
    apply_api_overlay,
    parse_api_overlay,
    routes_from_openapi_spec,
)
from ._headers import header_api_overlay, header_standard as _header
from .crud_generator import _pk_field
from .pydantic_renderer import _PY_SCALAR

OPENAPI_CONTRACT_PATH = "app/openapi_contract.py"


def _server_set(field: PrismaField) -> bool:
    return any(
        a.startswith("@default") or a.startswith("@updatedAt") or a == "@updatedAt"
        for a in field.attributes
    )


def _crud_routes(schema: PrismaSchema, schema_text: str) -> List[Tuple[str, str]]:
    """``(method, path)`` pairs mirroring ``render_routers`` / ``_entity_block``."""
    routes: List[Tuple[str, str]] = []
    for name in model_names(schema, schema_text):
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


def _conditional_routes(
    schema: PrismaSchema,
    schema_text: str,
    *,
    manifest_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    views_text: Optional[str] = None,
    imports_text: Optional[str] = None,
) -> List[Tuple[str, str]]:
    """Manifest-derived routes — empty when the triggering manifest is absent (FR-3 / SOTTO)."""
    routes: List[Tuple[str, str]] = []
    known = frozenset(model_names(schema, schema_text))

    if pages_text:
        from .pages_generator import parse_pages

        pages, _ = parse_pages(pages_text)
        for page in pages:
            routes.append(("GET", page.slug))

    if manifest_text:
        from .ai_layer import _triggered_passes, parse_ai_passes

        for ps in parse_ai_passes(manifest_text):
            routes.append(("POST", f"/ai{ps.route_path}"))
        for ps in _triggered_passes(manifest_text):
            entity = ps.trigger.entity.lower()
            id_param = f"{entity}_id"
            routes.append(("POST", f"/ui/{entity}/{{{id_param}}}/run-{ps.module}"))

    if views_text:
        from .editors_manifest import parse_editors
        from .flows_manifest import parse_flows

        for flow in parse_flows(views_text, known_entities=known):
            name = flow.name
            routes.extend(
                [
                    ("POST", f"/flow/{name}/start"),
                    ("GET", f"/flow/{name}/{{draft_id}}"),
                    ("POST", f"/flow/{name}/{{draft_id}}/advance"),
                    ("POST", f"/flow/{name}/{{draft_id}}/back"),
                ]
            )
        for editor in parse_editors(views_text, known_entities=known):
            routes.append(("GET", editor.route))
            routes.append(("POST", editor.route))

    if imports_text:
        from .import_surface import surface_enabled

        if surface_enabled(imports_text):
            routes.extend([("GET", "/import"), ("POST", "/import")])

    return routes


def _generic_path_parameters(path: str) -> List[Dict[str, Any]]:
    """Declare OpenAPI path params for any ``{name}`` segment (non-CRUD conditional/overlay paths)."""
    params: List[Dict[str, Any]] = []
    for name in re.findall(r"\{([^}]+)\}", path):
        params.append(
            {
                "name": name,
                "in": "path",
                "required": True,
                "schema": {"type": "string"},
            }
        )
    return params


def _path_item_parameters(
    path: str, schema: PrismaSchema, schema_text: str
) -> List[Dict[str, Any]]:
    """OpenAPI path params for ``/{entity}/{item_id}`` routes (validator requires resolution)."""
    if "{item_id}" not in path:
        return _generic_path_parameters(path)
    segments = [s for s in path.split("/") if s and not s.startswith("{")]
    entity = next(
        (n for n in model_names(schema, schema_text) if n.lower() == (segments[0] if segments else "")),
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

    for name in model_names(schema, schema_text):
        scalars = schema.scalar_fields(name)
        create_fields = [f for f in scalars if not _server_set(f)]
        update_fields = [f for f in scalars if not f.is_id]
        schemas[f"{name}Create"] = object_schema(create_fields, schema)
        schemas[f"{name}Read"] = object_schema(list(scalars), schema)
        schemas[f"{name}Update"] = object_schema(update_fields, schema, force_optional=True)

    for method, path in routes:
        entry = paths.setdefault(path, {})
        op: Dict[str, Any] = {"responses": {"200": {"description": "OK"}}}
        if method == "POST":
            match = next(
                (n for n in model_names(schema, schema_text) if n.lower() == path.strip("/").split("/")[0]),
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
                    (n for n in model_names(schema, schema_text) if n.lower() == segments[0]),
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

    names = model_names(schema, schema_text)
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


def _project_openapi(
    schema_text: str,
    *,
    api_text: Optional[str] = None,
    manifest_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    views_text: Optional[str] = None,
    imports_text: Optional[str] = None,
    overlay_warnings: Optional[List[str]] = None,
) -> Tuple[List[Tuple[str, str]], Dict[str, Any]]:
    """Build sorted routes + OpenAPI spec from schema, conditional manifests, and optional overlay."""
    schema = parse_prisma_schema(schema_text)
    routes = sorted(
        _crud_routes(schema, schema_text)
        + _health_routes()
        + _conditional_routes(
            schema,
            schema_text,
            manifest_text=manifest_text,
            pages_text=pages_text,
            views_text=views_text,
            imports_text=imports_text,
        )
    )
    spec = _build_openapi_spec(routes, schema, schema_text)
    if api_text:
        overlay = parse_api_overlay(api_text)
        spec, warnings = apply_api_overlay(spec, overlay, schema_text)
        if overlay_warnings is not None:
            overlay_warnings.extend(warnings)
    routes = routes_from_openapi_spec(spec)
    return routes, spec


def render_openapi_contract(
    schema_text: str,
    source_file: str = "prisma/schema.prisma",
    *,
    api_text: Optional[str] = None,
    manifest_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    views_text: Optional[str] = None,
    imports_text: Optional[str] = None,
    overlay_warnings: Optional[List[str]] = None,
) -> str:
    """Render ``app/openapi_contract.py`` — static ``ROUTE_MANIFEST`` + ``OPENAPI_SPEC``."""
    sha = schema_sha256(schema_text)
    routes, spec = _project_openapi(
        schema_text,
        api_text=api_text,
        manifest_text=manifest_text,
        pages_text=pages_text,
        views_text=views_text,
        imports_text=imports_text,
        overlay_warnings=overlay_warnings,
    )
    spec_json = json.dumps(spec, indent=2, sort_keys=True)

    if api_text:
        header = header_api_overlay(
            source_file, sha, schema_sha256(api_text), "python-openapi-contract"
        )
    else:
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
