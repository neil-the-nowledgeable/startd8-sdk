"""Tests for cross-context smoke test emission and loopback round-trip (Role 3 M2)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from startd8.backend_codegen import render_backend
from startd8.backend_codegen.drift import owned_file_in_sync
from startd8.backend_codegen.test_emitter import (
    CROSS_CONTEXT_SMOKE_TESTS_PATH,
    render_cross_context_smoke_tests,
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
    routes: crud
"""


def test_render_cross_context_smoke_tests_emits_local_test() -> None:
    text = render_cross_context_smoke_tests(SCHEMA, CONTEXTS)
    assert "python-tests-cross-context" in text
    assert "test_catalog_client_list_create_round_trip" in text
    assert "run_context_client_smoke" in text
    assert "CatalogClient" in text


def test_render_backend_includes_cross_context_smoke_tests() -> None:
    arts = dict(render_backend(SCHEMA, contexts_text=CONTEXTS))
    assert CROSS_CONTEXT_SMOKE_TESTS_PATH in arts
    assert "test_catalog_client_list_create_round_trip" in arts[CROSS_CONTEXT_SMOKE_TESTS_PATH]


def test_cross_context_smoke_drift_in_sync() -> None:
    text = render_cross_context_smoke_tests(SCHEMA, CONTEXTS)
    assert owned_file_in_sync(SCHEMA, text, contexts_text=CONTEXTS)


def test_cross_context_smoke_asgi_round_trip(tmp_path: Path) -> None:
    """Generated client + TestClient shim list+create against the local producer app."""
    pytest.importorskip("fastapi")
    pytest.importorskip("sqlmodel")

    arts = dict(render_backend(SCHEMA, contexts_text=CONTEXTS))
    for rel, content in arts.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    (tmp_path / "clients" / "__init__.py").write_text("", encoding="utf-8")

    sys.path.insert(0, str(tmp_path))
    try:
        from fastapi.testclient import TestClient

        from app.main import app
        from app.openapi_contract import OPENAPI_SPEC
        from clients.catalog_client import CatalogClient
        from startd8.deploy_harness.context_smoke import run_context_client_smoke

        class _TestClientHttpx:
            def __init__(self, tc):
                self._tc = tc

            def get(self, url, **kwargs):
                return self._tc.get(url, **kwargs)

            def post(self, url, **kwargs):
                return self._tc.post(url, **kwargs)

            def patch(self, url, **kwargs):
                return self._tc.patch(url, **kwargs)

            def delete(self, url, **kwargs):
                return self._tc.delete(url, **kwargs)

            def close(self) -> None:
                pass

        with TestClient(app) as tc:
            with CatalogClient("http://test", client=_TestClientHttpx(tc)) as outbound:
                outcome = run_context_client_smoke(outbound, OPENAPI_SPEC)
        assert outcome.status == "pass", outcome.reason
    finally:
        sys.path.remove(str(tmp_path))
