"""FR-1 — sandboxed generated-app oracle runner."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.oracle_loop import (
    VERDICT_ERROR,
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_SKIP,
)
from startd8.oracle_loop import runner as runner_mod
from startd8.oracle_loop.runner import run_oracle

pytestmark = pytest.mark.unit

_FIX = Path(__file__).parent / "fixtures"
_APP = _FIX / "passing_app"


class _FakeSandboxResult:
    def __init__(self, returncode=0, violation=None):
        self.returncode = returncode
        self.stdout = ""
        self.stderr = "boom" if returncode else ""
        self.violation = violation
        self.isolation_level = "rlimits+seatbelt"


def test_oneshot_runs_via_sandbox_and_passes(monkeypatch):
    calls = {}

    def _fake_run_sandboxed(cmd, workspace, cfg=None, **kw):
        calls["cmd"] = cmd
        return _FakeSandboxResult(returncode=0)

    monkeypatch.setattr(runner_mod, "run_sandboxed", _fake_run_sandboxed)
    verdicts = run_oracle(_FIX / "passing_spec.md", _APP, live_port=8000)
    by_id = {v.fr_id: v for v in verdicts}
    assert by_id["FR-1"].verdict == VERDICT_PASS
    assert by_id["FR-1"].isolation_level == "rlimits+seatbelt"
    assert calls["cmd"][0] == "pytest"  # ran through the sandbox boundary


def test_oneshot_nonzero_is_fail_not_error(monkeypatch):
    monkeypatch.setattr(
        runner_mod, "run_sandboxed",
        lambda *a, **k: _FakeSandboxResult(returncode=1),
    )
    verdicts = run_oracle(_FIX / "passing_spec.md", _APP, live_port=8000)
    assert {v.fr_id: v.verdict for v in verdicts}["FR-1"] == VERDICT_FAIL


def test_sandbox_violation_degrades_to_error_not_model_fail(monkeypatch):
    """Env failure (violation) → error (degrade), never the model's fail (FR-1)."""
    monkeypatch.setattr(
        runner_mod, "run_sandboxed",
        lambda *a, **k: _FakeSandboxResult(returncode=-9, violation="killed by signal 9"),
    )
    verdicts = run_oracle(_FIX / "passing_spec.md", _APP, live_port=8000)
    assert {v.fr_id: v.verdict for v in verdicts}["FR-1"] == VERDICT_ERROR


def test_service_probe_against_live_port(monkeypatch):
    """The service probe uses a fixed loopback client rendered from the data-only struct."""
    class _Resp:
        status_code = 200

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def request(self, method, url, json=None):
            assert method == "GET"
            assert url.endswith("/health")
            return _Resp()

    import httpx

    monkeypatch.setattr(httpx, "Client", _Client)
    monkeypatch.setattr(runner_mod, "run_sandboxed", lambda *a, **k: _FakeSandboxResult(0))
    verdicts = run_oracle(_FIX / "passing_spec.md", _APP, live_port=9999)
    assert {v.fr_id: v.verdict for v in verdicts}["FR-2"] == VERDICT_PASS


def test_non_runnable_fr_yields_skip(monkeypatch):
    monkeypatch.setattr(runner_mod, "run_sandboxed", lambda *a, **k: _FakeSandboxResult(0))
    verdicts = run_oracle(_FIX / "passing_spec.md", _APP, live_port=8000)
    fr3 = {v.fr_id: v for v in verdicts}["FR-3"]
    assert fr3.verdict == VERDICT_SKIP
    assert fr3.assertion_text  # residue preserved


def test_runner_never_imports_navigator_evaluate():
    """FR-1/NR-2: the runner must not import or call verify_oracle.evaluate/classify."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(runner_mod))
    # No import of verify_oracle.
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert "verify_oracle" not in (node.module or "")
        if isinstance(node, ast.Import):
            assert all("verify_oracle" not in a.name for a in node.names)
        # No call to classify(...) / evaluate(...).
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in ("classify", "evaluate")


def test_unresolved_console_script_is_error_not_executed(tmp_path, monkeypatch):
    """Harvest H1 (security): a bare verb that is NOT pytest/python and has no app/bin entry point
    (e.g. `rm`) must fail loud as ERROR — never fall through to a sandbox-PATH exec."""
    ran = {"called": False}

    def _boom(*a, **k):
        ran["called"] = True
        raise AssertionError("run_sandboxed must not be called for an unresolved console-script")

    monkeypatch.setattr(runner_mod, "run_sandboxed", _boom)
    from startd8.oracle_loop.grammar import ParsedClause, KIND_ONESHOT
    from startd8.oracle_loop.runner import _run_oneshot
    from startd8.benchmark_matrix.sandbox import SandboxConfig

    clause = ParsedClause(fr_id="FR-1", kind=KIND_ONESHOT,
                          command_argv=("rm", "-rf", "app"), is_console_script=True)
    v = _run_oneshot(clause, tmp_path, SandboxConfig())
    assert v.verdict == VERDICT_ERROR and "unresolved console-script" in v.reason
    assert ran["called"] is False   # never executed
