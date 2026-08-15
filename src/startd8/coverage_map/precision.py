"""Tier-2 precision layer: per-domain contract-IDL registry → precise operations.

The coverage map (Tier 1) answers *"does this repo TOUCH §5 domain X?"* from imports — and the
session finding is that coverage **saturates at imports**. Precision (Tier 2) answers the next
question — *"WHICH operations, and what role?"* — by parsing the domain's **contract IDL**, wiring
the SDK's existing IDL parsers (Mottainai: cite, don't rebuild):

    http → OpenAPI  (backend_codegen.openapi_normalize.load_openapi_document)
    rpc  → Protocol Buffers (proto_codegen.proto_parser.parse_proto)
    db   → Prisma schema     (languages.prisma_parser.parse_prisma_schema)

Precision is **available only where a contract IDL exists** in the repo — otherwise it is a
correct-absence (coverage-only), the same honesty the coverage floor uses. This is the twin of the
coverage crosswalk: coverage = "domain → import signatures"; precision = "domain → IDL + its parser".

Pattern: dev-os/LANGUAGE-DOMAIN-COVERAGE-MAP.md (§ three-tier stack). Spec:
docs/design/REQ-precision-layer-contract-idl-operations.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from startd8.backend_codegen.openapi_normalize import load_openapi_document
from startd8.languages.prisma_parser import parse_prisma_schema
from startd8.proto_codegen.proto_parser import parse_proto

_HTTP_METHODS = ("get", "put", "post", "delete", "patch", "options", "head", "trace")
_EXCLUDE_SEG = frozenset({"node_modules", "vendor", "dist", "build", ".git"})


def _http_ops(path: Path) -> list[dict[str, Any]]:
    """OpenAPI 3.0 spec → server endpoints (path × method)."""
    spec = load_openapi_document(path)  # raises ValueError on non-3.0 / malformed
    ops: list[dict[str, Any]] = []
    for route, item in (spec.get("paths") or {}).items():
        if not isinstance(item, dict):
            continue
        for method in _HTTP_METHODS:
            op = item.get(method)
            if isinstance(op, dict):
                ops.append({
                    "op": f"{method.upper()} {route}",
                    "operation_id": op.get("operationId"),
                    "role": "SERVER",
                })
    return ops


def _rpc_ops(path: Path) -> list[dict[str, Any]]:
    """.proto → gRPC service methods (with request/response types)."""
    doc = parse_proto(path.read_text(encoding="utf-8", errors="replace"))
    return [
        {"op": f"{svc.name}.{rpc.name}", "request": rpc.request, "response": rpc.response, "role": "SERVER"}
        for svc in doc.services for rpc in svc.rpcs
    ]


def _db_ops(path: Path) -> list[dict[str, Any]]:
    """Prisma schema → data models (with field counts)."""
    schema = parse_prisma_schema(path.read_text(encoding="utf-8", errors="replace"))
    return [
        {"op": name, "kind": "model", "fields": len(model.fields)}
        for name, model in schema.models.items()
    ]


#: domain → its contract IDL + parser. The precision twin of the coverage crosswalk.
PRECISION_DOMAINS: dict[str, dict[str, Any]] = {
    "http": {"idl": "OpenAPI", "extract": _http_ops,
             "globs": ("**/openapi*.yaml", "**/openapi*.yml", "**/openapi*.json",
                       "**/swagger*.yaml", "**/swagger*.yml", "**/swagger*.json", "**/api.yaml")},
    "rpc":  {"idl": "Protocol Buffers", "extract": _rpc_ops, "globs": ("**/*.proto",)},
    "db":   {"idl": "Prisma schema", "extract": _db_ops, "globs": ("**/*.prisma",)},
}


def _find_idls(repo_root: Path, globs: tuple[str, ...]) -> list[Path]:
    seen: set[Path] = set()
    for g in globs:
        for p in repo_root.glob(g):
            if p.is_file() and not any(seg in _EXCLUDE_SEG for seg in p.parts):
                seen.add(p)
    return sorted(seen)


def extract_precision(repo_root: Path, domain: str) -> dict[str, Any]:
    """For one domain, find its contract IDL(s) and extract the precise operations.

    Returns {domain, idl_type, idl_files:[{path, operations, count}], total_operations, parse_errors}.
    total_operations == 0 with no idl_files ⇒ precision unavailable (coverage-only) — a correct-absence.
    """
    spec = PRECISION_DOMAINS.get(domain)
    if spec is None:
        raise KeyError(f"no precision extractor for domain {domain!r}")
    files, errors = [], []
    for path in _find_idls(repo_root, spec["globs"]):
        try:
            ops = spec["extract"](path)
        except Exception as exc:  # un-parseable IDL (e.g. swagger 2.0) — record, don't crash
            errors.append({"path": str(path.relative_to(repo_root)), "error": f"{type(exc).__name__}: {exc}"})
            continue
        files.append({"path": str(path.relative_to(repo_root)), "operations": ops, "count": len(ops)})
    return {
        "domain": domain,
        "idl_type": spec["idl"],
        "idl_files": files,
        "total_operations": sum(f["count"] for f in files),
        "parse_errors": errors,
        "precision_available": bool(files),
    }
