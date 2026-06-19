"""Minimal .proto parser for gRPC skeleton generation (benchmark-shaped protos)."""

from __future__ import annotations

import re
from typing import List

from .models import ProtoDocument, ProtoRpc, ProtoService

_PACKAGE_RE = re.compile(r"^\s*package\s+(\w+)\s*;", re.M)
_GO_PACKAGE_RE = re.compile(r'^\s*option\s+go_package\s*=\s*"([^"]+)"\s*;', re.M)
_SERVICE_START_RE = re.compile(r"service\s+(\w+)\s*\{")
# Tolerate the optional `stream` keyword on request/response so streaming RPCs are not
# silently dropped from the generated skeleton (they'd otherwise leave the servicer
# missing methods → runtime errors when gRPC dispatches the call).
_RPC_RE = re.compile(
    r"rpc\s+(\w+)\s*\(\s*(?:stream\s+)?(\w+)\s*\)\s*returns\s*\(\s*(?:stream\s+)?(\w+)\s*\)",
)


def _extract_braced_body(text: str, open_brace_index: int) -> str:
    """Return the inner text of a ``{...}`` block starting at ``open_brace_index``."""
    depth = 0
    start = None
    for i, ch in enumerate(text[open_brace_index:], start=open_brace_index):
        if ch == "{":
            depth += 1
            if depth == 1:
                start = i + 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                return text[start:i]
    return ""


def parse_proto(text: str) -> ProtoDocument:
    """Parse services and RPCs from a ``.proto`` file (comments ignored)."""
    stripped = re.sub(r"//.*?$", "", text, flags=re.M)
    pkg_m = _PACKAGE_RE.search(stripped)
    go_m = _GO_PACKAGE_RE.search(stripped)
    services: List[ProtoService] = []
    for match in _SERVICE_START_RE.finditer(stripped):
        name = match.group(1)
        brace_at = stripped.find("{", match.start())
        body = _extract_braced_body(stripped, brace_at)
        rpcs = [
            ProtoRpc(name=rpc_name, request=req, response=res)
            for rpc_name, req, res in _RPC_RE.findall(body)
        ]
        services.append(ProtoService(name=name, rpcs=tuple(rpcs)))
    return ProtoDocument(
        package=pkg_m.group(1) if pkg_m else "",
        services=tuple(services),
        go_package=go_m.group(1) if go_m else None,
    )


def get_service(doc: ProtoDocument, service_name: str) -> ProtoService:
    for svc in doc.services:
        if svc.name == service_name:
            return svc
    names = ", ".join(s.name for s in doc.services) or "(none)"
    raise ValueError(f"service {service_name!r} not found in proto; available: {names}")
