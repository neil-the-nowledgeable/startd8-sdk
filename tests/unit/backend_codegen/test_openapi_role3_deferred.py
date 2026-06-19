"""Role 3 deferred items D1–D5 — auth, TS client, context graph, gRPC client."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from startd8.backend_codegen import render_backend
from startd8.backend_codegen.context_graph_renderer import (
    CONTEXT_GRAPH_PATH,
    build_context_graph,
)
from startd8.backend_codegen.context_manifest import parse_contexts_file

pytestmark = pytest.mark.unit

SCHEMA = """\
model Note {
  id    String @id @default(cuid())
  title String
}
"""

CONTEXTS_AUTH = """\
outbound:
  - id: catalog
    local: true
    base_url: http://127.0.0.1:8001
    routes: crud
    auth:
      scheme: bearer
      env: STARTD8_CONTEXT_CATALOG_TOKEN
"""

CONTEXTS_TS = """\
emit_languages:
  - typescript
outbound:
  - id: catalog
    contract: openapi/catalog.json
    base_url: http://127.0.0.1:8001
    routes: crud
"""

PROTO = """\
syntax = "proto3";
package catalog;
service CatalogService {
  rpc ListNotes(ListNotesRequest) returns (ListNotesResponse);
}
message ListNotesRequest {}
message ListNotesResponse {}
"""

CONTEXTS_GRPC = """\
outbound:
  - id: catalog
    protocol: grpc
    contract: proto/catalog.proto
    grpc_service: CatalogService
    base_url: localhost:50051
"""


def test_auth_headers_in_http_client(tmp_path: Path) -> None:
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "contexts.yaml").write_text(CONTEXTS_AUTH, encoding="utf-8")
    arts = dict(
        render_backend(
            SCHEMA,
            contexts_text=CONTEXTS_AUTH,
            project_root=str(tmp_path),
        )
    )
    client = arts["clients/catalog_client.py"]
    assert "_AUTH_ENV = 'STARTD8_CONTEXT_CATALOG_TOKEN'" in client
    assert "Bearer {token}" in client
    assert "headers.update(self._auth_headers())" in client


def test_typescript_client_emitted_when_requested(tmp_path: Path) -> None:
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "schema.prisma").write_text(SCHEMA, encoding="utf-8")
    (tmp_path / "prisma" / "contexts.yaml").write_text(CONTEXTS_TS, encoding="utf-8")
    (tmp_path / "openapi").mkdir()
    (tmp_path / "openapi" / "catalog.json").write_text(
        json.dumps(
            {
                "openapi": "3.0.3",
                "paths": {
                    "/note/": {
                        "get": {"responses": {"200": {"description": "OK"}}},
                        "post": {
                            "requestBody": {
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/NoteCreate"}
                                    }
                                }
                            },
                            "responses": {"200": {"description": "OK"}},
                        },
                    }
                },
                "components": {
                    "schemas": {
                        "NoteCreate": {"type": "object", "properties": {"title": {"type": "string"}}}
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    arts = dict(
        render_backend(
            SCHEMA,
            contexts_text=CONTEXTS_TS,
            project_root=str(tmp_path),
        )
    )
    assert "clients/catalog_client.ts" in arts
    assert "export class CatalogClient" in arts["clients/catalog_client.ts"]
    assert "async list_note" in arts["clients/catalog_client.ts"]


def test_context_graph_export(tmp_path: Path) -> None:
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "contexts.yaml").write_text(CONTEXTS_AUTH, encoding="utf-8")
    arts = dict(
        render_backend(
            SCHEMA,
            contexts_text=CONTEXTS_AUTH,
            project_root=str(tmp_path),
        )
    )
    assert CONTEXT_GRAPH_PATH in arts
    graph = json.loads(arts[CONTEXT_GRAPH_PATH])
    assert graph["schema_version"] == 1
    assert graph["outbound"][0]["id"] == "catalog"
    assert graph["outbound"][0]["auth"]["env"] == "STARTD8_CONTEXT_CATALOG_TOKEN"
    assert "python" in graph["outbound"][0]["clients"]


def test_grpc_client_emitted(tmp_path: Path) -> None:
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "contexts.yaml").write_text(CONTEXTS_GRPC, encoding="utf-8")
    (tmp_path / "proto").mkdir()
    (tmp_path / "proto" / "catalog.proto").write_text(PROTO, encoding="utf-8")
    arts = dict(
        render_backend(
            SCHEMA,
            contexts_text=CONTEXTS_GRPC,
            project_root=str(tmp_path),
        )
    )
    assert "clients/catalog_grpc_client.py" in arts
    grpc_client = arts["clients/catalog_grpc_client.py"]
    assert "CatalogGrpcClient" in grpc_client
    assert "def list_notes" in grpc_client
    assert "catalog_pb2_grpc" in grpc_client
    graph = build_context_graph(SCHEMA, CONTEXTS_GRPC, project_root=str(tmp_path))
    assert graph["outbound"][0]["protocol"] == "grpc"
    assert "contract_sha256" in graph["outbound"][0]


def test_parse_contexts_file_emit_languages() -> None:
    manifest = parse_contexts_file(CONTEXTS_TS)
    assert manifest.emit_languages == ("typescript",)
