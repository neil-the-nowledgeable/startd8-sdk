# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""role-rubric adapter tests (FR-5): pinned mapping, input-shape guard, round-trip through parse_roster."""

from __future__ import annotations

import yaml
import pytest

from startd8.stakeholder_panel.adapters import AdapterError
from startd8.stakeholder_panel.adapters.role_rubric import RoleRubricAdapter
from startd8.stakeholder_panel.roster import parse_roster, validate_roster

_SRC = """\
version: 1
frontend_services: [frontend]
roles:
  - key: SE_MANAGER
    label: Software Engineering Manager
    lens: overall fitness, maintainability
    coverage: { scope: round_level }
    rubric:
      - { name: overall_fitness, description: "Is this fit-for-purpose?" }
      - { name: risk, description: "Residual risk." }
  - key: SRE
    label: Site Reliability Engineer
    lens: operability
    coverage: { scope: per_cell, mandatory: true }
    out_of_scope: ["business logic correctness"]
    rubric:
      - { name: operability, description: "Can it run in prod?" }
"""


def _adapt(text=_SRC):
    return RoleRubricAdapter().adapt(text)


def test_pinned_mapping_field_by_field():
    roster = _adapt().roster
    se, sre = roster.personas
    assert se.role_id == "se-manager"
    assert se.display_name == "Software Engineering Manager"
    assert se.goals == ["Review through the lens of: overall fitness, maintainability."]
    assert se.known_positions == [
        "overall_fitness: Is this fit-for-purpose?",
        "risk: Residual risk.",
    ]
    assert se.answers_for == ["overall_fitness", "risk"]  # rubric names → routing keys
    assert se.constraints == [
        "You sign off at the round level, not per individual service."
    ]


def test_coverage_and_out_of_scope_mapping():
    sre = _adapt().roster.personas[1]
    assert sre.constraints == ["You are assigned to every reviewable service."]
    assert sre.out_of_scope == ["business logic correctness"]  # pass-through


def test_result_is_lossless_and_valid():
    result = _adapt()
    assert result.warnings == []
    assert validate_roster(result.roster) == []


def test_output_round_trips_through_parse_roster():
    roster = _adapt().roster
    reparsed = parse_roster(yaml.safe_dump(roster.to_dict()))
    assert [p.role_id for p in reparsed.personas] == ["se-manager", "sre"]


# ── input-shape guard (R1-S6) ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "bad",
    [
        "- not\n- a\n- mapping\n",
        "roles: []\n",
        "roles:\n  - label: No Key\n    rubric: []\n",  # missing key
        "roles:\n  - key: k\n    rubric: []\n",  # missing label
        "roles:\n  - key: k\n    label: L\n",  # missing rubric
        "roles:\n  - key: k\n    label: L\n    rubric: not-a-list\n",  # rubric wrong type
    ],
)
def test_malformed_source_raises_adapter_error(bad):
    with pytest.raises(AdapterError):
        _adapt(bad)


def test_malformed_coverage_and_scalars_do_not_crash():
    # Regression (review HIGH/MED): non-dict coverage, string applies_to_services / out_of_scope, and
    # a dim missing a name must NOT raise a raw AttributeError/TypeError — they coerce or drop.
    src = """\
roles:
  - key: k
    label: L
    lens: quality
    coverage: round_level          # scalar, not a mapping
    out_of_scope: pricing          # scalar, not a list
    rubric:
      - {name: good, description: solid}
      - {description: nameless}     # missing name → dropped
"""
    persona = _adapt(src).roster.personas[0]
    assert persona.constraints == []  # unusable coverage → no constraint, no crash
    assert persona.out_of_scope == ["pricing"]  # coerced to a 1-element list, not chars
    assert persona.known_positions == ["good: solid"]  # nameless dim dropped
    assert persona.answers_for == ["good"]


def test_string_applies_to_services_is_not_char_split():
    src = """\
roles:
  - key: fe
    label: FE
    lens: ui
    coverage: {applies_to_services: frontend}
    rubric: [{name: ux, description: markup}]
"""
    persona = _adapt(src).roster.personas[0]
    assert persona.constraints == ["You review only these services: frontend."]


def test_duplicate_keys_produce_an_adapter_error():
    # A well-formed source that yields a dup role_id is a source defect (defense-in-depth, R2-S1).
    dup = """\
roles:
  - key: dup
    label: A
    rubric: [{name: x, description: y}]
  - key: dup
    label: B
    rubric: [{name: z, description: w}]
"""
    with pytest.raises(AdapterError, match="invalid roster"):
        _adapt(dup)
