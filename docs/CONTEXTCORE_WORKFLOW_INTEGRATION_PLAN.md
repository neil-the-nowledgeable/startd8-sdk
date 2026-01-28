# ContextCore + StartD8 SDK Workflow Integration Plan

> **STATUS: IMPLEMENTED (Historical Document)**
>
> This planning document has been **fully implemented**. The features described below
> are now available in `src/startd8/integrations/contextcore.py`.
>
> **For current usage documentation, see:**
> - `$STARTD8_SDK_ROOT/docs/CONTEXTCORE_WORKFLOW_AUTOMATION.md` (user guide)
> - `~/Documents/dev/contextcore-beaver/docs/PRIME_CONTRACTOR_WORKFLOW.md` (canonical reference)
>
> This document is preserved for historical context on the design decisions.
>
> ---
> *Archived: 2026-01-27*

## Overview

This plan outlines how to integrate StartD8 SDK workflows (like LeadContractorWorkflow) with ContextCore's task tracking system, enabling:
- Workflow executions to be tracked as ContextCore tasks (OTel spans)
- Workflow results to be linked to project/sprint context
- Unified observability in Grafana (traces, metrics, logs)

## ContextCore Task Model

ContextCore models tasks as **OpenTelemetry spans** with:

| Concept | OTel Mapping |
|---------|-------------|
| Task creation | `span.start()` |
| Status updates | `span.add_event("task.status_changed")` |
| Blockers | `span.set_status(ERROR)` + event |
| Completion | `span.end()` |
| Parent tasks | `parent_span_id` |
| Dependencies | `span.Link` |

### Key Semantic Conventions

```python
# Task attributes
task.id              # Unique identifier (e.g., "SDK-102")
task.type            # epic|story|task|subtask|bug|spike
task.title           # Human-readable title
task.status          # todo|in_progress|in_review|blocked|done
task.priority        # critical|high|medium|low
task.assignee        # Person assigned
task.story_points    # Estimated effort
task.parent_id       # Parent task ID
task.percent_complete # Progress (0-100)

# Project context
project.id           # Project identifier
project.name         # Project display name
sprint.id            # Sprint identifier
sprint.name          # Sprint name
```

---

## Integration Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      ContextCore Project                         │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Epic: SDK Development (EPIC-001)                            ││
│  │  ├── Story: ContextCore Integration (SDK-100)               ││
│  │  │    ├── Task: Add session tracking (SDK-101)              ││
│  │  │    ├── Task: Update MetricsHandler (SDK-102)     ← ──────┤│
│  │  │    │         ↓                                           ││
│  │  │    │   ┌─────────────────────────────────────┐           ││
│  │  │    │   │ LeadContractorWorkflow Execution    │           ││
│  │  │    │   │  • Creates span linked to SDK-102   │           ││
│  │  │    │   │  • Emits phase events               │           ││
│  │  │    │   │  • Records metrics with context     │           ││
│  │  │    │   └─────────────────────────────────────┘           ││
│  │  │    └── Task: Create dashboard (SDK-103)                  ││
│  │  └── Story: OTel Integration (SDK-110)                      ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Tasks

### Task 1: Create ContextCore Integration Module

Create `src/startd8/integrations/contextcore.py`:

```python
"""ContextCore integration for workflow task tracking."""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any

@dataclass
class ContextCoreConfig:
    """Configuration for ContextCore integration."""
    project_id: str
    project_name: Optional[str] = None
    sprint_id: Optional[str] = None
    parent_task_id: Optional[str] = None
    otlp_endpoint: str = "localhost:4317"
    auto_create_task: bool = True  # Create task span on workflow start
    auto_complete_task: bool = True  # Complete task span on workflow success
```

### Task 2: Create ContextCoreWorkflowAdapter

An adapter that wraps any workflow to add ContextCore tracking:

```python
class ContextCoreWorkflowAdapter:
    """
    Wraps a workflow to track execution as a ContextCore task.
    
    Example:
        from contextcore import TaskTracker
        from startd8.integrations.contextcore import ContextCoreWorkflowAdapter
        
        # Setup
        tracker = TaskTracker(project="my-project")
        workflow = LeadContractorWorkflow()
        adapter = ContextCoreWorkflowAdapter(workflow, tracker)
        
        # Execute with task tracking
        result = adapter.run(
            config={"task_description": "Implement auth"},
            task_id="SDK-102",
            task_title="Implement user authentication",
        )
    """
    
    def __init__(
        self,
        workflow: WorkflowBase,
        tracker: "TaskTracker",
        default_task_type: str = "task",
    ):
        self.workflow = workflow
        self.tracker = tracker
        self.default_task_type = default_task_type
    
    def run(
        self,
        config: Dict[str, Any],
        task_id: str,
        task_title: Optional[str] = None,
        task_type: str = "task",
        parent_id: Optional[str] = None,
        sprint_id: Optional[str] = None,
        assignee: Optional[str] = None,
        story_points: Optional[int] = None,
        **kwargs,
    ) -> WorkflowResult:
        """
        Execute workflow as a ContextCore task.
        
        1. Creates task span in ContextCore
        2. Updates status to "in_progress"
        3. Runs workflow
        4. Completes/blocks task based on result
        """
        # Start task span
        self.tracker.start_task(
            task_id=task_id,
            title=task_title or config.get("task_description", task_id),
            task_type=task_type,
            status="in_progress",
            parent_id=parent_id,
            sprint_id=sprint_id,
            assignee=assignee,
            story_points=story_points,
        )
        
        try:
            # Execute workflow
            result = self.workflow.run(config, **kwargs)
            
            if result.success:
                # Add completion event with metrics
                self.tracker._get_span(task_id).add_event(
                    "workflow.completed",
                    attributes={
                        "workflow_id": result.workflow_id,
                        "total_cost": result.metrics.total_cost,
                        "total_time_ms": result.metrics.total_time_ms,
                        "step_count": result.metrics.step_count,
                    }
                )
                self.tracker.complete_task(task_id)
            else:
                # Block task with error
                self.tracker.block_task(
                    task_id,
                    reason=result.error or "Workflow failed",
                )
            
            return result
            
        except Exception as e:
            self.tracker.block_task(task_id, reason=str(e))
            raise
```

### Task 3: Create LeadContractorContextCoreWorkflow

A specialized workflow that natively integrates with ContextCore:

```python
class LeadContractorContextCoreWorkflow(LeadContractorWorkflow):
    """
    Lead Contractor workflow with native ContextCore task tracking.
    
    Config extends LeadContractorWorkflow with:
        - task_id: ContextCore task ID (required)
        - task_title: Task title (optional, defaults to task_description)
        - parent_task_id: Parent epic/story ID (optional)
        - sprint_id: Sprint ID (optional)
        - contextcore_project: Project ID (required)
    
    Example:
        workflow = LeadContractorContextCoreWorkflow()
        result = workflow.run({
            "task_description": "Implement rate limiter",
            "task_id": "SDK-102",
            "contextcore_project": "startd8-sdk",
            "sprint_id": "sprint-3",
            "parent_task_id": "SDK-100",  # Parent story
        })
    """
    
    def _execute(self, config, agents, on_progress):
        # Initialize tracker
        project = config.get("contextcore_project", "default")
        tracker = self._get_or_create_tracker(project)
        
        task_id = config["task_id"]
        
        # Start task span
        tracker.start_task(
            task_id=task_id,
            title=config.get("task_title", config["task_description"]),
            task_type="task",
            status="in_progress",
            parent_id=config.get("parent_task_id"),
            sprint_id=config.get("sprint_id"),
            url=config.get("task_url"),
        )
        
        try:
            # Add spec phase event
            tracker._get_span(task_id).add_event(
                "workflow.phase",
                attributes={"phase": "spec", "status": "started"}
            )
            
            # Run parent workflow logic
            result = super()._execute(config, agents, on_progress)
            
            # Record result
            if result.success:
                tracker._get_span(task_id).add_event(
                    "workflow.completed",
                    attributes={
                        "lead_cost": result.metadata.get("lead_cost", 0),
                        "drafter_cost": result.metadata.get("drafter_cost", 0),
                        "iterations": result.metadata.get("total_iterations", 0),
                    }
                )
                tracker.complete_task(task_id)
            else:
                tracker.block_task(task_id, reason=result.error)
            
            return result
            
        except Exception as e:
            tracker.block_task(task_id, reason=str(e))
            raise
```

### Task 4: Add Task List Support

Support running multiple workflow tasks from a task list:

```python
@dataclass
class WorkflowTaskSpec:
    """Specification for a single workflow task."""
    task_id: str
    title: str
    config: Dict[str, Any]
    parent_id: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)
    story_points: Optional[int] = None

class ContextCoreTaskRunner:
    """
    Run multiple workflow tasks with dependency tracking.
    
    Example:
        runner = ContextCoreTaskRunner(
            project="startd8-sdk",
            sprint_id="sprint-3",
        )
        
        tasks = [
            WorkflowTaskSpec(
                task_id="SDK-101",
                title="Add session tracking",
                config={"task_description": "..."},
                story_points=3,
            ),
            WorkflowTaskSpec(
                task_id="SDK-102", 
                title="Update MetricsHandler",
                config={"task_description": "..."},
                depends_on=["SDK-101"],  # Run after SDK-101
                story_points=2,
            ),
        ]
        
        results = runner.run_all(tasks, workflow=LeadContractorWorkflow())
    """
```

### Task 5: CLI Integration

Add CLI commands for task-based workflow execution:

```bash
# Run workflow as ContextCore task
startd8 workflow run lead-contractor \
    --task-id SDK-102 \
    --project startd8-sdk \
    --sprint sprint-3 \
    --parent SDK-100 \
    --config '{"task_description": "Implement auth"}'

# Run task list from file
startd8 workflow run-tasks tasks.yaml \
    --project startd8-sdk \
    --sprint sprint-3
```

### Task 6: Grafana Integration

Update dashboards to show workflow-task correlation:

```promql
# Workflow cost by ContextCore project
sum by (project_id) (
  increase(startd8_cost_total{project_id!=""}[24h])
)

# Task completion rate by sprint
count(contextcore_task_status{status="done", sprint_id="$sprint"}) /
count(contextcore_task_status{sprint_id="$sprint"})

# Workflow executions linked to tasks
trace_info{service="startd8-sdk", task.id=~".+"}
```

---

## Implementation Phases

### Phase 1: Core Integration (Tasks 1-2)
- Create `ContextCoreConfig` dataclass
- Create `ContextCoreWorkflowAdapter`
- Add unit tests

### Phase 2: Native Workflow (Task 3)
- Create `LeadContractorContextCoreWorkflow`
- Update workflow registry
- Add integration tests

### Phase 3: Task List Support (Task 4)
- Create `WorkflowTaskSpec` model
- Create `ContextCoreTaskRunner`
- Add dependency resolution

### Phase 4: CLI & Dashboard (Tasks 5-6)
- Add CLI commands
- Update Grafana dashboard
- Documentation

---

## Usage Examples

### Basic: Single Task Execution

```python
from contextcore import TaskTracker
from startd8.workflows.builtin import LeadContractorWorkflow
from startd8.integrations.contextcore import ContextCoreWorkflowAdapter

# Setup
tracker = TaskTracker(project="startd8-sdk")
workflow = LeadContractorWorkflow()
adapter = ContextCoreWorkflowAdapter(workflow, tracker)

# Execute
result = adapter.run(
    config={
        "task_description": "Implement rate limiter using token bucket",
        "context": {"language": "Python"},
    },
    task_id="SDK-102",
    task_title="Implement rate limiter",
    parent_id="SDK-100",  # Parent story
    sprint_id="sprint-3",
    story_points=3,
)

print(f"Task SDK-102: {'completed' if result.success else 'blocked'}")
```

### Advanced: Task List with Dependencies

```python
from startd8.integrations.contextcore import ContextCoreTaskRunner, WorkflowTaskSpec

runner = ContextCoreTaskRunner(
    project="startd8-sdk",
    sprint_id="sprint-3",
)

tasks = [
    WorkflowTaskSpec(
        task_id="SDK-101",
        title="Add ContextCore session fields",
        config={"task_description": "Add project_id, task_id, sprint_id to SessionMetrics"},
        story_points=2,
    ),
    WorkflowTaskSpec(
        task_id="SDK-102",
        title="Update MetricsHandler",
        config={"task_description": "Add per-project metrics aggregation"},
        depends_on=["SDK-101"],
        story_points=3,
    ),
    WorkflowTaskSpec(
        task_id="SDK-103",
        title="Create Grafana dashboard",
        config={"task_description": "Add project context filtering"},
        depends_on=["SDK-101", "SDK-102"],
        story_points=2,
    ),
]

results = runner.run_all(tasks, workflow=LeadContractorWorkflow())

for task_id, result in results.items():
    status = "✅" if result.success else "❌"
    print(f"{status} {task_id}: {result.metrics.total_time_ms}ms, ${result.metrics.total_cost:.2f}")
```

### CLI Usage

```bash
# Single task
startd8 workflow run lead-contractor \
    --task-id SDK-102 \
    --task-title "Implement rate limiter" \
    --project startd8-sdk \
    --sprint sprint-3 \
    --parent SDK-100 \
    --config-file task-config.json

# From task list YAML
startd8 workflow run-tasks sprint-3-tasks.yaml

# View task status in ContextCore
contextcore task list --project startd8-sdk
```

---

## Benefits

1. **Unified Tracking**: Workflow executions appear as tasks in ContextCore
2. **Cost Attribution**: Costs roll up to projects, sprints, epics
3. **Progress Visibility**: Workflow progress updates task percent_complete
4. **Dependency Management**: Tasks run in order based on dependencies
5. **Observability**: Single pane of glass in Grafana for code + business metrics

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `src/startd8/integrations/__init__.py` | Create | Integration module init |
| `src/startd8/integrations/contextcore.py` | Create | Core ContextCore integration |
| `src/startd8/workflows/builtin/lead_contractor_contextcore_workflow.py` | Create | Native ContextCore workflow |
| `src/startd8/workflows/builtin/__init__.py` | Modify | Add new workflow export |
| `src/startd8/cli.py` | Modify | Add task-based commands |
| `dashboards/startd8-contextcore.json` | Create | Combined dashboard |
| `tests/integration/test_contextcore_integration.py` | Create | Integration tests |

---

## Next Steps

1. Review this plan
2. Start Phase 1: Core Integration
3. Test with real ContextCore instance
4. Iterate based on feedback
