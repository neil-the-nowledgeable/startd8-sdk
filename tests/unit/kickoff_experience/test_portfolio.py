"""FR-E16 — multi-project portfolio readiness board ($0 disk scan)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from startd8.kickoff_experience.portfolio import (  # noqa: E402
    discover_projects,
    entry_from_view,
    portfolio_summary,
    render_portfolio_markdown,
    scan_portfolio,
)


class _FakeView:
    def __init__(self, readiness, blocked=0, next_step=""):
        self._r = readiness
        self.state = (type("S", (), {"attention_counts":
                     {"blocked": blocked, "ok": 0, "review": 0, "backlog": 0}})()
                      if readiness is not None else None)
        self.next_action = type("NA", (), {"title": next_step})() if next_step else None

    def readiness_percent(self):
        return self._r


def test_classification():
    assert entry_from_view("a", _FakeView(100, 0)).status == "build-ready"
    assert entry_from_view("b", _FakeView(60, 2)).status == "stuck"       # blocked → stuck
    assert entry_from_view("c", _FakeView(70, 0)).status == "in-progress"
    assert entry_from_view("d", _FakeView(None)).status == "not-started"


def test_entry_extracts_next_step_and_blocked():
    e = entry_from_view("x", _FakeView(50, 3, next_step="resolve /goal"))
    assert e.blocked == 3 and e.next_step == "resolve /goal" and e.readiness == 50


def test_ranking_build_ready_first_stuck_last():
    from startd8.kickoff_experience.portfolio import _ranked
    entries = [entry_from_view(n, v) for n, v in [
        ("stuck1", _FakeView(40, 1)),
        ("ready1", _FakeView(100, 0)),
        ("prog1", _FakeView(80, 0)),
        ("new1", _FakeView(None)),
    ]]
    order = [e.name for e in _ranked(entries)]
    assert order == ["ready1", "prog1", "stuck1", "new1"]


def test_render_has_summary_and_rows():
    entries = _ranked_sample()
    md = render_portfolio_markdown(Path("/tmp/ws"), entries)
    assert "# Portfolio readiness — ws" in md
    assert "build-ready" in md and "stuck" in md
    assert "ready1" in md and "100%" in md
    # summary counts
    s = portfolio_summary(entries)
    assert s["total"] == 3 and s["build-ready"] == 1 and s["stuck"] == 1


def _ranked_sample():
    from startd8.kickoff_experience.portfolio import _ranked
    return _ranked([entry_from_view(n, v) for n, v in [
        ("ready1", _FakeView(100, 0)),
        ("stuck1", _FakeView(30, 2, next_step="fix it")),
        ("prog1", _FakeView(75, 0)),
    ]])


def test_render_empty_workspace():
    md = render_portfolio_markdown(Path("/tmp/empty"), [])
    assert "No projects found" in md


def test_discover_and_scan_a_workspace(tmp_path):
    # two projects (each a dir with docs/kickoff) + one non-project dir → discovers exactly two
    for name in ("proj-a", "proj-b"):
        (tmp_path / name / "docs" / "kickoff").mkdir(parents=True)
    (tmp_path / "not-a-project").mkdir()
    roots = discover_projects(tmp_path)
    assert [r.name for r in roots] == ["proj-a", "proj-b"]
    # scan is robust on bare packages (empty docs/kickoff) — 2 entries, never crashes
    entries = scan_portfolio(tmp_path)
    assert {e.name for e in entries} == {"proj-a", "proj-b"}
