"""REQ-cross-surface-view-definition FR-3 — cockpit presentation declared from the same state."""
from __future__ import annotations

from pathlib import Path

import pytest

from startd8.kickoff_experience import portal_spec
from startd8.kickoff_experience.portal_spec import _ATTENTION_DISPLAY, attention_colors
from startd8.navigator.view_definition import (
    DEFINITION_REGISTRY,
    REQUIREMENTS_DEFINITION,
    cockpit_attention_colors,
    cockpit_statuses_from_node_state,
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


def test_fr3c_portal_spec_glyphs_unchanged_and_colors_come_from_node_state():
    """EC-CS-8: glyphs stay local; paint syncs with shared cockpit colors (NR-7 glyphs half)."""
    src = Path(portal_spec.__file__).read_text(encoding="utf-8")
    assert "_ATTENTION_DISPLAY" in src
    assert set(_ATTENTION_DISPLAY) == {"ok", "review", "blocked", "backlog"}
    assert _ATTENTION_DISPLAY["ok"] == ("✅", "confirmed")
    shared = cockpit_attention_colors(
        resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY).node_state
    )
    assert attention_colors() == shared
    assert shared == {
        "ok": "#3d7a57",
        "review": "#a9781a",
        "backlog": "#948b78",
        "blocked": "#ab473a",
    }


def test_ec_cs_3_cockpit_projector_skips_project_kind_and_is_the_validate_read_model():
    """Public projector: per-node cockpit leaves only; activated (kind=project) omitted."""
    states = resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY).node_state
    cockpit = cockpit_statuses_from_node_state(states)
    assert set(cockpit) == set(_PER_NODE)
    assert "activated" not in cockpit
    assert cockpit["grounded"]["attention"] == "ok"
    assert cockpit["unknown"]["attention"] == "blocked"
    # Malformed / empty → omitted (same skip class as the navig8r projector).
    assert cockpit_statuses_from_node_state({
        "states": {
            "grounded": {"presentation": {"cockpit": "ok"}},
            "spec": {"kind": "project", "presentation": {"cockpit": {"attention": "ok"}}},
        },
    }) == {}


def test_ec_cs_8_badge_css_reads_shared_cockpit_colors():
    """web._BADGE glyphs unchanged; CSS paint comes from presentation.cockpit.color."""
    from startd8.kickoff_experience.web import _BADGE, _badge_extra_css

    assert _BADGE["ok"] == ("✓", "badge-ok")
    css = _badge_extra_css()
    assert ".badge-ok{color:#3d7a57}" in css
    assert ".badge-review{color:#a9781a}" in css
    assert ".badge-blocked{color:#ab473a}" in css
    assert ".badge-backlog{color:#948b78}" in css
    # Pre-EC-CS-8 local fallbacks must not win when shared colors are present.
    assert "var(--color-success)" not in css
    assert "#b45309" not in css
