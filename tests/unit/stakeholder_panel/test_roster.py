# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Roster load / validate / assess tests (FR-1/FR-4)."""

from __future__ import annotations

import pytest

from startd8.stakeholder_panel import (
    RosterError,
    assess_roster,
    load_roster,
    validate_roster,
)

_VALID = """\
domain: stakeholders
provenance_default: authored
personas:
  - role_id: product-owner
    display_name: Product Owner
    goals: ["ship the MVP"]
    out_of_scope: ["infra"]
  - role_id: end-user
    display_name: Representative End User
    known_positions: ["wants one-click checkout"]
"""


def _write(tmp_path, text, name="stakeholders.yaml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# ── load ──────────────────────────────────────────────────────────────────────


def test_load_valid_roster(tmp_path):
    r = load_roster(_write(tmp_path, _VALID))
    assert [p.role_id for p in r.personas] == ["product-owner", "end-user"]
    assert r.provenance_default == "authored"


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(RosterError):
        load_roster(tmp_path / "nope.yaml")


def test_load_malformed_yaml_raises(tmp_path):
    with pytest.raises(RosterError):
        load_roster(_write(tmp_path, "personas: [unclosed"))


def test_load_non_mapping_raises(tmp_path):
    with pytest.raises(RosterError):
        load_roster(_write(tmp_path, "- just\n- a\n- list\n"))


def test_load_empty_file_is_empty_roster(tmp_path):
    # An empty document loads (no *load* failure); it fails *validation* instead.
    r = load_roster(_write(tmp_path, ""))
    assert r.personas == []


# ── validate (FR-4) ─────────────────────────────────────────────────────────────


def test_validate_clean_roster_has_no_issues(tmp_path):
    assert validate_roster(load_roster(_write(tmp_path, _VALID))) == []


def test_validate_flags_no_personas(tmp_path):
    issues = validate_roster(load_roster(_write(tmp_path, "domain: stakeholders\n")))
    assert any("no personas" in i for i in issues)


def test_validate_flags_duplicate_role_id(tmp_path):
    text = _VALID + """\
  - role_id: product-owner
    display_name: Dupe
    goals: ["x"]
"""
    issues = validate_roster(load_roster(_write(tmp_path, text)))
    assert any("duplicate role_id 'product-owner'" in i for i in issues)


def test_validate_flags_empty_brief(tmp_path):
    text = """\
personas:
  - role_id: ghost
    display_name: Ghost
    out_of_scope: ["everything"]
"""
    issues = validate_roster(load_roster(_write(tmp_path, text)))
    assert any("empty brief" in i for i in issues)


def test_validate_flags_missing_fields_and_bad_role_id():
    from startd8.stakeholder_panel.models import Roster

    r = Roster.from_dict(
        {"personas": [{"role_id": "Bad ID", "display_name": "", "goals": ["g"]}]}
    )
    issues = validate_roster(r)
    assert any("kebab-case" in i for i in issues)
    assert any("missing display_name" in i for i in issues)


# ── assess (FR-4 + R2-S5) ────────────────────────────────────────────────────────


def test_assess_absent(tmp_path):
    assert assess_roster(tmp_path / "stakeholders.yaml") == {"status": "absent"}


def test_assess_invalid_on_validation_failure(tmp_path):
    got = assess_roster(_write(tmp_path, "domain: stakeholders\n"))
    assert got["status"] == "invalid"
    assert got["issues"]


def test_assess_invalid_on_malformed(tmp_path):
    got = assess_roster(_write(tmp_path, "personas: [unclosed"))
    assert got["status"] == "invalid"
    assert "error" in got


def test_assess_present_reports_personas(tmp_path):
    got = assess_roster(_write(tmp_path, _VALID))
    assert got["status"] == "present"
    assert got["persona_count"] == 2
    assert got["role_ids"] == ["product-owner", "end-user"]
