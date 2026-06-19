# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: python-tests-health
# Source of truth: the Prisma schema.
# schema-sha256: 0b898e5f7f7f45151610a0e3830b0b5c32150ec8cc732b449b0d0ea40e8ce102

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

_testclient = pytest.importorskip("fastapi.testclient")
pytest.importorskip("sqlmodel")
pytest.importorskip("httpx")

from app.main import app  # noqa: E402


def test_health_ready():
    """Bare /health is readiness — 200 {"status": "ok"} when the DB answers."""
    with _testclient.TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


def test_health_live():
    with _testclient.TestClient(app) as client:
        r = client.get("/health/live")
        assert r.status_code == 200
        assert r.json() == {"status": "alive"}
