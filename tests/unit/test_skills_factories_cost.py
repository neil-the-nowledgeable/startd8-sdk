# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Regression: skill factories built ``CostTracker()`` with no args (TypeError) on ``cost_tracking=True``."""

from __future__ import annotations

import pytest

from startd8.skills.factories import _build_cost_tracker, create_game_enhancer_agent


def test_build_cost_tracker_is_usable(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))  # isolate ~/.startd8/skill-costs.db
    tracker = _build_cost_tracker()
    assert tracker is not None
    rec = tracker.record_cost(
        agent_name="skill:test", model="claude-sonnet-4-6", input_tokens=100, output_tokens=50
    )
    assert rec.total_cost > 0


def test_cost_tracking_true_no_longer_typeerrors(tmp_path, monkeypatch):
    # Before the fix, cost_tracking=True raised `TypeError: CostTracker.__init__() missing 2 required
    # positional arguments`. It now builds a real tracker and proceeds to the SEPARATE MCP/API-key
    # validation — so a missing key raises RuntimeError (proving we got past cost construction),
    # never a TypeError.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        create_game_enhancer_agent(cost_tracking=True)
