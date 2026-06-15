"""Re-score tool — pure-logic guard (no node/LLM): cells.json parsing, missing-server handling,
report rendering. End-to-end scoring is covered by the pilot re-run + smoke."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_SEEDS = _REPO / "docs" / "design" / "model-benchmark" / "seeds"


def _load():
    spec = importlib.util.spec_from_file_location("_rescore", _REPO / "scripts" / "rescore_behavioral.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_rescore"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_rescore_reports_missing_server_without_running(tmp_path):
    m = _load()
    # cells.json points at a cell whose workdir doesn't exist → "no persisted server", no node call.
    (tmp_path / "cells.json").write_text(json.dumps([
        {"service": "paymentservice", "model": "anthropic:claude-opus-4-8",
         "repetition": 0, "functional_coverage": None, "status": "ok"}]))
    payload = m.rescore(tmp_path, _SEEDS)
    cell = payload["cells"][0]
    assert cell["rescored_functional"] is None
    assert cell["rescore_note"] == "no persisted server"
    assert payload["recovered_cells"] == 0
    assert payload["by_model_median"]["anthropic:claude-opus-4-8"] is None
    # report renders without error
    md = m._report_md(payload)
    assert "Behavioral re-score" in md and "anthropic:claude-opus-4-8" in md
