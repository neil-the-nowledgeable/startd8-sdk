"""Step 5 (FR-4): deterministic HTMX/Jinja UI — templates + web.py routes + inline validation.

Asserts structure (CRUD vocabulary + inline-validation hooks + field→widget mapping), valid Python
for web.py, optional Jinja parse for templates (when jinja2 is present — it's a generated-app dep,
not an SDK dep), and that every artifact is drift-recognized in-sync via the entity-aware dispatch.
"""

from __future__ import annotations

import pytest

from startd8.backend_codegen import owned_file_in_sync, render_ui, render_web
from startd8.backend_codegen.drift import embedded_artifact_kind, embedded_entity
from startd8.backend_codegen.htmx_generator import (
    render_form_template,
    render_list_template,
)
from startd8.contractors import deterministic_providers as dp
from startd8.contractors.deterministic_providers import (
    ProviderContext,
    is_deterministically_provided,
)
from startd8.backend_codegen import PydanticSQLModelProvider

pytestmark = pytest.mark.unit

SCHEMA = """\
enum Confidence {
  draft
  confirmed
}

model ProofPoint {
  id         String     @id
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


@pytest.fixture(autouse=True)
def _clean_registry():
    dp.clear_providers()
    dp._DISCOVERED = True
    yield
    dp.clear_providers()


def test_web_py_routes_compile_and_cover_crud_and_validation():
    web = render_web(SCHEMA)
    compile(web, "<web>", "exec")
    # canonical imports
    assert "from .db import get_session" in web
    assert "from .tables import Metric, ProofPoint" in web
    assert 'Jinja2Templates(directory=str(Path(__file__).parent / "templates"))' in web
    # CRUD + inline-validation routes for an entity with a PK
    for route in (
        '@web_router.get("/ui/proofpoint"',
        '@web_router.get("/ui/proofpoint/new"',
        '@web_router.post("/ui/proofpoint/validate"',
        '@web_router.post("/ui/proofpoint"',
        '@web_router.get("/ui/proofpoint/{id}"',
        '@web_router.get("/ui/proofpoint/{id}/edit"',
        '@web_router.post("/ui/proofpoint/{id}"',
        '@web_router.post("/ui/proofpoint/{id}/delete"',
    ):
        assert route in web, route
    # deterministic per-entity validation rules
    assert "_proofpoint_rules = {" in web
    assert '"confidence": ("select", True)' in web
    assert '"tags": ("text-list", False)' in web
    assert '"metricId": ("text", False)' in web  # optional FK scalar


def test_form_template_widgets_and_inline_validation():
    form = render_form_template(SCHEMA, "prisma/schema.prisma", "ProofPoint")
    # enum -> select with options
    assert '<select name="confidence"' in form
    assert '<option value="draft"' in form and '<option value="confirmed"' in form
    # number widget for the Metric.value lives in Metric's form; here check text + required
    assert '<input type="text" name="result"' in form
    assert " required" in form  # result is required
    # inline-validation hooks on every field
    assert 'hx-post="/ui/proofpoint/validate"' in form
    assert 'hx-trigger="blur changed"' in form
    assert 'id="err-result"' in form
    # create-vs-edit action switch
    assert "{% if item %}/ui/proofpoint/" in form


def test_number_widget_for_float_field():
    form = render_form_template(SCHEMA, "prisma/schema.prisma", "Metric")
    assert '<input type="number" step="any" name="value"' in form


def test_list_template_has_rows_and_delete():
    lst = render_list_template(SCHEMA, "prisma/schema.prisma", "ProofPoint")
    assert "{% for item in items %}" in lst
    assert "<td>{{ item.result }}</td>" in lst
    assert 'hx-post="/ui/proofpoint/{{ item.id }}/delete"' in lst
    assert 'hx-swap="outerHTML"' in lst


def test_all_ui_artifacts_in_sync_and_kind_tagged():
    arts = render_ui(SCHEMA)
    paths = [p for p, _ in arts]
    assert "app/web.py" in paths
    assert "app/templates/base.html" in paths
    assert "app/templates/proofpoint/form.html" in paths
    for _path, content in arts:
        assert owned_file_in_sync(SCHEMA, content) is True
        assert embedded_artifact_kind(content) is not None


def test_per_entity_templates_carry_entity_tag():
    arts = dict(render_ui(SCHEMA))
    pp_list = arts["app/templates/proofpoint/list.html"]
    assert embedded_entity(pp_list) == "ProofPoint"
    # template provenance lives inside a Jinja comment so it stays invisible at render time
    assert pp_list.startswith("{#")


def test_jinja_templates_parse_if_available():
    try:
        import jinja2
    except ImportError:
        pytest.skip("jinja2 is a generated-app dep, not installed in the SDK env")
    env = jinja2.Environment()
    for path, content in render_ui(SCHEMA):
        if path.endswith(".html"):
            env.parse(content)  # raises TemplateSyntaxError on malformed Jinja


def test_template_provided_via_registry(tmp_path):
    p = tmp_path / "prisma" / "schema.prisma"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(SCHEMA, encoding="utf-8")
    dp.register_provider(PydanticSQLModelProvider())
    ctx = ProviderContext(
        project_root=tmp_path, source_anchors=("prisma/schema.prisma",)
    )
    form = render_form_template(SCHEMA, "prisma/schema.prisma", "ProofPoint")
    out = tmp_path / "app" / "templates" / "proofpoint" / "form.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(form, encoding="utf-8")
    # the one provider $0.00-recognizes a generated .html template too (kind+entity dispatch)
    assert is_deterministically_provided(out, form, ctx) is True
    assert (
        is_deterministically_provided(out, form.replace("<h1>", "<h2>", 1), ctx)
        is False
    )
