"""``editors:`` archetype — bulk child-field editor (FR-ED-1..16).

Edit ONE field across a parent's filtered, grouped children in one form/POST, with reset-to-default.
Covers: manifest parse, contract validation, generation + drift round-trip + $0 skip-hook recognition,
orphan handling, the schema-only main.py mount, and the runtime behaviours that are the correctness crux
(dirty-detection vs the submitted mirror, reset→NULL, server-side row + field allow-list / anti-IDOR).
"""

from __future__ import annotations

import importlib
import sys

import pytest

from startd8.backend_codegen.editors_manifest import EditorSpec, parse_editors
from startd8.backend_codegen.editor_generator import (
    render_editor_router,
    render_editors,
    _validate_editor,
)
from startd8.backend_codegen.drift import (
    check_drift,
    embedded_artifact_kind,
    is_owned_generated_file,
    owned_file_in_sync,
)
from startd8.backend_codegen.crud_generator import render_main
from startd8.languages.prisma_parser import parse_prisma_schema

pytestmark = pytest.mark.unit

SCHEMA = """
model ResumeBuild {
  id String @id @default(cuid())
}
model ResumeBuildItem {
  id            String  @id @default(cuid())
  resumeBuildId String
  overrideText  String?
  sectionKey    String  @default("summary")
  orderIndex    Int     @default(0)
  included      Boolean @default(true)
}
""".strip()

VIEWS = """
editors:
  resume_final_edit:
    parent: ResumeBuild
    child: ResumeBuildItem
    fk: resumeBuildId
    edit_field: overrideText
    filter: { included: true }
    group_by: sectionKey
    order_by: orderIndex
    route: /resume-wizard/{id}/edit
    label: Make final edits
""".strip()


# --------------------------------------------------------------------------- #
# FR-ED-1/2 — manifest parse
# --------------------------------------------------------------------------- #

def test_parse_editors_basic():
    (spec,) = parse_editors(VIEWS, known_entities=frozenset({"ResumeBuild", "ResumeBuildItem"}))
    assert spec.name == "resume_final_edit"
    assert spec.parent == "ResumeBuild" and spec.child == "ResumeBuildItem"
    assert spec.fk == "resumeBuildId" and spec.edit_field == "overrideText"
    assert spec.filter_map == {"included": True}
    assert spec.group_by == "sectionKey" and spec.order_by == "orderIndex"
    assert spec.reset_to_default is True and spec.default_value == ""  # omitted → zero-seam


def test_parse_editors_absent_is_tolerant():
    assert parse_editors("flows: []\n") == ()
    assert parse_editors("") == ()
    assert parse_editors(None) == ()


def test_parse_editors_unknown_key_loud():
    bad = VIEWS + "\n    bogus: 1\n"
    with pytest.raises(ValueError, match="unknown keys"):
        parse_editors(bad, known_entities=frozenset({"ResumeBuild", "ResumeBuildItem"}))


def test_parse_editors_missing_required_loud():
    bad = "editors:\n  e:\n    parent: ResumeBuild\n    child: ResumeBuildItem\n    fk: resumeBuildId\n"
    with pytest.raises(ValueError, match="missing required `edit_field`|missing required `route`"):
        parse_editors(bad, known_entities=frozenset({"ResumeBuild", "ResumeBuildItem"}))


def test_parse_editors_unknown_entity_loud():
    with pytest.raises(ValueError, match="unknown entity"):
        parse_editors(VIEWS, known_entities=frozenset({"ResumeBuild"}))  # child missing


# --------------------------------------------------------------------------- #
# FR-ED-3 / OQ-8 — contract validation
# --------------------------------------------------------------------------- #

def _spec(**over) -> EditorSpec:
    base = dict(
        name="e", parent="ResumeBuild", child="ResumeBuildItem", fk="resumeBuildId",
        edit_field="overrideText", route="/x/{id}/edit",
    )
    base.update(over)
    return EditorSpec(**base)


@pytest.mark.parametrize("over,msg", [
    (dict(fk="nope"), "fk 'nope' is not a column"),
    (dict(edit_field="nope"), "edit_field 'nope' is not a column"),
    (dict(group_by="nope"), "group_by 'nope' is not a column"),
    (dict(order_by="nope"), "order_by 'nope' is not a column"),
    (dict(filter=(("nope", True),)), "filter column 'nope' is not a column"),
    (dict(parent="Nope"), "unknown parent entity"),
    (dict(child="Nope"), "unknown child entity"),
    (dict(route="/x/edit"), "exactly one `{id}`"),
    (dict(route="/x/{id}/{slug}"), "exactly one `{id}`"),
])
def test_validate_editor_loud(over, msg):
    schema = parse_prisma_schema(SCHEMA)
    with pytest.raises(ValueError, match=msg):
        _validate_editor(schema, _spec(**over))


def test_validate_editor_ui_route_warns():
    schema = parse_prisma_schema(SCHEMA)
    with pytest.warns(UserWarning, match="CRUD namespace"):
        _validate_editor(schema, _spec(route="/ui/{id}/edit"))


# --------------------------------------------------------------------------- #
# FR-ED-4..8 — generation + FR-ED-10 drift round-trip + $0 skip-hook
# --------------------------------------------------------------------------- #

def test_router_compiles_and_has_endpoints():
    (spec,) = parse_editors(VIEWS, known_entities=frozenset({"ResumeBuild", "ResumeBuildItem"}))
    r = render_editor_router(SCHEMA, VIEWS, spec)
    compile(r, "<editor>", "exec")
    assert '@editor_resume_final_edit_router.get("/resume-wizard/{id}/edit"' in r
    assert '@editor_resume_final_edit_router.post("/resume-wizard/{id}/edit"' in r
    assert "stmt = stmt.where(ResumeBuildItem.included.is_(True))" in r     # bool filter → .is_()
    assert "stmt = stmt.order_by(ResumeBuildItem.orderIndex)" in r          # order_by


def test_filter_bool_and_null_use_is_not_equals():
    """SQLAlchemy correctness: `== None`/`== True` are wrong/non-idiomatic; bool+None → `.is_()`."""
    schema = "model P { id String @id }\nmodel C { id String @id\n pId String\n txt String?\n flag Boolean\n}\n"
    views = (
        "editors:\n  e:\n    parent: P\n    child: C\n    fk: pId\n    edit_field: txt\n"
        "    filter: { flag: false, txt: null }\n    route: /e/{id}/edit\n"
    )
    (spec,) = parse_editors(views, known_entities=frozenset({"P", "C"}))
    r = render_editor_router(schema, views, spec)
    assert "C.flag.is_(False)" in r and "C.txt.is_(None)" in r
    assert "== None" not in r and "== True" not in r and "== False" not in r


def test_editor_check_round_trip_and_skip_hook():
    files = dict(render_editors(SCHEMA, VIEWS))
    assert set(files) == {
        "app/editors/resume_final_edit.py",
        "app/templates/editors/resume_final_edit/form.html",
        "app/editors/__init__.py",
    }
    for rel, content in files.items():
        assert check_drift(SCHEMA, content, forms_text=VIEWS).status == "in_sync", rel
        assert owned_file_in_sync(SCHEMA, content, views_text=VIEWS) is True, rel


def test_editor_artifacts_are_header_bearing():
    files = dict(render_editors(SCHEMA, VIEWS))
    kinds = {rel: embedded_artifact_kind(c) for rel, c in files.items()}
    assert kinds["app/editors/resume_final_edit.py"] == "fastapi-editor"
    assert kinds["app/templates/editors/resume_final_edit/form.html"] == "editor-form"
    assert kinds["app/editors/__init__.py"] == "editor-aggregator"
    assert all(is_owned_generated_file(c) for c in files.values())


def test_orphan_editor_drifts_not_crashes():
    rel, content = render_editors(SCHEMA, VIEWS)[0]  # the router
    res = check_drift(SCHEMA, content, forms_text="editors: {}\n")
    assert res.status in {"stale", "tampered"}  # drift (exit 1), deterministic, no exception


def test_inert_without_editors_section():
    assert render_editors(SCHEMA, "filters:\n  ResumeBuildItem:\n    facets: [sectionKey]\n") == []


def test_main_mount_block_is_static_literal_byte_identical():
    """FR-ED-13/R1-S5: render_main is schema-only; the editor mount block must not vary by manifest."""
    a = render_main(SCHEMA)
    b = render_main(SCHEMA)
    assert a == b
    assert "from .editors import editor_routers" in a
    assert "for _editor_router in editor_routers:" in a
    compile(a, "<main>", "exec")


def test_omitted_default_value_is_zero_seam():
    """FR-ED-9/R1-F7: no default_value → no resolver import; default mirror is raw edit_field."""
    views = VIEWS.replace("    label: Make final edits", "").replace(
        "    route: /resume-wizard/{id}/edit", "    route: /rw/{id}/edit"
    )
    (spec,) = parse_editors(views, known_entities=frozenset({"ResumeBuild", "ResumeBuildItem"}))
    r = render_editor_router(SCHEMA, views, spec)
    assert "from app.editors.resolvers import" not in r
    assert "_resolve_default = None" in r


# --------------------------------------------------------------------------- #
# FR-ED-5/6/12/14 — runtime: dirty-detection, reset, anti-IDOR, field-scope
# --------------------------------------------------------------------------- #

def _purge():
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]


def test_editor_runtime_dirty_reset_and_allowlist(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    sqlmodel = pytest.importorskip("sqlmodel")
    from startd8.backend_codegen import render_backend

    def _drop():
        md = sqlmodel.SQLModel.metadata
        for t in ("resumebuild", "resumebuilditem"):
            tbl = md.tables.get(t)
            if tbl is not None:
                md.remove(tbl)

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
        main = importlib.import_module("app.main")
        db = importlib.import_module("app.db")
        tables = importlib.import_module("app.tables")
        from fastapi.testclient import TestClient
        from sqlmodel import Session

        db.init_db()  # create tables before seeding (lifespan would, but we seed pre-TestClient)
        with Session(db.engine) as s:
            parent = tables.ResumeBuild()
            s.add(parent)
            s.commit()
            s.refresh(parent)
            pid = parent.id
            kept, changed, excluded = (
                tables.ResumeBuildItem(resumeBuildId=pid, sectionKey="a", orderIndex=0, included=True),
                tables.ResumeBuildItem(resumeBuildId=pid, sectionKey="a", orderIndex=1, included=True),
                tables.ResumeBuildItem(resumeBuildId=pid, sectionKey="a", orderIndex=2, included=False),
            )
            for it in (kept, changed, excluded):
                s.add(it)
            s.commit()
            for it in (kept, changed, excluded):
                s.refresh(it)
            kept_id, changed_id, excl_id = kept.id, changed.id, excluded.id

        def _override(item_id):
            with Session(db.engine) as s:
                return s.get(tables.ResumeBuildItem, item_id).overrideText

        with TestClient(main.app, follow_redirects=False) as c:
            # GET renders only the two included children (excluded filtered out)
            page = c.get(f"/resume-wizard/{pid}/edit")
            assert page.status_code == 200
            assert f'name="item-{kept_id}"' in page.text
            assert f'name="item-{changed_id}"' in page.text
            assert f'name="item-{excl_id}"' not in page.text  # FR-ED-4 filter

            # POST: kept unchanged (== mirror ""), changed → "Polished".
            # Also attempt IDOR (excluded id) + mass-assign (item-<id>-sectionKey) — both must be ignored.
            resp = c.post(f"/resume-wizard/{pid}/edit", data={
                f"item-{kept_id}": "", f"default-{kept_id}": "",
                f"item-{changed_id}": "Polished", f"default-{changed_id}": "",
                f"item-{excl_id}": "HACK", f"default-{excl_id}": "",          # not in editable set → ignored
                f"item-{changed_id}-sectionKey": "HACKED",                    # field-scope → ignored
            })
            assert resp.status_code == 303
            assert _override(kept_id) is None            # unchanged → stays NULL (no materialization)
            assert _override(changed_id) == "Polished"   # genuinely changed → stored
            assert _override(excl_id) is None            # IDOR ignored
            with Session(db.engine) as s:
                assert s.get(tables.ResumeBuildItem, changed_id).sectionKey == "a"  # mass-assign ignored

            # Reset: clear the changed one → empty != mirror "Polished"... use the now-current mirror.
            resp2 = c.post(f"/resume-wizard/{pid}/edit", data={
                f"item-{changed_id}": "", f"default-{changed_id}": "Polished",
            })
            assert resp2.status_code == 303
            assert _override(changed_id) is None         # empty + reset_to_default → NULL
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        _purge()
        _drop()
