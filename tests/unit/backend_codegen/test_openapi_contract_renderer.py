"""Unit tests for the deterministic OpenAPI contract renderer (python-openapi-contract)."""

from __future__ import annotations

import ast
import json

import pytest

from startd8.backend_codegen import (
    is_owned_generated_file,
    owned_file_in_sync,
    render_backend,
)
from startd8.backend_codegen.openapi_contract_renderer import (
    _crud_routes,
    render_openapi_contract,
)
from startd8.backend_codegen.test_emitter import render_openapi_contract_tests
from startd8.languages.prisma_parser import parse_prisma_schema
from startd8.validators.boot_smoke import expected_routes_from_contract

pytestmark = pytest.mark.unit

SCHEMA = """\
model Note {
  id    String @id @default(cuid())
  title String
}

model Link {
  noteId String
  url    String
}
"""


def test_header_carries_kind_and_sha() -> None:
    text = render_openapi_contract(SCHEMA)
    assert "# startd8-artifact: python-openapi-contract" in text
    assert "# schema-sha256: " in text


def test_byte_identical_per_schema() -> None:
    assert render_openapi_contract(SCHEMA) == render_openapi_contract(SCHEMA)


def test_skip_hook_in_sync_from_schema_only() -> None:
    text = render_openapi_contract(SCHEMA)
    assert owned_file_in_sync(SCHEMA, text) is True
    assert is_owned_generated_file(text) is True


def test_crud_paths_match_router_conventions() -> None:
    schema = parse_prisma_schema(SCHEMA)
    routes = set(_crud_routes(schema, SCHEMA))
    assert ("GET", "/note/") in routes
    assert ("POST", "/note/") in routes
    assert ("GET", "/note/{item_id}") in routes
    # keyless Link (no @id / single @unique): list + create only
    assert ("GET", "/link/") in routes
    assert ("POST", "/link/") in routes
    assert ("GET", "/link/{item_id}") not in routes


def test_openapi_spec_loads_from_emitted_module() -> None:
    text = render_openapi_contract(SCHEMA)
    mod = ast.parse(text)
    spec = None
    for node in mod.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "OPENAPI_SPEC":
                    spec = ast.literal_eval(node.value)
    assert spec is None  # uses json.loads call, not literal
    assert "OPENAPI_SPEC" in text
    assert "json.loads" in text
    # Execute only the spec literal portion
    ns: dict = {}
    exec(  # noqa: S102 - generated contract under test
        text.split("def route_paths", 1)[0],
        ns,
    )
    loaded = ns["OPENAPI_SPEC"]
    assert loaded["openapi"] == "3.0.3"
    assert "/note/" in loaded["paths"]
    assert "NoteCreate" in loaded["components"]["schemas"]


def test_assembler_emits_contract_and_tests() -> None:
    paths = {p for p, _ in render_backend(SCHEMA)}
    assert "app/openapi_contract.py" in paths
    assert "tests/test_openapi_contract.py" in paths


def test_expected_routes_extractor(tmp_path) -> None:
    text = render_openapi_contract(SCHEMA)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "openapi_contract.py").write_text(text, encoding="utf-8")
    routes = expected_routes_from_contract(str(tmp_path))
    assert routes is not None
    assert "/note/" in routes
    assert "/health" in routes
    assert "/health/live" in routes


def test_contract_tests_render_and_compile() -> None:
    text = render_openapi_contract_tests(SCHEMA)
    assert "# startd8-artifact: python-tests-openapi-contract" in text
    compile(text, "tests/test_openapi_contract.py", "exec")


def test_openapi_spec_supports_smoke_resource_selection() -> None:
    """FR-10: static OPENAPI_SPEC is compatible with deploy_harness smoke selection."""
    from startd8.deploy_harness.smoke import select_crud_resource

    ns: dict = {}
    exec(  # noqa: S102
        render_openapi_contract(SCHEMA).split("def route_paths", 1)[0],
        ns,
    )
    choice, reason = select_crud_resource(ns["OPENAPI_SPEC"])
    assert choice is not None, reason
    assert choice.path in {"/note/", "/link/"}
