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
    # REQ-view-definition-mode FR-2/FR-5 (the ONE deliberate panel edit): the debugging layer collapses
    # to a top-right panel with a pick-one VIEW picker (Requirement / View Definition) + an additive
    # OVERLAYS stack (Show node metadata · Outline regions · Hide app-scaffold chrome · per-layer). It is
    # RUNTIME-gated to a profile (app path renders an empty, hidden panel) and no-profile is byte-identical.
    prof = RenderProfile(statuses=(StatusStyle("spec", "Spec", "#888888", "written, not built"),))
    profiled = render_html(_keyed_plan(), profile=prof)
    assert 'id="debug"' in profiled                      # the debug panel container
    # VIEW picker — Requirement (default) vs the requirement-free View Definition frame
    assert 'id="viewRequirement"' in profiled and "checked" in profiled  # Requirement is the default pick
    assert 'id="viewDefinition"' in profiled             # the in-render View Definition pick (FR-1)
    # OVERLAYS — additive
    assert 'id="nodeMeta"' in profiled                   # Show node metadata (the retired modes' item.meta payload)
    assert "body.show-node-meta .node-meta" in profiled  # the metadata reveal CSS
    assert 'class="node-meta"' in profiled or "node-meta" in profiled          # metadata line renders
    assert 'id="outlineRegions"' in profiled             # Outline regions (was "Scaffold mode")
    assert 'id="hideScaffold"' in profiled               # multi-stage cruft-purge toggle
    assert "body.hide-scaffold .signoff" in profiled     # purge hides the app-scaffold sign-off subsystem
    assert "body.scaffold [data-scaffold]" in profiled   # region-outline overlay CSS (Outline regions / View Definition)
    assert "body.frame-bare [data-scaffold]" in profiled # frame-bare CSS drives the View Definition pick
    assert "data-scaffold=" in profiled                  # regions carry their scaffold role
    assert 'data-layer=' in profiled                     # regions carry their layer classification
    assert 'class="dbg-layers"' in profiled              # the layer legend
    assert 'body.scaffold [data-layer="computed"]' in profiled  # layer-aware colouring
    # the density modes + scaffoldOnly are retired — their ids must be gone
    assert 'id="structOnly"' not in profiled and 'id="combined"' not in profiled and 'id="scaffoldOnly"' not in profiled
    # two clean axes under labelled headers
    assert 'class="dbg-group' in profiled                # group-header markup is present
    assert "#debug .dbg-group{" in profiled              # group-header CSS is present (inert on app path)
    assert ">View <span" in profiled                     # VIEW group header (pick one)
    assert ">Overlays <span" in profiled                 # OVERLAYS group header (additive)
    assert ">Template anatomy <span" not in profiled     # the retired standalone group header is gone
    assert "if(payload.profile)" in profiled             # the panel is gated on a profile
    # Byte-safe: the app path is byte-identical with/without an explicit None (FR-8 preserved).
    assert render_html(_plan()) == render_html(_plan(), profile=None)


def test_view_definition_shows_every_region_display_logic_template():
    # REQ-view-definition-mode FR-6 (v0.5): when the View Definition is shown, EVERY region renders a
    # slot-annotated DISPLAY-LOGIC template (built from the real render classes) showing what it displays
    # and FROM WHAT it derives — not just the node region. JS-injected only in frame mode, so ABSENT from
    # a normal render's served HTML → byte-identity holds.
    prof = RenderProfile(statuses=(StatusStyle("spec", "Spec", "#888888", "written, not built"),))
    profiled = render_html(_keyed_plan(), profile=prof)
    # the template map + its frame-mode wiring ship in the (client-side) render
    assert "FRAME_TEMPLATES" in profiled                    # the per-region display-logic template map
    assert "payload.profile.region_templates" in profiled   # FR-13: read FROM the View Definition, not hardcoded
    assert "function syncFrameTemplates" in profiled        # injected/removed with the View Definition (syncView)
    # the map keys cover EVERY region — now carried in the profile payload (region_templates JSON)
    for region in ('"mast":', '"glance":', '"toolbar":', '"legend":', '"seclead":', '"outline":'):
        assert region in profiled, region
    # per-region derivation sources are annotated (ASCII markers survive the JSON embed; the ‹…›/— slot
    # text is now JSON-encoded in the payload since the templates live in the definition — FR-13)
    for src in ("status_counts", "plan.shape", "audience", "profile.statuses", "profile.section_lead"):
        assert src in profiled, src
    # the node-card (outline) template still ships in region_templates (its ndt-cap caption survives ASCII)
    assert "ndt-cap" in profiled
    # frame-bare hides real content with display:none (collapses space) and EXCLUDES the vd-template so
    # it always shows; the template force-reveals the normally-hidden key+meta slots
    assert "body.frame-bare [data-scaffold] > *:not(.vd-template){display:none}" in profiled
    assert ".vd-template .lbl-key{display:inline" in profiled
    # JS-injected only — NOT pre-rendered into the served HTML (a normal render is unchanged)
    assert 'class="vd-template"' not in profiled
    # Byte-safe: the app path is byte-identical (templates never land in a normal render).
    assert render_html(_plan()) == render_html(_plan(), profile=None)


def test_requirement_card_shows_structured_what_how_why_and_is_byte_safe():
    # The profiled card parses the node-detail blob into captioned WHAT/HOW/WHY slots (Verify = how you'll
    # know, Serves = why it matters). Client-side machinery ships; the app path keeps the plain .det blob.
    prof = RenderProfile(statuses=(StatusStyle("spec", "Spec", "#888888", "written, not built"),))
    profiled = render_html(_keyed_plan(), profile=prof)
    assert "function structuredDet" in profiled                       # the blob→slots parser
    assert "payload.profile?structuredDet(item.detail)" in profiled   # profiled card uses it; app path does not
    assert "Verify · how you’ll know" in profiled and "Serves · why it matters" in profiled  # captions
    assert "Name · deterministic identity" in profiled                # DIDL semantic name shown up top
    assert "body.nav-profiled #outline .item .ci-row.ci-why{border-left-color:var(--accent)" in profiled
    # app path byte-identical (structuredDet only runs when a profile is present)
    assert render_html(_plan()) == render_html(_plan(), profile=None)


def test_requirement_card_readability_is_profiled_navigator_only_and_byte_safe():
    # frontend-design: the editorial requirement-card styling (status spine, FR-id tag, serif prose,
    # evidence block) is scoped to body.nav-profiled so a generated-app preview (no profile) keeps the
    # plain .item card — the app path stays byte-identical. The scoping ships in the (client-side) render.
    prof = RenderProfile(statuses=(StatusStyle("spec", "Spec", "#888888", "written, not built"),))
    profiled = render_html(_keyed_plan(), profile=prof)
    assert "body.nav-profiled #outline .item{" in profiled              # the card styling is scoped
    assert "border-left:3px solid var(--st" in profiled                 # the status spine
    assert "body.nav-profiled #outline .item .det{font-family:var(--serif)" in profiled  # readable prose
    assert 'classList.toggle("nav-profiled", !!payload.profile)' in profiled  # class added only when profiled
    assert 'w.style.setProperty("--st"' in profiled                     # status colour stamped per card
    # app path byte-identical (nav-profiled never set without a profile)
    assert render_html(_plan()) == render_html(_plan(), profile=None)


def test_debug_group_and_raw_data_panel_ship_and_are_byte_safe():
    # REQ-view-definition-mode FR-8: the Debug control group (Raw data / Node data) + a #rawdata panel
    # positioned BELOW the sign-off (#signbar) ship in the profiled render, hidden by default; app-safe.
    prof = RenderProfile(statuses=(StatusStyle("spec", "Spec", "#888888", "written, not built"),))
    profiled = render_html(_keyed_plan(), profile=prof)
    assert 'data-group="debug"' in profiled                 # the Debug group header
    assert 'id="rawData"' in profiled and 'id="nodeData"' in profiled   # the two debug toggles
    assert "function renderRawData" in profiled             # the raw-data renderer
    # the panel is placed below the sign-off (its element appears AFTER #signbar in the document)
    assert profiled.index('id="rawdata"') > profiled.index('id="signbar"')
    assert 'class="rawdata"' in profiled and "hidden" in profiled       # hidden until a toggle is on
    # app path never emits the debug panel content / byte-identity holds
    assert render_html(_plan()) == render_html(_plan(), profile=None)


def test_inspect_cells_shows_per_node_data_and_display_mapping():
    # REQ-view-definition-mode FR-10: an Inspect cells Debug toggle shows, under each card, the node's
    # data (fields+values) and how each field is displayed (field→element mapping). Cards stash their
    # exact node data (_nodeData). Client-side machinery ships; the app path is byte-identical.
    prof = RenderProfile(statuses=(StatusStyle("spec", "Spec", "#888888", "written, not built"),))
    profiled = render_html(_keyed_plan(), profile=prof)
    assert 'id="inspectCells"' in profiled                   # the toggle
    assert "function buildInspect" in profiled and "function syncInspect" in profiled   # the inspector
    assert "w._nodeData=item" in profiled                    # exact per-cell data stashed at render
    assert "INSPECT_MAP" in profiled                         # the field→element display mapping
    # FR-10: rendered as a TABLE with the three headings
    assert 'class="ni-table"' in profiled
    for th in ("<th>node data</th>", "<th>value</th>", "how it’s displayed</th>"):
        assert th in profiled, th
    # FR-11: not-displayed value cells are editable (contenteditable) and edit NON-PERSISTENTLY
    assert 'class="ni-v ni-edit" contenteditable="true"' in profiled
    assert "function updateAddedLine" in profiled            # surfaces the edited field in the card
    assert "card._nodeData[f]=cell.textContent" in profiled  # in-memory only (no disk write path)
    # FR-12: EVERY field's row carries an on/off switch — displayed toggles the element, not-displayed
    # surfaces the value. Both switch flavours + their handlers ship.
    assert "data-ni-toggle=" in profiled and "data-ni-show=" in profiled and 'class="ni-sw"' in profiled
    assert 'el.style.display = inp.checked ? "" : "none"' in profiled   # displayed: per-card element toggle
    assert "inp.checked ? card._nodeData[f] : \"\"" in profiled          # not-displayed: surface the raw value
    assert 'typeof raw==="object"?JSON.stringify(raw)' in profiled        # coerce list/num/bool (the toggle bug fix)
    assert 'class="node-inspect"' not in profiled            # injected on toggle only, not pre-rendered
    # app path byte-identical (inspector is profiled-navigator-only)
    assert render_html(_plan()) == render_html(_plan(), profile=None)


def test_paging_control_ships_and_is_byte_safe():
    # REQ-view-definition-mode FR-9: a definition-owned Paging group (pick-one page size incl. 1-at-a-time)
    # + a #pagebar below the outline pages through the requirement nodes N at a time. Client-side machinery
    # ships in the profiled render; the app path is byte-identical (no paging emitted without a profile).
    prof = RenderProfile(statuses=(StatusStyle("spec", "Spec", "#888888", "written, not built"),))
    profiled = render_html(_keyed_plan(), profile=prof)
    assert 'data-group="paging"' in profiled                 # the Paging group header
    for tid in ('id="pageAll"', 'id="page10"', 'id="page5"', 'id="page1"'):
        assert tid in profiled, tid                          # the pick-one page sizes incl. 1-at-a-time
    assert "function applyPaging" in profiled                # the paging engine
    assert 'id="pagebar"' in profiled                        # the prev/next bar element
    # the bar sits below the node outline (appears after #outline in the document)
    assert profiled.index('id="pagebar"') > profiled.index('id="outline"')
    assert "pg-hidden" in profiled and "pg-next" in profiled  # slice-hiding + next control
    # app path byte-identical (paging is profiled-navigator-only)
    assert render_html(_plan()) == render_html(_plan(), profile=None)


def test_frame_provenance_reads_as_definition_summary_not_cruft():
    # REQ-view-definition-mode FR-7: a bare frame (payload.frame) must NOT report its empty chrome slots
    # as "cruft" — the readout reads as a definition summary. (Client-side: the frame-branch ships in JS.)
    prof = RenderProfile(statuses=(StatusStyle("spec", "Spec", "#888888", "written, not built"),))
    profiled = render_html(_keyed_plan(), profile=prof)
    # the definition-summary branch is present and gated on payload.frame
    assert "if(payload.frame){" in profiled
    assert "View Definition · " in profiled and "regions · " in profiled   # the definition-summary text
    # the app path stays byte-identical
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
        control={"groups": {"overlays": {"label": "Filters", "toggles": {}}}},
        regions={"bindings": {"outline": {"layer": "node", "scaffold": "the requirements list"}}},
    )
    html = render_html(_plan(), profile=prof)
    assert '"Filters"' in html                        # control-group override embedded in the payload
    assert '"the requirements list"' in html         # region-anatomy override embedded in the payload
    assert "applyDefinitionOverride" in html         # the additive-override machinery is present
    assert 'data-group="overlays"' in html           # the control DOM hook exists
    assert 'id="outline"' in html                    # the region DOM hook exists
    # a profile WITHOUT control/regions injects an inert (empty) override — app path byte-identical.
    assert render_html(_plan()) == render_html(_plan(), profile=None)
