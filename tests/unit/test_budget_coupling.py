"""
Tests for budget and cost-tracker coupling behavior (Issue 2).
"""

import tempfile
from pathlib import Path

import pytest

from startd8.agents import MockAgent
from startd8.costs.tracker import CostTracker
from startd8.costs.store import CostStore
from startd8.costs.pricing import PricingService
from startd8.costs.budget import BudgetManager, BudgetExceededError
from startd8.costs.models import CostPeriod


class TestBudgetCostTrackerCoupling:
    """Test that budget enforcement works independently from cost tracking (Issue 3)"""

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
    def cost_tracker(self, store, pricing):
        """Create a cost tracker"""
        return CostTracker(store, pricing, enabled=True)

    @pytest.fixture
    def budget_manager(self, store):
        """Create a budget manager"""
        return BudgetManager(store=store)

    def test_budget_check_without_cost_tracker(self, budget_manager):
        """Budget enforcement should run without cost_tracker"""
        budget_manager.create_budget(
            name="test-budget",
            period=CostPeriod.DAILY,
            limit_amount=100.0,
            block_on_exceed=False,
            scope_project="test-project"
        )

        agent = MockAgent(name="test-agent", model="mock-model")
        agent.budget_manager = budget_manager
        agent.cost_tracker = None

        response = agent.create_response(
            prompt_id="test-123",
            prompt="Test prompt",
            project="test-project"
        )

        assert response is not None
        assert len(response.response) > 0

    def test_budget_enforcement_without_cost_tracker(self, budget_manager):
        """Blocking budgets should still raise when no cost_tracker"""
        budget_manager.create_budget(
            name="test-budget",
            period=CostPeriod.DAILY,
            limit_amount=0.0001,
            block_on_exceed=True,
            scope_project="test-project"
        )

        agent = MockAgent(name="test-agent", model="mock-model")
        agent.budget_manager = budget_manager
        agent.cost_tracker = None

        with pytest.raises(BudgetExceededError):
            agent.create_response(
                prompt_id="test-123",
                prompt="Test prompt",
                project="test-project"
            )

    def test_budget_with_cost_tracker_and_budget_manager(self, budget_manager, store, pricing):
        """Budget enforcement works with both budget_manager and cost_tracker"""
        cost_tracker = CostTracker(store, pricing, enabled=True)

        budget_manager.create_budget(
            name="test-budget",
            period=CostPeriod.DAILY,
            limit_amount=0.0001,
            block_on_exceed=True,
            scope_project="test-project"
        )

        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        agent.budget_manager = budget_manager

        with pytest.raises(BudgetExceededError):
            agent.create_response(
                prompt_id="test-123",
                prompt="Test prompt",
                project="test-project"
            )

    def test_budget_uses_pricing_service_without_cost_tracker(self, budget_manager):
        """Budget checks should leverage PricingService when cost_tracker absent"""
        budget_manager.create_budget(
            name="test-budget",
            period=CostPeriod.DAILY,
            limit_amount=100.0,
            block_on_exceed=False,
            scope_project="test-project"
        )

        agent = MockAgent(name="test-agent", model="mock-model")
        agent.budget_manager = budget_manager
        agent.cost_tracker = None

        response = agent.create_response(
            prompt_id="test-123",
            prompt="Test prompt",
            project="test-project"
        )

        assert response is not None

    @pytest.mark.asyncio
    async def test_async_budget_without_cost_tracker(self, budget_manager):
        """Async path should enforce budget without cost_tracker"""
        budget_manager.create_budget(
            name="test-budget",
            period=CostPeriod.DAILY,
            limit_amount=0.0001,
            block_on_exceed=True,
            scope_project="test-project"
        )

        agent = MockAgent(name="test-agent", model="mock-model")
        agent.budget_manager = budget_manager
        agent.cost_tracker = None

        with pytest.raises(BudgetExceededError):
            await agent.acreate_response(
                prompt_id="test-123",
                prompt="Test prompt",
                project="test-project"
            )

    def test_budget_ignores_missing_project(self, budget_manager):
        """Budget check should be skipped when project missing"""
        budget_manager.create_budget(
            name="test-budget",
            period=CostPeriod.DAILY,
            limit_amount=0.0001,
            block_on_exceed=True,
            scope_project="test-project"
        )

        agent = MockAgent(name="test-agent", model="mock-model")
        agent.budget_manager = budget_manager
        agent.cost_tracker = None

        # Missing project means budget check should be skipped
        response = agent.create_response(
            prompt_id="test-123",
            prompt="Test prompt",
            project=None
        )

        assert response is not None

    def test_budget_enforcement_respects_scope(self, budget_manager):
        """Budget scoped to project should not block other projects"""
        budget_manager.create_budget(
            name="test-budget",
            period=CostPeriod.DAILY,
            limit_amount=0.0001,
            block_on_exceed=True,
            scope_project="project-a"
        )

        agent = MockAgent(name="test-agent", model="mock-model")
        agent.budget_manager = budget_manager
        agent.cost_tracker = None

        # Different project should not trigger the budget
        response = agent.create_response(
            prompt_id="test-123",
            prompt="Test prompt",
            project="project-b"
        )

        assert response is not None
        assert len(response.response) > 0

    def test_budget_works_with_cost_tracking_context(self, cost_tracker, budget_manager):
        """Budget should still work when both trackers configured"""
        budget_manager.create_budget(
            name="test-budget",
            period=CostPeriod.DAILY,
            limit_amount=100.0,
            block_on_exceed=False,
            scope_project="test-project"
        )

        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        agent.budget_manager = budget_manager

        response = agent.create_response(
            prompt_id="test-123",
            prompt="Test prompt",
            project="test-project"
        )

        assert response is not None
        assert len(response.response) > 0

    @pytest.mark.asyncio
    async def test_budget_enforcement_with_cost_tracking_context(self, cost_tracker, budget_manager):
        """Async budget enforcement should work with both trackers"""
        budget_manager.create_budget(
            name="test-budget",
            period=CostPeriod.DAILY,
            limit_amount=0.0001,
            block_on_exceed=True,
            scope_project="test-project"
        )

        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        agent.budget_manager = budget_manager

        with pytest.raises(BudgetExceededError):
            await agent.acreate_response(
                prompt_id="test-123",
                prompt="Test prompt",
                project="test-project"
            )
