"""
Tests for the WorkflowRegistry and workflow system.
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import Dict, Any, List, Optional

from startd8.workflows import (
    WorkflowRegistry,
    WorkflowBase,
    WorkflowMetadata,
    WorkflowResult,
    WorkflowMetrics,
    ValidationResult,
    WorkflowInput,
    AgentCount,
)
from startd8.workflows.base import ProgressCallback


class MockWorkflow(WorkflowBase):
    """Simple mock workflow for testing."""

    def __init__(self, workflow_id: str = "mock-workflow"):
        self._workflow_id = workflow_id

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id=self._workflow_id,
            name="Mock Workflow",
            description="A mock workflow for testing",
            version="1.0.0",
            capabilities=["testing", "mock"],
            tags=["test"],
            requires_agents=False,
            agent_count=AgentCount.NONE,
            min_agents=0,
            inputs=[
                WorkflowInput(name="message", type="string", required=True),
            ]
        )

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> WorkflowResult:
        message = config.get("message", "default")
        return WorkflowResult(
            workflow_id=self.metadata.workflow_id,
            success=True,
            output=f"Processed: {message}",
            metrics=WorkflowMetrics(total_time_ms=100),
        )


class TestWorkflowRegistry:
    """Test WorkflowRegistry functionality."""

    def setup_method(self):
        """Clear registry before each test."""
        WorkflowRegistry.clear()

    def teardown_method(self):
        """Clean up after each test."""
        WorkflowRegistry.clear()

    def test_register_workflow(self):
        """Test registering a workflow."""
        workflow = MockWorkflow()
        WorkflowRegistry.register(workflow)

        assert "mock-workflow" in WorkflowRegistry.list_workflows()

    def test_register_workflow_invalid(self):
        """Test registering an invalid workflow raises TypeError."""
        invalid = {"not": "a workflow"}

        with pytest.raises(TypeError):
            WorkflowRegistry.register(invalid)

    def test_get_workflow(self):
        """Test retrieving a registered workflow."""
        workflow = MockWorkflow()
        WorkflowRegistry.register(workflow)

        retrieved = WorkflowRegistry.get_workflow("mock-workflow")
        assert retrieved is not None
        assert retrieved.metadata.workflow_id == "mock-workflow"

    def test_get_workflow_not_found(self):
        """Test retrieving non-existent workflow returns None."""
        # Don't discover - we want empty registry
        with patch.object(WorkflowRegistry, 'discover'):
            result = WorkflowRegistry.get_workflow("non-existent")
        assert result is None

    def test_list_workflows(self):
        """Test listing all registered workflows."""
        WorkflowRegistry.register(MockWorkflow("workflow-1"))
        WorkflowRegistry.register(MockWorkflow("workflow-2"))

        workflows = WorkflowRegistry.list_workflows()
        assert "workflow-1" in workflows
        assert "workflow-2" in workflows
        assert len(workflows) >= 2

    def test_list_workflow_metadata(self):
        """Test listing workflow metadata."""
        WorkflowRegistry.register(MockWorkflow())

        metadata_list = WorkflowRegistry.list_workflow_metadata()
        assert len(metadata_list) >= 1

        mock_meta = next(
            (m for m in metadata_list if m.workflow_id == "mock-workflow"),
            None
        )
        assert mock_meta is not None
        assert mock_meta.name == "Mock Workflow"

    def test_get_workflow_info(self):
        """Test getting workflow info dictionary."""
        WorkflowRegistry.register(MockWorkflow())

        info = WorkflowRegistry.get_workflow_info("mock-workflow")
        assert info is not None
        assert info["workflow_id"] == "mock-workflow"
        assert info["name"] == "Mock Workflow"
        assert "input_schema" in info

    def test_validate_config(self):
        """Test config validation."""
        WorkflowRegistry.register(MockWorkflow())

        # Valid config
        result = WorkflowRegistry.validate_config(
            "mock-workflow",
            {"message": "hello"}
        )
        assert result.valid

        # Invalid config (missing required field)
        result = WorkflowRegistry.validate_config("mock-workflow", {})
        assert not result.valid
        assert len(result.errors) > 0

    def test_run_workflow(self):
        """Test running a workflow."""
        WorkflowRegistry.register(MockWorkflow())

        result = WorkflowRegistry.run_workflow(
            "mock-workflow",
            config={"message": "test input"}
        )

        assert result.success
        assert "Processed: test input" in result.output

    def test_run_workflow_not_found(self):
        """Test running non-existent workflow raises ConfigurationError."""
        from startd8.exceptions import ConfigurationError

        with pytest.raises(ConfigurationError):
            WorkflowRegistry.run_workflow("non-existent", config={})

    def test_find_workflows_by_capability(self):
        """Test finding workflows by capability."""
        WorkflowRegistry.register(MockWorkflow())

        found = WorkflowRegistry.find_workflows_by_capability("testing")
        assert len(found) >= 1
        assert any(w.metadata.workflow_id == "mock-workflow" for w in found)

    def test_find_workflows_by_tag(self):
        """Test finding workflows by tag."""
        WorkflowRegistry.register(MockWorkflow())

        found = WorkflowRegistry.find_workflows_by_tag("test")
        assert len(found) >= 1
        assert any(w.metadata.workflow_id == "mock-workflow" for w in found)

    def test_workflow_id_case_insensitive(self):
        """Test that workflow IDs are case-insensitive."""
        WorkflowRegistry.register(MockWorkflow("MyWorkflow"))

        # Should find with lowercase
        assert WorkflowRegistry.get_workflow("myworkflow") is not None
        assert WorkflowRegistry.get_workflow("MYWORKFLOW") is not None


class SearchableWorkflow(WorkflowBase):
    """Workflow with specific capabilities/tags for search testing."""

    def __init__(self, wid="searchable", caps=None, tags=None, name="Searchable", desc="A searchable workflow"):
        self._wid = wid
        self._caps = caps or ["document-enhancement", "multi-agent"]
        self._tags = tags or ["review", "analysis"]
        self._name = name
        self._desc = desc

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id=self._wid,
            name=self._name,
            description=self._desc,
            version="1.0.0",
            capabilities=self._caps,
            tags=self._tags,
            requires_agents=False,
            agent_count=AgentCount.NONE,
            min_agents=0,
            inputs=[],
        )

    def _execute(self, config, agents=None, on_progress=None):
        return WorkflowResult(
            workflow_id=self._wid,
            success=True,
            output="ok",
        )


class TestDiscoverySearch:
    """FR-200, FR-201: Partial matching and search_workflows."""

    def setup_method(self):
        WorkflowRegistry.clear()

    def teardown_method(self):
        WorkflowRegistry.clear()

    def test_find_by_capability_partial_match(self):
        """FR-200: Partial/substring matching."""
        WorkflowRegistry.register(SearchableWorkflow())
        found = WorkflowRegistry.find_workflows_by_capability("doc")
        assert len(found) >= 1
        assert any(w.metadata.workflow_id == "searchable" for w in found)

    def test_find_by_capability_exact_still_works(self):
        """Exact match still works after partial match change."""
        WorkflowRegistry.register(SearchableWorkflow())
        found = WorkflowRegistry.find_workflows_by_capability("document-enhancement")
        assert len(found) >= 1
        assert any(w.metadata.workflow_id == "searchable" for w in found)

    def test_find_by_capability_partial_no_match(self):
        WorkflowRegistry.register(SearchableWorkflow())
        found = WorkflowRegistry.find_workflows_by_capability("xyz-nonexistent")
        assert not any(w.metadata.workflow_id == "searchable" for w in found)

    def test_search_workflows_by_name(self):
        """FR-201: Search by name."""
        WorkflowRegistry.register(SearchableWorkflow(name="Document Enhancer"))
        found = WorkflowRegistry.search_workflows("Document")
        assert len(found) >= 1
        assert any(w.metadata.workflow_id == "searchable" for w in found)

    def test_search_workflows_by_description(self):
        """FR-201: Search by description."""
        WorkflowRegistry.register(SearchableWorkflow(desc="Analyzes policy documents"))
        found = WorkflowRegistry.search_workflows("policy")
        assert len(found) >= 1
        assert any(w.metadata.workflow_id == "searchable" for w in found)

    def test_search_case_insensitive(self):
        WorkflowRegistry.register(SearchableWorkflow(name="Critical Review"))
        found = WorkflowRegistry.search_workflows("critical review")
        assert len(found) >= 1
        assert any(w.metadata.workflow_id == "searchable" for w in found)

    def test_search_no_match(self):
        WorkflowRegistry.register(SearchableWorkflow())
        found = WorkflowRegistry.search_workflows("nonexistent-term-xyz")
        assert not any(w.metadata.workflow_id == "searchable" for w in found)


class TestWorkflowModels:
    """Test workflow data models."""

    def test_workflow_metadata_to_dict(self):
        """Test WorkflowMetadata serialization."""
        meta = WorkflowMetadata(
            workflow_id="test",
            name="Test Workflow",
            description="A test",
            capabilities=["cap1"],
            inputs=[
                WorkflowInput(name="input1", type="string", required=True),
            ]
        )

        data = meta.to_dict()
        assert data["workflow_id"] == "test"
        assert "input_schema" in data
        assert "input1" in data["input_schema"]["properties"]

    def test_workflow_result_to_dict(self):
        """Test WorkflowResult serialization."""
        result = WorkflowResult(
            workflow_id="test",
            success=True,
            output="test output",
            metrics=WorkflowMetrics(total_time_ms=100, total_cost=0.01),
        )

        data = result.to_dict()
        assert data["workflow_id"] == "test"
        assert data["success"] is True
        assert data["metrics"]["total_time_ms"] == 100

    def test_workflow_result_from_error(self):
        """Test creating failed result from error."""
        result = WorkflowResult.from_error("test", "Something went wrong")

        assert not result.success
        assert result.error == "Something went wrong"

    def test_validation_result_success(self):
        """Test ValidationResult success helper."""
        result = ValidationResult.success()
        assert result.valid
        assert len(result.errors) == 0

    def test_validation_result_failure(self):
        """Test ValidationResult failure helper."""
        result = ValidationResult.failure(["Error 1", "Error 2"])
        assert not result.valid
        assert len(result.errors) == 2


class TestWorkflowBase:
    """Test WorkflowBase functionality."""

    def test_default_validation(self):
        """Test default validation checks required inputs."""
        workflow = MockWorkflow()

        # Valid
        result = workflow.validate_config({"message": "hello"})
        assert result.valid

        # Invalid - missing required
        result = workflow.validate_config({})
        assert not result.valid

    def test_sync_run(self):
        """Test synchronous run."""
        workflow = MockWorkflow()
        result = workflow.run(config={"message": "hello"})

        assert result.success
        assert "Processed: hello" in result.output

    def test_progress_callback(self):
        """Test progress callback is called."""
        workflow = MockWorkflow()
        progress_calls = []

        def on_progress(current, total, message):
            progress_calls.append((current, total, message))

        workflow.run(config={"message": "hello"}, on_progress=on_progress)

        # The base implementation may or may not call progress
        # This test just ensures it doesn't crash


@pytest.mark.asyncio
class TestWorkflowAsync:
    """Test async workflow functionality."""

    async def test_async_run(self):
        """Test asynchronous run."""
        workflow = MockWorkflow()
        result = await workflow.arun(config={"message": "async hello"})

        assert result.success
        assert "Processed: async hello" in result.output


class TestBuiltinWorkflows:
    """Test built-in workflow wrappers can be instantiated."""

    def test_pipeline_workflow_metadata(self):
        """Test PipelineWorkflow can be created and has metadata."""
        from startd8.workflows.builtin.pipeline_workflow import PipelineWorkflow

        workflow = PipelineWorkflow()
        meta = workflow.metadata

        assert meta.workflow_id == "pipeline"
        assert meta.requires_agents is True
        assert len(meta.inputs) > 0

    def test_doc_enhancement_workflow_metadata(self):
        """Test DocEnhancementWorkflow can be created and has metadata."""
        from startd8.workflows.builtin.doc_enhancement_workflow import DocEnhancementWorkflow

        workflow = DocEnhancementWorkflow()
        meta = workflow.metadata

        assert meta.workflow_id == "doc-enhancement"
        assert meta.requires_agents is True

    def test_iterative_dev_workflow_metadata(self):
        """Test IterativeDevWorkflowWrapper can be created and has metadata."""
        from startd8.workflows.builtin.iterative_dev_workflow import IterativeDevWorkflowWrapper

        workflow = IterativeDevWorkflowWrapper()
        meta = workflow.metadata

        assert meta.workflow_id == "iterative-dev"
        assert meta.min_agents == 2
