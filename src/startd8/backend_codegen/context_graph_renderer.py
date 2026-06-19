"""Machine-readable inter-context graph export (OpenAPI Role 3 — deferred D4).

Emits ``openapi/context-graph.json`` — a platform-neutral graph of outbound producer dependencies
for CI, Terraform, or mesh tooling (not full gateway codegen).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..frontend_codegen.schema_renderer import schema_sha256
from .context_client_renderer import _resolve_producer_spec
from .context_manifest import (
    contract_sha256,
    filter_spec_for_context,
    load_proto_contract,
    parse_contexts_file,
    proto_contract_sha256,
)

CONTEXT_GRAPH_PATH = "openapi/context-graph.json"
_SCHEMA_VERSION = 1


def build_context_graph(
    schema_text: str,
    contexts_text: str,
    *,
    project_root: Optional[str] = None,
    source_file: str = "prisma/schema.prisma",
) -> Dict[str, Any]:
    """Build the context graph dict from schema + contexts manifest."""
    manifest = parse_contexts_file(contexts_text)
    root = Path(project_root) if project_root else None
    nodes: List[Dict[str, Any]] = []
    for ctx in manifest.outbound:
        node: Dict[str, Any] = {
            "id": ctx.id,
            "protocol": ctx.protocol,
            "local": ctx.local,
            "contract": ctx.contract,
            "base_url": ctx.base_url,
            "routes": ctx.routes,
            "schemas": list(ctx.schemas),
            "clients": {},
        }
        if ctx.grpc_service:
            node["grpc_service"] = ctx.grpc_service
        if ctx.auth:
            node["auth"] = {
                "scheme": ctx.auth.scheme,
                "env": ctx.auth.env,
                "header": ctx.auth.header,
            }
        if ctx.protocol == "grpc":
            proto_text = load_proto_contract(ctx.contract, project_root=root)
            node["contract_sha256"] = proto_contract_sha256(proto_text)
            node["clients"]["python_grpc"] = f"clients/{ctx.id}_grpc_client.py"
        else:
            raw = _resolve_producer_spec(
                schema_text, ctx, project_root=project_root
            )
            filtered = filter_spec_for_context(raw, schema_text, ctx)
            node["contract_sha256"] = contract_sha256(filtered)
            node["clients"]["python"] = f"clients/{ctx.id}_client.py"
            if "typescript" in manifest.emit_languages:
                node["clients"]["typescript"] = f"clients/{ctx.id}_client.ts"
        nodes.append(node)
    return {
        "schema_version": _SCHEMA_VERSION,
        "source_file": source_file,
        "schema_sha256": schema_sha256(schema_text),
        "contexts_sha256": schema_sha256(contexts_text),
        "emit_languages": list(manifest.emit_languages),
        "outbound": nodes,
    }


def render_context_graph(
    schema_text: str,
    contexts_text: str,
    *,
    project_root: Optional[str] = None,
    source_file: str = "prisma/schema.prisma",
) -> str:
    """Canonical JSON for ``openapi/context-graph.json``."""
    graph = build_context_graph(
        schema_text,
        contexts_text,
        project_root=project_root,
        source_file=source_file,
    )
    return json.dumps(graph, indent=2, sort_keys=True) + "\n"
