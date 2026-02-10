"""
Pytest assertion helpers for testing workflow execution results.

Usage:
    from startd8.testing import assert_workflow_success, assert_step_called

    def test_my_workflow():
        result = workflow.run(config, agents)
        assert_workflow_success(result)
        assert_step_called(result, "draft")
"""

from .assertions import (
    assert_workflow_success,
    assert_step_called,
    assert_step_not_called,
    assert_cost_below,
    assert_steps_in_order,
)

__all__ = [
    "assert_workflow_success",
    "assert_step_called",
    "assert_step_not_called",
    "assert_cost_below",
    "assert_steps_in_order",
]
