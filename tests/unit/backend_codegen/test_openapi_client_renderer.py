"""Unit tests for the deterministic httpx API client renderer (M3 / FR-7)."""

from __future__ import annotations

import pytest

from startd8.backend_codegen import (
    is_owned_generated_file,
    owned_file_in_sync,
    render_backend,
)
from startd8.backend_codegen.openapi_client_renderer import render_http_client
from startd8.backend_codegen.sqlmodel_renderer import render_sqlmodel_tables

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
    text = render_http_client(SCHEMA)
    assert "# startd8-artifact: python-openapi-client" in text
    assert "# schema-sha256: " in text


def test_byte_identical_per_schema() -> None:
    assert render_http_client(SCHEMA) == render_http_client(SCHEMA)


def test_skip_hook_in_sync_from_schema_only() -> None:
    text = render_http_client(SCHEMA)
    assert owned_file_in_sync(SCHEMA, text) is True
    assert is_owned_generated_file(text) is True


def test_crud_methods_emitted() -> None:
    text = render_http_client(SCHEMA)
    assert "def list_note(" in text
    assert "def create_note(" in text
    assert "def get_note(" in text
    assert "def update_note(" in text
    assert "def delete_note(" in text
    assert "def list_link(" in text
    assert "def create_link(" in text
    assert "get_link(" not in text


def test_assembler_emits_client_package() -> None:
    paths = {p for p, _ in render_backend(SCHEMA)}
    assert "clients/__init__.py" in paths
    assert "clients/http_client.py" in paths


def test_render_compiles() -> None:
    compile(render_http_client(SCHEMA), "clients/http_client.py", "exec")


def test_client_create_and_list_via_mock_transport() -> None:
    import sys
    import types

    httpx = pytest.importorskip("httpx")
    pytest.importorskip("sqlmodel")

    schema = "model Note { id String @id @default(cuid())\n title String\n }\n"
    table_ns: dict = {}
    exec(compile(render_sqlmodel_tables(schema).text, "app.tables", "exec"), table_ns)
    app_pkg = types.ModuleType("app")
    tables_mod = types.ModuleType("app.tables")
    for key, val in table_ns.items():
        setattr(tables_mod, key, val)
    app_pkg.tables = tables_mod
    sys.modules["app"] = app_pkg
    sys.modules["app.tables"] = tables_mod
    NoteCreate = table_ns["NoteCreate"]

    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "POST" and request.url.path == "/note/":
            return httpx.Response(200, json={"id": "n1", "title": "hello"})
        if request.method == "GET" and request.url.path == "/note/":
            return httpx.Response(200, json=[{"id": "n1", "title": "hello"}])
        return httpx.Response(404)

    client_ns: dict = {}
    exec(compile(render_http_client(schema), "clients.http_client", "exec"), client_ns)
    ApiClient = client_ns["ApiClient"]

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport, base_url="http://test") as hc:
        api = ApiClient("http://test", client=hc)
        created = api.create_note(NoteCreate(title="hello"))
        assert created.id == "n1"
        listed = api.list_note()
        assert len(listed) == 1

    assert ("POST", "/note/") in calls
    assert ("GET", "/note/") in calls
