"""Unit tests — inter-context consumer client emission + drift (Role 3 M1)."""

from __future__ import annotations

import ast
import json

import pytest

from startd8.backend_codegen import owned_file_in_sync, render_backend
from startd8.backend_codegen.context_client_renderer import (
    client_method_paths,
    render_context_client,
)
from startd8.backend_codegen.openapi_contract_renderer import render_openapi_contract
from startd8.validators.openapi_spec_gate import extract_openapi_spec_from_text

pytestmark = pytest.mark.unit

SCHEMA = """\
model Note {
  id    String @id @default(cuid())
  title String
}
"""

CONTEXTS = """\
outbound:
  - id: catalog
    local: true
    base_url: http://127.0.0.1:8001
    routes: crud
"""

OVERLAY = """\
paths:
  /webhooks/stripe:
    post:
      responses:
        '200':
          description: OK
"""


def _route_manifest_pairs(contract_text: str) -> set[tuple[str, str]]:
    tree = ast.parse(contract_text)
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "ROUTE_MANIFEST" and isinstance(node.value, ast.Tuple):
                return set(ast.literal_eval(node.value))
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "ROUTE_MANIFEST":
                    return set(ast.literal_eval(node.value))
    raise AssertionError("ROUTE_MANIFEST not found")


def test_render_context_client_local_crud_methods() -> None:
    from startd8.backend_codegen.context_manifest import parse_contexts

    (ctx,) = parse_contexts(CONTEXTS)
    text = render_context_client(SCHEMA, CONTEXTS, ctx)
    assert "startd8-artifact: python-context-client" in text
    assert "startd8-entity: catalog" in text
    assert "contract-sha256:" in text
    assert "class CatalogClient:" in text
    assert "``GET /note/``" in text
    paths = client_method_paths(text)
    assert ("GET", "/note/") in paths


def test_context_client_method_paths_subset_of_manifest() -> None:
    from startd8.backend_codegen.context_manifest import parse_contexts

    contract = render_openapi_contract(SCHEMA, api_text=OVERLAY)
    manifest = _route_manifest_pairs(contract)
    (ctx,) = parse_contexts(CONTEXTS)
    client = render_context_client(SCHEMA, CONTEXTS, ctx, api_text=OVERLAY)
    for method, path in client_method_paths(client):
        assert (method, path) in manifest


def test_owned_file_in_sync_context_client() -> None:
    from startd8.backend_codegen.context_manifest import parse_contexts

    (ctx,) = parse_contexts(CONTEXTS)
    text = render_context_client(SCHEMA, CONTEXTS, ctx)
    assert owned_file_in_sync(
        SCHEMA,
        text,
        contexts_text=CONTEXTS,
        project_root="/tmp",
    )


def test_context_client_stale_when_contexts_change() -> None:
    from startd8.backend_codegen.context_manifest import parse_contexts

    (ctx,) = parse_contexts(CONTEXTS)
    text = render_context_client(SCHEMA, CONTEXTS, ctx)
    assert owned_file_in_sync(SCHEMA, text, contexts_text=CONTEXTS)
    changed = CONTEXTS.replace("8001", "8002")
    assert not owned_file_in_sync(SCHEMA, text, contexts_text=changed)


def test_backend_emits_context_clients(tmp_path) -> None:
    contexts = tmp_path / "prisma" / "contexts.yaml"
    contexts.parent.mkdir(parents=True)
    contexts.write_text(CONTEXTS, encoding="utf-8")
    artifacts = dict(
        render_backend(
            SCHEMA,
            contexts_text=CONTEXTS,
            project_root=str(tmp_path),
        )
    )
    assert "clients/catalog_client.py" in artifacts
    assert "CatalogClient" in artifacts["clients/catalog_client.py"]


def test_export_openapi_matches_openapi_spec_canonical() -> None:
    """M0 — exported JSON is a canonical dump of owned OPENAPI_SPEC."""
    contract = render_openapi_contract(SCHEMA, api_text=OVERLAY)
    spec = extract_openapi_spec_from_text(contract)
    assert spec is not None
    canonical = json.dumps(spec, indent=2, sort_keys=True) + "\n"
    re_extracted = json.loads(canonical)
    assert re_extracted == spec
    assert "/webhooks/stripe" in spec["paths"]
