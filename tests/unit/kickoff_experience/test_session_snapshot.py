"""M1 — durable agentic-session snapshot (FR-1/FR-4/FR-6b).

Covers: transcript normalization (both provider dialects), redaction parity (planted secret absent
from BOTH the written bytes and the Loki log line), presence-gating, the cost line, temp-then-rename
durability (interrupted overwrite leaves the prior snapshot readable + no partial file), and the
fault-injection ordering guarantee (a snapshot-write failure leaves any prior state intact).
"""

from __future__ import annotations

import json

import pytest

from startd8.kickoff_experience import session_snapshot as ss

# An API-key-shaped token the redactor must strip (matches the anthropic_api_key pattern).
PLANTED_SECRET = "sk-ant-ABCDEFGH1234567890abcdefghij"


# --------------------------------------------------------------------------- normalization


def test_normalize_anthropic_dialect_extracts_roles_text_and_tool_names():
    messages = [
        {"role": "user", "content": "how ready is this project?"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me check."},
                {"type": "tool_use", "id": "t1", "name": "survey", "input": {"deep": True}},
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "3 fields blocked"}],
        },
        {"role": "assistant", "content": [{"type": "text", "text": "Three fields need attention."}]},
    ]
    turns = ss.normalize_messages(messages)
    assert [t.role for t in turns] == ["user", "assistant", "tool", "assistant"]
    assert turns[1].tool_calls == ("survey",)
    # the tool-result turn resolves its producing tool via the tool_use id map
    assert turns[2].tool_name == "survey"
    assert "3 fields blocked" in turns[2].text
    # tool arguments are never persisted (FR-1: names only)
    assert all("deep" not in json.dumps(t.to_dict()) for t in turns)
    # indices are contiguous
    assert [t.index for t in turns] == [0, 1, 2, 3]


def test_normalize_openai_dialect():
    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "calling a tool",
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "assess", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "readiness: 40%"},
    ]
    turns = ss.normalize_messages(messages)
    assert [t.role for t in turns] == ["user", "assistant", "tool"]
    assert turns[1].tool_calls == ("assess",)
    assert "readiness" in turns[2].text


# --------------------------------------------------------------------------- redaction (R1-F1)


def _messages_with_secret():
    return [
        {"role": "user", "content": f"my key is {PLANTED_SECRET} please save it"},
        {"role": "assistant", "content": [{"type": "text", "text": "I never store secrets."}]},
    ]


def test_planted_secret_absent_from_written_bytes(tmp_path):
    snap = ss.build_session_snapshot(
        messages=_messages_with_secret(),
        model="claude-x",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
        cost_usd=0.001,
        posture="kickoff · read-only",
        project=str(tmp_path),
        session_id="sess123",
        generated_at="2026-07-09T00:00:00+00:00",
    )
    path = ss.write_snapshot(tmp_path, snap)
    raw = path.read_text(encoding="utf-8")
    assert PLANTED_SECRET not in raw
    assert "«REDACTED:anthropic_api_key»" in raw


def test_planted_secret_absent_from_loki_line(caplog):
    snap = ss.build_session_snapshot(
        messages=_messages_with_secret(),
        model=None,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        cost_usd=0.0,
        posture="kickoff · read-only",
        project="proj",
        session_id="s",
        generated_at="t",
    )
    with caplog.at_level("INFO", logger=ss.TRANSCRIPT_LOGGER_NAME):
        emitted = ss.emit_transcript_to_loki(snap)
    assert emitted == 2
    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert PLANTED_SECRET not in joined
    assert "kickoff_transcript_turn" in joined


# --------------------------------------------------------------------------- cost line (FR-4)


def test_cost_line_shape_matches_chat_py():
    snap = ss.build_session_snapshot(
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": [{"type": "text", "text": "hello"}]},
        ],
        model="m",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        cost_usd=0.1234,
        posture="concierge · propose-only",
        project="p",
        session_id="s",
        generated_at="t",
    )
    # mirrors chat.py:cost_line() -> "[tag] turns=N tokens=T cost≈$X.XXXX"
    assert snap.cost_line() == "[concierge · propose-only] turns=1 tokens=150 cost≈$0.1234"


# --------------------------------------------------------------------------- round-trip


def test_snapshot_round_trips_through_json():
    snap = ss.build_session_snapshot(
        messages=[
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "a"},
                    {"type": "tool_use", "id": "t", "name": "assess", "input": {}},
                ],
            },
        ],
        model="m",
        input_tokens=1,
        output_tokens=2,
        total_tokens=3,
        cost_usd=0.0,
        posture="kickoff · read-only",
        project="p",
        session_id="s",
        generated_at="t",
        pending_proposal_ids=("p1", "p2"),
    )
    restored = ss.AgenticSessionSnapshot.from_dict(json.loads(snap.to_json()))
    assert restored == snap
    assert restored.pending_proposal_ids == ("p1", "p2")


# --------------------------------------------------------------------------- Tier-1 #3/#4


def test_at_a_glance_and_stop_reason_round_trip():
    snap = ss.build_session_snapshot(
        messages=[
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "a"},
                    {"type": "tool_use", "id": "t1", "name": "survey", "input": {}},
                    {"type": "tool_use", "id": "t2", "name": "assess", "input": {}},
                ],
            },
            {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": "t3", "name": "survey", "input": {}}],
            },
        ],
        model="m", input_tokens=10, output_tokens=5, total_tokens=15, cost_usd=0.0031,
        posture="concierge · propose-only", project="p", session_id="s", generated_at="t",
        pending_proposal_ids=("a", "b"),
        stop_reason="budget",
    )
    assert snap.tool_call_counts() == {"survey": 2, "assess": 1}
    glance = snap.at_a_glance()
    assert "survey ×2" in glance and "assess ×1" in glance
    assert "2 proposals pending" in glance and "cost ≈$0.0031" in glance
    assert "stopped: budget" in glance
    # stop_reason survives the JSON round-trip
    restored = ss.AgenticSessionSnapshot.from_dict(json.loads(snap.to_json()))
    assert restored.stop_reason == "budget"


def test_at_a_glance_omits_stop_reason_when_completed():
    snap = ss.build_session_snapshot(
        messages=[{"role": "assistant", "content": [{"type": "text", "text": "done"}]}],
        model="m", input_tokens=0, output_tokens=0, total_tokens=0, cost_usd=0.0,
        posture="kickoff · read-only", project="p", session_id="s", generated_at="t",
        stop_reason="completed",
    )
    assert "stopped" not in snap.at_a_glance()


# --------------------------------------------------------------------------- presence gating (FR-1)


def test_absent_session_writes_no_file(tmp_path):
    class _Chat:
        session = type("S", (), {"messages": [], "total_tokens": 0, "total_cost_usd": 0.0})()
        buffer = None
        agentic = False
        red_carpet = False

    path = ss.persist_snapshot_for_chat(tmp_path, _Chat(), session_id="s", generated_at="t")
    assert path is None
    assert not ss.snapshot_path(tmp_path).exists()


def test_persist_for_chat_writes_and_reports_pending(tmp_path):
    class _Action:
        id = "prop-1"

    class _Buffer:
        def pending(self):
            return [_Action()]

    class _Session:
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": [{"type": "text", "text": "hello"}]},
        ]
        total_tokens = 10
        total_input_tokens = 6
        total_output_tokens = 4
        total_cost_usd = 0.01
        agent = type("A", (), {"model": "claude-x"})()

    class _Chat:
        session = _Session()
        buffer = _Buffer()
        agentic = True
        red_carpet = False

    path = ss.persist_snapshot_for_chat(tmp_path, _Chat(), session_id="s", generated_at="t")
    assert path is not None and path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["pending_proposal_ids"] == ["prop-1"]
    assert data["posture"] == "concierge · propose-only"
    assert data["cost"]["model"] == "claude-x"


# --------------------------------------------------------------------------- durability (R1-F5 / R1-S1)


def _valid_snapshot(project):
    return ss.build_session_snapshot(
        messages=[
            {"role": "user", "content": "first session"},
            {"role": "assistant", "content": [{"type": "text", "text": "prior reply"}]},
        ],
        model="m",
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        cost_usd=0.0,
        posture="kickoff · read-only",
        project=str(project),
        session_id="prior",
        generated_at="t0",
    )


def test_interrupted_overwrite_leaves_prior_snapshot_readable(tmp_path, monkeypatch):
    # First write a valid snapshot.
    ss.write_snapshot(tmp_path, _valid_snapshot(tmp_path))
    prior = ss.snapshot_path(tmp_path).read_text(encoding="utf-8")
    assert "prior reply" in prior

    # Now attempt a second write that fails mid-stream (simulate fsync/replace failure).
    boom = ss.build_session_snapshot(
        messages=[{"role": "assistant", "content": [{"type": "text", "text": "second reply"}]}],
        model="m",
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        cost_usd=0.0,
        posture="kickoff · read-only",
        project=str(tmp_path),
        session_id="second",
        generated_at="t1",
    )
    real_replace = ss.os.replace

    def _fail_replace(*a, **k):
        raise OSError("simulated interruption")

    monkeypatch.setattr(ss.os, "replace", _fail_replace)
    with pytest.raises(OSError):
        ss.write_snapshot(tmp_path, boom)
    monkeypatch.setattr(ss.os, "replace", real_replace)

    # The prior snapshot is untouched and readable; no partial file, no stray temp files.
    after = ss.snapshot_path(tmp_path).read_text(encoding="utf-8")
    assert after == prior
    leftovers = list(ss.snapshot_path(tmp_path).parent.glob(".agentic-session.*.tmp"))
    assert leftovers == []


def test_snapshot_write_failure_is_isolated_in_persist(tmp_path, monkeypatch):
    # persist_snapshot_for_chat must swallow a write failure (never break session exit) and return None.
    class _Session:
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": [{"type": "text", "text": "hello"}]},
        ]
        total_tokens = 1
        total_cost_usd = 0.0
        agent = type("A", (), {"model": "m"})()

    class _Chat:
        session = _Session()
        buffer = None
        agentic = False
        red_carpet = False

    def _boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(ss, "write_snapshot", _boom)
    path = ss.persist_snapshot_for_chat(tmp_path, _Chat(), session_id="s", generated_at="t")
    assert path is None  # swallowed, not raised
