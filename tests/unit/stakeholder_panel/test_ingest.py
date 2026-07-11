# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""ingest() tests (FR-3/FR-7, OQ-7): round-trip gate, provenance header, error taxonomy."""

from __future__ import annotations

import pytest

import startd8.stakeholder_panel.adapters as reg
from startd8.stakeholder_panel.adapters import AdaptResult, AdapterError
from startd8.stakeholder_panel.ingest import (
    GENERATED_MARKER,
    IngestGateError,
    IngestResult,
    ingest,
    looks_generated,
)
from startd8.stakeholder_panel.models import PersonaBrief, Roster
from startd8.stakeholder_panel.roster import parse_roster

_ROLE_RUBRIC = (
    "roles:\n"
    "  - {key: SRE, label: Site Reliability Engineer, lens: operability, "
    "rubric: [{name: operability, description: 'prod-ready?'}]}\n"
)


@pytest.fixture(autouse=True)
def _reset_registry():
    saved, was = dict(reg._registered), reg._discovered
    yield
    reg._registered.clear()
    reg._registered.update(saved)
    reg._discovered = was


def test_ingest_role_rubric_happy_path():
    result = ingest("role-rubric", _ROLE_RUBRIC, source="/x/reviewer_roles.yaml")
    assert isinstance(result, IngestResult)
    assert [p.role_id for p in result.roster.personas] == ["sre"]
    assert result.warnings == []
    first_line = result.yaml_text.splitlines()[0]
    assert first_line.startswith(GENERATED_MARKER)
    assert "reviewer_roles.yaml" in first_line  # basename, not the abs path
    parse_roster(
        result.yaml_text
    )  # the written bytes round-trip through the strict parser


def test_unknown_format_raises_adapter_error():
    with pytest.raises(AdapterError):
        ingest("no-such-format", _ROLE_RUBRIC)


def test_malformed_source_raises_adapter_error():
    with pytest.raises(AdapterError):
        ingest("role-rubric", "- not a mapping\n")


class _GateFailingAdapter:
    """Passes adapt() but emits an invalid roster (bad role_id) → caught by the round-trip gate."""

    name = "gate-bad"

    def adapt(self, text):
        return AdaptResult(
            roster=Roster(
                personas=[PersonaBrief(role_id="Bad ID", display_name="X", goals=["g"])]
            )
        )


def test_round_trip_gate_rejects_a_bad_adapter_output():
    reg.register(_GateFailingAdapter())
    with pytest.raises(IngestGateError):
        ingest("gate-bad", "anything")


def test_header_basename_keeps_body_deterministic():
    a = ingest("role-rubric", _ROLE_RUBRIC, source="/one/place/roles.yaml")
    b = ingest("role-rubric", _ROLE_RUBRIC, source="/other/dir/roles.yaml")
    # same basename → byte-identical output; differing basename → identical body (R1-S5)
    assert a.yaml_text == b.yaml_text
    c = ingest("role-rubric", _ROLE_RUBRIC, source="/x/different-name.yaml")
    assert a.yaml_text.split("\n", 1)[1] == c.yaml_text.split("\n", 1)[1]


class _RosterErrorAdapter:
    """A misbehaving adapter that raises RosterError from adapt() (must be translated)."""

    name = "raises-roster-error"

    def adapt(self, text):
        from startd8.stakeholder_panel.roster import RosterError

        raise RosterError("boom from inside the adapter")


def test_stray_roster_error_from_adapter_is_translated_to_adapter_error():
    # Regression (review LOW): a RosterError leaking from adapt() must not reach the user as a
    # RosterError — ingest wraps it as AdapterError (the FR-9 taxonomy: not a user-roster fault).
    reg.register(_RosterErrorAdapter())
    with pytest.raises(AdapterError):
        ingest("raises-roster-error", "anything")


def test_broken_builtin_surfaces_as_adapter_error(monkeypatch):
    # Regression (review LOW): a listed-but-unimportable built-in → clean AdapterError, not a raw
    # ImportError escaping the taxonomy.
    monkeypatch.setitem(reg._BUILTINS, "role-rubric", "startd8.does.not.exist:Nope")
    reg._registered.pop("role-rubric", None)
    with pytest.raises(AdapterError, match="failed to load"):
        ingest("role-rubric", _ROLE_RUBRIC)


def test_looks_generated_helper():
    assert looks_generated(
        GENERATED_MARKER + " from x via role-rubric\ndomain: stakeholders\n"
    )
    assert not looks_generated("domain: stakeholders\n")
