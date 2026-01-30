"""
Tests for Phase 1.3 Testing Assertions: FR-500 through FR-504.
"""

import pytest

from startd8.workflows.models import WorkflowResult, WorkflowMetrics, StepResult
from startd8.testing import (
    assert_workflow_success,
    assert_step_called,
    assert_step_not_called,
    assert_cost_below,
    assert_steps_in_order,
)


def _make_result(success=True, error=None, steps=None, cost=0.0):
    """Helper to build WorkflowResult for tests."""
    return WorkflowResult(
        workflow_id="test-workflow",
        success=success,
        output="test output",
        error=error,
        metrics=WorkflowMetrics(total_cost=cost),
        steps=steps or [],
    )


def _make_step(name, error=None):
    """Helper to build StepResult. Per Lesson 10.7: success is derived from error."""
    return StepResult(step_name=name, error=error)


class TestAssertWorkflowSuccess:
    """FR-501: assert_workflow_success."""

    def test_passes_on_success(self):
        result = _make_result(success=True)
        assert_workflow_success(result)  # Should not raise

    def test_fails_with_details(self):
        steps = [
            _make_step("step1"),
            _make_step("step2", error="Something broke"),
        ]
        result = _make_result(success=False, error="Workflow failed", steps=steps)
        with pytest.raises(AssertionError, match="test-workflow"):
            assert_workflow_success(result)

    def test_error_includes_step_statuses(self):
        steps = [
            _make_step("draft"),
            _make_step("review", error="Bad output"),
        ]
        result = _make_result(success=False, error="Review failed", steps=steps)
        with pytest.raises(AssertionError) as exc_info:
            assert_workflow_success(result)
        msg = str(exc_info.value)
        assert "draft: OK" in msg
        assert "review: FAILED" in msg


class TestAssertStepCalled:
    """FR-502: assert_step_called / assert_step_not_called."""

    def test_step_called_found(self):
        result = _make_result(steps=[_make_step("draft"), _make_step("review")])
        assert_step_called(result, "draft")  # Should not raise

    def test_step_called_not_found(self):
        result = _make_result(steps=[_make_step("draft")])
        with pytest.raises(AssertionError, match="review"):
            assert_step_called(result, "review")

    def test_step_not_called_absent(self):
        result = _make_result(steps=[_make_step("draft")])
        assert_step_not_called(result, "review")  # Should not raise

    def test_step_not_called_found(self):
        result = _make_result(steps=[_make_step("draft"), _make_step("review")])
        with pytest.raises(AssertionError, match="review"):
            assert_step_not_called(result, "review")


class TestAssertCostBelow:
    """FR-503: assert_cost_below."""

    def test_cost_below_passes(self):
        result = _make_result(cost=0.05)
        assert_cost_below(result, 0.10)  # Should not raise

    def test_cost_below_fails(self):
        result = _make_result(cost=0.15)
        with pytest.raises(AssertionError, match=r"\$0\.15.+\$0\.10"):
            assert_cost_below(result, 0.10)

    def test_cost_exactly_equal_passes(self):
        result = _make_result(cost=0.10)
        assert_cost_below(result, 0.10)  # Equal is not exceeding


class TestAssertStepsInOrder:
    """FR-504: assert_steps_in_order."""

    def test_exact_order_passes(self):
        result = _make_result(steps=[
            _make_step("draft"),
            _make_step("review"),
            _make_step("integrate"),
        ])
        assert_steps_in_order(result, ["draft", "review", "integrate"])

    def test_allows_gaps(self):
        result = _make_result(steps=[
            _make_step("draft"),
            _make_step("polish"),
            _make_step("review"),
            _make_step("integrate"),
        ])
        assert_steps_in_order(result, ["draft", "review", "integrate"])

    def test_fails_wrong_order(self):
        result = _make_result(steps=[
            _make_step("review"),
            _make_step("draft"),
        ])
        with pytest.raises(AssertionError, match="draft"):
            assert_steps_in_order(result, ["draft", "review"])

    def test_fails_missing_step(self):
        result = _make_result(steps=[_make_step("draft")])
        with pytest.raises(AssertionError, match="review"):
            assert_steps_in_order(result, ["draft", "review"])
