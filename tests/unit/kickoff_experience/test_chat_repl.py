"""Host for the read-only agentic chat — the REPL driver (no live LLM)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from startd8.kickoff_experience.chat import run_kickoff_repl


@dataclass
class _FakeResult:
    text: str
    turns: int = 1
    total_tokens: int = 10
    total_cost_usd: float = 0.001


@dataclass
class _Recorder:
    lines: List[str] = field(default_factory=list)

    def emit(self, line: str) -> None:
        self.lines.append(line)


def _scripted_reader(inputs):
    seq = list(inputs)

    def read(_prompt):
        return seq.pop(0) if seq else None

    return read


def test_repl_runs_turns_until_quit() -> None:
    rec = _Recorder()
    asks: List[str] = []

    def ask_sync(msg):
        asks.append(msg)
        return _FakeResult(text=f"answer to: {msg}")

    turns = run_kickoff_repl(
        banner="BANNER",
        ask_sync=ask_sync,
        read_input=_scripted_reader(["what's missing?", "quit"]),
        emit_line=rec.emit,
        cost_line=lambda r: f"cost={r.total_cost_usd}",
    )
    assert turns == 1
    assert asks == ["what's missing?"]
    assert "BANNER" in rec.lines
    assert "answer to: what's missing?" in rec.lines
    assert any("cost=" in line for line in rec.lines)


def test_repl_ends_on_eof_none() -> None:
    rec = _Recorder()
    turns = run_kickoff_repl(
        banner="B", ask_sync=lambda m: _FakeResult("x"),
        read_input=_scripted_reader([None]),  # EOF / non-TTY immediately
        emit_line=rec.emit,
    )
    assert turns == 0  # never spent a turn


def test_repl_blank_line_exits() -> None:
    turns = run_kickoff_repl(
        banner="B", ask_sync=lambda m: _FakeResult("x"),
        read_input=_scripted_reader([""]),  # empty line ends the session
        emit_line=lambda _l: None,
    )
    assert turns == 0


def test_repl_multiple_turns() -> None:
    asks: List[str] = []
    run_kickoff_repl(
        banner="B",
        ask_sync=lambda m: (asks.append(m) or _FakeResult("ok")),
        read_input=_scripted_reader(["q1", "q2", "exit"]),
        emit_line=lambda _l: None,
    )
    assert asks == ["q1", "q2"]
