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


# --- agentic Concierge proposal handling in the REPL (FR-AC-3 / R1-F5 / NR-5) -------------------

@dataclass
class _FakeAction:
    kind: str
    id: str

    def summary(self) -> str:
        return f"{self.kind}:{self.id}"


@dataclass
class _FakeOutcome:
    code: str
    detail: str = ""
    retriable: bool = False


class _FakeBuffer:
    def __init__(self, items):
        self._items = list(items)

    def pending(self):
        return list(self._items)

    def pop(self, action_id):
        self._items = [a for a in self._items if a.id != action_id]


def _one_turn_repl(buffer, confirm, apply_proposal, applied):
    return run_kickoff_repl(
        banner="B",
        ask_sync=lambda m: _FakeResult("ok"),
        read_input=_scripted_reader(["go", "quit"]),
        emit_line=lambda _l: None,
        pending=buffer.pending,
        confirm=confirm,
        apply_proposal=lambda a: (applied.append(a.id) or apply_proposal(a)),
        consume=lambda a: buffer.pop(a.id),
    )


def test_repl_confirm_applies_and_consumes() -> None:
    buf = _FakeBuffer([_FakeAction("instantiate", "a1")])
    applied: List[str] = []
    _one_turn_repl(buf, lambda _m: True, lambda a: _FakeOutcome("ok"), applied)
    assert applied == ["a1"]
    assert buf.pending() == []          # terminal success → consumed


def test_repl_decline_discards_without_apply() -> None:
    buf = _FakeBuffer([_FakeAction("friction", "a2")])
    applied: List[str] = []
    _one_turn_repl(buf, lambda _m: False, lambda a: _FakeOutcome("ok"), applied)
    assert applied == []                # never applied
    assert buf.pending() == []          # discarded (popped)


def test_repl_none_confirmation_fails_closed_and_keeps() -> None:
    buf = _FakeBuffer([_FakeAction("capture", "a3")])
    applied: List[str] = []
    _one_turn_repl(buf, lambda _m: None, lambda a: _FakeOutcome("ok"), applied)
    assert applied == []                # no apply on a None confirmation (NR-5)
    assert buf.pending() != []          # left pending


def test_repl_retriable_outcome_keeps_proposal() -> None:
    buf = _FakeBuffer([_FakeAction("capture", "a4")])
    applied: List[str] = []
    _one_turn_repl(buf, lambda _m: True, lambda a: _FakeOutcome("stale_file", retriable=True), applied)
    assert applied == ["a4"]            # applied (attempted)
    assert buf.pending() != []          # but kept pending for retry (R1-F5)
