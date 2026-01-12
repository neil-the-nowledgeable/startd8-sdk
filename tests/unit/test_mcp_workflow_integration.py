"""
Tests for MCP Gateway workflow integration.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from typing import Dict, Any, List, Optional

from startd8.mcp import (
    MCPGateway,
    MCPGatewayConfig,
    WorkflowExecutionResult,
)
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


class TestWorkflowExecutionResult:
    """Test WorkflowExecutionResult type."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = WorkflowExecutionResult(
            workflow_id="test",
            success=True,
            output="test output",
            execution_time_ms=100,
            total_cost=0.01,
            input_tokens=50,
            output_tokens=100,
        )

        data = result.to_dict()
        assert data["workflow_id"] == "test"
        assert data["success"] is True
        assert data["output"] == "test output"
        assert data["execution_time_ms"] == 100
        assert data["total_cost"] == 0.01
        assert data["token_usage"]["input"] == 50
        assert data["token_usage"]["output"] == 100
        assert data["token_usage"]["total"] == 150

    def test_from_workflow_result(self):
        """Test creation from WorkflowResult."""
        workflow_result = WorkflowResult(
            workflow_id="test",
            success=True,
            output="test output",
            metrics=WorkflowMetrics(
                total_time_ms=200,
                total_cost=0.02,
                input_tokens=100,
                output_tokens=200,
            ),
        )

        result = WorkflowExecutionResult.from_workflow_result(workflow_result)
        assert result.workflow_id == "test"
        assert result.success is True
        assert result.output == "test output"
        assert result.execution_time_ms == 200
        assert result.total_cost == 0.02
        assert result.input_tokens == 100
        assert result.output_tokens == 200


class TestMCPGatewayWorkflows:
    """Test MCPGateway workflow methods."""

    def setup_method(self):
        """Clear registry before each test."""
        WorkflowRegistry.clear()

    def teardown_method(self):
        """Clean up after each test."""
        WorkflowRegistry.clear()

    @pytest.mark.asyncio
    async def test_list_workflows(self):
        """Test listing workflows via gateway."""
        # Register a mock workflow
        WorkflowRegistry.register(MockWorkflow())

        # Create gateway (won't initialize fully without API key)
        gateway = MCPGateway(MCPGatewayConfig())

        # List workflows (doesn't require full initialization)
        workflows = await gateway.list_workflows()

        assert len(workflows) >= 1
        mock_wf = next(
            (w for w in workflows if w["workflow_id"] == "mock-workflow"),
            None
        )
        assert mock_wf is not None
        assert mock_wf["name"] == "Mock Workflow"
        assert mock_wf["requires_agents"] is False

    @pytest.mark.asyncio
    async def test_describe_workflow(self):
        """Test describing a workflow via gateway."""
        WorkflowRegistry.register(MockWorkflow())
        gateway = MCPGateway(MCPGatewayConfig())

        info = await gateway.describe_workflow("mock-workflow")

        assert info is not None
        assert info["workflow_id"] == "mock-workflow"
        assert info["name"] == "Mock Workflow"
        assert "input_schema" in info

    @pytest.mark.asyncio
    async def test_describe_workflow_not_found(self):
        """Test describing non-existent workflow."""
        gateway = MCPGateway(MCPGatewayConfig())

        info = await gateway.describe_workflow("non-existent")
        assert info is None

    @pytest.mark.asyncio
    async def test_execute_workflow(self):
        """Test executing a workflow via gateway."""
        WorkflowRegistry.register(MockWorkflow())
        gateway = MCPGateway(MCPGatewayConfig())

        # Mock rate limiter to not block
        gateway._global_rate_limiter.acquire = AsyncMock()

        result = await gateway.execute_workflow(
            workflow_id="mock-workflow",
            config={"message": "test input"}
        )

        assert result.success is True
        assert "Processed: test input" in result.output
        assert result.workflow_id == "mock-workflow"

    @pytest.mark.asyncio
    async def test_execute_workflow_validation_error(self):
        """Test workflow execution with invalid config."""
        WorkflowRegistry.register(MockWorkflow())
        gateway = MCPGateway(MCPGatewayConfig())
        gateway._global_rate_limiter.acquire = AsyncMock()

        result = await gateway.execute_workflow(
            workflow_id="mock-workflow",
            config={}  # Missing required 'message'
        )

        assert result.success is False
        assert "Validation failed" in result.error

    @pytest.mark.asyncio
    async def test_execute_workflow_not_found(self):
        """Test executing non-existent workflow."""
        gateway = MCPGateway(MCPGatewayConfig())
        gateway._global_rate_limiter.acquire = AsyncMock()

        with pytest.raises(Exception) as exc_info:
            await gateway.execute_workflow(
                workflow_id="non-existent",
                config={}
            )
        assert "not found" in str(exc_info.value).lower()

    def test_get_workflow_tool_schema(self):
        """Test MCP tool schema generation."""
        gateway = MCPGateway(MCPGatewayConfig())
        schema = gateway.get_workflow_tool_schema()

        assert schema["name"] == "startd8_workflow"
        assert "description" in schema
        assert schema["input_schema"]["type"] == "object"
        assert "action" in schema["input_schema"]["properties"]
        assert "workflow_id" in schema["input_schema"]["properties"]
        assert "config" in schema["input_schema"]["properties"]
        assert schema["input_schema"]["properties"]["action"]["enum"] == ["list", "describe", "run"]


class TestMCPGatewayHandleWorkflowTool:
    """Test the handle_workflow_tool method."""

    def setup_method(self):
        """Clear registry before each test."""
        WorkflowRegistry.clear()

    def teardown_method(self):
        """Clean up after each test."""
        WorkflowRegistry.clear()

    @pytest.mark.asyncio
    async def test_handle_list_action(self):
        """Test 'list' action."""
        WorkflowRegistry.register(MockWorkflow())
        gateway = MCPGateway(MCPGatewayConfig())

        response = await gateway.handle_workflow_tool(action="list")

        assert "workflows" in response
        assert len(response["workflows"]) >= 1

    @pytest.mark.asyncio
    async def test_handle_describe_action(self):
        """Test 'describe' action."""
        WorkflowRegistry.register(MockWorkflow())
        gateway = MCPGateway(MCPGatewayConfig())

        response = await gateway.handle_workflow_tool(
            action="describe",
            workflow_id="mock-workflow"
        )

        assert "workflow" in response
        assert response["workflow"]["workflow_id"] == "mock-workflow"

    @pytest.mark.asyncio
    async def test_handle_describe_missing_id(self):
        """Test 'describe' action without workflow_id."""
        gateway = MCPGateway(MCPGatewayConfig())

        response = await gateway.handle_workflow_tool(action="describe")

        assert "error" in response
        assert "workflow_id required" in response["error"]

    @pytest.mark.asyncio
    async def test_handle_run_action(self):
        """Test 'run' action."""
        WorkflowRegistry.register(MockWorkflow())
        gateway = MCPGateway(MCPGatewayConfig())
        gateway._global_rate_limiter.acquire = AsyncMock()

        response = await gateway.handle_workflow_tool(
            action="run",
            workflow_id="mock-workflow",
            config={"message": "hello from MCP"}
        )

        assert "result" in response
        assert response["result"]["success"] is True
        assert "Processed: hello from MCP" in response["result"]["output"]

    @pytest.mark.asyncio
    async def test_handle_run_missing_id(self):
        """Test 'run' action without workflow_id."""
        gateway = MCPGateway(MCPGatewayConfig())

        response = await gateway.handle_workflow_tool(
            action="run",
            config={"message": "test"}
        )

        assert "error" in response
        assert "workflow_id required" in response["error"]

    @pytest.mark.asyncio
    async def test_handle_run_missing_config(self):
        """Test 'run' action without config."""
        gateway = MCPGateway(MCPGatewayConfig())

        response = await gateway.handle_workflow_tool(
            action="run",
            workflow_id="mock-workflow"
        )

        assert "error" in response
        assert "config required" in response["error"]

    @pytest.mark.asyncio
    async def test_handle_unknown_action(self):
        """Test unknown action."""
        gateway = MCPGateway(MCPGatewayConfig())

        response = await gateway.handle_workflow_tool(action="unknown")

        assert "error" in response
        assert "Unknown action" in response["error"]
