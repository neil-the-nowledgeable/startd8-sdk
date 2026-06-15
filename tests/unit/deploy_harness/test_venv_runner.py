"""M1 unit tests for venv_runner.py — network-free pieces (rlimits, venv creation, tail)."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from startd8.deploy_harness import ResourceLimits, create_venv
from startd8.deploy_harness.venv_runner import _tail

pytestmark = pytest.mark.unit


def test_resource_limits_preexec_callable_on_posix() -> None:
    fn = ResourceLimits().preexec()
    if os.name == "posix":
        assert callable(fn)
    else:  # pragma: no cover
        assert fn is None


def test_resource_limits_all_none_is_noop_callable() -> None:
    fn = ResourceLimits(
        address_space_bytes=None, max_processes=None, cpu_seconds=None
    ).preexec()
    if os.name == "posix":
        fn()  # must not raise even with nothing to set


def test_tail_keeps_last_lines() -> None:
    text = "\n".join(str(i) for i in range(100))
    out = _tail(text, lines=5)
    assert out.splitlines() == ["95", "96", "97", "98", "99"]
    assert _tail("") == ""
    assert _tail(None) == ""


@pytest.mark.slow
def test_create_venv_yields_working_interpreter(tmp_path) -> None:
    v = create_venv(tmp_path)
    assert v.python.exists()
    out = subprocess.run(
        [str(v.python), "--version"], capture_output=True, text=True, timeout=30
    )
    assert "Python" in (out.stdout or out.stderr)
    # the venv interpreter is NOT the SDK interpreter (FR-4 isolation)
    assert str(v.python) != sys.executable


# --------------------------------------------------------------------------- editable install mode


def test_build_pip_cmd_plain() -> None:
    from startd8.deploy_harness.venv_runner import _build_pip_cmd

    cmd = _build_pip_cmd("/v/python", ["fastapi", "startd8"], [], build_isolation=True)
    assert cmd[:4] == ["/v/python", "-m", "pip", "install"]
    assert "-e" not in cmd
    assert "fastapi" in cmd and "uvicorn[standard]" in cmd  # runner dep appended


def test_build_pip_cmd_with_editable_precedes_packages() -> None:
    from startd8.deploy_harness.venv_runner import _build_pip_cmd

    cmd = _build_pip_cmd(
        "/v/python", ["fastapi", "startd8"], ["/abs/startd8-sdk"], build_isolation=True
    )
    # editable appears as `-e <path>` and BEFORE the bare `startd8` requirement
    assert "-e" in cmd and "/abs/startd8-sdk" in cmd
    assert cmd.index("/abs/startd8-sdk") < cmd.index("startd8")


def test_build_pip_cmd_no_build_isolation_flag() -> None:
    from startd8.deploy_harness.venv_runner import _build_pip_cmd

    cmd = _build_pip_cmd("/v/python", ["fastapi"], [], build_isolation=False)
    assert "--no-build-isolation" in cmd


def test_pip_run_reason_phase_labels() -> None:
    from startd8.deploy_harness.venv_runner import _PipRun

    assert (
        _PipRun(ok=False, returncode=1, duration_s=0).reason("editable")
        == "editable-pip-exit-1"
    )
    assert (
        _PipRun(ok=False, returncode=1, duration_s=0).reason("install") == "pip-exit-1"
    )
    assert (
        _PipRun(
            ok=False, returncode=None, duration_s=0, timed_out=True, timeout_s=600
        ).reason("install")
        == "install-timeout:600s"
    )


def test_nproc_disabled_by_default() -> None:
    # RLIMIT_NPROC's per-user-total semantics make a fixed cap unsafe → off by default.
    assert ResourceLimits().max_processes is None
    assert ResourceLimits().address_space_bytes is not None  # memory cap stays on
