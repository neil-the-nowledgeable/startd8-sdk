"""M1/M2 runtime tests: generate a backend, SERVE it, and exercise /health live.

Proves the mount works end-to-end (`pass:app-health` for the deploy harness) and the fail-closed 503
path via a dependency override (no real broken DB needed).
"""

from __future__ import annotations

import importlib
import sys

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlmodel")
pytest.importorskip("jinja2")
pytest.importorskip("multipart")

from startd8.backend_codegen import render_backend  # noqa: E402

pytestmark = pytest.mark.unit

# Unique model name: SQLModel.metadata is a process-global table registry, so reusing a name another
# runtime test uses (e.g. `Note`) collides on import. The health renderer is schema-invariant anyway.
SCHEMA = "model HealthFixtureRow {\n  id    String @id\n  title String\n}\n"


def _purge_app_modules():
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]


def _serve(tmp_path, monkeypatch):
    for rel, content in render_backend(SCHEMA):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'app.db'}")
    sys.path.insert(0, str(tmp_path))
    _purge_app_modules()
    main = importlib.import_module("app.main")
    from fastapi.testclient import TestClient

    return main, TestClient(main.app)


def test_health_live_200_and_fail_closed_503(tmp_path, monkeypatch):
    """One served app: /health → 200 ready, /health/live → 200, then DB-down → /health 503.

    Single test (not two) to avoid cross-test contamination of the cached ``app.*`` modules.
    """
    try:
        main, client = _serve(tmp_path, monkeypatch)
        with client:
            # happy path — pass:app-health for the deploy harness
            r = client.get("/health")
            assert r.status_code == 200 and r.json() == {"status": "ok"}
            live = client.get("/health/live")
            assert live.status_code == 200 and live.json() == {"status": "alive"}

            # fail-closed: override get_session with a session whose execute raises → 503
            from app.db import get_session  # noqa: PLC0415

            class _BrokenSession:
                def execute(self, *_a, **_k):
                    raise RuntimeError("db down")

            def _broken():
                yield _BrokenSession()

            main.app.dependency_overrides[get_session] = _broken
            bad = client.get("/health")
            assert bad.status_code == 503
            assert bad.json() == {"status": "degraded", "checks": {"db": "down"}}
            main.app.dependency_overrides.clear()
    finally:
        sys.path[:] = [p for p in sys.path if p != str(tmp_path)]
        _purge_app_modules()
