"""
Unit tests for ComparisonAnalytics
"""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile

from startd8.costs.store import CostStore
from startd8.costs.comparison import ComparisonAnalytics
from startd8.costs.external import ExternalUsageTracker
from startd8.costs.models import (
    CostRecord,
    UsageSource,
    SourceUsageSummary,
    ToolComparisonReport,
)


class TestComparisonAnalytics:
    """Test ComparisonAnalytics functionality"""

    @pytest.fixture
    def store(self):
        """Create a temporary cost store"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield CostStore(Path(tmpdir) / "test_costs.db")

    @pytest.fixture
    def analytics(self, store):
        """Create analytics with store"""
        return ComparisonAnalytics(store)

    @pytest.fixture
    def tracker(self, store):
        """Create external tracker"""
        return ExternalUsageTracker(store)

    def _create_sdk_record(
        self,
        store,
        input_tokens=1000,
        output_tokens=500,
        total_cost=0.01,
        timestamp=None,
        project=None,
    ):
        """Create and save an SDK record"""
        record = CostRecord(
            agent_name="claude",
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            input_cost=total_cost * 0.6,
            output_cost=total_cost * 0.4,
            total_cost=total_cost,
            source_type=UsageSource.SDK,
            timestamp=timestamp or datetime.now(timezone.utc),
            project=project,
        )
        store.save(record)
        return record

    def test_get_usage_by_source_empty(self, analytics):
        """Test usage by source with no data"""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)

        usage = analytics.get_usage_by_source(start, now)

        # Should have SDK entry with zeros
        assert "sdk" in usage
        assert usage["sdk"].total_cost == 0.0
        assert usage["sdk"].total_calls == 0

    def test_get_usage_by_source_sdk_only(self, analytics, store):
        """Test usage by source with only SDK records"""
        # Use a fixed time range to avoid timing issues
        base_time = datetime.now(timezone.utc) - timedelta(hours=1)
        start = base_time - timedelta(days=7)
        end = base_time + timedelta(hours=2)

        # Add SDK records with explicit timestamps
        for i in range(3):
            self._create_sdk_record(store, total_cost=0.01, timestamp=base_time)

        usage = analytics.get_usage_by_source(start, end)

        assert usage["sdk"].total_calls == 3
        assert usage["sdk"].total_cost == pytest.approx(0.03, rel=0.01)

    def test_get_usage_by_source_mixed(self, analytics, store, tracker):
        """Test usage by source with SDK and external records"""
        base_time = datetime.now(timezone.utc) - timedelta(hours=1)
        start = base_time - timedelta(days=7)
        end = base_time + timedelta(hours=2)

        # Add SDK records with explicit timestamps
        for i in range(2):
            self._create_sdk_record(store, total_cost=0.01, timestamp=base_time)

        # Add external records with explicit timestamps
        tracker.record_external_usage(
            tool_name="claude-code",
            input_tokens=5000,
            output_tokens=2000,
            timestamp=base_time,
        )
        tracker.record_external_usage(
            tool_name="cursor",
            total_cost=2.00,
            timestamp=base_time,
        )

        usage = analytics.get_usage_by_source(start, end)

        assert usage["sdk"].total_calls == 2
        assert "external:claude-code" in usage
        assert "external:cursor" in usage
        assert usage["external:cursor"].total_cost == 2.00

    def test_get_tool_comparison(self, analytics, store, tracker):
        """Test tool comparison report generation"""
        base_time = datetime.now(timezone.utc) - timedelta(hours=1)
        start = base_time - timedelta(days=7)
        end = base_time + timedelta(hours=2)

        # Add mixed records with explicit timestamps
        self._create_sdk_record(store, total_cost=0.05, input_tokens=5000, output_tokens=2000, timestamp=base_time)
        tracker.record_external_usage(
            tool_name="claude-code",
            input_tokens=10000,
            output_tokens=5000,
            timestamp=base_time,
        )

        report = analytics.get_tool_comparison(start, end)

        assert isinstance(report, ToolComparisonReport)
        assert report.sdk_usage.total_calls == 1
        assert report.total_calls == 2  # 1 SDK + 1 external
        assert report.total_cost > 0

    def test_get_tool_comparison_most_cost_effective(self, analytics, store, tracker):
        """Test finding most cost-effective tool"""
        base_time = datetime.now(timezone.utc) - timedelta(hours=1)
        start = base_time - timedelta(days=7)
        end = base_time + timedelta(hours=2)

        # Add records with different cost efficiency
        # SDK: 1000 tokens for $0.01 = $0.01/1K tokens
        self._create_sdk_record(
            store,
            input_tokens=600,
            output_tokens=400,
            total_cost=0.01,
            timestamp=base_time,
        )

        # External: 1000 tokens for $0.02 = $0.02/1K tokens (more expensive)
        tracker.record_external_usage(
            tool_name="claude-code",
            input_tokens=600,
            output_tokens=400,
            total_cost=0.02,
            timestamp=base_time,
        )

        report = analytics.get_tool_comparison(start, end)

        # SDK should be more cost-effective
        assert report.most_cost_effective_tool == "sdk"

    def test_get_tool_comparison_recommendations(self, analytics, store, tracker):
        """Test that recommendations are generated"""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)

        # Add some data
        self._create_sdk_record(store, total_cost=0.01)

        report = analytics.get_tool_comparison(start, now)

        assert report.recommendations is not None
        assert len(report.recommendations) > 0

    def test_get_productivity_metrics(self, analytics, store, tracker):
        """Test productivity metrics calculation"""
        base_time = datetime.now(timezone.utc) - timedelta(hours=1)
        start = base_time - timedelta(days=7)
        end = base_time + timedelta(hours=2)

        # Add records with task descriptions
        tracker.record_external_usage(
            tool_name="claude-code",
            input_tokens=1000,
            output_tokens=500,
            task_description="Fixed bug #123",
            timestamp=base_time,
        )
        tracker.record_external_usage(
            tool_name="claude-code",
            input_tokens=2000,
            output_tokens=1000,
            task_description="Implemented feature X",
            timestamp=base_time,
        )
        tracker.record_external_usage(
            tool_name="cursor",
            total_cost=1.00,
            task_description="Code review",
            timestamp=base_time,
        )

        metrics = analytics.get_productivity_metrics(start, end)

        assert "claude-code" in metrics.tasks_completed
        assert metrics.tasks_completed["claude-code"] == 2
        assert metrics.tasks_completed["cursor"] == 1

    def test_get_productivity_metrics_sessions(self, analytics, store, tracker):
        """Test session-based productivity metrics"""
        base_time = datetime.now(timezone.utc) - timedelta(hours=1)
        start = base_time - timedelta(days=7)
        end = base_time + timedelta(hours=2)

        # Add records with session IDs
        tracker.record_external_usage(
            tool_name="claude-code",
            input_tokens=1000,
            output_tokens=500,
            session_id="session-1",
            timestamp=base_time,
        )
        tracker.record_external_usage(
            tool_name="claude-code",
            input_tokens=2000,
            output_tokens=1000,
            session_id="session-1",  # Same session
            timestamp=base_time,
        )
        tracker.record_external_usage(
            tool_name="claude-code",
            input_tokens=500,
            output_tokens=250,
            session_id="session-2",  # Different session
            timestamp=base_time,
        )

        metrics = analytics.get_productivity_metrics(start, end)

        assert "claude-code" in metrics.sessions_count
        assert metrics.sessions_count["claude-code"] == 2  # 2 unique sessions

    def test_generate_comparison_report_markdown(self, analytics, store, tracker):
        """Test markdown report generation"""
        base_time = datetime.now(timezone.utc) - timedelta(hours=1)
        start = base_time - timedelta(days=7)
        end = base_time + timedelta(hours=2)

        # Add some data with explicit timestamps
        self._create_sdk_record(store, total_cost=0.05, timestamp=base_time)
        tracker.record_external_usage(
            tool_name="cursor",
            total_cost=2.00,
            timestamp=base_time,
        )

        report = analytics.generate_comparison_report(start, end, format="markdown")

        assert "# AI Usage Comparison Report" in report
        assert "SDK (StartD8)" in report
        assert "cursor" in report
        assert "Recommendations" in report

    def test_generate_comparison_report_text(self, analytics, store, tracker):
        """Test text report generation"""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)

        # Add some data
        self._create_sdk_record(store, total_cost=0.05)

        report = analytics.generate_comparison_report(start, now, format="text")

        assert "AI USAGE COMPARISON REPORT" in report
        assert "SDK (StartD8)" in report
        assert "RECOMMENDATIONS" in report

    def test_get_daily_comparison(self, analytics, store, tracker):
        """Test daily comparison data"""
        now = datetime.now(timezone.utc)

        # Add records on different days
        yesterday = now - timedelta(days=1)
        self._create_sdk_record(store, total_cost=0.05, timestamp=yesterday)

        tracker.record_external_usage(
            tool_name="cursor",
            total_cost=2.00,
        )

        daily_data = analytics.get_daily_comparison(days=7)

        assert len(daily_data) > 0
        # Should have date strings as keys
        for date_str, sources in daily_data:
            assert "-" in date_str  # YYYY-MM-DD format

    def test_comparison_with_project_filter(self, analytics, store, tracker):
        """Test comparison filtered by project"""
        base_time = datetime.now(timezone.utc) - timedelta(hours=1)
        start = base_time - timedelta(days=7)
        end = base_time + timedelta(hours=2)

        # Add records with different projects
        self._create_sdk_record(store, total_cost=0.05, project="project-a", timestamp=base_time)
        self._create_sdk_record(store, total_cost=0.03, project="project-b", timestamp=base_time)

        tracker.record_external_usage(
            tool_name="cursor",
            total_cost=2.00,
            project="project-a",
            timestamp=base_time,
        )

        # Filter by project-a
        report = analytics.get_tool_comparison(start, end, project="project-a")

        # Should only include project-a records
        assert report.sdk_usage.total_calls == 1
        assert report.sdk_usage.total_cost == pytest.approx(0.05, rel=0.01)


class TestSourceUsageSummary:
    """Test SourceUsageSummary model"""

    def test_from_records_empty(self):
        """Test creating summary from empty records"""
        summary = SourceUsageSummary.from_records([], UsageSource.SDK, None)

        assert summary.total_cost == 0.0
        assert summary.total_tokens == 0
        assert summary.total_calls == 0

    def test_from_records_calculates_averages(self):
        """Test that averages are calculated correctly"""
        records = [
            CostRecord(
                agent_name="test",
                model="test",
                provider="test",
                input_tokens=500,
                output_tokens=500,
                total_tokens=1000,
                input_cost=0.005,
                output_cost=0.005,
                total_cost=0.01,
                source_type=UsageSource.SDK,
            ),
            CostRecord(
                agent_name="test",
                model="test",
                provider="test",
                input_tokens=500,
                output_tokens=500,
                total_tokens=1000,
                input_cost=0.005,
                output_cost=0.005,
                total_cost=0.01,
                source_type=UsageSource.SDK,
            ),
        ]

        summary = SourceUsageSummary.from_records(records, UsageSource.SDK, None)

        assert summary.total_calls == 2
        assert summary.total_tokens == 2000
        assert summary.total_cost == 0.02
        assert summary.avg_cost_per_call == pytest.approx(0.01, rel=0.01)
        assert summary.avg_tokens_per_call == 1000
        # $0.02 / 2000 tokens * 1000 = $0.01 per 1K tokens
        assert summary.avg_cost_per_1k_tokens == pytest.approx(0.01, rel=0.01)
