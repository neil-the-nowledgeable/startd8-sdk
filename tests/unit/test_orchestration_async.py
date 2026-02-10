"""
Unit tests for async orchestration functionality
"""

import pytest
import asyncio

from startd8.orchestration import Pipeline, PipelineStep
from startd8.agents import MockAgent
from startd8.events import EventBus, EventType


class TestAsyncPipeline:
    """Test async Pipeline functionality"""
    
    def setup_method(self):
        """Clear event bus before each test"""
        EventBus.clear()
    
    def teardown_method(self):
        """Clear event bus after each test"""
        EventBus.clear()
    
    @pytest.mark.asyncio
    async def test_arun_pipeline(self):
        """Test async pipeline execution"""
        pipeline = Pipeline(name="test-pipeline")
        
        agent1 = MockAgent(name="agent1")
        agent2 = MockAgent(name="agent2")
        
        pipeline.add_step("step1", agent1)
        pipeline.add_step("step2", agent2)
        
        result = await pipeline.arun("Test input", store=False)
        
        assert result is not None
        assert len(result.steps) == 2
        assert result.final_output is not None
        assert result.total_time_ms >= 0  # may round to 0 on fast machines
        assert result.total_tokens > 0
    
    @pytest.mark.asyncio
    async def test_arun_with_transforms(self):
        """Test async pipeline with input transforms"""
        pipeline = Pipeline(name="test-transform")
        
        agent1 = MockAgent(name="agent1")
        agent2 = MockAgent(name="agent2")
        
        pipeline.add_step("step1", agent1)
        pipeline.add_step(
            "step2",
            agent2,
            transform=lambda x: f"Transformed: {x}"
        )
        
        result = await pipeline.arun("Original input", store=False)
        
        assert result is not None
        assert len(result.steps) == 2
        # Second step should have received transformed input
        assert "Transformed:" in result.steps[1]["input"]
    
    @pytest.mark.asyncio
    async def test_arun_emits_events(self):
        """Test that async pipeline emits proper events"""
        received_events = []
        
        @EventBus.on([
            EventType.PIPELINE_START,
            EventType.PIPELINE_STEP_START,
            EventType.PIPELINE_STEP_COMPLETE,
            EventType.PIPELINE_COMPLETE
        ])
        def capture_events(event):
            received_events.append(event.type)
        
        pipeline = Pipeline(name="test-events")
        agent = MockAgent()
        pipeline.add_step("step1", agent)
        
        await pipeline.arun("Test input", store=False)
        
        assert EventType.PIPELINE_START in received_events
        assert EventType.PIPELINE_STEP_START in received_events
        assert EventType.PIPELINE_STEP_COMPLETE in received_events
        assert EventType.PIPELINE_COMPLETE in received_events
    
    @pytest.mark.asyncio
    async def test_arun_parallel_agents(self):
        """Test running multiple agents in parallel"""
        pipeline = Pipeline(name="test-parallel")
        agents = [MockAgent(name=f"agent-{i}") for i in range(3)]
        
        results = await pipeline.arun_parallel_agents("Test prompt", agents)
        
        assert len(results) == 3
        for response_text, response_time_ms, token_usage in results:
            assert isinstance(response_text, str)
            assert response_time_ms > 0
            assert token_usage.total > 0
    
    @pytest.mark.asyncio
    async def test_arun_parallel_with_error(self):
        """Test parallel execution with one agent failing"""
        pipeline = Pipeline(name="test-parallel-error")
        
        # Create a mock agent that will fail
        class FailingAgent(MockAgent):
            async def agenerate(self, prompt):
                raise Exception("Test failure")
        
        agents = [
            MockAgent(name="good-agent-1"),
            FailingAgent(name="bad-agent"),
            MockAgent(name="good-agent-2")
        ]
        
        results = await pipeline.arun_parallel_agents("Test prompt", agents)
        
        # Should get 2 successful results
        assert len(results) == 2
    
    def test_sync_run_wrapper(self):
        """Test that sync run method properly wraps async"""
        pipeline = Pipeline(name="test-sync-wrapper")
        agent = MockAgent()
        pipeline.add_step("step1", agent)
        
        result = pipeline.run("Test input", store=False)
        
        assert result is not None
        assert len(result.steps) == 1
        assert result.total_time_ms >= 0  # may round to 0 on fast machines
    
    @pytest.mark.asyncio
    async def test_multiple_parallel_pipelines(self):
        """Test running multiple pipelines in parallel"""
        async def run_pipeline(name: str):
            pipeline = Pipeline(name=name)
            agent = MockAgent()
            pipeline.add_step("step1", agent)
            return await pipeline.arun(f"Input for {name}", store=False)
        
        results = await asyncio.gather(
            run_pipeline("pipeline-1"),
            run_pipeline("pipeline-2"),
            run_pipeline("pipeline-3")
        )
        
        assert len(results) == 3
        for result in results:
            assert result is not None
            assert len(result.steps) == 1


class TestAsyncPipelinePerformance:
    """Test performance characteristics of async pipelines"""
    
    @pytest.mark.asyncio
    async def test_sequential_vs_parallel_timing(self):
        """Test that parallel execution is faster than sequential"""
        import time
        
        # Create agents with artificial delay
        class SlowMockAgent(MockAgent):
            async def agenerate(self, prompt):
                await asyncio.sleep(0.2)  # 200ms delay
                return await super().agenerate(prompt)
        
        agents = [SlowMockAgent(name=f"agent-{i}") for i in range(3)]
        pipeline = Pipeline()
        
        # Test parallel execution
        start_parallel = time.time()
        await pipeline.arun_parallel_agents("Test", agents)
        parallel_time = time.time() - start_parallel
        
        # Test sequential execution (using pipeline steps)
        sequential_pipeline = Pipeline()
        for i, agent in enumerate(agents):
            sequential_pipeline.add_step(f"step-{i}", agent)
        
        start_sequential = time.time()
        await sequential_pipeline.arun("Test", store=False)
        sequential_time = time.time() - start_sequential
        
        # Parallel should be significantly faster than sequential
        # With 3 agents at 200ms each:
        # Sequential: ~600ms
        # Parallel: ~200ms
        assert parallel_time < sequential_time * 0.5

