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
  metric     Metric?    @relation(fields: [metricId], references: [id])
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
        tables = importlib.import_module("app.tables")
        from fastapi.testclient import TestClient

        # FK constraint is declared on the SQLAlchemy table (from @relation)
        fks = list(tables.ProofPoint.__table__.c.metricId.foreign_keys)
        assert fks and fks[0].target_fullname == "metric.id"

        with TestClient(main.app) as c:  # context-manager triggers lifespan -> init_db
            # a Metric to reference (create_all dependency-ordered the tables)
            assert c.post("/metric", json={"id": "m1", "value": 2.5}).status_code == 200

            # JSON API with the DTO split + a valid FK reference
            body = {
                "id": "p1",
                "situation": "S",
                "action": "A",
                "result": "shipped",
                "confidence": "draft",
                "tags": ["growth", "ml"],
                "metricId": "m1",
            }
            r = c.post("/proofpoint", json=body)
            assert r.status_code == 200, r.text
            assert r.json()["tags"] == ["growth", "ml"]  # JSON-list column round-trip
            assert r.json()["confidence"] == "draft"  # enum
            assert r.json()["metricId"] == "m1"  # FK reference persisted

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


# Python-side cuid default on the PK — the UI create form omits the id (FR-PG-5), so the
# default_factory must fill it and the PRG redirect must recover it (FR-FS-2).
PRG = """\
model Note {
  id    String @id @default(cuid())
  title String
}
"""


def test_ui_create_prg_flow(tmp_path, monkeypatch):
    """FORM_SUBMIT_BEHAVIOR FR-FS-1..3/6: plain form POST → 303 → detail with the flash banner."""
    for rel, content in render_backend(PRG):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'app.db'}")

    sys.path.insert(0, str(tmp_path))
    _purge_app_modules()
    try:
        main = importlib.import_module("app.main")
        from fastapi.testclient import TestClient

        with TestClient(main.app) as c:
            # the defect this exists to prevent: a plain form POST must 303, never a blank 200
            r = c.post("/ui/note", data={"title": "hello"}, follow_redirects=False)
            assert r.status_code == 303, r.text
            loc = r.headers["location"]
            assert loc.startswith("/ui/note/") and loc.endswith("?created=1")

            # following the redirect lands on the detail page with the confirmation flash
            r = c.get(loc)
            assert r.status_code == 200
            assert "✓ Note stored." in r.text and "hello" in r.text

            # a browser refresh re-GETs the destination — no re-submit (PRG), record count stays 1
            assert len(c.get("/note").json()) == 1
            assert "✓ Note stored." in c.get(loc).text
            assert len(c.get("/note").json()) == 1

            # without the query param the banner is absent
            assert "stored." not in c.get(loc.split("?")[0]).text

            # edit PRGs back to detail with the updated flash
            note_id = loc.split("/")[-1].split("?")[0]
            r = c.post(f"/ui/note/{note_id}", data={"title": "revised"}, follow_redirects=False)
            assert r.status_code == 303
            assert r.headers["location"] == f"/ui/note/{note_id}?updated=1"
            r = c.get(r.headers["location"])
            assert "✓ Note updated." in r.text and "revised" in r.text

            # list mode highlights the new row when ?created=<pk> is echoed
            r = c.get(f"/ui/note?created={note_id}")
            assert 'class="new-row"' in r.text

            # HTMX delete swaps the row for a visible deleted-confirmation row
            r = c.post(f"/ui/note/{note_id}/delete")
            assert r.status_code == 200 and "✓ Note deleted." in r.text
            assert c.get("/note").json() == []
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        _purge_app_modules()


# Confirmed-bearing entity for the AR-5 confirm toggle. A unique model name avoids colliding with
# the other smoke tests' tables in SQLModel's process-global metadata registry.
CONFIRM = """\
model Suggestion {
  id        String  @id @default(cuid())
  result    String
  source    String  @default("human")
  confirmed Boolean @default(false)
}
"""


def test_confirm_toggle_flips_and_reswaps_the_row(tmp_path, monkeypatch):
    """CONFIRM_AFFORDANCE FR-CA-2/4/7: POST confirm flips `confirmed` and returns the re-rendered row."""
    for rel, content in render_backend(CONFIRM):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'app.db'}")

    sys.path.insert(0, str(tmp_path))
    _purge_app_modules()
    try:
        main = importlib.import_module("app.main")
        from fastapi.testclient import TestClient

        with TestClient(main.app) as c:
            # an AI-suggested, unconfirmed row (created via the UI form → confirmed defaults false)
            r = c.post("/ui/suggestion", data={"result": "shipped"}, follow_redirects=False)
            sid = r.headers["location"].split("/")[-1].split("?")[0]
            assert c.get(f"/suggestion/{sid}").json()["confirmed"] is False

            # the list row offers a confirm control (not yet confirmed)
            assert ">confirm</button>" in c.get("/ui/suggestion").text

            # POST confirm flips the DB flag and returns the re-rendered row showing the new state
            r = c.post(f"/ui/suggestion/{sid}/confirm")
            assert r.status_code == 200
            assert "✓ confirmed" in r.text and ">unconfirm</button>" in r.text
            assert f'id="row-{sid}"' in r.text  # same row id → subsequent toggles still target it
            assert c.get(f"/suggestion/{sid}").json()["confirmed"] is True

            # a second POST toggles it back (FR-CA-4 full toggle, reversible)
            r = c.post(f"/ui/suggestion/{sid}/confirm")
            assert ">confirm</button>" in r.text
            assert c.get(f"/suggestion/{sid}").json()["confirmed"] is False

            # FR-CA-5: the detail page carries the same toggle in its own block
            detail = c.get(f"/ui/suggestion/{sid}")
            assert detail.status_code == 200
            assert f'id="confirm-{sid}"' in detail.text and ">confirm</button>" in detail.text

            # the detail control sends HX-Target=confirm-<id> → route returns the confirm fragment
            # (a <span>, not a <tr>), and flips the flag
            r = c.post(
                f"/ui/suggestion/{sid}/confirm", headers={"HX-Target": f"confirm-{sid}"}
            )
            assert r.status_code == 200
            assert f'<span id="confirm-{sid}">' in r.text and "<tr" not in r.text
            assert "✓ confirmed" in r.text and ">unconfirm</button>" in r.text
            assert c.get(f"/suggestion/{sid}").json()["confirmed"] is True
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        _purge_app_modules()
