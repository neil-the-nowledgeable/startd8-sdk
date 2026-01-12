"""
Diagnostic data models for self-diagnostic workflow.

Provides structured representations for health checks, diagnostic results,
and remediation recommendations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class HealthStatus(Enum):
    """Health status levels for diagnostic checks."""
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"
    SKIPPED = "skipped"  # Check was skipped (e.g., missing dependency)


class CheckCategory(Enum):
    """Categories of diagnostic checks."""
    AGENTS = "agents"
    COSTS = "costs"
    STORAGE = "storage"
    FRAMEWORK = "framework"


@dataclass
class HealthCheck:
    """Result of a single health check."""
    name: str
    category: CheckCategory
    status: HealthStatus
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_ms: Optional[float] = None
    fix_hint: Optional[str] = None  # Hint for auto-fix

    @property
    def is_healthy(self) -> bool:
        """Check if status is HEALTHY."""
        return self.status == HealthStatus.HEALTHY

    @property
    def is_failure(self) -> bool:
        """Check if status is WARNING, CRITICAL, or UNKNOWN."""
        return self.status in (HealthStatus.WARNING, HealthStatus.CRITICAL, HealthStatus.UNKNOWN)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "category": self.category.value,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "fix_hint": self.fix_hint,
        }


@dataclass
class DiagnosticReport:
    """Complete diagnostic report with all check results."""
    checks: List[HealthCheck]
    generated_at: datetime = field(default_factory=datetime.utcnow)
    analysis: Optional[str] = None  # Agent analysis if run
    recommendations: Optional[List[str]] = None
    auto_fixes_applied: Optional[List[str]] = None

    @property
    def summary(self) -> Dict[str, int]:
        """Count checks by status."""
        counts = {status.value: 0 for status in HealthStatus}
        for check in self.checks:
            counts[check.status.value] += 1
        return counts

    @property
    def category_summary(self) -> Dict[str, Dict[str, int]]:
        """Count checks by category and status."""
        result: Dict[str, Dict[str, int]] = {}
        for category in CheckCategory:
            result[category.value] = {status.value: 0 for status in HealthStatus}
        for check in self.checks:
            result[check.category.value][check.status.value] += 1
        return result

    def has_failures(self) -> bool:
        """Check if any checks failed (WARNING, CRITICAL, or UNKNOWN)."""
        return any(check.is_failure for check in self.checks)

    def has_critical(self) -> bool:
        """Check if any checks are CRITICAL."""
        return any(check.status == HealthStatus.CRITICAL for check in self.checks)

    def get_failures(self) -> List[HealthCheck]:
        """Get all failed checks."""
        return [check for check in self.checks if check.is_failure]

    def get_by_category(self, category: CheckCategory) -> List[HealthCheck]:
        """Get checks for a specific category."""
        return [check for check in self.checks if check.category == category]

    def get_fixable(self) -> List[HealthCheck]:
        """Get checks that have fix hints."""
        return [check for check in self.checks if check.fix_hint and check.is_failure]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "checks": [check.to_dict() for check in self.checks],
            "summary": self.summary,
            "category_summary": self.category_summary,
            "generated_at": self.generated_at.isoformat(),
            "analysis": self.analysis,
            "recommendations": self.recommendations,
            "auto_fixes_applied": self.auto_fixes_applied,
        }

    def to_markdown(self) -> str:
        """Format report as markdown for display."""
        lines = [
            "# Diagnostic Report",
            f"Generated: {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Summary",
        ]

        summary = self.summary
        total = len(self.checks)
        lines.append(f"- Total checks: {total}")
        lines.append(f"- Healthy: {summary['healthy']}")
        lines.append(f"- Warnings: {summary['warning']}")
        lines.append(f"- Critical: {summary['critical']}")
        if summary['unknown'] > 0:
            lines.append(f"- Unknown: {summary['unknown']}")
        if summary['skipped'] > 0:
            lines.append(f"- Skipped: {summary['skipped']}")
        lines.append("")

        # Group by category
        for category in CheckCategory:
            category_checks = self.get_by_category(category)
            if not category_checks:
                continue

            lines.append(f"## {category.value.title()}")
            for check in category_checks:
                icon = {
                    HealthStatus.HEALTHY: "✅",
                    HealthStatus.WARNING: "⚠️",
                    HealthStatus.CRITICAL: "❌",
                    HealthStatus.UNKNOWN: "❓",
                    HealthStatus.SKIPPED: "⏭️",
                }[check.status]
                lines.append(f"- {icon} **{check.name}**: {check.message}")
                if check.details:
                    for key, value in check.details.items():
                        lines.append(f"  - {key}: {value}")
            lines.append("")

        # Add analysis if present
        if self.analysis:
            lines.append("## Agent Analysis")
            lines.append(self.analysis)
            lines.append("")

        # Add recommendations if present
        if self.recommendations:
            lines.append("## Recommendations")
            for rec in self.recommendations:
                lines.append(f"- {rec}")
            lines.append("")

        # Add auto-fixes if applied
        if self.auto_fixes_applied:
            lines.append("## Auto-Fixes Applied")
            for fix in self.auto_fixes_applied:
                lines.append(f"- {fix}")
            lines.append("")

        return "\n".join(lines)


@dataclass
class CheckDefinition:
    """Definition of a diagnostic check for registration."""
    name: str
    category: CheckCategory
    check_func: Callable[..., HealthCheck]
    requires_framework: bool = False
    requires_api_call: bool = False  # True for connectivity tests
    description: Optional[str] = None
