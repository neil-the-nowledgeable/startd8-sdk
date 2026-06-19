"""Shared OpenAPI JSON-Schema resolution + smoke-body synthesis (OpenAPI Role 1 — M4).

Extracted from ``deploy_harness.smoke`` so the deploy harness, static contract tests, and
codegen tooling share one implementation of ``$ref``/``allOf`` resolution, body synthesis, and
FK-free list+create resource selection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

_MAX_REF_DEPTH = 16
_STRING_FORMATS = {
    "date-time": "2024-01-01T00:00:00Z",
    "date": "2024-01-01",
    "time": "00:00:00",
    "uuid": "00000000-0000-0000-0000-000000000000",
    "email": "smoke@example.com",
    "uri": "https://example.com",
    "hostname": "example.com",
    "ipv4": "127.0.0.1",
    "byte": "c2FtcGxl",  # base64("sample")
}


def _deref(ref: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve a local ``#/components/schemas/X`` pointer against the spec."""
    if not ref.startswith("#/"):
        return {}
    node: Any = spec
    for part in ref[2:].split("/"):
        if not isinstance(node, dict):
            return {}
        node = node.get(part, {})
    return node if isinstance(node, dict) else {}


def resolve_schema(
    schema: Dict[str, Any], spec: Dict[str, Any], *, depth: int = 0
) -> Dict[str, Any]:
    """Resolve ``$ref`` and flatten ``allOf`` into a single object-ish schema (properties+required)."""
    if depth > _MAX_REF_DEPTH or not isinstance(schema, dict):
        return schema if isinstance(schema, dict) else {}
    if "$ref" in schema:
        return resolve_schema(_deref(schema["$ref"], spec), spec, depth=depth + 1)
    if "allOf" in schema:
        merged: Dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        for sub in schema["allOf"]:
            r = resolve_schema(sub, spec, depth=depth + 1)
            merged["properties"].update(r.get("properties", {}))
            merged["required"].extend(r.get("required", []))
        merged["properties"].update(schema.get("properties", {}))
        merged["required"].extend(schema.get("required", []))
        merged["required"] = list(dict.fromkeys(merged["required"]))
        return merged
    return schema


def _is_nullable(schema: Dict[str, Any]) -> bool:
    if schema.get("nullable") is True:  # OpenAPI 3.0
        return True
    t = schema.get("type")
    return isinstance(t, list) and "null" in t  # OpenAPI 3.1 union


def _primary_type(schema: Dict[str, Any]) -> Optional[str]:
    t = schema.get("type")
    if isinstance(t, list):
        non_null = [x for x in t if x != "null"]
        return non_null[0] if non_null else "null"
    return t


def synthesize_body(schema: Dict[str, Any], spec: Dict[str, Any]) -> Any:
    """Synthesize a minimal valid value for ``schema`` (only required object fields are filled)."""
    return _synth(schema, spec, depth=0)


def _synth(schema: Dict[str, Any], spec: Dict[str, Any], *, depth: int) -> Any:
    s = resolve_schema(schema, spec, depth=depth)
    if depth > _MAX_REF_DEPTH:
        return None
    if "default" in s:
        return s["default"]
    if s.get("enum"):
        return s["enum"][0]
    if "oneOf" in s:
        return _synth(s["oneOf"][0], spec, depth=depth + 1)
    if "anyOf" in s:
        branches = [
            b for b in s["anyOf"] if _primary_type(resolve_schema(b, spec)) != "null"
        ]
        return _synth((branches or s["anyOf"])[0], spec, depth=depth + 1)

    t = _primary_type(s)
    if t == "object" or "properties" in s:
        out: Dict[str, Any] = {}
        for name in dict.fromkeys(s.get("required", [])):
            prop = s.get("properties", {}).get(name, {})
            rprop = resolve_schema(prop, spec, depth=depth + 1)
            out[name] = (
                None if _is_nullable(rprop) else _synth(rprop, spec, depth=depth + 1)
            )
        return out
    if t == "array":
        return []
    if t == "string":
        return _STRING_FORMATS.get(s.get("format"), "sample")
    if t == "integer":
        return 1
    if t == "number":
        return 1.0
    if t == "boolean":
        return False
    if t == "null":
        return None
    return "sample"


def _is_fk_field(name: str, prop: Dict[str, Any], spec: Dict[str, Any]) -> bool:
    """A required field that is a foreign-key/relation — a row that must already exist."""
    if name == "id":
        return False
    if name.endswith("_id") or (name.endswith("Id") and name != "id"):
        return True
    r = resolve_schema(prop, spec)
    return _primary_type(r) == "object" or "$ref" in prop


def _has_required_fk(schema: Dict[str, Any], spec: Dict[str, Any]) -> bool:
    s = resolve_schema(schema, spec)
    props = s.get("properties", {})
    return any(
        _is_fk_field(name, props.get(name, {}), spec) for name in s.get("required", [])
    )


def _json_request_schema(operation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    content = ((operation or {}).get("requestBody") or {}).get("content") or {}
    media = content.get("application/json")
    if not media:
        return None
    return media.get("schema")


@dataclass
class ResourceChoice:
    path: str
    create_schema: Dict[str, Any]


def select_crud_resource(
    spec: Dict[str, Any],
) -> Tuple[Optional[ResourceChoice], Optional[str]]:
    """Pick the simplest FK-free JSON list+create collection, or a typed skip reason.

    Returns ``(choice, None)`` or ``(None, skip_reason)``.
    """
    candidates: List[ResourceChoice] = []
    for path, item in (spec.get("paths") or {}).items():
        if "{" in path or not isinstance(item, dict):
            continue
        if "post" not in item or "get" not in item:
            continue
        schema = _json_request_schema(item["post"])
        if schema is None:
            continue
        candidates.append(ResourceChoice(path=path, create_schema=schema))

    if not candidates:
        return None, "skipped:no-list-create-resource"

    fk_free = [c for c in candidates if not _has_required_fk(c.create_schema, spec)]
    if not fk_free:
        return None, "skipped:all-resources-fk-coupled"

    def _required_count(c: ResourceChoice) -> int:
        return len(resolve_schema(c.create_schema, spec).get("required", []))

    fk_free.sort(key=lambda c: (_required_count(c), len(c.path), c.path))
    return fk_free[0], None
