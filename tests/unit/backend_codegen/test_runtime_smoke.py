"""Runtime smoke test: generate the backend, then actually SERVE it via FastAPI's TestClient.

This is the only test that imports fastapi/sqlmodel/jinja2 and drives a request cycle, so it catches
defects static checks can't (Starlette ``TemplateResponse`` signature, unmounted routers, JSON-column
round-trip, DTO validation). The app's runtime deps are NOT SDK deps, so the test **skips** when they
are absent (the SDK venv) and runs in any environment that has them (CI-with-app-deps, or after
`pip install -r requirements.txt`). It mirrors the manual smoke run that validated the path.
"""

from __future__ import annotations

import importlib
import sys

import pytest

# App-runtime deps (skip cleanly if not installed — they are generated-app deps, not SDK deps).
pytest.importorskip("fastapi")
pytest.importorskip("sqlmodel")
pytest.importorskip("jinja2")
pytest.importorskip("multipart")  # python-multipart imports as `multipart`

from startd8.backend_codegen import render_backend  # noqa: E402

pytestmark = pytest.mark.unit

PILOT = """\
enum Confidence {
  draft
  confirmed
}

model ProofPoint {
  id         String     @id
  situation  String
  action     String
  result     String
  confidence Confidence
  tags       String[]
  metricId   String?
}

model Metric {
  id    String @id
  value Float
}
"""


def _purge_app_modules():
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]


def test_generated_app_serves_full_cycle(tmp_path, monkeypatch):
    # 1. generate the whole backend to a temp project root
    for rel, content in render_backend(PILOT):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    # sqlite in the temp dir (db.py uses ./app.db relative to CWD)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'app.db'}")

    # 2. import the freshly-generated app package
    sys.path.insert(0, str(tmp_path))
    _purge_app_modules()
    try:
        main = importlib.import_module("app.main")
        from fastapi.testclient import TestClient

        with TestClient(main.app) as c:  # context-manager triggers lifespan -> init_db
            # JSON API with the DTO split
            body = {
                "id": "p1",
                "situation": "S",
                "action": "A",
                "result": "shipped",
                "confidence": "draft",
                "tags": ["growth", "ml"],
                "metricId": None,
            }
            r = c.post("/proofpoint", json=body)
            assert r.status_code == 200, r.text
            assert r.json()["tags"] == ["growth", "ml"]  # JSON-list column round-trip
            assert r.json()["confidence"] == "draft"  # enum

            # partial PATCH via XUpdate leaves other fields intact
            r = c.patch("/proofpoint/p1", json={"result": "promoted"})
            assert r.status_code == 200 and r.json()["result"] == "promoted"
            assert r.json()["situation"] == "S"

            # HTMX UI (web_router mounting + Jinja templates)
            r = c.get("/ui/proofpoint")
            assert r.status_code == 200 and "<table" in r.text and "promoted" in r.text
            r = c.get("/ui/proofpoint/new")
            assert r.status_code == 200 and '<select name="confidence"' in r.text
            # inline validation (needs python-multipart)
            r = c.post("/ui/proofpoint/validate", data={"result": ""})
            assert r.status_code == 200 and "required" in r.text.lower()
            # delete
            assert c.post("/ui/proofpoint/p1/delete").status_code == 200
            assert c.get("/proofpoint").json() == []
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        _purge_app_modules()
