"""Runtime smoke: generate backend → `polish` → the app boots and SERVES the polished stylesheet.

Proves the whole Tier-1 path end-to-end (FR-22): the FR-25 static hook in the generated main.py
activates once polish writes static_setup.py + the CSS, and base.html's <link> resolves to it.
Skips cleanly when the app-runtime deps (not SDK deps) are absent — same discipline as
backend_codegen's runtime smoke.
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
from startd8.presentation_polish import PolishConfig, apply_polish  # noqa: E402

pytestmark = pytest.mark.unit

# Distinct model names per test — SQLModel/SQLAlchemy keeps a process-global MetaData, so two
# imports of the same model name across tests would clash (mirrors backend_codegen's runtime smoke).
SCHEMA = """\
model Gadget {
  id    String @id @default(cuid())
  title String
}
"""

SCHEMA_BARE = """\
model Widget {
  id    String @id @default(cuid())
  title String
}
"""


def _purge_app_modules():
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]


def test_polished_app_serves_stylesheet(tmp_path, monkeypatch):
    # 1. generate the backend (now emits the static hook in main.py + the <link> in base.html)
    for rel, content in render_backend(SCHEMA):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    base_html = (tmp_path / "app/templates/base.html").read_text()
    assert '<link rel="stylesheet" href="/static/css/app.css">' in base_html

    # 2. apply polish
    result = apply_polish(PolishConfig(project_root=tmp_path, theme="professional"))
    assert result.cost_usd == 0.0
    assert (tmp_path / "app/static/css/app.css").is_file()
    assert (tmp_path / "app/static_setup.py").is_file()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'app.db'}")
    sys.path.insert(0, str(tmp_path))
    _purge_app_modules()
    try:
        main = importlib.import_module("app.main")
        from fastapi.testclient import TestClient

        with TestClient(main.app) as c:
            # the polished stylesheet is actually served at the linked path
            r = c.get("/static/css/app.css")
            assert r.status_code == 200, r.text
            assert "STARTD8-POLISH" in r.text
            assert "theme=professional" in r.text
            assert "var(--color-primary)" in r.text

            # the UI page links the stylesheet and still renders
            page = c.get("/ui/gadget")
            assert page.status_code == 200
            assert '/static/css/app.css' in page.text
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        _purge_app_modules()


def test_unpolished_app_still_boots(tmp_path, monkeypatch):
    """The static hook is a no-op when polish hasn't run — the bare app is unaffected."""
    for rel, content in render_backend(SCHEMA_BARE):
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
            assert c.get("/ui/widget").status_code == 200  # boots fine without static_setup.py
            assert c.get("/static/css/app.css").status_code == 404  # nothing mounted yet
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        _purge_app_modules()
