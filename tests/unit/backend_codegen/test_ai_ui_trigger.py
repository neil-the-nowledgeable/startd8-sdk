"""Generated UI trigger to run an AI pass — FR-AIT (strtd8 SDK_QUICK_WINS #3).

A pass opts into a detail-page 'Run {pass}' button via `trigger:` in ai_passes.yaml; the AI layer
emits a form-POST route (`app/ai/ui.py`) + a per-entity partial, included by the detail template
through a tolerant `{% include ... ignore missing %}` seam so no-trigger projects are untouched.
"""

from __future__ import annotations

import importlib
import sys

import pytest

from startd8.backend_codegen.ai_layer import (
    PassTrigger,
    parse_ai_passes,
    render_ai_layer,
    render_ai_trigger_partials,
    render_ai_ui_routes,
)
from startd8.backend_codegen.crud_generator import render_main
from startd8.backend_codegen.htmx_generator import render_detail_template

pytestmark = pytest.mark.unit

SCHEMA = """
model ImportedDocument {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(true)
  rawText   String
}

model ProofPoint {
  id               String  @id @default(cuid())
  ownerId          String  @default("local")
  source           String  @default("user")
  confirmed        Boolean @default(false)
  title            String?
  sourceDocumentId String?
}

model AiCall {
  id        String  @id @default(cuid())
  ownerId   String  @default("local")
  source    String  @default("user")
  confirmed Boolean @default(true)
  purpose   String?
}
""".strip()

MANIFEST = """
passes:
  - name: extract_document
    output_entities: [ProofPoint]
    route_path: /extract-document
    prompt: prompts/extract_document.md
    source_binding: sourceDocumentId
    trigger:
      entity: ImportedDocument
      text_field: rawText
      label: Extract proof points
""".strip()

NO_TRIGGER_MANIFEST = """
passes:
  - name: extract_document
    output_entities: [ProofPoint]
    route_path: /extract-document
    prompt: prompts/extract_document.md
""".strip()


# --------------------------------------------------------------------------- #
# FR-AIT-1 manifest
# --------------------------------------------------------------------------- #

def test_trigger_parses():
    ps = parse_ai_passes(MANIFEST)[0]
    assert ps.trigger == PassTrigger("ImportedDocument", "rawText", "Extract proof points")


def test_trigger_label_defaults_to_run_name():
    m = MANIFEST.replace("\n      label: Extract proof points", "")
    assert parse_ai_passes(m)[0].trigger.label == "Run extract_document"


def test_trigger_missing_text_field_fails_loud():
    m = MANIFEST.replace("      text_field: rawText\n", "")
    with pytest.raises(ValueError, match="missing required `text_field`"):
        parse_ai_passes(m)


# --------------------------------------------------------------------------- #
# FR-AIT-2 route
# --------------------------------------------------------------------------- #

def test_ui_route_renders_and_compiles():
    ui = render_ai_ui_routes(SCHEMA, MANIFEST, "")
    compile(ui, "<ui>", "exec")
    assert 'ai_ui_router = APIRouter(tags=["ai-ui"])' in ui
    assert '@ai_ui_router.post("/ui/importeddocument/{importeddocument_id}/run-extract_document")' in ui
    assert 'getattr(item, "rawText", "")' in ui
    # source-bound ⇒ threads source_id; degrades to a flash, redirects (PRG, never a crash)
    assert "extract_document(text, session, source_id=importeddocument_id)" in ui
    assert "except AIUnavailableError:" in ui
    assert 'RedirectResponse(f"/ui/importeddocument/{importeddocument_id}?ai={flash}", status_code=303)' in ui


# --------------------------------------------------------------------------- #
# FR-AIT-3 partial + detail-template seam
# --------------------------------------------------------------------------- #

def test_trigger_partial_has_form_and_flash():
    partials = dict(render_ai_trigger_partials(SCHEMA, MANIFEST))
    html = partials["app/templates/importeddocument/_ai_triggers.html"]
    assert '<form method="post" action="/ui/importeddocument/{{ item.id }}/run-extract_document">' in html
    assert "<button type=\"submit\">Extract proof points</button>" in html
    assert "request.query_params.get('ai') == 'ok'" in html
    assert "request.query_params.get('ai') == 'unavailable'" in html


def test_detail_template_carries_tolerant_include():
    detail = render_detail_template(SCHEMA, "prisma/schema.prisma", "ImportedDocument")
    assert '{% include "importeddocument/_ai_triggers.html" ignore missing %}' in detail


# --------------------------------------------------------------------------- #
# FR-AIT-4 mount + FR-AIT-5 inert when no triggers
# --------------------------------------------------------------------------- #

def test_main_mounts_ai_ui_router_tolerantly():
    main = render_main(SCHEMA)
    assert "from .ai.ui import ai_ui_router" in main
    assert "app.include_router(ai_ui_router)" in main
    compile(main, "<main>", "exec")


def test_layer_emits_ui_only_when_triggered():
    with_trigger = dict(render_ai_layer(SCHEMA, MANIFEST, ""))
    assert "app/ai/ui.py" in with_trigger
    assert "app/templates/importeddocument/_ai_triggers.html" in with_trigger

    without = dict(render_ai_layer(SCHEMA, NO_TRIGGER_MANIFEST, ""))
    assert "app/ai/ui.py" not in without
    assert not any(k.endswith("_ai_triggers.html") for k in without)


# --------------------------------------------------------------------------- #
# FR-AIT-2 runtime — the button's route actually runs the pass + redirects (no crash)
# --------------------------------------------------------------------------- #

_MY_TABLES = {"importeddocument", "proofpoint", "aicall"}


def _purge_app():
    for m in [m for m in sys.modules if m == "app" or m.startswith("app.")]:
        del sys.modules[m]


def test_trigger_route_runs_pass_and_redirects(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    sqlmodel = pytest.importorskip("sqlmodel")
    from startd8.backend_codegen import render_backend

    def _drop():
        md = sqlmodel.SQLModel.metadata
        for n in list(_MY_TABLES):
            t = md.tables.get(n)
            if t is not None:
                md.remove(t)

    for rel, content in render_backend(SCHEMA, manifest_text=MANIFEST, human_inputs_text=""):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'app.db'}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")     # past the keyless precheck
    sys.path.insert(0, str(tmp_path))
    _purge_app()
    _drop()
    try:
        importlib.import_module("app.main")
        server = importlib.import_module("app.server")
        db = importlib.import_module("app.db")
        tables = importlib.import_module("app.tables")
        ai_service = importlib.import_module("app.ai.service")
        from fastapi.testclient import TestClient
        from sqlmodel import Session
        from startd8.models import GenerateResult

        class _FakeAgent:
            def generate_structured(self, prompt, output_schema, **kw):
                # source-bound pass → a single entity edge (provenance omitted, stamped by the harness)
                return output_schema(title="Led a team"), GenerateResult("{}", 1, None)

        monkeypatch.setattr(ai_service, "resolve_agent_spec", lambda *a, **k: _FakeAgent())

        with TestClient(server.app, follow_redirects=False) as c:
            with Session(db.engine) as s:
                doc = tables.ImportedDocument(rawText="A 12-person team, $2M delivered")
                s.add(doc)
                s.commit()
                s.refresh(doc)
                doc_id = doc.id
            resp = c.post(f"/ui/importeddocument/{doc_id}/run-extract_document")
            assert resp.status_code == 303
            assert resp.headers["location"] == f"/ui/importeddocument/{doc_id}?ai=ok"

        # provider failure at call time → ai=unavailable, still a redirect (app stays up)
        monkeypatch.setattr(ai_service, "resolve_agent_spec",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        with TestClient(server.app, follow_redirects=False) as c:
            resp = c.post(f"/ui/importeddocument/{doc_id}/run-extract_document")
            assert resp.status_code == 303 and resp.headers["location"].endswith("?ai=unavailable")
    finally:
        if str(tmp_path) in sys.path:
            sys.path.remove(str(tmp_path))
        _purge_app()
        _drop()
