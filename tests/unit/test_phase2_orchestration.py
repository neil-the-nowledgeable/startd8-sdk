"""
Tests for Phase 2 Core Orchestration:
- 2.1 Retry Resilience (FR-100, FR-101, FR-300, FR-301, FR-410, FR-411)
- 2.2 Mixed Steps / isinstance dispatch (FR-310)
- 2.3 Conditional Routing (FR-311, FR-312)
- 2.4 Parallel Execution (FR-320, FR-321, FR-322)
- 2.5 Workflow Composition (FR-330, FR-331, FR-332)
"""

import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from typing import Dict, Any, List, Optional

from startd8.orchestration import (
    Pipeline,
    PipelineStep,
    ConditionalStep,
    ParallelStep,
    WorkflowStep,
    StepType,
    is_retryable,
)
from startd8.workflows.models import (
    RetryPolicy,
    WorkflowMetrics,
    WorkflowResult,
    StepResult,
    ValidationResult,
)
from startd8.events import EventType
from startd8.exceptions import ConfigurationError, AgentError


# =========================================================================
# Helpers
# =========================================================================

def _make_mock_agent(name="mock-agent", model="mock-model", response="mock output"):
    """Create a mock agent with sync and async generate/create_response."""
    agent = MagicMock()
    agent.name = name
    agent.model = model

    # Mock token usage
    token_usage = MagicMock()
    token_usage.total = 100
    token_usage.cost_estimate = 0.001
    token_usage.input_tokens = 50
    token_usage.output_tokens = 50

    # Mock agent response
    agent_response = MagicMock()
    agent_response.response = response
    agent_response.response_time_ms = 50
    agent_response.token_usage = token_usage
    agent_response.id = "resp-123"
    agent_response.timestamp = None

    agent.acreate_response = AsyncMock(return_value=agent_response)
    agent.agenerate = AsyncMock(return_value=(response, 50, token_usage))
    return agent


# =========================================================================
# 2.1 Retry Resilience
# =========================================================================

class TestRetryPolicy:
    """FR-100: RetryPolicy dataclass."""

    def test_defaults(self):
        policy = RetryPolicy()
        assert policy.max_retries == 3
        assert policy.backoff_base == 1.0
        assert policy.backoff_max == 60.0
        assert policy.jitter is True
        assert 429 in policy.retryable_status_codes

    def test_custom_values(self):
        policy = RetryPolicy(max_retries=5, backoff_base=2.0, jitter=False)
        assert policy.max_retries == 5
        assert policy.backoff_base == 2.0
        assert policy.jitter is False


class TestIsRetryable:
    """FR-301: Error classification."""

    def test_timeout_is_retryable(self):
        assert is_retryable(TimeoutError(), [429, 500])

    def test_connection_error_is_retryable(self):
        assert is_retryable(ConnectionError(), [429, 500])

    def test_asyncio_timeout_is_retryable(self):
        assert is_retryable(asyncio.TimeoutError(), [429, 500])

    def test_configuration_error_not_retryable(self):
        assert not is_retryable(ConfigurationError("bad config"), [429, 500])

    def test_status_code_attribute_retryable(self):
        exc = Exception("rate limited")
        exc.status_code = 429
        assert is_retryable(exc, [429, 500])

    def test_status_code_401_not_retryable(self):
        exc = Exception("unauthorized")
        exc.status_code = 401
        assert not is_retryable(exc, [429, 500])

    def test_generic_exception_not_retryable(self):
        assert not is_retryable(ValueError("bad value"), [429, 500])


class TestWorkflowMetricsRetries:
    """FR-411: total_retries in WorkflowMetrics."""

    def test_total_retries_default(self):
        m = WorkflowMetrics()
        assert m.total_retries == 0

    def test_total_retries_in_to_dict(self):
        m = WorkflowMetrics(total_retries=3)
        d = m.to_dict()
        assert d["total_retries"] == 3


class TestPipelineRetryEvent:
    """FR-410: PIPELINE_STEP_RETRY event type exists."""

    def test_event_type_exists(self):
        assert hasattr(EventType, 'PIPELINE_STEP_RETRY')


# =========================================================================
# 2.2 Mixed Steps — isinstance dispatch (FR-310)
# =========================================================================

class TestMixedStepTypes:
    """FR-310: Pipeline accepts multiple step types."""

    def test_pipeline_steps_accepts_pipeline_step(self):
        p = Pipeline(name="test")
        agent = _make_mock_agent()
        p.add_step("step1", agent)
        assert isinstance(p.steps[0], PipelineStep)

    def test_pipeline_steps_accepts_conditional_step(self):
        p = Pipeline(name="test")
        agent = _make_mock_agent()
        p.add_conditional("cond", predicate=lambda x: True, if_agent=agent)
        assert isinstance(p.steps[0], ConditionalStep)

    def test_pipeline_steps_accepts_parallel_step(self):
        p = Pipeline(name="test")
        agent = _make_mock_agent()
        steps = [PipelineStep(name="p1", agent=agent)]
        p.add_parallel("par", steps=steps)
        assert isinstance(p.steps[0], ParallelStep)

    def test_pipeline_steps_accepts_workflow_step(self):
        p = Pipeline(name="test")
        mock_wf = MagicMock()
        p.add_workflow("wf", workflow=mock_wf, config_mapping=lambda x: {})
        assert isinstance(p.steps[0], WorkflowStep)

    def test_mixed_step_types_in_single_pipeline(self):
        p = Pipeline(name="test")
        agent = _make_mock_agent()
        p.add_step("seq", agent)
        p.add_conditional("cond", lambda x: True, agent)
        p.add_parallel("par", [PipelineStep(name="p1", agent=agent)])
        assert len(p.steps) == 3
        assert isinstance(p.steps[0], PipelineStep)
        assert isinstance(p.steps[1], ConditionalStep)
        assert isinstance(p.steps[2], ParallelStep)

    def test_unknown_step_type_raises(self):
        """Manually inserting an unknown type should raise wrapped AgentError at runtime."""
        p = Pipeline(name="test")
        p.steps.append("not a step")  # type: ignore
        with pytest.raises(AgentError, match="Unknown step type"):
            asyncio.run(p.arun("input"))


# =========================================================================
# 2.3 Conditional Routing (FR-311, FR-312)
# =========================================================================

class TestConditionalStep:
    """FR-311, FR-312: ConditionalStep and Pipeline.add_conditional()."""

    def test_conditional_dataclass(self):
        agent = _make_mock_agent()
        step = ConditionalStep(
            name="test",
            predicate=lambda x: True,
            if_step=PipelineStep(name="if", agent=agent),
        )
        assert step.name == "test"
        assert step.else_step is None
        assert step.metadata == {}

    def test_add_conditional_returns_self(self):
        p = Pipeline(name="test")
        result = p.add_conditional("c", lambda x: True, _make_mock_agent())
        assert result is p

    def test_conditional_true_branch(self):
        agent_if = _make_mock_agent(response="if branch output")
        p = Pipeline(name="test")
        p.add_conditional("c", lambda x: "yes" in x, if_agent=agent_if)

        result = p.run("yes please")
        assert "if branch output" in result.final_output

    def test_conditional_false_no_else_passthrough(self):
        agent_if = _make_mock_agent(response="if output")
        p = Pipeline(name="test")
        p.add_conditional("c", lambda x: False, if_agent=agent_if)

        result = p.run("input text")
        # No else_step → pass through unchanged
        assert result.final_output == "input text"

    def test_conditional_false_with_else(self):
        agent_if = _make_mock_agent(response="if output")
        agent_else = _make_mock_agent(response="else output")
        p = Pipeline(name="test")
        p.add_conditional("c", lambda x: False, if_agent=agent_if, else_agent=agent_else)

        result = p.run("input text")
        assert "else output" in result.final_output


# =========================================================================
# 2.4 Parallel Execution (FR-320, FR-321, FR-322)
# =========================================================================

class TestParallelStep:
    """FR-320, FR-321, FR-322: ParallelStep and Pipeline.add_parallel()."""

    def test_parallel_dataclass(self):
        step = ParallelStep(name="par", steps=[])
        assert step.failure_policy == "collect_all"
        assert step.aggregator is not None

    def test_default_aggregator_joins(self):
        step = ParallelStep(name="par", steps=[])
        result = step.aggregator(["a", "b", "c"])
        assert "a" in result
        assert "---" in result
        assert "c" in result

    def test_add_parallel_returns_self(self):
        p = Pipeline(name="test")
        result = p.add_parallel("par", steps=[])
        assert result is p

    def test_parallel_runs_concurrently(self):
        agent1 = _make_mock_agent(name="agent1", response="output1")
        agent2 = _make_mock_agent(name="agent2", response="output2")

        p = Pipeline(name="test")
        p.add_parallel("par", steps=[
            PipelineStep(name="s1", agent=agent1),
            PipelineStep(name="s2", agent=agent2),
        ])

        result = p.run("shared input")
        assert "output1" in result.final_output
        assert "output2" in result.final_output

    def test_parallel_custom_aggregator(self):
        agent1 = _make_mock_agent(response="A")
        agent2 = _make_mock_agent(response="B")

        p = Pipeline(name="test")
        p.add_parallel(
            "par",
            steps=[
                PipelineStep(name="s1", agent=agent1),
                PipelineStep(name="s2", agent=agent2),
            ],
            aggregator=lambda outputs: " + ".join(outputs),
        )

        result = p.run("input")
        assert "A + B" in result.final_output

    def test_parallel_collect_all_partial_failure(self):
        """collect_all policy: run all, include errors in output."""
        agent_ok = _make_mock_agent(response="ok")
        agent_fail = _make_mock_agent()
        agent_fail.acreate_response = AsyncMock(side_effect=TimeoutError("timeout"))

        p = Pipeline(name="test")
        p.add_parallel("par", steps=[
            PipelineStep(name="ok", agent=agent_ok),
            PipelineStep(name="fail", agent=agent_fail),
        ], failure_policy="collect_all")

        result = p.run("input")
        assert "ok" in result.final_output
        assert "ERROR" in result.final_output


# =========================================================================
# 2.5 Workflow Composition (FR-330, FR-331, FR-332)
# =========================================================================

class TestWorkflowStep:
    """FR-330, FR-331, FR-332: WorkflowStep and Pipeline.add_workflow()."""

    def test_workflow_step_dataclass(self):
        mock_wf = MagicMock()
        step = WorkflowStep(
            name="sub", workflow=mock_wf,
            config_mapping=lambda x: {"input": x}
        )
        assert step.name == "sub"
        assert step.metadata == {}

    def test_add_workflow_returns_self(self):
        p = Pipeline(name="test")
        mock_wf = MagicMock()
        result = p.add_workflow("sub", mock_wf, lambda x: {})
        assert result is p

    def test_workflow_step_delegates(self):
        """Sub-workflow is called and its output propagated."""
        mock_wf = MagicMock()
        mock_wf.validate_config.return_value = ValidationResult.success()
        mock_wf.run.return_value = WorkflowResult(
            workflow_id="sub-wf",
            success=True,
            output="sub-workflow output",
            metrics=WorkflowMetrics(input_tokens=10, output_tokens=20, total_cost=0.001),
            steps=[StepResult(step_name="sub_step1", output="sub out")],
        )
        # No arun → falls back to run
        del mock_wf.arun

        p = Pipeline(name="test")
        p.add_workflow("sub", mock_wf, lambda x: {"input": x})

        result = p.run("input text")
        assert "sub-workflow output" in result.final_output
        mock_wf.validate_config.assert_called_once()
        mock_wf.run.assert_called_once()

    def test_workflow_step_validation_failure(self):
        mock_wf = MagicMock()
        mock_wf.validate_config.return_value = ValidationResult.failure(["bad input"])

        p = Pipeline(name="test")
        p.add_workflow("sub", mock_wf, lambda x: {"input": x})

        with pytest.raises(Exception, match="validation failed"):
            p.run("input text")

    def test_workflow_step_metrics_aggregated(self):
        """FR-332: Sub-workflow metrics aggregated into parent."""
        mock_wf = MagicMock()
        mock_wf.validate_config.return_value = ValidationResult.success()
        mock_wf.run.return_value = WorkflowResult(
            workflow_id="sub-wf",
            success=True,
            output="result",
            metrics=WorkflowMetrics(
                input_tokens=100, output_tokens=200, total_cost=0.05
            ),
            steps=[],
        )
        del mock_wf.arun

        p = Pipeline(name="test")
        p.add_workflow("sub", mock_wf, lambda x: {})

        result = p.run("input")
        assert result.total_cost >= 0.05
        assert result.total_tokens >= 300

    def test_workflow_step_steps_namespaced(self):
        """FR-332: Sub-workflow steps are flattened with namespace prefix."""
        mock_wf = MagicMock()
        mock_wf.validate_config.return_value = ValidationResult.success()
        mock_wf.run.return_value = WorkflowResult(
            workflow_id="sub-wf",
            success=True,
            output="result",
            metrics=WorkflowMetrics(),
            steps=[
                StepResult(step_name="draft", output="draft out"),
                StepResult(step_name="review", output="review out"),
            ],
        )
        del mock_wf.arun

        p = Pipeline(name="test")
        p.add_workflow("enhance", mock_wf, lambda x: {})

        result = p.run("input")
        # Steps should be namespaced as "enhance:draft", "enhance:review"
        step_names = [s["step_name"] for s in result.steps]
        assert any("enhance:draft" in name for name in step_names)
        assert any("enhance:review" in name for name in step_names)
