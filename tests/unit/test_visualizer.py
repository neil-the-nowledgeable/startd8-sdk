"""
Tests for Phase 3.3 Visualization:
- FR-420: Pipeline structure → Mermaid flowchart
- FR-421: WorkflowResult → Mermaid with status colors
- FR-530: CLI command (structure only)
"""

import pytest
from unittest.mock import MagicMock
from typing import Dict, Any, List, Optional

from startd8.orchestration import (
    Pipeline,
    PipelineStep,
    ConditionalStep,
    ParallelStep,
    WorkflowStep,
)
from startd8.workflows.visualizer import WorkflowVisualizer
from startd8.workflows.models import (
    WorkflowResult,
    WorkflowMetrics,
    StepResult,
)


def _make_mock_agent(name="mock-agent", model="mock-model"):
    agent = MagicMock()
    agent.name = name
    agent.model = model
    return agent


# =========================================================================
# FR-420: Pipeline structure visualization
# =========================================================================

class TestPipelineToMermaid:
    def test_mermaid_sequential(self):
        """Sequential steps shown as linear flow."""
        p = Pipeline(name="seq")
        p.add_step("step_a", _make_mock_agent())
        p.add_step("step_b", _make_mock_agent())

        diagram = WorkflowVisualizer.to_mermaid(p)
        assert "graph TD" in diagram
        assert "start([Start])" in diagram
        assert "step0[step_a]" in diagram
        assert "step1[step_b]" in diagram
        assert "finish([End])" in diagram
        assert "start --> step0" in diagram
        assert "step0 --> step1" in diagram

    def test_mermaid_conditional_diamond(self):
        """ConditionalSteps shown as diamond decision nodes."""
        p = Pipeline(name="cond")
        agent = _make_mock_agent()
        p.add_conditional("check", lambda x: True, if_agent=agent)

        diagram = WorkflowVisualizer.to_mermaid(p)
        assert "{check}" in diagram
        assert "-->|True|" in diagram

    def test_mermaid_conditional_with_else(self):
        p = Pipeline(name="cond-else")
        agent = _make_mock_agent()
        else_agent = _make_mock_agent(name="else-agent")
        p.add_conditional("decide", lambda x: True, if_agent=agent, else_agent=else_agent)

        diagram = WorkflowVisualizer.to_mermaid(p)
        assert "-->|True|" in diagram
        assert "-->|False|" in diagram

    def test_mermaid_parallel_fork_join(self):
        """ParallelSteps shown as fork/join pattern."""
        p = Pipeline(name="par")
        agent1 = _make_mock_agent(name="a1")
        agent2 = _make_mock_agent(name="a2")
        p.add_parallel("fan-out", steps=[
            PipelineStep(name="p1", agent=agent1),
            PipelineStep(name="p2", agent=agent2),
        ])

        diagram = WorkflowVisualizer.to_mermaid(p)
        assert "Fork" in diagram
        assert "Join" in diagram
        assert "p1" in diagram
        assert "p2" in diagram

    def test_mermaid_workflow_subgraph(self):
        """WorkflowSteps shown as sub-graph."""
        p = Pipeline(name="compose")
        mock_wf = MagicMock()
        mock_wf.metadata.name = "Sub Workflow"
        p.add_workflow("enhance", mock_wf, lambda x: {})

        diagram = WorkflowVisualizer.to_mermaid(p)
        assert "subgraph" in diagram
        assert "enhance" in diagram
        assert "Sub Workflow" in diagram

    def test_mermaid_empty_pipeline(self):
        p = Pipeline(name="empty")
        diagram = WorkflowVisualizer.to_mermaid(p)
        assert "graph TD" in diagram
        assert "start([Start])" in diagram
        assert "finish([End])" in diagram

    def test_mermaid_returns_string(self):
        p = Pipeline(name="test")
        p.add_step("s1", _make_mock_agent())
        diagram = WorkflowVisualizer.to_mermaid(p)
        assert isinstance(diagram, str)


# =========================================================================
# FR-421: Post-execution visualization
# =========================================================================

class TestResultToMermaid:
    def test_result_mermaid_success_colors(self):
        result = WorkflowResult(
            workflow_id="test",
            success=True,
            output="done",
            steps=[
                StepResult(step_name="step1", output="ok", time_ms=100),
                StepResult(step_name="step2", output="ok", time_ms=200),
            ],
        )
        diagram = WorkflowVisualizer.to_mermaid(result)
        assert ":::success" in diagram
        assert "classDef success fill:#2ecc71" in diagram

    def test_result_mermaid_failure_colors(self):
        result = WorkflowResult(
            workflow_id="test",
            success=False,
            output=None,
            error="something broke",
            steps=[
                StepResult(step_name="step1", output="ok", time_ms=50),
                StepResult(step_name="step2", output="", time_ms=0, error="boom"),
            ],
        )
        diagram = WorkflowVisualizer.to_mermaid(result)
        assert ":::failure" in diagram
        assert "classDef failure fill:#e74c3c" in diagram
        assert "ERROR:" in diagram

    def test_result_mermaid_timing(self):
        result = WorkflowResult(
            workflow_id="test",
            success=True,
            output="done",
            steps=[
                StepResult(step_name="fast", output="ok", time_ms=42),
            ],
        )
        diagram = WorkflowVisualizer.to_mermaid(result)
        assert "42ms" in diagram

    def test_result_mermaid_step_flow(self):
        result = WorkflowResult(
            workflow_id="test",
            success=True,
            output="done",
            steps=[
                StepResult(step_name="a", output="ok", time_ms=10),
                StepResult(step_name="b", output="ok", time_ms=20),
                StepResult(step_name="c", output="ok", time_ms=30),
            ],
        )
        diagram = WorkflowVisualizer.to_mermaid(result)
        assert "step0 --> step1" in diagram
        assert "step1 --> step2" in diagram

    def test_result_empty_steps(self):
        result = WorkflowResult(
            workflow_id="test",
            success=True,
            output="done",
            steps=[],
        )
        diagram = WorkflowVisualizer.to_mermaid(result)
        assert "graph TD" in diagram


# =========================================================================
# Error handling
# =========================================================================

class TestVisualizerErrorHandling:
    def test_invalid_input_type(self):
        with pytest.raises(TypeError, match="Expected Pipeline or WorkflowResult"):
            WorkflowVisualizer.to_mermaid("not valid")  # type: ignore
