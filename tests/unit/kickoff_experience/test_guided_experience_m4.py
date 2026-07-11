# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""GE-M4 — surface parity (CLI / TUI / served) over ONE guided view-model (FR-GE-9).

The guided experience (Orient → Guide → Deepen, incl. GE-M3b's halted-session + per-round/total-cost
states) renders from ONE canonical view-model — ``build_guided_view`` in ``concierge_view.py``, the
parity oracle. Each surface is a *pure function* of that payload, differing only in rendering:

  * **CLI**   — ``startd8 kickoff guided`` (its ``--json`` emits the view verbatim; its Deepen block
                shares ``render_deepen_lines``).
  * **TUI**   — ``run_guided`` emits ``render_guided_lines`` of the same view.
  * **served**— ``_render_guided`` renders the same view as HTML (``/guided`` + ``/guided.json``).

Parity is a **structural/content** assertion, not a pixel match: for one fixture state (a HALTED,
cost-bearing Deepen session) all three surfaces present the same semantic content — the three phases,
the same Guide blockers/next-commands, the same Deepen halt banner, and the same session cost figure
(``guided_parity_digest`` is the surface-independent oracle).
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from startd8.cli import app
from startd8.kickoff_experience.concierge_view import (
    build_guided_view,
    format_cost,
    guided_parity_digest,
    load_latest_deepen_session,
    project_deepen_state,
    render_guided_lines,
    run_guided,
)
from startd8.kickoff_experience.web import _render_guided

runner = CliRunner()


def _make_project(tmp_path):
    root = tmp_path / "proj"
    (root / "docs" / "kickoff" / "inputs").mkdir(parents=True, exist_ok=True)
    (root / "REQUIREMENTS_app.md").write_text(
        "# Reqs\n## Entities\nAI assists\nOwned fields\n", encoding="utf-8"
    )
    return root


def _halted_cost_session():
    """A first-class HALTED, cost-bearing facilitation session (the GE-M3b transcript shape)."""
    return {
        "session_id": "kp-20260704T000000-abc123",
        "status": "halted",
        "halt": {
            "reason": "assumptions_gate",
            "message": "Validate the premise first — 3 high-impact/low-confidence assumptions.",
        },
        "budget_usd": 2.0,
        "cost_total_usd": 0.1234,
        "rounds": [{"round_id": "R1", "entries": [{"cost_usd": 0.1234}]}],
        "synthesis": None,
    }


def _persist_session(root, session):
    d = root / ".startd8" / "kickoff-panel"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{session['session_id']}.json").write_text(json.dumps(session), encoding="utf-8")


# ── the Deepen projection surfaces GE-M3b halt + cost states ─────────────────────────────────────


def test_deepen_projection_carries_halt_and_cost():
    d = project_deepen_state(_halted_cost_session())
    assert d["engaged"] is True and d["halted"] is True
    assert d["status"] == "halted"
    assert d["halt"]["reason"] == "assumptions_gate"
    assert d["cost_total_usd"] == 0.1234
    assert d["n_rounds"] == 1


def test_deepen_projection_none_is_unengaged_pointer():
    d = project_deepen_state(None)
    assert d["engaged"] is False and d["halted"] is False
    assert d["cost_total_usd"] == 0.0


def test_load_latest_deepen_session_reads_persisted_transcript(tmp_path):
    root = _make_project(tmp_path)
    assert load_latest_deepen_session(root) is None  # nothing persisted yet
    sess = _halted_cost_session()
    _persist_session(root, sess)
    loaded = load_latest_deepen_session(root)
    assert loaded is not None and loaded["session_id"] == sess["session_id"]


# ── the parity assertion: CLI / TUI / served present the SAME semantic content ────────────────────


def test_surface_parity_cli_tui_served(tmp_path):
    """FR-GE-9: for one guided view-model (halted + cost-bearing Deepen), all three surfaces present
    the same phases, blockers/next-commands, halt banner, and cost figure."""
    root = _make_project(tmp_path)
    _persist_session(root, _halted_cost_session())

    # The ONE view-model — read straight from disk (proves the Deepen transcript is surfaced).
    view = build_guided_view(root, load_deepen=True)
    assert view["deepen"]["halted"] is True
    digest = guided_parity_digest(view)

    # Surface 1 — served (HTML).
    html = _render_guided(view, "")
    # Surface 2 — CLI/TUI shared text projection (run_guided emits exactly these lines).
    text = "\n".join(render_guided_lines(view))
    # Surface 3 — the real CLI command (a pure function of the same oracle).
    res = runner.invoke(app, ["kickoff", "guided", str(root), "--json"])
    assert res.exit_code == 0, res.stdout
    cli = json.loads(res.stdout)

    # (a) same three phases present on every rendered surface
    for phase in digest["phases"]:
        assert phase in html, f"served missing phase {phase}"
        assert phase in text, f"text missing phase {phase}"
    assert cli["schema"] == "kickoff.guided.v1"

    # (b) same Deepen halt banner
    halt_msg = digest["deepen_halt_message"]
    assert halt_msg and halt_msg in html and halt_msg in text
    assert cli["deepen"]["halt"]["message"] == halt_msg

    # (c) same cost figure (byte-identical shared format across surfaces)
    cost = digest["deepen_cost_figure"]
    assert cost == format_cost(0.1234)
    assert cost in html and cost in text
    assert format_cost(cli["deepen"]["cost_total_usd"]) == cost

    # (d) same Guide blockers / next-commands
    cli_cmds = [s["command"] for s in cli["guide"]["steps"] if s.get("command")]
    assert tuple(cli_cmds) == digest["next_commands"]
    for cmd in digest["next_commands"]:
        assert cmd in html, f"served missing command {cmd}"
        assert cmd in text, f"text missing command {cmd}"


def test_cli_json_equals_the_view_model(tmp_path):
    """The CLI `--json` payload is byte-equal to the shared view-model (CLI is a pure fn of it)."""
    root = _make_project(tmp_path)
    _persist_session(root, _halted_cost_session())
    res = runner.invoke(app, ["kickoff", "guided", str(root), "--json"])
    cli = json.loads(res.stdout)
    view = build_guided_view(root, load_deepen=True)
    assert cli == json.loads(json.dumps(view))  # same JSON document


def test_tui_run_guided_emits_the_shared_projection(tmp_path):
    """The TUI leg (`run_guided`) emits exactly `render_guided_lines` of the shared view (parity)."""
    root = _make_project(tmp_path)
    session = _halted_cost_session()
    lines: list[str] = []
    view = run_guided(root, emit_line=lines.append, deepen_session=session, load_deepen=False)
    assert lines == render_guided_lines(view)
    # the halt banner + cost figure ride the TUI too
    joined = "\n".join(lines)
    assert session["halt"]["message"] in joined
    assert format_cost(session["cost_total_usd"]) in joined


def test_served_guided_route_renders_from_the_oracle(tmp_path):
    """The `/guided` + `/guided.json` served routes render the same view-model (served leg)."""
    import pytest

    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from startd8.kickoff_experience.web import build_kickoff_app

    root = _make_project(tmp_path)
    _persist_session(root, _halted_cost_session())
    client = TestClient(build_kickoff_app(root, mode="preview"))

    j = client.get("/guided.json")
    assert j.status_code == 200
    payload = j.json()
    assert payload["schema"] == "kickoff.guided.v1"
    assert payload["deepen"]["halted"] is True
    assert payload["deepen"]["cost_total_usd"] == 0.1234

    h = client.get("/guided")
    assert h.status_code == 200
    body = h.text
    assert "Orient" in body and "Guide" in body and "Deepen" in body
    assert _halted_cost_session()["halt"]["message"] in body
    assert format_cost(0.1234) in body


# ── SOTTO: the Deepen read is byte-transparent to the guided view when no session exists ──────────


def test_no_persisted_session_is_unengaged_pointer(tmp_path):
    root = _make_project(tmp_path)
    view = build_guided_view(root, load_deepen=True)
    assert view["deepen"]["engaged"] is False
    assert view["deepen"]["cost_total_usd"] == 0.0
