"""``contexts.yaml`` — inter-context outbound HTTP dependencies (OpenAPI Role 3).

Declares producer contexts this app consumes across a process boundary. Each outbound entry
pins a **contract snapshot** (``contract:`` path) or uses the **local** merged ``OPENAPI_SPEC``
from the same ``generate backend`` pass (``local: true``). The SDK emits typed
``clients/{id}_client.py`` artifacts with ``contract-sha256`` drift.

Closed grammar; tolerant of absence (no ``outbound:`` → no context clients, SOTTO).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import yaml

from ..frontend_codegen.schema_renderer import schema_sha256
from ..schema_contract.prisma_json_schema import model_names
from .openapi_contract_renderer import _crud_routes
from .openapi_client_renderer import _prisma_dto_names

_ROUTE_MODES = frozenset({"crud", "all_json"})
_PROTOCOLS = frozenset({"http", "grpc"})
_AUTH_SCHEMES = frozenset({"bearer", "api_key", "header"})
_EMIT_LANGUAGES = frozenset({"typescript"})
_TOP_KEYS = frozenset({"outbound", "emit_languages"})
_ENTRY_KEYS = frozenset({
    "id", "local", "contract", "base_url", "routes", "schemas",
    "auth", "protocol", "grpc_service",
})
_AUTH_KEYS = frozenset({"scheme", "env", "header"})
_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})


@dataclass(frozen=True)
class ContextAuth:
    """Optional outbound auth hook — credential read from env at request time."""

    scheme: str
    env: str
    header: str = ""


@dataclass(frozen=True)
class OutboundContext:
    """One outbound producer context."""

    id: str
    local: bool
    contract: str = ""
    base_url: str = ""
    routes: str = "crud"
    schemas: Tuple[str, ...] = ()
    auth: Optional[ContextAuth] = None
    protocol: str = "http"
    grpc_service: str = ""


@dataclass(frozen=True)
class ContextsFile:
    """Parsed ``contexts.yaml`` file (outbound entries + optional emit languages)."""

    outbound: Tuple[OutboundContext, ...] = ()
    emit_languages: Tuple[str, ...] = ()


def _parse_auth(ctx_id: str, raw: Any, index: int) -> Optional[ContextAuth]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError(f"contexts.yaml: outbound #{index} `auth` must be a mapping")
    unknown = set(raw) - _AUTH_KEYS
    if unknown:
        raise ValueError(
            f"contexts.yaml: outbound {ctx_id!r} auth has unknown keys {sorted(unknown)}"
        )
    scheme = str(raw.get("scheme") or "bearer").strip().lower()
    if scheme not in _AUTH_SCHEMES:
        raise ValueError(
            f"contexts.yaml: outbound {ctx_id!r}: auth.scheme must be one of {sorted(_AUTH_SCHEMES)}"
        )
    env = str(raw.get("env") or "").strip()
    if not env:
        raise ValueError(f"contexts.yaml: outbound {ctx_id!r}: auth.env is required")
    header = str(raw.get("header") or "").strip()
    if scheme == "header" and not header:
        raise ValueError(
            f"contexts.yaml: outbound {ctx_id!r}: auth.header is required when scheme is header"
        )
    if scheme == "api_key" and not header:
        header = "X-Api-Key"
    if scheme == "bearer" and not header:
        header = "Authorization"
    return ContextAuth(scheme=scheme, env=env, header=header)


def parse_contexts_file(text: Optional[str]) -> ContextsFile:
    """Parse full ``contexts.yaml`` including top-level ``emit_languages``."""
    data = yaml.safe_load(text or "") or {}
    if not isinstance(data, dict):
        raise ValueError("contexts.yaml must be a mapping")
    unknown_top = set(data) - _TOP_KEYS
    if unknown_top:
        raise ValueError(f"contexts.yaml has unknown top-level keys {sorted(unknown_top)}")
    raw_emit = data.get("emit_languages") or []
    if raw_emit and not isinstance(raw_emit, list):
        raise ValueError("contexts.yaml: `emit_languages` must be a list")
    emit_langs = tuple(
        lang
        for lang in (
            str(x).strip().lower() for x in raw_emit if str(x).strip()
        )
        if lang in _EMIT_LANGUAGES
    )
    if raw_emit and not emit_langs:
        raise ValueError(
            f"contexts.yaml: emit_languages must include one of {sorted(_EMIT_LANGUAGES)}"
        )
    if "outbound" not in data:
        return ContextsFile(emit_languages=emit_langs)
    raw = data["outbound"] or []
    if not isinstance(raw, list):
        raise ValueError("contexts.yaml: `outbound` must be a list")
    out: List[OutboundContext] = []
    seen: Set[str] = set()
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"contexts.yaml: outbound #{i} must be a mapping")
        unknown = set(entry) - _ENTRY_KEYS
        if unknown:
            raise ValueError(f"contexts.yaml: outbound #{i} has unknown keys {sorted(unknown)}")
        ctx_id = str(entry.get("id") or "").strip()
        if not ctx_id:
            raise ValueError(f"contexts.yaml: outbound #{i} missing required `id`")
        if not ctx_id.replace("_", "").isalnum():
            raise ValueError(f"contexts.yaml: outbound #{i} `id` must be alphanumeric/snake: {ctx_id!r}")
        if ctx_id in seen:
            raise ValueError(f"contexts.yaml: duplicate outbound id {ctx_id!r}")
        seen.add(ctx_id)
        protocol = str(entry.get("protocol") or "http").strip().lower()
        if protocol not in _PROTOCOLS:
            raise ValueError(
                f"contexts.yaml: outbound {ctx_id!r}: `protocol` must be one of {sorted(_PROTOCOLS)}"
            )
        local = bool(entry.get("local"))
        contract = str(entry.get("contract") or "").strip()
        if local and contract:
            raise ValueError(f"contexts.yaml: outbound {ctx_id!r}: set `local: true` OR `contract`, not both")
        if not local and not contract:
            raise ValueError(f"contexts.yaml: outbound {ctx_id!r}: requires `local: true` or `contract`")
        grpc_service = str(entry.get("grpc_service") or "").strip()
        if protocol == "grpc":
            if not grpc_service:
                raise ValueError(
                    f"contexts.yaml: outbound {ctx_id!r}: `grpc_service` required when protocol is grpc"
                )
            if not contract.endswith(".proto"):
                raise ValueError(
                    f"contexts.yaml: outbound {ctx_id!r}: grpc contract must be a .proto path"
                )
        routes = str(entry.get("routes") or "crud").strip().lower()
        if routes not in _ROUTE_MODES:
            raise ValueError(
                f"contexts.yaml: outbound {ctx_id!r}: `routes` must be one of {sorted(_ROUTE_MODES)}"
            )
        base_url = str(entry.get("base_url") or "").strip()
        raw_schemas = entry.get("schemas") or []
        if raw_schemas and not isinstance(raw_schemas, list):
            raise ValueError(f"contexts.yaml: outbound {ctx_id!r}: `schemas` must be a list")
        schemas = tuple(str(s).strip() for s in raw_schemas if str(s).strip())
        auth = _parse_auth(ctx_id, entry.get("auth"), i)
        out.append(
            OutboundContext(
                id=ctx_id,
                local=local,
                contract=contract,
                base_url=base_url,
                routes=routes,
                schemas=schemas,
                auth=auth,
                protocol=protocol,
                grpc_service=grpc_service,
            )
        )
    return ContextsFile(outbound=tuple(out), emit_languages=emit_langs)


def parse_contexts(text: Optional[str]) -> Tuple[OutboundContext, ...]:
    """Parse ``contexts.yaml`` → outbound contexts. Absent/empty → ``()``."""
    return parse_contexts_file(text).outbound


def contract_sha256(spec: Dict[str, Any]) -> str:
    """Content hash of a filtered OpenAPI spec dict (canonical JSON, Role 3 FR-4)."""
    payload = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    return schema_sha256(payload)


def load_contract_spec(contract_path: str, *, project_root: Optional[Path] = None) -> Dict[str, Any]:
    """Load an OpenAPI JSON contract snapshot from disk."""
    path = Path(contract_path)
    if not path.is_absolute() and project_root is not None:
        path = project_root / path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"context contract unreadable: {contract_path} ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"context contract not valid JSON: {contract_path} ({exc})") from exc
    if not isinstance(data, dict) or "paths" not in data:
        raise ValueError(f"context contract must be an OpenAPI mapping with `paths`: {contract_path}")
    return data


def load_proto_contract(contract_path: str, *, project_root: Optional[Path] = None) -> str:
    """Load a ``.proto`` contract snapshot from disk."""
    path = Path(contract_path)
    if not path.is_absolute() and project_root is not None:
        path = project_root / path
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"context proto unreadable: {contract_path} ({exc})") from exc


def proto_contract_sha256(proto_text: str) -> str:
    """Content hash of a pinned ``.proto`` contract (Role 3 gRPC seam)."""
    return schema_sha256(proto_text)


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
        schema = content.get("schema", {})
        if schema.get("type") == "array":
            return _ref_name(schema.get("items", {}).get("$ref"))
        return _ref_name(schema.get("$ref"))
    body = op.get("requestBody", {})
    content = body.get("content", {}).get("application/json", {})
    return _ref_name(content.get("schema", {}).get("$ref"))


def _openapi_crud_paths(spec: Dict[str, Any]) -> Set[Tuple[str, str]]:
    """Detect collection/item CRUD paths from a producer OpenAPI spec (no Prisma)."""
    kept: Set[Tuple[str, str]] = set()
    for path, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        is_collection = path.endswith("/") and "{" not in path
        is_item = "{" in path
        for method, op in path_item.items():
            if method not in _HTTP_METHODS or not isinstance(op, dict):
                continue
            http = method.upper()
            if is_collection and http in ("GET", "POST"):
                kept.add((http, path))
            elif is_item and http in ("GET", "PATCH", "DELETE", "PUT"):
                kept.add((http, path))
    return kept


def _schema_refs_from_paths(
    spec: Dict[str, Any], kept_paths: Set[Tuple[str, str]]
) -> Set[str]:
    refs: Set[str] = set()
    paths = spec.get("paths", {})
    for method, path in kept_paths:
        path_item = paths.get(path, {})
        if not isinstance(path_item, dict):
            continue
        op = path_item.get(method.lower())
        if not isinstance(op, dict):
            continue
        for dto in (_op_json_ref(op, response=False), _op_json_ref(op, response=True)):
            if dto:
                refs.add(dto)
    return refs


def filter_spec_for_context(
    spec: Dict[str, Any],
    schema_text: str,
    ctx: OutboundContext,
) -> Dict[str, Any]:
    """Filter a producer spec for one outbound context entry."""
    return filter_spec_for_client(
        spec,
        schema_text,
        routes=ctx.routes,
        pinned_contract=not ctx.local,
        explicit_schemas=ctx.schemas or None,
    )


def filter_spec_for_client(
    spec: Dict[str, Any],
    schema_text: str,
    *,
    routes: str = "crud",
    pinned_contract: bool = False,
    explicit_schemas: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Subset a producer spec to client-emittable JSON routes (FR-3 / OQ-3 / M5).

    When ``pinned_contract`` is True (remote ``contract:`` pin), filtering uses the
    producer OpenAPI paths/schemas directly — the consumer Prisma schema is not required
    to share entity names with the producer (cross-repo seam).
    """
    from ..languages.prisma_parser import parse_prisma_schema

    schema = parse_prisma_schema(schema_text)
    if pinned_contract:
        if routes == "crud":
            kept = _openapi_crud_paths(spec)
            filtered_paths: Dict[str, Any] = {}
            for method, path in sorted(kept):
                path_item = spec.get("paths", {}).get(path, {})
                if not isinstance(path_item, dict):
                    continue
                op = path_item.get(method.lower())
                if isinstance(op, dict):
                    filtered_paths.setdefault(path, {})[method.lower()] = op
            schema_refs = _schema_refs_from_paths(spec, kept)
            if explicit_schemas:
                schema_refs.update(explicit_schemas)
            all_schemas = spec.get("components", {}).get("schemas", {})
            filtered_schemas = {
                name: all_schemas[name]
                for name in sorted(schema_refs)
                if isinstance(all_schemas, dict) and name in all_schemas
            }
            return {
                "openapi": spec.get("openapi", "3.0.3"),
                "info": spec.get("info", {"title": "context", "version": "0.0.0"}),
                "paths": filtered_paths,
                "components": {"schemas": filtered_schemas},
            }
        # pinned + all_json: keep every JSON op; schemas per explicit list or full set
        filtered_paths = {}
        for path, path_item in spec.get("paths", {}).items():
            if not isinstance(path_item, dict):
                continue
            kept_ops: Dict[str, Any] = {}
            for method, op in path_item.items():
                if method not in _HTTP_METHODS or not isinstance(op, dict):
                    continue
                req_ct = (
                    op.get("requestBody", {})
                    .get("content", {})
                    .get("application/json")
                )
                resp_ct = (
                    op.get("responses", {})
                    .get("200", {})
                    .get("content", {})
                    .get("application/json")
                )
                if req_ct or resp_ct:
                    kept_ops[method] = op
            if kept_ops:
                filtered_paths[path] = kept_ops
        all_schemas = spec.get("components", {}).get("schemas", {})
        if explicit_schemas and isinstance(all_schemas, dict):
            filtered_schemas = {
                name: all_schemas[name]
                for name in explicit_schemas
                if name in all_schemas
            }
        else:
            filtered_schemas = dict(all_schemas) if isinstance(all_schemas, dict) else {}
        return {
            "openapi": spec.get("openapi", "3.0.3"),
            "info": spec.get("info", {"title": "context", "version": "0.0.0"}),
            "paths": filtered_paths,
            "components": {"schemas": filtered_schemas},
        }

    crud = set(_crud_routes(schema, schema_text))
    dto_names = _prisma_dto_names(schema, schema_text)
    filtered_paths: Dict[str, Any] = {}
    for path, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        kept_ops: Dict[str, Any] = {}
        for method, op in path_item.items():
            if method not in _HTTP_METHODS or not isinstance(op, dict):
                continue
            http_method = method.upper()
            if routes == "crud":
                if (http_method, path) in crud:
                    kept_ops[method] = op
                    continue
                req = _op_json_ref(op, response=False)
                resp = _op_json_ref(op, response=True)
                if (req and req in dto_names) or (resp and resp in dto_names):
                    kept_ops[method] = op
            else:  # all_json
                req_ct = (
                    op.get("requestBody", {})
                    .get("content", {})
                    .get("application/json")
                )
                resp_ct = (
                    op.get("responses", {})
                    .get("200", {})
                    .get("content", {})
                    .get("application/json")
                )
                if req_ct or resp_ct:
                    kept_ops[method] = op
        if kept_ops:
            filtered_paths[path] = kept_ops
    schemas = spec.get("components", {}).get("schemas", {})
    if routes == "crud":
        keep_schema_names = set()
        for entity in model_names(schema, schema_text):
            keep_schema_names.update(
                {f"{entity}Create", f"{entity}Read", f"{entity}Update"}
            )
        filtered_schemas = {
            name: schemas[name]
            for name in sorted(keep_schema_names)
            if name in schemas
        }
    else:
        filtered_schemas = dict(schemas) if isinstance(schemas, dict) else {}
    return {
        "openapi": spec.get("openapi", "3.0.3"),
        "info": spec.get("info", {"title": "context", "version": "0.0.0"}),
        "paths": filtered_paths,
        "components": {"schemas": filtered_schemas},
    }
