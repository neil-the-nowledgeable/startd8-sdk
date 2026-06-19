"""Integration tests — manifest + api.yaml overlay contract drift (FR-5 / Role 2 v1)."""

from __future__ import annotations

import json

import pytest

from startd8.backend_codegen import owned_file_in_sync, render_backend
from startd8.backend_codegen.openapi_contract_renderer import render_openapi_contract
from startd8.backend_codegen.test_emitter import render_openapi_contract_tests
from startd8.validators.openapi_spec_gate import extract_openapi_spec_from_text

pytestmark = pytest.mark.unit

SCHEMA = """\
model Note {
  id    String @id @default(cuid())
  title String
}
"""

AI_MANIFEST = """
passes:
  - name: extract
    output_entities: [Note]
    route_path: /extract
    prompt: prompts/extract.md
""".strip()

PAGES_MANIFEST = """
pages:
  - slug: /
    title: Home
    content: pages/home.md
""".strip()

OVERLAY = """\
paths:
  /webhooks/stripe:
    post:
      responses:
        '200':
          description: OK
"""


def test_contract_drift_with_manifests_and_overlay() -> None:
    text = render_openapi_contract(
        SCHEMA,
        manifest_text=AI_MANIFEST,
        pages_text=PAGES_MANIFEST,
        api_text=OVERLAY,
    )
    assert owned_file_in_sync(
        SCHEMA,
        text,
        manifest_text=AI_MANIFEST,
        pages_text=PAGES_MANIFEST,
        api_text=OVERLAY,
    )


def test_contract_tests_emit_conditional_and_ref_check() -> None:
    text = render_openapi_contract_tests(
        SCHEMA,
        manifest_text=AI_MANIFEST,
        pages_text=PAGES_MANIFEST,
    )
    assert "_CONDITIONAL:" in text
    assert '("POST", "/ai/extract")' in text
    assert "test_conditional_routes_in_manifest" in text
    assert "test_openapi_internal_refs_resolve" in text


def test_backend_emits_reconciliation_test_block() -> None:
    artifacts = dict(
        render_backend(
            SCHEMA,
            manifest_text=AI_MANIFEST,
            api_text=OVERLAY,
        )
    )
    tests = artifacts["tests/test_openapi_contract.py"]
    assert "test_openapi_internal_refs_resolve" in tests
    assert "/webhooks/stripe" in artifacts["app/openapi_contract.py"]


def test_export_openapi_shape_matches_merged_contract() -> None:
    text = render_openapi_contract(SCHEMA, api_text=OVERLAY, manifest_text=AI_MANIFEST)
    spec = extract_openapi_spec_from_text(text)
    assert spec is not None
    assert "/webhooks/stripe" in spec["paths"]
    assert "/note/" in spec["paths"]
    exported = json.dumps(spec, indent=2, sort_keys=True)
    assert "/ai/extract" in exported or "ai" in json.dumps(spec["paths"])
