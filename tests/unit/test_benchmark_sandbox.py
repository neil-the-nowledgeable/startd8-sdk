"""M4.1 — untrusted-code sandbox (FR-44).

Adversarial fixtures prove the controls hold: secret env vars are scrubbed, a wall-clock
timeout fires, CPU/resource limits kill runaway code (recorded as a sandbox violation, NOT
model quality), and network egress is blocked where the OS supports it.
"""
from __future__ import annotations

import sys

import pytest

from startd8.benchmark_matrix.sandbox import (
    SandboxConfig,
    run_sandboxed,
    sandbox_caps,
    scrub_env,
)


def test_scrub_env_removes_secrets_and_redirects_home(tmp_path):
    base = {
        "ANTHROPIC_API_KEY": "sk-secret", "OPENAI_API_KEY": "sk-x", "DOPPLER_TOKEN": "dp.x",
        "AWS_SECRET_ACCESS_KEY": "z", "PATH": "/usr/bin", "HOME": "/Users/real", "FOO": "ok",
    }
    env = scrub_env(tmp_path, base=base)
    for leaked in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "DOPPLER_TOKEN", "AWS_SECRET_ACCESS_KEY"):
        assert leaked not in env
    assert env["PATH"] == "/usr/bin"      # toolchain resolution preserved
    assert env["FOO"] == "ok"             # non-secret preserved
    assert env["HOME"] == str(tmp_path)   # dotfiles/creds unreachable


def test_benign_command_runs(tmp_path):
    r = run_sandboxed([sys.executable, "-c", "print('hello')"], tmp_path,
                      SandboxConfig(wall_timeout_s=30))
    assert r.returncode == 0 and "hello" in r.stdout and r.violation is None


def test_secret_env_is_not_visible_to_untrusted_code(tmp_path, monkeypatch):
    # Adversary fixture: code tries to read an API key. The harness has it set; the sandbox must not.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-must-not-leak")
    code = "import os; print('LEAK=' + (os.environ.get('ANTHROPIC_API_KEY') or 'NONE'))"
    r = run_sandboxed([sys.executable, "-c", code], tmp_path, SandboxConfig(wall_timeout_s=30))
    assert "LEAK=NONE" in r.stdout, r.stdout


def test_wall_timeout_is_enforced(tmp_path):
    r = run_sandboxed([sys.executable, "-c", "import time; time.sleep(10)"], tmp_path,
                      SandboxConfig(wall_timeout_s=1.0))
    assert r.timed_out is True
    assert r.violation and "timeout" in r.violation


@pytest.mark.skipif(not sandbox_caps()["rlimits"], reason="no setrlimit on this platform")
def test_cpu_limit_kills_runaway_code(tmp_path):
    # Busy loop should hit RLIMIT_CPU (1s) and be killed by signal -> violation (not quality).
    r = run_sandboxed([sys.executable, "-c", "while True: pass"], tmp_path,
                      SandboxConfig(cpu_seconds=1, wall_timeout_s=20))
    assert r.violation is not None
    assert r.returncode != 0


def test_isolation_level_reported(tmp_path):
    r = run_sandboxed([sys.executable, "-c", "pass"], tmp_path, SandboxConfig(wall_timeout_s=20))
    assert r.isolation_level  # non-empty; records which controls applied
    assert ("rlimits" in r.isolation_level) or r.isolation_level == "none(best-effort)"


@pytest.mark.skipif(not sandbox_caps()["sandbox_exec"], reason="network isolation needs sandbox-exec (macOS)")
def test_network_egress_blocked_when_supported(tmp_path):
    code = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 443), timeout=5); print('NET_OK')\n"
        "except Exception as e:\n"
        "    print('NET_BLOCKED')\n"
    )
    r = run_sandboxed([sys.executable, "-c", code], tmp_path,
                      SandboxConfig(no_network=True, wall_timeout_s=20))
    assert r.network_isolated is True
    assert "NET_BLOCKED" in r.stdout, r.stdout
