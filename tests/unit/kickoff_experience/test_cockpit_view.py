"""Terminal cockpit parity view (roadmap Tier 2).

Verifies the terminal render surfaces the SAME facts as the Grafana board (both derive from one
`AgenticView`), the empty states are honest, and the `startd8 kickoff cockpit` command runs.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from startd8.kickoff_experience import session_snapshot as ss
from startd8.kickoff_experience.agentic_view import (
    SNAPSHOT_ABSENT,
    SNAPSHOT_PRESENT,
    AgenticView,
    ProposalRow,
    confirm_command,
    parse_confirm_command,
)
from startd8.kickoff_experience.cockpit_view import cockpit_to_text, render_cockpit
from startd8.kickoff_experience.portal_spec_v2 import build_workbook_v2
from startd8.kickoff_experience.ranking import next_action
from startd8.kickoff_experience.state import FieldState, KickoffState, SourceInventory

pytestmark = pytest.mark.unit
runner = CliRunner()


def _state():
    def _fs(m, p, a, v="v", s="extracted"):
        return FieldState(manifest=m, value_path=p, status=s, attention=a, ambiguity="none", value=v)

    return KickoffState(
        fields=(
            _fs("business-targets.yaml", "/goal", "blocked", None, "not_extracted"),
            _fs("business-targets.yaml", "/kpi", "ok", "95%"),
            _fs("conventions.yaml", "/lang", "ok", "python"),
        ),
        inventory=SourceInventory((), (), (), {}),
        grammar_version="g",
    )


def _snapshot(tmp_path, *, stop_reason="completed"):
    return ss.build_session_snapshot(
        messages=[
            {"role": "user", "content": "how ready?"},
            {"role": "assistant", "content": [{"type": "text", "text": "two gaps"},
                                              {"type": "tool_use", "id": "t", "name": "assess", "input": {}}]},
        ],
        model="m", input_tokens=1, output_tokens=1, total_tokens=2, cost_usd=0.0031,
        posture="concierge · propose-only", project=str(tmp_path), session_id="sid",
        generated_at="2026-07-09T00:00:00+00:00", stop_reason=stop_reason,
    )


def _view(tmp_path, *, with_snapshot=True, with_proposals=True, stop_reason="completed"):
    state = _state()
    snap = _snapshot(tmp_path, stop_reason=stop_reason) if with_snapshot else None
    props = ()
    if with_proposals:
        props = (
            ProposalRow(
                id="P-1", kind="capture", target="conventions.tz",
                summary="set conventions.tz = UTC",
                confirm_command=confirm_command("P-1", kind="capture", value_path="conventions.tz"),
            ),
        )
    return AgenticView(
        project_root=str(tmp_path),
        state=state,
        snapshot=snap,
        snapshot_status=SNAPSHOT_PRESENT if with_snapshot else SNAPSHOT_ABSENT,
        proposals=props,
        proposals_present=with_proposals,
        readiness=None,
        next_action=next_action(state, None),
    )


# --------------------------------------------------------------------------- rendering


def test_status_shows_readiness_and_next_step(tmp_path):
    out = cockpit_to_text(_view(tmp_path))
    assert "67% ready" in out  # 2 ok / 3
    assert "Next step" in out and "/goal" in out  # the blocked field


def test_assistant_shows_glance_and_stop_reason(tmp_path):
    out = cockpit_to_text(_view(tmp_path, stop_reason="budget"))
    assert "Session at a glance:" in out and "assess ×1" in out
    assert "budget cap" in out  # the shared stop-reason hint


def test_proposals_table_and_confirm_commands(tmp_path):
    out = cockpit_to_text(_view(tmp_path))
    assert "P-1" in out and "capture" in out
    # the confirm command is present and round-trips to the proposal id
    view = _view(tmp_path)
    assert parse_confirm_command(view.proposals[0].confirm_command)["id"] == "P-1"


def test_empty_states_are_honest(tmp_path):
    out = cockpit_to_text(_view(tmp_path, with_snapshot=False, with_proposals=False))
    assert "kickoff chat" in out  # assistant empty hint
    assert "No proposals" in out


def test_pipeline_panel_shown_only_when_there_is_activity(tmp_path):
    # M1: the terminal cockpit gains a Pipeline & Stakeholders panel from the folded oracle state.
    view = _view(tmp_path)  # no pipeline/roster → panel absent
    assert "Pipeline & Stakeholders" not in cockpit_to_text(view)
    active = AgenticView(
        project_root=str(tmp_path),
        state=view.state,
        snapshot=view.snapshot,
        snapshot_status=view.snapshot_status,
        proposals=view.proposals,
        proposals_present=view.proposals_present,
        next_action=view.next_action,
        pipeline={"inbox": {"present": True, "count": 2}, "dispositions": {"present": False}, "staged": []},
        roster=["p1"],
    )
    out = cockpit_to_text(active)
    assert "Pipeline & Stakeholders" in out and "2 in VIPP inbox" in out


# --------------------------------------------------------------------------- parity (FR-3)


def test_terminal_and_dashboard_agree_on_the_facts(tmp_path):
    # The same AgenticView drives both surfaces → same next step + same proposal id (single oracle).
    view = _view(tmp_path)
    terminal = cockpit_to_text(view)
    board = build_workbook_v2(_state(), "demo", view=view)
    board_text = json.dumps(board)

    # next step: the recommended action title appears in BOTH
    assert view.next_action.title in terminal
    assert view.next_action.title in board_text
    # proposal id appears in BOTH
    assert "P-1" in terminal and "P-1" in board_text


# --------------------------------------------------------------------------- CLI


def test_cockpit_command_runs(tmp_path):
    from startd8.cli_concierge import kickoff_kernel_app

    # seed a real snapshot + inbox so build_agentic_view has content
    ss.write_snapshot(tmp_path, _snapshot(tmp_path))
    from startd8.vipp.models import EnvelopedProposal, ProposalEnvelope

    env = ProposalEnvelope(
        project_id="p", envelope_seq=1,
        proposals=[EnvelopedProposal(kind="capture", params={"value_path": "a.b", "value": "c"}, id="P-9")],
    )
    ip = tmp_path / ".startd8" / "vipp" / "proposals-inbox.json"
    ip.parent.mkdir(parents=True, exist_ok=True)
    ip.write_text(json.dumps(env.to_dict()), encoding="utf-8")

    res = runner.invoke(kickoff_kernel_app, ["cockpit", str(tmp_path), "--plain"])
    assert res.exit_code == 0, res.output
    assert "Status" in res.output and "Assistant" in res.output and "Proposals" in res.output
    assert "P-9" in res.output
