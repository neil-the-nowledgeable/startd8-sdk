"""Unit tests for the OpenAPI spec validation gate (M2 / FR-6)."""

from __future__ import annotations

import pytest

from startd8.backend_codegen.openapi_contract_renderer import render_openapi_contract
from startd8.validators.openapi_spec_gate import (
    extract_openapi_spec_from_text,
    run_openapi_spec_gate,
    validate_openapi_spec_dict,
)

pytestmark = pytest.mark.unit

SCHEMA = "model Note {\n  id String @id\n  title String\n}\n"


def test_extract_openapi_spec_from_text() -> None:
    text = render_openapi_contract(SCHEMA)
    spec = extract_openapi_spec_from_text(text)
    assert spec is not None
    assert spec["openapi"] == "3.0.3"
    assert "/note/" in spec["paths"]


def test_validate_emitted_spec_passes_when_validator_installed() -> None:
    pytest.importorskip("openapi_spec_validator")
    spec = extract_openapi_spec_from_text(render_openapi_contract(SCHEMA))
    assert spec is not None
    result = validate_openapi_spec_dict(spec)
    assert result.status == "checked"
    assert result.is_pass


def test_validate_invalid_spec_fails() -> None:
    pytest.importorskip("openapi_spec_validator")
    result = validate_openapi_spec_dict({"openapi": "3.0.3"})
    assert result.status == "checked"
    assert not result.is_pass


def test_run_gate_on_generated_project(tmp_path) -> None:
    pytest.importorskip("openapi_spec_validator")
    text = render_openapi_contract(SCHEMA)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "openapi_contract.py").write_text(text, encoding="utf-8")
    result = run_openapi_spec_gate(str(tmp_path))
    assert result.is_pass


def test_run_gate_missing_contract_is_error(tmp_path) -> None:
    result = run_openapi_spec_gate(str(tmp_path))
    assert result.status == "error"
    assert not result.is_pass
