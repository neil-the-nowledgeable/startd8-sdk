"""Python project build gate (Step 3 / FR-5): compileall floor + optional mypy/pytest.

Mirrors ts_toolchain's verdict contract + loud-degradation. The pure parsers are tested without
mypy/pytest installed; the orchestrator is tested via the always-available compileall floor so the
suite is deterministic regardless of whether mypy/pytest are present.
"""

from __future__ import annotations

import pytest

from startd8.backend_codegen import render_pydantic_models
from startd8.validators.python_toolchain import (
    PyToolchainResult,
    parse_compileall_output,
    parse_mypy_output,
    python_typecheck_enabled,
    run_project_check,
)

pytestmark = pytest.mark.unit

SCHEMA = "model Widget {\n  id String @id\n  name String\n  qty Int?\n}\n"


# --------------------------------------------------------------------------- #
# Pure parsers
# --------------------------------------------------------------------------- #


def test_parse_mypy_output_with_and_without_col_and_code():
    text = (
        "app/models.py:10:5: error: Name 'Foo' is not defined  [name-defined]\n"
        "app/x.py:3: error: Incompatible return value type\n"
        "note: some non-error note line\n"
    )
    diags = parse_mypy_output(text)
    assert len(diags) == 2
    assert (diags[0].file, diags[0].line, diags[0].col, diags[0].code) == (
        "app/models.py",
        10,
        5,
        "name-defined",
    )
    assert diags[1].col == 0 and diags[1].code == ""
    assert all(d.stage == "mypy" for d in diags)


def test_parse_compileall_output_syntax_error():
    text = (
        "*** Error compiling '/p/app/models.py'...\n"
        '  File "/p/app/models.py", line 7\n'
        "    def f(\n"
        "         ^\n"
        "SyntaxError: '(' was never closed\n"
    )
    diags = parse_compileall_output(text)
    assert len(diags) == 1
    assert diags[0].file == "/p/app/models.py"
    assert diags[0].line == 7
    assert diags[0].code == "SyntaxError"
    assert diags[0].stage == "compileall"


# --------------------------------------------------------------------------- #
# Verdict contract
# --------------------------------------------------------------------------- #


def test_verdict_contract():
    assert PyToolchainResult(status="unavailable").verdict == "unavailable"
    assert PyToolchainResult(status="unavailable").is_pass is False
    assert PyToolchainResult(status="error").is_pass is False
    assert PyToolchainResult(status="checked", diagnostics=[]).is_pass is True
    from startd8.validators.python_toolchain import PyDiagnostic

    d = PyDiagnostic("f.py", 1, 0, "X", "m", "compileall")
    assert PyToolchainResult(status="checked", diagnostics=[d]).verdict == "fail"


# --------------------------------------------------------------------------- #
# Orchestrator (compileall floor — deterministic regardless of mypy/pytest)
# --------------------------------------------------------------------------- #


def test_clean_generated_project_passes_compileall_floor(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "models.py").write_text(
        render_pydantic_models(SCHEMA).text, encoding="utf-8"
    )
    res = run_project_check(tmp_path, run_mypy=False, run_pytest=False)
    assert res.status == "checked"
    assert res.is_pass is True
    assert "compileall" in res.stages_run
    # absence is recorded, never a silent pass (loud degradation)
    assert "mypy" in res.stages_skipped and "pytest" in res.stages_skipped


def test_syntax_error_fails_with_diagnostic(tmp_path):
    (tmp_path / "broken.py").write_text("def f(\n", encoding="utf-8")
    res = run_project_check(tmp_path, run_mypy=False, run_pytest=False)
    assert res.status == "checked"
    assert res.is_pass is False
    assert any(d.stage == "compileall" for d in res.diagnostics)


def test_nonexistent_path_is_error_not_pass(tmp_path):
    res = run_project_check(tmp_path / "nope", run_mypy=False, run_pytest=False)
    assert res.status == "error"
    assert res.is_pass is False


def test_full_run_does_not_crash_and_runs_compileall(tmp_path):
    # mypy/pytest may or may not be installed; assert only that the gate completes and the floor ran.
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "models.py").write_text(
        render_pydantic_models(SCHEMA).text, encoding="utf-8"
    )
    res = run_project_check(tmp_path)
    assert res.status == "checked"
    assert "compileall" in res.stages_run
    assert res.verdict in ("pass", "fail")


def test_toggle_default_off(monkeypatch):
    monkeypatch.delenv("STARTD8_PY_TYPECHECK", raising=False)
    assert python_typecheck_enabled() is False
    monkeypatch.setenv("STARTD8_PY_TYPECHECK", "1")
    assert python_typecheck_enabled() is True
