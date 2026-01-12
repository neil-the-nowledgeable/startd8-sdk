"""
Comparison Analytics for SDK vs External Tool Usage.

This module provides analytics for comparing LLM usage across
different sources (SDK, external tools) to help developers
understand their overall AI tool costs and productivity.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from .models import (
    CostRecord,
    SourceUsageSummary,
    ToolComparisonReport,
    ProductivityMetrics,
    UsageSource,
)
from .store import CostStore
from ..logging_config import get_logger

logger = get_logger(__name__)


class ComparisonAnalytics:
    """
    Analytics service for comparing SDK vs external tool usage.

    Provides methods to:
    - Compare costs across SDK and external tools
    - Analyze productivity metrics by tool
    - Generate comparison reports
    - Identify cost optimization opportunities

    Example:
        analytics = ComparisonAnalytics(store)

        # Get tool comparison for last 30 days
        report = analytics.get_tool_comparison(
            start=datetime.now() - timedelta(days=30),
            end=datetime.now()
        )

        print(f"Most cost-effective tool: {report.most_cost_effective_tool}")
        for rec in report.recommendations:
            print(f"  - {rec}")
    """

    def __init__(self, store: CostStore):
        """
        Initialize comparison analytics.

        Args:
            store: CostStore for querying usage data
        """
        self.store = store

    def get_usage_by_source(
        self,
        start: datetime,
        end: datetime,
        project: Optional[str] = None,
    ) -> Dict[str, SourceUsageSummary]:
        """
        Get usage summaries grouped by source type and tool.

        Args:
            start: Start datetime
            end: End datetime
            project: Optional project filter

        Returns:
            Dictionary mapping source/tool to SourceUsageSummary
        """
        # Get all records in range
        sdk_records = self.store.query_by_source(
            source_type=UsageSource.SDK,
            start=start,
            end=end,
            project=project,
        )

        external_records = self.store.query_by_source(
            source_type=UsageSource.EXTERNAL,
            start=start,
            end=end,
            project=project,
        )

        import_records = self.store.query_by_source(
            source_type=UsageSource.IMPORT,
            start=start,
            end=end,
            project=project,
        )

        result: Dict[str, SourceUsageSummary] = {}

        # SDK summary
        result["sdk"] = SourceUsageSummary.from_records(
            sdk_records, UsageSource.SDK, None
        )

        # Group external by tool_name
        external_by_tool: Dict[str, List[CostRecord]] = {}
        for record in external_records:
            tool = record.tool_name or "unknown"
            if tool not in external_by_tool:
                external_by_tool[tool] = []
            external_by_tool[tool].append(record)

        for tool_name, records in external_by_tool.items():
            result[f"external:{tool_name}"] = SourceUsageSummary.from_records(
                records, UsageSource.EXTERNAL, tool_name
            )

        # Group imports by tool_name
        import_by_tool: Dict[str, List[CostRecord]] = {}
        for record in import_records:
            tool = record.tool_name or "imported"
            if tool not in import_by_tool:
                import_by_tool[tool] = []
            import_by_tool[tool].append(record)

        for tool_name, records in import_by_tool.items():
            result[f"import:{tool_name}"] = SourceUsageSummary.from_records(
                records, UsageSource.IMPORT, tool_name
            )

        return result

    def get_tool_comparison(
        self,
        start: datetime,
        end: datetime,
        project: Optional[str] = None,
    ) -> ToolComparisonReport:
        """
        Generate a side-by-side comparison of SDK vs external tools.

        Args:
            start: Start datetime
            end: End datetime
            project: Optional project filter

        Returns:
            ToolComparisonReport with comparison data and recommendations
        """
        usage_by_source = self.get_usage_by_source(start, end, project)

        # Extract SDK usage
        sdk_usage = usage_by_source.get("sdk", SourceUsageSummary(
            source_type=UsageSource.SDK,
            tool_name=None,
            total_cost=0.0,
            total_tokens=0,
            total_calls=0,
        ))

        # Extract external usage (group by tool)
        external_usage: Dict[str, SourceUsageSummary] = {}
        for key, summary in usage_by_source.items():
            if key.startswith("external:") or key.startswith("import:"):
                tool_name = key.split(":", 1)[1]
                external_usage[tool_name] = summary

        # Calculate totals
        total_cost = sdk_usage.total_cost + sum(
            s.total_cost for s in external_usage.values()
        )
        total_tokens = sdk_usage.total_tokens + sum(
            s.total_tokens for s in external_usage.values()
        )
        total_calls = sdk_usage.total_calls + sum(
            s.total_calls for s in external_usage.values()
        )

        # Find most cost-effective tool
        all_sources = [("sdk", sdk_usage)] + list(external_usage.items())
        most_cost_effective = None
        best_cost_per_1k = float("inf")

        for name, summary in all_sources:
            if summary.total_tokens > 0:
                cost_per_1k = summary.avg_cost_per_1k_tokens
                if cost_per_1k > 0 and cost_per_1k < best_cost_per_1k:
                    best_cost_per_1k = cost_per_1k
                    most_cost_effective = name

        # Generate recommendations
        recommendations = self._generate_recommendations(
            sdk_usage, external_usage, total_cost
        )

        return ToolComparisonReport(
            period_start=start,
            period_end=end,
            sdk_usage=sdk_usage,
            external_usage=external_usage,
            total_cost=total_cost,
            total_tokens=total_tokens,
            total_calls=total_calls,
            most_cost_effective_tool=most_cost_effective,
            recommendations=recommendations,
        )

    def _generate_recommendations(
        self,
        sdk_usage: SourceUsageSummary,
        external_usage: Dict[str, SourceUsageSummary],
        total_cost: float,
    ) -> List[str]:
        """Generate cost optimization recommendations."""
        recommendations: List[str] = []

        # Check if SDK is significantly more/less cost effective
        if sdk_usage.total_tokens > 0:
            sdk_cost_per_1k = sdk_usage.avg_cost_per_1k_tokens

            for tool_name, ext_summary in external_usage.items():
                if ext_summary.total_tokens > 0:
                    ext_cost_per_1k = ext_summary.avg_cost_per_1k_tokens

                    # SDK is more cost-effective
                    if ext_cost_per_1k > sdk_cost_per_1k * 1.5:
                        potential_savings = (
                            (ext_cost_per_1k - sdk_cost_per_1k)
                            * ext_summary.total_tokens
                            / 1000
                        )
                        recommendations.append(
                            f"Consider migrating {tool_name} workflows to SDK. "
                            f"Potential savings: ${potential_savings:.2f}/month"
                        )

                    # External tool is more cost-effective
                    elif sdk_cost_per_1k > ext_cost_per_1k * 1.5:
                        recommendations.append(
                            f"{tool_name} shows better cost efficiency than SDK for similar tasks. "
                            f"Review if SDK usage could use more efficient models."
                        )

        # Check subscription vs per-token economics
        for tool_name, summary in external_usage.items():
            if summary.total_cost > 0 and summary.total_tokens == 0:
                # Likely subscription-based with estimated costs
                recommendations.append(
                    f"Consider tracking actual token usage for {tool_name} "
                    f"to better compare with per-token tools."
                )

        # Check for low-usage subscriptions
        # (would need tool info to know subscription cost)

        # General recommendation if external usage is high
        external_total = sum(s.total_cost for s in external_usage.values())
        if external_total > total_cost * 0.7 and external_total > 10:
            recommendations.append(
                "External tools account for >70% of your AI costs. "
                "Consider consolidating to fewer tools or using SDK more."
            )

        # No recommendations case
        if not recommendations:
            recommendations.append(
                "Your usage patterns look balanced. Continue monitoring "
                "to identify optimization opportunities."
            )

        return recommendations

    def get_productivity_metrics(
        self,
        start: datetime,
        end: datetime,
        project: Optional[str] = None,
    ) -> ProductivityMetrics:
        """
        Calculate productivity metrics by tool.

        Requires task_description and/or session_id to be populated
        for meaningful results.

        Args:
            start: Start datetime
            end: End datetime
            project: Optional project filter

        Returns:
            ProductivityMetrics with per-tool productivity data
        """
        # Get all records
        all_records = self.store.query(start=start, end=end, project=project)

        # Initialize metrics
        tasks_by_tool: Dict[str, int] = {}
        cost_by_tool: Dict[str, float] = {}
        tokens_by_tool: Dict[str, int] = {}
        sessions_by_tool: Dict[str, set] = {}
        session_costs_by_tool: Dict[str, float] = {}

        for record in all_records:
            # Determine tool identifier
            if record.source_type == UsageSource.SDK:
                tool = "sdk"
            else:
                tool = record.tool_name or "unknown"

            # Initialize if needed
            if tool not in tasks_by_tool:
                tasks_by_tool[tool] = 0
                cost_by_tool[tool] = 0.0
                tokens_by_tool[tool] = 0
                sessions_by_tool[tool] = set()
                session_costs_by_tool[tool] = 0.0

            # Count tasks (records with task_description)
            if record.task_description:
                tasks_by_tool[tool] += 1

            # Accumulate costs and tokens
            cost_by_tool[tool] += record.total_cost
            tokens_by_tool[tool] += record.total_tokens

            # Track sessions
            if record.session_id:
                sessions_by_tool[tool].add(record.session_id)
                session_costs_by_tool[tool] += record.total_cost

        # Calculate averages
        avg_cost_per_task: Dict[str, float] = {}
        avg_tokens_per_task: Dict[str, int] = {}
        sessions_count: Dict[str, int] = {}
        avg_cost_per_session: Dict[str, float] = {}

        for tool in tasks_by_tool:
            task_count = tasks_by_tool[tool]
            session_count = len(sessions_by_tool[tool])

            avg_cost_per_task[tool] = (
                cost_by_tool[tool] / task_count if task_count > 0 else 0.0
            )
            avg_tokens_per_task[tool] = (
                tokens_by_tool[tool] // task_count if task_count > 0 else 0
            )
            sessions_count[tool] = session_count
            avg_cost_per_session[tool] = (
                session_costs_by_tool[tool] / session_count if session_count > 0 else 0.0
            )

        return ProductivityMetrics(
            period_start=start,
            period_end=end,
            tasks_completed=tasks_by_tool,
            avg_cost_per_task=avg_cost_per_task,
            avg_tokens_per_task=avg_tokens_per_task,
            sessions_count=sessions_count,
            avg_cost_per_session=avg_cost_per_session,
        )

    def generate_comparison_report(
        self,
        start: datetime,
        end: datetime,
        project: Optional[str] = None,
        format: str = "markdown",
    ) -> str:
        """
        Generate a formatted comparison report.

        Args:
            start: Start datetime
            end: End datetime
            project: Optional project filter
            format: Output format ("markdown" or "text")

        Returns:
            Formatted report string
        """
        report = self.get_tool_comparison(start, end, project)
        metrics = self.get_productivity_metrics(start, end, project)

        if format == "markdown":
            return self._format_markdown_report(report, metrics)
        else:
            return self._format_text_report(report, metrics)

    def _format_markdown_report(
        self,
        report: ToolComparisonReport,
        metrics: ProductivityMetrics,
    ) -> str:
        """Format report as Markdown."""
        lines = [
            "# AI Usage Comparison Report",
            "",
            f"**Period:** {report.period_start.strftime('%Y-%m-%d')} to "
            f"{report.period_end.strftime('%Y-%m-%d')}",
            "",
            "## Summary",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Cost | ${report.total_cost:.2f} |",
            f"| Total Tokens | {report.total_tokens:,} |",
            f"| Total Calls | {report.total_calls:,} |",
            f"| Most Cost-Effective | {report.most_cost_effective_tool or 'N/A'} |",
            "",
            "## Usage by Source",
            "",
            "| Source | Calls | Tokens | Cost | $/1K tokens |",
            "|--------|-------|--------|------|-------------|",
        ]

        # SDK row
        sdk = report.sdk_usage
        lines.append(
            f"| SDK (StartD8) | {sdk.total_calls:,} | {sdk.total_tokens:,} | "
            f"${sdk.total_cost:.2f} | ${sdk.avg_cost_per_1k_tokens:.4f} |"
        )

        # External tools
        for tool_name, summary in sorted(report.external_usage.items()):
            lines.append(
                f"| {tool_name} | {summary.total_calls:,} | {summary.total_tokens:,} | "
                f"${summary.total_cost:.2f} | ${summary.avg_cost_per_1k_tokens:.4f} |"
            )

        # Productivity section (if data available)
        if any(metrics.tasks_completed.values()):
            lines.extend([
                "",
                "## Productivity Metrics",
                "",
                "| Tool | Tasks | Avg Cost/Task | Sessions | Avg Cost/Session |",
                "|------|-------|---------------|----------|------------------|",
            ])

            for tool in sorted(metrics.tasks_completed.keys()):
                lines.append(
                    f"| {tool} | {metrics.tasks_completed[tool]} | "
                    f"${metrics.avg_cost_per_task.get(tool, 0):.2f} | "
                    f"{metrics.sessions_count.get(tool, 0)} | "
                    f"${metrics.avg_cost_per_session.get(tool, 0):.2f} |"
                )

        # Recommendations
        lines.extend([
            "",
            "## Recommendations",
            "",
        ])
        for rec in report.recommendations:
            lines.append(f"- {rec}")

        return "\n".join(lines)

    def _format_text_report(
        self,
        report: ToolComparisonReport,
        metrics: ProductivityMetrics,
    ) -> str:
        """Format report as plain text."""
        lines = [
            "=" * 60,
            "AI USAGE COMPARISON REPORT",
            "=" * 60,
            "",
            f"Period: {report.period_start.strftime('%Y-%m-%d')} to "
            f"{report.period_end.strftime('%Y-%m-%d')}",
            "",
            "SUMMARY",
            "-" * 40,
            f"  Total Cost:           ${report.total_cost:.2f}",
            f"  Total Tokens:         {report.total_tokens:,}",
            f"  Total Calls:          {report.total_calls:,}",
            f"  Most Cost-Effective:  {report.most_cost_effective_tool or 'N/A'}",
            "",
            "USAGE BY SOURCE",
            "-" * 40,
        ]

        # Format as table
        header = f"{'Source':<20} {'Calls':>8} {'Tokens':>12} {'Cost':>10} {'$/1K':>10}"
        lines.append(header)
        lines.append("-" * len(header))

        # SDK row
        sdk = report.sdk_usage
        lines.append(
            f"{'SDK (StartD8)':<20} {sdk.total_calls:>8,} {sdk.total_tokens:>12,} "
            f"${sdk.total_cost:>9.2f} ${sdk.avg_cost_per_1k_tokens:>9.4f}"
        )

        # External tools
        for tool_name, summary in sorted(report.external_usage.items()):
            lines.append(
                f"{tool_name:<20} {summary.total_calls:>8,} {summary.total_tokens:>12,} "
                f"${summary.total_cost:>9.2f} ${summary.avg_cost_per_1k_tokens:>9.4f}"
            )

        # Recommendations
        lines.extend([
            "",
            "RECOMMENDATIONS",
            "-" * 40,
        ])
        for rec in report.recommendations:
            lines.append(f"  * {rec}")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)

    def get_daily_comparison(
        self,
        days: int = 30,
        project: Optional[str] = None,
    ) -> List[Tuple[str, Dict[str, float]]]:
        """
        Get daily cost breakdown by source.

        Args:
            days: Number of days to include
            project: Optional project filter

        Returns:
            List of (date_str, {source: cost}) tuples
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        # Get all records in range
        records = self.store.query(start=start, end=end, project=project)

        # Group by day and source
        daily_data: Dict[str, Dict[str, float]] = {}

        for record in records:
            day = record.timestamp.strftime("%Y-%m-%d")

            if day not in daily_data:
                daily_data[day] = {"sdk": 0.0}

            if record.source_type == UsageSource.SDK:
                daily_data[day]["sdk"] += record.total_cost
            else:
                tool = record.tool_name or "external"
                if tool not in daily_data[day]:
                    daily_data[day][tool] = 0.0
                daily_data[day][tool] += record.total_cost

        # Sort by date and return as list
        return sorted(daily_data.items(), key=lambda x: x[0])
