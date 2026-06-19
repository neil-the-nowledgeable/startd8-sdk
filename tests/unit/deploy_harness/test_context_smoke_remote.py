"""Unit tests — remote/deployed outbound producer smoke (Role 3 M2 remote)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from startd8.backend_codegen.context_manifest import parse_contexts
from startd8.deploy_harness.context_smoke import (
    OutboundSmokeResult,
    SmokeOutcome,
    aggregate_outbound_smoke,
    context_base_url_env_key,
    resolve_context_base_url,
    run_outbound_context_smokes,
    run_remote_producer_smoke,
)

pytestmark = pytest.mark.unit

SCHEMA = """\
model Note {
  id    String @id @default(cuid())
  title String
}
"""

REMOTE_CONTEXTS = """\
outbound:
  - id: catalog
    contract: openapi/catalog.json
    base_url: https://catalog.example.com
    routes: crud
"""

LOCAL_CONTEXTS = """\
outbound:
  - id: catalog
    local: true
    routes: crud
"""


def test_context_base_url_env_key() -> None:
    assert context_base_url_env_key("catalog") == "STARTD8_CONTEXT_CATALOG_BASE_URL"
    assert context_base_url_env_key("pay-svc") == "STARTD8_CONTEXT_PAY_SVC_BASE_URL"


def test_resolve_context_base_url_env_wins() -> None:
    (ctx,) = parse_contexts(REMOTE_CONTEXTS)
    url = resolve_context_base_url(
        ctx,
        env={"STARTD8_CONTEXT_CATALOG_BASE_URL": "https://override.example.com/"},
    )
    assert url == "https://override.example.com"


def test_resolve_context_base_url_local_loopback() -> None:
    (ctx,) = parse_contexts(LOCAL_CONTEXTS)
    assert resolve_context_base_url(ctx, loopback_port=8123) == "http://127.0.0.1:8123"
    assert resolve_context_base_url(ctx) is None


def test_resolve_context_base_url_manifest_port_placeholder() -> None:
    text = """\
outbound:
  - id: catalog
    local: true
    base_url: http://127.0.0.1:{port}
    routes: crud
"""
    (ctx,) = parse_contexts(text)
    assert resolve_context_base_url(ctx, loopback_port=9000) == "http://127.0.0.1:9000"


def test_aggregate_outbound_smoke_fail_wins() -> None:
    results = (
        OutboundSmokeResult("a", SmokeOutcome(status="pass")),
        OutboundSmokeResult("b", SmokeOutcome(status="fail", reason="post-500")),
    )
    status, reason = aggregate_outbound_smoke(results)
    assert status == "fail"
    assert reason == "outbound-fail:b"


def test_run_outbound_context_smokes_skips_without_base_url(tmp_path: Path) -> None:
    (tmp_path / "prisma").mkdir()
    (tmp_path / "prisma" / "contexts.yaml").write_text(
        "outbound:\n  - id: catalog\n    contract: openapi/catalog.json\n    routes: crud\n",
        encoding="utf-8",
    )
    (tmp_path / "prisma" / "schema.prisma").write_text(SCHEMA, encoding="utf-8")
    results = run_outbound_context_smokes(tmp_path)
    assert len(results) == 1
    assert results[0].outcome.status == "skipped"
    assert results[0].outcome.reason == "skipped:no-base-url"


def test_run_outbound_context_smokes_with_contract(tmp_path: Path) -> None:
    (tmp_path / "prisma").mkdir()
    (tmp_path / "openapi").mkdir()
    spec = {
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
                "NoteCreate": {
                    "type": "object",
                    "required": ["title"],
                    "properties": {"title": {"type": "string"}},
                }
            }
        },
    }
    (tmp_path / "openapi" / "catalog.json").write_text(json.dumps(spec), encoding="utf-8")
    (tmp_path / "prisma" / "contexts.yaml").write_text(REMOTE_CONTEXTS, encoding="utf-8")
    (tmp_path / "prisma" / "schema.prisma").write_text(SCHEMA, encoding="utf-8")

    with patch(
        "startd8.deploy_harness.context_smoke.run_remote_producer_smoke",
        return_value=SmokeOutcome(status="pass", resource="/note/"),
    ) as mock_run:
        results = run_outbound_context_smokes(tmp_path)
    assert len(results) == 1
    assert results[0].outcome.status == "pass"
    mock_run.assert_called_once()
    assert mock_run.call_args.args[0] == "https://catalog.example.com"


def test_run_remote_producer_smoke_delegates_to_run_smoke() -> None:
    with patch(
        "startd8.deploy_harness.context_smoke.run_smoke",
        return_value=SmokeOutcome(status="pass"),
    ) as mock_smoke:
        outcome = run_remote_producer_smoke("https://example.com", spec={"paths": {}})
    assert outcome.status == "pass"
    mock_smoke.assert_called_once_with(
        "https://example.com", spec={"paths": {}}, timeout=10.0
    )
