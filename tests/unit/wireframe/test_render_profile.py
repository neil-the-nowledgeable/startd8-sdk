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
