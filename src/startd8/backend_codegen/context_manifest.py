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
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from ..frontend_codegen.schema_renderer import schema_sha256
from .openapi_contract_renderer import _crud_routes, _model_names
from .openapi_client_renderer import (
    _HTTP_METHODS,
    _op_json_ref,
    _prisma_dto_names,
)

_ROUTE_MODES = frozenset({"crud", "all_json"})
_KEYS = frozenset({"id", "local", "contract", "base_url", "routes"})


@dataclass(frozen=True)
class OutboundContext:
    """One outbound producer context."""

    id: str
    local: bool
    contract: str = ""
    base_url: str = ""
    routes: str = "crud"


def parse_contexts(text: Optional[str]) -> Tuple[OutboundContext, ...]:
    """Parse ``contexts.yaml`` → outbound contexts. Absent/empty → ``()``."""
    data = yaml.safe_load(text or "") or {}
    if not isinstance(data, dict) or "outbound" not in data:
        return ()
    raw = data["outbound"] or []
    if not isinstance(raw, list):
        raise ValueError("contexts.yaml: `outbound` must be a list")
    out: List[OutboundContext] = []
    seen: Set[str] = set()
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ValueError(f"contexts.yaml: outbound #{i} must be a mapping")
        unknown = set(entry) - _KEYS
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
        local = bool(entry.get("local"))
        contract = str(entry.get("contract") or "").strip()
        if local and contract:
            raise ValueError(f"contexts.yaml: outbound {ctx_id!r}: set `local: true` OR `contract`, not both")
        if not local and not contract:
            raise ValueError(f"contexts.yaml: outbound {ctx_id!r}: requires `local: true` or `contract`")
        routes = str(entry.get("routes") or "crud").strip().lower()
        if routes not in _ROUTE_MODES:
            raise ValueError(
                f"contexts.yaml: outbound {ctx_id!r}: `routes` must be one of {sorted(_ROUTE_MODES)}"
            )
        base_url = str(entry.get("base_url") or "").strip()
        out.append(
            OutboundContext(
                id=ctx_id,
                local=local,
                contract=contract,
                base_url=base_url,
                routes=routes,
            )
        )
    return tuple(out)


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


def filter_spec_for_client(
    spec: Dict[str, Any],
    schema_text: str,
    *,
    routes: str = "crud",
) -> Dict[str, Any]:
    """Subset a producer spec to client-emittable JSON routes (FR-3 / OQ-3)."""
    from ..languages.prisma_parser import parse_prisma_schema

    schema = parse_prisma_schema(schema_text)
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
        for entity in _model_names(schema, schema_text):
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
