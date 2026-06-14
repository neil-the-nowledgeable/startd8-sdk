"""Unit tests for AgentInsightBridge emission surface (T0.2/T0.3 / FR-27/FR-28).

Hermetic: ContextCore's ``agent`` submodule is not installed in CI, so we inject a fake
``contextcore.agent`` into ``sys.modules`` providing the five symbols the bridge imports.
"""

import sys
import types
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pytest

from startd8.integrations.contextcore import AgentInsightBridge

FAKE_KEY = "sk-ant-" + "Z" * 40


class _InsightType(str, Enum):
    ANALYSIS = "analysis"
    RECOMMENDATION = "recommendation"
    DECISION = "decision"
    QUESTION = "question"
    BLOCKER = "blocker"
    DISCOVERY = "discovery"
    RISK = "risk"
    PROGRESS = "progress"
    LESSON = "lesson"


class _InsightAudience(str, Enum):
    AGENT = "agent"
    HUMAN = "human"
    BOTH = "both"


@dataclass
class _Evidence:
    type: str
    ref: str
    description: Optional[str] = None
    query: Optional[str] = None
    timestamp: Optional[str] = None


class _RecordingEmitter:
    def __init__(self, **kwargs):
        self.calls = []

    def emit(self, insight_type, summary, confidence, **kwargs):
        self.calls.append(
            {"type": insight_type, "summary": summary, "confidence": confidence, **kwargs}
        )
        return object()


class _Querier:
    def __init__(self, **kwargs):
        pass


@pytest.fixture
def bridge(monkeypatch):
    """A bridge wired to a recording emitter via a fake contextcore.agent module."""
    fake = types.ModuleType("contextcore.agent")
    fake.InsightType = _InsightType
    fake.InsightAudience = _InsightAudience
    fake.Evidence = _Evidence
    fake.InsightEmitter = _RecordingEmitter
    fake.InsightQuerier = _Querier
    monkeypatch.setitem(sys.modules, "contextcore.agent", fake)

    b = AgentInsightBridge(project_id="startd8-benchmark", agent_id="claude-opus-4-8")
    # _initialize ran in __init__ using the fake; emitter is our recorder
    assert b.enabled, "bridge should initialize against the fake contextcore.agent"
    assert isinstance(b._emitter, _RecordingEmitter)
    return b


@pytest.mark.parametrize(
    "method,expected_type",
    [
        ("emit_decision", "decision"),
        ("emit_lesson", "lesson"),
        ("emit_risk", "risk"),
        ("emit_blocker", "blocker"),
        ("emit_progress", "progress"),
        ("emit_discovery", "discovery"),
    ],
)
def test_each_type_routes_to_emit(bridge, method, expected_type):
    ok = getattr(bridge, method)("a summary", 0.9)
    assert ok is True
    assert bridge._emitter.calls[-1]["type"].value == expected_type


def test_emit_question_no_attribute_error(bridge):
    """FR-28 regression: emit_question must not raise AttributeError and must route through emit()."""
    ok = bridge.emit_question("Which budget ceiling?", blocking=True, options=["$10", "$40"])
    assert ok is True
    call = bridge._emitter.calls[-1]
    assert call["type"].value == "question"
    assert call["audience"].value == "human"  # questions target humans


def test_evidence_audience_supersedes_round_trip(bridge):
    """FR-27b/FR-15/FR-16: evidence/audience/supersedes reach the emitter."""
    ok = bridge.emit_decision(
        "Cut Cursor from Round 1",
        0.95,
        rationale="no public inference API",
        evidence=[{"type": "doc", "ref": "INVESTIGATION_CURSOR_AGENT_ERROR.md"}],
        audience="both",
        supersedes="insight-123",
    )
    assert ok is True
    call = bridge._emitter.calls[-1]
    assert call["audience"].value == "both"
    assert call["supersedes"] == "insight-123"
    assert isinstance(call["evidence"][0], _Evidence)
    assert call["evidence"][0].ref == "INVESTIGATION_CURSOR_AGENT_ERROR.md"


def test_summary_and_evidence_are_redacted(bridge):
    """FR-19: secrets/paths scrubbed before reaching the emitter."""
    bridge.emit_risk(
        f"leak risk {FAKE_KEY}",
        0.8,
        evidence=[{"type": "file", "ref": "/Users/neil/secret.env"}],
    )
    call = bridge._emitter.calls[-1]
    assert FAKE_KEY not in call["summary"]
    assert "/Users/neil/" not in call["evidence"][0].ref


def test_disabled_bridge_returns_false_without_emitter():
    """No contextcore.agent → graceful mock, no raise."""
    b = AgentInsightBridge.__new__(AgentInsightBridge)
    b.project_id, b.agent_id, b.session_id = "p", "a", "s"
    b._emitter, b._querier, b._enabled = None, None, False
    assert b.emit_decision("x") is False
    assert b.emit_question("y?") is False
