"""TypeScript outbound context client (OpenAPI Role 3 — deferred D3).

Emits ``clients/{id}_client.ts`` when ``emit_languages: [typescript]`` is set in contexts.yaml.
Uses fetch + pinned-contract paths (dict bodies) — no consumer Prisma DTO coupling.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from ..frontend_codegen.schema_renderer import schema_sha256
from .context_client_renderer import _class_name, _resolve_producer_spec
from .context_manifest import (
    OutboundContext,
    contract_sha256,
    filter_spec_for_context,
    parse_contexts_file,
)
from .openapi_client_renderer import (
    _HTTP_METHODS,
    _crud_method_name,
    _overlay_method_name,
    _path_param_names,
    _response_json_kind,
)

CONTEXT_TS_CLIENT_KIND = "typescript-context-client"


def _ts_header(
    source_file: str,
    schema_sha: str,
    contexts_sha: str,
    contract_sha: str,
    producer_id: str,
) -> str:
    return (
        f"// GENERATED from {source_file} (+ contexts.yaml) — do not edit by hand.\n"
        f"// startd8-artifact: {CONTEXT_TS_CLIENT_KIND}\n"
        f"// startd8-entity: {producer_id}\n"
        f"// schema-sha256: {schema_sha}\n"
        f"// contexts-sha256: {contexts_sha}\n"
        f"// contract-sha256: {contract_sha}"
    )


def _ts_auth_lines(auth_env: Optional[str], auth_scheme: str, auth_header: str) -> List[str]:
    if not auth_env:
        return [
            "  private authHeaders(): Record<string, string> {",
            "    return {};",
            "  }",
        ]
    if auth_scheme == "bearer":
        return [
            f"  private static readonly AUTH_ENV = {auth_env!r};",
            f"  private static readonly AUTH_HEADER = {auth_header!r};",
            "  private authHeaders(): Record<string, string> {",
            "    const token = (process.env[this.AUTH_ENV] ?? '').trim();",
            "    if (!token) return {};",
            "    return { [this.AUTH_HEADER]: `Bearer ${token}` };",
            "  }",
        ]
    return [
        f"  private static readonly AUTH_ENV = {auth_env!r};",
        f"  private static readonly AUTH_HEADER = {auth_header!r};",
        "  private authHeaders(): Record<string, string> {",
        "    const token = (process.env[this.AUTH_ENV] ?? '').trim();",
        "    if (!token) return {};",
        "    return { [this.AUTH_HEADER]: token };",
        "  }",
    ]


def _ts_url_expr(path: str) -> str:
    params = _path_param_names(path)
    if not params:
        return f"`{path}`"
    escaped = path
    for name in params:
        escaped = escaped.replace("{" + name + "}", "${" + name + "}")
    return f"`{escaped}`"


def _ts_method_blocks(spec: Dict[str, Any]) -> str:
    blocks: List[str] = []
    for path, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, op in path_item.items():
            if method not in _HTTP_METHODS or not isinstance(op, dict):
                continue
            http = method.upper()
            fn = _crud_method_name(http, path) or _overlay_method_name(http, path)
            params = _path_param_names(path)
            sig_parts = [f"{name}: string" for name in params]
            has_body = bool(
                op.get("requestBody", {})
                .get("content", {})
                .get("application/json")
            )
            if has_body:
                sig_parts.append("body: Record<string, unknown>")
            signature = ", ".join(sig_parts)
            ts_url = _ts_url_expr(path)
            resp_kind = _response_json_kind(op)
            ret_type = (
                "Promise<Record<string, unknown>[]>"
                if resp_kind == "array"
                else "Promise<Record<string, unknown>>"
                if resp_kind == "object"
                else "Promise<void>"
            )
            body_line = (
                "body: JSON.stringify(body),"
                if has_body
                else ""
            )
            blocks.append(
                "\n".join(
                    [
                        f"  async {fn}({signature}): {ret_type} {{",
                        f'    const resp = await this.request({http!r}, {ts_url}, {{',
                        *(["      " + body_line] if body_line else []),
                        "    }});",
                        "    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);",
                        *(
                            ["    return (await resp.json()) as Record<string, unknown>[];"]
                            if resp_kind == "array"
                            else ["    return (await resp.json()) as Record<string, unknown>;"]
                            if resp_kind == "object"
                            else []
                        ),
                        "  }",
                    ]
                )
            )
    return "\n\n".join(blocks)


def render_context_ts_client(
    schema_text: str,
    contexts_text: str,
    ctx: OutboundContext,
    source_file: str = "prisma/schema.prisma",
    *,
    project_root: Optional[str] = None,
    **kwargs: Any,
) -> str:
    """Render ``clients/{id}_client.ts`` for one outbound HTTP context."""
    if ctx.protocol != "http":
        return ""
    raw_spec = _resolve_producer_spec(
        schema_text, ctx, project_root=project_root, **kwargs
    )
    spec = filter_spec_for_context(raw_spec, schema_text, ctx)
    contract_sha = contract_sha256(spec)
    class_name = _class_name(ctx.id)
    sha = schema_sha256(schema_text)
    contexts_sha = schema_sha256(contexts_text)
    header = _ts_header(source_file, sha, contexts_sha, contract_sha, ctx.id)
    auth_env = ctx.auth.env if ctx.auth else None
    auth_scheme = ctx.auth.scheme if ctx.auth else ""
    auth_header = ctx.auth.header if ctx.auth else "Authorization"
    methods = _ts_method_blocks(spec)
    lines = [
        f"export class {class_name} {{",
        "  constructor(private readonly baseUrl: string) {}",
        "",
        "  private async request(method: string, path: string, init: RequestInit = {}): Promise<Response> {",
        "    const headers: Record<string, string> = {",
        "      ...this.authHeaders(),",
        "      ...(init.headers as Record<string, string> ?? {}),",
        "    };",
        "    if (init.body !== undefined) {",
        "      headers['content-type'] = 'application/json';",
        "    }",
        "    const url = `${this.baseUrl.replace(/\\/$/, '')}${path}`;",
        "    return fetch(url, { ...init, method, headers });",
        "  }",
        "",
        *(_ts_auth_lines(auth_env, auth_scheme, auth_header)),
    ]
    if methods:
        lines.append("")
        lines.append(methods)
    lines.append("}")
    return header + "\n\n" + "\n".join(lines) + "\n"


def render_context_ts_clients(
    schema_text: str,
    contexts_text: str,
    source_file: str = "prisma/schema.prisma",
    *,
    project_root: Optional[str] = None,
    **kwargs: Any,
) -> List[Tuple[str, str]]:
    """Emit TypeScript clients when ``emit_languages`` includes ``typescript``."""
    manifest = parse_contexts_file(contexts_text)
    if "typescript" not in manifest.emit_languages:
        return []
    pairs: List[Tuple[str, str]] = []
    for ctx in manifest.outbound:
        if ctx.protocol != "http":
            continue
        text = render_context_ts_client(
            schema_text,
            contexts_text,
            ctx,
            source_file,
            project_root=project_root,
            **kwargs,
        )
        if text:
            pairs.append((f"clients/{ctx.id}_client.ts", text))
    return pairs
