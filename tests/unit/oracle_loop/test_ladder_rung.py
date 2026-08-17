"""FR-3 (ORACLE rung) + FR-11 (default-off byte-identity)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from startd8.deploy_harness import deploy_app_local
from startd8.deploy_harness.ladder import Stage, _STAGE_ORDER

pytestmark = pytest.mark.unit


def _write_bare_app(root: Path) -> None:
    app = root / "app"
    app.mkdir(parents=True, exist_ok=True)
    (app / "__init__.py").write_text("", encoding="utf-8")
    # unknown-mode app so boot is skipped — a cheap, network-free ladder path.
    (app / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )
    (app / "settings.py").write_text("# no mode header\nX = 1\n", encoding="utf-8")


def test_oracle_appended_last_no_renumber():
    """R1-S3: ORACLE=6 after CONTEXT_SMOKE=5; existing orders unchanged."""
    assert _STAGE_ORDER[Stage.DISCOVER] == 0
    assert _STAGE_ORDER[Stage.SMOKE] == 4
    assert _STAGE_ORDER[Stage.CONTEXT_SMOKE] == 5
    assert _STAGE_ORDER[Stage.ORACLE] == 6
    assert Stage.ORACLE.order > Stage.CONTEXT_SMOKE.order


def test_disabled_deploy_is_byte_identical_no_oracle_rung(tmp_path, monkeypatch):
    """FR-11: gate off (default) → no ORACLE rung → byte-identical LadderResult."""
    monkeypatch.delenv("STARTD8_ORACLE_LOOP_ENABLED", raising=False)
    _write_bare_app(tmp_path)

    baseline = deploy_app_local(tmp_path, runner_python=sys.executable)
    # Even supplying a spec, while the flag is off the rung must not appear.
    with_spec = deploy_app_local(
        tmp_path,
        runner_python=sys.executable,
        spec_path=Path(__file__).parent / "fixtures" / "passing_spec.md",
    )
    assert "oracle" not in baseline.stages
    assert "oracle" not in with_spec.stages
    assert baseline.oracle_verdicts == {}
    assert with_spec.oracle_verdicts == {}
    # Byte-identical modulo the volatile app_root/timings — compare the stage table.
    assert baseline.model_dump()["stages"] == with_spec.model_dump()["stages"]


def test_spec_less_call_emits_no_oracle_rung_even_enabled(tmp_path, monkeypatch):
    """Doubly-gated: enabled but NO spec → still no ORACLE rung (presence gate)."""
    monkeypatch.setenv("STARTD8_ORACLE_LOOP_ENABLED", "1")
    _write_bare_app(tmp_path)
    res = deploy_app_local(tmp_path, runner_python=sys.executable)  # no spec_path
    assert "oracle" not in res.stages
