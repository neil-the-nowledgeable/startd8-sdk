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


@pytest.mark.parametrize("key", ["empty", "controls", "success", "error"])
def test_reserved_phase2_keys_loud_fail(key):
    with pytest.raises(ValueError, match="reserved"):
        parse_view_prose(f"value_map:\n  {key}: x\n")


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


def test_model_scoped_export_prose_loud_fails():
    model_export = VIEWS + "\n  - name: full_export\n    kind: export-package\n    scope: model\n"
    with pytest.raises(ValueError, match="no HTML page|landing surface"):
        render_views(SCHEMA, model_export, None, "full_export:\n  title: x\n")


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
