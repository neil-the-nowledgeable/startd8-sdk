# Migration Guide - Week 1 Async Features

This guide helps you migrate existing StartD8 SDK code to take advantage of the new async features introduced in Week 1.

## TL;DR - Quick Migration

**Good news:** All changes are backward compatible! Your existing code will continue to work without modifications.

**To get performance benefits:** Change your functions to `async` and use `await` with the new async methods.

---

## What Changed?

### Before Week 1
- All agent calls were synchronous (blocking)
- No way to run multiple agents in parallel
- Limited visibility into framework operations
- Sequential pipeline execution only

### After Week 1
- Agents support async/await patterns
- Multiple agents can run in parallel
- Full event system for monitoring
- Async pipelines with parallel support
- 3x+ performance improvement in parallel workloads

---

## Migration Scenarios

### Scenario 1: Single Agent Usage

#### Before
```python
from startd8.providers import ProviderRegistry

ProviderRegistry.discover()
mock = ProviderRegistry.get_provider("mock")
agent = mock.create_agent("mock-model")
response_text, time_ms, tokens = agent.generate("Hello")
print(response_text)
```

#### After (Async)
```python
import asyncio
from startd8.providers import ProviderRegistry

async def main():
    ProviderRegistry.discover()
    mock = ProviderRegistry.get_provider("mock")
    agent = mock.create_agent("mock-model")
    response_text, time_ms, tokens = await agent.agenerate("Hello")
    print(response_text)

asyncio.run(main())
```

#### Migration Steps
1. Add `import asyncio`
2. Change function to `async def`
3. Change `generate()` to `await agent.agenerate()`
4. Wrap execution in `asyncio.run()`

**Backward Compatibility:** The sync `generate()` method still works!

---

### Scenario 2: Comparing Multiple Agents

#### Before
```python
def compare_agents(prompt):
    from startd8.providers import ProviderRegistry

    ProviderRegistry.discover()
    mock = ProviderRegistry.get_provider("mock")
    agent_a = mock.create_agent("mock-model", name="agent-a")
    agent_b = mock.create_agent("mock-model", name="agent-b")
    
    # Sequential execution - slow!
    result1 = agent_a.generate(prompt)
    result2 = agent_b.generate(prompt)
    
    return [result1, result2]
```

#### After (Parallel Async)
```python
import asyncio

async def compare_agents(prompt):
    from startd8.providers import ProviderRegistry

    ProviderRegistry.discover()
    mock = ProviderRegistry.get_provider("mock")
    agent_a = mock.create_agent("mock-model", name="agent-a")
    agent_b = mock.create_agent("mock-model", name="agent-b")
    
    # Parallel execution - fast!
    results = await asyncio.gather(
        agent_a.agenerate(prompt),
        agent_b.agenerate(prompt)
    )
    
    return results
```

#### Migration Steps
1. Change function to `async def`
2. Replace sequential calls with `asyncio.gather()`
3. Use `await` with `agenerate()`

**Performance Gain:** 2x faster with 2 agents, 3x faster with 3 agents!

---

### Scenario 3: Pipeline Workflows

#### Before
```python
from startd8.orchestration import Pipeline

def run_workflow(input_text):
    pipeline = Pipeline(name="my-workflow")
    pipeline.add_step("planner", planner_agent)
    pipeline.add_step("implementer", implementer_agent)
    
    result = pipeline.run(input_text)
    return result
```

#### After (Async)
```python
from startd8.orchestration import Pipeline

async def run_workflow(input_text):
    pipeline = Pipeline(name="my-workflow")
    pipeline.add_step("planner", planner_agent)
    pipeline.add_step("implementer", implementer_agent)
    
    result = await pipeline.arun(input_text)
    return result
```

#### Migration Steps
1. Change function to `async def`
2. Change `pipeline.run()` to `await pipeline.arun()`

**Backward Compatibility:** The sync `run()` method still works!

---

### Scenario 4: Benchmarking

#### Before
```python
from startd8.benchmark import BenchmarkRunner

def run_benchmark(framework):
    runner = BenchmarkRunner(framework)
    agents = [claude, gpt4, gemini]
    
    # Sequential execution
    result = runner.run_benchmark(
        prompt_content="Test prompt",
        agents=agents,
        benchmark_name="test"
    )
    return result
```

#### After (Parallel Async)
```python
from startd8.benchmark import BenchmarkRunner

async def run_benchmark(framework):
    runner = BenchmarkRunner(framework)
    agents = [claude, gpt4, gemini]
    
    # Parallel execution - much faster!
    result = await runner.arun_benchmark(
        prompt_content="Test prompt",
        agents=agents,
        benchmark_name="test",
        parallel=True  # New parameter!
    )
    return result
```

#### Migration Steps
1. Change function to `async def`
2. Change `run_benchmark()` to `await arun_benchmark()`
3. Add `parallel=True` for maximum speed

**Performance Gain:** 3x faster with 3 agents!

---

## Adding Event Monitoring

### Before (No Monitoring)
```python
# No way to see what's happening
result = agent.generate("Hello")
```

### After (With Events)
```python
from startd8.events import EventBus, ConsoleProgressHandler, MetricsHandler

# Enable monitoring
ConsoleProgressHandler.register()
MetricsHandler.register()

# Run your code (events are emitted automatically)
result = await agent.agenerate("Hello")

# Check metrics
metrics = MetricsHandler.get_metrics()
print(f"Total API calls: {metrics['agent_calls']}")
print(f"Total tokens: {metrics['total_tokens']}")
```

### Custom Event Handlers
```python
from startd8.events import EventBus, EventType

@EventBus.on(EventType.AGENT_CALL_COMPLETE)
def track_completion(event):
    print(f"✅ {event.data['agent_name']} completed in {event.data['response_time_ms']}ms")

@EventBus.on(EventType.AGENT_CALL_ERROR)
def track_error(event):
    print(f"❌ {event.data['agent_name']} failed: {event.data['error']}")
```

---

## Common Patterns

### Pattern 1: Process Multiple Prompts

#### Before (Sequential)
```python
def process_prompts(agent, prompts):
    results = []
    for prompt in prompts:
        result = agent.generate(prompt)
        results.append(result)
    return results
```

#### After (Parallel)
```python
async def process_prompts(agent, prompts):
    tasks = [agent.agenerate(prompt) for prompt in prompts]
    results = await asyncio.gather(*tasks)
    return results
```

### Pattern 2: Timeout Protection

```python
import asyncio

async def generate_with_timeout(agent, prompt, timeout=30):
    try:
        result = await asyncio.wait_for(
            agent.agenerate(prompt),
            timeout=timeout
        )
        return result
    except asyncio.TimeoutError:
        print("Agent call timed out!")
        return None
```

### Pattern 3: Retry Logic

```python
async def generate_with_retry(agent, prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await agent.agenerate(prompt)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            print(f"Attempt {attempt + 1} failed, retrying...")
            await asyncio.sleep(1)
```

### Pattern 4: Race Condition (First to Respond)

```python
async def race_agents(agents, prompt):
    """Use the first agent to respond"""
    tasks = [agent.agenerate(prompt) for agent in agents]
    done, pending = await asyncio.wait(
        tasks,
        return_when=asyncio.FIRST_COMPLETED
    )
    
    # Cancel remaining tasks
    for task in pending:
        task.cancel()
    
    return list(done)[0].result()
```

---

## Testing Async Code

### Before
```python
def test_agent():
    agent = MockAgent()
    result = agent.generate("Test")
    assert result is not None
```

### After
```python
import pytest

@pytest.mark.asyncio
async def test_agent():
    agent = MockAgent()
    result = await agent.agenerate("Test")
    assert result is not None
```

**Requirements:**
```bash
pip install pytest pytest-asyncio
```

**pytest.ini:**
```ini
[pytest]
asyncio_mode = auto
```

---

## Troubleshooting

### Error: "RuntimeError: This event loop is already running"

**Cause:** Calling `asyncio.run()` inside an already running event loop.

**Solution:** Use `await` instead.

```python
# ❌ Bad
async def my_function():
    result = asyncio.run(agent.agenerate("test"))

# ✅ Good
async def my_function():
    result = await agent.agenerate("test")
```

### Error: "Coroutine was never awaited"

**Cause:** Forgot to `await` an async function.

**Solution:** Add `await`.

```python
# ❌ Bad
result = agent.agenerate("test")

# ✅ Good
result = await agent.agenerate("test")
```

### Error: "Cannot run event loop while another loop is running"

**Cause:** Using the sync wrapper (`generate()`) inside an async context.

**Solution:** Use the async method directly.

```python
# ❌ Bad
async def my_function():
    result = agent.generate("test")  # Sync wrapper in async context

# ✅ Good
async def my_function():
    result = await agent.agenerate("test")
```

---

## Performance Checklist

Use this checklist to ensure you're getting maximum performance:

- ✅ Changed functions to `async def`
- ✅ Using `await agent.agenerate()` instead of `agent.generate()`
- ✅ Running multiple agents with `asyncio.gather()`
- ✅ Using `parallel=True` in benchmarks
- ✅ Using `await pipeline.arun()` for pipelines
- ✅ Batching operations where possible
- ✅ Added timeout protection for long-running calls
- ✅ Using event system for monitoring

---

## Complete Example: Before & After

### Before (Sync, Sequential)

```python
from startd8.providers import ProviderRegistry
from startd8.orchestration import Pipeline
from startd8.benchmark import BenchmarkRunner
from startd8.framework import AgentFramework

def main():
    # Setup
    ProviderRegistry.discover()
    mock = ProviderRegistry.get_provider("mock")

    framework = AgentFramework()
    agent_a = mock.create_agent("mock-model", name="agent-a")
    agent_b = mock.create_agent("mock-model", name="agent-b")
    
    # Compare agents
    r1 = agent_a.generate("Test")
    r2 = agent_b.generate("Test")
    
    # Run pipeline
    pipeline = Pipeline()
    pipeline.add_step("step1", agent_a)
    pipeline.add_step("step2", agent_b)
    result = pipeline.run("Input")
    
    # Run benchmark
    runner = BenchmarkRunner(framework)
    benchmark = runner.run_benchmark(
        "Test prompt",
        [agent_a, agent_b],
        "test-benchmark"
    )
    
    print("Done!")

if __name__ == "__main__":
    main()
```

### After (Async, Parallel)

```python
import asyncio
from startd8.providers import ProviderRegistry
from startd8.orchestration import Pipeline
from startd8.benchmark import BenchmarkRunner
from startd8.framework import AgentFramework
from startd8.events import ConsoleProgressHandler, MetricsHandler

async def main():
    # Setup
    ProviderRegistry.discover()
    mock = ProviderRegistry.get_provider("mock")

    framework = AgentFramework()
    agent_a = mock.create_agent("mock-model", name="agent-a")
    agent_b = mock.create_agent("mock-model", name="agent-b")
    
    # Enable monitoring
    ConsoleProgressHandler.register()
    MetricsHandler.register()
    
    # Compare agents (in parallel!)
    results = await asyncio.gather(
        agent_a.agenerate("Test"),
        agent_b.agenerate("Test")
    )
    
    # Run pipeline (async)
    pipeline = Pipeline()
    pipeline.add_step("step1", agent_a)
    pipeline.add_step("step2", agent_b)
    result = await pipeline.arun("Input")
    
    # Run benchmark (in parallel!)
    runner = BenchmarkRunner(framework)
    benchmark = await runner.arun_benchmark(
        "Test prompt",
        [agent_a, agent_b],
        "test-benchmark",
        parallel=True
    )
    
    # Show metrics
    metrics = MetricsHandler.get_metrics()
    print(f"Total API calls: {metrics['agent_calls']}")
    print(f"Total tokens: {metrics['total_tokens']}")
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
```

**Key Changes:**
1. Added `import asyncio`
2. Changed `main()` to `async def main()`
3. Added event handlers for monitoring
4. Changed to async methods with `await`
5. Used `asyncio.gather()` for parallel execution
6. Added `parallel=True` to benchmark
7. Show collected metrics
8. Wrapped in `asyncio.run()`

**Performance Gain:** ~3x faster overall!

---

## Next Steps

1. **Start Small:** Convert one function at a time
2. **Test Thoroughly:** Use the new test patterns
3. **Monitor Performance:** Use `MetricsHandler` to measure improvements
4. **Read Documentation:** Check [ASYNC_FEATURES.md](examples/ASYNC_FEATURES.md)
5. **Run Examples:** Try [async_features_demo.py](examples/async_features_demo.py)

---

## Support

- Examples: [examples/async_features_demo.py](examples/async_features_demo.py)
- Guide: [examples/ASYNC_FEATURES.md](examples/ASYNC_FEATURES.md)
- Tests: [tests/unit/test_orchestration_async.py](tests/unit/test_orchestration_async.py)
- Summary: [WEEK1_COMPLETION_SUMMARY.md](WEEK1_COMPLETION_SUMMARY.md)

**Happy migrating! 🚀**

