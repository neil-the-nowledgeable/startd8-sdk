"""Phase 2 — ContextCore agentic integration (FR-CC1/CC2/CC3/CC4).

FR-CC1/CC2: observer + task-lifecycle adapter, driven by a recording fake tracker (no ContextCore
install needed). FR-CC3: the agentic.session descriptor is collectable. FR-CC4: dogfood — a real
agentic.session span is emitted and queried back via an in-memory exporter."""

from __future__ import annotations

import pytest

from startd8.agents.mock import MockAgent
from startd8.agents.agentic import AgenticSession, ToolRegistry, ToolSpec
from startd8.integrations.contextcore_agentic import (
    ContextCoreAgenticAdapter,
    ContextCoreProgressObserver,
    ProgressEmitter,
)


class _FakeTracker:
    """Records the TaskTrackerWrapper calls the observer/adapter make (no ContextCore needed)."""

    def __init__(self):
        self.calls: list = []

    def start_task(self, task_id, title, task_type="task", **kw):
        self.calls.append(("start_task", task_id, task_type)); return True

    def update_status(self, task_id, status):
        self.calls.append(("update_status", task_id, status)); return True

    def add_event(self, task_id, event_name, attributes=None):
        self.calls.append(("add_event", event_name, attributes or {})); return True

    def complete_task(self, task_id):
        self.calls.append(("complete_task", task_id)); return True

    def fail_task(self, task_id, reason):
        self.calls.append(("fail_task", task_id, reason)); return True

    # convenience views
    def events(self):
        return [c for c in self.calls if c[0] == "add_event"]

    def event_names(self):
        return [c[1] for c in self.events()]


def _echo_tool(log):
    def handler(args):
        log.append(args); return "echo"
    return ToolSpec("echo", "echo", {"type": "object"}, handler, effect_class="read")


# --- FR-CC1: the observer satisfies the ProgressEmitter protocol and emits per-event ----------------
def test_observer_satisfies_protocol_and_emits():
    tracker = _FakeTracker()
    obs = ContextCoreProgressObserver(tracker, "task-1")
    assert isinstance(obs, ProgressEmitter)

    from startd8.models import ToolCallStarted, ToolCallResult, TurnComplete, CompactionEvent
    obs.on_event(ToolCallStarted("c1", "survey"))
    obs.on_event(ToolCallResult("c1", "survey", True))
    obs.on_event(TurnComplete(None))
    obs.on_event(CompactionEvent(1))

    names = tracker.event_names()
    assert names == [
        "agentic.tool_call_started", "agentic.tool_call_result",
        "agentic.turn_complete", "agentic.compaction",
    ]


# --- FR-CC2: a successful run becomes a tracked task with the SpanState-v2 lifecycle ----------------
@pytest.mark.asyncio
async def test_adapter_tracks_a_successful_run():
    tracker = _FakeTracker()
    agent = MockAgent(model="mock-model", streaming=True, tool_turns=[
        {"tool_calls": [("c1", "echo", {"x": 1})]},
        {"text": "done", "tool_calls": []},
    ])
    session = AgenticSession(agent, ToolRegistry([_echo_tool([])]))
    adapter = ContextCoreAgenticAdapter(session, project_id="proj", task_id="run-1", tracker=tracker)

    forwarded = []
    result = await adapter.run("go", on_event=lambda e: forwarded.append(type(e).__name__))

    assert result.ok
    # lifecycle: start_task → task.created zero-point → in_progress → ... → done + complete_task
    assert ("start_task", "run-1", "task") in tracker.calls
    created = [c for c in tracker.events() if c[1] == "task.created"][0]
    assert created[2]["task.percent_complete"] == 0 and created[2]["task.status"] == "todo"
    assert ("update_status", "run-1", "in_progress") in tracker.calls
    assert ("update_status", "run-1", "done") in tracker.calls
    assert ("complete_task", "run-1") in tracker.calls
    # progress events flowed (tool + turn), and the caller's on_event was forwarded a copy (tee)
    assert "agentic.tool_call_started" in tracker.event_names()
    assert "RunComplete" in forwarded and "TextDelta" in forwarded


@pytest.mark.asyncio
async def test_adapter_marks_non_completed_run_cancelled():
    """A budget stop (not 'completed') → fail_task + cancelled, never a false 'done'."""
    tracker = _FakeTracker()
    from startd8.agents.agentic import SessionConfig
    agent = MockAgent(model="mock-model", streaming=True,
                      tool_turns=[{"tool_calls": [("c%d" % i, "echo", {"i": i})]} for i in range(6)])
    session = AgenticSession(agent, ToolRegistry([_echo_tool([])]), config=SessionConfig(max_total_tokens=3))
    adapter = ContextCoreAgenticAdapter(session, project_id="proj", task_id="run-2", tracker=tracker)
    result = await adapter.run("go")
    assert result.stop_reason == "budget"
    assert ("update_status", "run-2", "cancelled") in tracker.calls
    assert any(c[0] == "fail_task" for c in tracker.calls)
    assert ("update_status", "run-2", "done") not in tracker.calls


def test_no_contextcore_import_in_core_loop_still_holds():
    """FR-S12: the optional integration lives in integrations/, the core loop never imports it."""
    import re
    from pathlib import Path
    agentic = (Path(__file__).resolve().parents[3] / "src" / "startd8" / "agents" / "agentic.py").read_text()
    assert not re.search(r"import.*integrations\.contextcore", agentic)


# --- FR-CC3: the agentic.session span descriptor is registered & collectable ------------------------
def test_fr_cc3_descriptor_is_collectable():
    from startd8.observability.collector import collect_span_descriptors
    descs = collect_span_descriptors()
    names = {d.name_pattern for d in descs}
    assert "agentic.session" in names
    sess = [d for d in descs if d.name_pattern == "agentic.session"][0]
    assert "gen_ai.usage.input_tokens" in sess.attributes
    assert "agentic.stop_reason" in sess.attributes


# --- FR-CC4: dogfood — a REAL agentic.session span is emitted and queried back ----------------------
@pytest.mark.asyncio
async def test_fr_cc4_dogfood_real_span_has_declared_attrs():
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    if isinstance(provider, TracerProvider):
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    else:
        provider = TracerProvider(); provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

    agent = MockAgent(model="mock-model", streaming=True, tool_turns=[{"text": "hi", "tool_calls": []}])
    await AgenticSession(agent, ToolRegistry([])).send("go")

    sess = [s for s in exporter.get_finished_spans() if s.name == "agentic.session"]
    assert sess, "no agentic.session span emitted"
    attrs = sess[0].attributes
    # runtime coverage assertion (LL obs: emission != capability) — the declared attrs are real
    for declared in ("gen_ai.system", "gen_ai.request.model", "agentic.stop_reason", "agentic.turns"):
        assert declared in attrs, f"declared descriptor attr {declared} not actually emitted"
