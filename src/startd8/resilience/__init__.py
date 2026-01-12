"""
Startd8 Resilience Configuration.

Unified configuration for all self-healing and resilience capabilities:
- Retry behavior for transient failures
- Circuit breaker for cascading failure prevention
- Error handling strategies for workflows
- Self-diagnostics and auto-fix controls

Example:
    from startd8.resilience import ResilienceConfig, ResilienceLevel

    # Use preset level
    config = ResilienceConfig.from_level(ResilienceLevel.STANDARD)

    # Or customize
    config = ResilienceConfig(
        enabled=True,
        retry=RetrySettings(enabled=True, max_attempts=3),
        circuit_breaker=CircuitBreakerSettings(enabled=True),
        auto_fix=AutoFixSettings(enabled=True, safe_only=True),
    )
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple, Type


class ResilienceLevel(str, Enum):
    """Preset resilience levels for quick configuration."""
    OFF = "off"              # No resilience features
    MINIMAL = "minimal"      # Basic retry only
    STANDARD = "standard"    # Retry + circuit breaker (recommended)
    AGGRESSIVE = "aggressive"  # All features, more retries
    CUSTOM = "custom"        # Fully customized


class ErrorStrategy(str, Enum):
    """Strategy for handling errors in workflows."""
    STOP = "stop"            # Stop workflow on first error
    RETRY = "retry"          # Retry failed step
    SKIP = "skip"            # Skip failed step, continue workflow
    FALLBACK = "fallback"    # Use fallback agent/response


@dataclass
class RetrySettings:
    """Configuration for retry behavior."""
    enabled: bool = True
    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_factor: float = 0.1
    retryable_status_codes: Tuple[int, ...] = (429, 500, 502, 503, 504, 529)

    def __post_init__(self):
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds must be non-negative")

    def to_retry_config(self):
        """Convert to utils.retry.RetryConfig."""
        from ..utils.retry import RetryConfig
        return RetryConfig(
            max_attempts=self.max_attempts,
            base_delay=self.base_delay_seconds,
            max_delay=self.max_delay_seconds,
            exponential_base=self.exponential_base,
            jitter=self.jitter,
            jitter_factor=self.jitter_factor,
            retryable_status_codes=self.retryable_status_codes,
        )


@dataclass
class CircuitBreakerSettings:
    """Configuration for circuit breaker behavior."""
    enabled: bool = True
    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    half_open_max_requests: int = 3

    def __post_init__(self):
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if self.recovery_timeout_seconds <= 0:
            raise ValueError("recovery_timeout_seconds must be > 0")

    def to_circuit_breaker_config(self):
        """Convert to mcp.types.CircuitBreakerConfig."""
        from ..mcp.types import CircuitBreakerConfig
        return CircuitBreakerConfig(
            failure_threshold=self.failure_threshold,
            recovery_timeout_seconds=self.recovery_timeout_seconds,
            half_open_max_requests=self.half_open_max_requests,
        )


@dataclass
class WorkflowErrorSettings:
    """Configuration for workflow error handling."""
    default_strategy: ErrorStrategy = ErrorStrategy.STOP
    max_iterations: int = 5  # For iterative workflows
    continue_on_warning: bool = True

    def __post_init__(self):
        if self.max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")


@dataclass
class AutoFixSettings:
    """Configuration for self-diagnostic auto-fix behavior."""
    enabled: bool = True
    safe_only: bool = True  # Only apply non-destructive fixes
    require_confirmation: bool = True  # Ask before applying
    auto_run_on_startup: bool = False  # Run diagnostics at startup


@dataclass
class DiagnosticsSettings:
    """Configuration for self-diagnostics."""
    enabled: bool = True
    include_api_checks: bool = False  # Include real API connectivity tests
    check_interval_minutes: int = 0  # 0 = manual only
    auto_analyze: bool = False  # Auto-analyze failures with agent


@dataclass
class ResilienceConfig:
    """
    Unified resilience configuration for Startd8 SDK.

    Controls all self-healing and fault-tolerance capabilities.

    Example:
        # Quick setup with preset
        config = ResilienceConfig.from_level(ResilienceLevel.STANDARD)

        # Custom configuration
        config = ResilienceConfig(
            retry=RetrySettings(max_attempts=5),
            circuit_breaker=CircuitBreakerSettings(failure_threshold=3),
            auto_fix=AutoFixSettings(enabled=True, safe_only=True),
        )
    """
    enabled: bool = True
    level: ResilienceLevel = ResilienceLevel.STANDARD

    # Component settings
    retry: RetrySettings = field(default_factory=RetrySettings)
    circuit_breaker: CircuitBreakerSettings = field(default_factory=CircuitBreakerSettings)
    workflow_errors: WorkflowErrorSettings = field(default_factory=WorkflowErrorSettings)
    auto_fix: AutoFixSettings = field(default_factory=AutoFixSettings)
    diagnostics: DiagnosticsSettings = field(default_factory=DiagnosticsSettings)

    @classmethod
    def from_level(cls, level: ResilienceLevel) -> "ResilienceConfig":
        """
        Create configuration from a preset level.

        Args:
            level: Preset resilience level

        Returns:
            ResilienceConfig with appropriate settings
        """
        if level == ResilienceLevel.OFF:
            return cls(
                enabled=False,
                level=level,
                retry=RetrySettings(enabled=False),
                circuit_breaker=CircuitBreakerSettings(enabled=False),
                auto_fix=AutoFixSettings(enabled=False),
                diagnostics=DiagnosticsSettings(enabled=False),
            )

        elif level == ResilienceLevel.MINIMAL:
            return cls(
                enabled=True,
                level=level,
                retry=RetrySettings(enabled=True, max_attempts=2),
                circuit_breaker=CircuitBreakerSettings(enabled=False),
                workflow_errors=WorkflowErrorSettings(default_strategy=ErrorStrategy.STOP),
                auto_fix=AutoFixSettings(enabled=False),
                diagnostics=DiagnosticsSettings(enabled=True, include_api_checks=False),
            )

        elif level == ResilienceLevel.STANDARD:
            return cls(
                enabled=True,
                level=level,
                retry=RetrySettings(enabled=True, max_attempts=3),
                circuit_breaker=CircuitBreakerSettings(enabled=True),
                workflow_errors=WorkflowErrorSettings(
                    default_strategy=ErrorStrategy.RETRY,
                    max_iterations=3,
                ),
                auto_fix=AutoFixSettings(enabled=True, safe_only=True),
                diagnostics=DiagnosticsSettings(enabled=True),
            )

        elif level == ResilienceLevel.AGGRESSIVE:
            return cls(
                enabled=True,
                level=level,
                retry=RetrySettings(
                    enabled=True,
                    max_attempts=5,
                    base_delay_seconds=2.0,
                    max_delay_seconds=120.0,
                ),
                circuit_breaker=CircuitBreakerSettings(
                    enabled=True,
                    failure_threshold=3,
                    recovery_timeout_seconds=60.0,
                ),
                workflow_errors=WorkflowErrorSettings(
                    default_strategy=ErrorStrategy.RETRY,
                    max_iterations=5,
                ),
                auto_fix=AutoFixSettings(
                    enabled=True,
                    safe_only=True,
                    require_confirmation=False,
                ),
                diagnostics=DiagnosticsSettings(
                    enabled=True,
                    include_api_checks=True,
                    auto_analyze=True,
                ),
            )

        else:  # CUSTOM
            return cls(enabled=True, level=level)

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "enabled": self.enabled,
            "level": self.level.value,
            "retry": {
                "enabled": self.retry.enabled,
                "max_attempts": self.retry.max_attempts,
                "base_delay_seconds": self.retry.base_delay_seconds,
                "max_delay_seconds": self.retry.max_delay_seconds,
            },
            "circuit_breaker": {
                "enabled": self.circuit_breaker.enabled,
                "failure_threshold": self.circuit_breaker.failure_threshold,
                "recovery_timeout_seconds": self.circuit_breaker.recovery_timeout_seconds,
            },
            "workflow_errors": {
                "default_strategy": self.workflow_errors.default_strategy.value,
                "max_iterations": self.workflow_errors.max_iterations,
            },
            "auto_fix": {
                "enabled": self.auto_fix.enabled,
                "safe_only": self.auto_fix.safe_only,
                "require_confirmation": self.auto_fix.require_confirmation,
            },
            "diagnostics": {
                "enabled": self.diagnostics.enabled,
                "include_api_checks": self.diagnostics.include_api_checks,
            },
        }


# Default configuration
DEFAULT_RESILIENCE_CONFIG = ResilienceConfig.from_level(ResilienceLevel.STANDARD)


__all__ = [
    "ResilienceLevel",
    "ErrorStrategy",
    "RetrySettings",
    "CircuitBreakerSettings",
    "WorkflowErrorSettings",
    "AutoFixSettings",
    "DiagnosticsSettings",
    "ResilienceConfig",
    "DEFAULT_RESILIENCE_CONFIG",
]
