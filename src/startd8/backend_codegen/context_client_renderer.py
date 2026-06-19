"""Inter-context consumer client renderer (OpenAPI Role 3 — M1).

Emits ``clients/{producer_id}_client.py`` — a typed httpx wrapper for an outbound producer
context declared in ``contexts.yaml``. Methods reuse the Role 1/2 client emitter; the producer
contract is pinned via ``contract-sha256`` drift.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ..frontend_codegen.schema_renderer import schema_sha256
from ..languages.prisma_parser import PrismaSchema, parse_prisma_schema
from ._headers import header_context_client
from .context_manifest import (
    OutboundContext,
    contract_sha256,
    filter_spec_for_context,
    load_contract_spec,
    parse_contexts,
)
from .crud_generator import _pk_field
from .openapi_client_renderer import (
    _entity_methods,
    _op_json_ref,
    _overlay_client_methods,
    _pinned_spec_methods,
    _prisma_dto_names,
)
from .openapi_contract_renderer import _model_names, _project_openapi


def _class_name(ctx_id: str) -> str:
    parts = [p for p in re.split(r"[^0-9a-zA-Z]+", ctx_id) if p]
    return "".join(p[:1].upper() + p[1:] for p in parts) + "Client"


def _resolve_producer_spec(
    schema_text: str,
    ctx: OutboundContext,
    *,
    api_text: Optional[str] = None,
    manifest_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    views_text: Optional[str] = None,
    imports_text: Optional[str] = None,
    project_root: Optional[str] = None,
) -> Dict[str, Any]:
    if ctx.local:
        _, spec = _project_openapi(
            schema_text,
            api_text=api_text,
            manifest_text=manifest_text,
            pages_text=pages_text,
            views_text=views_text,
            imports_text=imports_text,
        )
        return spec
    from pathlib import Path

    root = Path(project_root) if project_root else None
    return load_contract_spec(ctx.contract, project_root=root)


def render_context_client(
    schema_text: str,
    contexts_text: str,
    ctx: OutboundContext,
    source_file: str = "prisma/schema.prisma",
    *,
    api_text: Optional[str] = None,
    manifest_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    views_text: Optional[str] = None,
    imports_text: Optional[str] = None,
    project_root: Optional[str] = None,
) -> str:
    """Render ``clients/{id}_client.py`` for one outbound context."""
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    contexts_sha = schema_sha256(contexts_text)
    raw_spec = _resolve_producer_spec(
        schema_text,
        ctx,
        api_text=api_text,
        manifest_text=manifest_text,
        pages_text=pages_text,
        views_text=views_text,
        imports_text=imports_text,
        project_root=project_root,
    )
    spec = filter_spec_for_context(raw_spec, schema_text, ctx)
    contract_sha = contract_sha256(spec)
    class_name = _class_name(ctx.id)
    pinned = not ctx.local

    table_imports: Set[str] = set()
    if not pinned:
        for n in _model_names(schema, schema_text):
            table_imports.add(n)
            table_imports.add(f"{n}Create")
            table_imports.add(f"{n}Read")
            if _pk_field(schema, n) is not None:
                table_imports.add(f"{n}Update")
        for _, path_item in spec.get("paths", {}).items():
            if not isinstance(path_item, dict):
                continue
            for method in path_item:
                op = path_item.get(method)
                if not isinstance(op, dict):
                    continue
                for dto in (_op_json_ref(op, response=False), _op_json_ref(op, response=True)):
                    if dto and dto in _prisma_dto_names(schema, schema_text):
                        table_imports.add(dto)

    if pinned:
        method_block = _pinned_spec_methods(spec, use_traced_request=True)
        blocks = [method_block] if method_block else []
    else:
        blocks = [
            _entity_methods(schema, schema_text, n, use_traced_request=True)
            for n in _model_names(schema, schema_text)
        ]
        overlay_block = _overlay_client_methods(
            schema, schema_text, spec, use_traced_request=True
        )
        if overlay_block:
            blocks.append(overlay_block)

    header = header_context_client(
        source_file,
        sha,
        contexts_sha,
        contract_sha,
        "python-context-client",
        producer_id=ctx.id,
    )
    base_doc = ctx.base_url or "(configure at runtime)"
    source_doc = "local OPENAPI_SPEC" if ctx.local else ctx.contract
    imports = "from __future__ import annotations\n\nimport httpx\n\n"
    imports += "from clients._context_otel import trace_outbound_request\n\n"
    if table_imports:
        imports += (
            "from app.tables import " + ", ".join(sorted(table_imports)) + "\n"
        )
    class_lines = [
        f"class {class_name}:",
        f'    """Typed HTTP client for outbound context {ctx.id!r} ({source_doc})."""',
        f"    # Default base URL (override in __init__): {base_doc}",
        "",
        "    def __init__(self, base_url: str, *, client: httpx.Client | None = None) -> None:",
        "        self._base_url = base_url.rstrip(\"/\")",
        "        if client is not None:",
        "            self._client = client",
        "            self._owns_client = False",
        "        else:",
        "            self._client = httpx.Client(base_url=self._base_url)",
        "            self._owns_client = True",
        f'        self._producer_id = "{ctx.id}"',
        "",
        "    def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:",
        "        def _do() -> httpx.Response:",
        f"            return getattr(self._client, method.lower())(path, **kwargs)",
        "        return trace_outbound_request(self._producer_id, method, path, _do)",
        "",
        "    def close(self) -> None:",
        "        if self._owns_client:",
        "            self._client.close()",
        "",
        f"    def __enter__(self) -> \"{class_name}\":",
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


def render_context_clients(
    schema_text: str,
    contexts_text: str,
    source_file: str = "prisma/schema.prisma",
    *,
    api_text: Optional[str] = None,
    manifest_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    views_text: Optional[str] = None,
    imports_text: Optional[str] = None,
    project_root: Optional[str] = None,
) -> List[Tuple[str, str]]:
    """All ``(relative_path, text)`` pairs for declared outbound contexts."""
    pairs: List[Tuple[str, str]] = []
    for ctx in parse_contexts(contexts_text):
        rel = f"clients/{ctx.id}_client.py"
        pairs.append(
            (
                rel,
                render_context_client(
                    schema_text,
                    contexts_text,
                    ctx,
                    source_file,
                    api_text=api_text,
                    manifest_text=manifest_text,
                    pages_text=pages_text,
                    views_text=views_text,
                    imports_text=imports_text,
                    project_root=project_root,
                ),
            )
        )
    return pairs


def client_method_paths(text: str) -> Set[Tuple[str, str]]:
    """Best-effort scan of generated method docstrings ``METHOD path`` for FR-7 tests."""
    paths: Set[Tuple[str, str]] = set()
    for match in re.finditer(r"``(GET|POST|PATCH|DELETE|PUT)\s+([^`]+)``", text):
        paths.add((match.group(1), match.group(2).strip()))
    return paths
