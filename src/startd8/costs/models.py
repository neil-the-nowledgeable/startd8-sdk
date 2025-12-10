"""
Data models for cost tracking and budget management
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum
import uuid


class CostPeriod(str, Enum):
    """Budget period types"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    TOTAL = "total"  # Lifetime


class CostRecord(BaseModel):
    """
    Individual cost record for an API call.
    
    Stored for every agent call to enable historical analysis.
    """
    id: str = Field(default_factory=lambda: f"cost-{uuid.uuid4().hex[:12]}")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # What was called
    agent_name: str = Field(description="Agent that made the call")
    model: str = Field(description="Model used")
    provider: str = Field(description="Provider (anthropic, openai, etc.)")
    
    # Token usage
    input_tokens: int = Field(description="Input tokens used")
    output_tokens: int = Field(description="Output tokens generated")
    total_tokens: int = Field(description="Total tokens")
    
    # Cost breakdown
    input_cost: float = Field(description="Cost for input tokens")
    output_cost: float = Field(description="Cost for output tokens")
    total_cost: float = Field(description="Total cost in USD")
    
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
    
    class Config:
        json_schema_extra = {
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
        }


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
