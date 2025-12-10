"""
Unit tests for BudgetManager
"""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile

from startd8.costs.budget import BudgetManager, BudgetExceededError
from startd8.costs.store import CostStore
from startd8.costs.models import CostPeriod, CostRecord
from startd8.events import EventBus, EventType


class TestBudgetManager:
    """Tests for BudgetManager"""
    
    @pytest.fixture
    def store(self):
        """Create a temporary cost store"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_budgets.db"
            yield CostStore(db_path)
    
    @pytest.fixture
    def manager(self, store):
        """Create a budget manager"""
        return BudgetManager(store)
    
    def test_create_budget(self, manager):
        """Test creating a budget"""
        budget = manager.create_budget(
            name="Test Budget",
            period=CostPeriod.MONTHLY,
            limit_amount=100.0,
            warning_threshold=0.8
        )
        
        assert budget.id is not None
        assert budget.name == "Test Budget"
        assert budget.period == CostPeriod.MONTHLY
        assert budget.limit_amount == 100.0
        assert budget.warning_threshold == 0.8
        assert budget.is_active is True
    
    def test_create_budget_with_scope(self, manager):
        """Test creating a budget with scope filters"""
        budget = manager.create_budget(
            name="Project Budget",
            period=CostPeriod.DAILY,
            limit_amount=10.0,
            scope_project="my-project",
            scope_model="claude-3-5-sonnet-20241022",
            scope_tags=["production"]
        )
        
        assert budget.scope_project == "my-project"
        assert budget.scope_model == "claude-3-5-sonnet-20241022"
        assert "production" in budget.scope_tags
    
    def test_list_budgets(self, manager):
        """Test listing budgets"""
        # Create some budgets
        manager.create_budget("Budget 1", CostPeriod.DAILY, 10.0)
        manager.create_budget("Budget 2", CostPeriod.MONTHLY, 100.0)
        
        budgets = manager.list_budgets()
        assert len(budgets) == 2
    
    def test_delete_budget(self, manager):
        """Test deleting a budget"""
        budget = manager.create_budget("Test Budget", CostPeriod.DAILY, 10.0)
        
        # Delete it
        result = manager.delete_budget(budget.id)
        assert result is True
        
        # Should not be in list anymore
        budgets = manager.list_budgets()
        assert len(budgets) == 0
    
    def test_get_budget_status(self, manager, store):
        """Test getting budget status"""
        # Create a budget
        budget = manager.create_budget(
            name="Test Budget",
            period=CostPeriod.DAILY,
            limit_amount=1.0  # $1 limit
        )
        
        # Record some costs
        cost_record = CostRecord(
            agent_name="test-agent",
            model="claude-3-5-sonnet-20241022",
            provider="anthropic",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            input_cost=0.003,
            output_cost=0.0075,
            total_cost=0.0105
        )
        store.save(cost_record)
        
        # Get status
        status = manager.get_budget_status(budget.id)
        assert status is not None
        assert status.current_spend > 0
        assert status.remaining < 1.0
        assert not status.is_exceeded
    
    def test_check_budget_no_exceed(self, manager, store):
        """Test budget check when under limit"""
        # Create a high budget
        manager.create_budget("Test Budget", CostPeriod.DAILY, 100.0)
        
        # Check should pass
        warnings = manager.check_budget(
            model="claude-3-5-sonnet-20241022",
            estimated_cost=0.01
        )
        
        # Should not raise exception
        assert isinstance(warnings, list)
    
    def test_check_budget_warning(self, manager, store):
        """Test budget check when at warning threshold"""
        # Create a budget
        budget = manager.create_budget(
            name="Test Budget",
            period=CostPeriod.DAILY,
            limit_amount=1.0,
            warning_threshold=0.8
        )
        
        # Record costs to reach 80%
        cost_record = CostRecord(
            agent_name="test-agent",
            model="claude-3-5-sonnet-20241022",
            provider="anthropic",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            input_cost=0.4,
            output_cost=0.4,
            total_cost=0.8
        )
        store.save(cost_record)
        
        # Check should return warnings
        warnings = manager.check_budget(
            model="claude-3-5-sonnet-20241022",
            estimated_cost=0.0
        )
        
        assert len(warnings) > 0
    
    def test_check_budget_blocking(self, manager, store):
        """Test that budget check blocks when exceeded"""
        # Create a blocking budget
        manager.create_budget(
            name="Test Budget",
            period=CostPeriod.DAILY,
            limit_amount=0.01,  # Very low limit
            block_on_exceed=True
        )
        
        # Record costs that exceed the budget
        cost_record = CostRecord(
            agent_name="test-agent",
            model="claude-3-5-sonnet-20241022",
            provider="anthropic",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            input_cost=0.006,
            output_cost=0.006,
            total_cost=0.012
        )
        store.save(cost_record)
        
        # Check should raise exception
        with pytest.raises(BudgetExceededError):
            manager.check_budget(
                model="claude-3-5-sonnet-20241022",
                estimated_cost=0.0
            )
    
    def test_budget_emits_events(self, manager):
        """Test that budget operations emit events"""
        events_received = []
        
        def handler(event):
            events_received.append(event)
        
        EventBus.subscribe(EventType.BUDGET_CREATED, handler)
        
        try:
            manager.create_budget("Test Budget", CostPeriod.DAILY, 10.0)
            
            assert len(events_received) == 1
            assert events_received[0].type == EventType.BUDGET_CREATED
        finally:
            EventBus.unsubscribe(EventType.BUDGET_CREATED, handler)
    
    def test_scoped_budget_matching(self, manager, store):
        """Test that scoped budgets only apply to matching costs"""
        # Create a project-specific budget
        manager.create_budget(
            name="Project Budget",
            period=CostPeriod.DAILY,
            limit_amount=0.01,
            scope_project="project-a",
            block_on_exceed=True
        )
        
        # Check for a different project should pass
        warnings = manager.check_budget(
            project="project-b",
            estimated_cost=1.0  # High cost, but different project
        )
        
        # Should not raise exception since budget doesn't apply
        assert isinstance(warnings, list)

