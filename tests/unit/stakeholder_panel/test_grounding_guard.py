# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Grounding-guard tests (FR-7 / OQ-10, M3): catch in-scope fabrication of unsupported specifics."""

from __future__ import annotations

from startd8.stakeholder_panel.grounding_guard import (
    check_grounding,
    unsupported_specifics,
)
from startd8.stakeholder_panel.models import Grounding, PersonaBrief

_BRIEF = PersonaBrief(
    role_id="product-owner",
    display_name="Product Owner",
    goals=["ship the MVP by Q3"],
    constraints=["budget <= $5k/mo"],
    known_positions=["target 40% activation"],
)


# ── unsupported_specifics: money / percent / temporal, value-normalized ───────────


def test_money_supported_when_value_matches_even_if_format_differs():
    # $5k in the brief ≡ $5,000 in the answer — value-normalized, so NOT flagged.
    assert unsupported_specifics(_BRIEF, "We can spend up to $5,000/month.") == []


def test_money_flagged_when_not_in_brief():
    assert unsupported_specifics(_BRIEF, "The budget is $10,000.") == ["$10000"]


def test_percent_supported_and_flagged():
    assert unsupported_specifics(_BRIEF, "We target 40% activation.") == []
    assert unsupported_specifics(_BRIEF, "We need 90% uptime.") == ["90%"]


def test_temporal_supported_and_flagged():
    assert unsupported_specifics(_BRIEF, "We ship in Q3.") == []  # Q3 is in the brief
    got = unsupported_specifics(_BRIEF, "We ship in Q4 2027.")
    assert "q4" in got and "2027" in got


def test_bare_integers_are_not_flagged():
    # Conservative: only $/%/temporal are checked, so "3 goals" does not false-positive.
    assert unsupported_specifics(_BRIEF, "We have 3 main goals and 2 personas.") == []


# ── check_grounding: downgrade + flag ─────────────────────────────────────────────


def test_grounded_with_unsupported_specific_downgrades_to_uncertain():
    grounding, flags = check_grounding(
        _BRIEF, "The budget is $10,000.", Grounding.GROUNDED
    )
    assert grounding is Grounding.UNCERTAIN
    assert flags and "unsupported-specifics" in flags[0] and "$10000" in flags[0]


def test_grounded_without_specifics_stays_grounded():
    grounding, flags = check_grounding(
        _BRIEF, "Yes, that's the plan.", Grounding.GROUNDED
    )
    assert grounding is Grounding.GROUNDED
    assert flags == []


def test_deferred_and_unavailable_pass_through_unchecked():
    # A deferral asserts nothing, so it is never downgraded or flagged even with a stray number.
    g, f = check_grounding(_BRIEF, "Not my call — maybe $99999.", Grounding.DEFERRED)
    assert g is Grounding.DEFERRED and f == []
    g, f = check_grounding(_BRIEF, "(unavailable)", Grounding.UNAVAILABLE)
    assert g is Grounding.UNAVAILABLE and f == []


def test_uncertain_with_specifics_stays_uncertain_but_flags():
    # An already-hedged answer is not downgraded further, but the flag still surfaces.
    grounding, flags = check_grounding(
        _BRIEF, "Maybe around $10,000?", Grounding.UNCERTAIN
    )
    assert grounding is Grounding.UNCERTAIN
    assert flags and "$10000" in flags[0]
