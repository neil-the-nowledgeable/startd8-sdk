"""
Unit tests for async benchmark functionality
"""

import pytest
import asyncio

from startd8.benchmark import BenchmarkRunner
from startd8.framework import AgentFramework
from startd8.agents import MockAgent
from startd8.events import EventBus, EventType


class TestAsyncBenchmarkRunner:
    """Test async BenchmarkRunner functionality"""
    
    def setup_method(self):
        """Setup test environment"""
        import tempfile
        import shutil
        from pathlib import Path
        
        # Create temporary directory for test storage
        self.temp_dir = Path(tempfile.mkdtemp())
        self.framework = AgentFramework(storage_dir=self.temp_dir)
        self.runner = BenchmarkRunner(self.framework)
        
        EventBus.clear()
    
    def teardown_method(self):
        """Clean up after tests"""
        import shutil
        if hasattr(self, 'temp_dir') and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
        
        EventBus.clear()
    
    @pytest.mark.asyncio
    async def test_arun_benchmark_parallel(self):
        """Test async benchmark with parallel execution"""
        agents = [
            MockAgent(name="agent1", model="model1"),
            MockAgent(name="agent2", model="model2"),
            MockAgent(name="agent3", model="model3")
        ]
        
        result = await self.runner.arun_benchmark(
            prompt_content="Test prompt",
            agents=agents,
            benchmark_name="test-parallel",
            parallel=True
        )
        
        assert result is not None
        assert "benchmark" in result
        assert "responses" in result
        assert len(result["responses"]) == 3
    
    @pytest.mark.asyncio
    async def test_arun_benchmark_sequential(self):
        """Test async benchmark with sequential execution"""
        agents = [
            MockAgent(name="agent1"),
            MockAgent(name="agent2")
        ]
        
        result = await self.runner.arun_benchmark(
            prompt_content="Test prompt",
            agents=agents,
            benchmark_name="test-sequential",
            parallel=False
        )
        
        assert result is not None
        assert len(result["responses"]) == 2
    
    @pytest.mark.asyncio
    async def test_arun_benchmark_emits_events(self):
        """Test that async benchmark emits proper events"""
        received_events = []
        
        @EventBus.on([EventType.BENCHMARK_CREATED, EventType.BENCHMARK_COMPLETED])
        def capture_events(event):
            received_events.append(event.type)
        
        agents = [MockAgent(name="agent1")]
        
        await self.runner.arun_benchmark(
            prompt_content="Test prompt",
            agents=agents,
            benchmark_name="test-events"
        )
        
        assert EventType.BENCHMARK_CREATED in received_events
        assert EventType.BENCHMARK_COMPLETED in received_events
    
    @pytest.mark.asyncio
    async def test_arun_benchmark_with_failing_agent(self):
        """Test benchmark continues when one agent fails"""
        
        class FailingAgent(MockAgent):
            async def agenerate(self, prompt):
                raise Exception("Test failure")
        
        agents = [
            MockAgent(name="good-agent"),
            FailingAgent(name="bad-agent")
        ]
        
        result = await self.runner.arun_benchmark(
            prompt_content="Test prompt",
            agents=agents,
            benchmark_name="test-with-failure"
        )
        
        # Should get 1 successful response
        assert len(result["responses"]) == 1
        assert result["responses"][0]["agent_name"] == "good-agent"
    
    def test_sync_run_benchmark_wrapper(self):
        """Test that sync run_benchmark wraps async properly"""
        agents = [MockAgent(name="agent1")]
        
        result = self.runner.run_benchmark(
            prompt_content="Test prompt",
            agents=agents,
            benchmark_name="test-sync-wrapper"
        )
        
        assert result is not None
        assert len(result["responses"]) == 1
    
    @pytest.mark.asyncio
    async def test_parallel_benchmark_performance(self):
        """Test that parallel execution is faster than sequential"""
        import time
        
        class SlowMockAgent(MockAgent):
            async def agenerate(self, prompt):
                await asyncio.sleep(0.2)
                return await super().agenerate(prompt)
        
        agents = [SlowMockAgent(name=f"agent-{i}") for i in range(3)]
        
        # Test parallel
        start_parallel = time.time()
        await self.runner.arun_benchmark(
            prompt_content="Test",
            agents=agents,
            benchmark_name="parallel-perf",
            parallel=True
        )
        parallel_time = time.time() - start_parallel
        
        # Test sequential
        start_sequential = time.time()
        await self.runner.arun_benchmark(
            prompt_content="Test",
            agents=agents,
            benchmark_name="sequential-perf",
            parallel=False
        )
        sequential_time = time.time() - start_sequential
        
        # Parallel should be significantly faster
        assert parallel_time < sequential_time * 0.5

