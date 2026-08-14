"""ATM metabolize: app-bound cascade shape on Node plans must fail loud + stay fixed."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.navigator.project import nodes_to_wireframe_plan, render_nodes_html
from startd8.navigator.sources_capability import (
    CAPABILITY_PROFILE,
    default_capability_index_path,
    nodes_from_capability_index,
)
from startd8.navigator.sources_requirements import (
    REQUIREMENTS_PROFILE,
    nodes_from_requirements,
)
from startd8.wireframe.shape_dialect import (
    APP_APEX_BLEED_TOKENS,
    find_app_apex_bleed,
    format_shape_line,
    format_status_counts_line,
    reject_app_bound_node_shape,
)
from startd8.wireframe_view.compose import compose

REQ01 = Path("docs/design/requirements-visualization/REQ-01-sdk-node-home.md")
FIXTURE = Path("tests/unit/navigator/fixtures/REQ-fixture-minimal.md")


def test_reject_app_bound_node_shape_bites_on_bad():
    """Guard FAILS on the metabolized class (nodes>0 + app cascade keys)."""
    bad = {
        "nodes": 10,
        "sections": 1,
        "entities": 0,
        "crud_routes": 0,
        "pages": 0,
        "views": 0,
        "ai_passes": 0,
    }
    with pytest.raises(ValueError, match="app-bound cascade"):
        reject_app_bound_node_shape(bad)


def test_reject_app_bound_node_shape_passes_on_good():
    """Guard PASSES on node-domain shape (no cascade keys)."""
    reject_app_bound_node_shape({"nodes": 10, "sections": 1})
    reject_app_bound_node_shape({"entities": 3, "crud_routes": 1, "pages": 1, "views": 0, "ai_passes": 0})


def test_nodes_to_wireframe_plan_emits_node_domain_shape_only():
    nodes = nodes_from_requirements(FIXTURE if FIXTURE.is_file() else REQ01)
    plan = nodes_to_wireframe_plan(nodes)
    assert "nodes" in plan.shape and plan.shape["nodes"] == len(nodes)
    for k in ("entities", "crud_routes", "pages", "views", "ai_passes"):
        assert k not in plan.shape
    reject_app_bound_node_shape(plan.shape)  # must not raise


def test_compose_req_summary_has_no_entities_bleed():
    """Regression bite: REQ navigator summary must not speak Entities/CRUD zeros."""
    assert REQ01.is_file()
    nodes = nodes_from_requirements(REQ01)
    plan = nodes_to_wireframe_plan(nodes)
    vm = compose(plan, role="architect")
    shape = vm["summary"]["shape"]
    assert "Entities" not in shape
    assert "CRUD" not in shape
    assert "Nodes:" in shape
    counts = vm["summary"]["counts"]
    assert "planned /" not in counts or "grounded" in counts
    assert "grounded" in counts or "spec" in counts
    # Lives survive to item view (lacuna L1 data plane).
    with_lives = [it for sec in vm["sections"] for it in sec["items"] if it.get("lives")]
    assert with_lives, "expected typed lives on at least one FR item"


def test_format_helpers_dialect():
    assert "Entities:" in format_shape_line(
        {"entities": 1, "crud_routes": 0, "pages": 0, "views": 0, "ai_passes": 0}
    )
    assert format_shape_line({"nodes": 3, "sections": 1}) == "Nodes: 3 | Sections: 1"
    assert "grounded" in format_status_counts_line({"grounded": 9, "spec": 1})
    assert "planned" in format_status_counts_line({"planned": 2, "not_defined": 1})


# --- ATM metabolize, second face: app-build APEX prose on a profiled Node consumer ----------
# The shape/footer guard above stops "Entities/CRUD zeros"; these stop the masthead sub-headline
# and Why/Do whybox from bleeding "$0 generation / entity count IS the contract / DATA MODEL
# bookend" onto a requirements / capability navigator (the apex band the first metabolize missed).


def test_find_app_apex_bleed_bites_on_app_prose():
    """The detector FIRES on raw app apex prose and is clean on Node apex prose."""
    assert set(find_app_apex_bleed(" ".join(APP_APEX_BLEED_TOKENS))) == set(APP_APEX_BLEED_TOKENS)
    assert find_app_apex_bleed("Each requirement is a Node — where it Lives, and whether it grounds.") == []


def test_requirements_html_apex_speaks_node_dialect(tmp_path):
    """Dogfood: the REQ-01 navigator HTML carries no app-build apex prose and shows the profile apex."""
    nodes = nodes_from_requirements(REQ01)
    out = render_nodes_html(nodes, tmp_path / "req.html", profile=REQUIREMENTS_PROFILE)
    html = out.read_text(encoding="utf-8")
    assert find_app_apex_bleed(html) == [], "app-build apex prose bled into the requirements navigator"
    # The profile's own apex chrome is present (headline + summary_meta lead-in). Assert an ASCII
    # slice of summary_meta — the embed JSON escapes non-ASCII (em-dash → —).
    assert REQUIREMENTS_PROFILE.headline in html
    assert "A glance-approvable view of every requirement in this spec" in html


def test_capability_html_apex_speaks_node_dialect(tmp_path):
    """Same guard on the capability-index consumer (the other profiled source)."""
    path = default_capability_index_path()
    if not path.is_file():  # capability manifest not present in this checkout
        pytest.skip(f"capability index absent at {path}")
    nodes = nodes_from_capability_index(path)
    out = render_nodes_html(nodes, tmp_path / "cap.html", profile=CAPABILITY_PROFILE)
    html = out.read_text(encoding="utf-8")
    assert find_app_apex_bleed(html) == [], "app-build apex prose bled into the capability navigator"
    assert CAPABILITY_PROFILE.headline in html
