"""Filtered / faceted list views — P0-2 (strtd8 RESUME_LIBRARY_ARCHETYPE_GAPS).

A `filters:` section in views.yaml gives each entity facet (exact / JSON-array membership) + free-text
search; the generated `list_<e>` handler narrows server-side and the list template renders a GET form.
"""

from __future__ import annotations

import importlib
import sys

import pytest

from startd8.backend_codegen.filters_manifest import EntityFilter, parse_filters
from startd8.backend_codegen.htmx_generator import render_list_template, render_web

pytestmark = pytest.mark.unit

# `tags` is a list field (Column(JSON)) → membership; `status` scalar → exact; `label` searched.
SCHEMA = """
model Item {
  id     String   @id @default(cuid())
  status String   @default("active")
  label  String?
  tags   String[] @default([])
}
""".strip()

VIEWS = """
filters:
  Item:
    facets: [status, tags]
    search: [label]
""".strip()


# --------------------------------------------------------------------------- #
# FR-FL-1 manifest
# --------------------------------------------------------------------------- #

def test_parse_filters():
    assert parse_filters(VIEWS, known_entities=frozenset({"Item"})) == {
        "Item": EntityFilter(facets=("status", "tags"), search=("label",))
    }


def test_parse_filters_unknown_entity_fails():
    with pytest.raises(ValueError, match="unknown entity"):
        parse_filters(VIEWS, known_entities=frozenset({"Other"}))


def test_unknown_filter_field_fails_at_render():
    bad = "filters:\n  Item:\n    facets: [nope]\n"
    with pytest.raises(ValueError, match="unknown field 'nope'"):
        render_web(SCHEMA, forms_text=bad)


# --------------------------------------------------------------------------- #
# FR-FL-2/3 handler + FR-FL-4 template
# --------------------------------------------------------------------------- #

def test_handler_builds_facet_and_search_query():
    web = render_web(SCHEMA, forms_text=VIEWS)
    compile(web, "<web>", "exec")
    assert "from sqlalchemy import String as _SAString, cast as _sa_cast, or_ as _or" in web
    assert "stmt = select(Item)" in web
    assert "stmt = stmt.where(Item.status == _v)" in web                       # scalar exact
    # JSON membership + search use autoescape so LIKE wildcards (% _) in user input aren't wildcards
    assert "_sa_cast(Item.tags, _SAString).contains('\"' + _v + '\"', autoescape=True)" in web
    assert "_or(_sa_cast(Item.label, _SAString).icontains(_q, autoescape=True))" in web
    assert '"filters": dict(request.query_params)' in web


def test_list_template_has_filter_form():
    html = render_list_template(SCHEMA, "prisma/schema.prisma", "Item",
                                EntityFilter(facets=("status", "tags"), search=("label",)))
    assert '<form method="get" action="/ui/item"' in html
    assert 'name="status"' in html and 'name="tags"' in html
    assert 'name="q"' in html
    assert 'href="/ui/item">clear</a>' in html


# --------------------------------------------------------------------------- #
# FR-FL-6 inert without filters
# --------------------------------------------------------------------------- #

def test_no_filters_keeps_static_handler():
    web = render_web(SCHEMA)                                   # no forms_text
    assert "items = list(session.exec(select(Item)).all())" in web   # unchanged static query
    assert "_sa_cast" not in web
    html = render_list_template(SCHEMA, "prisma/schema.prisma", "Item")
    assert "<form method=\"get\"" not in html


# --------------------------------------------------------------------------- #
# FR-FL-2/3 runtime — the filters actually narrow rows
# --------------------------------------------------------------------------- #

_MY_TABLES = {"item"}


def _purge():
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]


def test_filters_narrow_rows_at_runtime(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    sqlmodel = pytest.importorskip("sqlmodel")
    from startd8.backend_codegen import render_backend

    def _drop():
        md = sqlmodel.SQLModel.metadata
        t = md.tables.get("item")
        if t is not None:
            md.remove(t)

    for rel, content in render_backend(SCHEMA, views_text=VIEWS):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'app.db'}")
    sys.path.insert(0, str(tmp_path))
    _purge()
    _drop()
    try:
        main = importlib.import_module("app.main")        # no AI layer → app lives in app.main
        db = importlib.import_module("app.db")
        tables = importlib.import_module("app.tables")
        from fastapi.testclient import TestClient
        from sqlmodel import Session

        with TestClient(main.app) as c:
            with Session(db.engine) as s:
                s.add(tables.Item(status="active", label="Lead engineer", tags=["python", "go"]))
                s.add(tables.Item(status="archived", label="Manager", tags=["python"]))
                s.add(tables.Item(status="active", label="Designer", tags=["figma"]))
                s.commit()

            def _ids(params):
                r = c.get("/ui/item", params=params)
                assert r.status_code == 200, r.text
                return r.text

            all_rows = _ids({})
            assert all_rows.count("/ui/item/") >= 3                  # no filter → all
            active = _ids({"status": "active"})
            assert "Lead engineer" in active and "Designer" in active and "Manager" not in active
            py = _ids({"tags": "python"})                            # JSON membership
            assert "Lead engineer" in py and "Manager" in py and "Designer" not in py
            assert "figma" not in py or "Designer" not in py         # figma row excluded
            srch = _ids({"q": "lead"})                               # case-insensitive search
            assert "Lead engineer" in srch and "Manager" not in srch
            # autoescape: a literal LIKE wildcard in user input is NOT a wildcard (no match-everything)
            pct = _ids({"q": "%"})
            assert "Lead engineer" not in pct and "Manager" not in pct and "Designer" not in pct
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        _purge()
        _drop()
