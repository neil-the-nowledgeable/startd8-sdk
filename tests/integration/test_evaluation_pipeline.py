"""
End-to-end integration tests for the evaluation pipeline.

This module tests the complete evaluation flow integrating:
1. Rate limiter (src/startd8/ratelimit/) - DONE
2. Task corpus (src/startd8/evaluation/) - Real implementation
3. Quality scorer (src/startd8/evaluation/) - Real implementation
4. Existing: BenchmarkRunner, AgentFramework, providers (anthropic, openai, gemini, mock)

Tests use MockAgent exclusively - no real API calls are made.
Run with: pytest tests/integration/test_evaluation_pipeline.py -v
"""

import asyncio
import pytest
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

from startd8 import AgentFramework, BenchmarkRunner
from startd8.agents import MockAgent, BaseAgent
from startd8.models import TokenUsage, AgentResponse
from startd8.providers import ProviderRegistry, MockProvider
from startd8.ratelimit import (
    RateLimiter,
    RateLimitConfig,
    BackpressureStrategy,
    get_rate_limiter,
    clear_rate_limiters,
)

# Import from real evaluation module
from startd8.evaluation import (
    Task, TaskCorpus, TaskFilter, TaskLoader, TaskResult, EvaluationRun,
    TaskCategory, TaskDifficulty, Capability,
    load_default_corpus,
)
from startd8.evaluation import (
    QualityScorer, QualityScorerConfig, QualityScore,
    ScoringDimension, DimensionScore,
    RuleBasedScorer,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def storage_dir(temp_dir):
    """Create a storage directory for tests."""
    storage_path = temp_dir / "storage"
    storage_path.mkdir(parents=True, exist_ok=True)
    return storage_path


@pytest.fixture
def framework(storage_dir):
    """Create an AgentFramework instance for testing."""
    return AgentFramework(storage_dir=storage_dir)


@pytest.fixture
def mock_agent():
    """Create a mock agent for testing."""
    return MockAgent(name="test-mock", model="mock-model")


@pytest.fixture
def task_corpus():
    """Load the built-in task corpus using real loader."""
    return load_default_corpus()


@pytest.fixture
def quality_scorer():
    """Create a quality scorer with default configuration (rules-only)."""
    return QualityScorer()


@pytest.fixture(autouse=True)
def cleanup_rate_limiters():
    """Clean up rate limiters after each test."""
    yield
    clear_rate_limiters()


# =============================================================================
# HELPER: Simple Evaluation Runner for Tests
# =============================================================================


class SimpleEvaluationRunner:
    """
    Simple evaluation runner for testing purposes.

    Uses real QualityScorer but runs synchronously against MockAgent.
    Note: Named 'SimpleEvaluationRunner' to avoid pytest collection warning
    (pytest tries to collect classes starting with 'Test').
    """

    def __init__(
        self,
        corpus: TaskCorpus,
        agents: List[BaseAgent],
        scorer: QualityScorer,
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.corpus = corpus
        self.agents = agents
        self.scorer = scorer
        self.rate_limiter = rate_limiter
        self.results: List[TaskResult] = []

    async def run(
        self,
        task_filter: Optional[TaskFilter] = None,
        max_tasks: Optional[int] = None,
    ) -> List[TaskResult]:
        """Run evaluation on filtered tasks."""
        tasks = self.corpus.list_tasks(task_filter)
        if max_tasks:
            tasks = tasks[:max_tasks]

        self.results = []

        for task in tasks:
            for agent in self.agents:
                result = await self._evaluate_task(task, agent)
                self.results.append(result)

        return self.results

    async def _evaluate_task(
        self,
        task: Task,
        agent: BaseAgent,
    ) -> TaskResult:
        """Evaluate a single task with an agent."""
        # Render prompt (use empty dict for variables - tasks have defaults or none required)
        try:
            prompt = task.render_prompt({})
        except ValueError:
            # If variables are required, provide empty strings as fallback
            variables = {v.name: v.default or "" for v in task.variables}
            prompt = task.render_prompt(variables)

        # Apply rate limiting if configured
        if self.rate_limiter:
            async with self.rate_limiter.acquire(estimated_tokens=500):
                response_text, response_time_ms, token_usage = await agent.agenerate(prompt)
        else:
            response_text, response_time_ms, token_usage = await agent.agenerate(prompt)

        # Score the response using real QualityScorer
        score = self.scorer.score_sync(response_text, task, task.reference_solution)

        return TaskResult(
            task_id=task.id,
            agent_name=agent.name,
            model=agent.model,
            prompt=prompt,
            response=response_text,
            response_time_ms=response_time_ms,
            token_usage={
                "input": token_usage.input if token_usage else 0,
                "output": token_usage.output if token_usage else 0,
                "total": token_usage.total if token_usage else 0,
            },
            score=score.overall,
            criteria_scores={dim.value: ds.score for dim, ds in score.dimensions.items()},
        )

    def get_comparison_report(self) -> Dict[str, Any]:
        """Generate comparison report across agents."""
        agent_scores: Dict[str, List[float]] = {}
        agent_times: Dict[str, List[int]] = {}

        for result in self.results:
            if result.agent_name not in agent_scores:
                agent_scores[result.agent_name] = []
                agent_times[result.agent_name] = []
            if result.score is not None:
                agent_scores[result.agent_name].append(result.score)
            agent_times[result.agent_name].append(result.response_time_ms)

        return {
            "agent_avg_scores": {
                name: sum(scores) / len(scores) if scores else 0.0
                for name, scores in agent_scores.items()
            },
            "agent_avg_times": {
                name: sum(times) / len(times) if times else 0
                for name, times in agent_times.items()
            },
            "total_evaluations": len(self.results),
            "agents_evaluated": list(agent_scores.keys()),
        }


# =============================================================================
# TEST CLASS: Full Evaluation Flow
# =============================================================================


@pytest.mark.evaluation
class TestFullEvaluationFlow:
    """Test the complete evaluation flow with mock agent."""

    def test_load_task_corpus(self, task_corpus: TaskCorpus):
        """Test loading the task corpus."""
        tasks = task_corpus.list_tasks()
        assert len(tasks) > 0

        # Check summary has categories
        summary = task_corpus.summary()
        assert summary["total_tasks"] > 0
        assert len(summary["by_category"]) > 0
        assert len(summary["by_difficulty"]) > 0

    def test_filter_tasks_by_category(self, task_corpus: TaskCorpus):
        """Test filtering tasks by category."""
        filter_obj = TaskFilter(categories=[TaskCategory.CODING])
        tasks = task_corpus.list_tasks(filter_obj)

        assert len(tasks) > 0
        for task in tasks:
            # Handle both enum and string values
            cat = task.category.value if hasattr(task.category, 'value') else task.category
            assert cat == TaskCategory.CODING.value

    def test_filter_tasks_by_difficulty(self, task_corpus: TaskCorpus):
        """Test filtering tasks by difficulty."""
        filter_obj = TaskFilter(difficulties=[TaskDifficulty.EASY])
        tasks = task_corpus.list_tasks(filter_obj)

        assert len(tasks) > 0
        for task in tasks:
            diff = task.difficulty.value if hasattr(task.difficulty, 'value') else task.difficulty
            assert diff == TaskDifficulty.EASY.value

    def test_filter_tasks_by_capabilities(self, task_corpus: TaskCorpus):
        """Test filtering tasks by required capabilities."""
        filter_obj = TaskFilter(capabilities=[Capability.CODE_GENERATION])
        tasks = task_corpus.list_tasks(filter_obj)

        assert len(tasks) > 0
        for task in tasks:
            caps = [c.value if hasattr(c, 'value') else c for c in task.capabilities_tested]
            assert Capability.CODE_GENERATION.value in caps

    def test_task_prompt_rendering(self, task_corpus: TaskCorpus):
        """Test that task prompts render correctly with variables."""
        tasks = task_corpus.list_tasks()
        task = tasks[0]

        # Provide variable values if needed
        variables = {v.name: v.default or "test" for v in task.variables}
        rendered = task.render_prompt(variables)

        # Should not contain unrendered placeholders with double braces
        assert "{{" not in rendered or "}}" not in rendered

    @pytest.mark.asyncio
    async def test_full_evaluation_flow(
        self,
        task_corpus: TaskCorpus,
        mock_agent: MockAgent,
        quality_scorer: QualityScorer,
    ):
        """Test complete evaluation flow: load -> filter -> run -> score."""
        # Filter to a subset of tasks
        filter_obj = TaskFilter(
            categories=[TaskCategory.CODING],
            difficulties=[TaskDifficulty.EASY],
        )

        # Create evaluation runner
        evaluation = SimpleEvaluationRunner(
            corpus=task_corpus,
            agents=[mock_agent],
            scorer=quality_scorer,
        )

        # Run evaluation (limit to 2 tasks)
        results = await evaluation.run(task_filter=filter_obj, max_tasks=2)

        # Verify results
        assert len(results) > 0
        for result in results:
            assert result.task_id
            assert result.agent_name == mock_agent.name
            assert result.response_time_ms > 0
            assert result.token_usage is not None
            assert result.score is not None
            assert 0.0 <= result.score <= 1.0

    @pytest.mark.asyncio
    async def test_evaluation_tracks_metrics(
        self,
        task_corpus: TaskCorpus,
        mock_agent: MockAgent,
        quality_scorer: QualityScorer,
    ):
        """Test that evaluation tracks cost, latency, and quality scores."""
        evaluation = SimpleEvaluationRunner(
            corpus=task_corpus,
            agents=[mock_agent],
            scorer=quality_scorer,
        )

        results = await evaluation.run(max_tasks=3)

        # Verify metrics are tracked
        total_tokens = 0
        total_time = 0
        scores = []

        for result in results:
            assert result.token_usage is not None
            total_tokens += result.token_usage.get("total", 0)
            total_time += result.response_time_ms
            if result.score is not None:
                scores.append(result.score)

        assert total_tokens > 0, "Should track token usage"
        assert total_time > 0, "Should track response time"
        assert all(0 <= s <= 1 for s in scores), "Scores should be normalized"


# =============================================================================
# TEST CLASS: Rate-Limited Parallel Evaluation
# =============================================================================


@pytest.mark.evaluation
class TestRateLimitedEvaluation:
    """Test rate-limited parallel evaluation."""

    @pytest.mark.asyncio
    async def test_evaluation_with_rate_limiter(
        self,
        task_corpus: TaskCorpus,
        mock_agent: MockAgent,
        quality_scorer: QualityScorer,
    ):
        """Test evaluation with rate limiter configured."""
        # Configure rate limiter for mock provider
        config = RateLimitConfig(
            requests_per_minute=600,  # 10/sec
            tokens_per_minute=100_000,
            backpressure_strategy=BackpressureStrategy.QUEUE,
        )
        rate_limiter = RateLimiter(config=config, name="mock-limiter")

        evaluation = SimpleEvaluationRunner(
            corpus=task_corpus,
            agents=[mock_agent],
            scorer=quality_scorer,
            rate_limiter=rate_limiter,
        )

        results = await evaluation.run(max_tasks=3)

        # Verify rate limiter was used
        assert rate_limiter.stats.requests_made >= len(results)
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_rate_limits_respected(self, mock_agent: MockAgent):
        """Test that rate limits are respected during parallel execution."""
        # Create a very restrictive rate limiter
        config = RateLimitConfig(
            requests_per_minute=60,  # 1/sec
            tokens_per_minute=10_000,
            burst_multiplier=1.0,  # No burst
            backpressure_strategy=BackpressureStrategy.QUEUE,
            max_wait_seconds=10.0,
        )
        rate_limiter = RateLimiter(config=config, name="restrictive-limiter")

        # Time multiple requests
        start = time.monotonic()

        async def rate_limited_call():
            async with rate_limiter.acquire(estimated_tokens=100):
                return await mock_agent.agenerate("Test prompt")

        # Run 3 requests - should take ~2 seconds due to rate limiting
        results = await asyncio.gather(*[rate_limited_call() for _ in range(3)])

        elapsed = time.monotonic() - start

        assert len(results) == 3
        # With 1 req/sec and 3 requests, should take at least 1.5 seconds
        assert elapsed >= 1.5, f"Rate limiting should slow down requests (took {elapsed:.2f}s)"
        assert rate_limiter.stats.requests_queued >= 2, "Requests should be queued"

    @pytest.mark.asyncio
    async def test_no_rejections_with_queue_strategy(
        self,
        task_corpus: TaskCorpus,
        mock_agent: MockAgent,
        quality_scorer: QualityScorer,
    ):
        """Test that QUEUE strategy doesn't reject requests."""
        # Use a reasonable rate that allows completion within test time
        config = RateLimitConfig(
            requests_per_minute=300,  # 5/sec - fast enough for tests
            tokens_per_minute=100_000,
            burst_multiplier=2.0,  # Allow burst for test
            backpressure_strategy=BackpressureStrategy.QUEUE,
            max_wait_seconds=30.0,
        )
        rate_limiter = RateLimiter(config=config, name="queue-limiter")

        evaluation = SimpleEvaluationRunner(
            corpus=task_corpus,
            agents=[mock_agent],
            scorer=quality_scorer,
            rate_limiter=rate_limiter,
        )

        results = await evaluation.run(max_tasks=5)

        # Should complete without rejections
        assert len(results) == 5
        assert rate_limiter.stats.requests_rejected == 0

    @pytest.mark.asyncio
    async def test_parallel_agents_with_rate_limiting(self):
        """Test multiple agents running in parallel with shared rate limiter."""
        agents = [
            MockAgent(name=f"agent-{i}", model="mock-model")
            for i in range(3)
        ]

        config = RateLimitConfig(
            requests_per_minute=1200,  # 20/sec - enough for parallel
            tokens_per_minute=200_000,
            backpressure_strategy=BackpressureStrategy.QUEUE,
        )
        rate_limiter = RateLimiter(config=config, name="shared-limiter")

        async def agent_call(agent: BaseAgent):
            async with rate_limiter.acquire(estimated_tokens=100):
                return await agent.agenerate("Test prompt")

        # Run all agents in parallel
        results = await asyncio.gather(*[agent_call(a) for a in agents])

        assert len(results) == 3
        assert rate_limiter.stats.requests_made == 3


# =============================================================================
# TEST CLASS: Multi-Agent Comparison
# =============================================================================


@pytest.mark.evaluation
class TestMultiAgentComparison:
    """Test multi-agent comparison scenarios."""

    @pytest.mark.asyncio
    async def test_compare_multiple_agents(
        self,
        task_corpus: TaskCorpus,
        quality_scorer: QualityScorer,
    ):
        """Test running same tasks against multiple agents."""
        # Create agents with different response patterns
        agents = [
            MockAgent(name="agent-fast", model="mock-fast"),
            MockAgent(name="agent-detailed", model="mock-detailed"),
            MockAgent(name="agent-concise", model="mock-concise"),
        ]

        evaluation = SimpleEvaluationRunner(
            corpus=task_corpus,
            agents=agents,
            scorer=quality_scorer,
        )

        results = await evaluation.run(max_tasks=2)

        # Should have results for each agent x task combination
        assert len(results) == 2 * 3  # 2 tasks x 3 agents

        # Verify all agents were evaluated
        agent_names = set(r.agent_name for r in results)
        assert len(agent_names) == 3

    @pytest.mark.asyncio
    async def test_comparison_report_generation(
        self,
        task_corpus: TaskCorpus,
        quality_scorer: QualityScorer,
    ):
        """Test generating comparison report across agents."""
        agents = [
            MockAgent(name="agent-a", model="model-a"),
            MockAgent(name="agent-b", model="model-b"),
        ]

        evaluation = SimpleEvaluationRunner(
            corpus=task_corpus,
            agents=agents,
            scorer=quality_scorer,
        )

        await evaluation.run(max_tasks=3)
        report = evaluation.get_comparison_report()

        assert "agent_avg_scores" in report
        assert "agent_avg_times" in report
        assert "total_evaluations" in report
        assert report["total_evaluations"] == 6  # 3 tasks x 2 agents
        assert len(report["agents_evaluated"]) == 2

    @pytest.mark.asyncio
    async def test_scores_vary_by_task_category(
        self,
        task_corpus: TaskCorpus,
    ):
        """Test that scores may vary based on task category."""
        # Create scorer (rules-only)
        scorer = QualityScorer()

        agent = MockAgent(name="test-agent", model="mock-model")

        # Get coding and documentation tasks
        coding_filter = TaskFilter(categories=[TaskCategory.CODING])
        doc_filter = TaskFilter(categories=[TaskCategory.DOCUMENTATION])

        coding_tasks = task_corpus.list_tasks(coding_filter)
        doc_tasks = task_corpus.list_tasks(doc_filter)

        # Evaluate both
        code_result = None
        doc_result = None

        if coding_tasks:
            task = coding_tasks[0]
            variables = {v.name: v.default or "" for v in task.variables}
            prompt = task.render_prompt(variables)
            response, _, _ = await agent.agenerate(prompt)
            code_result = scorer.score_sync(response, task)

        if doc_tasks:
            task = doc_tasks[0]
            variables = {v.name: v.default or "" for v in task.variables}
            prompt = task.render_prompt(variables)
            response, _, _ = await agent.agenerate(prompt)
            doc_result = scorer.score_sync(response, task)

        # Scores should be generated for both
        if code_result:
            assert 0.0 <= code_result.overall <= 1.0
        if doc_result:
            assert 0.0 <= doc_result.overall <= 1.0


# =============================================================================
# TEST CLASS: Task Corpus Loading
# =============================================================================


@pytest.mark.evaluation
class TestTaskCorpusLoading:
    """Test task corpus loading and validation."""

    def test_load_builtin_corpus(self):
        """Test loading the built-in corpus."""
        corpus = load_default_corpus()

        assert corpus is not None
        assert len(corpus.list_tasks()) > 0

    def test_tasks_have_required_fields(self, task_corpus: TaskCorpus):
        """Test that all tasks have required fields."""
        for task in task_corpus.list_tasks():
            assert task.id, "Task must have an ID"
            assert task.name, "Task must have a name"
            assert task.prompt_template, "Task must have a prompt template"
            assert task.category, "Task must have a category"
            assert task.difficulty, "Task must have a difficulty"

    def test_task_categories_are_valid(self, task_corpus: TaskCorpus):
        """Test that all task categories are valid enum values."""
        valid_categories = set(c.value for c in TaskCategory)
        for task in task_corpus.list_tasks():
            cat = task.category.value if hasattr(task.category, 'value') else task.category
            assert cat in valid_categories

    def test_task_difficulties_are_valid(self, task_corpus: TaskCorpus):
        """Test that all task difficulties are valid enum values."""
        valid_difficulties = set(d.value for d in TaskDifficulty)
        for task in task_corpus.list_tasks():
            diff = task.difficulty.value if hasattr(task.difficulty, 'value') else task.difficulty
            assert diff in valid_difficulties

    def test_corpus_has_diverse_categories(self, task_corpus: TaskCorpus):
        """Test that corpus has multiple categories."""
        summary = task_corpus.summary()
        categories = summary["by_category"]
        assert len(categories) >= 3, "Corpus should have diverse categories"

    def test_corpus_has_diverse_difficulties(self, task_corpus: TaskCorpus):
        """Test that corpus has multiple difficulty levels."""
        summary = task_corpus.summary()
        difficulties = summary["by_difficulty"]
        assert len(difficulties) >= 2, "Corpus should have varied difficulties"


# =============================================================================
# TEST CLASS: Quality Scoring Integration
# =============================================================================


@pytest.mark.evaluation
class TestQualityScoringIntegration:
    """Test quality scoring integration."""

    def test_score_mock_response_rule_based(self, task_corpus: TaskCorpus):
        """Test scoring mock responses with rule-based checks."""
        scorer = QualityScorer()
        tasks = task_corpus.list_tasks()
        task = tasks[0]

        # Generate a mock response
        mock_response = "def calculate_sum(a: int, b: int) -> int:\n    \"\"\"Calculate sum.\"\"\"\n    return a + b"

        score = scorer.score_sync(
            mock_response,
            task,
            task.reference_solution,
        )

        assert 0.0 <= score.overall <= 1.0
        assert len(score.dimensions) > 0
        for dim, dim_score in score.dimensions.items():
            assert 0.0 <= dim_score.score <= 1.0
            assert 0.0 <= dim_score.confidence <= 1.0
            assert dim_score.explanation

    def test_different_scoring_dimensions(self, task_corpus: TaskCorpus):
        """Test different scoring dimensions."""
        # All available dimensions
        all_dimensions = list(ScoringDimension)

        config = QualityScorerConfig(dimensions=all_dimensions)
        scorer = QualityScorer(config)

        tasks = task_corpus.list_tasks()
        task = tasks[0]

        response = "def example():\n    \"\"\"Example function.\"\"\"\n    return True"

        score = scorer.score_sync(response, task)

        # Should have scores for all dimensions used by rule-based scorer
        assert len(score.dimensions) > 0

    def test_scores_attached_to_results(
        self,
        task_corpus: TaskCorpus,
        mock_agent: MockAgent,
        quality_scorer: QualityScorer,
    ):
        """Test that scores are properly attached to evaluation results."""
        # Run a single evaluation
        tasks = task_corpus.list_tasks()
        task = tasks[0]
        variables = {v.name: v.default or "" for v in task.variables}
        prompt = task.render_prompt(variables)

        # Generate response
        response_text, response_time_ms, token_usage = asyncio.run(
            mock_agent.agenerate(prompt)
        )

        # Score
        score = quality_scorer.score_sync(
            response_text,
            task,
            task.reference_solution,
        )

        # Create result
        result = TaskResult(
            task_id=task.id,
            agent_name=mock_agent.name,
            model=mock_agent.model,
            prompt=prompt,
            response=response_text,
            response_time_ms=response_time_ms,
            token_usage={
                "input": token_usage.input if token_usage else 0,
                "output": token_usage.output if token_usage else 0,
                "total": token_usage.total if token_usage else 0,
            },
            score=score.overall,
            criteria_scores={dim.value: ds.score for dim, ds in score.dimensions.items()},
        )

        assert result.score == score.overall
        assert len(result.criteria_scores) > 0


# =============================================================================
# TEST CLASS: Integration with Existing Components
# =============================================================================


@pytest.mark.evaluation
class TestExistingComponentIntegration:
    """Test integration with existing SDK components."""

    def test_integration_with_benchmark_runner(
        self,
        framework: AgentFramework,
        mock_agent: MockAgent,
    ):
        """Test that evaluation works alongside BenchmarkRunner."""
        runner = BenchmarkRunner(framework)

        # Run a benchmark
        result = runner.run_benchmark(
            prompt_content="Write a hello world function",
            agents=[mock_agent],
            benchmark_name="eval-integration-test",
        )

        assert result is not None
        assert "benchmark" in result
        assert "responses" in result
        assert len(result["responses"]) == 1

    def test_integration_with_provider_registry(self):
        """Test that evaluation works with provider registry."""
        ProviderRegistry.discover()

        # Get mock provider
        provider = ProviderRegistry.get_provider("mock")
        assert provider is not None

        # Create agent via provider
        agent = provider.create_agent("mock-model")
        assert agent is not None
        assert isinstance(agent, MockAgent)

    @pytest.mark.asyncio
    async def test_framework_records_evaluation_responses(
        self,
        framework: AgentFramework,
        task_corpus: TaskCorpus,
        mock_agent: MockAgent,
    ):
        """Test that evaluation responses can be recorded in framework."""
        tasks = task_corpus.list_tasks()
        task = tasks[0]
        variables = {v.name: v.default or "" for v in task.variables}
        prompt = task.render_prompt(variables)

        # Create prompt in framework
        stored_prompt = framework.create_prompt(
            content=prompt,
            version="1.0.0",
            tags=["evaluation"],
        )

        # Generate response
        response = await mock_agent.acreate_response(
            prompt_id=stored_prompt.id,
            prompt=prompt,
        )

        # Record response
        recorded = framework.record_response(
            prompt_id=stored_prompt.id,
            agent_name=response.agent_name,
            model=response.model,
            response=response.response,
            response_time_ms=response.response_time_ms,
            token_usage=response.token_usage,
        )

        # Verify
        assert recorded is not None
        assert framework.get_response(recorded.id) is not None


# =============================================================================
# TEST CLASS: Sync/Async Variants
# =============================================================================


@pytest.mark.evaluation
class TestSyncAsyncVariants:
    """Test both sync and async evaluation variants."""

    def test_sync_evaluation_flow(
        self,
        task_corpus: TaskCorpus,
        mock_agent: MockAgent,
        quality_scorer: QualityScorer,
    ):
        """Test synchronous evaluation flow."""
        tasks = task_corpus.list_tasks()
        task = tasks[0]
        variables = {v.name: v.default or "" for v in task.variables}
        prompt = task.render_prompt(variables)

        # Sync generate
        response_text, response_time_ms, token_usage = mock_agent.generate(prompt)

        # Score
        score = quality_scorer.score_sync(response_text, task)

        assert response_text
        assert response_time_ms > 0
        assert 0.0 <= score.overall <= 1.0

    @pytest.mark.asyncio
    async def test_async_evaluation_flow(
        self,
        task_corpus: TaskCorpus,
        mock_agent: MockAgent,
        quality_scorer: QualityScorer,
    ):
        """Test asynchronous evaluation flow."""
        tasks = task_corpus.list_tasks()
        task = tasks[0]
        variables = {v.name: v.default or "" for v in task.variables}
        prompt = task.render_prompt(variables)

        # Async generate
        response_text, response_time_ms, token_usage = await mock_agent.agenerate(prompt)

        # Score
        score = quality_scorer.score_sync(response_text, task)

        assert response_text
        assert response_time_ms > 0
        assert 0.0 <= score.overall <= 1.0

    @pytest.mark.asyncio
    async def test_sync_async_parity(
        self,
        task_corpus: TaskCorpus,
        quality_scorer: QualityScorer,
    ):
        """Test that sync and async produce similar results."""
        tasks = task_corpus.list_tasks()
        task = tasks[0]
        variables = {v.name: v.default or "" for v in task.variables}
        prompt = task.render_prompt(variables)

        # Create two agents
        agent_sync = MockAgent(name="sync", model="mock-model")
        agent_async = MockAgent(name="async", model="mock-model")

        # Generate responses
        sync_response, sync_time, sync_usage = agent_sync.generate(prompt)
        async_response, async_time, async_usage = await agent_async.agenerate(prompt)

        # Both should work
        assert sync_response
        assert async_response

        # Usage should be similar (same model, same prompt)
        assert sync_usage.total > 0
        assert async_usage.total > 0


# =============================================================================
# TEST CLASS: Edge Cases
# =============================================================================


@pytest.mark.evaluation
class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_corpus(self):
        """Test handling of empty corpus."""
        corpus = TaskCorpus(name="empty", description="Empty corpus")

        assert len(corpus.list_tasks()) == 0

    def test_filter_no_matches(self, task_corpus: TaskCorpus):
        """Test filter that matches no tasks."""
        # Use a filter that likely matches nothing
        filter_obj = TaskFilter(
            ids=["non-existent-task-id"],
        )

        tasks = task_corpus.list_tasks(filter_obj)
        # May be empty, which is fine
        assert isinstance(tasks, list)

    def test_scoring_empty_response(self, task_corpus: TaskCorpus):
        """Test scoring an empty response."""
        scorer = QualityScorer()
        tasks = task_corpus.list_tasks()
        task = tasks[0]

        score = scorer.score_sync("", task)

        # Should return score (may be low)
        assert 0.0 <= score.overall <= 1.0

    def test_scoring_very_long_response(self, task_corpus: TaskCorpus):
        """Test scoring a very long response."""
        scorer = QualityScorer()
        tasks = task_corpus.list_tasks()
        task = tasks[0]

        # Generate very long response
        long_response = "This is a test response. " * 1000

        score = scorer.score_sync(long_response, task)

        assert 0.0 <= score.overall <= 1.0

    @pytest.mark.asyncio
    async def test_evaluation_with_single_task(
        self,
        mock_agent: MockAgent,
        quality_scorer: QualityScorer,
    ):
        """Test evaluation with only one task."""
        # Create a single task corpus
        from startd8.evaluation import Task, TaskVariable

        single_task = Task(
            id="single-task",
            name="Single Task",
            description="Test",
            prompt_template="Hello {{NAME}}!",
            category=TaskCategory.DOCUMENTATION,
            difficulty=TaskDifficulty.EASY,
            variables=[TaskVariable(name="NAME", default="World", required=False)],
        )

        corpus = TaskCorpus(name="single", description="Single task corpus")
        corpus.add_task(single_task)

        evaluation = SimpleEvaluationRunner(
            corpus=corpus,
            agents=[mock_agent],
            scorer=quality_scorer,
        )

        results = await evaluation.run()

        assert len(results) == 1
        assert results[0].task_id == "single-task"

    def test_task_with_no_reference_answer(self, quality_scorer: QualityScorer):
        """Test scoring when no reference answer is available."""
        from startd8.evaluation import Task

        task = Task(
            id="no-ref-task",
            name="No Reference",
            description="Test",
            prompt_template="Generate something creative",
            category=TaskCategory.DOCUMENTATION,
            difficulty=TaskDifficulty.MEDIUM,
            reference_solution=None,  # No reference
        )

        score = quality_scorer.score_sync(
            "A creative response here",
            task,
            reference=None,
        )

        # Should still score based on other criteria
        assert 0.0 <= score.overall <= 1.0


# =============================================================================
# TEST CLASS: EvaluationRun Model Tests
# =============================================================================


@pytest.mark.evaluation
class TestEvaluationRunModel:
    """Test the EvaluationRun Pydantic model."""

    def test_evaluation_run_creation(self):
        """Test creating an EvaluationRun."""
        run = EvaluationRun(corpus_name="test-corpus")

        assert run.run_id is not None
        assert run.corpus_name == "test-corpus"
        assert len(run.results) == 0
        assert run.started_at is not None
        assert run.completed_at is None

    def test_evaluation_run_add_result(self):
        """Test adding results to an EvaluationRun."""
        run = EvaluationRun(corpus_name="test-corpus")

        result = TaskResult(
            task_id="task-1",
            agent_name="test-agent",
            model="mock-model",
            prompt="Test prompt",
            response="Test response",
            response_time_ms=100,
            score=0.8,
        )

        run.add_result(result)

        assert run.total_tasks == 1
        assert run.tasks_scored == 1
        assert run.average_score == 0.8

    def test_evaluation_run_complete(self):
        """Test completing an EvaluationRun."""
        run = EvaluationRun(corpus_name="test-corpus")

        assert run.completed_at is None
        run.complete()
        assert run.completed_at is not None

    def test_evaluation_run_summary_by_agent(self):
        """Test summary by agent."""
        run = EvaluationRun(corpus_name="test-corpus")

        run.add_result(TaskResult(
            task_id="task-1",
            agent_name="agent-a",
            model="model-a",
            prompt="prompt",
            response="response",
            response_time_ms=100,
            score=0.8,
        ))
        run.add_result(TaskResult(
            task_id="task-2",
            agent_name="agent-a",
            model="model-a",
            prompt="prompt",
            response="response",
            response_time_ms=150,
            score=0.9,
        ))
        run.add_result(TaskResult(
            task_id="task-1",
            agent_name="agent-b",
            model="model-b",
            prompt="prompt",
            response="response",
            response_time_ms=200,
            score=0.7,
        ))

        summary = run.summary_by_agent()

        assert "agent-a" in summary
        assert "agent-b" in summary
        assert summary["agent-a"]["count"] == 2
        # Use pytest.approx for floating point comparison
        assert summary["agent-a"]["average_score"] == pytest.approx(0.85, rel=1e-9)
        assert summary["agent-b"]["count"] == 1


# =============================================================================
# RUN CONFIGURATION
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "evaluation"])
