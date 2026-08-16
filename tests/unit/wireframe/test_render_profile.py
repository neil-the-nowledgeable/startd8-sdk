"""RenderProfile — the HTML preview's opt-in domain vocabulary/chrome.

Guards: (1) no profile ⇒ byte-identical to today (the app path is untouched);
(2) a profile relabels the status vocabulary + chrome in the rendered output.
"""
from __future__ import annotations

from startd8.wireframe import (
    ContentCoverageStats,
    RenderProfile,
    StatusStyle,
    WireframeItem,
    WireframePlan,
    WireframeSection,
)
from startd8.wireframe_view.view import render_html


def _plan() -> WireframePlan:
    item = WireframeItem(label="FR-1 — Sign in", status="spec", detail="", paths=())
    sec = WireframeSection(key="identity", title="Identity", status="spec", items=(item,))
    return WireframePlan(
        project_root=".",
        sections=(sec,),
        input_provenance={},
        merge_warnings=(),
        shape={"entities": 0, "crud_routes": 0, "pages": 0, "views": 0, "ai_passes": 0},
        readiness={},
        status_counts={"spec": 1},
        content_coverage=ContentCoverageStats(),
    )


def test_no_profile_is_byte_identical():
    # Opt-in: an omitted profile must not change a single byte of the app output.
    assert render_html(_plan()) == render_html(_plan(), profile=None)


# ── REQ-11 — theme-token activation ──────────────────────────────────────────────────────────────

def test_theme_tokens_empty_by_default_and_render_byte_identical():
    # FR-2: theme_tokens defaults empty (the byte-identity guard); an empty map emits no override.
    assert RenderProfile(statuses=()).theme_tokens == {}
    # a profile WITHOUT a theme injects no :root override — render matches the no-theme render.
    prof_no_theme = RenderProfile(statuses=(StatusStyle("spec", "Spec", "#888", "written, not built"),))
    html = render_html(_plan(), profile=prof_no_theme)
    assert "<style>:root{--" not in html          # the injected override marker is absent
    # and the app path (no profile) is byte-identical (FR-2 re-assertion, unedited guard below too)
    assert render_html(_plan()) == render_html(_plan(), profile=None)


def test_theme_tokens_emit_additive_root_override():
    # FR-4: a non-empty theme_tokens map emits an additive :root override (spliced before </head>,
    # after the template's own :root → CSS cascade last-wins applies the domain's tokens).
    prof = RenderProfile(
        statuses=(StatusStyle("spec", "Spec", "#888", "written, not built"),),
        theme_tokens={"accent": "#3a6a94"},
    )
    html = render_html(_plan(), profile=prof)
    assert "<style>:root{--accent:#3a6a94;}</style></head>" in html   # additive override, before </head>
    # the app path emits no such override and stays byte-identical
    assert "<style>:root{--accent" not in render_html(_plan())
    assert render_html(_plan()) == render_html(_plan(), profile=None)


def test_domain_accent_override_renders_visibly():
    # FR-6: a domain that overrides accent (capability → #3a6a94) renders a different accent than a
    # non-overriding domain (requirements → the reconciled base #1b545f) — the cascade's visible teeth.
    req = RenderProfile(statuses=(StatusStyle("spec", "S", "#888", "m"),), theme_tokens={"accent": "#1b545f"})
    cap = RenderProfile(statuses=(StatusStyle("spec", "S", "#888", "m"),), theme_tokens={"accent": "#3a6a94"})
    req_html = render_html(_plan(), profile=req)
    cap_html = render_html(_plan(), profile=cap)
    assert "--accent:#1b545f;" in req_html
    assert "--accent:#3a6a94;" in cap_html
    assert req_html != cap_html                    # the override is visibly different


def test_profile_relabels_status_vocabulary_and_chrome():
    base = render_html(_plan())
    prof = RenderProfile(
        statuses=(StatusStyle("spec", "Spec", "#888888", "written, not built"),),
        section_lead="What this spec defines",
    )
    html = render_html(_plan(), profile=prof)
    assert html != base
    assert "written, not built" in html          # legend meaning (not "not set up yet")
    assert "What this spec defines" in html       # chrome section-lead
    assert "Spec" in html                          # badge label carried in the embed


def _keyed_plan() -> WireframePlan:
    item = WireframeItem(label="FR-1 — Sign in", status="spec", detail="", paths=(), key="FR-1")
    sec = WireframeSection(key="identity", title="Identity", status="spec", items=(item,))
    return WireframePlan(
        project_root=".", sections=(sec,), input_provenance={}, merge_warnings=(),
        shape={"nodes": 1, "sections": 1}, readiness={}, status_counts={"spec": 1},
        content_coverage=ContentCoverageStats(),
    )


def test_debug_view_mode_panel_is_profiled_and_byte_safe():
    # FR-11/FR-12: the debugging layer ships — a top-right view-mode panel (Structure only + Combined)
    # with body-class CSS and per-item bare-key/metadata spans. It is RUNTIME-gated to a profile
    # (so the app path renders an empty, hidden panel) and the no-profile render is byte-identical.
    prof = RenderProfile(statuses=(StatusStyle("spec", "Spec", "#888888", "written, not built"),))
    profiled = render_html(_keyed_plan(), profile=prof)
    assert 'id="debug"' in profiled                      # the debug panel container
    assert 'id="structOnly"' in profiled                 # Structure only switch
    assert 'id="combined"' in profiled                   # Combined switch
    assert "body.structure-only" in profiled and "body.combined" in profiled  # both modes' CSS
    assert 'class="lbl-key"' in profiled                 # structure-only bare key
    assert 'class="node-meta"' in profiled or "node-meta" in profiled          # metadata line
    assert 'id="hideScaffold"' in profiled               # FR-14 multi-stage cruft-purge toggle
    assert "body.hide-scaffold .signoff" in profiled     # purge hides the app-scaffold sign-off subsystem
    assert 'id="scaffold"' in profiled                   # FR-15 scaffold mode (template anatomy)
    assert "body.scaffold [data-scaffold]" in profiled   # scaffold-mode region overlay CSS
    assert "data-scaffold=" in profiled                  # regions carry their scaffold role
    assert 'data-layer=' in profiled                     # regions carry their layer classification
    assert 'class="dbg-layers"' in profiled              # the scaffold-mode layer legend
    assert 'body.scaffold [data-layer="computed"]' in profiled  # layer-aware colouring
    assert 'id="scaffoldOnly"' in profiled               # FR-16 scaffold-only (anatomy isolation) toggle
    assert 'body.scaffold-only [data-layer="node"]' in profiled  # FR-16 hides node content, keeps skeleton
    # FR-19: the panel's three logically-distinct kinds of control are grouped under labelled headers
    # (VIEW modes · OVERLAYS · TEMPLATE ANATOMY) — reorganization + labelling only, no behavior change.
    assert 'class="dbg-group' in profiled                # group-header markup is present
    assert "#debug .dbg-group{" in profiled              # group-header CSS is present (inert on app path)
    assert ">View <span" in profiled                     # VIEW group header (Structure only + Combined)
    assert ">Overlays <span" in profiled                 # OVERLAYS group header (Hide app-scaffold chrome)
    assert ">Template anatomy <span" in profiled         # TEMPLATE ANATOMY group header (scaffold + legend)
    assert "if(payload.profile)" in profiled             # the panel is gated on a profile
    # Byte-safe: the app path is byte-identical with/without an explicit None (FR-8 preserved).
    assert render_html(_plan()) == render_html(_plan(), profile=None)


def test_chrome_provenance_readout_embeds_and_is_byte_safe():
    # FR-13: the debug panel's live provenance readout is fed by an embedded chrome summary; the app
    # path (no chrome) stays byte-identical.
    prof = RenderProfile(statuses=(StatusStyle("spec", "Spec", "#888888", "written, not built"),))
    ch = {"score": 0.9, "present": 9, "total": 10, "orphans": ["why"]}
    withc = render_html(_keyed_plan(), profile=prof, chrome=ch)
    assert '"orphans"' in withc and '"score"' in withc   # the summary is embedded for the readout
    assert "dbg-prov" in withc                            # the readout element + its cruft styling
    # No chrome ⇒ payload unchanged; app path byte-identical regardless of the new param.
    assert render_html(_plan()) == render_html(_plan(), profile=None, chrome=None)


def test_profiled_render_carries_filter_machinery_and_data_status():
    """PF-1: a profiled render must embed the profile payload so the client-side filter machinery
    activates, AND the no-profile path must remain byte-identical (re-asserted here for completeness).

    The filter machinery is client-side JS — chip DOM nodes and data-status attributes are injected at
    runtime by renderGlance() / renderItem().  What we can inspect in the raw HTML is:
      • the embedded plan-data JSON — profile key present iff a profile was passed (the JS guard);
      • the JS source in the template — contains the filter machinery identifiers unconditionally
        (the template is a constant; behavior is gated on payload.profile at runtime, not on template bytes).
    """
    prof = RenderProfile(
        statuses=(
            StatusStyle("spec", "Spec", "#888888", "written, not built"),
            StatusStyle("grounded", "Grounded", "#3d7a57", "verified against source"),
        ),
    )
    html = render_html(_plan(), profile=prof)
    no_profile = render_html(_plan())

    # Byte-identity re-assertion: explicit profile=None must equal the default (no arg).
    assert render_html(_plan()) == render_html(_plan(), profile=None)

    # The profiled render must differ from the no-profile render.
    assert html != no_profile

    # The profiled JSON payload embeds the profile dict (the JS guard: payload.profile).
    assert '"profile"' in html

    # The profile's status keys and colors are in the embedded JSON.
    assert '"spec"' in html
    assert '#888888' in html

    # The no-profile payload does NOT embed a profile key — the app path is untouched.
    assert '"profile"' not in no_profile

    # The template (constant) carries the filter machinery JS identifiers regardless of profile;
    # this confirms the JS source is present in both renders (it is always emitted by the template).
    assert 'status-chips' in html
    assert 'data-chip-key' in html
    assert 'data-status' in html
    # Same strings appear in no-profile (template is constant; runtime behavior is gated on payload.profile).
    assert 'status-chips' in no_profile
    assert 'data-chip-key' in no_profile
    assert 'data-status' in no_profile


def test_req14_control_and_region_override_embed_and_render_byte_safe():
    # FR-3/FR-5/FR-7: a profile carrying a control-group + region override embeds them in the payload,
    # and the additive-override machinery + its DOM hooks are present so the browser applies them over
    # the hardcoded panel / static region attrs (the scaffold then reveals the definition, not template
    # strings). The default (no-delta) render + app path stay byte-identical.
    prof = RenderProfile(
        statuses=(StatusStyle("spec", "Spec", "#888888", "written, not built"),),
        control={"groups": {"template-anatomy": {"label": "Structure", "toggles": {}}}},
        regions={"bindings": {"outline": {"layer": "node", "scaffold": "the requirements list"}}},
    )
    html = render_html(_plan(), profile=prof)
    assert '"Structure"' in html                     # control-group override embedded in the payload
    assert '"the requirements list"' in html         # region-anatomy override embedded in the payload
    assert "applyDefinitionOverride" in html         # the additive-override machinery is present
    assert 'data-group="template-anatomy"' in html   # the control DOM hook exists
    assert 'id="outline"' in html                    # the region DOM hook exists
    # a profile WITHOUT control/regions injects an inert (empty) override — app path byte-identical.
    assert render_html(_plan()) == render_html(_plan(), profile=None)
