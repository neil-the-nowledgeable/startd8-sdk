"""
Workflow data models for the StartD8 SDK.

These models define the structure for workflow metadata, configuration,
and results used by the WorkflowRegistry and workflow implementations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class WorkflowStatus(str, Enum):
    """Status of a workflow execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ProjectContext:
    """
    ContextCore project metadata for workflow tracking.
    
    Enables correlation of workflow executions with project management
    systems and Grafana dashboards.
    
    Semantic Conventions:
        - project_id: io.contextcore.project.id
        - project_name: io.contextcore.project.name
        - task_id: io.contextcore.task.id
        - sprint_id: io.contextcore.sprint.id
    """
    project_id: Optional[str] = None
    project_name: Optional[str] = None
    task_id: Optional[str] = None
    sprint_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary, excluding None values."""
        return {k: v for k, v in {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "task_id": self.task_id,
            "sprint_id": self.sprint_id,
        }.items() if v is not None}
    
    def to_labels(self) -> Dict[str, str]:
        """Convert to Prometheus/OTel labels format."""
        labels = {}
        if self.project_id:
            labels["project_id"] = self.project_id
        if self.project_name:
            labels["project_name"] = self.project_name
        if self.task_id:
            labels["task_id"] = self.task_id
        if self.sprint_id:
            labels["sprint_id"] = self.sprint_id
        return labels
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> "ProjectContext":
        """
        Extract project context from workflow config.
        
        Looks for top-level keys or nested under 'project_context'.
        """
        # Check for nested project_context first
        if "project_context" in config and isinstance(config["project_context"], dict):
            ctx = config["project_context"]
            return cls(
                project_id=ctx.get("project_id"),
                project_name=ctx.get("project_name"),
                task_id=ctx.get("task_id"),
                sprint_id=ctx.get("sprint_id"),
            )
        
        # Fall back to top-level keys
        return cls(
            project_id=config.get("project_id"),
            project_name=config.get("project_name"),
            task_id=config.get("task_id"),
            sprint_id=config.get("sprint_id"),
        )
    
    def is_empty(self) -> bool:
        """Check if all fields are None."""
        return all(v is None for v in [
            self.project_id, self.project_name, self.task_id, self.sprint_id
        ])


class AgentCount(str, Enum):
    """How many agents a workflow requires."""
    NONE = "none"           # Workflow doesn't use agents
    SINGLE = "single"       # Exactly one agent
    MULTIPLE = "multiple"   # Fixed number > 1
    CONFIGURABLE = "configurable"  # User-defined count


@dataclass
class WorkflowInput:
    """Definition of a workflow input parameter."""
    name: str
    type: str  # "string", "text", "file", "number", "boolean", "agent_spec", "agent_spec_list"
    required: bool = True
    description: str = ""
    default: Any = None

    def to_json_schema(self) -> Dict[str, Any]:
        """Convert to JSON Schema format."""
        type_mapping = {
            "string": "string",
            "text": "string",
            "file": "string",
            "number": "number",
            "boolean": "boolean",
            "agent_spec": "string",
            "agent_spec_list": {"type": "array", "items": {"type": "string"}},
        }

        schema: Dict[str, Any] = {}
        mapped_type = type_mapping.get(self.type, "string")

        if isinstance(mapped_type, dict):
            schema.update(mapped_type)
        else:
            schema["type"] = mapped_type

        if self.description:
            schema["description"] = self.description
        if self.default is not None:
            schema["default"] = self.default

        return schema


@dataclass
class WorkflowMetadata:
    """
    Metadata describing a workflow's capabilities and requirements.

    Used by the WorkflowRegistry for discovery and by external agents
    to understand how to invoke workflows.
    """
    workflow_id: str          # Unique identifier (e.g., "pipeline", "critical-review")
    name: str                 # Display name
    description: str          # What this workflow does
    version: str = "1.0.0"    # Semantic version

    # Capabilities and categorization
    capabilities: List[str] = field(default_factory=list)  # What it can do
    tags: List[str] = field(default_factory=list)          # Categories/filtering

    # Agent requirements
    requires_agents: bool = True
    agent_count: AgentCount = AgentCount.CONFIGURABLE
    min_agents: int = 1
    max_agents: Optional[int] = None  # None = unlimited

    # Input/output definitions
    inputs: List[WorkflowInput] = field(default_factory=list)

    def get_input_schema(self) -> Dict[str, Any]:
        """Generate JSON Schema for workflow inputs."""
        properties = {}
        required = []

        for inp in self.inputs:
            properties[inp.name] = inp.to_json_schema()
            if inp.required:
                required.append(inp.name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON export."""
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": self.capabilities,
            "tags": self.tags,
            "requires_agents": self.requires_agents,
            "agent_count": self.agent_count.value,
            "min_agents": self.min_agents,
            "max_agents": self.max_agents,
            "input_schema": self.get_input_schema(),
        }


@dataclass
class RetryPolicy:
    """Configuration for automatic retry on transient failures (FR-100)."""
    max_retries: int = 3
    backoff_base: float = 1.0       # seconds
    backoff_max: float = 60.0       # seconds
    jitter: bool = True
    retryable_status_codes: List[int] = field(
        default_factory=lambda: [429, 500, 502, 503, 504]
    )


@dataclass
class WorkflowMetrics:
    """Metrics collected during workflow execution."""
    total_time_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0
    step_count: int = 0
    total_retries: int = 0  # FR-411

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_time_ms": self.total_time_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_cost": self.total_cost,
            "step_count": self.step_count,
            "total_retries": self.total_retries,
        }


@dataclass
class StepResult:
    """Result of a single workflow step."""
    step_name: str
    agent_name: Optional[str] = None
    input: str = ""
    output: str = ""
    time_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.error is None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_name": self.step_name,
            "agent_name": self.agent_name,
            "output": self.output[:500] + "..." if len(self.output) > 500 else self.output,
            "time_ms": self.time_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost": self.cost,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class WorkflowResult:
    """
    Result of a workflow execution.

    Contains the final output, all step results, and aggregated metrics.
    Includes optional ContextCore project context for tracking/correlation.
    """
    workflow_id: str
    success: bool
    output: Any  # Workflow-specific output (string, dict, etc.)
    metrics: WorkflowMetrics = field(default_factory=WorkflowMetrics)
    steps: List[StepResult] = field(default_factory=list)
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    # ContextCore project context
    project_context: Optional[ProjectContext] = None

    @property
    def duration_ms(self) -> int:
        """Calculate duration from timestamps if available."""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return self.metrics.total_time_ms

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON export."""
        result = {
            "workflow_id": self.workflow_id,
            "success": self.success,
            "output": str(self.output)[:1000] if self.output else None,
            "error": self.error,
            "metrics": self.metrics.to_dict(),
            "steps": [s.to_dict() for s in self.steps],
            "duration_ms": self.duration_ms,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
        }
        # Include project context if present
        if self.project_context and not self.project_context.is_empty():
            result["project_context"] = self.project_context.to_dict()
        return result

    @classmethod
    def from_error(
        cls,
        workflow_id: str,
        error: str,
        steps: Optional[List["StepResult"]] = None,
        metrics: Optional["WorkflowMetrics"] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "WorkflowResult":
        """
        Create a failed result from an error message.

        Args:
            workflow_id: Workflow identifier
            error: Error message describing the failure
            steps: Optional list of steps completed before failure
            metrics: Optional metrics collected before failure
            metadata: Optional metadata to include
        """
        return cls(
            workflow_id=workflow_id,
            success=False,
            output=None,
            error=error,
            steps=steps or [],
            metrics=metrics,
            metadata=metadata or {},
        )


@dataclass
class ValidationResult:
    """Result of workflow configuration validation."""
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @classmethod
    def success(cls) -> "ValidationResult":
        return cls(valid=True)

    @classmethod
    def failure(cls, errors: List[str]) -> "ValidationResult":
        return cls(valid=False, errors=errors)
