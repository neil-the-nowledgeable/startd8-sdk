"""Passive ledger capture (Tier-D/C/E fuel) — state-changing writes append a transition row."""

from __future__ import annotations

import pytest

from startd8.cli_concierge import _record_transition
from startd8.kickoff_experience.activation import ActivationLedger

pytestmark = pytest.mark.unit


def test_record_transition_appends_and_dedups(tmp_path):
    led = ActivationLedger(tmp_path)
    assert led.entries() == []
    _record_transition(tmp_path)  # first observation → one row
    assert len(led.entries()) == 1
    _record_transition(tmp_path)  # unchanged signature → dedup, no new row
    assert len(led.entries()) == 1


def test_record_transition_never_raises_on_bad_root(tmp_path):
    # a path under a file (un-mkdir-able) must not raise — telemetry-grade best-effort
    bad = tmp_path / "afile"
    bad.write_text("x", encoding="utf-8")
    _record_transition(bad / "nested")  # should swallow any error
