# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Build a panel ``budget_preflight`` from the SDK budget infra (FR-17).

The panel takes an injected ``budget_preflight: Callable[[int], None]`` that raises to deny a paid
fan-out before spend. This adapts the SDK :class:`~startd8.costs.budget.BudgetManager` into that
shape so a caller can wire a real dollar ceiling instead of hand-rolling one:

    from startd8.costs.budget import BudgetManager
    from startd8.stakeholder_panel import budget_preflight, StakeholderPanel

    gate = budget_preflight(BudgetManager(store), model="anthropic:claude-haiku-4-5-20251001",
                            cost_per_question=0.01)
    panel = StakeholderPanel(roster, budget_preflight=gate)   # ask_all AND the VIPP pass honor it
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, List, Optional

if TYPE_CHECKING:  # avoid importing the costs stack at panel-import time
    from startd8.costs.budget import BudgetManager

__all__ = ["budget_preflight"]


def budget_preflight(
    manager: "BudgetManager",
    *,
    model: str,
    cost_per_question: float,
    project: str = "stakeholder-panel",
    tags: Optional[List[str]] = None,
) -> Callable[[int], None]:
    """Return a panel ``budget_preflight`` backed by *manager* (FR-17).

    The callable estimates the pass cost as ``n_questions * cost_per_question`` and calls
    ``BudgetManager.check_budget`` — which raises ``BudgetExceededError`` when a *blocking* budget
    would be exceeded, so the panel aborts (``ask_all``) or degrades (the VIPP consult pass) **before**
    any spend. ``cost_per_question`` is the caller's per-ask estimate (real cost is only known after
    the call, so the preflight is necessarily an estimate).
    """

    def _preflight(n_questions: int) -> None:
        manager.check_budget(
            model=model,
            project=project,
            tags=tags,
            estimated_cost=max(0, n_questions) * cost_per_question,
        )

    return _preflight
