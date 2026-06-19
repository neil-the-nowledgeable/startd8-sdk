"""Unit tests — outbound context client registry (Role 3 P2)."""

from __future__ import annotations

import pytest

from startd8.backend_codegen import owned_file_in_sync, render_backend
from startd8.backend_codegen.context_integration_renderer import (
    CONTEXT_INTEGRATION_KIND,
    CONTEXT_INTEGRATION_PATH,
    context_client_bindings,
    extract_client_methods,
    render_context_clients_module,
)

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


def test_render_context_clients_module_factories() -> None:
    text = render_context_clients_module(SCHEMA, CONTEXTS, project_root="/tmp")
    assert f"startd8-artifact: {CONTEXT_INTEGRATION_KIND}" in text
    assert "def get_catalog_client() -> CatalogClient:" in text
    assert "_CONTRACT_SHA_CATALOG" in text
    assert "def _context_env_key(producer_id: str)" in text


def test_context_client_bindings() -> None:
    bindings = context_client_bindings(SCHEMA, CONTEXTS, project_root="/tmp")
    assert len(bindings) == 1
    assert bindings[0].producer_id == "catalog"
    assert bindings[0].factory_name == "get_catalog_client"
    assert bindings[0].module_path == "clients/catalog_client.py"


def test_backend_emits_context_clients_registry(tmp_path) -> None:
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
    assert CONTEXT_INTEGRATION_PATH in artifacts
    registry = artifacts[CONTEXT_INTEGRATION_PATH]
    assert "get_catalog_client" in registry
    assert "from clients.catalog_client import CatalogClient" in registry


def test_owned_file_in_sync_context_integration() -> None:
    text = render_context_clients_module(SCHEMA, CONTEXTS, project_root="/tmp")
    assert owned_file_in_sync(
        SCHEMA,
        text,
        contexts_text=CONTEXTS,
        project_root="/tmp",
    )


def test_context_integration_stale_when_contexts_change() -> None:
    text = render_context_clients_module(SCHEMA, CONTEXTS, project_root="/tmp")
    changed = CONTEXTS.replace("8001", "8002")
    assert not owned_file_in_sync(SCHEMA, text, contexts_text=changed, project_root="/tmp")


def test_extract_client_methods() -> None:
    source = """
class CatalogClient:
    def list_note(self) -> list:
        ...
    def create_note(self, body) -> dict:
        ...
"""
    assert extract_client_methods(source) == ["list_note", "create_note"]
