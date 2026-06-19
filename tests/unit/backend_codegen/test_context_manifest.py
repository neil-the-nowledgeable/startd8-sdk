"""Unit tests — ``contexts.yaml`` grammar and contract filtering (Role 3 M1)."""

from __future__ import annotations

import pytest

from startd8.backend_codegen.context_manifest import (
    contract_sha256,
    filter_spec_for_client,
    parse_contexts,
)

pytestmark = pytest.mark.unit

SCHEMA = """\
model Note {
  id    String @id @default(cuid())
  title String
}
"""

VALID = """\
outbound:
  - id: catalog
    local: true
    base_url: http://127.0.0.1:8001
    routes: crud
"""


def test_parse_contexts_absent_returns_empty() -> None:
    assert parse_contexts(None) == ()
    assert parse_contexts("") == ()


def test_parse_contexts_valid_local() -> None:
    (ctx,) = parse_contexts(VALID)
    assert ctx.id == "catalog"
    assert ctx.local is True
    assert ctx.routes == "crud"
    assert ctx.base_url == "http://127.0.0.1:8001"


def test_parse_contexts_rejects_local_and_contract() -> None:
    text = "outbound:\n  - id: x\n    local: true\n    contract: openapi/x.json\n"
    with pytest.raises(ValueError, match="local: true.*contract"):
        parse_contexts(text)


def test_parse_contexts_rejects_duplicate_ids() -> None:
    text = "outbound:\n  - id: a\n    local: true\n  - id: a\n    local: true\n"
    with pytest.raises(ValueError, match="duplicate"):
        parse_contexts(text)


def test_filter_spec_for_client_crud_keeps_entity_paths() -> None:
    from startd8.backend_codegen.openapi_contract_renderer import render_openapi_contract
    from startd8.validators.openapi_spec_gate import extract_openapi_spec_from_text

    contract = render_openapi_contract(SCHEMA)
    spec = extract_openapi_spec_from_text(contract)
    assert spec is not None
    filtered = filter_spec_for_client(spec, SCHEMA, routes="crud")
    assert "/note/" in filtered["paths"]
    assert "NoteCreate" in filtered["components"]["schemas"]
    assert contract_sha256(filtered) == contract_sha256(filter_spec_for_client(spec, SCHEMA))
