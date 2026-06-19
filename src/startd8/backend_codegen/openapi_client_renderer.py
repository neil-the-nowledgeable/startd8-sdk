"""Deterministic httpx API client renderer (OpenAPI Role 1 — M3 / FR-7).

Projects schema-derived CRUD operations into ``clients/http_client.py`` — a minimal typed
``httpx`` wrapper for inter-context / escape-hatch consumers. Paths mirror
``openapi_contract_renderer._crud_routes`` and DTOs come from ``app.tables``. Role 2 M3 adds
methods for overlay operations whose request/response ``$ref`` resolve to Prisma-derived DTOs.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ..frontend_codegen.schema_renderer import schema_sha256
from ..languages.prisma_parser import PrismaSchema, parse_prisma_schema
from ._headers import header_api_overlay, header_standard as _header
from .crud_generator import _pk_field
from .openapi_contract_renderer import (
    _crud_routes,
    _model_names,
    _project_openapi,
)

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})
_DTO_SUFFIXES = ("Create", "Read", "Update")


def _pk_py_type(schema: PrismaSchema, name: str) -> str:
    pk = _pk_field(schema, name)
    if pk is not None and pk.type in ("Int", "BigInt"):
        return "int"
    return "str"


def _prisma_dto_names(schema: PrismaSchema, schema_text: str) -> Set[str]:
    names: Set[str] = set()
    for entity in _model_names(schema, schema_text):
        names.update(f"{entity}{suffix}" for suffix in _DTO_SUFFIXES)
    return names


def _ref_name(ref: Any) -> Optional[str]:
    if not isinstance(ref, str) or not ref.startswith("#/components/schemas/"):
        return None
    return ref.rsplit("/", 1)[-1]


def _op_json_ref(op: Dict[str, Any], *, response: bool) -> Optional[str]:
    if response:
        content = (
            op.get("responses", {})
            .get("200", {})
            .get("content", {})
            .get("application/json", {})
        )
        return _ref_name(content.get("schema", {}).get("$ref"))
    body = op.get("requestBody", {})
    content = body.get("content", {}).get("application/json", {})
    return _ref_name(content.get("schema", {}).get("$ref"))


def _overlay_method_name(method: str, path: str) -> str:
    parts = [method.lower()]
    for segment in path.strip("/").split("/"):
        if segment.startswith("{") and segment.endswith("}"):
            parts.append(segment[1:-1])
        else:
            parts.append(re.sub(r"[^0-9a-zA-Z_]+", "_", segment).strip("_").lower())
    return "_".join(p for p in parts if p)


def _path_param_names(path: str) -> List[str]:
    return re.findall(r"\{([^}]+)\}", path)


def _client_url_expr(path: str) -> str:
    """OpenAPI path → generated Python URL expression (plain string or f-string)."""
    params = _path_param_names(path)
    if not params:
        return f'"{path}"'
    escaped = path.replace("{", "{{").replace("}", "}}")
    for name in params:
        escaped = escaped.replace("{{" + name + "}}", "{" + name + "}")
    return f'f"{escaped}"'


def _overlay_client_methods(
    schema: PrismaSchema,
    schema_text: str,
    spec: Dict[str, Any],
    *,
    use_traced_request: bool = False,
) -> str:
    """Emit httpx methods for non-CRUD overlay ops with Prisma-derived ``$ref`` DTOs (FR-10)."""
    crud = set(_crud_routes(schema, schema_text))
    dto_names = _prisma_dto_names(schema, schema_text)
    blocks: List[str] = []

    for path, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, op in path_item.items():
            if method not in _HTTP_METHODS or not isinstance(op, dict):
                continue
            http_method = method.upper()
            if (http_method, path) in crud:
                continue
            req_dto = _op_json_ref(op, response=False)
            resp_dto = _op_json_ref(op, response=True)
            if (req_dto is None or req_dto not in dto_names) and (
                resp_dto is None or resp_dto not in dto_names
            ):
                continue

            fn = _overlay_method_name(http_method, path)
            params = _path_param_names(path)
            sig_parts = [f"{name}: str" for name in params]
            if req_dto and req_dto in dto_names:
                sig_parts.append(f"body: {req_dto}")
            signature = ", ".join(sig_parts)
            if signature:
                signature = ", " + signature

            call_kw = ""
            if req_dto and req_dto in dto_names:
                call_kw = ", json=body.model_dump()"

            if use_traced_request:
                http_line = (
                    f"        resp = self._request({http_method!r}, "
                    f"{_client_url_expr(path)}{call_kw})"
                )
            else:
                http_line = (
                    f"        resp = self._client.{method.lower()}"
                    f"({_client_url_expr(path)}{call_kw})"
                )

            lines = [
                f"    def {fn}(self{signature})"
                + (f" -> {resp_dto}" if resp_dto and resp_dto in dto_names else " -> None"),
                f'        """``{http_method} {path}`` — overlay operation."""',
                http_line,
                "        resp.raise_for_status()",
            ]
            if resp_dto and resp_dto in dto_names:
                lines.append(f"        return {resp_dto}.model_validate(resp.json())")
            blocks.append("\n".join(lines))

    return "\n\n\n".join(blocks)


def _entity_methods(
    schema: PrismaSchema,
    schema_text: str,
    name: str,
    *,
    use_traced_request: bool = False,
) -> str:
    """One block of CRUD methods for *name* on :class:`ApiClient`."""
    low = name.lower()
    prefix = f"/{low}"
    lines: List[str] = []
    pk_py = _pk_py_type(schema, name)

    def _call(method: str, url: str, extra: str = "") -> str:
        if use_traced_request:
            return f'        resp = self._request({method!r}, {url}{extra})'
        verb = method.lower()
        if extra:
            return f"        resp = self._client.{verb}({url}{extra})"
        return f"        resp = self._client.{verb}({url})"

    lines += [
        f"    def list_{low}(self) -> list[{name}Read]:",
        f'        """``GET {prefix}/`` — list all {name} rows."""',
        _call("GET", f'"{prefix}/"'),
        "        resp.raise_for_status()",
        f"        return [{name}Read.model_validate(row) for row in resp.json()]",
        "",
        "",
        f"    def create_{low}(self, item: {name}Create) -> {name}Read:",
        f'        """``POST {prefix}/`` — create a {name}."""',
        _call("POST", f'"{prefix}/"', ", json=item.model_dump()"),
        "        resp.raise_for_status()",
        f"        return {name}Read.model_validate(resp.json())",
    ]

    if _pk_field(schema, name) is not None:
        lines += [
            "",
            "",
            f"    def get_{low}(self, item_id: {pk_py}) -> {name}Read:",
            f'        """``GET {prefix}/{{item_id}}`` — fetch one {name}."""',
            _call("GET", f'f"{prefix}/{{item_id}}"'),
            "        resp.raise_for_status()",
            f"        return {name}Read.model_validate(resp.json())",
            "",
            "",
            f"    def update_{low}(self, item_id: {pk_py}, item: {name}Update) -> {name}Read:",
            f'        """``PATCH {prefix}/{{item_id}}`` — partial update."""',
            _call(
                "PATCH",
                f'f"{prefix}/{{item_id}}"',
                ", json=item.model_dump(exclude_unset=True)",
            ),
            "        resp.raise_for_status()",
            f"        return {name}Read.model_validate(resp.json())",
            "",
            "",
            f"    def delete_{low}(self, item_id: {pk_py}) -> None:",
            f'        """``DELETE {prefix}/{{item_id}}`` — remove a {name}."""',
            _call("DELETE", f'f"{prefix}/{{item_id}}"'),
            "        resp.raise_for_status()",
        ]
    return "\n".join(lines)


def render_http_client(
    schema_text: str,
    source_file: str = "prisma/schema.prisma",
    *,
    api_text: Optional[str] = None,
    manifest_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    views_text: Optional[str] = None,
    imports_text: Optional[str] = None,
) -> str:
    """Render ``clients/http_client.py`` — typed httpx CRUD client for schema-derived routes."""
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    names = _model_names(schema, schema_text)

    _, spec = _project_openapi(
        schema_text,
        api_text=api_text,
        manifest_text=manifest_text,
        pages_text=pages_text,
        views_text=views_text,
        imports_text=imports_text,
    )

    table_imports: Set[str] = set()
    for n in names:
        table_imports.add(n)
        table_imports.add(f"{n}Create")
        table_imports.add(f"{n}Read")
        if _pk_field(schema, n) is not None:
            table_imports.add(f"{n}Update")
    for _, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method in path_item:
            if method not in _HTTP_METHODS:
                continue
            op = path_item[method]
            if not isinstance(op, dict):
                continue
            for dto in (_op_json_ref(op, response=False), _op_json_ref(op, response=True)):
                if dto and dto in _prisma_dto_names(schema, schema_text):
                    table_imports.add(dto)

    blocks = [_entity_methods(schema, schema_text, n) for n in names]
    overlay_block = _overlay_client_methods(schema, schema_text, spec)
    if overlay_block:
        blocks.append(overlay_block)

    if api_text and overlay_block:
        header = header_api_overlay(
            source_file, sha, schema_sha256(api_text), "python-openapi-client"
        )
    else:
        header = _header(source_file, sha, "python-openapi-client")
    imports = "from __future__ import annotations\n\nimport httpx\n\n"
    if table_imports:
        imports += (
            "from app.tables import " + ", ".join(sorted(table_imports)) + "\n"
        )

    class_lines = [
        "class ApiClient:",
        '    """Minimal typed HTTP client for schema-derived CRUD routes."""',
        "",
        "    def __init__(self, base_url: str, *, client: httpx.Client | None = None) -> None:",
        "        self._base_url = base_url.rstrip(\"/\")",
        "        if client is not None:",
        "            self._client = client",
        "            self._owns_client = False",
        "        else:",
        "            self._client = httpx.Client(base_url=self._base_url)",
        "            self._owns_client = True",
        "",
        "    def close(self) -> None:",
        "        if self._owns_client:",
        "            self._client.close()",
        "",
        "    def __enter__(self) -> \"ApiClient\":",
        "        return self",
        "",
        "    def __exit__(self, *exc: object) -> None:",
        "        self.close()",
    ]
    body = imports + "\n\n" + "\n".join(class_lines)
    if blocks:
        body += "\n" + "\n\n\n".join(blocks)
    body += "\n"
    return header + "\n\n" + body
