"""REQ-cross-surface-view-definition FR-4/FR-5/FR-6 — ``surface_links`` + surface-agnostic primitive."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from startd8.navigator.view_definition import (
    CAPABILITY_DEFINITION,
    DEFINITION_REGISTRY,
    REQUIREMENTS_DEFINITION,
    resolve,
)

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]
_VIEW_DEF = _REPO / "src" / "startd8" / "navigator" / "view_definition.py"
_GRAPH = _REPO / "src" / "startd8" / "navigator" / "graph_projection.py"
_TEMPLATE = _REPO / "src" / "startd8" / "wireframe_view" / "_template.py"
_SPEC = (
    _REPO / "docs" / "design" / "requirements-visualization"
    / "REQ-cross-surface-view-definition.md"
)


def test_fr4a_drill_binding_points_at_navig8r_via_fullview():
    drill = resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY).surface_links["drill"]
    assert drill["to_surface"] == "navig8r"
    assert drill["from_surface"] == "cockpit"
    assert drill["relation"] == "drill"
    assert drill["via"] == "fullview"


def test_fr4b_drill_via_names_the_registered_fullview_region():
    resolved = resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY)
    assert resolved.surface_links["drill"]["via"] == "fullview"
    assert "fullview" in resolved.regions["bindings"]
    assert "#<key>" in resolved.regions["bindings"]["fullview"]["scaffold"]


def test_fr4c_drill_adds_no_route_handler_to_the_template():
    """The binding is a data pointer — this delivery must not grow _template.py route code."""
    tree = ast.parse(_VIEW_DEF.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any("wireframe_view" in m or "_template" in m for m in imported)
    assert "function resolveHash" in _TEMPLATE.read_text(encoding="utf-8")


def test_fr5a_rollup_binding_points_at_cockpit_via_serves():
    rollup = resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY).surface_links["rollup"]
    assert rollup["from_surface"] == "navig8r"
    assert rollup["to_surface"] == "cockpit"
    assert rollup["relation"] == "rollup"
    assert rollup["via"] == "serves"


def test_fr5b_rollup_does_not_invent_an_edge_kind():
    src = _GRAPH.read_text(encoding="utf-8")
    assert src.count("new edge kind") == 0
    assert src.count("rollup-edge") == 0
    assert 'add_semantic(node.key, target, "serves")' in src


def test_fr5c_activated_is_the_project_level_rollup_target():
    states = resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY).node_state["states"]
    assert states["activated"]["kind"] == "project"
    assert states["activated"]["presentation"]["cockpit"]["label"] == "activated"
    assert states["activated"]["presentation"]["cockpit"]["attention"] == "ok"
    assert not states["activated"]["presentation"]["navig8r"]


def test_fr6a_capability_inherits_the_same_sections_unchanged():
    cap = resolve(CAPABILITY_DEFINITION, DEFINITION_REGISTRY)
    req = resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY)
    assert cap.node_state == req.node_state
    assert cap.surface_links == req.surface_links
    src = _VIEW_DEF.read_text(encoding="utf-8")
    assert "grounded↔ok" not in src
    assert "if status.startswith" not in src


def test_fr6a_definition_module_has_no_renderer_imports():
    tree = ast.parse(_VIEW_DEF.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(a.name for a in node.names)
    forbidden = ("startd8.wireframe_view", "startd8.kickoff_experience", "startd8.navigator.render_")
    assert not [m for m in imported if any(f in m for f in forbidden)], imported


def test_fr6b_spec_appendix_c_names_the_twins():
    text = _SPEC.read_text(encoding="utf-8")
    assert "REQ-feature-capability-composition-rollup.md" in text
    assert "STRATEGY_navig8r-inflection-two-sided-validation.md" in text
    assert "Move 1" in text
