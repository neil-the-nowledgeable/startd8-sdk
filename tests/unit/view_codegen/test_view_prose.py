"""View-prose (Phase 1: title/intro) — strict parse, untracked-fragment render, drift safety.

The load-bearing guarantees (VIEW_PROSE_PLAN R1-S4/S7, FR-PG-10/12):
- **byte-identical when absent** — no ``view_prose.yaml`` ⇒ identical to today, no fragments;
- **prose → untracked fragment + include** — owned template gets a content-independent ``{% include %}``;
- **the fragment is not an owned file** — the marker-absence gate (asserted directly, not just via e2e);
- **editing copy never trips ``--check``** — prose *content* never enters the owned template / hash;
- **presence is structural** — adding prose without threading it to the drift checker flags drift;
- **strict, loud-fail parse** — unknown/reserved keys, unknown views, model-export (no surface).
"""

from __future__ import annotations

import pytest

from startd8.view_codegen import (
    is_owned_view_file,
    parse_view_prose,
    render_view_prose_fragment,
    render_views,
    views_in_sync,
)
from startd8.view_codegen.view_prose import ViewProse

# Self-contained fixture (repo convention — each view test defines its own) covering the three
# Phase-1 archetypes that render an HTML page: model-compose (value_map), computed-panel, import-flow.
SCHEMA = """
model Capability {
  id      String @id @default(cuid())
  ownerId String @default("local")
  name    String
}

model CapabilityOutcome {
  id           String @id @default(cuid())
  ownerId      String @default("local")
  capabilityId String
  outcomeId    String
}
""".strip()

VIEWS = """
views:
  - name: value_map
    kind: detail-compose
    scope: model
    root: Capability
    relations:
      - { name: outcomes, from: CapabilityOutcome, fk: capabilityId }
  - name: completeness_panel
    kind: computed-panel
    compute: completeness
    route: /completeness
  - name: model_import
    kind: import-flow
    route: /import
""".strip()

_TMPL = "app/templates/views/value_map.html"
_FRAG = "app/templates/views/_value_map.prose.html"
_PROSE = """
value_map:
  title: "Your value map"
  intro: "How your **proof points** connect to capabilities."
completeness_panel:
  title: "How complete is your value model?"
"""


# --------------------------------------------------------------------------- #
# Parser (strict, loud-fail)
# --------------------------------------------------------------------------- #

def test_absent_manifest_is_empty():
    assert parse_view_prose(None) == {}
    assert parse_view_prose("") == {}
    assert parse_view_prose("\n\n") == {}


def test_parse_happy_path():
    out = parse_view_prose(_PROSE)
    assert out["value_map"] == ViewProse(title="Your value map",
                                         intro="How your **proof points** connect to capabilities.")
    assert out["completeness_panel"].title == "How complete is your value model?"
    assert out["completeness_panel"].intro is None


def test_entry_with_no_recognized_values_is_inert():
    # An empty mapping yields no ViewProse → no fragment → byte-identical output.
    assert parse_view_prose("value_map: {}") == {}


def test_unknown_key_loud_fails():
    with pytest.raises(ValueError, match="unknown keys"):
        parse_view_prose("value_map:\n  bogus: x\n")


# (No keys remain reserved at the parser level — `empty`/`success`/`error`/`controls` all ship; their
#  archetype validity is enforced in render_views. Unknown keys still loud-fail, tested above.)


def test_unknown_view_loud_fails_when_gated():
    with pytest.raises(ValueError, match="unknown view"):
        parse_view_prose("ghost:\n  title: x\n", known_views=frozenset({"value_map"}))


def test_non_string_value_loud_fails():
    with pytest.raises(ValueError, match="must be a string"):
        parse_view_prose("value_map:\n  title: 123\n")


def test_non_mapping_root_loud_fails():
    with pytest.raises(ValueError, match="must be a mapping"):
        parse_view_prose("- just\n- a\n- list\n")


# --------------------------------------------------------------------------- #
# Fragment render (escaping + markdown)
# --------------------------------------------------------------------------- #

def test_fragment_escapes_title_and_renders_intro_markdown():
    frag = render_view_prose_fragment(ViewProse(title="A & B <ok>", intro="**bold**"), "fallback")
    assert "<h1>A &amp; B &lt;ok&gt;</h1>" in frag        # title is escaped literal
    assert "<strong>bold</strong>" in frag                # intro is markdown→HTML
    assert frag.endswith("\n")
    assert "# startd8-artifact" not in frag               # no provenance header (untracked)


def test_fragment_falls_back_to_machine_name_without_title():
    frag = render_view_prose_fragment(ViewProse(intro="hi"), "value_map")
    assert "<h1>value_map</h1>" in frag


# --------------------------------------------------------------------------- #
# render_views integration — the byte-identical / fragment / include guarantees
# --------------------------------------------------------------------------- #

def test_no_prose_is_byte_identical_and_emits_no_fragments():
    base = dict(render_views(SCHEMA, VIEWS))
    assert dict(render_views(SCHEMA, VIEWS, None, None)) == base
    assert not any(k.endswith(".prose.html") for k in base)


def test_prose_emits_fragment_and_wires_include():
    out = dict(render_views(SCHEMA, VIEWS, None, _PROSE))
    assert _FRAG in out
    assert "<h1>Your value map</h1>" in out[_FRAG]
    assert "<strong>proof points</strong>" in out[_FRAG]
    assert '{% include "views/_value_map.prose.html" %}' in out[_TMPL]
    assert "<h1>value_map</h1>" not in out[_TMPL]   # raw machine name gone from the served page


def test_prose_leaves_unrelated_views_byte_identical():
    base = dict(render_views(SCHEMA, VIEWS))
    out = dict(render_views(SCHEMA, VIEWS, None, _PROSE))
    other = "app/templates/views/model_import.html"   # has no prose entry in _PROSE
    assert out[other] == base[other]
    assert "app/templates/views/_model_import.prose.html" not in out


def test_fragment_is_not_an_owned_file():
    # R1-S4: assert the gate directly — the fragment carries no marker, so drift skips it.
    out = dict(render_views(SCHEMA, VIEWS, None, _PROSE))
    assert is_owned_view_file(out[_FRAG]) is False
    assert is_owned_view_file(out[_TMPL]) is True   # the owned template still is owned


# (Model-scoped export title/intro is now ALLOWED — it opts into the Phase-2 export landing page;
#  see the "export landing" section below. `empty` on an export still loud-fails, tested there.)


# --------------------------------------------------------------------------- #
# Drift safety — the load-bearing contract
# --------------------------------------------------------------------------- #

def test_owned_template_in_sync_only_when_prose_threaded():
    owned = dict(render_views(SCHEMA, VIEWS, None, _PROSE))[_TMPL]
    target = "proj/" + _TMPL
    # Presence affects the owned template, so the checker must see the prose to reproduce the include.
    assert views_in_sync(SCHEMA, VIEWS, target, owned, None, _PROSE) is True
    # Not threading it → the re-render emits the literal title → correctly flagged as drift.
    assert views_in_sync(SCHEMA, VIEWS, target, owned, None, None) is False


def test_editing_prose_content_does_not_trip_check():
    owned = dict(render_views(SCHEMA, VIEWS, None, _PROSE))[_TMPL]
    edited = _PROSE.replace("Your value map", "Your totally rewritten value map heading")
    # The owned template is unchanged by a copy edit (include line is content-independent)…
    assert dict(render_views(SCHEMA, VIEWS, None, edited))[_TMPL] == owned
    # …so --check stays green even though the words changed.
    assert views_in_sync(SCHEMA, VIEWS, "proj/" + _TMPL, owned, None, edited) is True


# --------------------------------------------------------------------------- #
# Phase 2 — the `empty` key (model-compose no-rows surface, own untracked fragment)
# --------------------------------------------------------------------------- #

_EFRAG = "app/templates/views/_value_map.empty.html"


def test_empty_parses_and_is_a_view_prose_field():
    out = parse_view_prose("value_map:\n  empty: No data yet.\n")
    assert out["value_map"] == ViewProse(empty="No data yet.")


def test_empty_only_keeps_literal_title_and_emits_only_empty_fragment():
    out = dict(render_views(SCHEMA, VIEWS, None, "value_map:\n  empty: No value map yet.\n"))
    assert "<h1>value_map</h1>" in out[_TMPL]              # title stays literal (no title/intro authored)
    assert "app/templates/views/_value_map.prose.html" not in out  # no heading fragment
    assert _EFRAG in out and "No value map yet." in out[_EFRAG]
    assert '{% if not rows %}{% include "views/_value_map.empty.html" %}{% endif %}' in out[_TMPL]
    assert "No value map yet." not in out[_TMPL]           # the words live in the fragment, not the template


def test_empty_fragment_escapes_and_is_unowned():
    out = dict(render_views(SCHEMA, VIEWS, None, 'value_map:\n  empty: "A & B <x>"\n'))
    assert "<p class=\"empty\">A &amp; B &lt;x&gt;</p>" in out[_EFRAG]
    assert is_owned_view_file(out[_EFRAG]) is False


def test_title_and_empty_emit_both_fragments():
    out = dict(render_views(SCHEMA, VIEWS, None, "value_map:\n  title: Your value map\n  empty: None yet.\n"))
    assert "app/templates/views/_value_map.prose.html" in out
    assert _EFRAG in out
    assert '{% include "views/_value_map.prose.html" %}' in out[_TMPL]
    assert '{% include "views/_value_map.empty.html" %}' in out[_TMPL]


def test_editing_empty_text_does_not_trip_check():
    p = "value_map:\n  empty: Nothing here yet.\n"
    owned = dict(render_views(SCHEMA, VIEWS, None, p))[_TMPL]
    edited = p.replace("Nothing here yet.", "A completely different empty message")
    assert dict(render_views(SCHEMA, VIEWS, None, edited))[_TMPL] == owned
    assert views_in_sync(SCHEMA, VIEWS, "proj/" + _TMPL, owned, None, edited) is True


def test_empty_on_non_model_compose_loud_fails():
    # computed-panel has no no-rows surface today → loud-fail rather than silently drop.
    with pytest.raises(ValueError, match="no-rows surface"):
        render_views(SCHEMA, VIEWS, None, "completeness_panel:\n  empty: x\n")


# --------------------------------------------------------------------------- #
# Phase 2 — export landing (model-scoped export-package title/intro → opt-in HTML page)
# --------------------------------------------------------------------------- #

# A model-scoped export has NO HTML template today (served as raw JSON/Markdown); /export is a 404.
_EXPORT_VIEWS = VIEWS + "\n  - name: full_export\n    kind: export-package\n    scope: model\n    route: /export\n"
_LAND = "app/templates/views/full_export.html"
_LAND_FRAG = "app/templates/views/_full_export.prose.html"
_ROUTES = "app/views/routes.py"


def test_export_without_prose_has_no_landing_and_router_is_byte_identical():
    base = dict(render_views(SCHEMA, _EXPORT_VIEWS))
    assert _LAND not in base                      # no template (today: /export 404)
    assert dict(render_views(SCHEMA, _EXPORT_VIEWS, None, None)) == base


def test_export_with_prose_emits_landing_fragment_and_bare_route():
    p = 'full_export:\n  title: "Export your value model"\n  intro: "Download as **Markdown** or **JSON**."\n'
    out = dict(render_views(SCHEMA, _EXPORT_VIEWS, None, p))
    assert _LAND in out and _LAND_FRAG in out
    assert '{% include "views/_full_export.prose.html" %}' in out[_LAND]
    assert "/export/markdown" in out[_LAND] and "/export/json" in out[_LAND]
    assert "<h1>Export your value model</h1>" in out[_LAND_FRAG]
    # bare HTML route added; the raw md/json routes are kept
    assert "@views_router.get('/export', response_class=HTMLResponse)" in out[_ROUTES]
    assert "'/export/markdown'" in out[_ROUTES] and "'/export/json'" in out[_ROUTES]


def test_chrome_on_non_export_leaves_router_byte_identical():
    # Phase-1 manifests (chrome on a non-export view) must not change the router.
    base = dict(render_views(SCHEMA, _EXPORT_VIEWS))
    out = dict(render_views(SCHEMA, _EXPORT_VIEWS, None, "value_map:\n  title: Hi\n"))
    assert out[_ROUTES] == base[_ROUTES]


def test_editing_export_copy_does_not_trip_check():
    p = 'full_export:\n  title: "Export your value model"\n'
    files = dict(render_views(SCHEMA, _EXPORT_VIEWS, None, p))
    owned_land, owned_routes = files[_LAND], files[_ROUTES]
    edited = p.replace("Export your value model", "Export absolutely everything")
    assert dict(render_views(SCHEMA, _EXPORT_VIEWS, None, edited))[_LAND] == owned_land
    assert views_in_sync(SCHEMA, _EXPORT_VIEWS, "p/" + _LAND, owned_land, None, edited) is True
    assert views_in_sync(SCHEMA, _EXPORT_VIEWS, "p/" + _ROUTES, owned_routes, None, p) is True


def test_empty_on_export_loud_fails():
    with pytest.raises(ValueError, match="no-rows surface"):
        render_views(SCHEMA, _EXPORT_VIEWS, None, "full_export:\n  empty: x\n")


# --------------------------------------------------------------------------- #
# Phase 2 — import-flow restore outcome copy (success/error → HTML result page)
# --------------------------------------------------------------------------- #

_IMPORT_VIEWS = SCHEMA and "views:\n  - name: model_import\n    kind: import-flow\n    route: /import\n"
_ROUTER = "app/views/routes.py"
_OK_FRAG = "app/templates/views/_model_import.success.html"
_ERR_FRAG = "app/templates/views/_model_import.error.html"
_OK_PAGE = "app/templates/views/model_import_success.html"
_ERR_PAGE = "app/templates/views/model_import_error.html"
_OUTCOME = (
    'model_import:\n'
    '  success: "Restored {total} items. Your value model is back."\n'
    '  error: "Could not read that export: {errors}"\n'
)


def test_no_outcome_leaves_restore_route_byte_identical_even_with_title():
    base = dict(render_views(SCHEMA, _IMPORT_VIEWS))
    assert dict(render_views(SCHEMA, _IMPORT_VIEWS, None, None)) == base
    # title-only chrome must not perturb the (owned) router restore route.
    titled = dict(render_views(SCHEMA, _IMPORT_VIEWS, None, "model_import:\n  title: Restore\n"))
    assert titled[_ROUTER] == base[_ROUTER]


def test_outcome_emits_fragments_result_pages_and_html_restore_route():
    out = dict(render_views(SCHEMA, _IMPORT_VIEWS, None, _OUTCOME))
    assert {_OK_FRAG, _ERR_FRAG, _OK_PAGE, _ERR_PAGE} <= set(out)
    assert "{{ total }}" in out[_OK_FRAG]
    assert "{{ errors | join('; ') }}" in out[_ERR_FRAG]
    assert '{% include "views/_model_import.success.html" %}' in out[_OK_PAGE]
    assert "_templates.TemplateResponse(request, 'views/model_import_success.html'" in out[_ROUTER]
    assert "_templates.TemplateResponse(request, 'views/model_import_error.html'" in out[_ROUTER]
    assert "def model_import_restore_route(\n    request: Request," in out[_ROUTER]
    # validate stays JSON (out of scope)
    assert "def model_import_validate_route(file: UploadFile):" in out[_ROUTER]


def test_result_pages_owned_outcome_fragments_untracked():
    out = dict(render_views(SCHEMA, _IMPORT_VIEWS, None, _OUTCOME))
    assert is_owned_view_file(out[_OK_PAGE]) is True
    assert is_owned_view_file(out[_OK_FRAG]) is False


def test_editing_outcome_copy_does_not_trip_check():
    files = dict(render_views(SCHEMA, _IMPORT_VIEWS, None, _OUTCOME))
    owned_router, owned_page = files[_ROUTER], files[_OK_PAGE]
    edited = _OUTCOME.replace("Your value model is back.", "Everything is restored!")
    out = dict(render_views(SCHEMA, _IMPORT_VIEWS, None, edited))
    assert out[_ROUTER] == owned_router and out[_OK_PAGE] == owned_page
    assert views_in_sync(SCHEMA, _IMPORT_VIEWS, "p/" + _ROUTER, owned_router, None, edited) is True


def test_success_only_keeps_json_error_path():
    # error not authored → the invalid-payload path stays today's HTTPException (no error page).
    out = dict(render_views(SCHEMA, _IMPORT_VIEWS, None, 'model_import:\n  success: "Done: {total}"\n'))
    assert _OK_PAGE in out and _ERR_PAGE not in out
    assert "raise HTTPException(status_code=422" in out[_ROUTER]      # error path unchanged
    assert "views/model_import_success.html'" in out[_ROUTER]         # success path swapped


def test_wrong_placeholder_for_outcome_loud_fails():
    # `success` may only use {imported}/{total}; {errors} belongs to `error`.
    with pytest.raises(ValueError, match="not computed"):
        render_views(SCHEMA, _IMPORT_VIEWS, None, 'model_import:\n  success: "{errors}"\n')


def test_success_error_on_non_import_flow_loud_fails():
    views = _IMPORT_VIEWS + "  - name: cp\n    kind: computed-panel\n    compute: completeness\n    route: /c\n"
    with pytest.raises(ValueError, match="restore-outcome surface"):
        render_views(SCHEMA, views, None, "cp:\n  success: x\n")


# --------------------------------------------------------------------------- #
# Phase 2 — controls (import-flow button/checkbox labels → per-control untracked fragments)
# --------------------------------------------------------------------------- #

def test_controls_parse_to_normalized_mapping():
    # string shorthand and {label, help} both normalize to {label, help?}.
    out = parse_view_prose(
        'model_import:\n'
        '  controls:\n'
        '    validate: "Check this file"\n'
        '    restore: { label: "Restore my data", help: "Upserts; never deletes." }\n'
    )
    assert out["model_import"].controls == {
        "validate": {"label": "Check this file"},
        "restore": {"label": "Restore my data", "help": "Upserts; never deletes."},
    }


def test_no_controls_is_byte_identical():
    base = dict(render_views(SCHEMA, _IMPORT_VIEWS))
    assert dict(render_views(SCHEMA, _IMPORT_VIEWS, None, None)) == base


def test_authored_controls_become_includes_unauthored_stay_literal():
    p = 'model_import:\n  controls:\n    validate: "Check this file"\n    confirm: "Yes, write this in"\n'
    out = dict(render_views(SCHEMA, _IMPORT_VIEWS, None, p))
    tmpl = "app/templates/views/model_import.html"
    assert out["app/templates/views/_model_import.control.validate.html"] == "Check this file"
    assert "app/templates/views/_model_import.control.restore.html" not in out  # not authored
    assert '{% include "views/_model_import.control.validate.html" %}' in out[tmpl]
    assert '<button type="submit">Restore</button>' in out[tmpl]   # restore label stays literal
    assert "Check this file" not in out[tmpl]                       # label lives in the fragment


def test_control_fragment_escaped_and_unowned():
    out = dict(render_views(SCHEMA, _IMPORT_VIEWS, None, 'model_import:\n  controls: {validate: "A & B <x>"}\n'))
    frag = out["app/templates/views/_model_import.control.validate.html"]
    assert frag == "A &amp; B &lt;x&gt;"
    assert is_owned_view_file(frag) is False


def test_editing_control_label_does_not_trip_check():
    tmpl = "app/templates/views/model_import.html"
    p = 'model_import:\n  controls: {validate: "Check this file"}\n'
    owned = dict(render_views(SCHEMA, _IMPORT_VIEWS, None, p))[tmpl]
    edited = p.replace("Check this file", "Verify the file")
    assert dict(render_views(SCHEMA, _IMPORT_VIEWS, None, edited))[tmpl] == owned
    assert views_in_sync(SCHEMA, _IMPORT_VIEWS, "p/" + tmpl, owned, None, edited) is True


def test_unknown_control_id_loud_fails():
    with pytest.raises(ValueError, match="unknown control-id"):
        render_views(SCHEMA, _IMPORT_VIEWS, None, "model_import:\n  controls: {bogus: x}\n")


def test_controls_on_non_import_flow_loud_fails():
    views = _IMPORT_VIEWS + "  - name: cp\n    kind: computed-panel\n    compute: completeness\n    route: /c\n"
    with pytest.raises(ValueError, match="labelled controls"):
        render_views(SCHEMA, views, None, "cp:\n  controls: {validate: x}\n")


def test_control_value_must_be_string_or_mapping():
    with pytest.raises(ValueError, match="label string or a"):
        parse_view_prose("model_import:\n  controls: {validate: 123}\n")


def test_control_full_form_requires_label_and_rejects_unknown_inner_keys():
    with pytest.raises(ValueError, match="requires a string `label`"):
        parse_view_prose("model_import:\n  controls: {validate: {help: hi}}\n")
    with pytest.raises(ValueError, match="unknown keys"):
        parse_view_prose("model_import:\n  controls: {validate: {label: a, bogus: x}}\n")


# --------------------------------------------------------------------------- #
# Follow-ups — control help text + export-package format-link labels
# --------------------------------------------------------------------------- #

def test_control_help_emits_help_fragment_and_small_element():
    p = (
        'model_import:\n'
        '  controls:\n'
        '    validate: { label: "Check this file", help: "A dry run — writes nothing." }\n'
        '    restore: "Restore my data"\n'   # string form → no help
    )
    out = dict(render_views(SCHEMA, _IMPORT_VIEWS, None, p))
    tmpl = "app/templates/views/model_import.html"
    assert out["app/templates/views/_model_import.control.validate.help.html"] == "A dry run — writes nothing."
    assert "app/templates/views/_model_import.control.restore.help.html" not in out
    assert '<small class="control-help">{% include "views/_model_import.control.validate.help.html" %}</small>' in out[tmpl]
    assert out[tmpl].count("control-help") == 1   # only the one control with help


def test_editing_control_help_does_not_trip_check():
    tmpl = "app/templates/views/model_import.html"
    p = 'model_import:\n  controls: {validate: {label: "Check", help: "writes nothing"}}\n'
    owned = dict(render_views(SCHEMA, _IMPORT_VIEWS, None, p))[tmpl]
    edited = p.replace("writes nothing", "just inspects the file")
    assert dict(render_views(SCHEMA, _IMPORT_VIEWS, None, edited))[tmpl] == owned
    assert views_in_sync(SCHEMA, _IMPORT_VIEWS, "p/" + tmpl, owned, None, edited) is True


def test_export_link_labels_render_via_controls():
    p = 'full_export:\n  title: "Export your value model"\n  controls: {markdown: "Get Markdown", json: "Get JSON"}\n'
    out = dict(render_views(SCHEMA, _EXPORT_VIEWS, None, p))
    assert out["app/templates/views/_full_export.control.markdown.html"] == "Get Markdown"
    assert '{% include "views/_full_export.control.markdown.html" %}' in out["app/templates/views/full_export.html"]
    assert "Download as Markdown" not in out["app/templates/views/full_export.html"]
    assert "@views_router.get('/export', response_class=HTMLResponse)" in out["app/views/routes.py"]


def test_export_controls_only_still_opts_into_landing():
    # controls without title/intro still triggers the landing page (+ bare route), with a literal title.
    out = dict(render_views(SCHEMA, _EXPORT_VIEWS, None, 'full_export:\n  controls: {markdown: "MD"}\n'))
    land = out["app/templates/views/full_export.html"]
    assert "<h1>full_export</h1>" in land   # literal title (no chrome authored)
    assert '{% include "views/_full_export.control.markdown.html" %}' in land
    assert "@views_router.get('/export', response_class=HTMLResponse)" in out["app/views/routes.py"]


def test_unknown_export_control_id_loud_fails():
    with pytest.raises(ValueError, match="unknown control-id"):
        render_views(SCHEMA, _EXPORT_VIEWS, None, "full_export:\n  controls: {pdf: x}\n")
