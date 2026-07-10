"""M2 — agentic cockpit read-model (FR-3/FR-10).

Covers the single-oracle fold, the FR-7 confirm-command round-trip (spaces/quotes value_path), the
FR-3 version-degrade contract, and the FR-10 honest empty/unavailable states.
"""

from __future__ import annotations

import json

from startd8.kickoff_experience import agentic_view as av
from startd8.kickoff_experience import session_snapshot as ss


# --------------------------------------------------------------------------- confirm command (R1-F4)


def test_confirm_command_round_trips_with_spaces_and_quotes():
    tricky = "user's \"favorite\" path/with spaces"
    cmd = av.confirm_command("prop-9", kind="capture", value_path=tricky)
    parsed = av.parse_confirm_command(cmd)
    assert parsed["id"] == "prop-9"
    assert parsed["kind"] == "capture"
    assert parsed["path"] == tricky  # survived shlex escaping byte-for-byte
    # the command itself is a real, runnable two-step (no invented flags)
    assert cmd.startswith("startd8 vipp negotiate && startd8 vipp apply --apply --yes")


def test_parse_confirm_command_absent_annotation_is_empty():
    assert av.parse_confirm_command("echo hello") == {}


# --------------------------------------------------------------------------- helpers


def _write_snapshot(root, *, version=ss.SNAPSHOT_SCHEMA_VERSION, turns_text="hello"):
    snap = ss.build_session_snapshot(
        messages=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": [{"type": "text", "text": turns_text}]},
        ],
        model="m",
        input_tokens=1,
        output_tokens=1,
        total_tokens=2,
        cost_usd=0.0,
        posture="kickoff · read-only",
        project=str(root),
        session_id="s",
        generated_at="t",
    )
    d = snap.to_dict()
    d["schema_version"] = version
    p = ss.snapshot_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d), encoding="utf-8")
    return p


def _write_inbox(root, proposals):
    from startd8.vipp.models import EnvelopedProposal, ProposalEnvelope

    env = ProposalEnvelope(
        project_id="p",
        envelope_seq=1,
        proposals=[EnvelopedProposal(kind=k, params=params, id=pid) for (k, params, pid) in proposals],
    )
    ip = root / ".startd8" / "vipp" / "proposals-inbox.json"
    ip.parent.mkdir(parents=True, exist_ok=True)
    ip.write_text(json.dumps(env.to_dict()), encoding="utf-8")
    return ip


# --------------------------------------------------------------------------- snapshot health (FR-3/FR-10)


def test_absent_snapshot_yields_absent_state_and_hint(tmp_path):
    view = av.build_agentic_view(tmp_path)
    assert view.snapshot_status == av.SNAPSHOT_ABSENT
    assert view.snapshot is None
    assert "kickoff chat" in view.assistant_message()


def test_present_snapshot_parses(tmp_path):
    _write_snapshot(tmp_path)
    view = av.build_agentic_view(tmp_path)
    assert view.snapshot_status == av.SNAPSHOT_PRESENT
    assert view.has_snapshot
    assert view.assistant_message() is None
    assert view.snapshot.turns[1].text == "hello"


def test_unknown_schema_version_degrades_to_unsupported(tmp_path):
    _write_snapshot(tmp_path, version=999)
    view = av.build_agentic_view(tmp_path)
    assert view.snapshot_status == av.SNAPSHOT_UNSUPPORTED
    assert view.snapshot is None
    assert "unsupported snapshot version" in view.assistant_message()


def test_truncated_snapshot_degrades_to_unavailable(tmp_path):
    p = ss.snapshot_path(tmp_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('{"schema_version": 1, "turns": [ {trunc', encoding="utf-8")  # invalid JSON
    view = av.build_agentic_view(tmp_path)
    assert view.snapshot_status == av.SNAPSHOT_UNAVAILABLE
    assert view.snapshot is None
    assert "unavailable" in view.assistant_message().lower()


# --------------------------------------------------------------------------- proposals (FR-2/FR-7/FR-10)


def test_no_inbox_yields_empty_proposals_and_hint(tmp_path):
    view = av.build_agentic_view(tmp_path)
    assert view.proposals == ()
    assert view.proposals_present is False
    assert "No proposals" in view.proposals_message()


def test_inbox_proposals_are_normalized_with_confirm_commands(tmp_path):
    _write_inbox(
        tmp_path,
        [
            ("capture", {"value_path": "conventions.tz", "value": "UTC"}, "id-1"),
            ("instantiate", {"posture": "scrutiny"}, "id-2"),
        ],
    )
    view = av.build_agentic_view(tmp_path)
    assert view.proposals_present is True
    assert [r.id for r in view.proposals] == ["id-1", "id-2"]
    capture = view.proposals[0]
    assert capture.kind == "capture"
    assert capture.target == "conventions.tz"
    # the confirm command is id-bound: parsing it back resolves to this row's id
    assert av.parse_confirm_command(capture.confirm_command)["id"] == "id-1"
    assert view.proposals_message() is None


def test_malformed_inbox_degrades_to_empty_not_error(tmp_path):
    ip = tmp_path / ".startd8" / "vipp" / "proposals-inbox.json"
    ip.parent.mkdir(parents=True, exist_ok=True)
    ip.write_text("{not valid json", encoding="utf-8")
    view = av.build_agentic_view(tmp_path)
    assert view.proposals == ()
    assert view.proposals_present is False  # honest empty, no traceback


# --------------------------------------------------------------------------- parity (FR-3)


def test_convergence_folds_classic_state_absent_by_default(tmp_path):
    # M1: an empty project folds no stakeholder/pipeline/roster state (best-effort → None).
    view = av.build_agentic_view(tmp_path)
    assert view.pipeline is None and view.panel_answers is None and view.roster is None
    assert view.pipeline_summary() is None and view.stakeholder_summary() is None


def test_convergence_summaries_from_folded_state():
    # M1: AgenticView is the superset oracle — it summarizes the panel→bridge→VIPP funnel + stakeholders.
    view = av.AgenticView(
        project_root="p",
        state=None,
        snapshot=None,
        snapshot_status=av.SNAPSHOT_ABSENT,
        proposals=(),
        proposals_present=False,
        pipeline={
            "staged": [{}, {}],
            "inbox": {"present": True, "count": 3},
            "dispositions": {"present": True, "counts": {"ACCEPT": 2, "REJECT": 1, "COUNTER": 0}},
        },
        panel_answers=[{"text": "a"}, {"text": "b"}],
        roster=["p1", "p2", "p3"],
    )
    ps = view.pipeline_summary()
    assert "2 staged" in ps and "3 in VIPP inbox" in ps and "2 accept" in ps
    ss = view.stakeholder_summary()
    assert "3 personas" in ss and "2 answers" in ss


def test_view_is_deterministic_single_oracle(tmp_path):
    _write_snapshot(tmp_path)
    _write_inbox(tmp_path, [("capture", {"value_path": "a.b", "value": "c"}, "id-1")])
    v1 = av.build_agentic_view(tmp_path)
    v2 = av.build_agentic_view(tmp_path)
    # two builds of the same root produce equal view-models (drives dashboard + any future TUI)
    assert v1.snapshot == v2.snapshot
    assert v1.proposals == v2.proposals
    assert v1.snapshot_status == v2.snapshot_status
