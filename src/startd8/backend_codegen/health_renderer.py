"""Deterministic ``/health`` endpoint renderer (FastAPI) — bucket-1 applicational completion.

Emits ``app/health.py``: a **readiness** endpoint at the **bare** ``GET /health`` (exactly what the
deploy harness probes, so it grades ``pass:app-health`` not ``pass:liveness-only``) plus a ``GET
/health/live`` liveness endpoint. Readiness runs a trivial ``SELECT 1`` via the app's ``get_session``
and **fail-closes to 503** on DB failure — a ``200``-with-error-body would read as healthy to a load
balancer or the harness (HEALTH_ENDPOINT_REQUIREMENTS v0.2 FR-1/3/8).

**Mode-invariant** (FR-7): it uses whatever engine/session the app configured (installed → SQLite,
deployed → Postgres via ``DATABASE_URL``), so ONE schema-only artifact serves both modes — unlike
``settings.py`` there is no per-mode rendering.
"""

from __future__ import annotations

from ..frontend_codegen.schema_renderer import schema_sha256
from ._headers import header_standard as _header

_BODY = '''from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlmodel import Session

from .db import get_session

# Readiness is the BARE /health (the deploy harness probes that exact path); /health/live is liveness.
health_router = APIRouter(tags=["health"])


@health_router.get("/health")
def health(session: Session = Depends(get_session)) -> JSONResponse:
    """Readiness: 200 when the DB answers ``SELECT 1``, else 503 (fail-closed)."""
    try:
        session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - any DB failure is "not ready"
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "checks": {"db": "down"}},
        )
    return JSONResponse(content={"status": "ok"})


@health_router.get("/health/live")
def health_live() -> dict:
    """Liveness: 200 if the process serves (no DB dependency)."""
    return {"status": "alive"}
'''


def render_health(schema_text: str, source_file: str = "prisma/schema.prisma") -> str:
    """Render ``app/health.py`` — bare ``/health`` readiness (SELECT 1 → 200/503) + ``/health/live``.

    Deterministic and schema-only: the body is invariant; only the provenance header carries the
    ``schema-sha256`` so drift re-renders byte-identically (the ``fastapi-health`` owned kind).
    """
    sha = schema_sha256(schema_text)
    header = _header(source_file, sha, "fastapi-health")
    return header + "\n\n" + _BODY
