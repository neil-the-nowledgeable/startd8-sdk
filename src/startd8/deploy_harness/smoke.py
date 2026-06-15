"""Smoke-CRUD: synthesize a POST body from the live OpenAPI and round-trip it (FR-9/10).

The riskiest correctness surface in the harness (CRP R1-F4), so the schema work is split into pure,
unit-testable functions — :func:`select_crud_resource` and :func:`synthesize_body` — from the live
HTTP round-trip in :func:`run_smoke`. Synthesis honors an enumerated JSON-Schema feature set: ``$ref``
resolution, ``allOf`` merge, ``required`` vs ``nullable``, ``enum`` (first), ``format``, nested
objects, and ``oneOf``/``anyOf`` (first non-null branch). A feature it cannot satisfy yields a typed
``skipped`` reason, never a malformed body scored ``fail``.

Grading is best-effort and never fatal (CRP R1-F5) — the three non-pass outcomes are distinct so the
FK-free preference's bias is visible, not hidden as neutral:
- ``skipped:no-list-create-resource`` — the app exposes no JSON list+create collection.
- ``skipped:all-resources-fk-coupled`` — every such resource needs a required FK (harness limitation).
- ``fail`` — a derived case that errored against the live server.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from startd8.logging_config import get_logger

logger = get_logger("startd8.deploy_harness.smoke")

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


@dataclass
class SmokeOutcome:
    status: str  # pass | fail | skipped
    reason: Optional[str] = None
    resource: Optional[str] = None
    post_status: Optional[int] = None
    get_status: Optional[int] = None


# --------------------------------------------------------------------------- schema resolution


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


# --------------------------------------------------------------------------- body synthesis


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


# --------------------------------------------------------------------------- resource selection


def _is_fk_field(name: str, prop: Dict[str, Any], spec: Dict[str, Any]) -> bool:
    """A required field that is a foreign-key/relation — a row that must already exist."""
    if name == "id":
        return False
    if name.endswith("_id") or (name.endswith("Id") and name != "id"):
        return True
    r = resolve_schema(prop, spec)
    # a required nested object / relation ref also implies an existing dependency
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
            continue  # collection paths only (no path params)
        if "post" not in item or "get" not in item:
            continue  # presence, not truthiness — an op object may be present but minimal
        schema = _json_request_schema(item["post"])
        if schema is None:
            continue  # e.g. an HTMX form route (not application/json)
        candidates.append(ResourceChoice(path=path, create_schema=schema))

    if not candidates:
        return None, "skipped:no-list-create-resource"

    fk_free = [c for c in candidates if not _has_required_fk(c.create_schema, spec)]
    if not fk_free:
        return None, "skipped:all-resources-fk-coupled"

    # simplest = fewest required fields (then shortest path, for determinism)
    def _required_count(c: ResourceChoice) -> int:
        return len(resolve_schema(c.create_schema, spec).get("required", []))

    fk_free.sort(key=lambda c: (_required_count(c), len(c.path), c.path))
    return fk_free[0], None


# --------------------------------------------------------------------------- live round-trip


def _http(
    method: str, url: str, *, body: Any = None, timeout: float = 10.0
) -> Tuple[Optional[int], Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method
    )  # noqa: S310 - loopback only
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, _maybe_json(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, _maybe_json(exc.read())
    except (urllib.error.URLError, OSError) as exc:
        return None, str(exc)


def _maybe_json(raw: Any) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


def run_smoke(
    base_url: str, *, spec: Optional[Dict[str, Any]] = None, timeout: float = 10.0
) -> SmokeOutcome:
    """Derive and execute a create→list round-trip against the live server. Never raises."""
    if spec is None:
        status, spec = _http(
            "GET", base_url.rstrip("/") + "/openapi.json", timeout=timeout
        )
        if status is None or not isinstance(spec, dict):
            return SmokeOutcome(status="skipped", reason="skipped:no-openapi")

    choice, skip = select_crud_resource(spec)
    if choice is None:
        return SmokeOutcome(status="skipped", reason=skip)

    try:
        body = synthesize_body(choice.create_schema, spec)
    except Exception as exc:  # synthesis is best-effort
        logger.debug("body synthesis failed for %s: %s", choice.path, exc)
        return SmokeOutcome(
            status="skipped", reason="skipped:body-synth-failed", resource=choice.path
        )

    url = base_url.rstrip("/") + choice.path
    post_status, post_body = _http("POST", url, body=body, timeout=timeout)
    if post_status is None:
        return SmokeOutcome(
            status="fail", reason="post-no-response", resource=choice.path
        )
    if not (200 <= post_status < 300):
        return SmokeOutcome(
            status="fail",
            reason=f"post-{post_status}",
            resource=choice.path,
            post_status=post_status,
        )

    get_status, get_body = _http("GET", url, timeout=timeout)
    if get_status is None or not (200 <= get_status < 300):
        return SmokeOutcome(
            status="fail",
            reason=f"get-{get_status}",
            resource=choice.path,
            post_status=post_status,
            get_status=get_status,
        )

    if not _round_trip_ok(post_body, get_body):
        return SmokeOutcome(
            status="fail",
            reason="no-round-trip",
            resource=choice.path,
            post_status=post_status,
            get_status=get_status,
        )
    return SmokeOutcome(
        status="pass",
        resource=choice.path,
        post_status=post_status,
        get_status=get_status,
    )


def _round_trip_ok(post_body: Any, get_body: Any) -> bool:
    """The created row should be observable in the subsequent list."""
    items = (
        get_body
        if isinstance(get_body, list)
        else (get_body.get("items") if isinstance(get_body, dict) else None)
    )
    if items is None:
        return False
    if not items:
        return False  # we just created one — an empty list is a failed round-trip
    created_id = post_body.get("id") if isinstance(post_body, dict) else None
    if created_id is None:
        return True  # no id concept — a non-empty list after create is sufficient
    return any(isinstance(it, dict) and it.get("id") == created_id for it in items)
