# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Shared test doubles for the Stakeholder Panel M1 tests.

A ``ScriptedAgent`` is a duck-typed stand-in for a ``BaseAgent`` (persona code only calls
``agenerate`` and reads ``.model``), so tests never need provider keys. ``SpyTracker`` captures
``record_cost`` kwargs to assert FR-13 attribution.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Callable, Optional

import pytest

from startd8.models import GenerateResult, TokenUsage
from startd8.stakeholder_panel.models import PersonaBrief, Roster


class ScriptedAgent:
    """Deterministic agent double: fixed/callable reply, optional raise, optional delay."""

    def __init__(
        self,
        name: str = "persona",
        model: str = "fake-model",
        reply: str | Callable[[str], str] = "I think so.\nGROUNDING: grounded",
        raises: Optional[BaseException] = None,
        delay: float = 0.0,
    ) -> None:
        self.name = name
        self.model = model
        self._reply = reply
        self._raises = raises
        self._delay = delay
        self.calls: list = []  # (prompt, system_prompt) per call

    async def agenerate(
        self, prompt: str, system_prompt: Optional[str] = None, **_kw
    ) -> GenerateResult:
        self.calls.append((prompt, system_prompt))
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._raises is not None:
            raise self._raises
        text = self._reply(prompt) if callable(self._reply) else self._reply
        inp, out = len(prompt.split()), len(text.split())
        usage = TokenUsage(
            input=inp, output=out, total=inp + out, model_name=self.model
        )
        return GenerateResult(text, 1, usage)


class SpyTracker:
    """Captures record_cost kwargs; returns a record with a fixed total_cost."""

    def __init__(self, total_cost: float = 0.001) -> None:
        self.records: list = []
        self._total = total_cost

    def record_cost(self, **kwargs):
        self.records.append(kwargs)
        return SimpleNamespace(total_cost=self._total)


@pytest.fixture
def two_persona_roster() -> Roster:
    return Roster(
        personas=[
            PersonaBrief(
                role_id="product-owner",
                display_name="Product Owner",
                goals=["ship the MVP"],
                out_of_scope=["infra"],
            ),
            PersonaBrief(
                role_id="end-user",
                display_name="End User",
                known_positions=["wants one-click checkout"],
            ),
        ]
    )


@pytest.fixture
def scripted_factory():
    """Return a factory building a fresh ScriptedAgent per persona, plus a registry to inspect."""
    built: dict = {}

    def make(reply="Sure.\nGROUNDING: grounded", raises=None, delay=0.0):
        def factory(brief):
            agent = ScriptedAgent(
                name=f"persona:{brief.role_id}", reply=reply, raises=raises, delay=delay
            )
            built[brief.role_id] = agent
            return agent

        factory.built = built
        return factory

    return make
