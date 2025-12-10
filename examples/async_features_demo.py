"""
Demo script showcasing Week 1 async features

This example demonstrates:
1. Async agent calls
2. Parallel agent execution
3. Event system integration
4. Async pipelines
5. Parallel benchmarking
"""

import asyncio
from startd8.agents import MockAgent
from startd8.orchestration import Pipeline
from startd8.framework import AgentFramework
from startd8.benchmark import BenchmarkRunner
from startd8.events import EventBus, MetricsHandler, ConsoleProgressHandler


async def demo_async_agents():
    """Demo 1: Basic async agent calls"""
    print("\n" + "="*60)
    print("DEMO 1: Async Agent Calls")
    print("="*60)
    
    agent = MockAgent(name="demo-agent")
    
    # Single async call
    print("\nSingle async call:")
    response_text, time_ms, tokens = await agent.agenerate("What is async programming?")
    print(f"Response: {response_text}")
    print(f"Time: {time_ms}ms")
    print(f"Tokens: {tokens.total}")


async def demo_parallel_agents():
    """Demo 2: Running multiple agents in parallel"""
    print("\n" + "="*60)
    print("DEMO 2: Parallel Agent Execution")
    print("="*60)
    
    # Create multiple agents
    agents = [
        MockAgent(name="agent-1", model="model-1"),
        MockAgent(name="agent-2", model="model-2"),
        MockAgent(name="agent-3", model="model-3"),
    ]
    
    print(f"\nRunning {len(agents)} agents in parallel...")
    
    # Time the parallel execution
    import time
    start = time.time()
    
    tasks = [agent.agenerate("Explain Python decorators") for agent in agents]
    results = await asyncio.gather(*tasks)
    
    elapsed = time.time() - start
    
    print(f"\nCompleted in {elapsed:.2f}s")
    print(f"Results from {len(results)} agents:")
    for i, (text, time_ms, tokens) in enumerate(results, 1):
        print(f"  Agent {i}: {time_ms}ms, {tokens.total} tokens")


async def demo_event_system():
    """Demo 3: Event system integration"""
    print("\n" + "="*60)
    print("DEMO 3: Event System Integration")
    print("="*60)
    
    # Clear any existing handlers
    EventBus.clear()
    
    # Register handlers
    print("\nRegistering event handlers...")
    MetricsHandler.register()
    ConsoleProgressHandler.register()
    
    # Run an agent to trigger events
    print("\nRunning agent (watch for events)...")
    agent = MockAgent(name="event-demo")
    await agent.agenerate("Test prompt for events")
    
    # Show collected metrics
    print("\nCollected metrics:")
    metrics = MetricsHandler.get_metrics()
    for key, value in metrics.items():
        print(f"  {key}: {value}")
    
    # Clean up
    EventBus.clear()
    MetricsHandler.reset_metrics()


async def demo_async_pipeline():
    """Demo 4: Async pipeline execution"""
    print("\n" + "="*60)
    print("DEMO 4: Async Pipeline")
    print("="*60)
    
    # Create pipeline
    pipeline = Pipeline(name="demo-pipeline")
    
    # Add steps
    pipeline.add_step(
        "analyzer",
        MockAgent(name="analyzer"),
        metadata={"role": "analysis"}
    )
    
    pipeline.add_step(
        "summarizer",
        MockAgent(name="summarizer"),
        transform=lambda x: f"Summarize this: {x}",
        metadata={"role": "summary"}
    )
    
    print("\nRunning 2-step pipeline asynchronously...")
    result = await pipeline.arun("Analyze async programming benefits", store=False)
    
    print(f"\nPipeline completed:")
    print(f"  Steps: {len(result.steps)}")
    print(f"  Total time: {result.total_time_ms}ms")
    print(f"  Total tokens: {result.total_tokens}")
    print(f"  Total cost: ${result.total_cost:.4f}")
    
    print("\nStep details:")
    for step in result.steps:
        print(f"  {step['step_name']}: {step['response_time_ms']}ms")


async def demo_parallel_benchmark():
    """Demo 5: Parallel benchmarking"""
    print("\n" + "="*60)
    print("DEMO 5: Parallel Benchmarking")
    print("="*60)
    
    # Create temporary framework
    import tempfile
    from pathlib import Path
    
    with tempfile.TemporaryDirectory() as tmpdir:
        framework = AgentFramework(storage_dir=Path(tmpdir))
        runner = BenchmarkRunner(framework)
        
        # Create agents to benchmark
        agents = [
            MockAgent(name="fast-model", model="fast-v1"),
            MockAgent(name="balanced-model", model="balanced-v1"),
            MockAgent(name="accurate-model", model="accurate-v1"),
        ]
        
        print(f"\nBenchmarking {len(agents)} agents in parallel...")
        
        import time
        start = time.time()
        
        result = await runner.arun_benchmark(
            prompt_content="Explain the benefits of async programming in Python",
            agents=agents,
            benchmark_name="async-demo-benchmark",
            parallel=True
        )
        
        elapsed = time.time() - start
        
        print(f"\nBenchmark completed in {elapsed:.2f}s")
        print(f"Responses collected: {len(result['responses'])}")
        
        print("\nComparison:")
        comparison = result['comparison']
        
        print("\n  Fastest:")
        for rank in comparison['rankings']['by_speed'][:3]:
            print(f"    {rank['agent']}: {rank['time_ms']}ms")
        
        print("\n  Most efficient (tokens):")
        for rank in comparison['rankings']['by_token_efficiency'][:3]:
            print(f"    {rank['agent']}: {rank['tokens']} tokens")


async def demo_performance_comparison():
    """Demo 6: Sequential vs Parallel performance"""
    print("\n" + "="*60)
    print("DEMO 6: Performance Comparison")
    print("="*60)
    
    # Create agents with artificial delay
    class SlowMockAgent(MockAgent):
        async def agenerate(self, prompt):
            await asyncio.sleep(0.2)  # 200ms delay
            return await super().agenerate(prompt)
    
    agents = [SlowMockAgent(name=f"agent-{i}") for i in range(3)]
    
    # Test parallel execution
    print("\nTesting parallel execution (3 agents @ 200ms each)...")
    import time
    
    start = time.time()
    tasks = [agent.agenerate("Test") for agent in agents]
    await asyncio.gather(*tasks)
    parallel_time = time.time() - start
    
    print(f"Parallel time: {parallel_time:.2f}s")
    
    # Test sequential execution
    print("\nTesting sequential execution (3 agents @ 200ms each)...")
    start = time.time()
    for agent in agents:
        await agent.agenerate("Test")
    sequential_time = time.time() - start
    
    print(f"Sequential time: {sequential_time:.2f}s")
    
    # Calculate speedup
    speedup = sequential_time / parallel_time
    print(f"\n🚀 Speedup: {speedup:.1f}x faster with parallel execution!")


async def main():
    """Run all demos"""
    print("\n" + "🚀 StartD8 SDK - Week 1 Async Features Demo ".center(60, "="))
    
    await demo_async_agents()
    await demo_parallel_agents()
    await demo_event_system()
    await demo_async_pipeline()
    await demo_parallel_benchmark()
    await demo_performance_comparison()
    
    print("\n" + "="*60)
    print("All demos completed! ✅")
    print("="*60)
    print("\nKey Takeaways:")
    print("1. Agents support async/await patterns")
    print("2. Multiple agents can run in parallel")
    print("3. Event system provides full observability")
    print("4. Pipelines execute asynchronously")
    print("5. Benchmarks run faster with parallel execution")
    print("6. 3x+ speedup in parallel workloads")
    print("\nTry modifying this script to test different scenarios!")


if __name__ == "__main__":
    asyncio.run(main())

