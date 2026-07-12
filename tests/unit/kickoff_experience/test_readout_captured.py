"""FR-E14 — the "What was captured" section: the actual field values in the shareable readout
(Markdown + HTML), additive + byte-preserving when empty, XSS-safe in HTML."""
from __future__ import annotations

import pytest

from startd8.kickoff_experience.agentic_view import SNAPSHOT_ABSENT, AgenticView
from startd8.kickoff_experience.readout import render_html, render_markdown
from startd8.kickoff_experience.state import FieldState, KickoffState, SourceInventory

pytestmark = pytest.mark.unit


def _fs(path, value, attention="ok", status="extracted"):
    return FieldState(manifest="m.yaml", value_path=path, status=status,
                      attention=attention, ambiguity="none", value=value)


def _view(fields):
    return AgenticView(
        project_root="proj",
        state=KickoffState(fields=tuple(fields), inventory=SourceInventory((), (), (), {}),
                           grammar_version="g"),
        snapshot=None,
        snapshot_status=SNAPSHOT_ABSENT,
        proposals=(),
        proposals_present=False,
    )


def test_markdown_lists_captured_values():
    view = _view([
        _fs("/kpi", "95%"),
        _fs("/lang", "python"),
        _fs("/goal", None, attention="blocked", status="not_extracted"),  # unset → not captured
    ])
    md = render_markdown(view)
    assert "## What was captured" in md
    assert "/kpi" in md and "95%" in md
    assert "/lang" in md and "python" in md
    # the unset field is not a captured row, and the "not yet captured" hint appears
    cap = md.split("## What was captured", 1)[1].split("##", 1)[0]
    assert "/goal" not in cap
    assert "1 input(s) not yet captured" in cap


def test_section_absent_when_nothing_captured():
    # all values None → the section is omitted entirely (byte-preserving for an empty session)
    view = _view([_fs("/goal", None, attention="blocked", status="not_extracted")])
    assert "What was captured" not in render_markdown(view)
    assert "What was captured" not in render_html(view)


def test_html_escapes_captured_values():
    view = _view([_fs("/desc", "<script>alert(1)</script>")])
    html = render_html(view)
    assert "What was captured" in html
    assert "<script>alert(1)</script>" not in html          # never raw
    assert "&lt;script&gt;" in html                          # inert, escaped


def test_long_value_is_truncated():
    view = _view([_fs("/blob", "x" * 500)])
    md = render_markdown(view)
    assert "…" in md and ("x" * 500) not in md
