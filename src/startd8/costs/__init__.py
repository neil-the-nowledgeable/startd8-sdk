"""
Cost tracking and budget management for StartD8 SDK

This module provides comprehensive cost tracking, budget management,
and optimization recommendations for LLM API usage.

Main components:
- CostTracker: Record and track costs for API calls
- BudgetManager: Set and enforce spending limits
- PricingService: Manage model pricing
- CostAnalytics: Analyze spending and generate recommendations
- Cost Context: Manage tracking context for cost attribution
- ExternalUsageTracker: Track usage from external tools (Claude Code, Cursor, etc.)
- ComparisonAnalytics: Compare SDK vs external tool usage
"""

from .models import (
    CostRecord,
    Budget,
    BudgetStatus,
    CostSummary,
    CostOptimization,
    CostPeriod,
    # External tracking models
    UsageSource,
    PricingType,
    ExternalTool,
    SourceUsageSummary,
    ToolComparisonReport,
    ProductivityMetrics,
)
from .tracker import (
    CostTracker,
    get_cost_context,
    set_cost_context,
    clear_cost_context
)
from .budget import BudgetManager, BudgetExceededError
from .pricing import PricingService, ModelPricing
from .analytics import CostAnalytics
from .external import ExternalUsageTracker, DEFAULT_TOOLS
from .comparison import ComparisonAnalytics

__all__ = [
    # Models
    "CostRecord",
    "Budget",
    "BudgetStatus",
    "CostSummary",
    "CostOptimization",
    "CostPeriod",

    # External tracking models
    "UsageSource",
    "PricingType",
    "ExternalTool",
    "SourceUsageSummary",
    "ToolComparisonReport",
    "ProductivityMetrics",

    # Services
    "CostTracker",
    "BudgetManager",
    "PricingService",
    "CostAnalytics",
    "ExternalUsageTracker",
    "ComparisonAnalytics",

    # Context management (Issue #3)
    "get_cost_context",
    "set_cost_context",
    "clear_cost_context",

    # Exceptions
    "BudgetExceededError",

    # Additional exports
    "ModelPricing",
    "DEFAULT_TOOLS",
]
