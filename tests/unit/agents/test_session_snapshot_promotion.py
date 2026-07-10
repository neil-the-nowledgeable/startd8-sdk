"""Promoted agentic-session snapshot core (roadmap Tier 3).

The presentation-neutral snapshot lives in the agents layer now, and any AgenticSession can serialize
itself via `to_snapshot()`. These assert the neutral builder (redactor injection) and the
AgenticSession method, plus the kickoff re-export compat.
"""

from __future__ import annotations

import pytest

from startd8.agents import session_snapshot as neutral
from startd8.agents.agentic import AgenticSession, ToolRegistry

pytestmark = pytest.mark.unit

SECRET = "sk-ant-ABCDEFGH1234567890abcdefghij"


class _ToolAgent:
    """Minimal tool-capable agent stub (AgenticSession only reads .model here)."""

    name = "stub"
    model = "stub-model"

    def supports_tool_use(self) -> bool:
        return True


def _session():
    s = AgenticSession(_ToolAgent(), ToolRegistry([]))
    s.messages = [
        {"role": "user", "content": f"my key is {SECRET}"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "noted"},
                {"type": "tool_use", "id": "t1", "name": "survey", "input": {"argkey": "zzztopsecretarg"}},
            ],
        },
    ]
    s.total_tokens, s.total_input_tokens, s.total_output_tokens, s.total_cost_usd = 30, 20, 10, 0.02
    return s


def test_neutral_build_snapshot_default_is_no_redaction():
    snap = neutral.build_snapshot(
        messages=[{"role": "user", "content": SECRET}],
        model="m", input_tokens=0, output_tokens=0, total_tokens=0, cost_usd=0.0,
        posture="agentic", project="p", session_id="s", generated_at="t",
    )
    # no redactor → the neutral layer is policy-free (identity)
    assert SECRET in snap.turns[0].text


def test_neutral_build_snapshot_applies_injected_redactor():
    snap = neutral.build_snapshot(
        messages=[{"role": "user", "content": SECRET}],
        model="m", input_tokens=0, output_tokens=0, total_tokens=0, cost_usd=0.0,
        posture="agentic", project="p", session_id="s", generated_at="t",
        redactor=lambda x: x.replace(SECRET, "«REDACTED»"),
    )
    assert SECRET not in snap.turns[0].text and "«REDACTED»" in snap.turns[0].text


def test_agentic_session_to_snapshot():
    snap = _session().to_snapshot(project="proj", session_id="sid", generated_at="ts")
    assert snap.cost.model == "stub-model"
    assert snap.cost.total_tokens == 30
    assert snap.turns[1].tool_calls == ("survey",)  # tool NAME only, args dropped
    assert "zzztopsecretarg" not in snap.to_json()  # no tool args persisted


def test_to_snapshot_redactor_scrubs_transcript():
    snap = _session().to_snapshot(
        project="proj", session_id="sid", generated_at="ts",
        redactor=lambda x: x.replace(SECRET, "«X»"),
    )
    assert SECRET not in snap.to_json()


def test_kickoff_reexports_the_neutral_names():
    # compat: the kickoff import path still resolves the promoted names.
    from startd8.kickoff_experience import session_snapshot as ks

    assert ks.AgenticSessionSnapshot is neutral.AgenticSessionSnapshot
    assert ks.SNAPSHOT_SCHEMA_VERSION == neutral.SNAPSHOT_SCHEMA_VERSION
    # and the kickoff builder redacts (VIPP-parity redactor wired in)
    snap = ks.build_session_snapshot(
        messages=[{"role": "user", "content": f"key {SECRET}"}],
        model="m", input_tokens=0, output_tokens=0, total_tokens=0, cost_usd=0.0,
        posture="kickoff · read-only", project="p", session_id="s", generated_at="t",
    )
    assert SECRET not in snap.to_json()
