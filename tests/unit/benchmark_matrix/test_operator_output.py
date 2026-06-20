"""Operator output remains redacted, durable, and independent of scoring."""
from __future__ import annotations

import io
import json
import sys
from dataclasses import dataclass

from startd8.benchmark_matrix.operator_output import OperatorOutput
from startd8.model_comparison import run_command


@dataclass
class _Cell:
    cell_id: str = "run:service:model:r0"
    service: str = "service"
    model: str = "openai:model"
    repetition: int = 0
    status: str = "ok"
    cost_usd: float = 0.25

    def to_dict(self):
        return self.__dict__.copy()


def test_event_redacts_and_checkpoint_is_atomic(tmp_path):
    text = io.StringIO()
    events = tmp_path / "operator-events.jsonl"
    output = OperatorOutput("run", tmp_path, json_events=events, text_stream=text)
    output.emit("operator_warning", "test", "token=supersecretvalue sk-abcdefghijklmnopqrstuv")
    output.checkpoint([_Cell()], {"overall": {"n": 1}}, 2)

    assert "supersecretvalue" not in text.getvalue()
    assert "sk-abcdefghijklmnopqrstuv" not in events.read_text()
    assert json.loads((tmp_path / "progress.json").read_text())["completed_cells"] == 1
    assert not (tmp_path / "cells.json.tmp").exists()


def test_run_command_streams_both_pipes(tmp_path):
    received = []
    command = [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr)"]
    result = run_command(command, tmp_path, on_output=lambda stream, line: received.append((stream, line)))

    assert result["returncode"] == 0
    assert ("stdout", "out") in received
    assert ("stderr", "err") in received
