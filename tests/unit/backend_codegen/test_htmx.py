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
    # modern Starlette signature: request FIRST (runtime-test fix; old (name, ctx) form crashed)
    assert (
        'templates.TemplateResponse(\n        request, "proofpoint/list.html", ctx'
        in web
    )
    assert '"request":' not in web  # request must NOT be passed inside the context dict
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


# Schema carrying the full provenance/timestamp set, to exercise FR-PG-5 omission.
PROV_SCHEMA = """\
model Profile {
  id        String   @id
  name      String
  title     String?
  ownerId   String
  source    String
  confirmed Boolean
  createdAt DateTime
  updatedAt DateTime
}
"""

_SYSTEM_FIELDS = ("id", "ownerId", "source", "confirmed", "createdAt", "updatedAt")


def test_form_omits_system_and_provenance_fields():
    form = render_form_template(PROV_SCHEMA, "prisma/schema.prisma", "Profile")
    # human-authored fields are present...
    assert '<label for="f-name">name</label>' in form
    assert '<label for="f-title">title</label>' in form
    # ...and every system/provenance/timestamp field is gone (FR-PG-5)
    for sysf in _SYSTEM_FIELDS:
        assert f'name="{sysf}"' not in form, sysf
        assert f'id="f-{sysf}"' not in form, sysf


def test_web_create_rules_exclude_system_fields():
    web = render_web(PROV_SCHEMA)
    compile(web, "<web>", "exec")
    assert '"name": ("text", True)' in web
    # the create/update/validate rule map must not carry system fields
    for sysf in _SYSTEM_FIELDS:
        assert f'"{sysf}":' not in web, sysf


def test_list_still_shows_system_fields_for_readonly_display():
    # FR-PG-5 is forms-only: read-only list/detail still surface createdAt etc.
    lst = render_list_template(PROV_SCHEMA, "prisma/schema.prisma", "Profile")
    assert "{{ item.createdAt }}" in lst
    assert "{{ item.id }}" in lst


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


# --------------------------------------------------------------------------- #
# Post-submit behavior (FORM_SUBMIT_BEHAVIOR_REQUIREMENTS.md FR-FS-1..10)
# --------------------------------------------------------------------------- #

FORMS = """\
views: []
forms:
  ProofPoint: { on_create: confirmation }
  Metric:     { on_create: form }
"""


def test_create_is_prg_303_to_detail_by_default():
    web = render_web(SCHEMA)
    # FR-FS-1/2: a real 303 (browsers ignore HX-Redirect on a plain form POST — blank page)
    assert "HX-Redirect" not in web
    assert "session.refresh(obj)" in web  # uniform PK recovery before the redirect
    assert (
        'return RedirectResponse(f"/ui/proofpoint/{obj.id}?created=1", status_code=303)'
        in web
    )
    # FR-FS-6: update PRGs back to detail with the updated flash
    assert (
        'return RedirectResponse(f"/ui/proofpoint/{id}?updated=1", status_code=303)'
        in web
    )
    # routes pass the flash params through to the templates
    assert '"created": request.query_params.get("created")' in web
    assert '"updated": request.query_params.get("updated")' in web


def test_templates_carry_flash_banners():
    lst = render_list_template(SCHEMA, "prisma/schema.prisma", "ProofPoint")
    assert '{% if created %}<p class="flash">✓ ProofPoint stored.</p>{% endif %}' in lst
    form = render_form_template(SCHEMA, "prisma/schema.prisma", "ProofPoint")
    # form-mode banner carries the "view it" link (the echoed ?created=<pk>)
    assert (
        '{% if created %}<p class="flash">✓ ProofPoint stored.'
        ' <a href="/ui/proofpoint/{{ created }}">view it</a></p>{% endif %}'
    ) in form
    from startd8.backend_codegen.htmx_generator import render_detail_template

    detail = render_detail_template(SCHEMA, "prisma/schema.prisma", "ProofPoint")
    assert '{% if created %}<p class="flash">✓ ProofPoint stored.</p>{% endif %}' in detail
    assert '{% if updated %}<p class="flash">✓ ProofPoint updated.</p>{% endif %}' in detail


def test_list_highlights_new_row_and_base_has_styles():
    lst = render_list_template(SCHEMA, "prisma/schema.prisma", "ProofPoint")
    # ?created=<pk> (list mode) highlights the just-stored row
    assert '{% if created == item.id|string %} class="new-row"{% endif %}' in lst
    from startd8.backend_codegen.htmx_generator import render_base_template

    base = render_base_template(SCHEMA)
    assert "<style>" in base and "tr.new-row td" in base and ".flash" in base


def test_delete_swaps_in_a_flash_row():
    web = render_web(SCHEMA)
    # outerHTML swap replaces the row with a visible deleted confirmation (not an empty body)
    assert "✓ ProofPoint deleted." in web
    assert 'colspan="6"' in web  # ProofPoint: 5 display columns + 1 action column
    assert 'return HTMLResponse("")' not in web


def test_no_pk_form_has_no_view_link():
    form = render_form_template(NO_PK_SCHEMA, "prisma/schema.prisma", "Pair")
    assert "view it" not in form  # no-PK form mode echoes created=1, not a pk — no link


def test_on_create_modes_route_the_redirect():
    web = render_web(SCHEMA, forms_text=FORMS)
    compile(web, "<web>", "exec")
    # confirmation: 303 to the dedicated page + the extra GET route
    assert (
        'return RedirectResponse(f"/ui/proofpoint/{obj.id}/created", status_code=303)'
        in web
    )
    assert '@web_router.get("/ui/proofpoint/{id}/created"' in web
    # form: back to a fresh form, echoing the new pk (OQ-6)
    assert (
        'return RedirectResponse(f"/ui/metric/new?created={obj.id}", status_code=303)'
        in web
    )
    # 2-hash header: kind switches per dep-set (htmx-base/pages-base precedent)
    assert "# startd8-artifact: fastapi-web-forms" in web
    assert "# forms-sha256:" in web


def test_on_create_list_mode():
    forms = "forms:\n  ProofPoint: { on_create: list }\n"
    web = render_web(SCHEMA, forms_text=forms)
    assert (
        'return RedirectResponse(f"/ui/proofpoint?created={obj.id}", status_code=303)'
        in web
    )


def test_confirmation_emits_created_template_only_for_declared_entities():
    arts = dict(render_ui(SCHEMA, forms_text=FORMS))
    assert "app/templates/proofpoint/created.html" in arts
    assert "app/templates/metric/created.html" not in arts  # on_create: form — no page
    created = arts["app/templates/proofpoint/created.html"]
    assert embedded_artifact_kind(created) == "htmx-created"
    assert embedded_entity(created) == "ProofPoint"
    assert "✓ ProofPoint stored." in created
    for link in ("view</a>", "add another</a>", "back to list</a>"):
        assert link in created
    # without a manifest, no created.html anywhere
    assert "app/templates/proofpoint/created.html" not in dict(render_ui(SCHEMA))


def test_forms_artifacts_drift_in_sync_with_manifest():
    from startd8.backend_codegen import check_drift

    for _path, content in render_ui(SCHEMA, forms_text=FORMS):
        kind = embedded_artifact_kind(content)
        if kind in ("fastapi-web-forms", "htmx-created"):
            r = check_drift(SCHEMA, content, forms_text=FORMS)
            assert r.status == "in_sync", (kind, r.detail)
            # without the manifest the check degrades loudly, never to a false in-sync
            assert check_drift(SCHEMA, content).status == "error"
        else:
            assert owned_file_in_sync(SCHEMA, content) is True


def test_forms_manifest_fails_loud():
    from startd8.backend_codegen import parse_forms

    with pytest.raises(ValueError, match="unknown on_create"):
        parse_forms("forms:\n  ProofPoint: { on_create: detial }\n")
    with pytest.raises(ValueError, match="unknown keys"):
        parse_forms("forms:\n  ProofPoint: { on_creat: detail }\n")
    with pytest.raises(ValueError, match="unknown entity"):
        render_web(SCHEMA, forms_text="forms:\n  Nope: { on_create: list }\n")
    # tolerates a views-less manifest (parse_views requires >=1 view; this parser must not)
    assert parse_forms("forms:\n  ProofPoint: { on_create: list }\n") == {
        "ProofPoint": "list"
    }
    # absent section / absent manifest => defaults
    assert parse_forms("views: []\n") == {}
    assert parse_forms(None) == {}


NO_PK_SCHEMA = """\
model Pair {
  leftId  String
  rightId String

  @@id([leftId, rightId])
}
"""


def test_no_pk_falls_back_to_list():
    # FR-FS-8: no single-column PK -> no detail page; detail/confirmation fall back to list
    web = render_web(NO_PK_SCHEMA, forms_text="forms:\n  Pair: { on_create: confirmation }\n")
    compile(web, "<web>", "exec")
    assert "falls back to list (FR-FS-8)" in web
    assert 'return RedirectResponse("/ui/pair?created=1", status_code=303)' in web
    assert "/created" not in web  # no confirmation route without a by-id page


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
