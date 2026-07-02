# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Routing tests (FR-9c / OQ-9): explicit answers_for match, no-match, deterministic tie-break."""

from __future__ import annotations

from startd8.stakeholder_panel.models import PersonaBrief
from startd8.stakeholder_panel.routing import persona_matches, route

_PO = PersonaBrief(
    role_id="product-owner",
    display_name="PO",
    goals=["ship"],
    answers_for=["Order.*", "pricing"],
)
_USER = PersonaBrief(
    role_id="end-user",
    display_name="User",
    goals=["checkout fast"],
    answers_for=["checkout"],
)


def test_prefix_match_on_entity_and_field():
    assert persona_matches(_PO, "Order") is True
    assert persona_matches(_PO, "Order.total") is True
    assert persona_matches(_PO, "pricing") is True
    assert persona_matches(_PO, "pricing.tier") is True


def test_no_match_returns_false():
    assert persona_matches(_PO, "checkout") is False
    assert persona_matches(_PO, "") is False
    assert (
        persona_matches(PersonaBrief(role_id="x", display_name="X"), "Order") is False
    )


def test_route_picks_matching_persona():
    assert route([_PO, _USER], "Order.total") == "product-owner"
    assert route([_PO, _USER], "checkout.step") == "end-user"


def test_route_no_match_stays_omit():
    # FR-9c: no persona matches → None (the caller keeps the question as OMIT).
    assert route([_PO, _USER], "Warehouse.shelf") is None


def test_route_ambiguous_is_deterministic_first_in_order():
    both_a = PersonaBrief(role_id="a", display_name="A", answers_for=["Order.*"])
    both_b = PersonaBrief(role_id="b", display_name="B", answers_for=["Order.*"])
    # Roster order is the tie-break, never arbitrary.
    assert route([both_a, both_b], "Order.total") == "a"
    assert route([both_b, both_a], "Order.total") == "b"
