# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Tests for the shared verification core (verdict / coverage / scorecard)."""

from __future__ import annotations

from startd8.verification import (
    BINDING,
    Section,
    Verdict,
    compute_coverage,
    is_binding,
    render_scorecard,
    table,
)


def test_verdict_binding_set():
    assert Verdict.PASS in BINDING and Verdict.BOUND_NO_DATA in BINDING
    assert Verdict.FAIL not in BINDING
    assert is_binding("pass") and is_binding("bound_no_data")
    assert not is_binding("fail") and not is_binding("error")


def test_compute_coverage_binding_vs_data():
    c = compute_coverage(["pass", "pass", "bound_no_data", "fail"])
    assert c.total == 4 and c.excluded == 0 and c.denominator == 4
    assert c.data == 2 and c.bound == 3
    assert c.data_coverage == 0.5 and c.binding_coverage == 0.75


def test_compute_coverage_excludes_from_denominator():
    c = compute_coverage(["pass", "fail", "excluded", "excluded"])
    # excluded leave the denominator: 1 bound / 2 applicable = 0.5
    assert c.excluded == 2 and c.denominator == 2
    assert c.binding_coverage == 0.5


def test_compute_coverage_extra_excluded():
    # queries excluded before becoming verdicts (template-var skips) still don't count
    c = compute_coverage(["pass", "fail"], extra_excluded=3)
    assert c.total == 5 and c.excluded == 3 and c.denominator == 2
    assert c.binding_coverage == 0.5


def test_compute_coverage_empty_is_zero_not_error():
    c = compute_coverage([])
    assert c.denominator == 0 and c.binding_coverage == 0.0


def test_accepts_verdict_enum_and_str():
    c = compute_coverage([Verdict.PASS, "pass"])
    assert c.bound == 2


def test_table_and_scorecard_render():
    assert table(["a", "b"], []) == "_(none)_"
    t = table(["svc", "cov"], [["x", "100%"]])
    assert "| svc | cov |" in t and "| x | 100% |" in t
    md = render_scorecard(
        title="T", headline=["**BLUF**"],
        sections=[Section("Sec", t)], footer="fin",
    )
    assert md.startswith("# T") and "## Sec" in md and "fin" in md
