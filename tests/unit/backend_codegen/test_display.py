"""Presentation/display layer — `display.yaml` structure (FR-DM, increment 1).

Per-entity list columns/labels/order + detail sections + row label_field, opt-in. Stops generated
screens leaking system ids as labels. (Composite-view FK resolution is increment 2.)
"""

from __future__ import annotations

import importlib
import sys

import pytest

from startd8.backend_codegen import check_drift, render_backend
from startd8.backend_codegen.display_manifest import EntityDisplay, parse_display
from startd8.backend_codegen.htmx_generator import (
    render_detail_template,
    render_list_template,
    render_row_template,
)
from startd8.languages.prisma_parser import parse_prisma_schema

pytestmark = pytest.mark.unit

SCHEMA = """
model TargetRole {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  createdAt DateTime @default(now())
  name      String
  industry  String?
  notes     String?
}
""".strip()

DISPLAY = """
entities:
  TargetRole:
    title: Target Roles
    label_field: name
    columns:
      - {field: name, label: Role}
      - {field: industry, format: badge}
    hidden_fields: [ownerId, createdAt]
    sections:
      - {title: Basics, fields: [name, industry]}
      - {title: Notes, fields: [notes]}
""".strip()


def _disp():
    return parse_display(DISPLAY, parse_prisma_schema(SCHEMA))[0]["TargetRole"]


# --------------------------------------------------------------------------- #
# FR-DM-1 parser
# --------------------------------------------------------------------------- #

def test_parse_display():
    ed = _disp()
    assert ed.title == "Target Roles" and ed.label_field == "name"
    assert [c.field for c in ed.columns] == ["name", "industry"]
    assert ed.columns[1].format == "badge"
    assert ed.hidden_fields == ("ownerId", "createdAt")
    assert [s.title for s in ed.sections] == ["Basics", "Notes"]


def test_parse_display_unknown_field_fails():
    bad = "entities:\n  TargetRole:\n    columns:\n      - {field: nope}\n"
    with pytest.raises(ValueError, match="unknown field 'nope'"):
        parse_display(bad, parse_prisma_schema(SCHEMA))


def test_parse_display_bad_format_fails():
    bad = "entities:\n  TargetRole:\n    columns:\n      - {field: name, format: rainbow}\n"
    with pytest.raises(ValueError, match="format"):
        parse_display(bad, parse_prisma_schema(SCHEMA))


def test_parse_display_unknown_entity_fails():
    with pytest.raises(ValueError, match="unknown entity"):
        parse_display("entities:\n  Nope: {}\n", parse_prisma_schema(SCHEMA))


# --------------------------------------------------------------------------- #
# FR-DM-2/3/5 templates
# --------------------------------------------------------------------------- #

def test_list_uses_columns_labels_and_label_field():
    ed = _disp()
    lst = render_list_template(SCHEMA, "prisma/schema.prisma", "TargetRole", None, ed)
    assert "<th>Role</th>" in lst and "<th>industry</th>" in lst   # declared label + order
    assert "<th>id</th>" not in lst                                # system col not shown
    assert "<h1>Target Roles</h1>" in lst                          # display title
    row = render_row_template(SCHEMA, "prisma/schema.prisma", "TargetRole", ed)
    assert '<span class="badge">{{ item.industry }}</span>' in row  # FR-DM-5 badge format
    assert "{{ item.name or 'view' }}" in row                       # label_field as the link text
    assert "item.ownerId" not in row                                # hidden / not a column


def test_detail_groups_into_sections():
    detail = render_detail_template(SCHEMA, "prisma/schema.prisma", "TargetRole", _disp())
    assert "<h2>Basics</h2>" in detail and "<h2>Notes</h2>" in detail
    assert "<h1>Target Roles</h1>" in detail
    assert detail.index("Basics") < detail.index("Notes")          # declared order


def test_unconfigured_entity_is_byte_identical():
    # no-display renders deterministically (None == None). FR-DM-7: the zero-config default now hides
    # id + provenance (no manifest needed) and shows domain fields.
    a = render_list_template(SCHEMA, "prisma/schema.prisma", "TargetRole")
    b = render_list_template(SCHEMA, "prisma/schema.prisma", "TargetRole", None, None)
    assert a == b
    assert "<th>id</th>" not in a and "<th>ownerId</th>" not in a   # FR-DM-7: system cols hidden
    assert "<th>name</th>" in a                                     # domain field shown


# --------------------------------------------------------------------------- #
# FR-DM-4 wiring + drift consistency (the --check false-flag fix)
# --------------------------------------------------------------------------- #

def test_zero_config_defaults_hide_system_fields_and_label_by_heuristic():
    """FR-DM-7: with NO display.yaml at all, list/detail drop id + provenance/timestamps and the row
    link reads as the heuristic label (name/title/...) — so a zero-config app never leaks ids."""
    files = dict(render_backend(SCHEMA))                  # no display_text
    lst = files["app/templates/targetrole/list.html"]
    assert "<th>id</th>" not in lst and "<th>ownerId</th>" not in lst and "<th>createdAt</th>" not in lst
    assert "<th>name</th>" in lst and "<th>industry</th>" in lst
    row = files["app/templates/targetrole/_row.html"]
    assert "<td>{{ item.id }}</td>" not in row            # no id data cell
    assert "{{ item.name or 'view' }}" in row             # heuristic label on the link
    detail = files["app/templates/targetrole/detail.html"]
    assert "<dt>id</dt>" not in detail and "<dt>ownerId</dt>" not in detail
    assert "<dt>name</dt>" in detail


def test_display_threads_and_check_is_consistent():
    files = dict(render_backend(SCHEMA, display_text=DISPLAY))
    lst = files["app/templates/targetrole/list.html"]
    assert "<th>Role</th>" in lst                                   # --display threaded end-to-end
    # the SAME display_text re-render is in-sync (no false drift); a different one drifts
    assert check_drift(SCHEMA, lst, display_text=DISPLAY).status == "in_sync"
    assert check_drift(SCHEMA, lst, display_text=None).status != "in_sync"  # default ≠ configured


# --------------------------------------------------------------------------- #
# FR-DM runtime — a configured list/detail actually renders
# --------------------------------------------------------------------------- #

def _purge():
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]


def test_display_renders_at_runtime(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    sqlmodel = pytest.importorskip("sqlmodel")

    def _drop():
        md = sqlmodel.SQLModel.metadata
        t = md.tables.get("targetrole")
        if t is not None:
            md.remove(t)

    for rel, content in render_backend(SCHEMA, display_text=DISPLAY):
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

        with TestClient(main.app) as c:
            with Session(db.engine) as s:
                s.add(tables.TargetRole(name="Staff Engineer", industry="fintech", notes="x"))
                s.commit()
            lst = c.get("/ui/targetrole")
            assert lst.status_code == 200
            assert "<th>Role</th>" in lst.text and "Staff Engineer" in lst.text
            assert "neil" not in lst.text  # (no id leakage in the configured columns)
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        _purge()
        _drop()
