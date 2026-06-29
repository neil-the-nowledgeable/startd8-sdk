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
    """Full reset between this file's app-building functions: modules + SQLModel's process-global
    registry. The module-scoped conftest fixture only isolates *across* files; this file builds an app
    per function (same Widget/Gadget schema), so it must also clear the registry *between* functions or
    the second import hits 'Table already defined'."""
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]
    try:
        from sqlalchemy.orm import clear_mappers
        from sqlmodel import SQLModel
    except Exception:
        return
    reg = getattr(SQLModel, "_sa_registry", None)
    cls_reg = getattr(reg, "_class_registry", None)
    if cls_reg is None:
        return
    if any(
        isinstance(getattr(cls_reg.get(k), "__module__", ""), str)
        and getattr(cls_reg.get(k), "__module__", "").startswith("app")
        for k in list(cls_reg)
    ):
        clear_mappers()
        SQLModel.metadata.clear()
        for k in [k for k in list(cls_reg) if not k.startswith("_")]:
            del cls_reg[k]


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
            # This app authors `/` (Home page), so the index lives at the stable /_index sitemap and
            # the nav links it (FR-28a/28e); `/` itself stays the content page.
            sitemap = c.get("/_index")
            root = c.get("/")
        assert 'href="/ui/widget"' in html
        assert 'href="/ui/gadget"' in html
        assert 'href="/"' in html  # the Home content page
        assert 'href="/_index"' in html  # the nav links the sitemap (FR-28e)
        # FR-16 a11y: labelled landmark + the active item (current path) marked aria-current.
        assert '<nav aria-label="Primary"' in html
        assert 'href="/ui/widget" aria-current="page"' in html  # active on its own list route
        assert 'href="/ui/gadget" aria-current="page"' not in html  # a non-current item is not
        # FR-18 grouping: a separator is emitted at the page→entity boundary.
        assert 'aria-hidden="true"' in html
        # FR-28a: the sitemap is reachable at /_index and lists the app; `/` is the authored home.
        assert sitemap.status_code == 200 and 'href="/ui/widget"' in sitemap.text
        assert root.status_code == 200 and "this app" not in root.text  # `/` is the content page

        # 2) Operator hides the Gadget entity, then "restarts" (a new lifespan re-reads the config).
        (tmp_path / "nav.config.json").write_text('{"hidden": ["entity:Gadget"]}', encoding="utf-8")
        with TestClient(main.app) as c:
            html2 = c.get("/ui/widget").text
        assert 'href="/ui/widget"' in html2  # still visible
        assert 'href="/ui/gadget"' not in html2  # hidden by config at startup (FR-7)
        assert 'href="/"' in html2  # the content page is unaffected
    finally:
        _purge_app_modules()


def test_home_index_serves_at_root_and_lists_app(tmp_path, monkeypatch):
    """FR-28: with no content page owning `/`, the generated index serves `/` and lists the registry,
    respecting the visibility config (a hidden entity is absent from the index too)."""
    for rel, content in render_backend(SCHEMA):  # no pages → index claims `/`
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    assert (tmp_path / "app/index.py").exists() and (tmp_path / "app/templates/index.html").exists()
    (tmp_path / "nav.config.json").write_text('{"hidden": ["entity:Gadget"]}', encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'app.db'}")
    sys.path.insert(0, str(tmp_path))
    _purge_app_modules()
    try:
        main = importlib.import_module("app.main")
        from fastapi.testclient import TestClient

        with TestClient(main.app) as c:
            r = c.get("/")
        assert r.status_code == 200, r.text
        assert "What" in r.text and "this app" in r.text  # the index heading (FR-28c)
        assert 'href="/ui/widget"' in r.text  # lists the entity surface
        assert 'href="/ui/gadget"' not in r.text  # hidden by nav.config.json (FR-28b visibility)
        assert "<h2" in r.text  # grouped section heading
    finally:
        _purge_app_modules()


def test_index_shows_per_entity_record_counts(tmp_path, monkeypatch):
    """FR-28f: the index shows a live row count next to each entity (Records → Widget (N))."""
    for rel, content in render_backend(SCHEMA):  # no pages → index at `/`
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'app.db'}")
    sys.path.insert(0, str(tmp_path))
    _purge_app_modules()
    try:
        main = importlib.import_module("app.main")
        db = importlib.import_module("app.db")
        tables = importlib.import_module("app.tables")
        from fastapi.testclient import TestClient
        from sqlmodel import Session

        with TestClient(main.app) as c:  # lifespan creates tables
            with Session(db.engine) as s:
                s.add(tables.Widget(id="w1", name="a"))
                s.add(tables.Widget(id="w2", name="b"))
                s.add(tables.Gadget(id="g1", label="x"))
                s.commit()
            html = c.get("/").text
        # Two Widgets, one Gadget — counts render next to the entity labels.
        assert ">Widget</a> <span" in html and "(2)" in html
        assert "(1)" in html  # the single Gadget
    finally:
        _purge_app_modules()


def test_live_admin_toggle_hides_without_restart(tmp_path, monkeypatch):
    """FR-29: POST /admin/nav hides an entity in the SAME running process (no restart), persisted in
    the nav_hidden table; the admin page is reachable and (installed) shows the unauthenticated banner."""
    for rel, content in render_backend(SCHEMA):  # no pages → index + admin emitted
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    assert (tmp_path / "app/nav_store.py").exists() and (tmp_path / "app/nav_admin.py").exists()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'app.db'}")
    sys.path.insert(0, str(tmp_path))
    _purge_app_modules()
    try:
        main = importlib.import_module("app.main")
        from fastapi.testclient import TestClient

        with TestClient(main.app) as c:
            before = c.get("/ui/widget").text
            assert 'href="/ui/widget"' in before and 'href="/ui/gadget"' in before
            # admin page reachable; installed mode → unauthenticated banner
            admin = c.get("/admin/nav")
            assert admin.status_code == 200
            assert "Manage navigation" in admin.text and "unauthenticated" in admin.text
            # hide Gadget: submit every key as visible EXCEPT entity:Gadget
            r = c.post("/admin/nav", data={"visible": ["entity:Widget", "index"]})
            assert r.status_code == 200  # redirect followed back to the form
            # live, same process, no restart:
            after = c.get("/ui/widget").text
            assert 'href="/ui/widget"' in after  # still visible
            assert 'href="/ui/gadget"' not in after  # hidden by the live toggle
        # persisted in the nav_hidden table
        db = importlib.import_module("app.db")
        from sqlalchemy import text
        with db.engine.connect() as conn:
            rows = {r[0] for r in conn.execute(text("SELECT key FROM nav_hidden")).all()}
        assert "entity:Gadget" in rows
    finally:
        _purge_app_modules()
