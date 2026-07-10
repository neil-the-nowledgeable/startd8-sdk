"""Shareable kickoff readout (Markdown + HTML) — parity, empty states, XSS safety, CLI.

The readout renders the SAME `AgenticView` read-model the terminal cockpit and the Grafana board
render (single oracle), as a self-contained static document. These tests construct the view
directly (mirroring test_cockpit_view.py) so they don't depend on docs/kickoff on disk.
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
)
from startd8.kickoff_experience.ranking import next_action
from startd8.kickoff_experience.readout import render_html, render_markdown
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


def _snapshot(tmp_path, *, stop_reason="completed", text="two gaps"):
    return ss.build_session_snapshot(
        messages=[
            {"role": "user", "content": "how ready?"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": text},
                    {"type": "tool_use", "id": "t", "name": "assess", "input": {}},
                ],
            },
        ],
        model="m", input_tokens=1, output_tokens=1, total_tokens=2, cost_usd=0.0031,
        posture="concierge · propose-only", project=str(tmp_path), session_id="sid",
        generated_at="2026-07-09T00:00:00+00:00", stop_reason=stop_reason,
    )


def _view(tmp_path, *, with_snapshot=True, with_proposals=True, stop_reason="completed", text="two gaps"):
    state = _state()
    snap = _snapshot(tmp_path, stop_reason=stop_reason, text=text) if with_snapshot else None
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


# --------------------------------------------------------------------------- markdown


def test_markdown_has_the_facts(tmp_path):
    view = _view(tmp_path)
    md = render_markdown(view)
    assert "67% ready" in md  # 2 ok / 3
    assert view.next_action.title in md  # the recommended next step
    assert "P-1" in md  # the proposal id
    assert view.proposals[0].confirm_command in md  # the confirm command


# --------------------------------------------------------------------------- html


def test_html_is_a_full_document_with_the_facts(tmp_path):
    view = _view(tmp_path)
    doc = render_html(view)
    assert doc.startswith("<!DOCTYPE html>")
    assert "<html" in doc and "</html>" in doc
    assert "67% ready" in doc
    assert view.next_action.title in doc or _escaped(view.next_action.title) in doc
    assert "P-1" in doc


def _escaped(text):
    import html

    return html.escape(text)


def test_html_escapes_a_planted_xss_payload(tmp_path):
    payload = "<script>alert(1)</script>"
    view = _view(tmp_path, text=payload)
    doc = render_html(view)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in doc
    assert payload not in doc  # the raw, executable form must NOT appear


# --------------------------------------------------------------------------- empty states


def test_empty_states_are_honest(tmp_path):
    view = _view(tmp_path, with_snapshot=False, with_proposals=False)
    md = render_markdown(view)
    assert "kickoff chat" in md  # assistant absent hint
    assert view.proposals_message() in md  # the "no proposals" message
    doc = render_html(view)
    assert "kickoff chat" in doc
    assert _escaped(view.proposals_message()) in doc or view.proposals_message() in doc


# --------------------------------------------------------------------------- CLI


def test_readout_command_writes_a_file(tmp_path):
    from startd8.cli_concierge import kickoff_kernel_app

    # Seed a real snapshot + inbox so build_agentic_view has content.
    ss.write_snapshot(tmp_path, _snapshot(tmp_path))
    from startd8.vipp.models import EnvelopedProposal, ProposalEnvelope

    env = ProposalEnvelope(
        project_id="p", envelope_seq=1,
        proposals=[EnvelopedProposal(kind="capture", params={"value_path": "a.b", "value": "c"}, id="P-9")],
    )
    ip = tmp_path / ".startd8" / "vipp" / "proposals-inbox.json"
    ip.parent.mkdir(parents=True, exist_ok=True)
    ip.write_text(json.dumps(env.to_dict()), encoding="utf-8")

    out_file = tmp_path / "r.md"
    res = runner.invoke(
        kickoff_kernel_app,
        ["readout", str(tmp_path), "--format", "md", "--out", str(out_file)],
    )
    assert res.exit_code == 0, res.output
    assert out_file.is_file()
    body = out_file.read_text(encoding="utf-8")
    assert "## Status" in body and "## Proposals" in body
    assert "P-9" in body  # the seeded proposal id


def test_readout_command_rejects_bad_format(tmp_path):
    from startd8.cli_concierge import kickoff_kernel_app

    res = runner.invoke(kickoff_kernel_app, ["readout", str(tmp_path), "--format", "pdf"])
    assert res.exit_code == 2, res.output
