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
