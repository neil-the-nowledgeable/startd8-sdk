"""
Tests for Phase 3.1 Dry Run:
- FR-102: DryRunResult dataclass
- FR-103: dry_run parameter on run()
- FR-340: Dry run interception (no API calls)
- FR-341: Token/cost estimation
- FR-510: CLI --dry-run flag (structure only)
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import Dict, Any, List, Optional

from startd8.workflows.models import (
    DryRunResult,
    WorkflowMetadata,
    WorkflowInput,
    WorkflowResult,
)
from startd8.workflows.base import WorkflowBase


# =========================================================================
# Test workflow for dry run
# =========================================================================

class DryRunTestWorkflow(WorkflowBase):
    """Minimal workflow with defined inputs for dry run testing."""

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="dry-run-test",
            name="Dry Run Test",
            description="A workflow for testing dry run",
            inputs=[
                WorkflowInput(name="document", type="text", required=True),
                WorkflowInput(name="instructions", type="string", required=False, default=""),
            ],
            requires_agents=False,
        )

    def _execute(self, config, agents=None, on_progress=None):
        # Real execution — should NOT be called during dry run
        return WorkflowResult(
            workflow_id="dry-run-test",
            success=True,
            output="real output",
        )


# =========================================================================
# FR-102: DryRunResult dataclass
# =========================================================================

class TestDryRunResult:
    def test_dataclass_fields(self):
        dr = DryRunResult(
            execution_plan=[{"step": 1, "name": "doc"}],
            estimated_tokens={"doc": {"input": 100, "output": 200}},
            estimated_cost=0.001,
            step_order=["doc"],
        )
        assert dr.execution_plan == [{"step": 1, "name": "doc"}]
        assert dr.estimated_cost == 0.001
        assert dr.step_order == ["doc"]

    def test_to_dict(self):
        dr = DryRunResult(
            execution_plan=[],
            estimated_tokens={},
            estimated_cost=0.0,
            step_order=[],
        )
        d = dr.to_dict()
        assert "execution_plan" in d
        assert "estimated_tokens" in d
        assert "estimated_cost" in d
        assert "step_order" in d

    def test_serializable(self):
        """DryRunResult.to_dict() produces JSON-serializable output."""
        import json
        dr = DryRunResult(
            execution_plan=[{"step": 1, "name": "a"}],
            estimated_tokens={"a": {"input": 10, "output": 20}},
            estimated_cost=0.005,
            step_order=["a"],
        )
        serialized = json.dumps(dr.to_dict())
        assert '"estimated_cost"' in serialized


# =========================================================================
# FR-103 / FR-340: dry_run parameter and interception
# =========================================================================

class TestDryRunExecution:
    def test_dry_run_no_api_calls(self):
        """dry_run=True must NOT call _execute."""
        wf = DryRunTestWorkflow()
        wf._execute = MagicMock(side_effect=AssertionError("Should not be called"))
        result = wf.run({"document": "hello world"}, dry_run=True)
        assert result.success is True
        wf._execute.assert_not_called()

    def test_dry_run_returns_execution_plan(self):
        wf = DryRunTestWorkflow()
        result = wf.run({"document": "hello"}, dry_run=True)
        assert isinstance(result.output, dict)
        plan = result.output
        assert "execution_plan" in plan
        assert "step_order" in plan
        assert len(plan["execution_plan"]) == 2  # document + instructions

    def test_dry_run_metadata_flag(self):
        wf = DryRunTestWorkflow()
        result = wf.run({"document": "test"}, dry_run=True)
        assert result.metadata.get("dry_run") is True

    def test_dry_run_backward_compatible(self):
        """run() without dry_run still executes normally."""
        wf = DryRunTestWorkflow()
        result = wf.run({"document": "hello"})
        assert result.output == "real output"

    def test_dry_run_step_order(self):
        wf = DryRunTestWorkflow()
        result = wf.run({"document": "x"}, dry_run=True)
        assert result.output["step_order"] == ["document", "instructions"]

    def test_dry_run_with_agents(self):
        """Agent names appear in execution plan when provided."""
        wf = DryRunTestWorkflow()
        mock_agent = MagicMock()
        mock_agent.name = "claude"
        result = wf.run({"document": "x"}, agents=[mock_agent], dry_run=True)
        plan = result.output["execution_plan"]
        assert plan[0]["agent"] == "claude"
        assert plan[1]["agent"] == "unassigned"

    def test_dry_run_validation_still_runs(self):
        """Validation runs even on dry run — missing required input fails."""
        wf = DryRunTestWorkflow()
        result = wf.run({}, dry_run=True)
        assert result.success is False
        assert "Validation failed" in result.error


# =========================================================================
# FR-341: Token/cost estimation
# =========================================================================

class TestTokenEstimation:
    def test_estimates_tokens_from_input(self):
        wf = DryRunTestWorkflow()
        result = wf.run({"document": "a" * 400}, dry_run=True)
        tokens = result.output["estimated_tokens"]
        assert "document" in tokens
        assert tokens["document"]["input"] == 100  # 400 chars / 4

    def test_output_estimate_is_2x_input(self):
        wf = DryRunTestWorkflow()
        result = wf.run({"document": "a" * 100}, dry_run=True)
        tokens = result.output["estimated_tokens"]
        assert tokens["document"]["output"] == tokens["document"]["input"] * 2

    def test_estimated_cost_non_negative(self):
        wf = DryRunTestWorkflow()
        result = wf.run({"document": "hello"}, dry_run=True)
        assert result.output["estimated_cost"] >= 0.0

    def test_empty_input_zero_tokens(self):
        wf = DryRunTestWorkflow()
        result = wf.run({"document": ""}, dry_run=True)
        tokens = result.output["estimated_tokens"]
        assert tokens["document"]["input"] == 0
