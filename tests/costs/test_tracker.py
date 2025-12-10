"""
Unit tests for CostTracker
"""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile

from startd8.costs.tracker import CostTracker
from startd8.costs.store import CostStore
from startd8.costs.pricing import PricingService
from startd8.events import EventBus, EventType


class TestCostTracker:
    """Tests for CostTracker"""
    
    @pytest.fixture
    def store(self):
        """Create a temporary cost store"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield CostStore(Path(tmpdir) / "test_costs.db")
    
    @pytest.fixture
    def pricing(self):
        """Create a pricing service"""
        return PricingService()
    
    @pytest.fixture
    def tracker(self, store, pricing):
        """Create a cost tracker"""
        return CostTracker(store, pricing, enabled=True)
    
    def test_record_cost_basic(self, tracker):
        """Test basic cost recording"""
        record = tracker.record_cost(
            agent_name="test-agent",
            model="claude-3-5-sonnet-20241022",
            input_tokens=1000,
            output_tokens=500
        )
        
        assert record.id is not None
        assert record.agent_name == "test-agent"
        assert record.model == "claude-3-5-sonnet-20241022"
        assert record.input_tokens == 1000
        assert record.output_tokens == 500
        assert record.total_tokens == 1500
        assert record.total_cost > 0
    
    def test_record_cost_with_attribution(self, tracker):
        """Test cost recording with project and tags"""
        record = tracker.record_cost(
            agent_name="test-agent",
            model="claude-3-5-sonnet-20241022",
            input_tokens=1000,
            output_tokens=500,
            project="my-project",
            tags=["feature-x", "backend"]
        )
        
        assert record.project == "my-project"
        assert "feature-x" in record.tags
        assert "backend" in record.tags
    
    def test_record_cost_emits_event(self, tracker):
        """Test that recording cost emits an event"""
        events_received = []
        
        def handler(event):
            events_received.append(event)
        
        EventBus.subscribe(EventType.COST_RECORDED, handler)
        
        try:
            tracker.record_cost(
                agent_name="test-agent",
                model="claude-3-5-sonnet-20241022",
                input_tokens=1000,
                output_tokens=500
            )
            
            assert len(events_received) == 1
            event = events_received[0]
            assert event.type == EventType.COST_RECORDED
            assert "total_cost" in event.data
            assert "model" in event.data
        finally:
            EventBus.unsubscribe(EventType.COST_RECORDED, handler)
    
    def test_record_cost_when_disabled(self, store, pricing):
        """Test that costs are not recorded when disabled"""
        tracker = CostTracker(store, pricing, enabled=False)
        
        record = tracker.record_cost(
            agent_name="test-agent",
            model="claude-3-5-sonnet-20241022",
            input_tokens=1000,
            output_tokens=500
        )
        
        # Should return a zero-cost record
        assert record.total_cost == 0.0
    
    def test_get_summary(self, tracker):
        """Test getting cost summary"""
        # Record some costs
        for i in range(5):
            tracker.record_cost(
                agent_name=f"agent-{i}",
                model="claude-3-5-sonnet-20241022",
                input_tokens=1000,
                output_tokens=500,
                project="test-project"
            )
        
        # Get summary
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=1)
        summary = tracker.get_summary(start, end, project="test-project")
        
        assert summary.total_calls == 5
        assert summary.total_cost > 0
        assert summary.total_tokens == 7500  # 1500 * 5
        assert summary.avg_cost_per_call > 0
    
    def test_get_summary_with_filters(self, tracker):
        """Test summary with multiple filters"""
        # Record costs for different projects and models
        tracker.record_cost(
            agent_name="agent-1",
            model="claude-3-5-sonnet-20241022",
            input_tokens=1000,
            output_tokens=500,
            project="project-a"
        )
        tracker.record_cost(
            agent_name="agent-2",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            project="project-b"
        )
        
        # Get summary for project-a only
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=1)
        summary = tracker.get_summary(start, end, project="project-a")
        
        assert summary.total_calls == 1
        assert "project-a" in summary.by_project
    
    def test_tracking_context(self, tracker):
        """Test cost tracking context manager"""
        with tracker.tracking_context(project="my-project", tags=["test"]):
            # Context is set, but actual usage would be in agent calls
            pass
        
        # Context should be restored after exiting
        # This test mainly ensures no exceptions are raised
    
    def test_provider_auto_detection(self, tracker):
        """Test that provider is auto-detected from model"""
        record = tracker.record_cost(
            agent_name="test-agent",
            model="claude-3-5-sonnet-20241022",
            input_tokens=1000,
            output_tokens=500
        )
        
        assert record.provider == "anthropic"


class TestTrackingContext:
    """Test cost tracking context functionality (Issue #3)"""
    
    @pytest.fixture
    def store(self):
        """Create a temporary cost store"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield CostStore(Path(tmpdir) / "test_costs.db")
    
    @pytest.fixture
    def pricing(self):
        """Create a pricing service"""
        return PricingService()
    
    @pytest.fixture
    def tracker(self, store, pricing):
        """Create a cost tracker"""
        return CostTracker(store, pricing, enabled=True)
    
    def test_context_sets_project(self, tracker):
        """Test that tracking_context sets project default"""
        from startd8.costs import get_cost_context
        
        with tracker.tracking_context(project="my-app"):
            context = get_cost_context()
            assert context.get("project") == "my-app"
    
    def test_context_sets_tags(self, tracker):
        """Test that tracking_context sets tags"""
        from startd8.costs import get_cost_context
        
        with tracker.tracking_context(tags=["v1", "feature-x"]):
            context = get_cost_context()
            assert set(context.get("tags", [])) == {"v1", "feature-x"}
    
    def test_context_resets_on_exit(self, tracker):
        """Test that context is restored after exiting scope"""
        from startd8.costs import get_cost_context
        
        with tracker.tracking_context(project="app-a"):
            pass
        
        context = get_cost_context()
        assert context.get("project") is None
    
    def test_nested_context_merges_tags(self, tracker):
        """Test that nested contexts merge tags (decision A3)"""
        from startd8.costs import get_cost_context
        
        with tracker.tracking_context(tags=["v1"]):
            context1 = get_cost_context()
            assert context1.get("tags") == ["v1"]
            
            with tracker.tracking_context(tags=["v2"]):
                context2 = get_cost_context()
                # Tags should be merged (deduplicated)
                assert set(context2.get("tags", [])) == {"v1", "v2"}
            
            # Back to outer context
            context3 = get_cost_context()
            assert context3.get("tags") == ["v1"]
    
    def test_nested_context_overrides_project(self, tracker):
        """Test that nested contexts override project (decision A3)"""
        from startd8.costs import get_cost_context
        
        with tracker.tracking_context(project="app-a"):
            assert get_cost_context().get("project") == "app-a"
            
            with tracker.tracking_context(project="app-b"):
                # Inner project overrides outer
                assert get_cost_context().get("project") == "app-b"
            
            # Outer project restored
            assert get_cost_context().get("project") == "app-a"
    
    def test_record_cost_uses_context_defaults(self, tracker):
        """Test that record_cost() applies context defaults"""
        with tracker.tracking_context(project="my-app", tags=["v1"]):
            record = tracker.record_cost(
                agent_name="claude",
                model="claude-3-5-sonnet-20241022",
                input_tokens=100,
                output_tokens=50
            )
            
            assert record.project == "my-app"
            assert "v1" in record.tags
    
    def test_record_cost_merges_explicit_and_context_tags(self, tracker):
        """Test that explicit tags merge with context tags"""
        with tracker.tracking_context(tags=["v1"]):
            record = tracker.record_cost(
                agent_name="claude",
                model="claude-3-5-sonnet-20241022",
                input_tokens=100,
                output_tokens=50,
                tags=["feature-x"]  # Explicit tags
            )
            
            # Both tags should be present (merged)
            assert set(record.tags) == {"v1", "feature-x"}
    
    def test_explicit_project_overrides_context(self, tracker):
        """Test that explicit project overrides context default"""
        with tracker.tracking_context(project="default-app"):
            record = tracker.record_cost(
                agent_name="claude",
                model="claude-3-5-sonnet-20241022",
                input_tokens=100,
                output_tokens=50,
                project="override-app"  # Explicit project
            )
            
            assert record.project == "override-app"
    
    def test_context_works_across_multiple_calls(self, tracker):
        """Test that context persists across multiple cost records"""
        with tracker.tracking_context(project="my-app", tags=["batch-1"]):
            record1 = tracker.record_cost(
                agent_name="claude",
                model="claude-3-5-sonnet-20241022",
                input_tokens=100,
                output_tokens=50
            )
            
            record2 = tracker.record_cost(
                agent_name="gpt4",
                model="gpt-4o",
                input_tokens=200,
                output_tokens=100
            )
            
            # Both records should have the context defaults
            assert record1.project == "my-app"
            assert record2.project == "my-app"
            assert "batch-1" in record1.tags
            assert "batch-1" in record2.tags
    
    def test_helper_functions_accessible(self, tracker):
        """Test that context helper functions are accessible from module"""
        from startd8.costs import get_cost_context, set_cost_context, clear_cost_context
        
        # Should not raise ImportError
        set_cost_context(project="test")
        assert get_cost_context().get("project") == "test"
        
        clear_cost_context()
        assert get_cost_context().get("project") is None
    
    def test_deeply_nested_contexts(self, tracker):
        """Test context behavior with 3+ nesting levels"""
        from startd8.costs import get_cost_context
        
        with tracker.tracking_context(project="level1", tags=["a"]):
            assert get_cost_context().get("project") == "level1"
            assert set(get_cost_context().get("tags", [])) == {"a"}
            
            with tracker.tracking_context(tags=["b"]):
                assert get_cost_context().get("project") == "level1"
                assert set(get_cost_context().get("tags", [])) == {"a", "b"}
                
                with tracker.tracking_context(project="level3", tags=["c"]):
                    assert get_cost_context().get("project") == "level3"
                    assert set(get_cost_context().get("tags", [])) == {"a", "b", "c"}
                
                # Back to level 2
                assert get_cost_context().get("project") == "level1"
                assert set(get_cost_context().get("tags", [])) == {"a", "b"}
            
            # Back to level 1
            assert get_cost_context().get("project") == "level1"
            assert set(get_cost_context().get("tags", [])) == {"a"}

