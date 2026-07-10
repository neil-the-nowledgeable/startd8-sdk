"""Tier-D momentum folds into the single oracle + surfaces in `kickoff status`."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from startd8.cli_concierge import kickoff_kernel_app
from startd8.kickoff_experience.activation import ActivationLedger
from startd8.kickoff_experience.agentic_view import kickoff_status

pytestmark = pytest.mark.unit
runner = CliRunner()


def _seed_ledger(tmp_path, *percents):
    led = ActivationLedger(tmp_path)
    for i, p in enumerate(percents):
        # distinct signature per row so each is recorded (readiness differs or blocked nonce moves)
        led.record({"readiness_percent": p, "attention_counts": {"blocked": i}}, now=f"t{i}")


def test_oracle_to_dict_carries_momentum_and_leverage_keys(tmp_path):
    s = kickoff_status(tmp_path)  # empty project — keys present, degrade cleanly
    assert s["schema"] == "startd8.kickoff.status.v1"
    assert s["momentum"]["trend"] == "unknown"
    assert s["leverage"] == [] and s["leverage_nudge"] is None
    json.dumps(s)  # still fully serializable


def test_momentum_reflects_ledger_history(tmp_path):
    _seed_ledger(tmp_path, 40, 70)
    s = kickoff_status(tmp_path)
    assert s["momentum"]["trend"] == "rising"
    assert s["momentum"]["latest"] == 70 and s["momentum"]["previous"] == 40


def test_status_cli_shows_stalled_momentum(tmp_path):
    _seed_ledger(tmp_path, 60, 60)
    out = runner.invoke(kickoff_kernel_app, ["status", str(tmp_path)])
    assert out.exit_code == 0 and "stalled at 60%" in out.output
