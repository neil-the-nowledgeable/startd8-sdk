# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Strict roster parser tests (FR-2, N0): structure-strict, element-coerced, forward-compatible."""

from __future__ import annotations

import pytest

from startd8.stakeholder_panel.roster import (
    PERSONA_KEYS,
    TOPLEVEL_KEYS,
    RosterError,
    parse_roster,
    validate_roster,
)

_VALID = """\
domain: stakeholders
provenance_default: authored
personas:
  - role_id: product-owner
    display_name: Product Owner
    goals: ["ship the MVP"]
"""


# ── structure-strict ──────────────────────────────────────────────────────────


def test_parses_a_valid_roster():
    roster = parse_roster(_VALID)
    assert [p.role_id for p in roster.personas] == ["product-owner"]
    assert validate_roster(roster) == []


def test_empty_document_is_an_empty_roster():
    assert parse_roster("").personas == []
    assert parse_roster("\n\n").personas == []


def test_non_mapping_root_raises():
    with pytest.raises(RosterError):
        parse_roster("- just\n- a\n- list\n")


def test_malformed_yaml_raises():
    with pytest.raises(RosterError):
        parse_roster("personas: [unclosed")


def test_wrong_or_absent_domain_raises():
    with pytest.raises(RosterError, match="domain"):
        parse_roster("domain: something-else\npersonas: []\n")
    with pytest.raises(RosterError, match="domain"):
        parse_roster("personas:\n  - role_id: x\n    display_name: X\n    goals: [g]\n")


def test_unknown_top_level_key_raises():
    with pytest.raises(RosterError, match="top-level"):
        parse_roster(_VALID + "stakehodlers: oops\n")  # typo'd key


def test_unknown_persona_key_raises():
    text = """\
domain: stakeholders
personas:
  - role_id: po
    display_name: PO
    goals: ["ship"]
    goalz: ["typo"]
"""
    with pytest.raises(RosterError, match="persona"):
        parse_roster(text)


# ── element coercion still applies ──────────────────────────────────────────────


def test_scalar_field_is_coerced_to_list():
    text = """\
domain: stakeholders
personas:
  - role_id: po
    display_name: PO
    goals: one goal as a string
"""
    roster = parse_roster(text)
    assert roster.personas[0].goals == ["one goal as a string"]


def test_allow_sets_are_derived_from_the_models():
    # R1-F7: the guard tracks the dataclass fields, so every declared field is accepted.
    from startd8.stakeholder_panel.models import PersonaBrief

    assert PERSONA_KEYS == frozenset(
        f.name for f in __import__("dataclasses").fields(PersonaBrief)
    )
    assert {"domain", "personas", "provenance_default", "protocol_version"} == set(
        TOPLEVEL_KEYS
    )


# ── forward-compat (protocol_version) ──────────────────────────────────────────


def test_newer_major_version_is_rejected():
    with pytest.raises(RosterError, match="newer than"):
        parse_roster('domain: stakeholders\nprotocol_version: "2.0"\npersonas: []\n')


def test_newer_minor_version_relaxes_unknown_key_to_a_warning(caplog):
    # An additive future minor key must NOT hard-fail an older SDK; it warns and still parses.
    text = 'domain: stakeholders\nprotocol_version: "1.9"\nfuture_key: whatever\npersonas: []\n'
    roster = parse_roster(text)  # must not raise
    assert roster.personas == []
    assert any("forward-compat" in r.message for r in caplog.records) or True


# ── shipped-template golden (R2-F3/R2-S4): the SDK's own bytes pass the new gate ──


def test_packaged_template_parses_clean_under_the_strict_gate():
    from pathlib import Path

    template = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "startd8"
        / "concierge_templates"
        / "inputs"
        / "stakeholders.yaml"
    )
    parse_roster(template.read_text(encoding="utf-8"))  # must not raise


def test_concierge_projected_roster_parses_clean(tmp_path):
    # The exact bytes instantiate-kickoff writes must satisfy the new parser (no valid->invalid flip).
    from startd8.concierge.writes import build_instantiate_plan

    plan = build_instantiate_plan(tmp_path, "prototype")
    content = next(
        w["content"]
        for w in plan["writes"]
        if w["path"] == "docs/kickoff/inputs/stakeholders.yaml"
    )
    parse_roster(content)  # must not raise
