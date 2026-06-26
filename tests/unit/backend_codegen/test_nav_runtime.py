"""Runtime proof for the always-on default nav (FR-6/7/13): SERVE a generated app and assert the nav
renders all surfaces by default, then that a ``nav.config.json`` hides an item across a restart.

One app is generated once; visibility is re-read on each ``lifespan`` entry, so a second ``TestClient``
context *is* a restart (FR-6). Generating a single app per process avoids the SQLModel declarative-
registry collision that makes multiple app-generating tests share table classes (why test_runtime_smoke
is a single function). Skips cleanly when the generated-app runtime deps are absent in the SDK venv.
"""

from __future__ import annotations

import importlib
import sys

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlmodel")
pytest.importorskip("jinja2")

from startd8.backend_codegen import render_backend  # noqa: E402

pytestmark = pytest.mark.unit

SCHEMA = """\
model Widget {
  id   String @id
  name String
}

model Gadget {
  id    String @id
  label String
}
"""

PAGES = """\
pages:
  - slug: /
    title: Home
    content: pages/home.md
    nav_label: Home
"""


def _purge_app_modules():
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]


def test_nav_default_visible_then_config_hides_across_restart(tmp_path, monkeypatch):
    for rel, content in render_backend(SCHEMA, pages_text=PAGES):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    (tmp_path / "app/templates/pages").mkdir(parents=True, exist_ok=True)
    (tmp_path / "app/templates/pages/_home.body.html").write_text("<p>home</p>\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'app.db'}")
    sys.path.insert(0, str(tmp_path))
    _purge_app_modules()
    try:
        main = importlib.import_module("app.main")
        from fastapi.testclient import TestClient

        # 1) No config → all three surface classes visible by default (FR-2/3). An entity screen
        #    extends base.html, so it renders the _nav.html partial.
        with TestClient(main.app) as c:
            html = c.get("/ui/widget").text
        assert 'href="/ui/widget"' in html
        assert 'href="/ui/gadget"' in html
        assert 'href="/"' in html  # the Home content page

        # 2) Operator hides the Gadget entity, then "restarts" (a new lifespan re-reads the config).
        (tmp_path / "nav.config.json").write_text('{"hidden": ["entity:Gadget"]}', encoding="utf-8")
        with TestClient(main.app) as c:
            html2 = c.get("/ui/widget").text
        assert 'href="/ui/widget"' in html2  # still visible
        assert 'href="/ui/gadget"' not in html2  # hidden by config at startup (FR-7)
        assert 'href="/"' in html2  # the content page is unaffected
    finally:
        _purge_app_modules()
