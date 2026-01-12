"""
Unit tests for ExternalUsageTracker
"""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile

from startd8.costs.store import CostStore
from startd8.costs.external import ExternalUsageTracker, DEFAULT_TOOLS
from startd8.costs.models import (
    CostRecord,
    ExternalTool,
    PricingType,
    UsageSource,
)


class TestExternalUsageTracker:
    """Test ExternalUsageTracker functionality"""

    @pytest.fixture
    def store(self):
        """Create a temporary cost store"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield CostStore(Path(tmpdir) / "test_costs.db")

    @pytest.fixture
    def tracker(self, store):
        """Create tracker with store"""
        return ExternalUsageTracker(store, auto_register_defaults=True)

    def test_default_tools_registered(self, tracker):
        """Test that default tools are registered on init"""
        tools = tracker.list_tools()
        tool_ids = {t.id for t in tools}

        # Should have all default tools
        assert "claude-code" in tool_ids
        assert "cursor" in tool_ids
        assert "copilot" in tool_ids
        assert "chatgpt-web" in tool_ids
        assert "claude-web" in tool_ids

    def test_record_external_usage_with_tokens(self, tracker):
        """Test recording external usage with token counts"""
        record = tracker.record_external_usage(
            tool_name="claude-code",
            input_tokens=5000,
            output_tokens=2000,
            task_description="Refactored auth module",
            project="my-app",
        )

        assert record.source_type == UsageSource.EXTERNAL
        assert record.tool_name == "claude-code"
        assert record.input_tokens == 5000
        assert record.output_tokens == 2000
        assert record.total_tokens == 7000
        assert record.task_description == "Refactored auth module"
        assert record.project == "my-app"
        assert record.agent_name == "external:claude-code"

    def test_record_external_usage_with_cost(self, tracker):
        """Test recording external usage with direct cost"""
        record = tracker.record_external_usage(
            tool_name="cursor",
            total_cost=2.50,
            task_description="Built new feature",
        )

        assert record.source_type == UsageSource.EXTERNAL
        assert record.tool_name == "cursor"
        assert record.total_cost == 2.50
        assert record.task_description == "Built new feature"

    def test_record_external_usage_with_session(self, tracker):
        """Test recording external usage with session ID"""
        session_id = "session-abc123"

        record1 = tracker.record_external_usage(
            tool_name="claude-code",
            input_tokens=1000,
            output_tokens=500,
            session_id=session_id,
        )

        record2 = tracker.record_external_usage(
            tool_name="claude-code",
            input_tokens=2000,
            output_tokens=800,
            session_id=session_id,
        )

        assert record1.session_id == session_id
        assert record2.session_id == session_id

    def test_record_external_usage_with_tags(self, tracker):
        """Test recording external usage with tags"""
        record = tracker.record_external_usage(
            tool_name="cursor",
            total_cost=1.00,
            tags=["code-review", "backend"],
        )

        assert "code-review" in record.tags
        assert "backend" in record.tags

    def test_estimate_subscription_cost_hours(self, tracker):
        """Test subscription cost estimation from hours"""
        # Cursor is $20/month, assuming 160 work hours/month
        # 2 hours = $20 * (2/160) = $0.25
        cost = tracker.estimate_subscription_cost("cursor", usage_hours=2)
        assert cost == pytest.approx(0.25, rel=0.01)

    def test_estimate_subscription_cost_minutes(self, tracker):
        """Test subscription cost estimation from minutes"""
        # 30 minutes = 0.5 hours = $20 * (0.5/160) = $0.0625
        cost = tracker.estimate_subscription_cost("cursor", usage_minutes=30)
        assert cost == pytest.approx(0.0625, rel=0.01)

    def test_estimate_subscription_cost_per_token_tool(self, tracker):
        """Test that per-token tools return 0 for subscription estimate"""
        cost = tracker.estimate_subscription_cost("claude-code", usage_hours=2)
        assert cost == 0.0

    def test_register_custom_tool(self, tracker):
        """Test registering a custom tool"""
        custom_tool = ExternalTool(
            id="my-custom-tool",
            display_name="My Custom AI",
            provider="custom",
            pricing_type=PricingType.SUBSCRIPTION,
            subscription_cost=15.0,
        )

        tracker.register_tool(custom_tool)
        retrieved = tracker.get_tool("my-custom-tool")

        assert retrieved is not None
        assert retrieved.display_name == "My Custom AI"
        assert retrieved.subscription_cost == 15.0

    def test_unregister_tool(self, tracker):
        """Test unregistering a tool"""
        # First register a custom tool
        custom_tool = ExternalTool(
            id="temp-tool",
            display_name="Temporary Tool",
            provider="temp",
            pricing_type=PricingType.PER_TOKEN,
        )
        tracker.register_tool(custom_tool)

        # Verify it exists
        assert tracker.get_tool("temp-tool") is not None

        # Unregister
        result = tracker.unregister_tool("temp-tool")
        assert result is True

        # Verify it's gone
        assert tracker.get_tool("temp-tool") is None

    def test_get_tool_usage(self, tracker):
        """Test getting usage for a specific tool"""
        # Record some usage
        tracker.record_external_usage(
            tool_name="claude-code",
            input_tokens=1000,
            output_tokens=500,
        )
        tracker.record_external_usage(
            tool_name="cursor",
            total_cost=1.00,
        )
        tracker.record_external_usage(
            tool_name="claude-code",
            input_tokens=2000,
            output_tokens=1000,
        )

        # Get claude-code usage only
        records = tracker.get_tool_usage("claude-code")
        assert len(records) == 2
        assert all(r.tool_name == "claude-code" for r in records)

    def test_get_all_external_usage(self, tracker):
        """Test getting all external usage"""
        tracker.record_external_usage(
            tool_name="claude-code",
            input_tokens=1000,
            output_tokens=500,
        )
        tracker.record_external_usage(
            tool_name="cursor",
            total_cost=1.00,
        )

        records = tracker.get_all_external_usage()
        assert len(records) == 2
        assert all(r.source_type == UsageSource.EXTERNAL for r in records)

    def test_get_sdk_usage(self, tracker, store):
        """Test getting SDK usage for comparison"""
        # Add an SDK record directly to store
        sdk_record = CostRecord(
            agent_name="claude",
            model="claude-sonnet-4-20250514",
            provider="anthropic",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            input_cost=0.003,
            output_cost=0.0075,
            total_cost=0.0105,
            source_type=UsageSource.SDK,
        )
        store.save(sdk_record)

        # Add an external record
        tracker.record_external_usage(
            tool_name="cursor",
            total_cost=1.00,
        )

        # Get SDK usage only
        sdk_records = tracker.get_sdk_usage()
        assert len(sdk_records) == 1
        assert sdk_records[0].source_type == UsageSource.SDK

    def test_uses_tool_default_model(self, tracker):
        """Test that tool's default model is used when not specified"""
        record = tracker.record_external_usage(
            tool_name="claude-code",
            input_tokens=1000,
            output_tokens=500,
        )

        # Claude code has default_model set
        assert record.model is not None
        assert "claude" in record.model.lower() or record.model == "unknown"


class TestDefaultTools:
    """Test the default tools configuration"""

    def test_default_tools_have_required_fields(self):
        """Test all default tools have required fields"""
        for tool in DEFAULT_TOOLS:
            assert tool.id is not None
            assert tool.display_name is not None
            assert tool.provider is not None
            assert tool.pricing_type is not None

    def test_subscription_tools_have_costs(self):
        """Test subscription-based tools have subscription_cost"""
        subscription_tools = [
            t for t in DEFAULT_TOOLS
            if t.pricing_type in [PricingType.SUBSCRIPTION, PricingType.HYBRID]
        ]

        for tool in subscription_tools:
            assert tool.subscription_cost is not None
            assert tool.subscription_cost > 0

    def test_known_tools_present(self):
        """Test that all expected default tools are present"""
        tool_ids = {t.id for t in DEFAULT_TOOLS}

        expected = {"claude-code", "cursor", "copilot", "chatgpt-web", "claude-web"}
        for expected_id in expected:
            assert expected_id in tool_ids, f"Missing expected tool: {expected_id}"
