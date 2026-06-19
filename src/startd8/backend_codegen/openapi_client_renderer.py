"""Deterministic httpx API client renderer (OpenAPI Role 1 — M3 / FR-7).

Projects schema-derived CRUD operations into ``clients/http_client.py`` — a minimal typed
``httpx`` wrapper for inter-context / escape-hatch consumers. Paths mirror
``openapi_contract_renderer._crud_routes`` and DTOs come from ``app.tables``.
"""

from __future__ import annotations

from typing import List, Set

from ..frontend_codegen.schema_renderer import composite_type_names, schema_sha256
from ..languages.prisma_parser import PrismaSchema, parse_prisma_schema
from ._headers import header_standard as _header
from .crud_generator import _pk_field


def _model_names(schema: PrismaSchema, schema_text: str) -> List[str]:
    composites = composite_type_names(schema_text)
    return [n for n in schema.models if n not in composites]


def _pk_py_type(schema: PrismaSchema, name: str) -> str:
    pk = _pk_field(schema, name)
    if pk is not None and pk.type in ("Int", "BigInt"):
        return "int"
    return "str"


def _entity_methods(schema: PrismaSchema, schema_text: str, name: str) -> str:
    """One block of CRUD methods for *name* on :class:`ApiClient`."""
    low = name.lower()
    prefix = f"/{low}"
    lines: List[str] = []
    pk_py = _pk_py_type(schema, name)

    lines += [
        f"    def list_{low}(self) -> list[{name}Read]:",
        f'        """``GET {prefix}/`` — list all {name} rows."""',
        f'        resp = self._client.get("{prefix}/")',
        "        resp.raise_for_status()",
        f"        return [{name}Read.model_validate(row) for row in resp.json()]",
        "",
        "",
        f"    def create_{low}(self, item: {name}Create) -> {name}Read:",
        f'        """``POST {prefix}/`` — create a {name}."""',
        f'        resp = self._client.post("{prefix}/", json=item.model_dump())',
        "        resp.raise_for_status()",
        f"        return {name}Read.model_validate(resp.json())",
    ]

    if _pk_field(schema, name) is not None:
        lines += [
            "",
            "",
            f"    def get_{low}(self, item_id: {pk_py}) -> {name}Read:",
            f'        """``GET {prefix}/{{item_id}}`` — fetch one {name}."""',
            f'        resp = self._client.get(f"{prefix}/{{item_id}}")',
            "        resp.raise_for_status()",
            f"        return {name}Read.model_validate(resp.json())",
            "",
            "",
            f"    def update_{low}(self, item_id: {pk_py}, item: {name}Update) -> {name}Read:",
            f'        """``PATCH {prefix}/{{item_id}}`` — partial update."""',
            f'        resp = self._client.patch(',
            f'            f"{prefix}/{{item_id}}", json=item.model_dump(exclude_unset=True)',
            "        )",
            "        resp.raise_for_status()",
            f"        return {name}Read.model_validate(resp.json())",
            "",
            "",
            f"    def delete_{low}(self, item_id: {pk_py}) -> None:",
            f'        """``DELETE {prefix}/{{item_id}}`` — remove a {name}."""',
            f'        resp = self._client.delete(f"{prefix}/{{item_id}}")',
            "        resp.raise_for_status()",
        ]
    return "\n".join(lines)


def render_http_client(
    schema_text: str, source_file: str = "prisma/schema.prisma"
) -> str:
    """Render ``clients/http_client.py`` — typed httpx CRUD client for schema-derived routes."""
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    names = _model_names(schema, schema_text)

    table_imports: Set[str] = set()
    for n in names:
        table_imports.add(n)
        table_imports.add(f"{n}Create")
        table_imports.add(f"{n}Read")
        if _pk_field(schema, n) is not None:
            table_imports.add(f"{n}Update")

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
        "        self._client = client or httpx.Client(base_url=self._base_url)",
        "",
        "    def close(self) -> None:",
        "        self._client.close()",
        "",
        "    def __enter__(self) -> \"ApiClient\":",
        "        return self",
        "",
        "    def __exit__(self, *exc: object) -> None:",
        "        self.close()",
    ]

    blocks = [_entity_methods(schema, schema_text, n) for n in names]
    body = imports + "\n\n" + "\n".join(class_lines)
    if blocks:
        body += "\n" + "\n\n\n".join(blocks)
    body += "\n"
    return header + "\n\n" + body
