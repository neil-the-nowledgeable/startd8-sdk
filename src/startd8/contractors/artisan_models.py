"""
Pydantic v2 models for the Artisan Contractor workflow system.

This module provides comprehensive data models for representing workflows,
phases, work items, design documents, and retrospectives with full JSON
serialization support.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Type, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)


# ---------------------------------------------------------------------------
# Utility functions (must be defined before classes that use them as defaults)
# ---------------------------------------------------------------------------

def utc_now() -> datetime:
    """Get current UTC time with timezone info."""
    return datetime.now(timezone.utc)


def generate_id() -> str:
    """Generate a unique string identifier."""
    return str(uuid.uuid4())


def validate_uuid(value: str) -> str:
    """Validate UUID format string."""
    try:
        uuid.UUID(value)
        return value
    except ValueError:
        raise ValueError(f'Invalid UUID format: {value}')


def ensure_utc(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware, defaulting to UTC if naive."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------------------
# Base model
# ---------------------------------------------------------------------------

class BaseAppModel(BaseModel):
    """
    Base model with shared configuration and utilities.

    All models in the system inherit from this base to ensure consistent
    behavior for validation, serialization, and configuration.
    """
    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        str_strip_whitespace=True,
        json_schema_extra={'examples': []},
        populate_by_name=True,
    )

    def to_json_dict(self) -> Dict[str, Any]:
        """Export model to JSON-serializable dictionary."""
        return self.model_dump(mode='json', exclude_none=False)

    def to_json_string(self, indent: int = 2) -> str:
        """Export model to formatted JSON string."""
        return self.model_dump_json(indent=indent, exclude_none=False)

    @classmethod
    def from_json_dict(cls, data: Dict[str, Any]) -> 'BaseAppModel':
        """Create model instance from dictionary."""
        return cls.model_validate(data)

    @classmethod
    def from_json_string(cls, json_string: str) -> 'BaseAppModel':
        """Create model instance from JSON string."""
        return cls.model_validate_json(json_string)


# TypeVar for generic serialization functions
T = TypeVar('T', bound=BaseAppModel)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class WorkflowStatus(str, Enum):
    """Status of the overall workflow execution."""
    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class PhaseStatus(str, Enum):
    """Status of a workflow phase."""
    PENDING = 'pending'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    FAILED = 'failed'
    SKIPPED = 'skipped'


class WorkItemStatus(str, Enum):
    """Status of a work item."""
    TODO = 'todo'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    BLOCKED = 'blocked'
    CANCELLED = 'cancelled'


class WorkItemPriority(str, Enum):
    """Priority level of a work item."""
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'
    CRITICAL = 'critical'


class ChunkStatus(str, Enum):
    """Status of a design document chunk."""
    DRAFT = 'draft'
    IN_REVIEW = 'in_review'
    APPROVED = 'approved'
    REJECTED = 'rejected'


class PhaseType(str, Enum):
    """Enumeration of workflow phase types."""
    PLANNING = 'planning'
    DESIGN = 'design'
    IMPLEMENTATION = 'implementation'
    TESTING = 'testing'
    REVIEW = 'review'
    DEPLOYMENT = 'deployment'
    POST_DEPLOYMENT = 'post_deployment'


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class WorkItem(BaseAppModel):
    """Represents a discrete unit of work within a phase."""
    id: str = Field(default_factory=generate_id, description='Unique identifier')
    title: str = Field(..., min_length=1, max_length=200, description='Work item title')
    description: str = Field(default='', description='Detailed description')
    status: WorkItemStatus = Field(default=WorkItemStatus.TODO, description='Current status')
    priority: WorkItemPriority = Field(default=WorkItemPriority.MEDIUM, description='Priority level')
    assignee: Optional[str] = Field(default=None, description='Assigned person or agent')
    tags: List[str] = Field(default_factory=list, description='Categorization tags')
    estimated_hours: Optional[float] = Field(default=None, ge=0, description='Estimated effort in hours')
    actual_hours: Optional[float] = Field(default=None, ge=0, description='Actual effort in hours')
    created_at: datetime = Field(default_factory=utc_now, description='Creation timestamp')
    updated_at: datetime = Field(default_factory=utc_now, description='Last update timestamp')
    completed_at: Optional[datetime] = Field(default=None, description='Completion timestamp')
    dependencies: List[str] = Field(default_factory=list, description='IDs of dependent work items')
    metadata: Dict[str, Any] = Field(default_factory=dict, description='Additional metadata')

    @field_validator('title')
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Title cannot be empty')
        return v.strip()

    @field_validator('completed_at')
    @classmethod
    def validate_completed_at(cls, v: Optional[datetime], info: ValidationInfo) -> Optional[datetime]:
        if v is not None and info.data.get('status') != WorkItemStatus.COMPLETED:
            raise ValueError('completed_at can only be set when status is COMPLETED')
        return v


class LessonLearned(BaseAppModel):
    """Represents a lesson learned during workflow execution."""
    id: str = Field(default_factory=generate_id, description='Unique identifier')
    title: str = Field(..., min_length=1, max_length=200, description='Lesson title')
    description: str = Field(..., min_length=1, description='Detailed description')
    category: str = Field(..., min_length=1, description='Category of the lesson')
    impact: str = Field(default='medium', pattern='^(low|medium|high)$', description='Impact level')
    action_items: List[str] = Field(default_factory=list, description='Recommended actions')
    created_at: datetime = Field(default_factory=utc_now, description='Creation timestamp')
    phase: Optional[str] = Field(default=None, description='Phase where lesson was learned')
    metadata: Dict[str, Any] = Field(default_factory=dict, description='Additional metadata')

    @field_validator('title', 'description', 'category')
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Field cannot be empty')
        return v.strip()


class Retrospective(BaseAppModel):
    """Represents a retrospective analysis of workflow execution."""
    id: str = Field(default_factory=generate_id, description='Unique identifier')
    workflow_id: str = Field(..., description='Associated workflow ID')
    summary: str = Field(default='', description='Executive summary')
    what_went_well: List[str] = Field(default_factory=list, description='Positive outcomes')
    what_went_wrong: List[str] = Field(default_factory=list, description='Issues encountered')
    lessons_learned: List[LessonLearned] = Field(default_factory=list, description='Structured lessons')
    action_items: List[str] = Field(default_factory=list, description='Next steps')
    participants: List[str] = Field(default_factory=list, description='Participants')
    conducted_at: datetime = Field(default_factory=utc_now, description='When conducted')
    created_at: datetime = Field(default_factory=utc_now, description='Creation timestamp')
    metadata: Dict[str, Any] = Field(default_factory=dict, description='Additional metadata')

    @field_validator('workflow_id')
    @classmethod
    def workflow_id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('workflow_id cannot be empty')
        return v.strip()


class ChunkState(BaseAppModel):
    """Represents a chunk or section of a design document."""
    id: str = Field(default_factory=generate_id, description='Unique identifier')
    title: str = Field(..., min_length=1, max_length=300, description='Chunk title')
    content: str = Field(default='', description='Main content')
    order: int = Field(default=0, ge=0, description='Display order')
    status: ChunkStatus = Field(default=ChunkStatus.DRAFT, description='Current status')
    author: Optional[str] = Field(default=None, description='Author identifier')
    reviewer: Optional[str] = Field(default=None, description='Reviewer identifier')
    version: int = Field(default=1, ge=1, description='Version number')
    created_at: datetime = Field(default_factory=utc_now, description='Creation timestamp')
    updated_at: datetime = Field(default_factory=utc_now, description='Last update timestamp')
    approved_at: Optional[datetime] = Field(default=None, description='Approval timestamp')
    comments: List[str] = Field(default_factory=list, description='Review comments')
    metadata: Dict[str, Any] = Field(default_factory=dict, description='Additional metadata')

    @field_validator('title')
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Title cannot be empty')
        return v.strip()

    @field_validator('approved_at')
    @classmethod
    def validate_approved_at(cls, v: Optional[datetime], info: ValidationInfo) -> Optional[datetime]:
        if v is not None and info.data.get('status') != ChunkStatus.APPROVED:
            raise ValueError('approved_at can only be set when status is APPROVED')
        return v


class DesignDocument(BaseAppModel):
    """Represents a complete design document composed of chunks."""
    id: str = Field(default_factory=generate_id, description='Unique identifier')
    title: str = Field(..., min_length=1, max_length=300, description='Document title')
    description: str = Field(default='', description='Document description')
    version: str = Field(default='1.0.0', pattern='^\\d+\\.\\d+\\.\\d+$', description='Semantic version')
    status: ChunkStatus = Field(default=ChunkStatus.DRAFT, description='Overall status')
    chunks: List[ChunkState] = Field(default_factory=list, description='Document chunks')
    authors: List[str] = Field(default_factory=list, description='Author identifiers')
    reviewers: List[str] = Field(default_factory=list, description='Reviewer identifiers')
    created_at: datetime = Field(default_factory=utc_now, description='Creation timestamp')
    updated_at: datetime = Field(default_factory=utc_now, description='Last update timestamp')
    published_at: Optional[datetime] = Field(default=None, description='Publication timestamp')
    tags: List[str] = Field(default_factory=list, description='Categorization tags')
    metadata: Dict[str, Any] = Field(default_factory=dict, description='Additional metadata')

    @field_validator('title')
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Title cannot be empty')
        return v.strip()

    @field_validator('chunks')
    @classmethod
    def chunks_have_unique_orders(cls, v: List[ChunkState]) -> List[ChunkState]:
        if v:
            orders = [chunk.order for chunk in v]
            if len(orders) != len(set(orders)):
                raise ValueError('Chunk order values must be unique')
        return v


class PhaseResult(BaseAppModel):
    """Represents the result of a workflow phase execution."""
    id: str = Field(default_factory=generate_id, description='Unique identifier')
    phase_name: str = Field(..., min_length=1, max_length=100, description='Phase name')
    status: PhaseStatus = Field(default=PhaseStatus.PENDING, description='Phase status')
    work_items: List[WorkItem] = Field(default_factory=list, description='Phase work items')
    lessons_learned: List[LessonLearned] = Field(default_factory=list, description='Phase lessons')
    started_at: Optional[datetime] = Field(default=None, description='Start timestamp')
    completed_at: Optional[datetime] = Field(default=None, description='Completion timestamp')
    duration_seconds: Optional[float] = Field(default=None, ge=0, description='Duration in seconds')
    output: Dict[str, Any] = Field(default_factory=dict, description='Phase output')
    error_message: Optional[str] = Field(default=None, description='Error message if failed')
    metadata: Dict[str, Any] = Field(default_factory=dict, description='Additional metadata')

    @field_validator('phase_name')
    @classmethod
    def phase_name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('phase_name cannot be empty')
        return v.strip()

    @model_validator(mode='after')
    def validate_timestamps_and_duration(self) -> 'PhaseResult':
        if self.started_at and self.completed_at:
            if self.completed_at < self.started_at:
                raise ValueError('completed_at must be after started_at')
            if self.duration_seconds is None:
                self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
        if self.status == PhaseStatus.COMPLETED and not self.completed_at:
            self.completed_at = utc_now()
            if self.started_at and self.duration_seconds is None:
                self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
        if self.status == PhaseStatus.IN_PROGRESS and not self.started_at:
            self.started_at = utc_now()
        return self

    @model_validator(mode='after')
    def validate_status_consistency(self) -> 'PhaseResult':
        if self.status == PhaseStatus.FAILED and not self.error_message:
            raise ValueError('error_message is required when status is FAILED')
        if self.completed_at and self.status not in [PhaseStatus.COMPLETED, PhaseStatus.FAILED, PhaseStatus.SKIPPED]:
            raise ValueError('completed_at can only be set when status is COMPLETED, FAILED, or SKIPPED')
        return self


class WorkflowState(BaseAppModel):
    """Represents the complete state of a workflow execution."""
    id: str = Field(default_factory=generate_id, description='Unique identifier')
    name: str = Field(..., min_length=1, max_length=200, description='Workflow name')
    description: str = Field(default='', description='Workflow description')
    status: WorkflowStatus = Field(default=WorkflowStatus.PENDING, description='Workflow status')
    phases: List[PhaseResult] = Field(default_factory=list, description='Phase results')
    design_document: Optional[DesignDocument] = Field(default=None, description='Design document')
    retrospective: Optional[Retrospective] = Field(default=None, description='Retrospective')
    current_phase: int = Field(default=0, ge=0, description='Current phase index')
    created_at: datetime = Field(default_factory=utc_now, description='Creation timestamp')
    updated_at: datetime = Field(default_factory=utc_now, description='Last update timestamp')
    started_at: Optional[datetime] = Field(default=None, description='Start timestamp')
    completed_at: Optional[datetime] = Field(default=None, description='Completion timestamp')
    total_duration_seconds: Optional[float] = Field(default=None, ge=0, description='Total duration')
    context: Dict[str, Any] = Field(default_factory=dict, description='Workflow context')
    metadata: Dict[str, Any] = Field(default_factory=dict, description='Additional metadata')

    @field_validator('name')
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('name cannot be empty')
        return v.strip()

    @field_validator('current_phase')
    @classmethod
    def validate_current_phase(cls, v: int, info: ValidationInfo) -> int:
        phases = info.data.get('phases', [])
        if phases and v >= len(phases):
            raise ValueError(f'current_phase ({v}) must be less than number of phases ({len(phases)})')
        return v

    @model_validator(mode='after')
    def validate_timestamps_and_duration(self) -> 'WorkflowState':
        if self.started_at and self.completed_at:
            if self.completed_at < self.started_at:
                raise ValueError('completed_at must be after started_at')
            if self.total_duration_seconds is None:
                self.total_duration_seconds = (self.completed_at - self.started_at).total_seconds()
        if self.status == WorkflowStatus.COMPLETED and not self.completed_at:
            self.completed_at = utc_now()
            if self.started_at and self.total_duration_seconds is None:
                self.total_duration_seconds = (self.completed_at - self.started_at).total_seconds()
        if self.status == WorkflowStatus.IN_PROGRESS and not self.started_at:
            self.started_at = utc_now()
        return self

    @model_validator(mode='after')
    def validate_status_consistency(self) -> 'WorkflowState':
        if self.status == WorkflowStatus.COMPLETED:
            if not all(phase.status in [PhaseStatus.COMPLETED, PhaseStatus.SKIPPED] for phase in self.phases):
                raise ValueError('All phases must be COMPLETED or SKIPPED when workflow is COMPLETED')
        if self.completed_at and self.status not in [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED]:
            raise ValueError('completed_at can only be set when status is COMPLETED, FAILED, or CANCELLED')
        return self

    def get_current_phase(self) -> Optional[PhaseResult]:
        if 0 <= self.current_phase < len(self.phases):
            return self.phases[self.current_phase]
        return None

    def get_phase_by_name(self, phase_name: str) -> Optional[PhaseResult]:
        for phase in self.phases:
            if phase.phase_name == phase_name:
                return phase
        return None


# ---------------------------------------------------------------------------
# Serialization utilities
# ---------------------------------------------------------------------------

def serialize_to_file(model: BaseAppModel, filepath: str, indent: int = 2) -> None:
    """Serialize a model to a JSON file."""
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(model.to_json_string(indent=indent))


def deserialize_from_file(model_class: Type[T], filepath: str) -> T:
    """Deserialize a model from a JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return model_class.from_json_string(f.read())


def serialize_list(models: List[BaseAppModel], indent: int = 2) -> str:
    """Serialize a list of models to JSON string."""
    data = [model.to_json_dict() for model in models]
    return json.dumps(data, indent=indent, default=str)


def deserialize_list(model_class: Type[T], json_string: str) -> List[T]:
    """Deserialize a list of models from JSON string."""
    data = json.loads(json_string)
    if not isinstance(data, list):
        raise ValueError('JSON string must represent a list of models')
    return [model_class.from_json_dict(item) for item in data]


def deep_update(target: Dict[str, Any], source: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge source dictionary into target dictionary."""
    for key, value in source.items():
        if key in target and isinstance(target[key], dict) and isinstance(value, dict):
            deep_update(target[key], value)
        else:
            target[key] = value
    return target


__all__ = [
    'BaseAppModel', 'utc_now', 'generate_id', 'validate_uuid', 'ensure_utc',
    'WorkflowStatus', 'PhaseStatus', 'WorkItemStatus', 'WorkItemPriority',
    'ChunkStatus', 'PhaseType',
    'WorkItem', 'LessonLearned', 'Retrospective',
    'ChunkState', 'DesignDocument', 'PhaseResult', 'WorkflowState',
    'serialize_to_file', 'deserialize_from_file', 'serialize_list', 'deserialize_list',
    'deep_update',
]
