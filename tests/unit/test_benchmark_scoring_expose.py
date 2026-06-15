"""Expose-defects scoring (FR-B3): defect ledger de-saturates the composite."""

import pytest

from startd8.benchmark_matrix.scoring import (
    CompositeScore,
    GateResult,
    apply_defect_penalty,
    compute_composite,
    defect_penalty,
)


def _passing_base(structural=1.0):
    gate = GateResult("compile", available=True, passed=True)
    return compute_composite(structural=structural, compile_gate=gate)


def test_no_defects_leaves_score_unchanged():
    base = _passing_base(1.0)
    out = apply_defect_penalty(base, {"by_severity": {}, "by_category": {}, "total": 0})
    assert out.value == base.value == pytest.approx(1.0)


def test_defects_desaturate_a_compiling_file():
    base = _passing_base(1.0)  # compiles + structural 1.000 → would be 1.0
    ledger = {"by_severity": {"error": 1, "warning": 2}, "by_category": {"sql_injection_risk": 1, "stub": 2}, "total": 3}
    out = apply_defect_penalty(base, ledger)
    assert out.value < 1.0  # the whole point: parses-but-defective no longer tops the board
    assert "defect penalty" in out.note
    assert "defects" in out.terms_available


def test_penalty_is_bounded_and_severity_weighted():
    assert defect_penalty({}) == 0.0
    assert defect_penalty({"error": 100}) == 1.0  # bounded at 1
    # an error weighs more than a warning
    assert defect_penalty({"error": 1}) > defect_penalty({"warning": 1})


def test_penalty_floors_at_zero_not_negative():
    base = CompositeScore(value=0.1, structural=0.1, compile_ok=True, degraded=False)
    out = apply_defect_penalty(base, {"by_severity": {"error": 100}, "total": 100})
    assert out.value >= 0.0
