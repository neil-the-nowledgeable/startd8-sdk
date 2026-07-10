"""Decision log + retrospective (Tier C2/C3) — the 'how it got ready' story."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from startd8.cli_concierge import kickoff_kernel_app
from startd8.kickoff_experience.activation import ActivationLedger
from startd8.kickoff_experience.retrospective import (
    RETROSPECTIVE_SCHEMA,
    build_retrospective,
    decision_log,
    kickoff_retrospective,
)

pytestmark = pytest.mark.unit
runner = CliRunner()


def _status(**over):
    base = {
        "project_root": "/p",
        "readiness_percent": 100,
        "proposals": [{"id": "P-2", "kind": "capture", "target": "a.b"}],
        "pipeline": {
            "dispositions": {
                "present": True,
                "counts": {"ACCEPT": 1, "REJECT": 1, "COUNTER": 0},
                "items": [
                    {"proposal_id": "P-1", "decision": "ACCEPT", "reason": "clear win"},
                    {"proposal_id": "P-0", "decision": "REJECT", "reason": "out of scope"},
                ],
            }
        },
    }
    base.update(over)
    return base


def test_decision_log_splits_adjudicated_and_pending():
    d = decision_log(_status())
    assert d["adjudicated"] == 2 and d["pending"] == 1
    assert d["counts"]["ACCEPT"] == 1 and d["counts"]["REJECT"] == 1
    # P-2 is in the inbox but not adjudicated → pending
    assert d["pending_items"][0]["proposal_id"] == "P-2"


def test_decision_log_degrades_without_dispositions():
    d = decision_log({"proposals": [{"id": "X"}], "pipeline": None})
    assert d["adjudicated"] == 0 and d["pending"] == 1 and d["counts"] == {}


def test_retrospective_journey_from_ledger_milestones():
    entries = [
        {"ts": "t0", "readiness_percent": 0, "blocked": 2, "proposals_pending": 2, "snapshot_status": "absent"},
        {"ts": "t1", "readiness_percent": 60, "blocked": 0, "proposals_pending": 1, "snapshot_status": "present"},
        {"ts": "t2", "readiness_percent": 100, "blocked": 0, "proposals_pending": 0, "snapshot_status": "present"},
    ]
    retro = build_retrospective(_status(), entries)
    assert retro["schema"] == RETROSPECTIVE_SCHEMA
    j = retro["journey"]
    assert j["readiness_start"] == 0 and j["readiness_now"] == 100 and j["readiness_delta"] == 100
    assert j["transitions"] == 3
    ms = j["milestones"]
    assert "readiness 0% → 60%" in ms and "readiness 60% → 100%" in ms
    assert "cleared all blockers" in ms and "session snapshot promoted" in ms
    assert any("proposal(s) applied" in m for m in ms)
    json.dumps(retro)


def test_retrospective_empty_history():
    retro = build_retrospective(_status(), [])
    assert retro["journey"]["transitions"] == 0
    assert "decision" in retro["summary"] or "readiness" in retro["summary"]


def _seed(tmp_path, *rows):
    led = ActivationLedger(tmp_path)
    for i, (pct, blk, pend) in enumerate(rows):
        led.record(
            {"readiness_percent": pct, "attention_counts": {"blocked": blk}, "proposals": [{}] * pend},
            now=f"t{i}",
        )


def test_kickoff_retrospective_callable_and_cli(tmp_path):
    _seed(tmp_path, (40, 1, 2), (100, 0, 0))
    retro = kickoff_retrospective(tmp_path)
    assert retro["journey"]["readiness_start"] == 40 and retro["journey"]["readiness_now"] == 100
    out = runner.invoke(kickoff_kernel_app, ["retrospective", str(tmp_path)])
    assert out.exit_code == 0 and "readiness 40% → 100%" in out.output
    js = runner.invoke(kickoff_kernel_app, ["retrospective", str(tmp_path), "--json"])
    assert json.loads(js.output)["schema"] == RETROSPECTIVE_SCHEMA
