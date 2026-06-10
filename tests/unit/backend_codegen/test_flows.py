"""Wizard step-state primitive — P0-1 (shared-floor: StartDate wizard + navig8 tree traversal).

A `flows:` section in views.yaml generates a start/resume/advance/back router over a draft entity's
step pointer; per-step content is an app-owned tolerant include seam. The SDK owns the navigation/state.
"""

from __future__ import annotations

import importlib
import sys

import pytest

from startd8.backend_codegen.flow_generator import (
    render_flow_router,
    render_flow_shell,
    render_flows,
)
from startd8.backend_codegen.flows_manifest import FlowSpec, parse_flows
from startd8.backend_codegen.crud_generator import render_main

pytestmark = pytest.mark.unit

SCHEMA = """
model ResumeBuild {
  id          String  @id @default(cuid())
  ownerId     String  @default("local")
  currentStep String  @default("target")
  title       String?
}
""".strip()

VIEWS = """
flows:
  - name: resume_builder
    draft_entity: ResumeBuild
    step_field: currentStep
    steps: [target, competencies, review]
    on_finish: build_metadata_json
""".strip()


# --------------------------------------------------------------------------- #
# FR-WZ-1 manifest
# --------------------------------------------------------------------------- #

def test_parse_flows():
    flows = parse_flows(VIEWS, known_entities=frozenset({"ResumeBuild"}))
    assert flows == (FlowSpec("resume_builder", "ResumeBuild", "currentStep",
                              ("target", "competencies", "review"), "build_metadata_json"),)


def test_parse_flows_unknown_entity_fails():
    with pytest.raises(ValueError, match="unknown entity"):
        parse_flows(VIEWS, known_entities=frozenset({"Other"}))


def test_parse_flows_bad_steps_fail():
    empty = "flows:\n  - name: f\n    draft_entity: ResumeBuild\n    step_field: currentStep\n    steps: []\n"
    with pytest.raises(ValueError, match="steps"):                    # empty → loud
        parse_flows(empty, known_entities=frozenset({"ResumeBuild"}))
    nonstr = "flows:\n  - name: f\n    draft_entity: ResumeBuild\n    step_field: currentStep\n    steps: [1, 2]\n"
    with pytest.raises(ValueError, match="non-empty list of strings"):  # non-string → loud
        parse_flows(nonstr, known_entities=frozenset({"ResumeBuild"}))


def test_unknown_step_field_fails_at_render():
    bad = VIEWS.replace("step_field: currentStep", "step_field: nope")
    flow = parse_flows(bad, known_entities=frozenset({"ResumeBuild"}))[0]
    with pytest.raises(ValueError, match="not a column"):
        render_flow_router(SCHEMA, bad, flow)


# --------------------------------------------------------------------------- #
# FR-WZ-2/3/4 router + shell
# --------------------------------------------------------------------------- #

def test_router_renders_compiles_and_has_nav():
    flow = parse_flows(VIEWS, known_entities=frozenset({"ResumeBuild"}))[0]
    r = render_flow_router(SCHEMA, VIEWS, flow)
    compile(r, "<flow>", "exec")
    assert "_STEPS = ['target', 'competencies', 'review']" in r
    assert '@flow_resume_builder_router.post("/start")' in r
    assert '@flow_resume_builder_router.get("/{draft_id}"' in r
    assert '@flow_resume_builder_router.post("/{draft_id}/advance")' in r
    assert '@flow_resume_builder_router.post("/{draft_id}/back")' in r
    assert "from app.flows.finishers import build_metadata_json as _on_finish" in r  # tolerant hook
    assert "if _on_finish is not None:" in r


def test_shell_has_dynamic_seam_and_controls():
    flow = parse_flows(VIEWS, known_entities=frozenset({"ResumeBuild"}))[0]
    html = render_flow_shell(VIEWS, flow)
    assert '{% include "flows/resume_builder/_step_" ~ item.currentStep ~ ".html" ignore missing %}' in html
    assert '/flow/resume_builder/{{ item.id }}/back' in html
    assert '/flow/resume_builder/{{ item.id }}/advance' in html


def test_render_flows_aggregator_and_inert_without_flows():
    files = dict(render_flows(SCHEMA, VIEWS))
    assert "app/flows/resume_builder.py" in files
    assert "app/templates/flows/resume_builder/shell.html" in files
    agg = files["app/flows/__init__.py"]
    assert "flow_routers = [flow_resume_builder_router]" in agg
    assert render_flows(SCHEMA, "") == []                       # no flows: → nothing


def test_main_mounts_flow_routers_tolerantly():
    main = render_main(SCHEMA)
    assert "from .flows import flow_routers" in main
    assert "app.include_router(_flow_router)" in main
    compile(main, "<main>", "exec")


# --------------------------------------------------------------------------- #
# FR-WZ-2 runtime — start → advance → back actually persist + resume
# --------------------------------------------------------------------------- #

def _purge():
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]


def test_flow_runtime_start_advance_back(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    sqlmodel = pytest.importorskip("sqlmodel")
    from startd8.backend_codegen import render_backend

    def _drop():
        md = sqlmodel.SQLModel.metadata
        t = md.tables.get("resumebuild")
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
        main = importlib.import_module("app.main")
        db = importlib.import_module("app.db")
        tables = importlib.import_module("app.tables")
        from fastapi.testclient import TestClient
        from sqlmodel import Session

        with TestClient(main.app, follow_redirects=False) as c:
            start = c.post("/flow/resume_builder/start")
            assert start.status_code == 303
            loc = start.headers["location"]              # /flow/resume_builder/<id>
            draft_id = loc.rsplit("/", 1)[-1]

            def _step():
                with Session(db.engine) as s:
                    return s.get(tables.ResumeBuild, draft_id).currentStep

            assert _step() == "target"                    # created at step[0]
            c.post(f"/flow/resume_builder/{draft_id}/advance")
            assert _step() == "competencies"              # advanced + persisted
            c.post(f"/flow/resume_builder/{draft_id}/advance")
            assert _step() == "review"
            c.post(f"/flow/resume_builder/{draft_id}/back")
            assert _step() == "competencies"              # back + persisted
            # past-last advance: go to review then advance → finish redirect to the draft detail
            c.post(f"/flow/resume_builder/{draft_id}/advance")  # → review
            fin = c.post(f"/flow/resume_builder/{draft_id}/advance")  # past last → finish
            assert fin.status_code == 303
            assert fin.headers["location"] == f"/ui/resumebuild/{draft_id}"
            # resume: GET renders the shell at the persisted step
            r = c.get(f"/flow/resume_builder/{draft_id}")
            assert r.status_code == 200 and "Step:" in r.text
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        _purge()
        _drop()
