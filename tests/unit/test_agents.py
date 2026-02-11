"""
Unit tests for agent implementations
"""

import pytest
import asyncio
from pathlib import Path
import tempfile
from unittest.mock import Mock, MagicMock, patch

from startd8.agents import MockAgent, BaseAgent
from startd8.models import TokenUsage, GenerateResult
from startd8.exceptions import APIError
from startd8.costs.tracker import CostTracker
from startd8.costs.store import CostStore
from startd8.costs.pricing import PricingService
from startd8.costs.budget import BudgetManager, BudgetExceededError
from startd8.costs.models import CostPeriod
from startd8.events import EventBus, EventType


class TestMockAgent:
    """Test MockAgent implementation"""
    
    def test_mock_agent_initialization(self):
        """Test creating a mock agent"""
        agent = MockAgent(name="test-mock", model="test-model")
        assert agent.name == "test-mock"
        assert agent.model == "test-model"
    
    def test_mock_agent_generate(self):
        """Test mock agent generation"""
        agent = MockAgent()
        response_text, response_time_ms, token_usage = agent.generate("Test prompt")
        
        assert isinstance(response_text, str)
        assert response_time_ms > 0
        assert isinstance(token_usage, TokenUsage)
        assert token_usage.total > 0
    
    def test_mock_agent_create_response(self):
        """Test creating a response object"""
        agent = MockAgent()
        response = agent.create_response(
            prompt_id="test-123",
            prompt="Test prompt"
        )
        
        assert response.prompt_id == "test-123"
        assert response.agent_name == agent.name
        assert response.model == agent.model
        assert len(response.response) > 0


class TestBaseAgent:
    """Test BaseAgent abstract class"""
    
    def test_base_agent_cannot_be_instantiated(self):
        """Test that BaseAgent cannot be instantiated directly"""
        with pytest.raises(TypeError):
            BaseAgent(name="test", model="test")
    
    def test_base_agent_requires_agenerate_implementation(self):
        """Test that subclasses must implement agenerate"""
        class IncompleteAgent(BaseAgent):
            pass
        
        with pytest.raises(TypeError):
            IncompleteAgent(name="test", model="test")


class TestAsyncAgents:
    """Test async agent functionality"""
    
    @pytest.mark.asyncio
    async def test_mock_agent_agenerate(self):
        """Test async generation with mock agent"""
        agent = MockAgent()
        response_text, response_time_ms, token_usage = await agent.agenerate("Test prompt")
        
        assert isinstance(response_text, str)
        assert response_time_ms > 0
        assert isinstance(token_usage, TokenUsage)
        assert token_usage.total > 0
    
    @pytest.mark.asyncio
    async def test_mock_agent_acreate_response(self):
        """Test async response creation"""
        agent = MockAgent()
        response = await agent.acreate_response(
            prompt_id="test-async-123",
            prompt="Test async prompt"
        )
        
        assert response.prompt_id == "test-async-123"
        assert response.agent_name == agent.name
        assert response.model == agent.model
        assert len(response.response) > 0
    
    @pytest.mark.asyncio
    async def test_parallel_agent_calls(self):
        """Test running multiple agents in parallel"""
        agents = [MockAgent(name=f"agent-{i}") for i in range(3)]
        
        # Run all agents in parallel
        tasks = [agent.agenerate("Test prompt") for agent in agents]
        results = await asyncio.gather(*tasks)
        
        assert len(results) == 3
        for response_text, response_time_ms, token_usage in results:
            assert isinstance(response_text, str)
            assert response_time_ms > 0
            assert isinstance(token_usage, TokenUsage)
    
    def test_sync_wrapper_calls_async(self):
        """Test that sync generate method properly wraps async"""
        agent = MockAgent()
        response_text, response_time_ms, token_usage = agent.generate("Test prompt")
        
        assert isinstance(response_text, str)
        assert response_time_ms > 0
        assert isinstance(token_usage, TokenUsage)


class TestAgentCostTracking:
    """Test agent integration with cost tracking and budget enforcement (Phase 2 - Issue #1)"""
    
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
    
    @pytest.fixture
    def agent_with_tracking(self, cost_tracker, budget_manager):
        """Create a mock agent with cost tracking"""
        return MockAgent(
            name="tracked-agent",
            model="mock-model"
        )
    
    def test_agent_accepts_cost_tracker_and_budget_manager(self, cost_tracker, budget_manager):
        """Test that agent can be initialized with cost tracker and budget manager"""
        agent = MockAgent(name="test", model="test-model")
        agent.cost_tracker = cost_tracker
        agent.budget_manager = budget_manager
        
        assert agent.cost_tracker is cost_tracker
        assert agent.budget_manager is budget_manager
    
    def test_agent_works_without_cost_tracker(self):
        """Test that agent works gracefully when cost_tracker is None"""
        agent = MockAgent(name="test", model="test-model")
        
        response = agent.create_response(
            prompt_id="test-123",
            prompt="Test prompt"
        )
        
        assert response.prompt_id == "test-123"
        assert len(response.response) > 0
    
    def test_agent_works_without_budget_manager(self, cost_tracker):
        """Test that agent works and records cost without budget_manager"""
        agent = MockAgent(name="test", model="test-model")
        agent.cost_tracker = cost_tracker
        
        response = agent.create_response(
            prompt_id="test-123",
            prompt="Test prompt"
        )
        
        assert response.prompt_id == "test-123"
        assert len(response.response) > 0
    
    @pytest.mark.asyncio
    async def test_async_cost_recording(self, cost_tracker):
        """Test that async response creation records cost"""
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        
        response = await agent.acreate_response(
            prompt_id="test-123",
            prompt="Test prompt"
        )
        
        assert response.prompt_id == "test-123"
        assert response.token_usage is not None
        assert response.token_usage.input > 0
        assert response.token_usage.output > 0
    
    def test_sync_cost_recording(self, cost_tracker):
        """Test that sync response creation records cost"""
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        
        response = agent.create_response(
            prompt_id="test-123",
            prompt="Test prompt"
        )
        
        assert response.prompt_id == "test-123"
        assert response.token_usage is not None
        assert response.token_usage.input > 0
        assert response.token_usage.output > 0
    
    def test_budget_warning_with_non_blocking(self, cost_tracker, budget_manager):
        """Test that non-blocking budget warning allows flow to continue"""
        # Create a budget that will be exceeded
        budget = budget_manager.create_budget(
            name="test-budget",
            period=CostPeriod.DAILY,
            limit_amount=0.001,  # Very small budget
            block_on_exceed=False  # Non-blocking (default)
        )
        
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        agent.budget_manager = budget_manager
        
        # Should not raise an exception (non-blocking)
        response = agent.create_response(
            prompt_id="test-123",
            prompt="Test prompt"
        )
        
        assert response is not None
        assert len(response.response) > 0
    
    def test_budget_check_before_api_call(self, cost_tracker, budget_manager):
        """Test that budget check happens before API call"""
        # Create a budget that will be exceeded
        budget = budget_manager.create_budget(
            name="test-budget",
            period=CostPeriod.DAILY,
            limit_amount=0.001,  # Very small budget
            block_on_exceed=True,  # Blocking
            scope_project="test-project"  # Scope to specific project
        )
        
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        agent.budget_manager = budget_manager
        
        # Should raise BudgetExceededError before making the call
        with pytest.raises(BudgetExceededError):
            agent.create_response(
                prompt_id="test-123",
                prompt="Test prompt",
                project="test-project"  # Match the budget scope
            )
    
    @pytest.mark.asyncio
    async def test_async_budget_check(self, cost_tracker, budget_manager):
        """Test that async path also respects budget enforcement"""
        # Create a budget that will be exceeded
        budget = budget_manager.create_budget(
            name="test-budget",
            period=CostPeriod.DAILY,
            limit_amount=0.001,  # Very small budget
            block_on_exceed=True,  # Blocking
            scope_project="test-project"  # Scope to specific project
        )
        
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        agent.budget_manager = budget_manager
        
        # Should raise BudgetExceededError
        with pytest.raises(BudgetExceededError):
            await agent.acreate_response(
                prompt_id="test-123",
                prompt="Test prompt",
                project="test-project"  # Match the budget scope
            )
    
    def test_cost_record_includes_token_usage(self, cost_tracker):
        """Test that recorded cost includes token usage from response"""
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        
        response = agent.create_response(
            prompt_id="test-123",
            prompt="Test prompt"
        )
        
        # Cost should be recorded with token usage
        assert response.token_usage is not None
        assert response.token_usage.input > 0
        assert response.token_usage.output > 0
        
        # Verify it was actually recorded in the store
        records = cost_tracker.store.query()
        assert len(records) > 0
    
    def test_cost_event_emission(self, cost_tracker):
        """Test that COST_RECORDED event is emitted"""
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        
        # Track emitted events
        events_received = []
        
        def event_handler(event):
            events_received.append(event)
        
        EventBus.subscribe(EventType.COST_RECORDED, event_handler)
        
        try:
            response = agent.create_response(
                prompt_id="test-123",
                prompt="Test prompt"
            )
            
            # Should have emitted COST_RECORDED event
            assert len(events_received) > 0
            cost_event = events_received[0]
            assert cost_event.type == EventType.COST_RECORDED
        finally:
            EventBus.unsubscribe(EventType.COST_RECORDED, event_handler)
    
    def test_project_and_tags_flow_to_cost_record(self, cost_tracker):
        """Test that project and tags are applied to cost record"""
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        
        response = agent.create_response(
            prompt_id="test-123",
            prompt="Test prompt",
            metadata={"project": "my-project", "tags": ["v1", "feature-x"]}
        )
        
        # Verify cost was recorded with metadata
        records = cost_tracker.store.query()
        assert len(records) > 0
    
    def test_multiple_sequential_calls(self, cost_tracker):
        """Test that context persists and costs are recorded for multiple calls"""
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        
        # Make multiple calls
        response1 = agent.create_response(
            prompt_id="test-1",
            prompt="First prompt"
        )
        
        response2 = agent.create_response(
            prompt_id="test-2",
            prompt="Second prompt"
        )
        
        # Both should be recorded
        records = cost_tracker.store.query()
        assert len(records) >= 2
    
    @pytest.mark.asyncio
    async def test_async_sync_parity(self, cost_tracker):
        """Test that async and sync paths produce identical behavior"""
        # Create two identical agents
        agent_sync = MockAgent(name="sync-agent", model="mock-model")
        agent_sync.cost_tracker = cost_tracker
        
        agent_async = MockAgent(name="async-agent", model="mock-model")
        agent_async.cost_tracker = cost_tracker
        
        # Make sync call
        response_sync = agent_sync.create_response(
            prompt_id="sync-test",
            prompt="Test prompt"
        )
        
        # Make async call
        response_async = await agent_async.acreate_response(
            prompt_id="async-test",
            prompt="Test prompt"
        )
        
        # Both should have recorded costs
        records = cost_tracker.store.query()
        assert len(records) >= 2
        
        # Token usage should be similar (same model, same prompt)
        assert response_sync.token_usage.total > 0
        assert response_async.token_usage.total > 0
    
    def test_metadata_passed_to_cost_record(self, cost_tracker):
        """Test that metadata is passed through to cost record"""
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        
        metadata = {
            "custom_field": "custom_value",
            "request_id": "req-123"
        }
        
        response = agent.create_response(
            prompt_id="test-123",
            prompt="Test prompt",
            metadata=metadata
        )
        
        # Verify metadata was recorded
        records = cost_tracker.store.query()
        assert len(records) > 0
        assert records[0].metadata is not None
    
    @pytest.mark.asyncio
    async def test_cost_tracking_with_context_defaults(self, cost_tracker):
        """Test that cost tracking respects context defaults from Issue #3"""
        from startd8.costs import set_cost_context, get_cost_context, clear_cost_context
        
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        
        try:
            # Set context defaults
            set_cost_context(project="context-project", tags=["context-tag"])
            
            # Make a call
            response = await agent.acreate_response(
                prompt_id="test-123",
                prompt="Test prompt"
            )
            
            # Cost should be recorded
            assert response is not None
            records = cost_tracker.store.query()
            assert len(records) > 0
            
        finally:
            clear_cost_context()
    
    def test_cost_tracker_disabled_graceful(self):
        """Test that agent works when cost tracking is disabled"""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CostStore(Path(tmpdir) / "test_costs.db")
            pricing = PricingService()
            cost_tracker = CostTracker(store, pricing, enabled=False)
            
            agent = MockAgent(name="test-agent", model="mock-model")
            agent.cost_tracker = cost_tracker
            
            # Should not raise an error
            response = agent.create_response(
                prompt_id="test-123",
                prompt="Test prompt"
            )
            
            assert response is not None
    
    def test_concurrent_cost_tracking(self, cost_tracker):
        """Test that concurrent calls are tracked correctly"""
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        
        # Make multiple concurrent-ish calls
        responses = []
        for i in range(3):
            response = agent.create_response(
                prompt_id=f"test-{i}",
                prompt=f"Test prompt {i}"
            )
            responses.append(response)
        
        # All should be recorded
        records = cost_tracker.store.query()
        assert len(records) >= 3
    
    @pytest.mark.asyncio
    async def test_error_handling_in_cost_tracking(self, cost_tracker):
        """Test that errors in API call don't break cost tracking"""
        # Create a mock agent that raises an error
        class ErrorAgent(BaseAgent):
            async def agenerate(self, prompt: str):
                raise RuntimeError("Simulated API error")
        
        agent = ErrorAgent(name="error-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        
        # Should raise the error, but not crash the cost tracking system
        with pytest.raises(RuntimeError):
            await agent.acreate_response(
                prompt_id="test-123",
                prompt="Test prompt"
            )
    
    def test_response_id_linkage_sync(self, cost_tracker):
        """
        Regression test for Issue 1: Response ID Linkage
        
        Verifies that the same response_id is used in both:
        1. The cost record stored in the cost tracker
        2. The AgentResponse object returned to the caller
        
        This ensures analytics and auditing can correlate cost records with responses.
        """
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        
        # Make a call
        response = agent.create_response(
            prompt_id="test-123",
            prompt="Test prompt"
        )
        
        # Get the recorded cost
        records = cost_tracker.store.query()
        assert len(records) > 0, "No cost records found"
        cost_record = records[-1]  # Get the latest record
        
        # Verify response_id matches between AgentResponse and cost record
        assert response.id == cost_record.response_id, \
            f"Response ID mismatch: response.id={response.id} vs cost_record.response_id={cost_record.response_id}"
    
    @pytest.mark.asyncio
    async def test_response_id_linkage_async(self, cost_tracker):
        """
        Regression test for Issue 1: Response ID Linkage (async version)
        
        Verifies that the same response_id is used in both:
        1. The cost record stored in the cost tracker
        2. The AgentResponse object returned to the caller
        
        This ensures analytics and auditing can correlate cost records with responses.
        """
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        
        # Make a call
        response = await agent.acreate_response(
            prompt_id="test-async-123",
            prompt="Test async prompt"
        )
        
        # Get the recorded cost
        records = cost_tracker.store.query()
        assert len(records) > 0, "No cost records found"
        cost_record = records[-1]  # Get the latest record
        
        # Verify response_id matches between AgentResponse and cost record
        assert response.id == cost_record.response_id, \
            f"Response ID mismatch: response.id={response.id} vs cost_record.response_id={cost_record.response_id}"
    
    def test_response_id_uniqueness_across_calls(self, cost_tracker):
        """
        Verify that each call generates a unique response_id
        """
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        
        # Make multiple calls
        response_ids = []
        for i in range(5):
            response = agent.create_response(
                prompt_id=f"test-{i}",
                prompt=f"Test prompt {i}"
            )
            response_ids.append(response.id)
        
        # All response IDs should be unique
        assert len(response_ids) == len(set(response_ids)), \
            "Response IDs should be unique across different calls"
        
        # Each response ID should match its corresponding cost record
        records = cost_tracker.store.query()
        for i, cost_record in enumerate(records):
            assert response_ids[i] == cost_record.response_id, \
                f"Call {i}: Response ID mismatch"


class TestGeminiAgent:
    """Test Gemini agent implementation"""
    
    def test_gemini_agent_requires_package(self):
        """Test that GeminiAgent raises ImportError if google-generativeai not installed"""
        # This test verifies the error handling exists
        # Actual test would require mocking _GEMINI_AVAILABLE to False
        from startd8.agents.gemini import _GEMINI_AVAILABLE

        # If package is installed, we can't test the ImportError in this environment
        # But we verify the import guard exists
        if _GEMINI_AVAILABLE:
            # If available, instantiation should work (without valid API key)
            from startd8.agents import GeminiAgent
            import os
            # Clear API key from environment to test validation
            old_key = os.environ.pop('GOOGLE_API_KEY', None)
            try:
                # This will raise ValueError about API key, not ImportError
                # which means the ImportError guard works
                with pytest.raises(ValueError, match="Google API key required"):
                    GeminiAgent(name="test-gemini", model="gemini-2.0-flash")
            finally:
                if old_key:
                    os.environ['GOOGLE_API_KEY'] = old_key
        else:
            # If not available, ImportError should be raised
            from startd8.agents import GeminiAgent
            with pytest.raises(ImportError, match="google-genai"):
                GeminiAgent(name="test-gemini", model="gemini-2.0-flash")
    
    def test_gemini_agent_api_key_validation(self):
        """Test that GeminiAgent validates API key"""
        from startd8.agents import GeminiAgent
        from startd8.agents.gemini import _GEMINI_AVAILABLE
        import os

        if not _GEMINI_AVAILABLE:
            pytest.skip("google-generativeai not installed")

        # Clear API key from environment to test validation
        old_key = os.environ.pop('GOOGLE_API_KEY', None)
        try:
            # Test ValueError when API key is missing
            with pytest.raises(ValueError, match="Google API key required"):
                GeminiAgent(
                    name="test-gemini",
                    model="gemini-2.0-flash",
                    api_key=None  # No API key provided
                )
        finally:
            if old_key:
                os.environ['GOOGLE_API_KEY'] = old_key
    
    def test_gemini_agent_with_mock(self):
        """Test GeminiAgent with mocked google-generativeai"""
        from startd8.agents import GeminiAgent
        from startd8.agents.gemini import _GEMINI_AVAILABLE

        if not _GEMINI_AVAILABLE:
            pytest.skip("google-generativeai not installed")
        
        # Verify agent can be created with a dummy API key (won't actually call API)
        # This just tests initialization and structure
        agent = GeminiAgent(
            name="test-gemini",
            model="gemini-2.0-flash",
            api_key="test-key-12345",
            max_tokens=2048,
            temperature=0.5
        )
        
        assert agent.name == "test-gemini"
        assert agent.model == "gemini-2.0-flash"
        assert agent.max_tokens == 2048
        assert agent.temperature == 0.5
    
    def test_gemini_provider_creates_agent(self):
        """Test that GeminiProvider creates agents correctly"""
        from startd8.providers.gemini import GeminiProvider
        
        provider = GeminiProvider()
        
        # Test that it creates agents without instantiating them fully
        # (since that requires API key)
        assert provider.name == "gemini"
        assert "gemini-2.0-flash" in provider.supported_models
        # Hardcoded models plus dynamically discovered models
        assert len(provider.supported_models) >= 8
    
    def test_gemini_models_list(self):
        """Test that hardcoded Gemini models are properly configured"""
        from startd8.providers.gemini import GeminiProvider

        provider = GeminiProvider()

        # Verify hardcoded models have pricing info
        # (dynamically discovered models may not have pricing)
        for model in provider.HARDCODED_MODELS:
            info = provider.get_model_info(model)
            # Only check models that have MODEL_INFO entries
            if info is not None:
                assert "context_window" in info
                assert "max_output_tokens" in info
                assert "cost_per_1m_input" in info
                assert "cost_per_1m_output" in info
    
    def test_gemini_capabilities(self):
        """Test Gemini provider declares correct capabilities"""
        from startd8.providers.gemini import GeminiProvider
        
        provider = GeminiProvider()
        caps = provider.get_capabilities()
        
        # Should declare text-generation
        assert "text-generation" in caps


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
    def budget_manager(self, store):
        """Create a budget manager"""
        return BudgetManager(store=store)
    
    def test_budget_check_without_cost_tracker(self, budget_manager):
        """Test that budget enforcement works WITHOUT cost_tracker (Issue 3 fix)"""
        # Create a budget
        budget = budget_manager.create_budget(
            name="test-budget",
            period=CostPeriod.DAILY,
            limit_amount=100.0,  # High limit
            block_on_exceed=False,
            scope_project="test-project"
        )
        
        # Create agent with ONLY budget_manager, NO cost_tracker
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.budget_manager = budget_manager
        agent.cost_tracker = None  # Explicitly no cost tracker
        
        # This should work without errors (budget check should still run)
        response = agent.create_response(
            prompt_id="test-123",
            prompt="Test prompt",
            project="test-project"
        )
        
        assert response is not None
        assert len(response.response) > 0
    
    def test_budget_enforcement_without_cost_tracker(self, budget_manager):
        """Test that budget blocking works WITHOUT cost_tracker (Issue 3 fix)"""
        # Create a very restrictive budget
        budget = budget_manager.create_budget(
            name="test-budget",
            period=CostPeriod.DAILY,
            limit_amount=0.0001,  # Very small limit
            block_on_exceed=True,  # BLOCK on exceed
            scope_project="test-project"
        )
        
        # Create agent with ONLY budget_manager, NO cost_tracker
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.budget_manager = budget_manager
        agent.cost_tracker = None  # Explicitly no cost tracker
        
        # This should raise BudgetExceededError because budget is exceeded
        # The budget check should work WITHOUT cost_tracker
        with pytest.raises(BudgetExceededError):
            agent.create_response(
                prompt_id="test-123",
                prompt="Test prompt",
                project="test-project"
            )
    
    def test_budget_with_cost_tracker_and_budget_manager(self, budget_manager, store, pricing):
        """Test that budget works when BOTH cost_tracker AND budget_manager are configured"""
        cost_tracker = CostTracker(store, pricing, enabled=True)
        
        # Create a restrictive budget
        budget = budget_manager.create_budget(
            name="test-budget",
            period=CostPeriod.DAILY,
            limit_amount=0.0001,  # Very small
            block_on_exceed=True,
            scope_project="test-project"
        )
        
        # Create agent with BOTH cost_tracker AND budget_manager
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.cost_tracker = cost_tracker
        agent.budget_manager = budget_manager
        
        # Should raise BudgetExceededError
        with pytest.raises(BudgetExceededError):
            agent.create_response(
                prompt_id="test-123",
                prompt="Test prompt",
                project="test-project"
            )
    
    def test_budget_uses_pricing_service_without_cost_tracker(self, budget_manager):
        """Test that budget uses PricingService when cost_tracker not available"""
        # This test verifies the fix: budget check uses PricingService independently
        budget = budget_manager.create_budget(
            name="test-budget",
            period=CostPeriod.DAILY,
            limit_amount=100.0,  # High limit so it doesn't exceed
            block_on_exceed=False,
            scope_project="test-project"
        )
        
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.budget_manager = budget_manager
        agent.cost_tracker = None
        
        # Should work fine - budget check uses standalone PricingService
        response = agent.create_response(
            prompt_id="test-123",
            prompt="Test prompt",
            project="test-project"
        )
        
        assert response is not None
    
    @pytest.mark.asyncio
    async def test_async_budget_without_cost_tracker(self, budget_manager):
        """Test that async budget check works without cost_tracker (Issue 3 fix)"""
        budget = budget_manager.create_budget(
            name="test-budget",
            period=CostPeriod.DAILY,
            limit_amount=0.0001,  # Very small
            block_on_exceed=True,
            scope_project="test-project"
        )
        
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.budget_manager = budget_manager
        agent.cost_tracker = None  # NO cost tracker
        
        # Async path should also enforce budget without cost_tracker
        with pytest.raises(BudgetExceededError):
            await agent.acreate_response(
                prompt_id="test-123",
                prompt="Test prompt",
                project="test-project"
            )
    
    def test_budget_ignores_missing_project(self, budget_manager):
        """Test that budget check safely handles missing project"""
        # Budget requires a project scope
        budget = budget_manager.create_budget(
            name="test-budget",
            period=CostPeriod.DAILY,
            limit_amount=0.0001,
            block_on_exceed=True,
            scope_project="required-project"
        )
        
        agent = MockAgent(name="test-agent", model="mock-model")
        agent.budget_manager = budget_manager
        agent.cost_tracker = None
        
        # Without matching project, budget shouldn't block
        # (budget check only runs if effective_project is provided)
        response = agent.create_response(
            prompt_id="test-123",
            prompt="Test prompt",
            project="different-project"  # Different project
        )
        
        # Should succeed because budget scope doesn't match
        assert response is not None


class TestGenerateResult:
    """Test GenerateResult NamedTuple (Issue #3 fix)"""

    def _make_result(self) -> GenerateResult:
        """Helper to create a standard GenerateResult for testing."""
        usage = TokenUsage(input=10, output=20, total=30, model_name="mock-model")
        return GenerateResult(text="Hello world", time_ms=150, token_usage=usage)

    def test_named_field_access(self):
        """Test that named fields work: .text, .time_ms, .token_usage"""
        result = self._make_result()
        assert result.text == "Hello world"
        assert result.time_ms == 150
        assert isinstance(result.token_usage, TokenUsage)
        assert result.token_usage.input == 10
        assert result.token_usage.output == 20

    def test_tuple_unpacking(self):
        """Test backward-compatible tuple unpacking"""
        result = self._make_result()
        text, time_ms, usage = result
        assert text == "Hello world"
        assert time_ms == 150
        assert isinstance(usage, TokenUsage)
        assert usage.total == 30

    def test_index_access(self):
        """Test positional index access (backward compat)"""
        result = self._make_result()
        assert result[0] == "Hello world"
        assert result[1] == 150
        assert isinstance(result[2], TokenUsage)

    def test_str_returns_text(self):
        """Test that str(result) returns just the text"""
        result = self._make_result()
        assert str(result) == "Hello world"

    def test_is_tuple(self):
        """Test that GenerateResult is a true tuple subclass"""
        result = self._make_result()
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_len(self):
        """Test that len works correctly"""
        result = self._make_result()
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_mock_agent_returns_generate_result(self):
        """Test that MockAgent.agenerate returns a GenerateResult"""
        agent = MockAgent()
        result = await agent.agenerate("Test prompt")
        assert isinstance(result, GenerateResult)
        assert isinstance(result, tuple)
        assert isinstance(result.text, str)
        assert isinstance(result.time_ms, int)
        assert isinstance(result.token_usage, TokenUsage)

    @pytest.mark.asyncio
    async def test_mock_agent_unpack_still_works(self):
        """Test that existing tuple unpacking pattern still works with MockAgent"""
        agent = MockAgent()
        text, time_ms, usage = await agent.agenerate("Test prompt")
        assert isinstance(text, str)
        assert time_ms > 0
        assert isinstance(usage, TokenUsage)

    def test_sync_generate_returns_generate_result(self):
        """Test that sync generate() also returns GenerateResult"""
        agent = MockAgent()
        result = agent.generate("Test prompt")
        assert isinstance(result, GenerateResult)
        assert isinstance(result, tuple)
        assert isinstance(result.text, str)

    @pytest.mark.asyncio
    async def test_parallel_results_are_generate_result(self):
        """Test that parallel agent calls return GenerateResult instances"""
        agents = [MockAgent(name=f"agent-{i}") for i in range(3)]
        tasks = [agent.agenerate("Test prompt") for agent in agents]
        results = await asyncio.gather(*tasks)
        for result in results:
            assert isinstance(result, GenerateResult)
            text, time_ms, usage = result
            assert isinstance(text, str)

    def test_repr(self):
        """Test that repr produces a useful string"""
        result = self._make_result()
        r = repr(result)
        assert "GenerateResult" in r
        assert "Hello world" in r
        assert "150" in r

    def test_immutable(self):
        """Test that GenerateResult is immutable like a tuple"""
        result = self._make_result()
        with pytest.raises(AttributeError):
            result.text = "modified"

    def test_export_from_package(self):
        """Test that GenerateResult is importable from startd8"""
        from startd8 import GenerateResult as GR
        assert GR is GenerateResult


class TestSystemPromptSupport:
    """Test system_prompt support across agents (Issue #6)"""

    def test_mock_agent_stores_system_prompt_in_constructor(self):
        """Test that MockAgent stores system_prompt from constructor"""
        agent = MockAgent(name="test", model="mock-model", system_prompt="You are a helpful assistant.")
        assert agent.system_prompt == "You are a helpful assistant."

    def test_mock_agent_system_prompt_defaults_to_none(self):
        """Test that system_prompt defaults to None"""
        agent = MockAgent()
        assert agent.system_prompt is None

    @pytest.mark.asyncio
    async def test_mock_agent_per_call_system_prompt_override(self):
        """Test that per-call system_prompt overrides instance-level"""
        agent = MockAgent(system_prompt="Instance-level system prompt")
        await agent.agenerate("Hello", system_prompt="Call-level override")
        assert agent._last_system_prompt == "Call-level override"

    @pytest.mark.asyncio
    async def test_mock_agent_instance_system_prompt_used_when_no_override(self):
        """Test that instance-level system_prompt is used when no per-call override"""
        agent = MockAgent(system_prompt="Instance-level system prompt")
        await agent.agenerate("Hello")
        assert agent._last_system_prompt == "Instance-level system prompt"

    @pytest.mark.asyncio
    async def test_mock_agent_no_system_prompt_when_none(self):
        """Test that no system_prompt is used when both are None"""
        agent = MockAgent()
        await agent.agenerate("Hello")
        assert agent._last_system_prompt is None

    @pytest.mark.asyncio
    async def test_mock_agent_per_call_system_prompt_without_instance(self):
        """Test per-call system_prompt works when instance has None"""
        agent = MockAgent()
        await agent.agenerate("Hello", system_prompt="Per-call only")
        assert agent._last_system_prompt == "Per-call only"

    def test_mock_provider_forwards_system_prompt(self):
        """Test that MockProvider passes system_prompt through create_agent"""
        from startd8.providers.mock import MockProvider
        provider = MockProvider()
        agent = provider.create_agent("mock-model", system_prompt="Test system prompt")
        assert agent.system_prompt == "Test system prompt"

    def test_mock_provider_system_prompt_defaults_to_none(self):
        """Test that MockProvider creates agent with None system_prompt by default"""
        from startd8.providers.mock import MockProvider
        provider = MockProvider()
        agent = provider.create_agent("mock-model")
        assert agent.system_prompt is None

    def test_claude_agent_accepts_system_prompt(self):
        """Test that ClaudeAgent constructor accepts system_prompt parameter"""
        from startd8.agents.claude import ClaudeAgent, _ANTHROPIC_AVAILABLE
        if not _ANTHROPIC_AVAILABLE:
            pytest.skip("anthropic package not installed")

        # We can't fully initialize ClaudeAgent without a valid API key,
        # but we can verify the parameter is accepted by checking the signature
        import inspect
        sig = inspect.signature(ClaudeAgent.__init__)
        assert "system_prompt" in sig.parameters
        param = sig.parameters["system_prompt"]
        assert param.default is None

    def test_gpt4_agent_accepts_system_prompt(self):
        """Test that GPT4Agent constructor accepts system_prompt parameter"""
        from startd8.agents.openai import GPT4Agent, _OPENAI_AVAILABLE
        if not _OPENAI_AVAILABLE:
            pytest.skip("openai package not installed")

        import inspect
        sig = inspect.signature(GPT4Agent.__init__)
        assert "system_prompt" in sig.parameters
        param = sig.parameters["system_prompt"]
        assert param.default is None

    def test_openai_compatible_agent_accepts_system_prompt(self):
        """Test that OpenAICompatibleAgent constructor accepts system_prompt parameter"""
        from startd8.agents.openai import OpenAICompatibleAgent, _OPENAI_AVAILABLE
        if not _OPENAI_AVAILABLE:
            pytest.skip("openai package not installed")

        import inspect
        sig = inspect.signature(OpenAICompatibleAgent.__init__)
        assert "system_prompt" in sig.parameters
        param = sig.parameters["system_prompt"]
        assert param.default is None

    def test_gemini_agent_accepts_system_prompt(self):
        """Test that GeminiAgent constructor accepts system_prompt parameter"""
        from startd8.agents.gemini import GeminiAgent, _GEMINI_AVAILABLE
        if not _GEMINI_AVAILABLE:
            pytest.skip("google-genai package not installed")

        import inspect
        sig = inspect.signature(GeminiAgent.__init__)
        assert "system_prompt" in sig.parameters
        param = sig.parameters["system_prompt"]
        assert param.default is None

    def test_anthropic_provider_forwards_system_prompt(self):
        """Test that AnthropicProvider passes system_prompt through create_agent"""
        from startd8.providers.anthropic import AnthropicProvider
        from startd8.agents.claude import _ANTHROPIC_AVAILABLE
        if not _ANTHROPIC_AVAILABLE:
            pytest.skip("anthropic package not installed")

        provider = AnthropicProvider()
        # Use mock to avoid requiring a real API key
        with patch('startd8.agents.claude.Anthropic'), \
             patch('startd8.agents.claude.AsyncAnthropic'):
            agent = provider.create_agent(
                "claude-sonnet-4-20250514",
                api_key="test-key",
                system_prompt="You are a JSON generator"
            )
            assert agent.system_prompt == "You are a JSON generator"

    def test_openai_provider_forwards_system_prompt(self):
        """Test that OpenAIProvider passes system_prompt through create_agent"""
        from startd8.providers.openai import OpenAIProvider
        from startd8.agents.openai import _OPENAI_AVAILABLE
        if not _OPENAI_AVAILABLE:
            pytest.skip("openai package not installed")

        provider = OpenAIProvider()
        with patch('startd8.agents.openai.OpenAI'), \
             patch('startd8.agents.openai.AsyncOpenAI'):
            agent = provider.create_agent(
                "gpt-4o",
                api_key="test-key",
                system_prompt="You are a code reviewer"
            )
            assert agent.system_prompt == "You are a code reviewer"

    def test_resolve_agent_spec_forwards_system_prompt(self):
        """Test that resolve_agent_spec passes system_prompt to provider"""
        from startd8.utils.agent_resolution import resolve_agent_spec
        agent = resolve_agent_spec(
            "mock",
            validate=False,
            system_prompt="Test system prompt via resolve"
        )
        assert agent.system_prompt == "Test system prompt via resolve"

    @pytest.mark.asyncio
    async def test_generate_result_unaffected_by_system_prompt(self):
        """Test that system_prompt doesn't break GenerateResult format"""
        agent = MockAgent(system_prompt="You are a test assistant")
        result = await agent.agenerate("Hello")
        assert isinstance(result, GenerateResult)
        text, time_ms, usage = result
        assert isinstance(text, str)
        assert time_ms > 0
        assert isinstance(usage, TokenUsage)

    def test_sync_generate_with_system_prompt(self):
        """Test that sync generate works with system_prompt set"""
        agent = MockAgent(system_prompt="Sync test")
        result = agent.generate("Hello")
        assert isinstance(result, GenerateResult)
        assert isinstance(result.text, str)

