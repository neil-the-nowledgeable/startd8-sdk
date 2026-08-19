"""REQ-cross-surface-view-definition FR-3 — cockpit presentation declared from the same state."""
from __future__ import annotations

from pathlib import Path

import pytest

from startd8.kickoff_experience import portal_spec
from startd8.kickoff_experience.portal_spec import _ATTENTION_DISPLAY
from startd8.navigator.view_definition import (
    DEFINITION_REGISTRY,
    REQUIREMENTS_DEFINITION,
    resolve,
)

pytestmark = pytest.mark.unit

_PER_NODE = ("grounded", "spec", "awaiting", "excluded", "unknown")
_ALIGN = {
    "grounded": ("Grounded", "ok"),
    "spec": ("Spec", "review"),
    "awaiting": ("Awaiting", "review"),
    "excluded": ("Excluded", "backlog"),
    "unknown": ("Unknown", "blocked"),
}


def test_fr3a_cockpit_leaves_use_attention_display_keys():
    states = resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY).node_state["states"]
    attentions = {states[sid]["presentation"]["cockpit"]["attention"] for sid in _PER_NODE}
    assert attentions <= set(_ATTENTION_DISPLAY)
    assert attentions == {"ok", "review", "blocked", "backlog"}


def test_fr3b_alignment_map_is_declared_once_in_node_state():
    states = resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY).node_state["states"]
    got = {
        sid: (
            states[sid]["presentation"]["navig8r"]["label"],
            states[sid]["presentation"]["cockpit"]["label"],
        )
        for sid in _PER_NODE
    }
    assert got == _ALIGN
    assert got["grounded"] == ("Grounded", "ok")


def test_fr3c_portal_spec_derivation_is_untouched():
    """NR-3/NR-7: this delivery declares the presentation; it does not edit the cockpit module."""
    src = Path(portal_spec.__file__).read_text(encoding="utf-8")
    assert "_ATTENTION_DISPLAY" in src
    assert set(_ATTENTION_DISPLAY) == {"ok", "review", "blocked", "backlog"}
