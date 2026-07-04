"""Unit tests for brownfield OpenAPI normalize (OpenAPI Role 2 FR-D1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from startd8.backend_codegen.api_overlay_manifest import normalize_overlay_path
from startd8.backend_codegen.openapi_normalize import (
    load_openapi_document,
    normalize_openapi_to_overlay,
)
from startd8.cli_openapi import openapi_app

pytestmark = pytest.mark.unit

runner = CliRunner()

SCHEMA = """\
model Note {
  id    String @id @default(cuid())
  title String
}
"""


def _external_spec() -> dict:
    return {
        "openapi": "3.0.3",
        "info": {"title": "Brownfield", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.com"}],
        "tags": [{"name": "notes"}],
        "paths": {
            "/note/": {
                "get": {
                    "tags": ["notes"],
                    "operationId": "listNotes",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/note/{item_id}": {
                "get": {
                    "operationId": "getNote",
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/webhooks/stripe": {
                "post": {
                    "summary": "Stripe webhook",
                    "responses": {"200": {"description": "OK"}},
                }
            },
        },
        "components": {
            "schemas": {
                "NoteRead": {"type": "object", "properties": {"id": {"type": "string"}}},
                "WebhookPayload": {"type": "object"},
            }
        },
    }


def test_normalize_overlay_path_single_segment() -> None:
    assert normalize_overlay_path("/note") == "/note/"
    assert normalize_overlay_path("/webhooks/stripe") == "/webhooks/stripe"
    assert normalize_overlay_path("/note/{item_id}") == "/note/{item_id}"


def test_subtracts_base_crud_paths_with_schema() -> None:
    result = normalize_openapi_to_overlay(_external_spec(), schema_text=SCHEMA)
    assert "/webhooks/stripe" in result.kept_paths
    assert "/note/" not in result.kept_paths
    assert "/note/{item_id}" not in result.kept_paths
    assert len(result.stripped_paths) >= 2
    assert "NoteRead" in result.stripped_schemas


def test_strips_framework_noise() -> None:
    result = normalize_openapi_to_overlay(_external_spec())
    overlay = result.overlay
    assert "servers" not in overlay
    assert "tags" not in overlay
    post = overlay["paths"]["/webhooks/stripe"]["post"]
    assert "operationId" not in post
    assert "tags" not in post
    assert post["summary"] == "Stripe webhook"


def test_keeps_non_prisma_schemas_referenced() -> None:
    spec = _external_spec()
    spec["paths"]["/webhooks/stripe"]["post"]["requestBody"] = {
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/WebhookPayload"}
            }
        }
    }
    result = normalize_openapi_to_overlay(spec)
    schemas = result.overlay.get("components", {}).get("schemas", {})
    assert "WebhookPayload" in schemas


def test_trailing_slash_duplicate_warning() -> None:
    spec = _external_spec()
    spec["paths"]["/note"] = {
        "post": {"responses": {"200": {"description": "OK"}}}
    }
    result = normalize_openapi_to_overlay(spec)
    assert any("trailing-slash duplicate" in w for w in result.warnings)


def test_cli_normalize_writes_yaml(tmp_path: Path) -> None:
    schema = tmp_path / "schema.prisma"
    schema.write_text(SCHEMA, encoding="utf-8")
    src = tmp_path / "openapi.json"
    src.write_text(json.dumps(_external_spec()), encoding="utf-8")
    out = tmp_path / "api.yaml"

    result = runner.invoke(
        openapi_app,
        ["normalize", str(src), "--out", str(out), "--schema", str(schema)],
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()
    loaded = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert "/webhooks/stripe" in loaded["paths"]
    assert "/note/" not in loaded["paths"]


def test_load_openapi_document_json(tmp_path: Path) -> None:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps({"openapi": "3.0.3", "paths": {}}), encoding="utf-8")
    spec = load_openapi_document(path)
    assert spec["openapi"] == "3.0.3"


def test_load_openapi_document_rejects_empty_yaml(tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        load_openapi_document(path)
