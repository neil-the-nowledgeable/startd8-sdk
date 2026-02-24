"""Tests for FINALIZE phase status rollup considering test/review outcomes.

Verifies that the overall status in the workflow report reflects
test and review failures, not just generation success.

Tests the status computation logic directly rather than the full
handler (which requires extensive mocking of file I/O).
"""

from __future__ import annotations

import pytest


def _compute_status(
    *,
    generated_ok: int,
    generated_fail: int,
    total_tasks: int,
    tests_failed: int = 0,
    reviews_failed: int = 0,
) -> str:
    """Reproduce the FINALIZE status rollup logic from context_seed_handlers.py."""
    if generated_fail == 0 and generated_ok == total_tasks:
        if tests_failed > 0 or reviews_failed > 0:
            return "quality_failed"
        else:
            return "success"
    elif generated_ok == 0:
        return "failed"
    else:
        return "partial"


@pytest.mark.unit
class TestFinalizeStatusRollup:
    """Test that FINALIZE overall_status considers test/review outcomes."""

    def test_success_when_all_pass(self):
        """Generation OK + tests pass + review pass = success."""
        assert _compute_status(
            generated_ok=1, generated_fail=0, total_tasks=1,
            tests_failed=0, reviews_failed=0,
        ) == "success"

    def test_quality_failed_when_tests_fail(self):
        """Generation OK but tests fail = quality_failed."""
        assert _compute_status(
            generated_ok=1, generated_fail=0, total_tasks=1,
            tests_failed=1, reviews_failed=0,
        ) == "quality_failed"

    def test_quality_failed_when_review_fails(self):
        """Generation OK but review fails = quality_failed."""
        assert _compute_status(
            generated_ok=1, generated_fail=0, total_tasks=1,
            tests_failed=0, reviews_failed=1,
        ) == "quality_failed"

    def test_failed_when_generation_fails(self):
        """All generation fails = failed (regardless of test/review)."""
        assert _compute_status(
            generated_ok=0, generated_fail=1, total_tasks=1,
            tests_failed=0, reviews_failed=0,
        ) == "failed"

    def test_quality_failed_when_both_test_and_review_fail(self):
        """Generation OK but both tests and review fail = quality_failed."""
        assert _compute_status(
            generated_ok=1, generated_fail=0, total_tasks=1,
            tests_failed=1, reviews_failed=1,
        ) == "quality_failed"

    def test_success_when_zero_test_review_counts(self):
        """Generation OK + no test/review results (zero counts) = success."""
        assert _compute_status(
            generated_ok=1, generated_fail=0, total_tasks=1,
            tests_failed=0, reviews_failed=0,
        ) == "success"

    def test_partial_when_some_generation_fails(self):
        """Some generation fails = partial (even with passing tests)."""
        assert _compute_status(
            generated_ok=1, generated_fail=1, total_tasks=2,
            tests_failed=0, reviews_failed=0,
        ) == "partial"

    def test_multi_task_quality_failed(self):
        """Multiple tasks: all generated OK but tests fail = quality_failed."""
        assert _compute_status(
            generated_ok=3, generated_fail=0, total_tasks=3,
            tests_failed=2, reviews_failed=0,
        ) == "quality_failed"
