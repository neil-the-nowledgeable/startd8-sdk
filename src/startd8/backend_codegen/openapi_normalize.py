"""Brownfield OpenAPI → ``api.yaml`` overlay subset (OpenAPI Role 2 FR-D1 / M4).

Human-reviewed ingest helper: load an external OpenAPI document, strip framework noise,
optionally subtract the Prisma-derived Role 1 base projection, and emit a minimal overlay
YAML suitable for ``startd8 generate backend --api``.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from ..schema_contract.prisma_json_schema import model_names
from ..languages.prisma_parser import parse_prisma_schema
from .api_overlay_manifest import normalize_overlay_path
from .openapi_contract_renderer import _project_openapi

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})
_DTO_SUFFIXES = ("Create", "Read", "Update")
_VALIDATION_ONLY_KEY = "x-startd8-validation-only"
_KEEP_OPERATION_KEYS = frozenset(
    {"summary", "description", "parameters", "requestBody", "responses"}
)


@dataclass
class NormalizeResult:
    """Outcome of :func:`normalize_openapi_to_overlay`."""

    overlay: Dict[str, Any]
    warnings: List[str] = field(default_factory=list)
    stripped_paths: List[str] = field(default_factory=list)
    kept_paths: List[str] = field(default_factory=list)
    stripped_schemas: List[str] = field(default_factory=list)


def load_openapi_document(path: Path) -> Dict[str, Any]:
    """Load an OpenAPI 3.0 JSON or YAML document from *path*."""
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        data = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: OpenAPI document must be a mapping")
    openapi = data.get("openapi", "")
    if not isinstance(openapi, str) or not openapi.startswith("3.0"):
        raise ValueError(f"{path}: only OpenAPI 3.0.x is supported (got {openapi!r})")
    return data


def _prisma_dto_names(schema_text: str) -> Set[str]:
    names: Set[str] = set()
    for entity in model_names(parse_prisma_schema(schema_text), schema_text):
        names.update(f"{entity}{suffix}" for suffix in _DTO_SUFFIXES)
    return names


def _collect_schema_refs(node: Any, out: Set[str]) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            out.add(ref.rsplit("/", 1)[-1])
        for value in node.values():
            _collect_schema_refs(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_schema_refs(item, out)


def _strip_operation(operation: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key, value in operation.items():
        if key in _KEEP_OPERATION_KEYS:
            cleaned[key] = copy.deepcopy(value)
    return cleaned


def _strip_path_item(path_item: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    if path_item.get(_VALIDATION_ONLY_KEY) is True:
        cleaned[_VALIDATION_ONLY_KEY] = True
    for key, value in path_item.items():
        if key.startswith("x-") and key != _VALIDATION_ONLY_KEY:
            continue
        if key in _HTTP_METHODS and isinstance(value, dict):
            cleaned[key] = _strip_operation(value)
        elif key == "parameters" and isinstance(value, list):
            cleaned[key] = copy.deepcopy(value)
    return cleaned


def _normalize_paths(
    paths: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str]]:
    """Rewrite path keys via :func:`normalize_overlay_path`; warn on slash duplicates."""
    warnings: List[str] = []
    normalized: Dict[str, Any] = {}
    seen_canonical: Dict[str, str] = {}

    for raw_path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        norm_path = normalize_overlay_path(raw_path)
        if norm_path in seen_canonical and seen_canonical[norm_path] != raw_path:
            warnings.append(
                f"trailing-slash duplicate: {raw_path!r} and {seen_canonical[norm_path]!r} "
                f"both normalize to {norm_path!r}"
            )
        seen_canonical.setdefault(norm_path, raw_path)
        if norm_path in normalized and raw_path != norm_path:
            warnings.append(
                f"trailing-slash duplicate: {raw_path!r} collides with existing {norm_path!r}"
            )
            continue
        normalized[norm_path] = _strip_path_item(path_item)
    return normalized, warnings


def _base_spec_from_schema(schema_text: str) -> Dict[str, Any]:
    _, spec = _project_openapi(schema_text)
    return spec


def _subtract_base(
    spec: Dict[str, Any],
    base_spec: Dict[str, Any],
    schema_text: str,
) -> Tuple[Dict[str, Any], List[str], List[str], List[str]]:
    """Remove base-owned paths and Prisma-derived schemas from *spec*."""
    stripped_paths: List[str] = []
    stripped_schemas: List[str] = []
    warnings: List[str] = []

    base_paths = set(base_spec.get("paths", {}).keys())
    base_schemas = set(base_spec.get("components", {}).get("schemas", {}).keys())
    prisma_dtos = _prisma_dto_names(schema_text)

    kept_paths: Dict[str, Any] = {}
    for path, path_item in spec.get("paths", {}).items():
        if path in base_paths:
            stripped_paths.append(path)
            continue
        if normalize_overlay_path(path) in base_paths and path not in base_paths:
            warnings.append(
                f"path {path!r} normalizes to a base CRUD path — stripped as duplicate"
            )
            stripped_paths.append(path)
            continue
        kept_paths[path] = path_item

    all_schemas = spec.get("components", {}).get("schemas", {})
    if not isinstance(all_schemas, dict):
        all_schemas = {}

    needed: Set[str] = set()
    _collect_schema_refs({"paths": kept_paths}, needed)

    kept_schemas: Dict[str, Any] = {}
    for name, schema in all_schemas.items():
        if name in base_schemas or name in prisma_dtos:
            if name in needed:
                warnings.append(
                    f"schema {name!r} is Prisma/base-owned — omit from overlay "
                    "(use $ref to {{Entity}}{{Create,Read,Update}})"
                )
            stripped_schemas.append(name)
            continue
        if name in needed:
            kept_schemas[name] = schema
        else:
            stripped_schemas.append(name)

    for missing in sorted(needed - set(kept_schemas.keys()) - base_schemas - prisma_dtos):
        warnings.append(f"overlay references unknown schema {missing!r}")

    out = copy.deepcopy(spec)
    out["paths"] = kept_paths
    out.setdefault("components", {})["schemas"] = kept_schemas
    return out, stripped_paths, stripped_schemas, warnings


def _overlay_document(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Shape a minimal ``api.yaml`` overlay dict."""
    paths = spec.get("paths", {})
    schemas = spec.get("components", {}).get("schemas", {})
    overlay: Dict[str, Any] = {
        "openapi": spec.get("openapi", "3.0.3"),
        "info": {"title": "API overlay", "version": "0.0.0"},
        "paths": paths if isinstance(paths, dict) else {},
    }
    if isinstance(schemas, dict) and schemas:
        overlay["components"] = {"schemas": schemas}
    return overlay


def normalize_openapi_to_overlay(
    spec: Dict[str, Any],
    *,
    schema_text: Optional[str] = None,
) -> NormalizeResult:
    """Transform an external OpenAPI spec into a human-reviewed overlay subset."""
    working = copy.deepcopy(spec)
    warnings: List[str] = []

    for drop_key in ("servers", "security", "externalDocs", "webhooks", "tags"):
        working.pop(drop_key, None)

    raw_paths = working.get("paths", {})
    if not isinstance(raw_paths, dict):
        raw_paths = {}
    normalized_paths, path_warnings = _normalize_paths(raw_paths)
    warnings.extend(path_warnings)
    working["paths"] = normalized_paths

    stripped_paths: List[str] = []
    stripped_schemas: List[str] = []
    if schema_text is not None:
        base = _base_spec_from_schema(schema_text)
        working, stripped_paths, stripped_schemas, base_warnings = _subtract_base(
            working, base, schema_text
        )
        warnings.extend(base_warnings)

    overlay = _overlay_document(working)
    kept_paths = sorted(overlay.get("paths", {}).keys())
    return NormalizeResult(
        overlay=overlay,
        warnings=warnings,
        stripped_paths=sorted(stripped_paths),
        kept_paths=kept_paths,
        stripped_schemas=sorted(stripped_schemas),
    )


def render_overlay_yaml(overlay: Dict[str, Any]) -> str:
    """Serialize an overlay dict to stable YAML."""
    return yaml.safe_dump(
        overlay,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
