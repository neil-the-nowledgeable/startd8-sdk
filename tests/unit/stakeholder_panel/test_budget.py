# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""budget_preflight helper tests (FR-17): estimate n*cost and delegate to BudgetManager.check_budget."""

from __future__ import annotations

import pytest

from startd8.stakeholder_panel.budget import budget_preflight


class _FakeManager:
    def __init__(self, deny_at=None):
        self.calls = []
        self._deny_at = deny_at

    def check_budget(self, *, model, project, tags, estimated_cost):
        self.calls.append(
            {
                "model": model,
                "project": project,
                "tags": tags,
                "estimated_cost": estimated_cost,
            }
        )
        if self._deny_at is not None and estimated_cost >= self._deny_at:
            raise RuntimeError("budget exceeded")


def test_estimates_cost_and_forwards_fields():
    mgr = _FakeManager()
    gate = budget_preflight(
        mgr, model="m", cost_per_question=0.01, project="p", tags=["t"]
    )
    gate(5)
    call = mgr.calls[-1]
    assert call["estimated_cost"] == pytest.approx(0.05)
    assert call["model"] == "m" and call["project"] == "p" and call["tags"] == ["t"]


def test_propagates_a_budget_denial():
    mgr = _FakeManager(deny_at=0.03)
    gate = budget_preflight(mgr, model="m", cost_per_question=0.01)
    with pytest.raises(RuntimeError):
        gate(5)  # 5 * 0.01 = 0.05 >= 0.03 → deny


def test_zero_or_negative_n_estimates_zero():
    mgr = _FakeManager()
    budget_preflight(mgr, model="m", cost_per_question=0.01)(-3)
    assert mgr.calls[-1]["estimated_cost"] == 0
