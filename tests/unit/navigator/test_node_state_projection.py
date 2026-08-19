"""REQ-cross-surface-view-definition FR-2 — navig8r statuses project from ``node_state``."""
from __future__ import annotations

import pytest

from startd8.navigator.sources_capability import CAPABILITY_PROFILE
from startd8.navigator.sources_requirements import REQUIREMENTS_PROFILE
from startd8.navigator.view_definition import (
    DEFINITION_REGISTRY,
    REQUIREMENTS_DEFINITION,
    ResolvedDefinition,
    ViewDefinition,
    resolve,
    to_render_profile,
)
from startd8.wireframe.profile import StatusStyle

pytestmark = pytest.mark.unit

_EXPECTED_REQUIREMENTS_STATUSES = (
    StatusStyle("grounded", "Grounded", "#3d7a57", "reuses existing code", 0),
    StatusStyle("spec", "Spec", "#6b6252", "written, not built", 2),
    StatusStyle("awaiting", "Awaiting", "#a9781a", "needs a decision", 3, True),
    StatusStyle("excluded", "Excluded", "#948b78", "out of scope", 2),
    StatusStyle("unknown", "Unknown", "#ab473a", "done-claim without Lives", 4, True),
)


def test_fr2a_requirements_projection_matches_todays_status_tuple():
    projected = to_render_profile(resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY))
    assert projected.statuses == _EXPECTED_REQUIREMENTS_STATUSES
    assert REQUIREMENTS_PROFILE.statuses == _EXPECTED_REQUIREMENTS_STATUSES


def test_fr2a_projection_reads_node_state_not_just_the_vocabulary_literal():
    """The shared taxonomy is wired: mutating a navig8r leaf changes the projected StatusStyle."""
    mutated = ViewDefinition(
        name="req-mut",
        extends="base",
        vocabulary=REQUIREMENTS_DEFINITION.vocabulary,
        node_state={"states": {
            "grounded": {"presentation": {"navig8r": {
                "label": "Grounded", "color": "#000001",
                "meaning": "reuses existing code", "severity": 0,
            }}},
        }},
    )
    prof = to_render_profile(resolve(mutated, {**DEFINITION_REGISTRY, "req-mut": mutated}))
    assert prof.statuses[0].color == "#000001"
    assert prof.statuses[0].key == "grounded"
    assert prof.statuses[1].key == "spec"  # sibling kept from inherited node_state


def test_fr2c_domain_with_its_own_status_keys_keeps_vocabulary():
    """Empty-default: capability's keys are not equal to the canonical navig8r set."""
    assert tuple(s.key for s in CAPABILITY_PROFILE.statuses) == (
        "built", "thin", "spec", "deprecated",
    )


def test_fr2c_absent_node_state_falls_back_to_vocabulary():
    orphan = ResolvedDefinition(
        vocabulary={"statuses": {
            "ok": {"label": "OK", "color": "#0a0", "meaning": "fine", "severity": 0},
        }},
    )
    assert to_render_profile(orphan).statuses == (
        StatusStyle("ok", "OK", "#0a0", "fine", 0),
    )


def test_hth_proper_subset_of_canonical_keys_is_not_an_opt_in():
    """A domain keyed {spec, awaiting} must keep its own meanings — subset ≠ shared taxonomy."""
    child = ViewDefinition(
        name="subset-child",
        extends="base",
        vocabulary={"statuses": {
            "spec": {"label": "Draft", "color": "#111111", "meaning": "domain-local spec", "severity": 1},
            "awaiting": {"label": "Hold", "color": "#222222", "meaning": "domain-local hold", "severity": 2},
        }},
    )
    prof = to_render_profile(resolve(child, {**DEFINITION_REGISTRY, "subset-child": child}))
    assert tuple((s.key, s.label, s.color) for s in prof.statuses) == (
        ("spec", "Draft", "#111111"),
        ("awaiting", "Hold", "#222222"),
    )


def test_hth_empty_vocabulary_does_not_invent_canonical_statuses():
    child = ViewDefinition(name="chrome-only", extends="base", chrome={"title": "X"})
    prof = to_render_profile(resolve(child, {**DEFINITION_REGISTRY, "chrome-only": child}))
    assert prof.statuses == ()


def test_hth_malformed_navig8r_leaf_is_skipped_not_raised():
    orphan = ResolvedDefinition(
        node_state={"states": {"grounded": {"presentation": {"navig8r": "Grounded"}}}},
        vocabulary={"statuses": {
            "ok": {"label": "OK", "color": "#0a0", "meaning": "fine", "severity": 0},
        }},
    )
    assert to_render_profile(orphan).statuses == (
        StatusStyle("ok", "OK", "#0a0", "fine", 0),
    )


def test_hth_requirements_vocab_matches_navig8r_leaves():
    """Dual-write pin: projection reads node_state values; vocab content must stay equal."""
    resolved = resolve(REQUIREMENTS_DEFINITION, DEFINITION_REGISTRY)
    vocab = resolved.vocabulary["statuses"]
    states = resolved.node_state["states"]
    nav_keys = {
        sid for sid, spec in states.items()
        if isinstance(spec, dict) and (spec.get("presentation") or {}).get("navig8r")
    }
    assert set(vocab) == nav_keys
    for sid, spec in vocab.items():
        assert spec == states[sid]["presentation"]["navig8r"]
