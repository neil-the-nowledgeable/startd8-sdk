"""M-T2.4 ($0 wiring) — the behavioral (functional) term folded into the composite score.

Pure/deterministic (no subprocess): validates the weighting, the gate-floors-first rule, honest
degradation, and that the default (no functional args) path is byte-identical to before.
"""
from __future__ import annotations

import pytest

from startd8.benchmark_matrix.scoring import (
    COMPILE_FLOOR,
    FUNCTIONAL_WEIGHT,
    GateResult,
    compute_composite,
)


def _pass():
    return GateResult("compile", available=True, passed=True)


def _fail():
    return GateResult("compile", available=True, passed=False, detail="syntax error")


def test_functional_folds_in_weighted():
    # structural 1.0 (saturated) + functional 0.0 → pulled to the functional weight; 1.0 → stays 1.0.
    low = compute_composite(1.0, _pass(), functional=0.0)
    assert low.value == pytest.approx(1.0 - FUNCTIONAL_WEIGHT)  # 0.5*0 + 0.5*1.0
    assert "functional" in low.terms_available
    hi = compute_composite(1.0, _pass(), functional=1.0)
    assert hi.value == pytest.approx(1.0)
    # A frontier-saturated structural with partial behavior lands clearly below a complete one.
    partial = compute_composite(1.0, _pass(), functional=1 / 3)
    assert partial.value < hi.value


def test_functional_absent_is_byte_identical():
    # No functional args → value == structural, no functional term, not degraded (unchanged behavior).
    c = compute_composite(0.9, _pass())
    assert c.value == pytest.approx(0.9)
    assert "functional" not in c.terms_available and not c.degraded


def test_compile_fail_floors_before_functional():
    # Gates win: a non-compiling file is floored regardless of (irrelevant) behavioral coverage.
    c = compute_composite(1.0, _fail(), functional=1.0)
    assert c.value == pytest.approx(COMPILE_FLOOR)
    assert "functional" not in c.terms_available  # short-circuited before the functional term


def test_functional_degraded_marks_missing_not_zero():
    # Suite exists but couldn't run → term missing/degraded (FR-32), structural preserved, not zeroed.
    c = compute_composite(0.8, _pass(), functional=None, functional_degraded=True)
    assert c.value == pytest.approx(0.8)
    assert c.degraded and "functional" in c.terms_missing
