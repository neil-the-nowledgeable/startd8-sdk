# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: fastapi-health
# Source of truth: the Prisma schema.
# schema-sha256: 0b898e5f7f7f45151610a0e3830b0b5c32150ec8cc732b449b0d0ea40e8ce102

from __future__ import annotations

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
