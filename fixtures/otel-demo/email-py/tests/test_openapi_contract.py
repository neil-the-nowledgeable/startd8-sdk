# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-tests-openapi-contract
# Source of truth: the Prisma schema.
# schema-sha256: 0b898e5f7f7f45151610a0e3830b0b5c32150ec8cc732b449b0d0ea40e8ce102

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

_testclient = pytest.importorskip("fastapi.testclient")
pytest.importorskip("sqlmodel")
pytest.importorskip("httpx")

from app.main import app  # noqa: E402
from app.openapi_contract import OPENAPI_SPEC, ROUTE_MANIFEST  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

# Baked schema-derived CRUD subset (health is checked separately below).
_SCHEMA_CRUD: tuple[tuple[str, str], ...] = (
    ("DELETE", "/orderconfirmation/{item_id}"),
    ("GET", "/orderconfirmation/"),
    ("GET", "/orderconfirmation/{item_id}"),
    ("PATCH", "/orderconfirmation/{item_id}"),
    ("POST", "/orderconfirmation/"),
)


def _mounted() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for r in app.routes:
        if isinstance(r, APIRoute):
            for m in r.methods or ():
                if m in {"GET", "POST", "PATCH", "DELETE", "PUT"}:
                    out.add((m, r.path))
    return out


def test_openapi_spec_paths_match_manifest():
    assert set(OPENAPI_SPEC.get("paths", {}).keys()) == {p for _, p in ROUTE_MANIFEST}


def test_openapi_internal_refs_resolve():
    """FR-7: merged spec internal $refs resolve (no dangling pointers)."""
    from startd8.openapi_contract.schema_resolve import resolve_schema

    def _walk(obj):
        if isinstance(obj, dict):
            if "$ref" in obj:
                yield obj["$ref"]
            for v in obj.values():
                yield from _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                yield from _walk(item)

    dangling = []
    for ref in _walk(OPENAPI_SPEC):
        if not ref.startswith("#/"):
            dangling.append(ref)
            continue
        resolved = resolve_schema({"$ref": ref}, OPENAPI_SPEC)
        if not resolved:
            dangling.append(ref)
    assert not dangling, "unresolved $refs: " + repr(dangling)


def test_schema_crud_routes_in_manifest():
    missing = [pair for pair in _SCHEMA_CRUD if pair not in ROUTE_MANIFEST]
    assert not missing, "manifest missing schema-derived CRUD routes: " + repr(missing)


def test_manifest_routes_are_mounted():
    mounted = _mounted()
    missing = [pair for pair in ROUTE_MANIFEST if pair not in mounted]
    assert not missing, "mounted app missing manifest routes: " + repr(missing)


def test_health_routes_in_manifest():
    for pair in (("GET", "/health"), ("GET", "/health/live")):
        assert pair in ROUTE_MANIFEST
