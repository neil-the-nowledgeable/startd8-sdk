"""
StartD8 Workflows - Agent-accessible workflow system.

This module provides a unified interface for discovering, invoking, and
orchestrating workflows. Workflows can be accessed:
- Programmatically via Python API
- Via CLI: `startd8 workflow run <id>`
- Via MCP for external AI agents
- Via filesystem for token-efficient agent discovery

Quick Start:
    from startd8.workflows import WorkflowRegistry

    # Discover all workflows
    WorkflowRegistry.discover()

    # List available workflows
    for workflow_id in WorkflowRegistry.list_workflows():
        print(workflow_id)

    # Run a workflow
    result = WorkflowRegistry.run_workflow(
        "pipeline",
        config={"initial_input": "Write a function..."},
        agents=[my_agent]
    )

Filesystem-based Discovery (for agents):
    # Export workflows to filesystem for agent discovery
    result = WorkflowRegistry.export_to_filesystem("./workflows")

    # Agent discovers workflows from lightweight index
    workflows = WorkflowRegistry.discover_from_filesystem("./workflows")

    # Agent loads full schema only when needed
    schema = WorkflowRegistry.get_workflow_from_filesystem("pipeline")

Creating Custom Workflows:
    from startd8.workflows import WorkflowBase, WorkflowMetadata, WorkflowResult

    class MyWorkflow(WorkflowBase):
        @property
        def metadata(self) -> WorkflowMetadata:
            return WorkflowMetadata(
                workflow_id="my-workflow",
                name="My Custom Workflow",
                description="Does something useful",
            )

        def _execute(self, config, agents, on_progress):
            # Implementation
            return WorkflowResult(...)
"""

from .models import (
    WorkflowStatus,
    AgentCount,
    WorkflowInput,
    WorkflowMetadata,
    WorkflowMetrics,
    StepResult,
    WorkflowResult,
    ValidationResult,
)
from .base import (
    Workflow,
    AsyncWorkflow,
    WorkflowBase,
    ProgressCallback,
)
from .registry import WorkflowRegistry
from .filesystem import WorkflowFilesystem, export_registry_to_filesystem

__all__ = [
    # Models
    "WorkflowStatus",
    "AgentCount",
    "WorkflowInput",
    "WorkflowMetadata",
    "WorkflowMetrics",
    "StepResult",
    "WorkflowResult",
    "ValidationResult",
    # Base classes
    "Workflow",
    "AsyncWorkflow",
    "WorkflowBase",
    "ProgressCallback",
    # Registry
    "WorkflowRegistry",
    # Filesystem discovery
    "WorkflowFilesystem",
    "export_registry_to_filesystem",
]
