"""
Tests for DesignPolishWorkflow.
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import Dict, Any

from startd8.workflows.builtin.design_polish_workflow import DesignPolishWorkflow
from startd8.workflows.models import AgentCount, ValidationResult


class TestDesignPolishWorkflowMetadata:
    """Test DesignPolishWorkflow metadata."""

    def test_workflow_id(self):
        """Test workflow has correct ID."""
        workflow = DesignPolishWorkflow()
        assert workflow.metadata.workflow_id == "design-polish"

    def test_workflow_name(self):
        """Test workflow has descriptive name."""
        workflow = DesignPolishWorkflow()
        assert workflow.metadata.name == "Design Polish Workflow"

    def test_workflow_requires_exactly_3_agents(self):
        """Test workflow requires exactly 3 agents."""
        workflow = DesignPolishWorkflow()
        assert workflow.metadata.requires_agents is True
        assert workflow.metadata.agent_count == AgentCount.MULTIPLE
        assert workflow.metadata.min_agents == 3
        assert workflow.metadata.max_agents == 3

    def test_workflow_inputs(self):
        """Test workflow defines correct inputs."""
        workflow = DesignPolishWorkflow()
        inputs = {inp.name: inp for inp in workflow.metadata.inputs}

        assert "document" in inputs
        assert inputs["document"].required is True
        assert inputs["document"].type == "text"

        assert "agents" in inputs
        assert inputs["agents"].required is True
        assert inputs["agents"].type == "agent_spec_list"

        assert "prompt_instructions" in inputs
        assert inputs["prompt_instructions"].required is False

    def test_workflow_capabilities(self):
        """Test workflow has expected capabilities."""
        workflow = DesignPolishWorkflow()
        assert "document-polish" in workflow.metadata.capabilities
        assert "multi-agent" in workflow.metadata.capabilities


class TestDesignPolishWorkflowValidation:
    """Test DesignPolishWorkflow validation."""

    def test_valid_config(self):
        """Test valid configuration passes validation."""
        workflow = DesignPolishWorkflow()
        result = workflow.validate_config({
            "document": "# Design Document\nSome content here",
            "agents": ["mock:mock", "mock:mock", "mock:mock"]
        })
        assert result.valid is True
        assert len(result.errors) == 0

    def test_missing_document(self):
        """Test validation fails when document is missing."""
        workflow = DesignPolishWorkflow()
        result = workflow.validate_config({
            "agents": ["mock:mock", "mock:mock", "mock:mock"]
        })
        assert result.valid is False
        assert "document" in str(result.errors)

    def test_empty_document(self):
        """Test validation fails when document is empty."""
        workflow = DesignPolishWorkflow()
        result = workflow.validate_config({
            "document": "",
            "agents": ["mock:mock", "mock:mock", "mock:mock"]
        })
        assert result.valid is False
        assert "empty" in str(result.errors).lower()

    def test_whitespace_only_document(self):
        """Test validation fails when document is whitespace only."""
        workflow = DesignPolishWorkflow()
        result = workflow.validate_config({
            "document": "   \n\t  ",
            "agents": ["mock:mock", "mock:mock", "mock:mock"]
        })
        assert result.valid is False

    def test_missing_agents(self):
        """Test validation fails when agents are missing."""
        workflow = DesignPolishWorkflow()
        result = workflow.validate_config({
            "document": "# Design Document"
        })
        assert result.valid is False
        assert "agents" in str(result.errors).lower()

    def test_wrong_agent_count_too_few(self):
        """Test validation fails with fewer than 3 agents."""
        workflow = DesignPolishWorkflow()
        result = workflow.validate_config({
            "document": "# Design Document",
            "agents": ["mock:mock", "mock:mock"]
        })
        assert result.valid is False
        assert "3" in str(result.errors)

    def test_wrong_agent_count_too_many(self):
        """Test validation fails with more than 3 agents."""
        workflow = DesignPolishWorkflow()
        result = workflow.validate_config({
            "document": "# Design Document",
            "agents": ["mock:mock", "mock:mock", "mock:mock", "mock:mock"]
        })
        assert result.valid is False
        assert "3" in str(result.errors)

    def test_optional_prompt_instructions(self):
        """Test prompt_instructions is optional."""
        workflow = DesignPolishWorkflow()
        result = workflow.validate_config({
            "document": "# Design Document",
            "agents": ["mock:mock", "mock:mock", "mock:mock"],
            "prompt_instructions": "Focus on API design clarity"
        })
        assert result.valid is True


class TestDesignPolishWorkflowExecution:
    """Test DesignPolishWorkflow execution."""

    @pytest.fixture
    def mock_agents(self):
        """Create mock agents for testing."""
        agents = []
        for i, name in enumerate(["polisher", "updater", "final-polisher"]):
            agent = MagicMock()
            agent.name = name
            agent.model = "mock-model"
            agent.generate.return_value = (
                f"Output from {name}",
                100 + i * 50,
                MagicMock(input_tokens=100, output_tokens=50, cost=0.01)
            )
            agents.append(agent)
        return agents

    @pytest.fixture
    def mock_pipeline_result(self):
        """Create mock pipeline result."""
        result = MagicMock()
        result.success = True
        result.final_output = "Final polished document content"
        result.pipeline_name = "design-polish-chain"
        result.error = None
        result.steps = []

        # Add mock step results
        for i, name in enumerate(["polish", "suggest_updates", "final_polish"]):
            step = MagicMock()
            step.step_name = name
            step.agent_name = f"agent-{i}"
            step.output = f"Output from {name}"
            step.time_ms = 100 + i * 50
            step.token_usage = MagicMock(
                input_tokens=100,
                output_tokens=50,
                cost=0.01
            )
            step.error = None
            result.steps.append(step)

        return result

    @patch("startd8.workflows.builtin.design_polish_workflow.resolve_agents")
    @patch("startd8.workflows.builtin.design_polish_workflow.WorkflowTemplates")
    def test_successful_execution(
        self, mock_templates, mock_resolve, mock_agents, mock_pipeline_result
    ):
        """Test successful workflow execution."""
        mock_resolve.return_value = mock_agents
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = mock_pipeline_result
        mock_templates.design_polish_chain.return_value = mock_pipeline

        workflow = DesignPolishWorkflow()
        result = workflow.run(config={
            "document": "# Design Document\nContent here",
            "agents": ["mock:mock", "mock:mock", "mock:mock"]
        })

        assert result.success is True
        assert result.output == "Final polished document content"
        assert result.workflow_id == "design-polish"
        assert result.error is None

    @patch("startd8.workflows.builtin.design_polish_workflow.resolve_agents")
    @patch("startd8.workflows.builtin.design_polish_workflow.WorkflowTemplates")
    def test_execution_tracks_metrics(
        self, mock_templates, mock_resolve, mock_agents, mock_pipeline_result
    ):
        """Test execution tracks metrics correctly."""
        mock_resolve.return_value = mock_agents
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = mock_pipeline_result
        mock_templates.design_polish_chain.return_value = mock_pipeline

        workflow = DesignPolishWorkflow()
        result = workflow.run(config={
            "document": "# Design Document",
            "agents": ["mock:mock", "mock:mock", "mock:mock"]
        })

        assert result.metrics is not None
        assert result.metrics.step_count == 3
        assert result.metrics.total_time_ms > 0
        assert result.metrics.input_tokens > 0
        assert result.metrics.output_tokens > 0
        assert result.metrics.total_cost > 0

    @patch("startd8.workflows.builtin.design_polish_workflow.resolve_agents")
    @patch("startd8.workflows.builtin.design_polish_workflow.WorkflowTemplates")
    def test_execution_with_custom_instructions(
        self, mock_templates, mock_resolve, mock_agents, mock_pipeline_result
    ):
        """Test custom prompt_instructions are passed to pipeline."""
        mock_resolve.return_value = mock_agents
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = mock_pipeline_result
        mock_templates.design_polish_chain.return_value = mock_pipeline

        workflow = DesignPolishWorkflow()
        result = workflow.run(config={
            "document": "# Design Document",
            "agents": ["mock:mock", "mock:mock", "mock:mock"],
            "prompt_instructions": "Focus on API design clarity"
        })

        # Verify custom instructions were passed
        mock_templates.design_polish_chain.assert_called_once()
        call_kwargs = mock_templates.design_polish_chain.call_args[1]
        assert call_kwargs["prompt_instructions"] == "Focus on API design clarity"

    @patch("startd8.workflows.builtin.design_polish_workflow.resolve_agents")
    def test_execution_fails_with_wrong_agent_count(self, mock_resolve):
        """Test execution fails if wrong number of agents resolved."""
        mock_resolve.return_value = [MagicMock(), MagicMock()]  # Only 2 agents

        workflow = DesignPolishWorkflow()
        result = workflow.run(config={
            "document": "# Design Document",
            "agents": ["mock:mock", "mock:mock"]  # Only 2 specified
        })

        assert result.success is False
        assert "3 agents required" in result.error

    @patch("startd8.workflows.builtin.design_polish_workflow.resolve_agents")
    @patch("startd8.workflows.builtin.design_polish_workflow.WorkflowTemplates")
    def test_execution_handles_pipeline_error(
        self, mock_templates, mock_resolve, mock_agents
    ):
        """Test execution handles pipeline errors gracefully."""
        mock_resolve.return_value = mock_agents
        mock_pipeline = MagicMock()
        mock_pipeline.run.side_effect = RuntimeError("Pipeline failed")
        mock_templates.design_polish_chain.return_value = mock_pipeline

        workflow = DesignPolishWorkflow()
        result = workflow.run(config={
            "document": "# Design Document",
            "agents": ["mock:mock", "mock:mock", "mock:mock"]
        })

        assert result.success is False
        assert "Pipeline failed" in result.error

    @patch("startd8.workflows.builtin.design_polish_workflow.resolve_agents")
    @patch("startd8.workflows.builtin.design_polish_workflow.WorkflowTemplates")
    def test_execution_includes_agent_metadata(
        self, mock_templates, mock_resolve, mock_agents, mock_pipeline_result
    ):
        """Test result includes agent metadata."""
        mock_resolve.return_value = mock_agents
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = mock_pipeline_result
        mock_templates.design_polish_chain.return_value = mock_pipeline

        workflow = DesignPolishWorkflow()
        result = workflow.run(config={
            "document": "# Design Document",
            "agents": ["mock:mock", "mock:mock", "mock:mock"]
        })

        assert result.metadata is not None
        assert "polisher" in result.metadata
        assert "updater" in result.metadata
        assert "final_polisher" in result.metadata

    @patch("startd8.workflows.builtin.design_polish_workflow.resolve_agents")
    @patch("startd8.workflows.builtin.design_polish_workflow.WorkflowTemplates")
    def test_execution_reports_progress(
        self, mock_templates, mock_resolve, mock_agents, mock_pipeline_result
    ):
        """Test execution calls progress callback."""
        mock_resolve.return_value = mock_agents
        mock_pipeline = MagicMock()
        mock_pipeline.run.return_value = mock_pipeline_result
        mock_templates.design_polish_chain.return_value = mock_pipeline

        progress_calls = []

        def track_progress(current: int, total: int, message: str):
            progress_calls.append((current, total, message))

        workflow = DesignPolishWorkflow()
        result = workflow.run(
            config={
                "document": "# Design Document",
                "agents": ["mock:mock", "mock:mock", "mock:mock"]
            },
            on_progress=track_progress
        )

        # Should have at least the start progress call
        assert len(progress_calls) >= 1
        assert progress_calls[0][1] == 3  # total_steps


class TestDesignPolishWorkflowRegistration:
    """Test DesignPolishWorkflow registration."""

    def test_workflow_can_be_imported(self):
        """Test workflow can be imported from builtin package."""
        from startd8.workflows.builtin import DesignPolishWorkflow
        assert DesignPolishWorkflow is not None

    def test_workflow_conforms_to_protocol(self):
        """Test workflow conforms to WorkflowBase protocol."""
        from startd8.workflows import WorkflowBase
        workflow = DesignPolishWorkflow()
        assert isinstance(workflow, WorkflowBase)
