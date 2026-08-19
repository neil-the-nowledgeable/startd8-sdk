"""REQ-cross-surface-view-definition FR-1 — shared canonical ``node_state`` on the cascade."""
from __future__ import annotations

import json

import pytest

from startd8.navigator.view_definition import (
    BASE_NAVIG8R_DEFINITION,
    DEFINITION_REGISTRY,
    REQUIREMENTS_DEFINITION,
    ViewDefinition,
    _SECTIONS,
    resolve,
)

pytestmark = pytest.mark.unit

_PER_NODE = ("grounded", "spec", "awaiting", "excluded", "unknown")


def test_fr1a_resolved_requirements_carries_canonical_states_with_both_presentations():
    resolved = resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY)
    states = resolved.node_state["states"]
    for sid in _PER_NODE:
        pres = states[sid]["presentation"]
        assert pres["navig8r"]["label"], f"{sid} missing navig8r presentation"
        assert pres["cockpit"]["attention"], f"{sid} missing cockpit presentation"
    assert "activated" in states
    assert states["activated"]["kind"] == "project"


def test_fr1b_domain_override_of_one_cockpit_leaf_keeps_siblings():
    child = ViewDefinition(
        name="ns-child",
        extends="base",
        node_state={"states": {
            "grounded": {"presentation": {"cockpit": {"label": "ready", "attention": "ok"}}},
        }},
    )
    resolved = resolve(child, {**DEFINITION_REGISTRY, "ns-child": child})
    grounded = resolved.node_state["states"]["grounded"]
    assert grounded["presentation"]["cockpit"]["label"] == "ready"
    assert grounded["presentation"]["navig8r"]["label"] == "Grounded"
    assert resolved.node_state["states"]["spec"]["presentation"]["cockpit"]["attention"] == "review"


def test_fr1c_node_state_is_a_section_and_round_trips():
    assert "node_state" in _SECTIONS and "surface_links" in _SECTIONS
    d = BASE_NAVIG8R_DEFINITION
    assert ViewDefinition.from_dict(json.loads(json.dumps(d.to_dict()))) == d
    assert d.node_state["states"]["spec"]["presentation"]["navig8r"]["label"] == "Spec"
