"""M0 unit tests for the deterministic /health renderer (fastapi-health owned artifact).

Mirrors test_deployment_mode.py: the renderer is byte-stable + schema-only, and `owned_file_in_sync`
re-derives it from schema alone ($0 drift recognition — no app.yaml, no manifest).
"""

from __future__ import annotations

import pytest

from startd8.backend_codegen import (
    is_owned_generated_file,
    owned_file_in_sync,
    render_backend,
)
from startd8.backend_codegen.health_renderer import render_health

pytestmark = pytest.mark.unit

SCHEMA = "model Note {\n  id    String @id @default(cuid())\n  title String\n}\n"


def test_header_carries_kind_and_sha() -> None:
    text = render_health(SCHEMA)
    assert "# startd8-artifact: fastapi-health" in text
    assert "# schema-sha256: " in text


def test_byte_identical_per_schema() -> None:
    assert render_health(SCHEMA) == render_health(SCHEMA)


def test_skip_hook_in_sync_from_schema_only() -> None:
    # THE $0 property: drift re-renders from schema alone and byte-matches (no app.yaml/manifest).
    text = render_health(SCHEMA)
    assert owned_file_in_sync(SCHEMA, text) is True
    assert is_owned_generated_file(text) is True


def test_drift_detects_tamper() -> None:
    tampered = render_health(SCHEMA).replace('"status": "ok"', '"status": "OK"')
    assert owned_file_in_sync(SCHEMA, tampered) is False


def test_readiness_is_bare_health_path_not_prefixed() -> None:
    # The deploy harness probes the BARE /health — a prefix="/health" router would 404 there.
    text = render_health(SCHEMA)
    assert '@health_router.get("/health")' in text
    assert "APIRouter(tags=" in text and 'prefix="/health"' not in text


def test_fail_closed_503_and_select_1() -> None:
    text = render_health(SCHEMA)
    assert "status_code=503" in text
    assert '"checks": {"db": "down"}' in text
    assert 'text("SELECT 1")' in text


def test_liveness_endpoint_present() -> None:
    text = render_health(SCHEMA)
    assert '@health_router.get("/health/live")' in text
    assert '"status": "alive"' in text


def test_render_health_compiles() -> None:
    compile(render_health(SCHEMA), "app/health.py", "exec")


def test_assembler_emits_health_py() -> None:
    paths = [p for p, _ in render_backend(SCHEMA)]
    assert "app/health.py" in paths
