"""M1 orchestration tests — network-free ladder paths (no install, no live server).

Uses ``runner_python`` to skip venv creation, exercising the discover/mode-gating logic without pip
or uvicorn. The full live boot path is covered by the gated integration test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from startd8.deploy_harness import deploy_app_local

pytestmark = pytest.mark.unit


def _write_app(root: Path, *, settings_header: str | None = None) -> None:
    app = root / "app"
    app.mkdir(parents=True, exist_ok=True)
    (app / "__init__.py").write_text("", encoding="utf-8")
    (app / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )
    if settings_header is not None:
        (app / "settings.py").write_text(
            settings_header + "\nDEPLOYMENT_MODE = 'x'\n", encoding="utf-8"
        )


def test_entrypoint_missing_fails_at_discover(tmp_path: Path) -> None:
    (tmp_path / "readme.md").write_text("nothing", encoding="utf-8")
    res = deploy_app_local(tmp_path)
    assert res.stages["discover"].status.value == "fail"
    assert res.highest_stage == "discover"
    assert "install" not in res.stages  # never got to install


def test_deployed_mode_skips_boot(tmp_path: Path) -> None:
    _write_app(tmp_path, settings_header="# startd8-mode: deployed")
    res = deploy_app_local(tmp_path, runner_python=sys.executable)
    assert res.mode == "deployed"
    assert res.stages["install"].status.value == "skipped"  # prepared env
    assert res.stages["boot"].status.value == "skipped"
    assert res.stages["boot"].reason == "skipped:deployed-needs-db"
    assert res.highest_stage == "boot"


def test_unknown_mode_skips_boot(tmp_path: Path) -> None:
    _write_app(tmp_path, settings_header="# no mode header")
    res = deploy_app_local(tmp_path, runner_python=sys.executable)
    assert res.mode == "unknown"
    assert res.stages["boot"].reason == "skipped:mode-unknown"
    assert any(d.code == "mode-ambiguous" for d in res.deviations)


def test_harness_env_records_timeouts(tmp_path: Path) -> None:
    _write_app(tmp_path, settings_header="# startd8-mode: deployed")
    res = deploy_app_local(
        tmp_path, runner_python=sys.executable, install_timeout_s=123, boot_timeout_s=45
    )
    assert res.harness_env.install_timeout_s == 123
    assert res.harness_env.boot_timeout_s == 45
