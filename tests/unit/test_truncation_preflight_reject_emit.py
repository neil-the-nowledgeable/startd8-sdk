"""Regression for the survivorship-audit finding SA-STARTD8-TPR-DORMANT.

TRUNCATION_PREFLIGHT_REJECT was defined in the event enum and mapped in the OTel collector, and multiple
capability manifests claimed it was emitted — but it had zero emit sites (a dormant value path; the
manifest claim was an active doc-lie). This pins the wire down: when a strict pre-flight check rejects an
over-limit task, the event must actually fire (with the reject context), and the reject must still raise.
"""
import asyncio

import pytest

from startd8.agents.mock import MockAgent
from startd8.events.types import EventType
from startd8.events.bus import EventBus


class _RejectEstimate:
    """Minimal stand-in for a PreFlightEstimate that forces the reject branch."""
    exceeds_limit = True
    suggested_action = "reject"
    reasoning = "estimated output far exceeds the safe limit and is not chunkable"
    estimated_lines = 9999
    estimated_tokens = 99999


def test_preflight_reject_emits_event_and_still_raises():
    agent = MockAgent()
    # Force the reject branch without needing a real over-limit task.
    agent._pre_flight_check = lambda **kwargs: _RejectEstimate()

    captured = []
    handler = lambda ev: captured.append(ev)
    EventBus.subscribe(EventType.TRUNCATION_PREFLIGHT_REJECT, handler)
    try:
        with pytest.raises(ValueError, match="Pre-flight check rejected"):
            asyncio.run(agent.agenerate_with_validation(
                "some prompt", task_description="do an enormous thing", strict=True,
            ))
    finally:
        EventBus.unsubscribe(EventType.TRUNCATION_PREFLIGHT_REJECT, handler)

    # The dormant event now fires exactly once, carrying the reject context.
    assert len(captured) == 1
    ev = captured[0]
    assert ev.type == EventType.TRUNCATION_PREFLIGHT_REJECT
    assert ev.data["suggested_action"] == "reject"
    assert ev.data["agent_name"] == agent.name
    assert ev.data["estimated_lines"] == 9999
