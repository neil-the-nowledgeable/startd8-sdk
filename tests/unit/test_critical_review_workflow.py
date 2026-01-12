"""
Tests for CriticalReviewWorkflow.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from typing import Dict, Any

from startd8.workflows.builtin.critical_review_workflow import (
    CriticalReviewWorkflow,
    REVIEW_PROMPT_TEMPLATE,
)
from startd8.workflows.models import AgentCount, ValidationResult


class TestCriticalReviewWorkflowMetadata:
    """Test CriticalReviewWorkflow metadata."""

    def test_workflow_id(self):
        """Test workflow has correct ID."""
        workflow = CriticalReviewWorkflow()
        assert workflow.metadata.workflow_id == "critical-review"

    def test_workflow_name(self):
        """Test workflow has descriptive name."""
        workflow = CriticalReviewWorkflow()
        assert workflow.metadata.name == "Critical Review Workflow"

    def test_workflow_requires_configurable_agents(self):
        """Test workflow supports configurable number of agents."""
        workflow = CriticalReviewWorkflow()
        assert workflow.metadata.requires_agents is True
        assert workflow.metadata.agent_count == AgentCount.CONFIGURABLE
        assert workflow.metadata.min_agents == 1
        assert workflow.metadata.max_agents is None

    def test_workflow_inputs(self):
        """Test workflow defines correct inputs."""
        workflow = CriticalReviewWorkflow()
        inputs = {inp.name: inp for inp in workflow.metadata.inputs}

        assert "documents" in inputs
        assert inputs["documents"].required is True
        assert inputs["documents"].type == "string_list"

        assert "agents" in inputs
        assert inputs["agents"].required is True
        assert inputs["agents"].type == "agent_spec_list"

        assert "output_dir" in inputs
        assert inputs["output_dir"].required is False

        assert "review_template" in inputs
        assert inputs["review_template"].required is False

    def test_workflow_capabilities(self):
        """Test workflow has expected capabilities."""
        workflow = CriticalReviewWorkflow()
        assert "document-review" in workflow.metadata.capabilities
        assert "multi-agent" in workflow.metadata.capabilities
        assert "analysis" in workflow.metadata.capabilities


class TestCriticalReviewWorkflowValidation:
    """Test CriticalReviewWorkflow validation."""

    def test_valid_config(self):
        """Test valid configuration passes validation."""
        workflow = CriticalReviewWorkflow()
        result = workflow.validate_config({
            "documents": ["doc1.md", "doc2.md"],
            "agents": ["mock:mock"]
        })
        assert result.valid is True
        assert len(result.errors) == 0

    def test_valid_config_with_content(self):
        """Test valid configuration with document content."""
        workflow = CriticalReviewWorkflow()
        result = workflow.validate_config({
            "documents": ["# Design Document\nContent here"],
            "agents": ["mock:mock", "mock:mock2"]
        })
        assert result.valid is True

    def test_missing_documents(self):
        """Test validation fails when documents are missing."""
        workflow = CriticalReviewWorkflow()
        result = workflow.validate_config({
            "agents": ["mock:mock"]
        })
        assert result.valid is False
        assert "document" in str(result.errors).lower()

    def test_empty_documents(self):
        """Test validation fails when documents list is empty."""
        workflow = CriticalReviewWorkflow()
        result = workflow.validate_config({
            "documents": [],
            "agents": ["mock:mock"]
        })
        assert result.valid is False

    def test_missing_agents(self):
        """Test validation fails when agents are missing."""
        workflow = CriticalReviewWorkflow()
        result = workflow.validate_config({
            "documents": ["doc1.md"]
        })
        assert result.valid is False
        assert "agent" in str(result.errors).lower()

    def test_empty_agents(self):
        """Test validation fails when agents list is empty."""
        workflow = CriticalReviewWorkflow()
        result = workflow.validate_config({
            "documents": ["doc1.md"],
            "agents": []
        })
        assert result.valid is False

    def test_custom_template_without_placeholder(self):
        """Test validation fails for template without placeholder."""
        workflow = CriticalReviewWorkflow()
        result = workflow.validate_config({
            "documents": ["doc1.md"],
            "agents": ["mock:mock"],
            "review_template": "Review this document please."
        })
        assert result.valid is False
        assert "placeholder" in str(result.errors).lower()

    def test_custom_template_with_placeholder(self):
        """Test validation passes for template with placeholder."""
        workflow = CriticalReviewWorkflow()
        result = workflow.validate_config({
            "documents": ["doc1.md"],
            "agents": ["mock:mock"],
            "review_template": "Review this: {document_content}"
        })
        assert result.valid is True


class TestCriticalReviewWorkflowExecution:
    """Test CriticalReviewWorkflow execution."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent for testing."""
        agent = MagicMock()
        agent.name = "test-agent"
        agent.model = "test-model"
        agent.generate.return_value = (
            "## 1. What is Good\nWell structured.\n## 2. What is Bad\nNeeds more detail.",
            150,
            MagicMock(input_tokens=100, output_tokens=50, cost=0.01)
        )
        return agent

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def sample_doc(self, temp_dir):
        """Create a sample document file."""
        doc_path = temp_dir / "sample_design.md"
        doc_path.write_text("# Sample Design\nThis is a sample design document.")
        return doc_path

    @patch("startd8.workflows.builtin.critical_review_workflow.resolve_agents")
    def test_successful_execution_with_file(
        self, mock_resolve, mock_agent, temp_dir, sample_doc
    ):
        """Test successful workflow execution with a file."""
        mock_resolve.return_value = [mock_agent]

        workflow = CriticalReviewWorkflow()
        result = workflow.run(config={
            "documents": [str(sample_doc)],
            "agents": ["mock:mock"],
            "output_dir": str(temp_dir / "reviews")
        })

        assert result.success is True
        assert result.workflow_id == "critical-review"
        assert result.error is None
        assert result.output["successful"] == 1
        assert result.output["failed"] == 0

    @patch("startd8.workflows.builtin.critical_review_workflow.resolve_agents")
    def test_successful_execution_with_content(
        self, mock_resolve, mock_agent, temp_dir
    ):
        """Test successful workflow execution with document content."""
        mock_resolve.return_value = [mock_agent]

        workflow = CriticalReviewWorkflow()
        result = workflow.run(config={
            "documents": ["# Design\nContent here"],
            "agents": ["mock:mock"],
            "output_dir": str(temp_dir / "reviews")
        })

        assert result.success is True
        assert result.output["successful"] == 1

    @patch("startd8.workflows.builtin.critical_review_workflow.resolve_agents")
    def test_execution_with_multiple_agents(
        self, mock_resolve, temp_dir, sample_doc
    ):
        """Test execution with multiple agents reviewing same document."""
        agents = []
        for name in ["agent1", "agent2", "agent3"]:
            agent = MagicMock()
            agent.name = name
            agent.model = "test-model"
            agent.generate.return_value = (
                f"Review from {name}",
                100,
                MagicMock(input_tokens=50, output_tokens=25, cost=0.005)
            )
            agents.append(agent)

        mock_resolve.return_value = agents

        workflow = CriticalReviewWorkflow()
        result = workflow.run(config={
            "documents": [str(sample_doc)],
            "agents": ["mock:mock"] * 3,
            "output_dir": str(temp_dir / "reviews")
        })

        assert result.success is True
        assert result.output["successful"] == 3
        assert result.metrics.step_count == 3

    @patch("startd8.workflows.builtin.critical_review_workflow.resolve_agents")
    def test_execution_with_multiple_documents(
        self, mock_resolve, mock_agent, temp_dir
    ):
        """Test execution with multiple documents."""
        mock_resolve.return_value = [mock_agent]

        # Create multiple docs
        docs = []
        for i in range(3):
            doc_path = temp_dir / f"design_{i}.md"
            doc_path.write_text(f"# Design {i}\nContent for document {i}")
            docs.append(str(doc_path))

        workflow = CriticalReviewWorkflow()
        result = workflow.run(config={
            "documents": docs,
            "agents": ["mock:mock"],
            "output_dir": str(temp_dir / "reviews")
        })

        assert result.success is True
        assert result.output["successful"] == 3
        assert result.metadata["documents_count"] == 3

    @patch("startd8.workflows.builtin.critical_review_workflow.resolve_agents")
    def test_execution_creates_output_files(
        self, mock_resolve, mock_agent, temp_dir, sample_doc
    ):
        """Test execution creates output review files."""
        mock_resolve.return_value = [mock_agent]

        output_dir = temp_dir / "reviews"
        workflow = CriticalReviewWorkflow()
        result = workflow.run(config={
            "documents": [str(sample_doc)],
            "agents": ["mock:mock"],
            "output_dir": str(output_dir)
        })

        assert result.success is True
        assert output_dir.exists()

        # Check review file was created
        review_files = list(output_dir.glob("*.md"))
        assert len(review_files) == 1
        assert "sample_design" in review_files[0].name
        assert "test-agent" in review_files[0].name

    @patch("startd8.workflows.builtin.critical_review_workflow.resolve_agents")
    def test_execution_tracks_metrics(
        self, mock_resolve, mock_agent, temp_dir, sample_doc
    ):
        """Test execution tracks metrics correctly."""
        mock_resolve.return_value = [mock_agent]

        workflow = CriticalReviewWorkflow()
        result = workflow.run(config={
            "documents": [str(sample_doc)],
            "agents": ["mock:mock"],
            "output_dir": str(temp_dir / "reviews")
        })

        assert result.metrics is not None
        assert result.metrics.step_count == 1
        assert result.metrics.total_time_ms > 0
        assert result.metrics.input_tokens > 0
        assert result.metrics.output_tokens > 0
        assert result.metrics.total_cost > 0

    @patch("startd8.workflows.builtin.critical_review_workflow.resolve_agents")
    def test_execution_handles_agent_error(
        self, mock_resolve, temp_dir, sample_doc
    ):
        """Test execution handles agent errors gracefully."""
        failing_agent = MagicMock()
        failing_agent.name = "failing-agent"
        failing_agent.model = "test-model"
        failing_agent.generate.side_effect = RuntimeError("API Error")

        mock_resolve.return_value = [failing_agent]

        workflow = CriticalReviewWorkflow()
        result = workflow.run(config={
            "documents": [str(sample_doc)],
            "agents": ["mock:mock"],
            "output_dir": str(temp_dir / "reviews")
        })

        # Should still complete but with failed reviews
        assert result.success is False
        assert result.output["failed"] == 1
        assert result.output["successful"] == 0

    @patch("startd8.workflows.builtin.critical_review_workflow.resolve_agents")
    def test_execution_partial_success(
        self, mock_resolve, temp_dir
    ):
        """Test execution with partial success (some reviews fail)."""
        good_agent = MagicMock()
        good_agent.name = "good-agent"
        good_agent.model = "test-model"
        good_agent.generate.return_value = (
            "Good review",
            100,
            MagicMock(input_tokens=50, output_tokens=25, cost=0.005)
        )

        bad_agent = MagicMock()
        bad_agent.name = "bad-agent"
        bad_agent.model = "test-model"
        bad_agent.generate.side_effect = RuntimeError("Failed")

        mock_resolve.return_value = [good_agent, bad_agent]

        doc_path = temp_dir / "test.md"
        doc_path.write_text("# Test\nContent")

        workflow = CriticalReviewWorkflow()
        result = workflow.run(config={
            "documents": [str(doc_path)],
            "agents": ["mock:mock", "mock:mock2"],
            "output_dir": str(temp_dir / "reviews")
        })

        # Partial success - at least one review succeeded
        assert result.success is True
        assert result.output["successful"] == 1
        assert result.output["failed"] == 1

    @patch("startd8.workflows.builtin.critical_review_workflow.resolve_agents")
    def test_execution_with_custom_template(
        self, mock_resolve, mock_agent, temp_dir, sample_doc
    ):
        """Test execution with custom review template."""
        mock_resolve.return_value = [mock_agent]

        custom_template = "Custom review for: {document_content}"

        workflow = CriticalReviewWorkflow()
        result = workflow.run(config={
            "documents": [str(sample_doc)],
            "agents": ["mock:mock"],
            "output_dir": str(temp_dir / "reviews"),
            "review_template": custom_template
        })

        assert result.success is True
        # Verify custom template was used
        mock_agent.generate.assert_called_once()
        call_args = mock_agent.generate.call_args[0][0]
        assert "Custom review for:" in call_args

    @patch("startd8.workflows.builtin.critical_review_workflow.resolve_agents")
    def test_execution_reports_progress(
        self, mock_resolve, mock_agent, temp_dir, sample_doc
    ):
        """Test execution calls progress callback."""
        mock_resolve.return_value = [mock_agent]

        progress_calls = []

        def track_progress(current: int, total: int, message: str):
            progress_calls.append((current, total, message))

        workflow = CriticalReviewWorkflow()
        result = workflow.run(
            config={
                "documents": [str(sample_doc)],
                "agents": ["mock:mock"],
                "output_dir": str(temp_dir / "reviews")
            },
            on_progress=track_progress
        )

        assert result.success is True
        # Should have start progress + per-review progress
        assert len(progress_calls) >= 2

    @patch("startd8.workflows.builtin.critical_review_workflow.resolve_agents")
    def test_execution_file_versioning(
        self, mock_resolve, mock_agent, temp_dir, sample_doc
    ):
        """Test execution handles file versioning when file exists."""
        mock_resolve.return_value = [mock_agent]

        output_dir = temp_dir / "reviews"
        output_dir.mkdir()

        # Pre-create a review file
        existing_file = output_dir / "sample_design_review_test-agent.md"
        existing_file.write_text("Existing content")

        workflow = CriticalReviewWorkflow()
        result = workflow.run(config={
            "documents": [str(sample_doc)],
            "agents": ["mock:mock"],
            "output_dir": str(output_dir)
        })

        assert result.success is True

        # Check versioned file was created
        review_files = list(output_dir.glob("sample_design_review_test-agent*.md"))
        assert len(review_files) == 2  # Original + versioned

    @patch("startd8.workflows.builtin.critical_review_workflow.resolve_agents")
    def test_execution_no_agents_error(self, mock_resolve, temp_dir):
        """Test execution fails gracefully with no agents."""
        mock_resolve.return_value = []

        workflow = CriticalReviewWorkflow()
        result = workflow.run(config={
            "documents": ["# Content"],
            "agents": [],
            "output_dir": str(temp_dir / "reviews")
        })

        assert result.success is False
        assert "agent" in result.error.lower()


class TestCriticalReviewWorkflowRegistration:
    """Test CriticalReviewWorkflow registration."""

    def test_workflow_can_be_imported(self):
        """Test workflow can be imported from builtin package."""
        from startd8.workflows.builtin import CriticalReviewWorkflow
        assert CriticalReviewWorkflow is not None

    def test_workflow_conforms_to_protocol(self):
        """Test workflow conforms to WorkflowBase protocol."""
        from startd8.workflows import WorkflowBase
        workflow = CriticalReviewWorkflow()
        assert isinstance(workflow, WorkflowBase)


class TestReviewPromptTemplate:
    """Test the default review prompt template."""

    def test_template_has_placeholder(self):
        """Test default template has document_content placeholder."""
        assert "{document_content}" in REVIEW_PROMPT_TEMPLATE

    def test_template_has_review_sections(self):
        """Test default template includes all review sections."""
        assert "What is Good" in REVIEW_PROMPT_TEMPLATE
        assert "What is Bad" in REVIEW_PROMPT_TEMPLATE
        assert "What Needs More or Less" in REVIEW_PROMPT_TEMPLATE
        assert "Suggestions for Improvement" in REVIEW_PROMPT_TEMPLATE
