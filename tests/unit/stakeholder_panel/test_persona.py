# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Persona tests (FR-5/FR-6/FR-7/FR-16): prompt bounding, grounding parse, history, failure degrade."""

from __future__ import annotations

import asyncio

import pytest

from startd8.stakeholder_panel.models import Grounding, PersonaBrief
from startd8.stakeholder_panel.persona import (
    Persona,
    compile_system_prompt,
    parse_grounding,
)

from .conftest import ScriptedAgent

_BRIEF = PersonaBrief(
    role_id="product-owner",
    display_name="Product Owner",
    goals=["ship the MVP by Q3"],
    out_of_scope=["database engine choice"],
)


def test_system_prompt_states_defer_rule_and_grounding_contract():
    sp = compile_system_prompt(_BRIEF)
    assert "Product Owner" in sp and "ship the MVP by Q3" in sp
    assert "DEFER" in sp and "Do NOT invent" in sp
    assert "GROUNDING:" in sp


@pytest.mark.parametrize(
    "raw,expected_text,expected",
    [
        ("Yes.\nGROUNDING: grounded", "Yes.", Grounding.GROUNDED),
        ("Maybe.\nGROUNDING: uncertain", "Maybe.", Grounding.UNCERTAIN),
        ("Not my call.\nGROUNDING: deferred", "Not my call.", Grounding.DEFERRED),
        ("No marker here", "No marker here", Grounding.UNCERTAIN),
        ("Weird.\nGROUNDING: banana", "Weird.", Grounding.UNCERTAIN),
    ],
)
def test_parse_grounding(raw, expected_text, expected):
    text, grounding = parse_grounding(raw)
    assert text == expected_text
    assert grounding is expected


def test_ask_returns_grounded_answer_with_provenance():
    agent = ScriptedAgent(reply="We must ship by Q3.\nGROUNDING: grounded")
    persona = Persona(_BRIEF, agent)
    ans = asyncio.run(persona.ask("When do we ship?"))
    assert ans.text == "We must ship by Q3."
    assert ans.grounding is Grounding.GROUNDED
    assert ans.role_id == "product-owner"
    assert ans.brief_hash.startswith("sha256:")
    assert ans.output_tokens > 0
    assert ans.available is True


def test_ask_guard_downgrades_grounded_fabrication_and_flags():
    # FR-7 (M3): the persona claims "grounded" but asserts a $ figure absent from the brief.
    agent = ScriptedAgent(reply="The budget is $12,000.\nGROUNDING: grounded")
    persona = Persona(_BRIEF, agent)
    ans = asyncio.run(persona.ask("How much can we spend?"))
    assert ans.grounding is Grounding.UNCERTAIN  # downgraded, not trusted
    assert ans.flags and "$12000" in ans.flags[0]


def test_ask_grounded_answer_within_brief_keeps_no_flags():
    agent = ScriptedAgent(reply="We ship the MVP by Q3.\nGROUNDING: grounded")
    persona = Persona(_BRIEF, agent)  # brief goal mentions "by Q3"
    ans = asyncio.run(persona.ask("When do we ship?"))
    assert ans.grounding is Grounding.GROUNDED
    assert ans.flags == []


def test_ask_passes_system_prompt_to_agent():
    agent = ScriptedAgent()
    persona = Persona(_BRIEF, agent)
    asyncio.run(persona.ask("hi"))
    _prompt, system_prompt = agent.calls[-1]
    assert system_prompt == persona.system_prompt


def test_ask_degrades_to_unavailable_on_agent_failure():
    agent = ScriptedAgent(raises=TimeoutError("boom"))
    persona = Persona(_BRIEF, agent)
    ans = asyncio.run(persona.ask("anything"))  # must NOT raise (FR-16)
    assert ans.grounding is Grounding.UNAVAILABLE
    assert ans.available is False
    assert "unavailable" in ans.text
    assert ans.brief_hash.startswith("sha256:")  # provenance still stamped


def test_history_is_threaded_into_later_prompts():
    agent = ScriptedAgent(reply="ok\nGROUNDING: grounded")
    persona = Persona(_BRIEF, agent)
    asyncio.run(persona.ask("first question"))
    asyncio.run(persona.ask("second question"))
    last_prompt, _ = agent.calls[-1]
    assert "first question" in last_prompt
    assert "second question" in last_prompt


def test_history_is_capped():
    agent = ScriptedAgent(reply="ok\nGROUNDING: grounded")
    persona = Persona(_BRIEF, agent, history_turns=2)
    for i in range(5):
        asyncio.run(persona.ask(f"q{i}"))
    last_prompt, _ = agent.calls[-1]
    # Only the last 2 prior turns are threaded; q0/q1 have aged out.
    assert "q0" not in last_prompt and "q1" not in last_prompt
    assert "q3" in last_prompt


def test_history_turns_zero_keeps_no_memory():
    # Regression: history_turns=0 means STATELESS — it must not grow the prompt every turn.
    agent = ScriptedAgent(reply="ok\nGROUNDING: grounded")
    persona = Persona(_BRIEF, agent, history_turns=0)
    for i in range(4):
        asyncio.run(persona.ask(f"question {i}"))
    assert persona._history == []
    last_prompt, _ = agent.calls[-1]
    assert "question 0" not in last_prompt  # no prior turns threaded


def test_concurrent_asks_to_one_persona_are_serialized():
    # FR-20: the per-persona lock keeps concurrent asks from racing the shared history.
    agent = ScriptedAgent(reply="ok\nGROUNDING: grounded", delay=0.02)
    persona = Persona(_BRIEF, agent)

    async def run():
        return await asyncio.gather(persona.ask("a"), persona.ask("b"))

    results = asyncio.run(run())
    assert len(results) == 2
    assert len(persona._history) == 2  # both recorded, no lost update
