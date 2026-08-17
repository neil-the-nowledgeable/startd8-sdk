"""FR-6 (coverage/floor/no-fitness) + FR-7 (Goodhart disposition)."""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.oracle_loop import (
    ASSERTION_CONFIRMED_TRUE,
    ASSERTION_UNREVIEWED,
    VERDICT_FAIL,
    VERDICT_PASS,
    VERDICT_SKIP,
    OracleVerdict,
)
from startd8.oracle_loop.grammar import KIND_ASSERTION, KIND_ONESHOT, KIND_SERVICE
from startd8.oracle_loop.loop import (
    CAUSE_COVERAGE_BELOW_FLOOR,
    CAUSE_NO_FITNESS,
    GenOutcome,
    run_build_to_spec_loop,
)
from startd8.oracle_loop.report import (
    STATUS_FITNESS_PASSED,
    STATUS_NO_FITNESS,
    compute_coverage,
    coverage_meets_floor,
    is_spec_satisfied,
    rung_status,
)

pytestmark = pytest.mark.unit

_FIX = Path(__file__).parent / "fixtures"


def _v(fr_id, verdict, kind=KIND_ONESHOT, confirmed=ASSERTION_UNREVIEWED):
    return OracleVerdict(
        fr_id=fr_id, kind=kind, verdict=verdict, assertion_confirmed=confirmed
    )


def test_coverage_and_residue():
    verdicts = [
        _v("FR-1", VERDICT_PASS),
        _v("FR-2", VERDICT_PASS, kind=KIND_SERVICE),
        _v("FR-3", VERDICT_SKIP, kind=KIND_ASSERTION),
    ]
    cov = compute_coverage(verdicts)
    assert cov.total_frs == 3
    assert cov.runnable_frs == 2
    assert cov.residue_fr_ids == ["FR-3"]
    assert cov.coverage == pytest.approx(2 / 3)


def test_empty_runnable_set_is_no_fitness_not_pass():
    verdicts = [_v("FR-1", VERDICT_SKIP, kind=KIND_ASSERTION)]
    assert rung_status(verdicts) == STATUS_NO_FITNESS


def test_all_runnable_pass_is_fitness_passed():
    verdicts = [_v("FR-1", VERDICT_PASS), _v("FR-2", VERDICT_SKIP, kind=KIND_ASSERTION)]
    assert rung_status(verdicts) == STATUS_FITNESS_PASSED


def test_coverage_floor():
    cov = compute_coverage([_v("FR-1", VERDICT_PASS)] + [_v(f"P{i}", VERDICT_SKIP, kind=KIND_ASSERTION) for i in range(3)])
    assert cov.coverage == pytest.approx(0.25)
    assert not coverage_meets_floor(cov, 0.5)
    assert coverage_meets_floor(cov, 0.25)
    assert coverage_meets_floor(cov, None)


def test_spec_satisfied_false_while_any_pass_unreviewed():
    verdicts = [_v("FR-1", VERDICT_PASS, confirmed=ASSERTION_UNREVIEWED)]
    assert is_spec_satisfied(verdicts) is False
    # Only true when every pass is human-confirmed AND fitness passed.
    verdicts2 = [_v("FR-1", VERDICT_PASS, confirmed=ASSERTION_CONFIRMED_TRUE)]
    assert is_spec_satisfied(verdicts2) is True


def test_default_assertion_confirmed_is_unreviewed():
    v = OracleVerdict(fr_id="FR-1", kind=KIND_ONESHOT, verdict=VERDICT_PASS)
    assert v.assertion_confirmed == ASSERTION_UNREVIEWED


def test_no_fitness_spec_terminal(tmp_path, monkeypatch):
    """A spec with zero runnable clauses → no_fitness terminal (never a vacuous green)."""
    from startd8.oracle_loop import runner as runner_mod

    def dep(root):
        # All prose → all skip.
        return [
            OracleVerdict(fr_id="FR-1", kind=KIND_ASSERTION, verdict=VERDICT_SKIP),
            OracleVerdict(fr_id="FR-2", kind=KIND_ASSERTION, verdict=VERDICT_SKIP),
        ]

    report = run_build_to_spec_loop(
        _FIX / "no_fitness_spec.md",
        generate_fn=lambda fb: GenOutcome(app_root=tmp_path),
        deploy_fn=dep, enabled=True,
    )
    assert report.terminal_cause == CAUSE_NO_FITNESS
    assert report.status == STATUS_NO_FITNESS
    assert report.spec_satisfied is False


def test_coverage_below_floor_terminal(tmp_path):
    def dep(root):
        return [
            OracleVerdict(fr_id="FR-1", kind=KIND_ONESHOT, verdict=VERDICT_PASS),
            OracleVerdict(fr_id="FR-2", kind=KIND_ASSERTION, verdict=VERDICT_SKIP),
            OracleVerdict(fr_id="FR-3", kind=KIND_ASSERTION, verdict=VERDICT_SKIP),
            OracleVerdict(fr_id="FR-4", kind=KIND_ASSERTION, verdict=VERDICT_SKIP),
        ]

    report = run_build_to_spec_loop(
        _FIX / "low_coverage_spec.md",
        generate_fn=lambda fb: GenOutcome(app_root=tmp_path),
        deploy_fn=dep, min_coverage=0.5, enabled=True,
    )
    assert report.terminal_cause == CAUSE_COVERAGE_BELOW_FLOOR


def test_report_lists_residue_and_never_says_spec_satisfied(tmp_path):
    def dep(root):
        return [
            OracleVerdict(fr_id="FR-1", kind=KIND_ONESHOT, verdict=VERDICT_PASS),
            OracleVerdict(
                fr_id="FR-3", kind=KIND_ASSERTION, verdict=VERDICT_SKIP,
                assertion_text="a reviewer confirms the docstring",
            ),
        ]

    report = run_build_to_spec_loop(
        _FIX / "passing_spec.md",
        generate_fn=lambda fb: GenOutcome(app_root=tmp_path),
        deploy_fn=dep, enabled=True,
    )
    assert report.status == STATUS_FITNESS_PASSED
    assert report.spec_satisfied is False  # passes are unreviewed
    assert any("FR-3" in line for line in report.residue_lines())
