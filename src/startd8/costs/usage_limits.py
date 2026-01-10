"""
Usage limit tracking and monitoring for LLM API providers.

This module provides proactive monitoring of API usage limits to help
users avoid hitting rate limits and manage their API quotas effectively.

Main features:
- Track usage against known provider limits
- Warn when approaching thresholds (80%, 90%, 95%)
- Support for requests-per-minute and tokens-per-minute limits
- Historical usage analysis for trend detection
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
from collections import defaultdict

from .store import CostStore
from .models import CostRecord
from ..events import EventBus, Event, EventType, EventPriority
from ..logging_config import get_logger

logger = get_logger(__name__)


class LimitType(str, Enum):
    """Types of API limits"""
    REQUESTS_PER_MINUTE = "requests_per_minute"
    REQUESTS_PER_HOUR = "requests_per_hour"
    REQUESTS_PER_DAY = "requests_per_day"
    TOKENS_PER_MINUTE = "tokens_per_minute"
    TOKENS_PER_HOUR = "tokens_per_hour"
    TOKENS_PER_DAY = "tokens_per_day"


class UsageLevel(str, Enum):
    """Usage level indicators"""
    LOW = "low"           # 0-50%
    MODERATE = "moderate" # 50-80%
    HIGH = "high"         # 80-90%
    CRITICAL = "critical" # 90-95%
    EXCEEDED = "exceeded" # 95%+


@dataclass
class ProviderLimits:
    """
    Known limits for an API provider.
    
    These are default/typical limits - actual limits may vary by tier.
    """
    provider: str
    requests_per_minute: Optional[int] = None
    requests_per_hour: Optional[int] = None
    requests_per_day: Optional[int] = None
    tokens_per_minute: Optional[int] = None
    tokens_per_hour: Optional[int] = None
    tokens_per_day: Optional[int] = None
    
    # Notes about the limits
    notes: str = ""
    tier: str = "default"  # free, tier1, tier2, enterprise, etc.


@dataclass
class UsageLimitStatus:
    """
    Current usage status for a specific limit.
    """
    provider: str
    model: Optional[str]
    limit_type: LimitType
    
    # Current usage
    current_usage: int
    limit_value: int
    
    # Calculated fields
    usage_percentage: float
    remaining: int
    level: UsageLevel
    
    # Time window
    window_start: datetime
    window_end: datetime
    
    # Reset info
    resets_in_seconds: Optional[int] = None
    
    # Trend (increasing/decreasing/stable)
    trend: str = "stable"
    trend_percentage: float = 0.0
    
    @property
    def is_warning(self) -> bool:
        """Check if at warning threshold (80%+)"""
        return self.usage_percentage >= 80.0
    
    @property
    def is_critical(self) -> bool:
        """Check if at critical threshold (90%+)"""
        return self.usage_percentage >= 90.0
    
    @property
    def is_exceeded(self) -> bool:
        """Check if exceeded threshold (95%+)"""
        return self.usage_percentage >= 95.0


@dataclass
class UsageSummary:
    """
    Summary of usage across all providers and limits.
    """
    timestamp: datetime
    provider_statuses: Dict[str, List[UsageLimitStatus]] = field(default_factory=dict)
    warnings: List[UsageLimitStatus] = field(default_factory=list)
    critical: List[UsageLimitStatus] = field(default_factory=list)
    exceeded: List[UsageLimitStatus] = field(default_factory=list)
    
    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0
    
    @property
    def has_critical(self) -> bool:
        return len(self.critical) > 0
    
    @property
    def has_exceeded(self) -> bool:
        return len(self.exceeded) > 0
    
    @property
    def overall_status(self) -> UsageLevel:
        """Get overall status across all limits"""
        if self.has_exceeded:
            return UsageLevel.EXCEEDED
        elif self.has_critical:
            return UsageLevel.CRITICAL
        elif self.has_warnings:
            return UsageLevel.HIGH
        return UsageLevel.LOW


# Default provider limits (typical free/starter tier limits)
DEFAULT_PROVIDER_LIMITS: Dict[str, ProviderLimits] = {
    "anthropic": ProviderLimits(
        provider="anthropic",
        requests_per_minute=50,
        tokens_per_minute=40000,
        tokens_per_day=1000000,
        notes="Anthropic default tier limits. Higher tiers have increased limits.",
        tier="tier1"
    ),
    "openai": ProviderLimits(
        provider="openai",
        requests_per_minute=60,
        tokens_per_minute=90000,
        requests_per_day=10000,
        notes="OpenAI free tier limits. Paid tiers have significantly higher limits.",
        tier="free"
    ),
    "google": ProviderLimits(
        provider="google",
        requests_per_minute=15,
        tokens_per_minute=32000,
        requests_per_day=1500,
        notes="Gemini API free tier limits. Pro tier has higher limits.",
        tier="free"
    ),
}


class UsageLimitChecker:
    """
    Checks and monitors API usage against known limits.
    
    This service analyzes recent API usage from the cost tracking store
    and compares it against provider limits to provide warnings before
    hitting rate limits.
    
    Example:
        checker = UsageLimitChecker(cost_store)
        
        # Check all limits
        summary = checker.check_all_limits()
        if summary.has_warnings:
            for warning in summary.warnings:
                print(f"Warning: {warning.provider} {warning.limit_type.value} at {warning.usage_percentage:.1f}%")
        
        # Check specific provider
        status = checker.check_provider("anthropic")
        for limit_status in status:
            print(f"{limit_status.limit_type.value}: {limit_status.current_usage}/{limit_status.limit_value}")
    """
    
    def __init__(
        self,
        store: CostStore,
        custom_limits: Optional[Dict[str, ProviderLimits]] = None,
        warning_threshold: float = 80.0,
        critical_threshold: float = 90.0,
        exceeded_threshold: float = 95.0
    ):
        """
        Initialize usage limit checker.
        
        Args:
            store: CostStore for querying usage history
            custom_limits: Optional custom provider limits (overrides defaults)
            warning_threshold: Percentage threshold for warnings (default 80%)
            critical_threshold: Percentage threshold for critical (default 90%)
            exceeded_threshold: Percentage threshold for exceeded (default 95%)
        """
        self.store = store
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold
        self.exceeded_threshold = exceeded_threshold
        
        # Merge custom limits with defaults
        self.provider_limits = DEFAULT_PROVIDER_LIMITS.copy()
        if custom_limits:
            self.provider_limits.update(custom_limits)
        
        logger.info("Initialized UsageLimitChecker", extra={
            "providers": list(self.provider_limits.keys()),
            "warning_threshold": warning_threshold,
            "critical_threshold": critical_threshold
        })
    
    def set_provider_limits(self, provider: str, limits: ProviderLimits) -> None:
        """
        Set or update limits for a specific provider.
        
        Args:
            provider: Provider name (e.g., "anthropic", "openai")
            limits: ProviderLimits configuration
        """
        self.provider_limits[provider] = limits
        logger.info(f"Updated limits for provider: {provider}", extra={
            "provider": provider,
            "limits": {
                "requests_per_minute": limits.requests_per_minute,
                "tokens_per_minute": limits.tokens_per_minute
            }
        })
    
    def check_all_limits(self, auto_pause_handler: Optional[Any] = None) -> UsageSummary:
        """
        Check usage against all configured provider limits.
        
        Args:
            auto_pause_handler: Optional AutoPauseHandler instance for auto-resume
        
        Returns:
            UsageSummary with status for all providers and any warnings
        """
        now = datetime.now(timezone.utc)
        summary = UsageSummary(timestamp=now)
        
        for provider in self.provider_limits.keys():
            statuses = self.check_provider(provider)
            summary.provider_statuses[provider] = statuses
            
            # Categorize by severity
            for status in statuses:
                if status.is_exceeded:
                    summary.exceeded.append(status)
                elif status.is_critical:
                    summary.critical.append(status)
                elif status.is_warning:
                    summary.warnings.append(status)
        
        # Emit events for warnings
        self._emit_usage_events(summary)
        
        # Check if any auto-paused agents can be resumed
        if auto_pause_handler is not None:
            try:
                resumed = auto_pause_handler.check_and_resume(summary)
                if resumed:
                    logger.info(f"Auto-resumed {len(resumed)} agents: {resumed}")
            except Exception as e:
                logger.error(f"Error during auto-resume check: {e}", exc_info=True)
        
        return summary
    
    def check_provider(
        self,
        provider: str,
        model: Optional[str] = None
    ) -> List[UsageLimitStatus]:
        """
        Check usage for a specific provider.
        
        Args:
            provider: Provider name
            model: Optional model filter
            
        Returns:
            List of UsageLimitStatus for each limit type
        """
        limits = self.provider_limits.get(provider)
        if not limits:
            logger.warning(f"No limits configured for provider: {provider}")
            return []
        
        statuses = []
        now = datetime.now(timezone.utc)
        
        # Check requests per minute
        if limits.requests_per_minute:
            status = self._check_limit(
                provider=provider,
                model=model,
                limit_type=LimitType.REQUESTS_PER_MINUTE,
                limit_value=limits.requests_per_minute,
                window_minutes=1
            )
            statuses.append(status)
        
        # Check requests per hour
        if limits.requests_per_hour:
            status = self._check_limit(
                provider=provider,
                model=model,
                limit_type=LimitType.REQUESTS_PER_HOUR,
                limit_value=limits.requests_per_hour,
                window_minutes=60
            )
            statuses.append(status)
        
        # Check requests per day
        if limits.requests_per_day:
            status = self._check_limit(
                provider=provider,
                model=model,
                limit_type=LimitType.REQUESTS_PER_DAY,
                limit_value=limits.requests_per_day,
                window_minutes=1440
            )
            statuses.append(status)
        
        # Check tokens per minute
        if limits.tokens_per_minute:
            status = self._check_token_limit(
                provider=provider,
                model=model,
                limit_type=LimitType.TOKENS_PER_MINUTE,
                limit_value=limits.tokens_per_minute,
                window_minutes=1
            )
            statuses.append(status)
        
        # Check tokens per hour
        if limits.tokens_per_hour:
            status = self._check_token_limit(
                provider=provider,
                model=model,
                limit_type=LimitType.TOKENS_PER_HOUR,
                limit_value=limits.tokens_per_hour,
                window_minutes=60
            )
            statuses.append(status)
        
        # Check tokens per day
        if limits.tokens_per_day:
            status = self._check_token_limit(
                provider=provider,
                model=model,
                limit_type=LimitType.TOKENS_PER_DAY,
                limit_value=limits.tokens_per_day,
                window_minutes=1440
            )
            statuses.append(status)
        
        return statuses
    
    def _check_limit(
        self,
        provider: str,
        model: Optional[str],
        limit_type: LimitType,
        limit_value: int,
        window_minutes: int
    ) -> UsageLimitStatus:
        """Check request count limit"""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=window_minutes)
        window_end = now
        
        # Query records in window
        records = self._get_records_for_provider(
            provider=provider,
            model=model,
            start=window_start,
            end=window_end
        )
        
        current_usage = len(records)
        usage_percentage = (current_usage / limit_value * 100) if limit_value > 0 else 0
        remaining = max(0, limit_value - current_usage)
        
        # Calculate trend
        trend, trend_pct = self._calculate_trend(
            provider=provider,
            model=model,
            window_minutes=window_minutes,
            count_type="requests"
        )
        
        return UsageLimitStatus(
            provider=provider,
            model=model,
            limit_type=limit_type,
            current_usage=current_usage,
            limit_value=limit_value,
            usage_percentage=usage_percentage,
            remaining=remaining,
            level=self._get_usage_level(usage_percentage),
            window_start=window_start,
            window_end=window_end,
            resets_in_seconds=window_minutes * 60,
            trend=trend,
            trend_percentage=trend_pct
        )
    
    def _check_token_limit(
        self,
        provider: str,
        model: Optional[str],
        limit_type: LimitType,
        limit_value: int,
        window_minutes: int
    ) -> UsageLimitStatus:
        """Check token usage limit"""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(minutes=window_minutes)
        window_end = now
        
        # Query records in window
        records = self._get_records_for_provider(
            provider=provider,
            model=model,
            start=window_start,
            end=window_end
        )
        
        current_usage = sum(r.total_tokens for r in records)
        usage_percentage = (current_usage / limit_value * 100) if limit_value > 0 else 0
        remaining = max(0, limit_value - current_usage)
        
        # Calculate trend
        trend, trend_pct = self._calculate_trend(
            provider=provider,
            model=model,
            window_minutes=window_minutes,
            count_type="tokens"
        )
        
        return UsageLimitStatus(
            provider=provider,
            model=model,
            limit_type=limit_type,
            current_usage=current_usage,
            limit_value=limit_value,
            usage_percentage=usage_percentage,
            remaining=remaining,
            level=self._get_usage_level(usage_percentage),
            window_start=window_start,
            window_end=window_end,
            resets_in_seconds=window_minutes * 60,
            trend=trend,
            trend_percentage=trend_pct
        )
    
    def _get_records_for_provider(
        self,
        provider: str,
        model: Optional[str],
        start: datetime,
        end: datetime
    ) -> List[CostRecord]:
        """Get cost records for a provider in a time window"""
        # Query all records in the time window
        records = self.store.query(start=start, end=end)
        
        # Filter by provider
        filtered = [r for r in records if r.provider.lower() == provider.lower()]
        
        # Filter by model if specified
        if model:
            filtered = [r for r in filtered if r.model == model]
        
        return filtered
    
    def _calculate_trend(
        self,
        provider: str,
        model: Optional[str],
        window_minutes: int,
        count_type: str
    ) -> tuple[str, float]:
        """
        Calculate usage trend by comparing current window to previous window.
        
        Returns:
            Tuple of (trend_direction, trend_percentage)
        """
        now = datetime.now(timezone.utc)
        
        # Current window
        current_start = now - timedelta(minutes=window_minutes)
        current_records = self._get_records_for_provider(
            provider=provider,
            model=model,
            start=current_start,
            end=now
        )
        
        # Previous window
        prev_start = now - timedelta(minutes=window_minutes * 2)
        prev_end = now - timedelta(minutes=window_minutes)
        prev_records = self._get_records_for_provider(
            provider=provider,
            model=model,
            start=prev_start,
            end=prev_end
        )
        
        # Calculate counts
        if count_type == "tokens":
            current_count = sum(r.total_tokens for r in current_records)
            prev_count = sum(r.total_tokens for r in prev_records)
        else:
            current_count = len(current_records)
            prev_count = len(prev_records)
        
        # Calculate trend
        if prev_count == 0:
            if current_count > 0:
                return "increasing", 100.0
            return "stable", 0.0
        
        trend_pct = ((current_count - prev_count) / prev_count) * 100
        
        if trend_pct > 10:
            return "increasing", trend_pct
        elif trend_pct < -10:
            return "decreasing", trend_pct
        return "stable", trend_pct
    
    def _get_usage_level(self, percentage: float) -> UsageLevel:
        """Determine usage level from percentage"""
        if percentage >= self.exceeded_threshold:
            return UsageLevel.EXCEEDED
        elif percentage >= self.critical_threshold:
            return UsageLevel.CRITICAL
        elif percentage >= self.warning_threshold:
            return UsageLevel.HIGH
        elif percentage >= 50:
            return UsageLevel.MODERATE
        return UsageLevel.LOW
    
    def _emit_usage_events(self, summary: UsageSummary) -> None:
        """Emit events for usage warnings"""
        for status in summary.exceeded:
            EventBus.emit(Event(
                type=EventType.USAGE_LIMIT_EXCEEDED,
                source="UsageLimitChecker",
                priority=EventPriority.CRITICAL,
                data={
                    "provider": status.provider,
                    "model": status.model,
                    "limit_type": status.limit_type.value,
                    "usage_percentage": status.usage_percentage,
                    "current_usage": status.current_usage,
                    "limit_value": status.limit_value,
                    "remaining": status.remaining,
                    "resets_in_seconds": status.resets_in_seconds
                }
            ))
        
        for status in summary.critical:
            EventBus.emit(Event(
                type=EventType.USAGE_LIMIT_CRITICAL,
                source="UsageLimitChecker",
                priority=EventPriority.HIGH,
                data={
                    "provider": status.provider,
                    "model": status.model,
                    "limit_type": status.limit_type.value,
                    "usage_percentage": status.usage_percentage,
                    "current_usage": status.current_usage,
                    "limit_value": status.limit_value,
                    "remaining": status.remaining,
                    "resets_in_seconds": status.resets_in_seconds
                }
            ))
        
        for status in summary.warnings:
            EventBus.emit(Event(
                type=EventType.USAGE_LIMIT_WARNING,
                source="UsageLimitChecker",
                priority=EventPriority.NORMAL,
                data={
                    "provider": status.provider,
                    "model": status.model,
                    "limit_type": status.limit_type.value,
                    "usage_percentage": status.usage_percentage,
                    "current_usage": status.current_usage,
                    "limit_value": status.limit_value,
                    "remaining": status.remaining,
                    "resets_in_seconds": status.resets_in_seconds
                }
            ))
    
    def get_recommendations(self, summary: UsageSummary) -> List[str]:
        """
        Get recommendations based on usage summary.
        
        Args:
            summary: UsageSummary from check_all_limits()
            
        Returns:
            List of recommendation strings
        """
        recommendations = []
        
        if summary.has_exceeded:
            for status in summary.exceeded:
                recommendations.append(
                    f"⛔ {status.provider.upper()} {status.limit_type.value} EXCEEDED ({status.usage_percentage:.1f}%): "
                    f"Consider waiting {status.resets_in_seconds // 60} minutes for limit reset, "
                    f"or switch to a different provider/model."
                )
        
        if summary.has_critical:
            for status in summary.critical:
                recommendations.append(
                    f"🔴 {status.provider.upper()} {status.limit_type.value} CRITICAL ({status.usage_percentage:.1f}%): "
                    f"Slow down requests or prepare to switch providers. "
                    f"Resets in ~{status.resets_in_seconds // 60} minutes."
                )
        
        if summary.has_warnings:
            for status in summary.warnings:
                recommendations.append(
                    f"🟡 {status.provider.upper()} {status.limit_type.value} HIGH ({status.usage_percentage:.1f}%): "
                    f"Monitor usage closely. {status.remaining} remaining in current window."
                )
        
        # Add general recommendations
        if summary.has_warnings or summary.has_critical:
            recommendations.append(
                "💡 TIP: Consider implementing caching for repeated prompts to reduce API calls."
            )
            recommendations.append(
                "💡 TIP: Use smaller models (e.g., claude-3-5-haiku, gpt-4o-mini) for simpler tasks."
            )
        
        return recommendations
    
    def format_status_table(self, summary: UsageSummary) -> str:
        """
        Format usage summary as a text table for display.
        
        Args:
            summary: UsageSummary from check_all_limits()
            
        Returns:
            Formatted table string
        """
        lines = []
        lines.append("=" * 80)
        lines.append("USAGE LIMIT STATUS")
        lines.append("=" * 80)
        lines.append(f"Checked at: {summary.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(f"Overall Status: {summary.overall_status.value.upper()}")
        lines.append("-" * 80)
        
        for provider, statuses in summary.provider_statuses.items():
            lines.append(f"\n📊 {provider.upper()}")
            lines.append("-" * 40)
            
            for status in statuses:
                # Status indicator
                if status.is_exceeded:
                    indicator = "⛔"
                elif status.is_critical:
                    indicator = "🔴"
                elif status.is_warning:
                    indicator = "🟡"
                else:
                    indicator = "🟢"
                
                # Format limit type nicely
                limit_name = status.limit_type.value.replace("_", " ").title()
                
                # Progress bar
                bar_width = 20
                filled = int(status.usage_percentage / 100 * bar_width)
                bar = "█" * filled + "░" * (bar_width - filled)
                
                lines.append(
                    f"  {indicator} {limit_name}: [{bar}] "
                    f"{status.current_usage:,}/{status.limit_value:,} "
                    f"({status.usage_percentage:.1f}%)"
                )
                
                if status.trend != "stable":
                    trend_arrow = "↑" if status.trend == "increasing" else "↓"
                    lines.append(f"     Trend: {trend_arrow} {abs(status.trend_percentage):.1f}%")
        
        lines.append("\n" + "=" * 80)
        
        return "\n".join(lines)

