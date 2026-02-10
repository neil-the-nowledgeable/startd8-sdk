"""
Assertion functions for validating WorkflowResult objects in tests.

All functions raise AssertionError with descriptive messages on failure,
making them compatible with pytest's assertion introspection.
"""

from typing import List

from ..workflows.models import WorkflowResult


def assert_workflow_success(result: WorkflowResult) -> None:
    """Assert that a workflow completed successfully.

    Raises AssertionError with workflow_id, error message, and per-step
    status summary on failure.
    """
    if not result.success:
        step_summary = "\n".join(
            f"  - {s.step_name}: {'OK' if s.success else f'FAILED: {s.error}'}"
            for s in result.steps
        )
        raise AssertionError(
            f"Workflow '{result.workflow_id}' failed: {result.error}\n"
            f"Steps:\n{step_summary}"
        )


def assert_step_called(result: WorkflowResult, step_name: str) -> None:
    """Assert that a specific step was executed."""
    names = [s.step_name for s in result.steps]
    if step_name not in names:
        raise AssertionError(
            f"Step '{step_name}' was not called. "
            f"Executed steps: {names}"
        )


def assert_step_not_called(result: WorkflowResult, step_name: str) -> None:
    """Assert that a specific step was NOT executed."""
    names = [s.step_name for s in result.steps]
    if step_name in names:
        raise AssertionError(
            f"Step '{step_name}' was called but should not have been. "
            f"Executed steps: {names}"
        )


def assert_cost_below(result: WorkflowResult, max_cost: float) -> None:
    """Assert that total workflow cost is within budget."""
    actual = result.metrics.total_cost
    if actual > max_cost:
        raise AssertionError(
            f"Workflow cost ${actual:.4f} exceeds limit ${max_cost:.4f}"
        )


def assert_steps_in_order(result: WorkflowResult, expected: List[str]) -> None:
    """Assert that steps appeared in the given order (gaps allowed).

    The expected steps must appear in order within the actual step list,
    but other steps may appear between them.
    """
    actual = [s.step_name for s in result.steps]
    idx = 0
    for name in expected:
        try:
            idx = actual.index(name, idx) + 1
        except ValueError:
            raise AssertionError(
                f"Expected step order {expected}, "
                f"but '{name}' not found after position {idx}. "
                f"Actual: {actual}"
            )
