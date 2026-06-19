"""Unit tests for deploy_harness.context_smoke (Role 3 M2 / FR-6)."""

from __future__ import annotations

import sys

import pytest

from startd8.backend_codegen.openapi_contract_renderer import render_openapi_contract
from startd8.deploy_harness.context_smoke import (
    create_dto_name,
    run_context_client_smoke,
)
from startd8.openapi_contract import select_crud_resource
from startd8.validators.openapi_spec_gate import extract_openapi_spec_from_text

pytestmark = pytest.mark.unit

SCHEMA = """\
model Note {
  id    String @id @default(cuid())
  title String
}
"""


class _FakeRow:
    def __init__(self, **data: object) -> None:
        self._data = data

    def model_dump(self) -> dict:
        return dict(self._data)


class _FakeNoteClient:
    def __init__(self) -> None:
        self._rows: list[_FakeRow] = []

    def list_note(self) -> list[_FakeRow]:
        return list(self._rows)

    def create_note(self, item: object) -> _FakeRow:
        row = _FakeRow(id="smoke-1", title=getattr(item, "title", "sample"))
        self._rows.append(row)
        return row


def test_create_dto_name_from_ref() -> None:
    contract = render_openapi_contract(SCHEMA)
    spec = extract_openapi_spec_from_text(contract)
    assert spec is not None
    choice, _ = select_crud_resource(spec)
    assert choice is not None
    assert create_dto_name(choice.create_schema, spec) == "NoteCreate"


def test_run_context_client_smoke_passes_with_fake_client() -> None:
    import types

    from pydantic import BaseModel

    contract = render_openapi_contract(SCHEMA)
    spec = extract_openapi_spec_from_text(contract)
    assert spec is not None

    class NoteCreate(BaseModel):
        title: str = "sample"

    fake_tables = types.ModuleType("fake_tables")
    fake_tables.NoteCreate = NoteCreate
    sys.modules["fake_tables"] = fake_tables
    try:
        outcome = run_context_client_smoke(
            _FakeNoteClient(), spec, tables_module="fake_tables"
        )
    finally:
        sys.modules.pop("fake_tables", None)
    assert outcome.status == "pass"
    assert outcome.resource == "/note/"


def test_run_context_client_smoke_skips_without_methods() -> None:
    contract = render_openapi_contract(SCHEMA)
    spec = extract_openapi_spec_from_text(contract)
    assert spec is not None
    outcome = run_context_client_smoke(object(), spec)
    assert outcome.status == "skipped"
    assert outcome.reason == "skipped:no-client-methods"
