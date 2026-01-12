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
class WorkflowMetrics:
    """Metrics collected during workflow execution."""
    total_time_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0
    step_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_time_ms": self.total_time_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_cost": self.total_cost,
            "step_count": self.step_count,
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

    @property
    def duration_ms(self) -> int:
        """Calculate duration from timestamps if available."""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return self.metrics.total_time_ms

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON export."""
        return {
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

    @classmethod
    def from_error(cls, workflow_id: str, error: str) -> "WorkflowResult":
        """Create a failed result from an error message."""
        return cls(
            workflow_id=workflow_id,
            success=False,
            output=None,
            error=error,
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
