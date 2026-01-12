"""
External Usage Tracker for tracking LLM usage from non-SDK sources.

This module provides utilities for recording and tracking LLM usage from
external tools like Claude Code, Cursor, GitHub Copilot, ChatGPT web, etc.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from .models import (
    CostRecord,
    ExternalTool,
    PricingType,
    UsageSource,
)
from .store import CostStore
from .pricing import PricingService
from ..logging_config import get_logger

logger = get_logger(__name__)


# =============================================================================
# Default External Tools Registry
# =============================================================================

DEFAULT_TOOLS: List[ExternalTool] = [
    ExternalTool(
        id="claude-code",
        display_name="Claude Code (CLI)",
        provider="anthropic",
        default_model="claude-sonnet-4-20250514",
        pricing_type=PricingType.PER_TOKEN,
        subscription_cost=None,
        notes="Anthropic's official CLI tool for developers. Uses API pricing.",
    ),
    ExternalTool(
        id="cursor",
        display_name="Cursor IDE",
        provider="openai",
        default_model="gpt-4o",
        pricing_type=PricingType.SUBSCRIPTION,
        subscription_cost=20.0,
        notes="AI-first code editor with $20/month Pro subscription.",
    ),
    ExternalTool(
        id="copilot",
        display_name="GitHub Copilot",
        provider="github",
        default_model="codex",
        pricing_type=PricingType.SUBSCRIPTION,
        subscription_cost=10.0,
        notes="GitHub's AI pair programmer. $10/month individual plan.",
    ),
    ExternalTool(
        id="chatgpt-web",
        display_name="ChatGPT (Web)",
        provider="openai",
        default_model="gpt-4o",
        pricing_type=PricingType.HYBRID,
        subscription_cost=20.0,
        notes="ChatGPT Plus subscription with usage limits, then per-token.",
    ),
    ExternalTool(
        id="claude-web",
        display_name="Claude (Web)",
        provider="anthropic",
        default_model="claude-sonnet-4-20250514",
        pricing_type=PricingType.SUBSCRIPTION,
        subscription_cost=20.0,
        notes="Claude Pro subscription at claude.ai.",
    ),
    ExternalTool(
        id="gemini-web",
        display_name="Gemini (Web)",
        provider="google",
        default_model="gemini-2.0-flash",
        pricing_type=PricingType.SUBSCRIPTION,
        subscription_cost=20.0,
        notes="Google Gemini Advanced subscription.",
    ),
    ExternalTool(
        id="windsurf",
        display_name="Windsurf (Codeium)",
        provider="codeium",
        default_model="cascade",
        pricing_type=PricingType.SUBSCRIPTION,
        subscription_cost=15.0,
        notes="Codeium's AI-powered IDE. $15/month Pro subscription.",
    ),
    ExternalTool(
        id="aider",
        display_name="Aider",
        provider="multi",
        default_model="claude-sonnet-4-20250514",
        pricing_type=PricingType.PER_TOKEN,
        subscription_cost=None,
        notes="AI pair programming in terminal. Uses your own API keys.",
    ),
]


class ExternalUsageTracker:
    """
    Service for tracking LLM usage from external tools.

    This class provides methods to:
    - Record manual usage entries from external tools
    - Estimate costs for subscription-based tools
    - Manage the external tools registry
    - Query and analyze external usage data

    Example:
        tracker = ExternalUsageTracker(store)

        # Record usage from Claude Code
        record = tracker.record_external_usage(
            tool_name="claude-code",
            input_tokens=5000,
            output_tokens=2000,
            task_description="Refactored authentication module",
            project="my-app"
        )

        # Estimate subscription cost allocation
        cost = tracker.estimate_subscription_cost("cursor", usage_hours=4.5)

        # Get available tools
        tools = tracker.list_tools()
    """

    def __init__(
        self,
        store: CostStore,
        pricing_service: Optional[PricingService] = None,
        auto_register_defaults: bool = True,
    ):
        """
        Initialize the external usage tracker.

        Args:
            store: CostStore for persisting records
            pricing_service: Optional PricingService for cost calculation
            auto_register_defaults: If True, register default tools on init
        """
        self.store = store
        self.pricing_service = pricing_service or PricingService()

        if auto_register_defaults:
            self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register default external tools if not already present."""
        existing_tools = {t.id for t in self.store.list_external_tools()}

        for tool in DEFAULT_TOOLS:
            if tool.id not in existing_tools:
                self.store.save_external_tool(tool)
                logger.debug(f"Registered default tool: {tool.id}")

    def record_external_usage(
        self,
        tool_name: str,
        model: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        total_cost: Optional[float] = None,
        task_description: Optional[str] = None,
        session_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        project: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        source_type: UsageSource = UsageSource.EXTERNAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> CostRecord:
        """
        Record usage from an external tool.

        You can provide either token counts (for per-token tools) or
        total_cost directly (for subscription-based estimates).

        Args:
            tool_name: External tool identifier (e.g., 'claude-code', 'cursor')
            model: Model used (defaults to tool's default_model)
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated
            total_cost: Total cost in USD (calculated if not provided)
            task_description: Description of what was accomplished
            session_id: Session or conversation identifier
            tags: Tags for cost attribution
            project: Project identifier
            timestamp: When the usage occurred (defaults to now)
            source_type: Usage source type (defaults to EXTERNAL)
            metadata: Additional metadata

        Returns:
            The created CostRecord

        Raises:
            ValueError: If tool_name is not registered and no model provided

        Example:
            # Per-token usage (like Claude Code)
            record = tracker.record_external_usage(
                tool_name="claude-code",
                input_tokens=5000,
                output_tokens=2000,
                task_description="Fixed authentication bug"
            )

            # Subscription-based usage (estimated cost)
            record = tracker.record_external_usage(
                tool_name="cursor",
                total_cost=2.50,  # Estimated based on time
                task_description="Built new feature",
                session_id="session-123"
            )
        """
        # Get tool info for defaults
        tool = self.store.get_external_tool(tool_name)

        # Resolve model
        if not model:
            if tool:
                model = tool.default_model or "unknown"
            else:
                model = "unknown"

        # Resolve provider
        provider = tool.provider if tool else "unknown"

        # Handle tokens
        input_tokens = input_tokens or 0
        output_tokens = output_tokens or 0
        total_tokens = input_tokens + output_tokens

        # Calculate costs
        if total_cost is not None:
            # Use provided total cost, estimate split
            if total_tokens > 0:
                ratio = input_tokens / total_tokens if total_tokens > 0 else 0.6
                input_cost = total_cost * ratio
                output_cost = total_cost * (1 - ratio)
            else:
                input_cost = total_cost * 0.6  # Typical ratio
                output_cost = total_cost * 0.4
        else:
            # Calculate from tokens using pricing service
            try:
                input_cost = self.pricing_service.calculate_input_cost(
                    model, input_tokens
                )
                output_cost = self.pricing_service.calculate_output_cost(
                    model, output_tokens
                )
                total_cost = input_cost + output_cost
            except Exception as e:
                logger.warning(f"Could not calculate cost for model {model}: {e}")
                input_cost = 0.0
                output_cost = 0.0
                total_cost = 0.0

        # Create the record
        record = CostRecord(
            id=f"ext-{uuid.uuid4().hex[:12]}",
            timestamp=timestamp or datetime.now(timezone.utc),
            agent_name=f"external:{tool_name}",
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
            source_type=source_type,
            tool_name=tool_name,
            task_description=task_description,
            session_id=session_id,
            tags=tags or [],
            project=project,
            metadata=metadata or {},
        )

        # Save to store
        self.store.save(record)
        logger.info(
            f"Recorded external usage: {tool_name}, tokens={total_tokens}, cost=${total_cost:.4f}"
        )

        return record

    def estimate_subscription_cost(
        self,
        tool_name: str,
        usage_hours: Optional[float] = None,
        usage_minutes: Optional[float] = None,
        total_monthly_hours: float = 160.0,
    ) -> float:
        """
        Estimate cost allocation for subscription-based tools.

        For tools with fixed monthly subscriptions, this estimates
        a proportional cost based on usage time.

        Args:
            tool_name: Tool identifier
            usage_hours: Hours of usage
            usage_minutes: Minutes of usage (alternative to hours)
            total_monthly_hours: Total work hours per month for cost basis

        Returns:
            Estimated cost in USD

        Example:
            # Estimate Cursor cost for 2 hours of usage
            cost = tracker.estimate_subscription_cost("cursor", usage_hours=2)
            # If Cursor is $20/month and 160 work hours/month:
            # cost = $20 * (2/160) = $0.25
        """
        tool = self.store.get_external_tool(tool_name)

        if not tool:
            logger.warning(f"Tool not found: {tool_name}")
            return 0.0

        if tool.pricing_type == PricingType.PER_TOKEN:
            logger.warning(f"Tool {tool_name} uses per-token pricing, not subscription")
            return 0.0

        subscription_cost = tool.subscription_cost or 0.0

        # Convert to hours
        hours = usage_hours or 0.0
        if usage_minutes:
            hours += usage_minutes / 60.0

        if hours <= 0:
            return 0.0

        # Calculate proportional cost
        hourly_rate = subscription_cost / total_monthly_hours
        estimated_cost = hourly_rate * hours

        return round(estimated_cost, 4)

    def register_tool(self, tool: ExternalTool) -> None:
        """
        Register a new external tool.

        Args:
            tool: ExternalTool to register

        Example:
            tracker.register_tool(ExternalTool(
                id="my-custom-tool",
                display_name="My Custom AI Tool",
                provider="custom",
                pricing_type=PricingType.SUBSCRIPTION,
                subscription_cost=15.0
            ))
        """
        self.store.save_external_tool(tool)
        logger.info(f"Registered external tool: {tool.id}")

    def unregister_tool(self, tool_id: str) -> bool:
        """
        Remove a tool from the registry.

        Args:
            tool_id: Tool identifier to remove

        Returns:
            True if removed, False if not found
        """
        return self.store.delete_external_tool(tool_id)

    def get_tool(self, tool_id: str) -> Optional[ExternalTool]:
        """
        Get tool details by ID.

        Args:
            tool_id: Tool identifier

        Returns:
            ExternalTool or None if not found
        """
        return self.store.get_external_tool(tool_id)

    def list_tools(self) -> List[ExternalTool]:
        """
        List all registered external tools.

        Returns:
            List of ExternalTool objects
        """
        return self.store.list_external_tools()

    def get_tool_usage(
        self,
        tool_name: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        project: Optional[str] = None,
    ) -> List[CostRecord]:
        """
        Get usage records for a specific tool.

        Args:
            tool_name: Tool identifier
            start: Start datetime
            end: End datetime
            project: Optional project filter

        Returns:
            List of CostRecord objects for the tool
        """
        return self.store.query_by_source(
            source_type=UsageSource.EXTERNAL,
            tool_name=tool_name,
            start=start,
            end=end,
            project=project,
        )

    def get_all_external_usage(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        project: Optional[str] = None,
    ) -> List[CostRecord]:
        """
        Get all external usage records.

        Args:
            start: Start datetime
            end: End datetime
            project: Optional project filter

        Returns:
            List of all external CostRecord objects
        """
        return self.store.query_by_source(
            source_type=UsageSource.EXTERNAL,
            start=start,
            end=end,
            project=project,
        )

    def get_sdk_usage(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        project: Optional[str] = None,
    ) -> List[CostRecord]:
        """
        Get SDK usage records for comparison.

        Args:
            start: Start datetime
            end: End datetime
            project: Optional project filter

        Returns:
            List of SDK CostRecord objects
        """
        return self.store.query_by_source(
            source_type=UsageSource.SDK,
            start=start,
            end=end,
            project=project,
        )
