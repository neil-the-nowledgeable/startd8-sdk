"""OQ-5: the Python build gate wired into the prime-contractor postmortem evaluator.

Mirrors `_evaluate_ts_toolchain`: env-gated (STARTD8_PY_TYPECHECK), attributes real compileall/mypy
faults to the owning feature, and treats mypy import-resolution noise (absent generated-app deps) as
an infra condition, not a code fault. The filter/attribution tests monkeypatch the gate so they're
deterministic regardless of whether mypy is installed; one test exercises real compileall.
"""

from __future__ import annotations

import pytest

from startd8.contractors.prime_postmortem import (
    FeaturePostMortem,
    PrimePostMortemEvaluator,
)
from startd8.validators import python_toolchain as pt
from startd8.validators.python_toolchain import PyDiagnostic, PyToolchainResult

pytestmark = pytest.mark.unit


def _feature(fid="f1", files=("app/models.py",)):
    return FeaturePostMortem(
        feature_id=fid,
        name=fid,
        status="done",
        success=True,
        generated_files=list(files),
    )


def _run(features, project_root):
    PrimePostMortemEvaluator()._evaluate_python_toolchain(features, str(project_root))


def test_gate_off_is_noop(monkeypatch, tmp_path):
    monkeypatch.delenv("STARTD8_PY_TYPECHECK", raising=False)
    f = _feature()
    _run([f], tmp_path)
    assert f.success is True and f.verdict == ""


def test_no_python_files_is_noop(monkeypatch, tmp_path):
    monkeypatch.setenv("STARTD8_PY_TYPECHECK", "1")
    f = _feature(files=("app/templates/x/list.html",))
    _run([f], tmp_path)
    assert f.success is True


def test_real_syntax_error_fails_feature(monkeypatch, tmp_path):
    monkeypatch.setenv("STARTD8_PY_TYPECHECK", "1")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "broken.py").write_text("def f(\n", encoding="utf-8")
    f = _feature(files=("app/broken.py",))
    _run([f], tmp_path)
    assert f.success is False
    assert f.verdict == "FAIL:typecheck"
    cats = [i["category"] for i in f.disk_compliance.semantic_issues]
    assert any(c.startswith("py_compileall") for c in cats)


def test_clean_project_passes(monkeypatch, tmp_path):
    monkeypatch.setenv("STARTD8_PY_TYPECHECK", "1")
    monkeypatch.setattr(
        pt,
        "run_project_check",
        lambda *a, **k: PyToolchainResult(status="checked", diagnostics=[]),
    )
    f = _feature()
    _run([f], tmp_path)
    assert f.success is True and f.verdict == ""


def test_mypy_import_noise_is_filtered(monkeypatch, tmp_path):
    monkeypatch.setenv("STARTD8_PY_TYPECHECK", "1")
    noise = [
        PyDiagnostic(
            "app/models.py",
            3,
            0,
            "import-not-found",
            "Cannot find implementation or library stub for module named 'fastapi'",
            "mypy",
        ),
        PyDiagnostic(
            "app/models.py",
            4,
            0,
            "import-untyped",
            "Skipping analyzing 'sqlmodel'",
            "mypy",
        ),
    ]
    monkeypatch.setattr(
        pt,
        "run_project_check",
        lambda *a, **k: PyToolchainResult(status="checked", diagnostics=noise),
    )
    f = _feature()
    _run([f], tmp_path)
    # provisioning noise only -> no fault
    assert f.success is True and f.verdict == ""


def test_real_mypy_fault_fails_and_attributes(monkeypatch, tmp_path):
    monkeypatch.setenv("STARTD8_PY_TYPECHECK", "1")
    diags = [
        PyDiagnostic(
            "app/models.py",
            3,
            0,
            "import-not-found",
            "Cannot find ... stub for 'fastapi'",
            "mypy",
        ),  # noise
        PyDiagnostic(
            "app/models.py", 10, 5, "name-defined", "Name 'Foo' is not defined", "mypy"
        ),  # real
    ]
    monkeypatch.setattr(
        pt,
        "run_project_check",
        lambda *a, **k: PyToolchainResult(status="checked", diagnostics=diags),
    )
    f = _feature(files=("app/models.py",))
    _run([f], tmp_path)
    assert f.success is False and f.verdict == "FAIL:typecheck"
    msgs = " ".join(i["message"] for i in f.disk_compliance.semantic_issues)
    assert "name-defined" in msgs and "Foo" in msgs
    assert "fastapi" not in msgs  # the import noise was filtered out


def test_unavailable_is_surfaced_not_failed(monkeypatch, tmp_path):
    monkeypatch.setenv("STARTD8_PY_TYPECHECK", "1")
    monkeypatch.setattr(
        pt,
        "run_project_check",
        lambda *a, **k: PyToolchainResult(status="error", message="path not found"),
    )
    f = _feature()
    _run([f], tmp_path)
    # FR-9: unavailable is annotated as a warning, never a silent pass nor a hard fail
    assert f.success is True
    cats = [i["category"] for i in f.disk_compliance.semantic_issues]
    assert "py_verification_unavailable" in cats
