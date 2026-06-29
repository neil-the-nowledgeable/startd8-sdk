"""Quick-wins increment — home-page Red Carpet CTA (discoverability) + wireframe preview (FR-RCT-11)."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.kickoff_experience.proposals import ProposedAction, apply_proposal
from startd8.kickoff_experience.red_carpet import build_red_carpet_state

_BRIEF = """## Entities

### Customer
A person.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| name | text | yes | |
"""
_PAGES = "## Pages\n\n| Page | Purpose | Content file |\n|------|---------|--------------|\n| Home | landing | home.md |\n"
_VIEWS = "## Views\n\n### View: Dashboard\n- Kind: dashboard\n- Root: Customer\n- Shows: counts\n"


def test_home_page_surfaces_red_carpet_cta(tmp_path: Path) -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from startd8.kickoff_experience.web import build_kickoff_app

    html = TestClient(build_kickoff_app(tmp_path)).get("/").text
    assert "Build my app from scratch" in html          # discoverability CTA
    assert "/concierge/chat" in html                     # links to the Red Carpet build


def test_preview_absent_until_offerable_then_present(tmp_path: Path) -> None:
    # Not offerable → no preview (and no wasted wireframe compute).
    assert build_red_carpet_state(tmp_path).preview is None
    # Build the minimal subset (schema + app + pages + views) → preview appears.
    assert apply_proposal(tmp_path, ProposedAction("schema", {"brief": _BRIEF}, id="s")).ok
    (tmp_path / "app.yaml").write_text("package_name: demo\n")
    assert apply_proposal(tmp_path, ProposedAction("manifest", {"source": _PAGES}, id="m1")).ok
    assert apply_proposal(tmp_path, ProposedAction("manifest", {"source": _VIEWS}, id="m2")).ok
    state = build_red_carpet_state(tmp_path)
    assert state.cascade_offerable is True
    assert state.preview is not None and "shape" in state.preview      # FR-RCT-11 wireframe preview
    assert state.to_dict()["preview"] == state.preview                 # surfaced to the web/CLI
