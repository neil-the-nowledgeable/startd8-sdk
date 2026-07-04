"""``api.yaml`` overlay — parse, reconcile, and merge into Role 1 static OpenAPI (Role 2 M0+M1).

The Prisma+health projection from :mod:`openapi_contract_renderer` is the immutable base; the
overlay **adds** paths and ``components.schemas`` only. Handler bodies remain project-owned
(``user_routers.py`` / bucket 3).
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Tuple

import yaml

from ..schema_contract.prisma_json_schema import model_names
from ..languages.prisma_parser import PrismaSchema, parse_prisma_schema

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options"})
_DTO_SUFFIXES = ("Create", "Read", "Update")
_PATH_PARAM_RE = re.compile(r"\{([^}]+)\}")
_VALIDATION_ONLY_KEY = "x-startd8-validation-only"
_SINGLE_SEGMENT_RE = re.compile(r"^/[a-z][a-z0-9_-]*$")


class ReconcileError(ValueError):
    """Raised when an overlay conflicts with the Prisma-derived base contract."""


@dataclass
class OverlayMergePlan:
    """Partition of an overlay into paths/schemas to merge vs validation-only declarations."""

    additive: Dict[str, Any]
    warnings: List[str] = field(default_factory=list)


def normalize_overlay_path(path: str) -> str:
    """Normalize overlay path keys toward CRUD trailing-slash convention (OQ-7).

    Single-segment collection paths (``/note``) gain a trailing slash (``/note/``).
    Multi-segment paths and paths with template parameters are unchanged.
    """
    if _SINGLE_SEGMENT_RE.match(path):
        return path + "/"
    return path


def normalize_overlay_paths(
    paths: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str]]:
    """Rewrite overlay path keys; raise on trailing-slash duplicates (OQ-7)."""
    warnings: List[str] = []
    normalized: Dict[str, Any] = {}
    canonical_sources: Dict[str, str] = {}

    for raw_path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        norm_path = normalize_overlay_path(raw_path)
        prior = canonical_sources.get(norm_path)
        if prior is not None and prior != raw_path:
            raise ReconcileError(
                f"trailing-slash duplicate: {raw_path!r} and {prior!r} "
                f"both normalize to {norm_path!r}"
            )
        canonical_sources.setdefault(norm_path, raw_path)
        if norm_path in normalized and raw_path != norm_path:
            raise ReconcileError(
                f"trailing-slash duplicate: {raw_path!r} collides with {norm_path!r}"
            )
        normalized[norm_path] = path_item
    return normalized, warnings


def parse_api_overlay(text: str) -> Dict[str, Any]:
    """Load and normalize a minimal OpenAPI 3.0 YAML overlay."""
    data = yaml.safe_load(text)
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ValueError("api overlay must be a YAML mapping")
    if "openapi" not in data:
        data["openapi"] = "3.0.3"
    if "info" not in data:
        data["info"] = {"title": "API overlay", "version": "0.0.0"}
    if "paths" not in data:
        data["paths"] = {}
    if not isinstance(data["paths"], dict):
        raise ValueError("api overlay paths must be a mapping")
    components = data.setdefault("components", {})
    if not isinstance(components, dict):
        raise ValueError("api overlay components must be a mapping")
    schemas = components.setdefault("schemas", {})
    if not isinstance(schemas, dict):
        raise ValueError("api overlay components.schemas must be a mapping")
    data["paths"], _ = normalize_overlay_paths(data["paths"])
    return data


def routes_from_openapi_spec(spec: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Derive sorted ``(METHOD, path)`` pairs from an OpenAPI ``paths`` object."""
    routes: List[Tuple[str, str]] = []
    for path, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method in sorted(path_item.keys()):
            if method in _HTTP_METHODS and isinstance(path_item[method], dict):
                routes.append((method.upper(), path))
    return sorted(routes)


def merge_openapi_specs(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Return *base* deep-copied with overlay paths/schemas added (additive only)."""
    merged = copy.deepcopy(base)
    base_paths = merged.setdefault("paths", {})
    for path, item in overlay.get("paths", {}).items():
        if path in base_paths:
            raise ReconcileError(f"path collision: {path}")
        base_paths[path] = copy.deepcopy(item)
    merged_schemas = (
        merged.setdefault("components", {}).setdefault("schemas", {})
    )
    overlay_schemas = overlay.get("components", {}).get("schemas", {})
    for name, schema in overlay_schemas.items():
        if name in merged_schemas:
            raise ReconcileError(f"schema collision: {name}")
        merged_schemas[name] = copy.deepcopy(schema)
    return merged


def _is_validation_only_path(path_item: Dict[str, Any]) -> bool:
    return path_item.get(_VALIDATION_ONLY_KEY) is True


def _warnings_for_base_path_validation(
    path: str,
    overlay_item: Dict[str, Any],
    base_item: Dict[str, Any],
) -> List[str]:
    """Compare overlay declaration against an existing base path (FR-O1 / M2)."""
    warnings: List[str] = []
    for method, operation in overlay_item.items():
        if method.startswith("x-") or method not in _HTTP_METHODS:
            continue
        if not isinstance(operation, dict):
            continue
        if method not in base_item:
            warnings.append(
                f"validation-only: {method.upper()} {path} declared in api.yaml "
                "but not in contract base"
            )
    return warnings


def prepare_overlay_merge(
    base_spec: Dict[str, Any],
    overlay: Dict[str, Any],
) -> OverlayMergePlan:
    """Split overlay into additive merge material vs validation-only declarations (M2 / FR-O1)."""
    warnings: List[str] = []
    base_paths = base_spec.get("paths", {})
    base_schemas = base_spec.get("components", {}).get("schemas", {})
    additive_paths: Dict[str, Any] = {}

    for path, path_item in overlay.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        if path in base_paths:
            warnings.extend(
                _warnings_for_base_path_validation(path, path_item, base_paths[path])
            )
            continue
        if _is_validation_only_path(path_item):
            warnings.append(
                f"validation-only: path {path!r} is not in the contract base yet "
                "(manifest projection or inputs such as --ai-passes may be required)"
            )
            continue
        additive_paths[path] = copy.deepcopy(path_item)

    additive_schemas: Dict[str, Any] = {}
    for name, schema in overlay.get("components", {}).get("schemas", {}).items():
        if name in base_schemas:
            raise ReconcileError(f"schema collision: {name}")
        additive_schemas[name] = copy.deepcopy(schema)

    additive: Dict[str, Any] = {
        "openapi": overlay.get("openapi", "3.0.3"),
        "paths": additive_paths,
        "components": {"schemas": additive_schemas},
    }
    return OverlayMergePlan(additive=additive, warnings=warnings)


def _model_names(schema: PrismaSchema, schema_text: str) -> List[str]:
    return model_names(schema, schema_text)


def _collect_refs(node: Any, out: Set[str]) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            out.add(ref)
        for value in node.values():
            _collect_refs(value, out)
    elif isinstance(node, list):
        for item in node:
            _collect_refs(item, out)


def _path_template_params(path: str) -> Set[str]:
    return set(_PATH_PARAM_RE.findall(path))


def _declared_path_params(path_item: Dict[str, Any], operation: Dict[str, Any]) -> Set[str]:
    names: Set[str] = set()
    for params in (
        path_item.get("parameters") or [],
        operation.get("parameters") or [],
    ):
        if not isinstance(params, list):
            continue
        for param in params:
            if isinstance(param, dict) and param.get("in") == "path":
                name = param.get("name")
                if isinstance(name, str):
                    names.add(name)
    return names


def _validate_path_parameters(overlay: Dict[str, Any]) -> None:
    for path, path_item in overlay.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        needed = _path_template_params(path)
        if not needed:
            continue
        for method, operation in path_item.items():
            if method not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            declared = _declared_path_params(path_item, operation)
            missing = needed - declared
            if missing:
                raise ReconcileError(
                    f"path {path!r} {method.upper()} missing parameters: {sorted(missing)}"
                )


def _validate_overlay_refs(
    overlay: Dict[str, Any],
    base_schemas: Dict[str, Any],
    model_names: List[str],
) -> None:
    overlay_schemas = overlay.get("components", {}).get("schemas", {})
    refs: Set[str] = set()
    _collect_refs(overlay, refs)
    for ref in refs:
        if not ref.startswith("#/components/schemas/"):
            continue
        name = ref.rsplit("/", 1)[-1]
        if name in base_schemas or name in overlay_schemas:
            continue
        for suffix in _DTO_SUFFIXES:
            if name.endswith(suffix):
                entity = name[: -len(suffix)]
                if entity in model_names:
                    break
        else:
            raise ReconcileError(f"unresolved $ref in overlay: {ref}")


def reconcile_overlay(
    base_spec: Dict[str, Any],
    overlay: Dict[str, Any],
    schema_text: str,
) -> List[str]:
    """Validate additive overlay slice; return validation-only warnings (M2 / FR-O1)."""
    schema = parse_prisma_schema(schema_text)
    names = _model_names(schema, schema_text)
    plan = prepare_overlay_merge(base_spec, overlay)
    base_schemas = base_spec.get("components", {}).get("schemas", {})
    _validate_overlay_refs(plan.additive, base_schemas, names)
    _validate_path_parameters(plan.additive)
    return plan.warnings


def apply_api_overlay(
    base_spec: Dict[str, Any],
    overlay: Dict[str, Any],
    schema_text: str,
) -> Tuple[Dict[str, Any], List[str]]:
    """Validate, partition, and merge an overlay; return merged spec + validation warnings."""
    warnings = reconcile_overlay(base_spec, overlay, schema_text)
    plan = prepare_overlay_merge(base_spec, overlay)
    merged = merge_openapi_specs(base_spec, plan.additive)
    return merged, warnings
