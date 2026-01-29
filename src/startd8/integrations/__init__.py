"""
StartD8 SDK Integration Module.

Provides integrations with external systems like ContextCore for
project tracking and observability.

Integrations:
    - ContextCore: Task tracking as OpenTelemetry spans
    - AgentInsightBridge: Emit and query agent decisions/lessons/questions

Usage Examples:

    # Run a single task with adapter pattern
    from startd8.integrations import ContextCoreWorkflowAdapter, ContextCoreConfig
    from startd8.workflows.builtin import LeadContractorWorkflow

    adapter = ContextCoreWorkflowAdapter(
        workflow=LeadContractorWorkflow(),
        config=ContextCoreConfig(project_id="my-project"),
    )
    result = adapter.run_as_task(
        task_id="SDK-102",
        task_title="Implement feature",
        workflow_config={"task_description": "Implement X using Y"},
    )

    # Run all pending tasks from a ContextCore project
    from startd8.integrations import run_contextcore_project

    results = run_contextcore_project(
        project_id="my-project",
        sprint_id="sprint-3",
    )

    # Load tasks from ContextCore state files
    from startd8.integrations import ContextCoreTaskSource

    source = ContextCoreTaskSource(project_id="my-project")
    tasks = source.get_pending_tasks()  # Gets tasks with status 'todo' or 'backlog'

    # Emit and query agent insights
    from startd8.integrations import AgentInsightBridge

    bridge = AgentInsightBridge(project_id="my-project", agent_id="claude")
    bridge.emit_decision("Selected Redis for caching", confidence=0.9)
    bridge.emit_lesson("Always validate config before deployment", category="ops")

    # Query past decisions
    decisions = bridge.query_decisions(time_range="7d", confidence_min=0.8)
"""

from .contextcore import (
    ContextCoreConfig,
    WorkflowTaskSpec,
    ContextCoreWorkflowAdapter,
    ContextCoreTaskRunner,
    ContextCoreTaskSource,
    load_tasks_from_yaml,
    run_contextcore_project,
    # Insight bridge
    AgentInsightBridge,
    InsightRecord,
)

__all__ = [
    # Workflow integration
    "ContextCoreConfig",
    "WorkflowTaskSpec",
    "ContextCoreWorkflowAdapter",
    "ContextCoreTaskRunner",
    "ContextCoreTaskSource",
    "load_tasks_from_yaml",
    "run_contextcore_project",
    # Insight bridge
    "AgentInsightBridge",
    "InsightRecord",
]
