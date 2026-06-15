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
