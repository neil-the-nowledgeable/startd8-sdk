"""
Data models for cost tracking and budget management
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, ConfigDict, Field
from enum import Enum
import uuid


class CostPeriod(str, Enum):
    """Budget period types"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    TOTAL = "total"  # Lifetime


class UsageSource(str, Enum):
    """Source of LLM usage for tracking SDK vs external tools"""
    SDK = "sdk"              # StartD8 SDK programmatic calls
    EXTERNAL = "external"    # Manual external tool entry
    IMPORT = "import"        # Imported from external tool logs/exports


class PricingType(str, Enum):
    """Pricing model for external tools"""
    PER_TOKEN = "per_token"       # Pay per token (like API)
    SUBSCRIPTION = "subscription"  # Fixed monthly cost
    HYBRID = "hybrid"             # Subscription + per-token for overages


class ExternalTool(BaseModel):
    """
    Registry entry for an external AI tool.

    Used to track usage from tools outside the SDK like Claude Code,
    Cursor, GitHub Copilot, ChatGPT web interface, etc.
    """
    id: str = Field(description="Tool identifier (e.g., 'claude-code')")
    display_name: str = Field(description="Human-readable name")
    provider: str = Field(description="Provider (anthropic, openai, github, google, etc.)")
    default_model: Optional[str] = Field(
        default=None,
        description="Default model used by this tool"
    )
    pricing_type: PricingType = Field(
        default=PricingType.PER_TOKEN,
        description="How this tool is billed"
    )
    subscription_cost: Optional[float] = Field(
        default=None,
        description="Monthly subscription cost in USD (if subscription-based)"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Additional notes about this tool"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this tool was registered"
    )

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": "claude-code",
            "display_name": "Claude Code (CLI)",
            "provider": "anthropic",
            "default_model": "claude-sonnet-4-6",
            "pricing_type": "per_token",
            "subscription_cost": None,
            "notes": "Anthropic's official CLI tool"
        }
    })


class CostRecord(BaseModel):
    """
    Individual cost record for an API call or external tool usage.

    Stored for every agent call to enable historical analysis.
    Also supports tracking external tool usage (Claude Code, Cursor, etc.)
    via the source_type and tool_name fields.
    """
    id: str = Field(default_factory=lambda: f"cost-{uuid.uuid4().hex[:12]}")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # What was called
    agent_name: str = Field(description="Agent that made the call")
    model: str = Field(description="Model used")
    provider: str = Field(description="Provider (anthropic, openai, etc.)")

    # Token usage
    input_tokens: int = Field(description="Input tokens used (non-cached)")
    output_tokens: int = Field(description="Output tokens generated")
    total_tokens: int = Field(description="Total tokens")
    cache_creation_input_tokens: int = Field(
        default=0, description="Input tokens written to cache (billed at write multiplier)"
    )
    cache_read_input_tokens: int = Field(
        default=0, description="Input tokens read from cache (billed at read multiplier)"
    )

    # Cost breakdown
    input_cost: float = Field(description="Cost for input tokens (includes cache read/write cost)")
    output_cost: float = Field(description="Cost for output tokens")
    total_cost: float = Field(description="Total cost in USD")
    pricing_estimated: bool = Field(
        default=False,
        description="True when the rate used was a flagged estimate or fallback, not a confirmed published price",
    )

    # Source tracking (SDK vs external tools)
    source_type: UsageSource = Field(
        default=UsageSource.SDK,
        description="Source of this usage record (sdk, external, import)"
    )
    tool_name: Optional[str] = Field(
        default=None,
        description="External tool name (e.g., claude-code, cursor, copilot)"
    )
    task_description: Optional[str] = Field(
        default=None,
        description="Description of task performed (for external entries)"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session/conversation ID for grouping related usage"
    )

    # Attribution (for tracking by project/purpose)
    tags: List[str] = Field(default_factory=list, description="Cost attribution tags")
    project: Optional[str] = Field(default=None, description="Project identifier")
    prompt_id: Optional[str] = Field(default=None, description="Associated prompt ID")
    response_id: Optional[str] = Field(default=None, description="Associated response ID")
    pipeline_id: Optional[str] = Field(default=None, description="Pipeline ID if part of pipeline")
    job_id: Optional[str] = Field(default=None, description="Job ID if from queue")

    # Context
    correlation_id: Optional[str] = Field(default=None, description="For tracing")
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "id": "cost-abc123",
            "timestamp": "2025-12-09T10:30:00Z",
            "agent_name": "claude",
            "model": "claude-3-5-sonnet-20241022",
            "provider": "anthropic",
            "input_tokens": 1500,
            "output_tokens": 500,
            "total_tokens": 2000,
            "input_cost": 0.0045,
            "output_cost": 0.0075,
            "total_cost": 0.012,
            "tags": ["code-review", "backend"],
            "project": "my-app"
        }
    })


class Budget(BaseModel):
    """
    Budget configuration for cost limits.
    """
    id: str = Field(default_factory=lambda: f"budget-{uuid.uuid4().hex[:12]}")
    name: str = Field(description="Budget name")
    
    # Limits
    period: CostPeriod = Field(description="Budget period")
    limit_amount: float = Field(description="Maximum spend for period in USD")
    warning_threshold: float = Field(
        default=0.8, 
        description="Percentage at which to warn (0.0-1.0)"
    )
    
    # Behavior
    block_on_exceed: bool = Field(
        default=False, 
        description="Block API calls when budget exceeded"
    )
    
    # Scope (optional - for per-project/per-model budgets)
    scope_project: Optional[str] = Field(default=None, description="Apply to specific project")
    scope_model: Optional[str] = Field(default=None, description="Apply to specific model")
    scope_tags: List[str] = Field(default_factory=list, description="Apply to specific tags")
    
    # Status
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    def matches(self, record: CostRecord) -> bool:
        """Check if this budget applies to a cost record"""
        if self.scope_project and record.project != self.scope_project:
            return False
        if self.scope_model and record.model != self.scope_model:
            return False
        if self.scope_tags and not any(t in record.tags for t in self.scope_tags):
            return False
        return True


class BudgetStatus(BaseModel):
    """Current status of a budget"""
    budget: Budget
    current_spend: float = Field(description="Amount spent in current period")
    remaining: float = Field(description="Amount remaining")
    percentage_used: float = Field(description="Percentage of budget used")
    period_start: datetime = Field(description="Start of current period")
    period_end: datetime = Field(description="End of current period")
    is_exceeded: bool = Field(description="Whether budget is exceeded")
    is_warning: bool = Field(description="Whether at warning threshold")


class CostSummary(BaseModel):
    """Aggregated cost summary for reporting"""
    period_start: datetime
    period_end: datetime
    total_cost: float
    total_calls: int
    total_tokens: int
    
    # Breakdowns
    by_model: Dict[str, float] = Field(default_factory=dict)
    by_agent: Dict[str, float] = Field(default_factory=dict)
    by_provider: Dict[str, float] = Field(default_factory=dict)
    by_project: Dict[str, float] = Field(default_factory=dict)
    by_tag: Dict[str, float] = Field(default_factory=dict)
    by_day: Dict[str, float] = Field(default_factory=dict)  # ISO date -> cost
    
    # Efficiency metrics
    avg_cost_per_call: float = 0.0
    avg_tokens_per_call: float = 0.0
    avg_cost_per_1k_tokens: float = 0.0


class CostOptimization(BaseModel):
    """Cost optimization recommendation"""
    id: str = Field(default_factory=lambda: f"opt-{uuid.uuid4().hex[:12]}")
    title: str
    description: str
    potential_savings: float = Field(description="Estimated monthly savings in USD")
    effort: str = Field(description="low, medium, high")
    category: str = Field(description="model-selection, caching, prompt-optimization, etc.")

    # Supporting data
    current_cost: float
    optimized_cost: float
    affected_calls: int
    recommendation: str  # Specific action to take


# =============================================================================
# External Usage Comparison Models
# =============================================================================


class SourceUsageSummary(BaseModel):
    """Summary of usage for a specific source or tool"""
    source_type: UsageSource = Field(description="SDK, EXTERNAL, or IMPORT")
    tool_name: Optional[str] = Field(default=None, description="Tool name for external sources")
    total_cost: float = Field(description="Total cost in USD")
    total_tokens: int = Field(description="Total tokens used")
    total_calls: int = Field(description="Number of API calls / entries")
    avg_cost_per_call: float = Field(default=0.0, description="Average cost per call")
    avg_tokens_per_call: float = Field(default=0.0, description="Average tokens per call")
    avg_cost_per_1k_tokens: float = Field(default=0.0, description="Cost per 1K tokens")

    @classmethod
    def from_records(
        cls,
        records: List["CostRecord"],
        source_type: UsageSource,
        tool_name: Optional[str] = None
    ) -> "SourceUsageSummary":
        """Create summary from a list of cost records"""
        if not records:
            return cls(
                source_type=source_type,
                tool_name=tool_name,
                total_cost=0.0,
                total_tokens=0,
                total_calls=0,
            )

        total_cost = sum(r.total_cost for r in records)
        total_tokens = sum(r.total_tokens for r in records)
        total_calls = len(records)

        return cls(
            source_type=source_type,
            tool_name=tool_name,
            total_cost=total_cost,
            total_tokens=total_tokens,
            total_calls=total_calls,
            avg_cost_per_call=total_cost / total_calls if total_calls > 0 else 0.0,
            avg_tokens_per_call=total_tokens / total_calls if total_calls > 0 else 0.0,
            avg_cost_per_1k_tokens=(total_cost / total_tokens * 1000) if total_tokens > 0 else 0.0,
        )


class ToolComparisonReport(BaseModel):
    """Side-by-side comparison of SDK vs external tool usage"""
    period_start: datetime
    period_end: datetime

    # SDK usage summary
    sdk_usage: SourceUsageSummary

    # External tool usage (by tool_name)
    external_usage: Dict[str, SourceUsageSummary] = Field(
        default_factory=dict,
        description="External usage broken down by tool name"
    )

    # Totals
    total_cost: float = Field(description="Total cost across all sources")
    total_tokens: int = Field(description="Total tokens across all sources")
    total_calls: int = Field(description="Total calls across all sources")

    # Analysis
    most_cost_effective_tool: Optional[str] = Field(
        default=None,
        description="Tool with best cost per 1K tokens"
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="Cost optimization recommendations"
    )

    def get_all_sources(self) -> List[SourceUsageSummary]:
        """Get all usage summaries including SDK and external"""
        sources = [self.sdk_usage]
        sources.extend(self.external_usage.values())
        return sources


class ProductivityMetrics(BaseModel):
    """Productivity metrics comparing tools by task completion"""
    period_start: datetime
    period_end: datetime

    # Task-based metrics (requires task_description to be populated)
    tasks_completed: Dict[str, int] = Field(
        default_factory=dict,
        description="Number of tasks completed per tool"
    )
    avg_cost_per_task: Dict[str, float] = Field(
        default_factory=dict,
        description="Average cost per task per tool"
    )
    avg_tokens_per_task: Dict[str, int] = Field(
        default_factory=dict,
        description="Average tokens per task per tool"
    )

    # Session-based metrics (requires session_id to be populated)
    sessions_count: Dict[str, int] = Field(
        default_factory=dict,
        description="Number of sessions per tool"
    )
    avg_cost_per_session: Dict[str, float] = Field(
        default_factory=dict,
        description="Average cost per session per tool"
    )
