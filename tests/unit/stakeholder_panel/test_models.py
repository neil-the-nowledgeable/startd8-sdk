# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Roster contract tests (FR-2): PersonaBrief / Roster shape, coercion, round-trip."""

from __future__ import annotations

from startd8.stakeholder_panel.models import PROTOCOL_VERSION, PersonaBrief, Roster


def _persona(**over):
    base = dict(
        role_id="product-owner",
        display_name="Product Owner",
        goals=["ship the MVP by Q3"],
        constraints=["budget <= $5k/mo"],
        known_positions=["no PII in logs"],
        out_of_scope=["infra choices"],
        answers_for=["Order.*"],
    )
    base.update(over)
    return PersonaBrief.from_dict(base)


def test_persona_from_dict_normalizes_scalar_to_list():
    # Authors may write a single string where a list is expected; it coerces cleanly.
    p = PersonaBrief.from_dict(
        {"role_id": "po", "display_name": "PO", "goals": "one goal"}
    )
    assert p.goals == ["one goal"]
    assert p.constraints == []


def test_persona_from_dict_strips_and_drops_blanks():
    p = PersonaBrief.from_dict(
        {"role_id": " po ", "display_name": " PO ", "goals": ["  a  ", "", "  "]}
    )
    assert p.role_id == "po"
    assert p.display_name == "PO"
    assert p.goals == ["a"]


def test_persona_round_trip():
    p = _persona()
    assert PersonaBrief.from_dict(p.to_dict()) == p


def test_persona_is_empty_ignores_identity_and_out_of_scope():
    # role_id/display_name (and even out_of_scope) alone do not make a usable persona.
    empty = PersonaBrief.from_dict(
        {"role_id": "x", "display_name": "X", "out_of_scope": ["everything"]}
    )
    assert empty.is_empty is True
    assert _persona().is_empty is False


def test_roster_from_dict_skips_non_mapping_personas():
    r = Roster.from_dict(
        {"personas": [{"role_id": "a", "display_name": "A"}, "junk", 3]}
    )
    assert [p.role_id for p in r.personas] == ["a"]


def test_roster_round_trip_and_defaults():
    r = Roster(personas=[_persona()], provenance_default="authored")
    d = r.to_dict()
    assert d["domain"] == "stakeholders"
    assert d["protocol_version"] == PROTOCOL_VERSION
    assert Roster.from_dict(d).personas == r.personas


def test_roster_persona_lookup():
    r = Roster(personas=[_persona(), _persona(role_id="end-user", display_name="User")])
    assert r.persona("end-user").display_name == "User"
    assert r.persona("missing") is None
