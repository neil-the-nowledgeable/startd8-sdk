"""
Tests for filesystem-based workflow discovery.
"""

import pytest
import tempfile
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

from startd8.workflows import (
    WorkflowRegistry,
    WorkflowBase,
    WorkflowMetadata,
    WorkflowResult,
    WorkflowMetrics,
    WorkflowInput,
    AgentCount,
    WorkflowFilesystem,
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
            description="A mock workflow for testing filesystem export",
            version="1.0.0",
            capabilities=["testing", "mock", "filesystem"],
            tags=["test", "mock"],
            requires_agents=False,
            agent_count=AgentCount.NONE,
            min_agents=0,
            inputs=[
                WorkflowInput(
                    name="message",
                    type="string",
                    required=True,
                    description="The message to process"
                ),
                WorkflowInput(
                    name="count",
                    type="number",
                    required=False,
                    default=1,
                    description="Number of times to process"
                ),
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


class TestWorkflowFilesystem:
    """Test WorkflowFilesystem class."""

    def test_export_single_workflow(self):
        """Test exporting a single workflow to YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fs = WorkflowFilesystem(tmpdir)
            workflow = MockWorkflow()

            path = fs.export_workflow(workflow.metadata)

            assert path.exists()
            assert path.name == "mock-workflow.yaml"

            # Verify content
            import yaml
            with open(path) as f:
                data = yaml.safe_load(f)

            assert data['workflow_id'] == 'mock-workflow'
            assert data['name'] == 'Mock Workflow'
            assert 'input_schema' in data
            assert 'invocation' in data

    def test_export_all_creates_index(self):
        """Test exporting multiple workflows creates index file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fs = WorkflowFilesystem(tmpdir)
            workflows = [
                MockWorkflow("workflow-1").metadata,
                MockWorkflow("workflow-2").metadata,
            ]

            exported = fs.export_all(workflows)

            assert '_index' in exported
            assert exported['_index'].exists()
            assert 'workflow-1' in exported
            assert 'workflow-2' in exported

    def test_index_file_is_lightweight(self):
        """Test index file contains minimal info."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fs = WorkflowFilesystem(tmpdir)
            workflow = MockWorkflow()
            workflow._workflow_id = "test"
            # Create a long description
            meta = workflow.metadata
            meta.description = "A" * 200  # Long description

            fs.export_all([meta])

            import yaml
            index_path = Path(tmpdir) / "_index.yaml"
            with open(index_path) as f:
                data = yaml.safe_load(f)

            # Index entry should have truncated description
            entry = data['workflows'][0]
            assert len(entry['description']) <= 103  # 100 + "..."
            # Should only have first 3 capabilities
            assert len(entry.get('capabilities', [])) <= 3

    def test_list_workflows_from_index(self):
        """Test listing workflows from index file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fs = WorkflowFilesystem(tmpdir)
            workflows = [
                MockWorkflow("workflow-1").metadata,
                MockWorkflow("workflow-2").metadata,
            ]
            fs.export_all(workflows)

            # List from index
            listed = fs.list_workflows()

            assert len(listed) == 2
            ids = [w['workflow_id'] for w in listed]
            assert 'workflow-1' in ids
            assert 'workflow-2' in ids

    def test_get_workflow_definition(self):
        """Test loading full workflow definition."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fs = WorkflowFilesystem(tmpdir)
            workflow = MockWorkflow()
            fs.export_workflow(workflow.metadata)

            definition = fs.get_workflow_definition("mock-workflow")

            assert definition is not None
            assert definition['workflow_id'] == 'mock-workflow'
            assert 'input_schema' in definition
            assert definition['input_schema']['type'] == 'object'
            assert 'message' in definition['input_schema']['properties']

    def test_get_workflow_definition_not_found(self):
        """Test loading non-existent workflow returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fs = WorkflowFilesystem(tmpdir)

            definition = fs.get_workflow_definition("non-existent")

            assert definition is None

    def test_import_workflow_metadata(self):
        """Test importing workflow metadata from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fs = WorkflowFilesystem(tmpdir)
            original = MockWorkflow().metadata
            fs.export_workflow(original)

            imported = fs.import_workflow("mock-workflow")

            assert imported is not None
            assert imported.workflow_id == original.workflow_id
            assert imported.name == original.name
            assert imported.description == original.description
            assert len(imported.inputs) == len(original.inputs)

    def test_workflow_exists(self):
        """Test checking if workflow file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fs = WorkflowFilesystem(tmpdir)
            fs.export_workflow(MockWorkflow().metadata)

            assert fs.workflow_exists("mock-workflow")
            assert not fs.workflow_exists("non-existent")


class TestWorkflowRegistryFilesystem:
    """Test WorkflowRegistry filesystem methods."""

    def setup_method(self):
        """Clear registry before each test."""
        WorkflowRegistry.clear()

    def teardown_method(self):
        """Clean up after each test."""
        WorkflowRegistry.clear()

    def test_export_to_filesystem(self):
        """Test exporting registry to filesystem."""
        WorkflowRegistry.register(MockWorkflow("test-workflow"))

        with tempfile.TemporaryDirectory() as tmpdir:
            result = WorkflowRegistry.export_to_filesystem(tmpdir)

            assert 'files' in result
            assert 'index' in result
            assert 'directory' in result
            assert 'test-workflow' in result['files']
            assert Path(result['index']).exists()

    def test_discover_from_filesystem(self):
        """Test discovering workflows from filesystem."""
        WorkflowRegistry.register(MockWorkflow("fs-workflow"))

        with tempfile.TemporaryDirectory() as tmpdir:
            # Export first
            WorkflowRegistry.export_to_filesystem(tmpdir)

            # Clear and discover from filesystem
            WorkflowRegistry.clear()
            workflows = WorkflowRegistry.discover_from_filesystem(tmpdir)

            assert len(workflows) >= 1
            ids = [w['workflow_id'] for w in workflows]
            assert 'fs-workflow' in ids

    def test_get_workflow_from_filesystem(self):
        """Test getting workflow definition from filesystem."""
        WorkflowRegistry.register(MockWorkflow("fs-test"))

        with tempfile.TemporaryDirectory() as tmpdir:
            WorkflowRegistry.export_to_filesystem(tmpdir)

            definition = WorkflowRegistry.get_workflow_from_filesystem(
                "fs-test",
                directory=tmpdir
            )

            assert definition is not None
            assert definition['workflow_id'] == 'fs-test'
            assert 'input_schema' in definition
            assert 'invocation' in definition


class TestFilesystemInvocationExample:
    """Test that exported files contain valid invocation examples."""

    def test_invocation_example_in_export(self):
        """Test exported YAML contains MCP invocation example."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fs = WorkflowFilesystem(tmpdir)
            workflow = MockWorkflow()
            fs.export_workflow(workflow.metadata)

            definition = fs.get_workflow_definition("mock-workflow")

            assert 'invocation' in definition
            assert definition['invocation']['mcp_tool'] == 'startd8_workflow'
            assert definition['invocation']['action'] == 'run'
            assert 'example' in definition['invocation']
            assert definition['invocation']['example']['workflow_id'] == 'mock-workflow'


class TestTokenEfficiency:
    """Test that filesystem approach is token-efficient."""

    def test_index_is_smaller_than_full_schemas(self):
        """Test index file is significantly smaller than full schemas."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fs = WorkflowFilesystem(tmpdir)

            # Create multiple workflows with substantial metadata
            workflows = []
            for i in range(5):
                wf = MockWorkflow(f"workflow-{i}")
                meta = wf.metadata
                # Add long description
                meta.description = f"This is workflow {i}. " * 20
                workflows.append(meta)

            fs.export_all(workflows)

            # Calculate sizes
            index_size = os.path.getsize(Path(tmpdir) / "_index.yaml")
            total_schema_size = sum(
                os.path.getsize(Path(tmpdir) / f"workflow-{i}.yaml")
                for i in range(5)
            )

            # Index should be significantly smaller
            assert index_size < total_schema_size
            # Index should be less than 50% of total
            assert index_size < total_schema_size * 0.5
