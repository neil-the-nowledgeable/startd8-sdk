"""Unit tests for the shared-netns substrate (OQ-7 prototype) — macOS-runnable, NO netns required.

These exercise everything that does NOT need a live namespace: the ``unshare -rn`` command
construction (incl. the mandatory ``ip link set lo up``), the JSON result protocol round-trip, the
process-group teardown logic (mocked subprocess), and the honest degrade-on-unavailable path. The
live netns behavior is proven separately by the Linux-gated smoke (``tests/integration/
test_netns_substrate_smoke.py``), which SKIPS on macOS.
"""
from __future__ import annotations

import json
from unittest import mock

import pytest

from startd8.benchmark_matrix import netns_substrate as ns
from startd8.benchmark_matrix.netns_substrate import (
    CellRunnerSpec,
    NetnsCellResult,
    build_netns_command,
    emit_cell_payload,
    netns_available,
    parse_cell_payload,
    run_cell_in_shared_netns,
)


# --------------------------------------------------------------------------- command construction
def test_build_command_wraps_in_rootless_unshare_and_brings_lo_up():
    cmd = build_netns_command(["python3", "/tmp/cell_runner.py", "--spec", "x"])
    # Single rootless unshare with BOTH user-ns root mapping and net-ns (`-rn`).
    assert cmd[0] == "unshare"
    assert cmd[1] == "-rn"
    assert cmd[2:4] == ["sh", "-c"]
    inner = cmd[4]
    # `lo` MUST be brought up before anything binds/connects loopback.
    assert inner.startswith("ip link set lo up && exec ")
    # The cell runner command survives intact after `exec`.
    assert "python3" in inner and "/tmp/cell_runner.py" in inner and "--spec" in inner


def test_build_command_shell_quotes_runner_args_with_spaces():
    cmd = build_netns_command(["python3", "/tmp/a b/cell.py"])
    inner = cmd[4]
    # The path containing a space must be quoted so the shell does not split it.
    assert "'/tmp/a b/cell.py'" in inner
    assert inner.startswith("ip link set lo up && exec ")


# --------------------------------------------------------------------------- JSON result protocol
def test_emit_and_parse_payload_round_trip():
    payload = {"coverage": 0.75, "results": [{"name": "step1", "passed": True}]}
    line = emit_cell_payload(payload)
    assert line.startswith(ns.RESULT_BEGIN) and line.endswith(ns.RESULT_END)
    assert parse_cell_payload(line) == payload


def test_parse_payload_ignores_surrounding_log_noise():
    payload = {"coverage": 1.0, "results": []}
    stdout = "server starting...\nbound on 127.0.0.1:54321\n" + emit_cell_payload(payload) + "\nbye\n"
    assert parse_cell_payload(stdout) == payload


def test_parse_payload_uses_last_marked_span():
    first = emit_cell_payload({"coverage": 0.0, "results": []})
    second = emit_cell_payload({"coverage": 1.0, "results": [{"name": "x", "passed": True}]})
    # rfind on BEGIN → the LAST payload wins (a retry/re-emit supersedes earlier output).
    assert parse_cell_payload(first + "noise" + second)["coverage"] == 1.0


@pytest.mark.parametrize("stdout", ["", "no markers here", "<CELL_RESULT_BEGIN>not json<CELL_RESULT_END>",
                                    "<CELL_RESULT_BEGIN>{unterminated"])
def test_parse_payload_returns_none_on_missing_or_malformed(stdout):
    assert parse_cell_payload(stdout) is None


def test_parse_payload_rejects_non_dict_json():
    # A bare list is valid JSON but not a result dict → rejected.
    blob = ns.RESULT_BEGIN + json.dumps([1, 2, 3]) + ns.RESULT_END
    assert parse_cell_payload(blob) is None


# --------------------------------------------------------------------------- cell-runner contract
def test_cell_runner_spec_json_round_trip():
    spec = CellRunnerSpec(
        suite="checkout",
        serve_argv=["sh", "-c", "cd /x && exec ./.bin/server"],
        serve_env={"PORT": "5050"},
        stub_env_names=["PRODUCT_CATALOG_SERVICE_ADDR", "CART_SERVICE_ADDR"],
        tier="hardened",
        readiness_timeout_s=20.0,
    )
    back = CellRunnerSpec.from_json(spec.to_json())
    assert back == spec


# --------------------------------------------------------------------------- degrade-on-unavailable
def test_run_degrades_when_netns_unavailable(monkeypatch):
    # Force unavailable (the macOS reality) → no-op-skip outcome, NOT a launched subprocess.
    monkeypatch.setattr(ns, "netns_available", lambda: False)
    with mock.patch.object(ns.subprocess, "Popen") as popen:
        res = run_cell_in_shared_netns(["python3", "runner.py"])
    popen.assert_not_called()
    assert isinstance(res, NetnsCellResult)
    assert res.available is False
    assert res.ready is False
    assert res.payload is None
    assert res.network_isolated is False
    assert res.violation and "netns unavailable" in res.violation


def test_netns_available_false_on_darwin(monkeypatch):
    monkeypatch.setattr(ns.sys, "platform", "darwin")
    # Even if a stray `unshare` were on PATH, non-linux short-circuits to False.
    assert netns_available() is False


def test_netns_available_false_when_unshare_missing(monkeypatch):
    monkeypatch.setattr(ns.sys, "platform", "linux")
    monkeypatch.setattr(ns.shutil, "which", lambda _name: None)
    assert netns_available() is False


# --------------------------------------------------------------------------- teardown / lifecycle (mocked)
class _FakePopen:
    """Minimal Popen stand-in: records communicate/teardown without a real subprocess."""

    def __init__(self, *, stdout="", poll_returns=0, raise_timeout_first_communicate=False):
        self.pid = 4242
        self.returncode = poll_returns
        self._stdout = stdout
        self._poll = poll_returns
        self._communicate_calls = 0
        self._raise_timeout_first = raise_timeout_first_communicate
        self.signals_sent = []

    def poll(self):
        return self._poll

    def communicate(self, timeout=None):
        self._communicate_calls += 1
        if self._raise_timeout_first and self._communicate_calls == 1:
            raise ns.subprocess.TimeoutExpired(cmd="x", timeout=timeout)
        # First successful communicate returns the cell stdout; the post-teardown drain returns empty.
        return (self._stdout if self._communicate_calls == 1 else ""), ""

    def wait(self, timeout=None):
        return self.returncode

    def send_signal(self, sig):
        self.signals_sent.append(sig)


def _patch_launch(monkeypatch, fake):
    monkeypatch.setattr(ns, "netns_available", lambda: True)
    monkeypatch.setattr(ns.subprocess, "Popen", lambda *a, **k: fake)


def test_run_parses_payload_and_reports_isolated(monkeypatch):
    payload = {"coverage": 1.0, "results": [{"name": "loopback_peer_reach", "passed": True}]}
    fake = _FakePopen(stdout="log line\n" + emit_cell_payload(payload), poll_returns=0)
    _patch_launch(monkeypatch, fake)
    # Group teardown is a no-op here (poll() != None path): patch killpg to assert it's attempted.
    with mock.patch.object(ns.os, "killpg") as killpg, \
         mock.patch.object(ns.os, "getpgid", return_value=4242):
        # Make teardown see a live process once so killpg fires, then report dead.
        fake._poll = None
        res = run_cell_in_shared_netns(["python3", "runner.py"], timeout=30.0)
    assert res.available is True
    assert res.ready is True
    assert res.payload == payload
    assert res.network_isolated is True
    assert res.violation is None
    assert res.isolation_level == "rootless-shared-netns"
    killpg.assert_called()  # the whole cell group was torn down


def test_run_sets_violation_when_no_payload(monkeypatch):
    fake = _FakePopen(stdout="server crashed, no result\n", poll_returns=3)
    _patch_launch(monkeypatch, fake)
    with mock.patch.object(ns.os, "killpg"), mock.patch.object(ns.os, "getpgid", return_value=4242):
        res = run_cell_in_shared_netns(["python3", "runner.py"])
    assert res.available is True
    assert res.ready is False
    assert res.payload is None
    assert res.violation and "no parseable result payload" in res.violation


def test_run_times_out_and_degrades(monkeypatch):
    fake = _FakePopen(stdout=emit_cell_payload({"coverage": 1.0, "results": []}),
                      poll_returns=0, raise_timeout_first_communicate=True)
    _patch_launch(monkeypatch, fake)
    with mock.patch.object(ns.os, "killpg"), mock.patch.object(ns.os, "getpgid", return_value=4242):
        res = run_cell_in_shared_netns(["python3", "runner.py"], timeout=0.01)
    assert res.available is True
    # On timeout we do NOT trust a payload (the run was cut off) → degrade.
    assert res.payload is None
    assert res.violation and "timeout" in res.violation


def test_run_handles_launch_exception(monkeypatch):
    monkeypatch.setattr(ns, "netns_available", lambda: True)

    def _boom(*a, **k):
        raise OSError("no fork for you")

    monkeypatch.setattr(ns.subprocess, "Popen", _boom)
    res = run_cell_in_shared_netns(["python3", "runner.py"])
    assert res.available is True
    assert res.payload is None
    assert res.violation and "netns launch error" in res.violation
