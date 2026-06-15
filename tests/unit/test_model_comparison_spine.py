"""Tests for the determinism-boundary signal in model_comparison (check_spine_in_sync).

Salvaged capability from the e2e-model-comparison-harness: after a model's run, re-run the $0
deterministic backend generator in --check mode to detect whether the model drifted an OWNED
(spine) file. No-op for non-backend-codegen targets.
"""
from __future__ import annotations

from pathlib import Path

import startd8.model_comparison as mc


def test_no_op_without_prisma_schema(tmp_path: Path):
    """Returns None (no-op) when the target has no prisma/schema.prisma — e.g. a non-backend app."""
    assert mc.check_spine_in_sync(tmp_path, log=lambda *_: None) is None


def _make_workdir_with_schema(tmp_path: Path) -> Path:
    schema = tmp_path / "prisma" / "schema.prisma"
    schema.parent.mkdir(parents=True)
    schema.write_text("model Foo { id Int @id }\n", encoding="utf-8")
    return tmp_path


def test_in_sync_when_check_exits_zero(tmp_path: Path, monkeypatch):
    wd = _make_workdir_with_schema(tmp_path)
    monkeypatch.setattr(
        mc, "run_command",
        lambda *a, **k: {"returncode": 0, "stdout_tail": "in_sync", "stderr_tail": ""},
    )
    result = mc.check_spine_in_sync(wd, log=lambda *_: None)
    assert result is not None
    assert result["spine_in_sync"] is True
    assert result["spine_check_status"] == "in_sync"


def test_drift_when_check_exits_one(tmp_path: Path, monkeypatch):
    wd = _make_workdir_with_schema(tmp_path)
    monkeypatch.setattr(
        mc, "run_command",
        lambda *a, **k: {"returncode": 1, "stdout_tail": "drift: app/models.py", "stderr_tail": ""},
    )
    result = mc.check_spine_in_sync(wd, log=lambda *_: None)
    assert result["spine_in_sync"] is False
    assert result["spine_check_status"] == "drift"
    assert "drift" in result["spine_check_detail"]


def test_error_when_check_exits_two(tmp_path: Path, monkeypatch):
    wd = _make_workdir_with_schema(tmp_path)
    monkeypatch.setattr(
        mc, "run_command",
        lambda *a, **k: {"returncode": 2, "stdout_tail": "", "stderr_tail": "boom"},
    )
    result = mc.check_spine_in_sync(wd, log=lambda *_: None)
    assert result["spine_in_sync"] is False
    assert result["spine_check_status"] == "error"


def test_metric_row_present_in_markdown_table():
    """The determinism signal surfaces as a row in the comparison report table."""
    fields = {field for _label, field, _places in mc._METRIC_ROWS}
    assert "spine_check_status" in fields
