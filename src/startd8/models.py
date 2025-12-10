"""
Data models for StartDate Agent Framework
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum
from pathlib import Path
import re

if TYPE_CHECKING:
    from .agents import BaseAgent


class TokenUsage(BaseModel):
    """Token usage statistics"""
    input: int = Field(description="Input tokens used")
    output: int = Field(description="Output tokens generated")
    total: int = Field(description="Total tokens (input + output)")
    model_name: Optional[str] = Field(default=None, description="Model name for cost calculation")
    
    @field_validator('input', 'output', 'total')
    @classmethod
    def validate_tokens(cls, v: int) -> int:
        """Validate token counts are non-negative"""
        if v < 0:
            raise ValueError("Token counts must be non-negative")
        return v
    
    @model_validator(mode='after')
    def validate_total(self) -> 'TokenUsage':
        """Validate total matches input + output"""
        if self.total != self.input + self.output:
            raise ValueError(f"Total tokens ({self.total}) must equal input ({self.input}) + output ({self.output})")
        return self
    
    @property
    def cost_estimate(self) -> float:
        """Estimate cost in USD using configured pricing"""
        from .config_models import PricingConfig
        
        # Use default pricing config
        pricing_config = PricingConfig.default()
        
        if self.model_name:
            return pricing_config.calculate_cost(self.model_name, self.input, self.output)
        else:
            # Fallback to default Claude 3.5 Sonnet pricing
            input_cost = (self.input / 1_000_000) * 3.0
            output_cost = (self.output / 1_000_000) * 15.0
            return input_cost + output_cost


class Prompt(BaseModel):
    """Versioned prompt for agent testing"""
    id: str = Field(description="Unique identifier")
    content: str = Field(description="Prompt content")
    version: str = Field(description="Version identifier (semver)")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tags: List[str] = Field(default_factory=list, description="Categorization tags")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    @field_validator('content')
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Validate prompt content"""
        if not v or not v.strip():
            raise ValueError("Prompt content cannot be empty")
        if len(v) > 1_000_000:  # 1MB limit
            raise ValueError("Prompt content exceeds maximum length of 1,000,000 characters")
        return v.strip()
    
    @field_validator('version')
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Validate semver format"""
        # Basic semver pattern: MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]
        semver_pattern = r'^\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?(\+[a-zA-Z0-9.-]+)?$'
        if not re.match(semver_pattern, v):
            raise ValueError(
                f"Version '{v}' does not match semver format (e.g., '1.0.0', '1.0.0-alpha', '1.0.0+build')"
            )
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "prompt-123",
                "content": "Implement JWT authentication",
                "version": "1.0.0",
                "tags": ["auth", "security"],
                "metadata": {"priority": "high"}
            }
        }


class AgentResponse(BaseModel):
    """Agent's response to a prompt"""
    id: str = Field(description="Unique identifier")
    prompt_id: str = Field(description="ID of prompt this responds to")
    agent_name: str = Field(description="Name/identifier of the agent")
    model: str = Field(description="Model name (e.g., 'claude-3-5-sonnet-20241022')")
    response: str = Field(description="The agent's response content")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    response_time_ms: int = Field(description="Response time in milliseconds")
    token_usage: Optional[TokenUsage] = Field(default=None, description="Token usage statistics")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    @field_validator('response_time_ms')
    @classmethod
    def validate_response_time(cls, v: int) -> int:
        """Validate response time is positive"""
        if v < 0:
            raise ValueError("Response time must be non-negative")
        if v > 86_400_000:  # 24 hours in ms
            raise ValueError("Response time exceeds reasonable maximum (24 hours)")
        return v
    
    @property
    def response_time_seconds(self) -> float:
        """Response time in seconds"""
        return self.response_time_ms / 1000.0
    
    @property
    def tokens_per_second(self) -> float:
        """Calculate tokens generated per second"""
        if self.token_usage and self.response_time_ms > 0:
            return (self.token_usage.output / self.response_time_ms) * 1000.0
        return 0.0


class BenchmarkStatus(str, Enum):
    """Benchmark execution status"""
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Benchmark(BaseModel):
    """Benchmark comparison across multiple agents"""
    id: str = Field(description="Unique identifier")
    name: str = Field(description="Benchmark name")
    prompt_id: str = Field(description="ID of prompt being benchmarked")
    response_ids: List[str] = Field(default_factory=list, description="IDs of agent responses")
    status: BenchmarkStatus = Field(default=BenchmarkStatus.CREATED)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    summary: Optional[str] = Field(default=None, description="Summary of findings")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ComparisonMetrics(BaseModel):
    """Metrics for comparing agent responses"""
    total_responses: int
    avg_response_time_ms: float
    avg_tokens_per_second: float
    total_tokens: int
    total_cost_estimate: float
    models_used: List[str]
    fastest_agent: Optional[str] = None
    most_efficient_agent: Optional[str] = None
    cheapest_agent: Optional[str] = None


class ResponseComparison(BaseModel):
    """Detailed comparison of responses for a prompt"""
    prompt: Optional[Dict[str, Any]] = Field(default=None, description="Prompt data")
    total_responses: int = Field(description="Total number of responses")
    avg_response_time_ms: float = Field(description="Average response time in milliseconds")
    total_tokens: int = Field(description="Total tokens used across all responses")
    responses: List[Dict[str, Any]] = Field(default_factory=list, description="Response summaries")
    rankings: Dict[str, List[Dict[str, Any]]] = Field(
        default_factory=dict,
        description="Rankings by different metrics"
    )
    message: Optional[str] = Field(default=None, description="Optional message")


class BenchmarkReport(BaseModel):
    """Detailed benchmark report"""
    benchmark: Dict[str, Any] = Field(description="Benchmark data")
    prompt: Optional[Dict[str, Any]] = Field(default=None, description="Prompt data")
    comparison: ResponseComparison = Field(description="Response comparison")
    generated_at: str = Field(description="Report generation timestamp (ISO format)")


class GitBranchInfo(BaseModel):
    """Git branch information for agent work"""
    branch_name: str = Field(description="Name of the branch")
    agent_name: str = Field(description="Agent assigned to this branch")
    model: str = Field(description="Model being used")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    base_branch: str = Field(default="main", description="Base branch")
    commits: List[str] = Field(default_factory=list, description="Commit SHAs")
    status: str = Field(default="active", description="Branch status")


class PaginatedResult(BaseModel):
    """Paginated result wrapper"""
    items: List[Any] = Field(description="Items in current page")
    total: int = Field(description="Total number of items")
    page: int = Field(description="Current page number (1-indexed)")
    page_size: int = Field(description="Number of items per page")
    total_pages: int = Field(description="Total number of pages")
    
    @property
    def has_next(self) -> bool:
        """Check if there is a next page"""
        return self.page < self.total_pages
    
    @property
    def has_previous(self) -> bool:
        """Check if there is a previous page"""
        return self.page > 1


# ============================================================================
# Document Enhancement Chain Models
# ============================================================================

class ErrorHandling(str, Enum):
    """Error handling strategy for enhancement chain"""
    STOP = "stop"
    RETRY = "retry"
    SKIP = "skip"


class AgentConfig(BaseModel):
    """Configuration for a single agent in the enhancement chain"""
    agent_name: str = Field(description="Agent identifier (e.g., 'gpt4', 'claude')")
    step_name: str = Field(description="Step name (e.g., 'gpt4-enhancement')")
    order: int = Field(description="Position in chain (0-based)", ge=0)
    agent_instance: Any = Field(default=None, description="Agent instance (not serialized)")
    
    class Config:
        arbitrary_types_allowed = True
        
    @field_validator('agent_name')
    @classmethod
    def validate_agent_name(cls, v: str) -> str:
        """Validate agent name"""
        if not v or not v.strip():
            raise ValueError("Agent name cannot be empty")
        return v.strip()


class DocumentEnhancementConfig(BaseModel):
    """Configuration for document enhancement chain"""
    source_document: Path = Field(description="Path to source document")
    enhancement_instructions: Optional[str] = Field(
        default=None,
        description="Optional instructions for enhancement"
    )
    agents: List[AgentConfig] = Field(
        default_factory=list,
        description="List of agents in order"
    )
    output_path: Optional[Path] = Field(
        default=None,
        description="Path for final output"
    )
    save_intermediate: bool = Field(
        default=False,
        description="Save each agent's output"
    )
    on_error: ErrorHandling = Field(
        default=ErrorHandling.STOP,
        description="Error handling strategy"
    )
    
    class Config:
        arbitrary_types_allowed = True
        use_enum_values = True
    
    @field_validator('source_document')
    @classmethod
    def validate_source_document(cls, v: Path) -> Path:
        """Validate source document exists"""
        if not v.exists():
            raise ValueError(f"Source document does not exist: {v}")
        if not v.is_file():
            raise ValueError(f"Source document is not a file: {v}")
        return v
    
    @field_validator('agents')
    @classmethod
    def validate_agents(cls, v: List[AgentConfig]) -> List[AgentConfig]:
        """Validate agents list"""
        if not v:
            raise ValueError("At least one agent must be configured")
        # Check for duplicate orders
        orders = [agent.order for agent in v]
        if len(orders) != len(set(orders)):
            raise ValueError("Agent orders must be unique")
        return v


class EnhancementStepResult(BaseModel):
    """Result from a single enhancement step"""
    step_number: int = Field(description="Step number (1-based)", ge=1)
    agent_name: str = Field(description="Agent that performed this step")
    model: str = Field(description="Model used")
    input_document: str = Field(description="Document content before enhancement")
    output_document: str = Field(description="Document content after enhancement")
    response_time_ms: int = Field(description="Response time in milliseconds", ge=0)
    token_usage: Optional[TokenUsage] = Field(
        default=None,
        description="Token usage statistics"
    )
    success: bool = Field(description="Whether step succeeded")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of step completion"
    )
    intermediate_path: Optional[Path] = Field(
        default=None,
        description="Path to intermediate result file"
    )
    
    class Config:
        arbitrary_types_allowed = True


class DocumentEnhancementResult(BaseModel):
    """Complete result from enhancement chain"""
    config: DocumentEnhancementConfig = Field(description="Configuration used")
    steps: List[EnhancementStepResult] = Field(
        default_factory=list,
        description="Results from each step"
    )
    final_document: str = Field(description="Final enhanced document content")
    total_time_ms: int = Field(description="Total execution time in milliseconds", ge=0)
    total_tokens: int = Field(description="Total tokens used", ge=0)
    total_cost: float = Field(description="Total cost estimate", ge=0)
    success: bool = Field(description="Whether chain completed successfully")
    output_path: Optional[Path] = Field(
        default=None,
        description="Path where final document was saved"
    )
    chain_id: str = Field(description="Unique identifier for this chain run")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of chain completion"
    )
    
    class Config:
        arbitrary_types_allowed = True
    
    @property
    def steps_completed(self) -> int:
        """Number of successfully completed steps"""
        return sum(1 for step in self.steps if step.success)
    
    @property
    def steps_failed(self) -> int:
        """Number of failed steps"""
        return sum(1 for step in self.steps if not step.success)


# ============================================================================
# Job Queue Models
# ============================================================================

class JobStatus(str, Enum):
    """Job execution status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class PromptSpec(BaseModel):
    """Prompt specification for job files (embedded prompt definition)"""
    content: str = Field(description="Prompt content")
    version: str = Field(default="1.0.0", description="Version identifier (semver)")
    tags: List[str] = Field(default_factory=list, description="Categorization tags")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    @field_validator('content')
    @classmethod
    def validate_content(cls, v: str) -> str:
        """Validate prompt content"""
        if not v or not v.strip():
            raise ValueError("Prompt content cannot be empty")
        if len(v) > 1_000_000:  # 1MB limit
            raise ValueError("Prompt content exceeds maximum length of 1,000,000 characters")
        return v.strip()
    
    @field_validator('version')
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Validate semver format"""
        semver_pattern = r'^\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?(\+[a-zA-Z0-9.-]+)?$'
        if not re.match(semver_pattern, v):
            raise ValueError(
                f"Version '{v}' does not match semver format (e.g., '1.0.0', '1.0.0-alpha')"
            )
        return v


class JobFile(BaseModel):
    """Job file representation for queue processing"""
    job_id: str = Field(description="Unique job identifier")
    file_path: Optional[Path] = Field(default=None, description="Path to the job file")
    prompt: PromptSpec = Field(description="Embedded prompt specification")
    agents: List[str] = Field(
        default_factory=list,
        description="Agent names to run (empty = all configured agents)"
    )
    priority: int = Field(default=0, description="Job priority (higher = processed first)")
    status: JobStatus = Field(default=JobStatus.PENDING, description="Current job status")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Job creation timestamp"
    )
    started_at: Optional[datetime] = Field(default=None, description="Processing start time")
    completed_at: Optional[datetime] = Field(default=None, description="Processing completion time")
    response_ids: List[str] = Field(
        default_factory=list,
        description="IDs of agent responses generated"
    )
    error: Optional[str] = Field(default=None, description="Error message if failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional job metadata")
    
    class Config:
        arbitrary_types_allowed = True
        use_enum_values = True
    
    @property
    def processing_time_ms(self) -> Optional[int]:
        """Calculate processing time in milliseconds"""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return int(delta.total_seconds() * 1000)
        return None
    
    @property
    def is_pending(self) -> bool:
        """Check if job is pending"""
        return self.status == JobStatus.PENDING
    
    @property
    def is_completed(self) -> bool:
        """Check if job completed (success or failure)"""
        return self.status in (JobStatus.COMPLETED, JobStatus.FAILED)


class JobQueueConfig(BaseModel):
    """Configuration for job queue"""
    watch_folder: Path = Field(description="Folder to watch for job files")
    poll_interval_seconds: float = Field(
        default=5.0,
        description="Interval between folder scans in seconds",
        ge=0.5,
        le=300.0
    )
    max_concurrent_jobs: int = Field(
        default=1,
        description="Maximum concurrent jobs (1 = sequential)",
        ge=1,
        le=10
    )
    archive_completed: bool = Field(
        default=False,
        description="Move completed jobs to archive folder"
    )
    archive_folder: Optional[Path] = Field(
        default=None,
        description="Folder for archived completed jobs"
    )
    auto_start: bool = Field(
        default=False,
        description="Automatically start processing on queue initialization"
    )
    default_agents: List[str] = Field(
        default_factory=list,
        description="Default agents to use if job doesn't specify"
    )
    
    class Config:
        arbitrary_types_allowed = True
    
    @field_validator('watch_folder')
    @classmethod
    def validate_watch_folder(cls, v: Path) -> Path:
        """Ensure watch folder is a valid path (creates if needed during runtime)"""
        return Path(v)
    
    @model_validator(mode='after')
    def validate_archive_config(self) -> 'JobQueueConfig':
        """Validate archive configuration"""
        if self.archive_completed and not self.archive_folder:
            # Default archive folder inside watch folder
            self.archive_folder = self.watch_folder / "completed"
        return self


class JobResult(BaseModel):
    """Result/status tracking for a job (stored in .status.json)"""
    job_id: str = Field(description="Job identifier")
    status: JobStatus = Field(description="Current status")
    started_at: Optional[datetime] = Field(default=None, description="Processing start time")
    completed_at: Optional[datetime] = Field(default=None, description="Completion time")
    response_ids: List[str] = Field(
        default_factory=list,
        description="IDs of generated responses"
    )
    prompt_id: Optional[str] = Field(default=None, description="ID of created prompt")
    agents_run: List[str] = Field(
        default_factory=list,
        description="Agents that were run"
    )
    error: Optional[str] = Field(default=None, description="Error message if failed")
    
    class Config:
        use_enum_values = True
