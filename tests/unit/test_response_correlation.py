"""
Tests for response/cost correlation and ID linkage (Issue 3).
"""

import tempfile
from pathlib import Path

import pytest

from startd8.agents import MockAgent, BaseAgent
from startd8.costs.tracker import CostTracker
from startd8.costs.store import CostStore
from startd8.costs.pricing import PricingService
from startd8.costs.budget import BudgetManager
from startd8.costs.models import CostPeriod


class TestResponseCorrelation:
    """Verify response IDs correlate correctly with cost records."""

    @pytest.fixture
    def store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield CostStore(Path(tmpdir) / "test_costs.db")

    @pytest.fixture
    def pricing(self):
        return PricingService()

    @pytest.fixture
    def cost_tracker(self, store, pricing):
        return CostTracker(store, pricing, enabled=True)

    @pytest.fixture
    def budget_manager(self, store):
        return BudgetManager(store=store)

    def test_response_id_linkage_sync(self, cost_tracker):
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker

        response = agent.create_response(
            prompt_id="test-123",
            prompt="Test prompt"
        )

        records = cost_tracker.store.query()
        assert len(records) > 0, "No cost records found"
        cost_record = records[-1]

        assert response.id == cost_record.response_id

    @pytest.mark.asyncio
    async def test_response_id_linkage_async(self, cost_tracker):
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker

        response = await agent.acreate_response(
            prompt_id="test-async-123",
            prompt="Test async prompt"
        )

        records = cost_tracker.store.query()
        assert len(records) > 0, "No cost records found"
        cost_record = records[-1]

        assert response.id == cost_record.response_id

    def test_response_id_uniqueness_across_calls(self, cost_tracker):
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker

        response_ids = []
        for i in range(5):
            response = agent.create_response(
                prompt_id=f"test-{i}",
                prompt=f"Test prompt {i}"
            )
            response_ids.append(response.id)

        assert len(response_ids) == len(set(response_ids))

        records = cost_tracker.store.query()
        for i, cost_record in enumerate(records):
            assert response_ids[i] == cost_record.response_id

    @pytest.mark.parametrize("use_cost_tracker,use_budget_manager", [
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    ])
    def test_response_id_linkage_sync_matrix(self, store, pricing, use_cost_tracker, use_budget_manager):
        cost_tracker = CostTracker(store, pricing, enabled=True) if use_cost_tracker else None
        budget_manager = BudgetManager(store=store) if use_budget_manager else None

        if use_budget_manager:
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
            project="test-project" if use_budget_manager else None
        )

        assert response is not None
        assert response.id is not None

        if use_cost_tracker:
            records = cost_tracker.store.query()
            assert len(records) > 0
            cost_record = records[-1]
            assert response.id == cost_record.response_id

    @pytest.mark.parametrize("use_cost_tracker,use_budget_manager", [
        (True, True),
        (True, False),
        (False, True),
        (False, False),
    ])
    @pytest.mark.asyncio
    async def test_response_id_linkage_async_matrix(self, store, pricing, use_cost_tracker, use_budget_manager):
        cost_tracker = CostTracker(store, pricing, enabled=True) if use_cost_tracker else None
        budget_manager = BudgetManager(store=store) if use_budget_manager else None

        if use_budget_manager:
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

        response = await agent.acreate_response(
            prompt_id="test-async-123",
            prompt="Test async prompt",
            project="test-project" if use_budget_manager else None
        )

        assert response is not None
        assert response.id is not None

        if use_cost_tracker:
            records = cost_tracker.store.query()
            assert len(records) > 0
            cost_record = records[-1]
            assert response.id == cost_record.response_id

    def test_response_id_uniqueness_stress_test(self, cost_tracker):
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker

        response_ids = []
        for i in range(50):
            response = agent.create_response(
                prompt_id=f"prompt-{i}",
                prompt=f"Test prompt {i}"
            )
            response_ids.append(response.id)

        assert len(response_ids) == len(set(response_ids))

        records = cost_tracker.store.query()
        assert len(records) == 50

        record_ids = {r.response_id for r in records}
        assert record_ids == set(response_ids)
