# StartD8 SDK - Async Features Guide

This guide covers the async features introduced in Week 1 of the architecture improvements.

## Quick Start

```python
import asyncio
from startd8.providers import ProviderRegistry

async def main():
    ProviderRegistry.discover()
    mock = ProviderRegistry.get_provider("mock")
    agent = mock.create_agent("mock-model")
    
    # Use async/await for non-blocking calls
    text, elapsed_ms, usage = await agent.agenerate("Hello!")
    print(text)

asyncio.run(main())
```

## Running the Demo

```bash
cd examples
python async_features_demo.py
```

## Features Overview

### 1. Async Agent Calls

All agents now support async operations:

```python
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
mock = ProviderRegistry.get_provider("mock")

# Create agents
agent_a = mock.create_agent("mock-model", name="agent-a")
agent_b = mock.create_agent("mock-model", name="agent-b")

# Async calls
response1 = await agent_a.agenerate("Prompt 1")
response2 = await agent_b.agenerate("Prompt 2")
```

**Benefits:**
- Non-blocking I/O
- Better resource utilization
- Faster overall execution

### 2. Parallel Agent Execution

Run multiple agents simultaneously:

```python
import asyncio

from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
mock = ProviderRegistry.get_provider("mock")
agents = [
    mock.create_agent("mock-model", name="agent-a"),
    mock.create_agent("mock-model", name="agent-b"),
    mock.create_agent("mock-model", name="agent-c"),
]
prompt = "Explain async programming"

# Run all agents in parallel
tasks = [agent.agenerate(prompt) for agent in agents]
results = await asyncio.gather(*tasks)
```

**Performance:**
- 3 agents @ 2s each
- Sequential: ~6 seconds
- Parallel: ~2 seconds
- **3x faster!**

### 3. Event System

Monitor framework activity in real-time:

```python
from startd8.events import EventBus, EventType, MetricsHandler

# Subscribe to events
@EventBus.on(EventType.AGENT_CALL_COMPLETE)
def log_completion(event):
    print(f"Agent {event.data['agent_name']} completed!")

# Enable metrics collection
MetricsHandler.register()

# Run your workflow...

# Check metrics
metrics = MetricsHandler.get_metrics()
print(f"Total API calls: {metrics['agent_calls']}")
```

**Built-in Handlers:**
- `LoggingHandler` - Structured logging
- `MetricsHandler` - Collect statistics
- `ConsoleProgressHandler` - Pretty console output

### 4. Async Pipelines

Execute multi-step workflows asynchronously:

```python
from startd8.orchestration import Pipeline

pipeline = Pipeline(name="design-implement")

pipeline.add_step("planner", planner_agent)
pipeline.add_step("implementer", implementer_agent)

# Run asynchronously
result = await pipeline.arun("Design a feature")
```

**Parallel Agent Execution:**

```python
# Run multiple agents on same input
agents = [agent_a, agent_b, agent_c]
results = await pipeline.arun_parallel_agents("Test prompt", agents)
```

### 5. Parallel Benchmarking

Compare agents efficiently:

```python
from startd8.benchmark import BenchmarkRunner

runner = BenchmarkRunner(framework)
agents = [agent_a, agent_b, agent_c]

# Run benchmark in parallel
result = await runner.arun_benchmark(
    prompt_content="Write a haiku",
    agents=agents,
    benchmark_name="haiku-test",
    parallel=True  # Run all agents simultaneously!
)
```

## Best Practices

### 1. Always Use Async Context

```python
# ✅ Good
async def my_workflow():
    result = await agent.agenerate("prompt")
    return result

# ❌ Bad (blocks event loop)
async def my_workflow():
    result = agent.generate("prompt")  # Sync call in async context
    return result
```

### 2. Batch Parallel Operations

```python
# ✅ Good - Process all at once
tasks = [agent.agenerate(prompt) for agent in agents]
results = await asyncio.gather(*tasks)

# ❌ Bad - One at a time
results = []
for agent in agents:
    result = await agent.agenerate(prompt)
    results.append(result)
```

### 3. Handle Exceptions Gracefully

```python
# Use return_exceptions to handle failures
results = await asyncio.gather(
    *tasks,
    return_exceptions=True
)

for result in results:
    if isinstance(result, Exception):
        print(f"Failed: {result}")
    else:
        print(f"Success: {result}")
```

### 4. Use Event System for Observability

```python
from startd8.events import ConsoleProgressHandler, MetricsHandler

# Enable at start of program
ConsoleProgressHandler.register()
MetricsHandler.register()

# Your async workflows...

# Check metrics at end
print(MetricsHandler.get_metrics())
```

## Migration Guide

### From Sync to Async

**Before:**
```python
def run_comparison():
    from startd8.providers import ProviderRegistry

    ProviderRegistry.discover()
    mock = ProviderRegistry.get_provider("mock")
    agent1 = mock.create_agent("mock-model", name="agent-1")
    agent2 = mock.create_agent("mock-model", name="agent-2")
    
    r1 = agent1.generate("Test")
    r2 = agent2.generate("Test")
    
    return [r1, r2]
```

**After:**
```python
async def run_comparison():
    import asyncio
    from startd8.providers import ProviderRegistry

    ProviderRegistry.discover()
    mock = ProviderRegistry.get_provider("mock")
    agent1 = mock.create_agent("mock-model", name="agent-1")
    agent2 = mock.create_agent("mock-model", name="agent-2")
    
    # Run in parallel!
    results = await asyncio.gather(
        agent1.agenerate("Test"),
        agent2.agenerate("Test")
    )
    
    return results
```

### Backward Compatibility

All sync methods still work:

```python
# Still supported!
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
mock = ProviderRegistry.get_provider("mock")
agent = mock.create_agent("mock-model")
response = agent.generate("Hello")  # Sync wrapper
```

## Performance Tips

### 1. Use Parallel Execution

```python
# Sequential: ~6s for 3 agents
for agent in agents:
    await agent.agenerate(prompt)

# Parallel: ~2s for 3 agents
await asyncio.gather(*[agent.agenerate(prompt) for agent in agents])
```

### 2. Batch API Calls

```python
# Process multiple prompts in parallel
prompts = ["prompt1", "prompt2", "prompt3"]
results = await asyncio.gather(*[agent.agenerate(p) for p in prompts])
```

### 3. Use Timeout Protection

```python
import asyncio

try:
    result = await asyncio.wait_for(
        agent.agenerate(prompt),
        timeout=30.0  # 30 second timeout
    )
except asyncio.TimeoutError:
    print("Agent call timed out!")
```

## Common Patterns

### Pattern 1: Fan-out/Fan-in

```python
async def fan_out_fan_in(prompt: str, agents: list):
    """Send one prompt to multiple agents, collect all results"""
    tasks = [agent.agenerate(prompt) for agent in agents]
    results = await asyncio.gather(*tasks)
    return results
```

### Pattern 2: Race Condition

```python
async def race(prompt: str, agents: list):
    """Use the first agent to respond"""
    tasks = [agent.agenerate(prompt) for agent in agents]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    
    # Cancel remaining tasks
    for task in pending:
        task.cancel()
    
    return list(done)[0].result()
```

### Pattern 3: Pipeline with Parallel Steps

```python
async def parallel_pipeline(input_text: str):
    """Run some steps in parallel, others sequentially"""
    
    # Step 1: Single agent
    draft = await planner_agent.agenerate(input_text)
    
    # Step 2: Multiple agents in parallel review
    tasks = [
        reviewer1.agenerate(draft),
        reviewer2.agenerate(draft),
        reviewer3.agenerate(draft)
    ]
    reviews = await asyncio.gather(*tasks)
    
    # Step 3: Single agent synthesizes
    final = await synthesizer_agent.agenerate("\n\n".join(reviews))
    
    return final
```

## Troubleshooting

### Issue: "RuntimeError: This event loop is already running"

**Solution:** Don't call `asyncio.run()` inside an already running event loop.

```python
# ❌ Bad
async def my_function():
    result = asyncio.run(agent.agenerate("test"))

# ✅ Good
async def my_function():
    result = await agent.agenerate("test")
```

### Issue: "Coroutine was never awaited"

**Solution:** Always `await` async functions.

```python
# ❌ Bad
result = agent.agenerate("test")  # Forgot await!

# ✅ Good
result = await agent.agenerate("test")
```

### Issue: Tasks finish but results aren't what I expect

**Solution:** Check for exceptions using `return_exceptions=True`

```python
results = await asyncio.gather(*tasks, return_exceptions=True)

for i, result in enumerate(results):
    if isinstance(result, Exception):
        print(f"Task {i} failed: {result}")
```

## Further Reading

- [Python asyncio documentation](https://docs.python.org/3/library/asyncio.html)
- [Real Python: Async IO](https://realpython.com/async-io-python/)
- [Week 1 Completion Summary](../WEEK1_COMPLETION_SUMMARY.md)
- [Architecture Review](../startd8-architecture-review.md)

## Support

For questions or issues:
1. Check the [examples/async_features_demo.py](async_features_demo.py)
2. Review the [test suite](../tests/unit/test_orchestration_async.py)
3. Open an issue on GitHub

---

**Happy async coding! 🚀**

