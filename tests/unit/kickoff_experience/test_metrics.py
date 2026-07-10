"""Kickoff progress metrics emitter (roadmap Tier 3).

These assert the emitter's contract WITHOUT requiring a live OTel collector: it is best-effort,
never raises, and pulls the right values from an AgenticView. (The end-to-end Meter→Mimir path is
live-verified separately.)
"""

from __future__ import annotations

import pytest

from startd8.kickoff_experience import metrics as km
from startd8.kickoff_experience import session_snapshot as ss
from startd8.kickoff_experience.agentic_view import SNAPSHOT_PRESENT, AgenticView, ProposalRow, confirm_command
from startd8.kickoff_experience.state import FieldState, KickoffState, SourceInventory

pytestmark = pytest.mark.unit


def _state():
    def _fs(m, p, a, v="v", s="extracted"):
        return FieldState(manifest=m, value_path=p, status=s, attention=a, ambiguity="none", value=v)

    return KickoffState(
        fields=(
            _fs("business-targets.yaml", "/goal", "blocked", None, "not_extracted"),
            _fs("conventions.yaml", "/lang", "ok", "python"),
        ),
        inventory=SourceInventory((), (), (), {}),
        grammar_version="g",
    )


def test_record_is_best_effort_and_never_raises(monkeypatch):
    # Force the "no collector / OTel unavailable" path — the emitter must degrade to False, not raise.
    monkeypatch.setitem(km._state, "tried", True)
    monkeypatch.setitem(km._state, "gauges", None)
    assert km.record_kickoff_progress(project="p", readiness_percent=50) is False


def test_record_from_view_extracts_the_right_values(monkeypatch):
    captured = {}

    def _fake_record(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(km, "record_kickoff_progress", _fake_record)

    snap = ss.build_session_snapshot(
        messages=[{"role": "assistant", "content": [{"type": "text", "text": "hi"}]}],
        model="m", input_tokens=1, output_tokens=1, total_tokens=2, cost_usd=0.0031,
        posture="p", project="proj", session_id="s", generated_at="t",
    )
    view = AgenticView(
        project_root="proj",
        state=_state(),
        snapshot=snap,
        snapshot_status=SNAPSHOT_PRESENT,
        proposals=(
            ProposalRow(id="P-1", kind="capture", target="a.b", summary="s",
                        confirm_command=confirm_command("P-1")),
        ),
        proposals_present=True,
    )
    assert km.record_from_view(view, "proj") is True
    assert captured["project"] == "proj"
    assert captured["readiness_percent"] == 50  # 1 ok / 2
    assert captured["cost_usd"] == 0.0031
    assert captured["proposals_pending"] == 1
    assert captured["blocked"] == 1


def test_record_from_view_none_view_is_false():
    assert km.record_from_view(None, "proj") is False
