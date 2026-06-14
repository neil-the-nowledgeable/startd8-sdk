"""M4.2 — compile gate + composite scoring (FR-11 / FR-29 / FR-32)."""
from __future__ import annotations

import pytest

from startd8.benchmark_matrix.scoring import (
    COMPILE_FLOOR,
    GateResult,
    compute_composite,
    score_file,
)


# --- composite logic (pure) --------------------------------------------------

def test_compile_fail_floors_quality():
    gate = GateResult("compile", available=True, passed=False, detail="SyntaxError")
    cs = compute_composite(structural=1.0, compile_gate=gate)
    assert cs.value == COMPILE_FLOOR          # structurally perfect but doesn't compile -> floored
    assert cs.compile_ok is False
    assert cs.degraded is False


def test_compile_pass_uses_structural():
    gate = GateResult("compile", available=True, passed=True)
    cs = compute_composite(structural=0.88, compile_gate=gate)
    assert cs.value == pytest.approx(0.88)
    assert cs.compile_ok is True
    assert "compile" in cs.terms_available


def test_toolchain_absent_is_degraded_not_penalized():
    gate = GateResult("compile", available=False, passed=None, detail="toolchain absent")
    cs = compute_composite(structural=0.9, compile_gate=gate)
    assert cs.value == pytest.approx(0.9)     # FR-32: fall back to structural, don't penalize
    assert cs.compile_ok is None
    assert cs.degraded is True
    assert "compile" in cs.terms_missing


def test_lint_penalty_is_small():
    cgate = GateResult("compile", available=True, passed=True)
    lint = GateResult("lint", available=True, passed=False)
    cs = compute_composite(structural=1.0, compile_gate=cgate, lint_gate=lint)
    assert cs.value == pytest.approx(0.95)    # -0.05, never dominates


# --- real compile gate through the sandbox (Python) --------------------------

@pytest.fixture()
def py_profile():
    from startd8.languages import LanguageRegistry, resolve_language
    LanguageRegistry.discover()
    return resolve_language(["x.py"])


def test_score_file_valid_python_compiles(tmp_path, py_profile):
    f = tmp_path / "good.py"
    f.write_text("def add(a, b):\n    return a + b\n")
    cs = score_file(f, py_profile, structural=0.8, run_lint=False)
    assert cs.compile_ok is True
    assert cs.value == pytest.approx(0.8)


def test_score_file_broken_python_is_floored(tmp_path, py_profile):
    f = tmp_path / "bad.py"
    f.write_text("def broken(:\n    return\n")   # SyntaxError
    cs = score_file(f, py_profile, structural=1.0, run_lint=False)
    assert cs.compile_ok is False
    assert cs.value == COMPILE_FLOOR


def test_score_file_missing_file_floored(tmp_path, py_profile):
    cs = score_file(tmp_path / "nope.py", py_profile, structural=1.0)
    assert cs.value <= COMPILE_FLOOR


# --- Node sandbox-safe syntax fallback (node --check for .js) ----------------

@pytest.fixture()
def js_profile():
    from startd8.languages import LanguageRegistry, resolve_language
    LanguageRegistry.discover()
    return resolve_language(["server.js"])


def test_fallback_syntax_command_scoped_to_node_js():
    from startd8.benchmark_matrix.scoring import fallback_syntax_command
    from startd8.languages import LanguageRegistry, resolve_language
    LanguageRegistry.discover()
    js = resolve_language(["a.js"])
    assert fallback_syntax_command(js, "a.js") == ["node", "--check", "{file}"]
    # .tsx is intentionally NOT covered (node --check breaks on it, REQ-NODE-MP-305)
    assert fallback_syntax_command(js, "a.tsx") is None
    py = resolve_language(["a.py"])
    assert fallback_syntax_command(py, "a.py") is None  # python has its own syntax_check_command


def test_node_js_valid_compiles_via_fallback(tmp_path, js_profile):
    f = tmp_path / "server.js"
    f.write_text("const grpc = require('@grpc/grpc-js');\nfunction charge(req) { return { id: 1 }; }\n")
    cs = score_file(f, js_profile, structural=0.9, run_lint=False)
    assert cs.compile_ok is True            # node --check passes (require not resolved — syntax only)
    assert cs.degraded is False
    assert cs.value == pytest.approx(0.9)


def test_node_js_broken_is_floored_via_fallback(tmp_path, js_profile):
    f = tmp_path / "bad.js"
    f.write_text("const x = ;\nfunction (\n")   # SyntaxError
    cs = score_file(f, js_profile, structural=1.0, run_lint=False)
    assert cs.compile_ok is False
    assert cs.value == COMPILE_FLOOR
