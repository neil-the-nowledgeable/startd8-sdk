"""
Comprehensive unit tests for the Artisan Subagent Executor.

This module contains a complete test suite for the SubagentExecutor component,
including the reference implementation of the executor, all supporting types,
fixtures, and test cases covering invocation, retry logic, fallback mechanisms,
streaming, cost tracking, and concurrency.

All code is self-contained in a single file with no relative imports.

Test Coverage Areas:
    - TestSubagentInvocation: Basic invocation, input/output handling, token defaults
    - TestRetryLogic: Retry attempts, backoff, exception filtering, exhaustion
    - TestFallbackMechanism: Fallback invocation, cost tracking, failure propagation
    - TestStreamingBehavior: Chunk yielding, aggregation, error handling mid-stream
    - TestCostTracking: Accumulation, reset, precision, invocation counting
    - TestConcurrency: Parallel execution, ordering, thread-safe cost tracking
    - TestEdgeCases: Timeouts, large values, complex outputs, boundary conditions

Run with:
    pytest test_subagent_executor.py -v --tb=short
    pytest test_subagent_executor.py -v --cov --cov-report=term-missing
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, List, Optional, Tuple
from unittest.mock import AsyncMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# ENUMS AND DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────


class ExecutionStatus(Enum):
    """Status of a subagent execution."""

    SUCCESS = "success"
    FAILED = "failed"
    FALLBACK = "fallback"


@dataclass
class ExecutorConfig:
    """Configuration for the SubagentExecutor.

    Attributes:
        max_retries: Maximum number of retry attempts after initial failure.
        retry_delay: Base delay in seconds between retries.
        retry_backoff_multiplier: Multiplier applied to delay for exponential backoff.
        retry_on_exceptions: Tuple of exception types that trigger retry.
        timeout: Maximum seconds to wait for a single subagent execution.
    """

    max_retries: int = 3
    retry_delay: float = 0.1
    retry_backoff_multiplier: float = 2.0
    retry_on_exceptions: Tuple[type, ...] = field(default_factory=lambda: (Exception,))
    timeout: float = 30.0


@dataclass
class TokenUsage:
    """Token usage metrics for a single invocation or chunk.

    Attributes:
        input_tokens: Number of input tokens consumed.
        output_tokens: Number of output tokens generated.
        cost_usd: Monetary cost in USD.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class CostSummary:
    """Accumulated cost and token metrics across all invocations.

    Attributes:
        total_input_tokens: Sum of input tokens across all invocations.
        total_output_tokens: Sum of output tokens across all invocations.
        total_cost_usd: Sum of costs across all invocations.
        invocation_count: Number of successful cost-accumulation events.
    """

    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    invocation_count: int = 0


@dataclass
class ExecutionResult:
    """Result of a subagent invocation.

    Attributes:
        status: Final execution status (SUCCESS, FAILED, or FALLBACK).
        output: The output value from the subagent, or None on failure.
        error: Error message string if execution failed, else None.
        token_usage: Token and cost metrics for this invocation.
        retries_attempted: Number of retry attempts made.
        duration_seconds: Wall-clock duration of the entire invocation.
    """

    status: ExecutionStatus = ExecutionStatus.SUCCESS
    output: Any = None
    error: Optional[str] = None
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    retries_attempted: int = 0
    duration_seconds: float = 0.0


@dataclass
class StreamChunk:
    """A single chunk of streaming output from a subagent.

    Attributes:
        content: The text content of this chunk.
        is_final: Whether this is the final sentinel chunk.
        token_usage: Optional token metrics associated with this chunk.
    """

    content: str = ""
    is_final: bool = False
    token_usage: Optional[TokenUsage] = None


@dataclass
class SubagentTask:
    """A task to execute a subagent with specific input.

    Attributes:
        subagent: The subagent instance to invoke.
        input_data: Input dictionary for the subagent.
        kwargs: Additional keyword arguments passed to execute().
    """

    subagent: Any
    input_data: dict = field(default_factory=dict)
    kwargs: dict = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# SUBAGENT PROTOCOL
# ─────────────────────────────────────────────────────────────────────────────


class Subagent:
    """Base protocol for subagents that can be executed.

    Subclasses must implement execute() and optionally execute_stream().
    """

    async def execute(self, input_data: dict, **kwargs) -> dict:
        """Execute the subagent synchronously (single invocation).

        Args:
            input_data: Input dictionary for the subagent.
            **kwargs: Additional keyword arguments.

        Returns:
            Dictionary with 'output' and optionally 'input_tokens',
            'output_tokens', and 'cost_usd' keys.
        """
        raise NotImplementedError

    async def execute_stream(self, input_data: dict, **kwargs) -> AsyncIterator[StreamChunk]:
        """Execute the subagent with streaming output.

        Args:
            input_data: Input dictionary for the subagent.
            **kwargs: Additional keyword arguments.

        Yields:
            StreamChunk objects representing incremental output.
        """
        raise NotImplementedError
        yield  # pragma: no cover — makes this a generator


# ─────────────────────────────────────────────────────────────────────────────
# REFERENCE IMPLEMENTATION: SubagentExecutor
# ─────────────────────────────────────────────────────────────────────────────


class SubagentExecutor:
    """Subagent Executor with retry, fallback, streaming, cost tracking, and concurrency.

    This executor wraps subagent invocations with:
      - Configurable retry logic with exponential backoff
      - Optional fallback subagent when primary exhausts retries
      - Streaming output support with incremental chunk yielding
      - Thread-safe cost and token usage accumulation
      - Concurrent execution of multiple subagent tasks

    Args:
        config: ExecutorConfig with retry and timeout settings.
        fallback_subagent: Optional fallback subagent if primary fails.
    """

    def __init__(
        self,
        config: Optional[ExecutorConfig] = None,
        fallback_subagent: Optional[Subagent] = None,
    ) -> None:
        self.config = config or ExecutorConfig()
        self.fallback_subagent = fallback_subagent
        self._cost_lock = asyncio.Lock()
        self._cost_summary = CostSummary()

    async def invoke(self, subagent: Subagent, input_data: dict, **kwargs) -> ExecutionResult:
        """Invoke a subagent with retry logic and optional fallback.

        Attempts the primary subagent up to (max_retries + 1) times with
        exponential backoff. If all attempts fail and a fallback subagent
        is configured, the fallback is tried once.

        Args:
            subagent: The subagent to invoke.
            input_data: Input dictionary for the subagent.
            **kwargs: Additional keyword arguments forwarded to execute().

        Returns:
            ExecutionResult with status, output, error, token usage, and timing.
        """
        start = time.monotonic()
        last_exception: Optional[Exception] = None
        retries = 0

        # Primary invocation with retries
        for attempt in range(self.config.max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    subagent.execute(input_data, **kwargs), timeout=self.config.timeout
                )
                token_usage = TokenUsage(
                    input_tokens=result.get("input_tokens", 0),
                    output_tokens=result.get("output_tokens", 0),
                    cost_usd=result.get("cost_usd", 0.0),
                )
                await self._accumulate_cost(token_usage)
                return ExecutionResult(
                    status=ExecutionStatus.SUCCESS,
                    output=result.get("output"),
                    token_usage=token_usage,
                    retries_attempted=retries,
                    duration_seconds=time.monotonic() - start,
                )
            except self.config.retry_on_exceptions as err:
                last_exception = err
                retries = attempt + 1
                if attempt < self.config.max_retries:
                    delay = self.config.retry_delay * (
                        self.config.retry_backoff_multiplier ** attempt
                    )
                    await asyncio.sleep(delay)
            except Exception as err:
                # Non-retryable exception: fail immediately
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    error=str(err),
                    retries_attempted=retries,
                    duration_seconds=time.monotonic() - start,
                )

        # All retries exhausted — try fallback if configured
        if self.fallback_subagent is not None:
            try:
                result = await asyncio.wait_for(
                    self.fallback_subagent.execute(input_data, **kwargs),
                    timeout=self.config.timeout,
                )
                token_usage = TokenUsage(
                    input_tokens=result.get("input_tokens", 0),
                    output_tokens=result.get("output_tokens", 0),
                    cost_usd=result.get("cost_usd", 0.0),
                )
                await self._accumulate_cost(token_usage)
                return ExecutionResult(
                    status=ExecutionStatus.FALLBACK,
                    output=result.get("output"),
                    token_usage=token_usage,
                    retries_attempted=retries,
                    duration_seconds=time.monotonic() - start,
                )
            except Exception as fallback_err:
                return ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    error=f"Fallback failed: {fallback_err}",
                    retries_attempted=retries,
                    duration_seconds=time.monotonic() - start,
                )

        return ExecutionResult(
            status=ExecutionStatus.FAILED,
            error=str(last_exception),
            retries_attempted=retries,
            duration_seconds=time.monotonic() - start,
        )

    async def invoke_stream(
        self, subagent: Subagent, input_data: dict, **kwargs
    ) -> AsyncIterator[StreamChunk]:
        """Invoke a subagent and stream partial results.

        Yields each chunk from the subagent's execute_stream(), followed by
        a final sentinel chunk with aggregated token metrics. On error,
        yields an error chunk with partial metrics.

        Args:
            subagent: The subagent to invoke.
            input_data: Input dictionary for the subagent.
            **kwargs: Additional keyword arguments.

        Yields:
            StreamChunk objects with partial output, ending with a final chunk.
        """
        total_usage = TokenUsage()

        try:
            async for chunk in subagent.execute_stream(input_data, **kwargs):
                if chunk.token_usage:
                    total_usage.input_tokens += chunk.token_usage.input_tokens
                    total_usage.output_tokens += chunk.token_usage.output_tokens
                    total_usage.cost_usd += chunk.token_usage.cost_usd
                yield chunk

            await self._accumulate_cost(total_usage)
            yield StreamChunk(content="", is_final=True, token_usage=total_usage)
        except Exception as err:
            await self._accumulate_cost(total_usage)
            yield StreamChunk(
                content=f"[ERROR: {err}]", is_final=True, token_usage=total_usage
            )

    async def invoke_concurrent(self, tasks: List[SubagentTask]) -> List[ExecutionResult]:
        """Invoke multiple subagents concurrently.

        All tasks are started simultaneously via asyncio.gather. Results
        are returned in the same order as the input tasks list.

        Args:
            tasks: List of SubagentTask objects to execute in parallel.

        Returns:
            List of ExecutionResult objects in the same order as tasks.
        """
        coroutines = [
            self.invoke(task.subagent, task.input_data, **task.kwargs) for task in tasks
        ]
        results = await asyncio.gather(*coroutines, return_exceptions=False)
        return list(results)

    def get_cost_summary(self) -> CostSummary:
        """Get the current cost summary as an independent copy.

        Returns:
            CostSummary with aggregated metrics. Modifying the returned
            object does not affect the executor's internal state.
        """
        return CostSummary(
            total_input_tokens=self._cost_summary.total_input_tokens,
            total_output_tokens=self._cost_summary.total_output_tokens,
            total_cost_usd=self._cost_summary.total_cost_usd,
            invocation_count=self._cost_summary.invocation_count,
        )

    def reset_cost_tracking(self) -> None:
        """Reset all accumulated cost metrics to zero."""
        self._cost_summary = CostSummary()

    async def _accumulate_cost(self, usage: TokenUsage) -> None:
        """Accumulate token usage and cost metrics in a concurrency-safe manner.

        Args:
            usage: TokenUsage object to add to the running totals.
        """
        async with self._cost_lock:
            self._cost_summary.total_input_tokens += usage.input_tokens
            self._cost_summary.total_output_tokens += usage.output_tokens
            self._cost_summary.total_cost_usd += usage.cost_usd
            self._cost_summary.invocation_count += 1


# ─────────────────────────────────────────────────────────────────────────────
# PYTEST FIXTURES
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def default_config() -> ExecutorConfig:
    """Executor configuration with fast retries for testing."""
    return ExecutorConfig(
        max_retries=3, retry_delay=0.01, retry_backoff_multiplier=1.0, timeout=5.0
    )


@pytest.fixture
def no_retry_config() -> ExecutorConfig:
    """Executor configuration with zero retries."""
    return ExecutorConfig(max_retries=0, retry_delay=0.0, timeout=5.0)


@pytest.fixture
def single_retry_config() -> ExecutorConfig:
    """Executor configuration allowing exactly one retry."""
    return ExecutorConfig(max_retries=1, retry_delay=0.01, timeout=5.0)


@pytest.fixture
def mock_subagent() -> AsyncMock:
    """Mock subagent that returns a successful response with token metrics."""
    agent = AsyncMock(spec=Subagent)
    agent.execute = AsyncMock(
        return_value={
            "output": "Hello, world!",
            "input_tokens": 10,
            "output_tokens": 20,
            "cost_usd": 0.001,
        }
    )
    return agent


@pytest.fixture
def mock_fallback_subagent() -> AsyncMock:
    """Mock fallback subagent that returns a successful response."""
    agent = AsyncMock(spec=Subagent)
    agent.execute = AsyncMock(
        return_value={
            "output": "Fallback response",
            "input_tokens": 5,
            "output_tokens": 10,
            "cost_usd": 0.0005,
        }
    )
    return agent


@pytest.fixture
def executor(default_config: ExecutorConfig) -> SubagentExecutor:
    """Executor with default test configuration, no fallback."""
    return SubagentExecutor(config=default_config)


@pytest.fixture
def executor_with_fallback(
    default_config: ExecutorConfig, mock_fallback_subagent: AsyncMock
) -> SubagentExecutor:
    """Executor with default test configuration and a fallback subagent."""
    return SubagentExecutor(config=default_config, fallback_subagent=mock_fallback_subagent)


@pytest.fixture
def executor_no_retry(no_retry_config: ExecutorConfig) -> SubagentExecutor:
    """Executor configured with zero retries."""
    return SubagentExecutor(config=no_retry_config)


# ─────────────────────────────────────────────────────────────────────────────
# TEST CLASS: TestSubagentInvocation
# ─────────────────────────────────────────────────────────────────────────────


class TestSubagentInvocation:
    """Tests for basic subagent invocation and result handling."""

    @pytest.mark.asyncio
    async def test_invoke_success(
        self, executor: SubagentExecutor, mock_subagent: AsyncMock
    ) -> None:
        """Successful invocation returns SUCCESS with correct output and metrics."""
        result = await executor.invoke(mock_subagent, {"prompt": "Hello"})

        assert result.status == ExecutionStatus.SUCCESS
        assert result.output == "Hello, world!"
        assert result.token_usage.input_tokens == 10
        assert result.token_usage.output_tokens == 20
        assert result.token_usage.cost_usd == pytest.approx(0.001)
        assert result.retries_attempted == 0
        assert result.duration_seconds > 0
        assert result.error is None
        mock_subagent.execute.assert_awaited_once_with({"prompt": "Hello"})

    @pytest.mark.asyncio
    async def test_invoke_passes_input_data_and_kwargs(
        self, executor: SubagentExecutor, mock_subagent: AsyncMock
    ) -> None:
        """Input data and kwargs are correctly forwarded to subagent.execute."""
        await executor.invoke(
            mock_subagent, {"key": "value"}, extra_param="extra_value", flag=True
        )

        mock_subagent.execute.assert_awaited_once_with(
            {"key": "value"}, extra_param="extra_value", flag=True
        )

    @pytest.mark.asyncio
    async def test_invoke_returns_execution_result_type(
        self, executor: SubagentExecutor, mock_subagent: AsyncMock
    ) -> None:
        """Invoke returns properly typed ExecutionResult with correct field types."""
        result = await executor.invoke(mock_subagent, {})

        assert isinstance(result, ExecutionResult)
        assert isinstance(result.status, ExecutionStatus)
        assert isinstance(result.token_usage, TokenUsage)

    @pytest.mark.asyncio
    async def test_invoke_records_duration(
        self, executor: SubagentExecutor, mock_subagent: AsyncMock
    ) -> None:
        """Duration is measured and within reasonable bounds."""
        result = await executor.invoke(mock_subagent, {})

        assert result.duration_seconds > 0
        assert result.duration_seconds < 5.0

    @pytest.mark.asyncio
    async def test_invoke_with_default_config(self, mock_subagent: AsyncMock) -> None:
        """Executor with no explicit config uses sensible defaults."""
        executor = SubagentExecutor()
        result = await executor.invoke(mock_subagent, {})

        assert result.status == ExecutionStatus.SUCCESS
        assert executor.config.max_retries == 3
        assert executor.config.timeout == 30.0

    @pytest.mark.asyncio
    async def test_invoke_with_empty_input(
        self, executor: SubagentExecutor, mock_subagent: AsyncMock
    ) -> None:
        """Empty input dictionary is valid and passes through correctly."""
        result = await executor.invoke(mock_subagent, {})

        assert result.status == ExecutionStatus.SUCCESS
        assert result.output == "Hello, world!"
        mock_subagent.execute.assert_awaited_once_with({})

    @pytest.mark.asyncio
    async def test_invoke_with_missing_token_fields(
        self, executor: SubagentExecutor
    ) -> None:
        """Missing token fields in response default to zero."""
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(return_value={"output": "test"})

        result = await executor.invoke(mock_agent, {})

        assert result.token_usage.input_tokens == 0
        assert result.token_usage.output_tokens == 0
        assert result.token_usage.cost_usd == 0.0
        assert result.output == "test"

    @pytest.mark.asyncio
    async def test_invoke_with_partial_token_fields(
        self, executor: SubagentExecutor
    ) -> None:
        """Partial token fields are preserved; missing ones default to zero."""
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(
            return_value={"output": "test", "input_tokens": 5, "cost_usd": 0.0002}
        )

        result = await executor.invoke(mock_agent, {})

        assert result.token_usage.input_tokens == 5
        assert result.token_usage.output_tokens == 0
        assert result.token_usage.cost_usd == pytest.approx(0.0002)

    @pytest.mark.asyncio
    async def test_invoke_with_none_output(self, executor: SubagentExecutor) -> None:
        """Missing 'output' key in response results in None output."""
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(return_value={})

        result = await executor.invoke(mock_agent, {})

        assert result.output is None
        assert result.status == ExecutionStatus.SUCCESS


# ─────────────────────────────────────────────────────────────────────────────
# TEST CLASS: TestRetryLogic
# ─────────────────────────────────────────────────────────────────────────────


class TestRetryLogic:
    """Tests for retry behavior and transient failure handling."""

    @pytest.mark.asyncio
    async def test_retry_on_transient_failure_then_success(
        self, executor: SubagentExecutor
    ) -> None:
        """Transient failures are retried until a successful attempt."""
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(
            side_effect=[
                RuntimeError("Transient error 1"),
                RuntimeError("Transient error 2"),
                {
                    "output": "Recovered!",
                    "input_tokens": 5,
                    "output_tokens": 10,
                    "cost_usd": 0.0005,
                },
            ]
        )

        result = await executor.invoke(mock_agent, {"prompt": "test"})

        assert result.status == ExecutionStatus.SUCCESS
        assert result.output == "Recovered!"
        assert result.retries_attempted == 2
        assert mock_agent.execute.await_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted_returns_failed(
        self, executor: SubagentExecutor
    ) -> None:
        """FAILED status is returned when all retry attempts are exhausted."""
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(side_effect=RuntimeError("Persistent error"))

        result = await executor.invoke(mock_agent, {})

        assert result.status == ExecutionStatus.FAILED
        assert result.output is None
        assert result.error == "Persistent error"
        assert result.retries_attempted == 4
        # max_retries=3: initial attempt + 3 retries = 4 total calls, retries counted as attempt+1
        assert mock_agent.execute.await_count == 4

    @pytest.mark.asyncio
    async def test_retry_respects_max_retries_config(
        self, single_retry_config: ExecutorConfig
    ) -> None:
        """max_retries configuration is respected exactly."""
        executor = SubagentExecutor(config=single_retry_config)
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(side_effect=RuntimeError("Persistent error"))

        result = await executor.invoke(mock_agent, {})

        assert result.status == ExecutionStatus.FAILED
        assert result.retries_attempted == 2
        # max_retries=1: initial + 1 retry = 2 total calls, retries counted as attempt+1
        assert mock_agent.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_retry_with_zero_retries(self, no_retry_config: ExecutorConfig) -> None:
        """max_retries=0 means no retries; single attempt then failure."""
        executor = SubagentExecutor(config=no_retry_config)
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(side_effect=RuntimeError("Error"))

        result = await executor.invoke(mock_agent, {})

        assert result.status == ExecutionStatus.FAILED
        assert result.retries_attempted == 1
        assert mock_agent.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_retry_backoff_delay(self, default_config: ExecutorConfig) -> None:
        """Exponential backoff delays are calculated and applied correctly."""
        executor = SubagentExecutor(config=default_config)
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(
            side_effect=[
                RuntimeError("Error 1"),
                RuntimeError("Error 2"),
                RuntimeError("Error 3"),
                {
                    "output": "Success",
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cost_usd": 0.0001,
                },
            ]
        )

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            result = await executor.invoke(mock_agent, {})

        assert result.status == ExecutionStatus.SUCCESS
        # With retry_backoff_multiplier=1.0, all delays = 0.01
        assert mock_sleep.await_count == 3
        mock_sleep.assert_any_await(pytest.approx(0.01))

    @pytest.mark.asyncio
    async def test_retry_only_on_configured_exceptions(
        self, default_config: ExecutorConfig
    ) -> None:
        """Only configured exception types trigger retries."""
        executor = SubagentExecutor(
            config=ExecutorConfig(
                max_retries=3,
                retry_delay=0.01,
                retry_on_exceptions=(ValueError,),
            )
        )
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(side_effect=TypeError("Wrong type"))

        result = await executor.invoke(mock_agent, {})

        assert result.status == ExecutionStatus.FAILED
        assert result.retries_attempted == 0
        assert mock_agent.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_retry_preserves_last_error_message(
        self, executor: SubagentExecutor
    ) -> None:
        """Error message reflects the last exception encountered."""
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(side_effect=ValueError("Final error message"))

        result = await executor.invoke(mock_agent, {})

        assert result.status == ExecutionStatus.FAILED
        assert "Final error message" in result.error

    @pytest.mark.asyncio
    async def test_retry_success_on_last_attempt(
        self, single_retry_config: ExecutorConfig
    ) -> None:
        """Success on the final retry attempt is correctly recognized."""
        executor = SubagentExecutor(config=single_retry_config)
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(
            side_effect=[
                RuntimeError("First attempt fails"),
                {
                    "output": "Second attempt succeeds",
                    "input_tokens": 1,
                    "output_tokens": 1,
                    "cost_usd": 0.0001,
                },
            ]
        )

        result = await executor.invoke(mock_agent, {})

        assert result.status == ExecutionStatus.SUCCESS
        assert result.output == "Second attempt succeeds"
        assert result.retries_attempted == 1


# ─────────────────────────────────────────────────────────────────────────────
# TEST CLASS: TestFallbackMechanism
# ─────────────────────────────────────────────────────────────────────────────


class TestFallbackMechanism:
    """Tests for fallback subagent invocation and failure handling."""

    @pytest.mark.asyncio
    async def test_fallback_invoked_after_retries_exhausted(
        self,
        executor_with_fallback: SubagentExecutor,
        mock_fallback_subagent: AsyncMock,
    ) -> None:
        """Fallback is invoked when primary exhausts all retries."""
        mock_primary = AsyncMock(spec=Subagent)
        mock_primary.execute = AsyncMock(side_effect=RuntimeError("Primary fails"))

        result = await executor_with_fallback.invoke(mock_primary, {})

        assert result.status == ExecutionStatus.FALLBACK
        assert result.output == "Fallback response"
        mock_fallback_subagent.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fallback_not_invoked_on_success(
        self, executor_with_fallback: SubagentExecutor, mock_fallback_subagent: AsyncMock
    ) -> None:
        """Fallback is NOT invoked when primary succeeds."""
        mock_primary = AsyncMock(spec=Subagent)
        mock_primary.execute = AsyncMock(
            return_value={
                "output": "Primary success",
                "input_tokens": 1,
                "output_tokens": 1,
                "cost_usd": 0.0001,
            }
        )

        result = await executor_with_fallback.invoke(mock_primary, {})

        assert result.status == ExecutionStatus.SUCCESS
        mock_fallback_subagent.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fallback_not_invoked_when_not_configured(
        self, executor: SubagentExecutor
    ) -> None:
        """Absence of fallback results in FAILED status after retry exhaustion."""
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(side_effect=RuntimeError("Error"))

        result = await executor.invoke(mock_agent, {})

        assert result.status == ExecutionStatus.FAILED

    @pytest.mark.asyncio
    async def test_fallback_failure_returns_failed(
        self, executor_with_fallback: SubagentExecutor, mock_fallback_subagent: AsyncMock
    ) -> None:
        """Fallback failure results in FAILED status with descriptive error."""
        mock_fallback_subagent.execute = AsyncMock(
            side_effect=RuntimeError("Fallback error")
        )
        mock_primary = AsyncMock(spec=Subagent)
        mock_primary.execute = AsyncMock(side_effect=RuntimeError("Primary error"))

        result = await executor_with_fallback.invoke(mock_primary, {})

        assert result.status == ExecutionStatus.FAILED
        assert "Fallback failed" in result.error

    @pytest.mark.asyncio
    async def test_fallback_receives_same_input(
        self, executor_with_fallback: SubagentExecutor, mock_fallback_subagent: AsyncMock
    ) -> None:
        """Fallback receives the same input_data as the primary subagent."""
        input_data = {"key": "value", "nested": {"data": 123}}
        mock_primary = AsyncMock(spec=Subagent)
        mock_primary.execute = AsyncMock(side_effect=RuntimeError("Primary error"))

        await executor_with_fallback.invoke(mock_primary, input_data)

        mock_fallback_subagent.execute.assert_awaited_once_with(input_data)

    @pytest.mark.asyncio
    async def test_fallback_cost_is_tracked(
        self, executor_with_fallback: SubagentExecutor, mock_fallback_subagent: AsyncMock
    ) -> None:
        """Fallback token usage is accumulated in cost tracking."""
        mock_primary = AsyncMock(spec=Subagent)
        mock_primary.execute = AsyncMock(side_effect=RuntimeError("Primary error"))

        result = await executor_with_fallback.invoke(mock_primary, {})

        assert result.status == ExecutionStatus.FALLBACK
        summary = executor_with_fallback.get_cost_summary()
        assert summary.total_input_tokens == 5
        assert summary.total_output_tokens == 10
        assert summary.total_cost_usd == pytest.approx(0.0005)

    @pytest.mark.asyncio
    async def test_fallback_is_single_shot(
        self, default_config: ExecutorConfig, mock_fallback_subagent: AsyncMock
    ) -> None:
        """Fallback is attempted exactly once (no retries for fallback)."""
        executor = SubagentExecutor(
            config=default_config, fallback_subagent=mock_fallback_subagent
        )
        mock_fallback_subagent.execute = AsyncMock(
            side_effect=RuntimeError("Fallback error")
        )
        mock_primary = AsyncMock(spec=Subagent)
        mock_primary.execute = AsyncMock(side_effect=RuntimeError("Primary error"))

        result = await executor.invoke(mock_primary, {})

        assert result.status == ExecutionStatus.FAILED
        assert mock_fallback_subagent.execute.await_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# TEST CLASS: TestStreamingBehavior
# ─────────────────────────────────────────────────────────────────────────────


class TestStreamingBehavior:
    """Tests for streaming output and incremental result yielding."""

    @pytest.mark.asyncio
    async def test_stream_yields_chunks_incrementally(
        self, executor: SubagentExecutor
    ) -> None:
        """Stream yields all content chunks followed by a final sentinel."""
        chunks = [
            StreamChunk(
                content="Hello ",
                token_usage=TokenUsage(input_tokens=5, output_tokens=3, cost_usd=0.0001),
            ),
            StreamChunk(
                content="world",
                token_usage=TokenUsage(input_tokens=0, output_tokens=3, cost_usd=0.0001),
            ),
            StreamChunk(
                content="!",
                token_usage=TokenUsage(input_tokens=0, output_tokens=1, cost_usd=0.00005),
            ),
        ]

        mock_agent = AsyncMock(spec=Subagent)

        async def mock_stream(input_data: dict, **kwargs) -> AsyncIterator[StreamChunk]:
            for chunk in chunks:
                yield chunk

        mock_agent.execute_stream = mock_stream

        received = []
        async for chunk in executor.invoke_stream(mock_agent, {"prompt": "test"}):
            received.append(chunk)

        # 3 content chunks + 1 final sentinel
        assert len(received) == 4
        assert received[0].content == "Hello "
        assert received[1].content == "world"
        assert received[2].content == "!"
        assert received[3].is_final is True

    @pytest.mark.asyncio
    async def test_stream_final_chunk_has_aggregated_usage(
        self, executor: SubagentExecutor
    ) -> None:
        """Final chunk contains aggregated token metrics from all chunks."""
        chunks = [
            StreamChunk(
                content="A",
                token_usage=TokenUsage(input_tokens=5, output_tokens=3, cost_usd=0.0001),
            ),
            StreamChunk(
                content="B",
                token_usage=TokenUsage(input_tokens=0, output_tokens=3, cost_usd=0.0001),
            ),
        ]

        mock_agent = AsyncMock(spec=Subagent)

        async def mock_stream(input_data: dict, **kwargs) -> AsyncIterator[StreamChunk]:
            for chunk in chunks:
                yield chunk

        mock_agent.execute_stream = mock_stream

        final_chunk = None
        async for chunk in executor.invoke_stream(mock_agent, {}):
            if chunk.is_final:
                final_chunk = chunk

        assert final_chunk is not None
        assert final_chunk.token_usage.input_tokens == 5
        assert final_chunk.token_usage.output_tokens == 6
        assert final_chunk.token_usage.cost_usd == pytest.approx(0.0002)

    @pytest.mark.asyncio
    async def test_stream_empty_response(self, executor: SubagentExecutor) -> None:
        """Streaming with no content chunks still yields a final sentinel."""
        mock_agent = AsyncMock(spec=Subagent)

        async def mock_stream(input_data: dict, **kwargs) -> AsyncIterator[StreamChunk]:
            return
            yield  # pragma: no cover — makes this a generator

        mock_agent.execute_stream = mock_stream

        received = []
        async for chunk in executor.invoke_stream(mock_agent, {}):
            received.append(chunk)

        assert len(received) == 1
        assert received[0].is_final is True

    @pytest.mark.asyncio
    async def test_stream_error_midway(self, executor: SubagentExecutor) -> None:
        """Mid-stream errors are caught and reported in a final error chunk."""
        chunks = [
            StreamChunk(
                content="Start",
                token_usage=TokenUsage(input_tokens=5, output_tokens=2, cost_usd=0.0001),
            ),
        ]

        mock_agent = AsyncMock(spec=Subagent)

        async def mock_stream(input_data: dict, **kwargs) -> AsyncIterator[StreamChunk]:
            for chunk in chunks:
                yield chunk
            raise RuntimeError("Stream interrupted")

        mock_agent.execute_stream = mock_stream

        received = []
        async for chunk in executor.invoke_stream(mock_agent, {}):
            received.append(chunk)

        assert len(received) == 2
        assert received[0].content == "Start"
        assert received[1].is_final is True
        assert "[ERROR:" in received[1].content

    @pytest.mark.asyncio
    async def test_stream_cost_accumulated_on_success(
        self, executor: SubagentExecutor
    ) -> None:
        """Successful stream accumulates token usage in cost summary."""
        chunks = [
            StreamChunk(
                content="A",
                token_usage=TokenUsage(input_tokens=5, output_tokens=3, cost_usd=0.0001),
            ),
            StreamChunk(
                content="B",
                token_usage=TokenUsage(input_tokens=0, output_tokens=2, cost_usd=0.00005),
            ),
        ]

        mock_agent = AsyncMock(spec=Subagent)

        async def mock_stream(input_data: dict, **kwargs) -> AsyncIterator[StreamChunk]:
            for chunk in chunks:
                yield chunk

        mock_agent.execute_stream = mock_stream

        async for _ in executor.invoke_stream(mock_agent, {}):
            pass

        summary = executor.get_cost_summary()
        assert summary.total_input_tokens == 5
        assert summary.total_output_tokens == 5
        assert summary.total_cost_usd == pytest.approx(0.00015)
        assert summary.invocation_count == 1

    @pytest.mark.asyncio
    async def test_stream_cost_accumulated_on_error(
        self, executor: SubagentExecutor
    ) -> None:
        """Partial cost is tracked even when stream errors mid-way."""
        chunks = [
            StreamChunk(
                content="X",
                token_usage=TokenUsage(input_tokens=2, output_tokens=1, cost_usd=0.00001),
            ),
        ]

        mock_agent = AsyncMock(spec=Subagent)

        async def mock_stream(input_data: dict, **kwargs) -> AsyncIterator[StreamChunk]:
            for chunk in chunks:
                yield chunk
            raise ValueError("Stream failed")

        mock_agent.execute_stream = mock_stream

        async for _ in executor.invoke_stream(mock_agent, {}):
            pass

        summary = executor.get_cost_summary()
        assert summary.total_input_tokens == 2
        assert summary.total_output_tokens == 1
        assert summary.invocation_count == 1

    @pytest.mark.asyncio
    async def test_stream_chunks_without_token_usage(
        self, executor: SubagentExecutor
    ) -> None:
        """Chunks without token_usage don't cause errors; final metrics are zero."""
        chunks = [
            StreamChunk(content="Data"),
            StreamChunk(content=" continues"),
        ]

        mock_agent = AsyncMock(spec=Subagent)

        async def mock_stream(input_data: dict, **kwargs) -> AsyncIterator[StreamChunk]:
            for chunk in chunks:
                yield chunk

        mock_agent.execute_stream = mock_stream

        received = []
        async for chunk in executor.invoke_stream(mock_agent, {}):
            received.append(chunk)

        assert len(received) == 3  # 2 content + 1 final
        assert received[-1].token_usage.input_tokens == 0


# ─────────────────────────────────────────────────────────────────────────────
# TEST CLASS: TestCostTracking
# ─────────────────────────────────────────────────────────────────────────────


class TestCostTracking:
    """Tests for token usage and cost accumulation."""

    @pytest.mark.asyncio
    async def test_cost_accumulates_across_invocations(
        self, executor: SubagentExecutor
    ) -> None:
        """Multiple invocations accumulate costs correctly."""
        agents = []
        for idx in range(3):
            agent = AsyncMock(spec=Subagent)
            agent.execute = AsyncMock(
                return_value={
                    "output": f"result_{idx}",
                    "input_tokens": 10 * (idx + 1),
                    "output_tokens": 20 * (idx + 1),
                    "cost_usd": 0.001 * (idx + 1),
                }
            )
            agents.append(agent)

        for agent in agents:
            await executor.invoke(agent, {})

        summary = executor.get_cost_summary()
        assert summary.invocation_count == 3
        assert summary.total_input_tokens == 10 + 20 + 30  # 60
        assert summary.total_output_tokens == 20 + 40 + 60  # 120
        assert summary.total_cost_usd == pytest.approx(0.001 + 0.002 + 0.003)

    @pytest.mark.asyncio
    async def test_cost_includes_only_successful_attempts(
        self, executor: SubagentExecutor
    ) -> None:
        """Only the successful invocation's cost is tracked, not failed retries."""
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(
            side_effect=[
                RuntimeError("Fail 1"),
                RuntimeError("Fail 2"),
                {
                    "output": "Success",
                    "input_tokens": 100,
                    "output_tokens": 200,
                    "cost_usd": 0.01,
                },
            ]
        )

        result = await executor.invoke(mock_agent, {})

        assert result.status == ExecutionStatus.SUCCESS
        summary = executor.get_cost_summary()
        assert summary.total_input_tokens == 100
        assert summary.total_output_tokens == 200
        assert summary.invocation_count == 1

    @pytest.mark.asyncio
    async def test_cost_reset(
        self, executor: SubagentExecutor, mock_subagent: AsyncMock
    ) -> None:
        """reset_cost_tracking clears all accumulated metrics to zero."""
        await executor.invoke(mock_subagent, {})
        summary_before = executor.get_cost_summary()
        assert summary_before.invocation_count == 1

        executor.reset_cost_tracking()
        summary_after = executor.get_cost_summary()

        assert summary_after.invocation_count == 0
        assert summary_after.total_input_tokens == 0
        assert summary_after.total_output_tokens == 0
        assert summary_after.total_cost_usd == 0.0

    @pytest.mark.asyncio
    async def test_invocation_count_incremented(
        self, executor: SubagentExecutor
    ) -> None:
        """invocation_count increments once per successful cost accumulation."""
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(
            return_value={
                "output": "test",
                "input_tokens": 1,
                "output_tokens": 1,
                "cost_usd": 0.0001,
            }
        )

        for _ in range(5):
            await executor.invoke(mock_agent, {})

        summary = executor.get_cost_summary()
        assert summary.invocation_count == 5

    @pytest.mark.asyncio
    async def test_cost_summary_returns_copy(
        self, executor: SubagentExecutor, mock_subagent: AsyncMock
    ) -> None:
        """get_cost_summary returns an independent copy; mutations don't propagate."""
        await executor.invoke(mock_subagent, {})

        summary1 = executor.get_cost_summary()
        summary1.invocation_count = 999

        summary2 = executor.get_cost_summary()
        assert summary2.invocation_count == 1

    @pytest.mark.asyncio
    async def test_initial_cost_summary_is_zero(self, executor: SubagentExecutor) -> None:
        """Fresh executor has all-zero cost summary."""
        summary = executor.get_cost_summary()

        assert summary.total_input_tokens == 0
        assert summary.total_output_tokens == 0
        assert summary.total_cost_usd == 0.0
        assert summary.invocation_count == 0

    @pytest.mark.asyncio
    async def test_cost_with_zero_values(self, executor: SubagentExecutor) -> None:
        """Zero token/cost values are handled without error."""
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(
            return_value={
                "output": "test",
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
            }
        )

        await executor.invoke(mock_agent, {})

        summary = executor.get_cost_summary()
        assert summary.total_input_tokens == 0
        assert summary.total_output_tokens == 0
        assert summary.total_cost_usd == 0.0
        assert summary.invocation_count == 1


# ─────────────────────────────────────────────────────────────────────────────
# TEST CLASS: TestConcurrency
# ─────────────────────────────────────────────────────────────────────────────


class TestConcurrency:
    """Tests for concurrent execution and thread-safe cost tracking."""

    @pytest.mark.asyncio
    async def test_concurrent_invocation_multiple_subagents(
        self, default_config: ExecutorConfig
    ) -> None:
        """Multiple subagents are invoked concurrently with correct results."""
        executor = SubagentExecutor(config=default_config)
        num_tasks = 5

        agents = []
        for idx in range(num_tasks):
            agent = AsyncMock(spec=Subagent)
            agent.execute = AsyncMock(
                return_value={
                    "output": f"result_{idx}",
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "cost_usd": 0.001,
                }
            )
            agents.append(agent)

        tasks = [
            SubagentTask(subagent=agent, input_data={"id": idx})
            for idx, agent in enumerate(agents)
        ]
        results = await executor.invoke_concurrent(tasks)

        assert len(results) == num_tasks
        for idx, result in enumerate(results):
            assert result.status == ExecutionStatus.SUCCESS
            assert result.output == f"result_{idx}"

    @pytest.mark.asyncio
    async def test_concurrent_results_match_tasks(
        self, default_config: ExecutorConfig
    ) -> None:
        """Results are returned in the same order as the input tasks."""
        executor = SubagentExecutor(config=default_config)
        num_tasks = 10

        agents = []
        for idx in range(num_tasks):
            agent = AsyncMock(spec=Subagent)
            agent.execute = AsyncMock(
                return_value={
                    "output": f"output_{idx}",
                    "input_tokens": idx,
                    "output_tokens": idx * 2,
                    "cost_usd": idx * 0.001,
                }
            )
            agents.append(agent)

        tasks = [
            SubagentTask(subagent=agent, input_data={"task_id": idx})
            for idx, agent in enumerate(agents)
        ]
        results = await executor.invoke_concurrent(tasks)

        for idx, result in enumerate(results):
            assert result.output == f"output_{idx}"
            assert result.token_usage.input_tokens == idx

    @pytest.mark.asyncio
    async def test_concurrent_cost_tracking_is_safe(
        self, default_config: ExecutorConfig
    ) -> None:
        """Concurrent cost tracking produces accurate aggregate totals."""
        executor = SubagentExecutor(config=default_config)
        num_tasks = 20

        agents = []
        for idx in range(num_tasks):
            agent = AsyncMock(spec=Subagent)
            agent.execute = AsyncMock(
                return_value={
                    "output": f"result_{idx}",
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "cost_usd": 0.001,
                }
            )
            agents.append(agent)

        tasks = [SubagentTask(subagent=agent, input_data={}) for agent in agents]
        results = await executor.invoke_concurrent(tasks)

        assert len(results) == num_tasks
        summary = executor.get_cost_summary()
        assert summary.invocation_count == num_tasks
        assert summary.total_input_tokens == 10 * num_tasks
        assert summary.total_output_tokens == 20 * num_tasks
        assert summary.total_cost_usd == pytest.approx(0.001 * num_tasks)

    @pytest.mark.asyncio
    async def test_concurrent_mixed_success_and_failure(
        self, default_config: ExecutorConfig
    ) -> None:
        """Concurrent execution handles mixed success/failure correctly."""
        executor = SubagentExecutor(config=default_config)

        agents = []
        for idx in range(5):
            agent = AsyncMock(spec=Subagent)
            if idx % 2 == 0:
                agent.execute = AsyncMock(
                    return_value={
                        "output": f"success_{idx}",
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "cost_usd": 0.0001,
                    }
                )
            else:
                agent.execute = AsyncMock(side_effect=RuntimeError("Failure"))
            agents.append(agent)

        tasks = [SubagentTask(subagent=agent, input_data={}) for agent in agents]
        results = await executor.invoke_concurrent(tasks)

        assert len(results) == 5
        assert results[0].status == ExecutionStatus.SUCCESS
        assert results[2].status == ExecutionStatus.SUCCESS
        assert results[4].status == ExecutionStatus.SUCCESS
        assert results[1].status == ExecutionStatus.FAILED
        assert results[3].status == ExecutionStatus.FAILED
        summary = executor.get_cost_summary()
        assert summary.invocation_count == 3

    @pytest.mark.asyncio
    async def test_concurrent_with_retries(self, default_config: ExecutorConfig) -> None:
        """Concurrent execution handles per-task retries correctly."""
        executor = SubagentExecutor(config=default_config)

        agents = []
        for idx in range(3):
            agent = AsyncMock(spec=Subagent)
            if idx == 0:
                agent.execute = AsyncMock(
                    return_value={
                        "output": "immediate_success",
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "cost_usd": 0.0001,
                    }
                )
            elif idx == 1:
                agent.execute = AsyncMock(
                    side_effect=[
                        RuntimeError("Fail 1"),
                        {
                            "output": "retry_success",
                            "input_tokens": 2,
                            "output_tokens": 2,
                            "cost_usd": 0.0002,
                        },
                    ]
                )
            else:
                agent.execute = AsyncMock(side_effect=RuntimeError("Permanent failure"))
            agents.append(agent)

        tasks = [SubagentTask(subagent=agent, input_data={}) for agent in agents]
        results = await executor.invoke_concurrent(tasks)

        assert results[0].status == ExecutionStatus.SUCCESS
        assert results[1].status == ExecutionStatus.SUCCESS
        assert results[2].status == ExecutionStatus.FAILED
        summary = executor.get_cost_summary()
        assert summary.invocation_count == 2

    @pytest.mark.asyncio
    async def test_concurrent_empty_task_list(self, executor: SubagentExecutor) -> None:
        """Empty task list returns empty result list."""
        results = await executor.invoke_concurrent([])

        assert results == []
        summary = executor.get_cost_summary()
        assert summary.invocation_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# TEST CLASS: TestEdgeCases
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_invoke_timeout(self) -> None:
        """Very short timeout causes failure (after retries if TimeoutError is retried)."""
        timeout_config = ExecutorConfig(
            max_retries=1,
            retry_delay=0.01,
            retry_on_exceptions=(asyncio.TimeoutError,),
            timeout=0.001,
        )
        executor = SubagentExecutor(config=timeout_config)

        mock_agent = AsyncMock(spec=Subagent)

        async def slow_execute(input_data: dict, **kwargs) -> dict:
            await asyncio.sleep(1.0)
            return {"output": "never reached"}  # pragma: no cover

        mock_agent.execute = slow_execute

        result = await executor.invoke(mock_agent, {})

        assert result.status == ExecutionStatus.FAILED

    @pytest.mark.asyncio
    async def test_executor_default_initialization(self) -> None:
        """Executor initializes with sensible defaults when no args provided."""
        executor = SubagentExecutor()

        assert executor.config is not None
        assert executor.config.max_retries == 3
        assert executor.config.timeout == 30.0
        assert executor.fallback_subagent is None

    @pytest.mark.asyncio
    async def test_config_defaults(self) -> None:
        """ExecutorConfig has expected default values."""
        config = ExecutorConfig()

        assert config.max_retries == 3
        assert config.retry_delay == 0.1
        assert config.retry_backoff_multiplier == 2.0
        assert config.timeout == 30.0

    @pytest.mark.asyncio
    async def test_invoke_with_extra_kwargs(
        self, executor: SubagentExecutor, mock_subagent: AsyncMock
    ) -> None:
        """Arbitrary kwargs are forwarded transparently to subagent."""
        await executor.invoke(
            mock_subagent, {"input": "data"}, option1="value1", option2=42, flag=True
        )

        mock_subagent.execute.assert_awaited_once_with(
            {"input": "data"}, option1="value1", option2=42, flag=True
        )

    @pytest.mark.asyncio
    async def test_large_token_values(self, executor: SubagentExecutor) -> None:
        """Large token counts are handled correctly."""
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(
            return_value={
                "output": "huge result",
                "input_tokens": 1_000_000,
                "output_tokens": 5_000_000,
                "cost_usd": 100.0,
            }
        )

        result = await executor.invoke(mock_agent, {})

        assert result.token_usage.input_tokens == 1_000_000
        assert result.token_usage.output_tokens == 5_000_000
        assert result.token_usage.cost_usd == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_floating_point_cost_precision(self, executor: SubagentExecutor) -> None:
        """Floating-point costs maintain reasonable precision over many invocations."""
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(
            return_value={
                "output": "test",
                "input_tokens": 1,
                "output_tokens": 1,
                "cost_usd": 0.000001,
            }
        )

        for _ in range(1000):
            await executor.invoke(mock_agent, {})

        summary = executor.get_cost_summary()
        assert summary.total_cost_usd == pytest.approx(0.001, rel=1e-6)

    @pytest.mark.asyncio
    async def test_result_with_complex_output_structure(
        self, executor: SubagentExecutor
    ) -> None:
        """Complex nested output structures are preserved in the result."""
        complex_output = {
            "data": [1, 2, 3],
            "nested": {"key": "value"},
            "list_of_dicts": [{"id": 1}, {"id": 2}],
        }

        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(
            return_value={
                "output": complex_output,
                "input_tokens": 1,
                "output_tokens": 1,
                "cost_usd": 0.0001,
            }
        )

        result = await executor.invoke(mock_agent, {})

        assert result.output == complex_output
        assert result.output["nested"]["key"] == "value"

    @pytest.mark.asyncio
    async def test_stream_with_high_chunk_count(
        self, executor: SubagentExecutor
    ) -> None:
        """Streaming handles many chunks efficiently."""
        num_chunks = 100
        chunks = [
            StreamChunk(
                content=f"chunk_{idx}",
                token_usage=TokenUsage(
                    input_tokens=1 if idx == 0 else 0,
                    output_tokens=1,
                    cost_usd=0.00001,
                ),
            )
            for idx in range(num_chunks)
        ]

        mock_agent = AsyncMock(spec=Subagent)

        async def mock_stream(input_data: dict, **kwargs) -> AsyncIterator[StreamChunk]:
            for chunk in chunks:
                yield chunk

        mock_agent.execute_stream = mock_stream

        received = []
        async for chunk in executor.invoke_stream(mock_agent, {}):
            received.append(chunk)

        assert len(received) == num_chunks + 1  # content chunks + final
        assert received[-1].is_final is True

    @pytest.mark.asyncio
    async def test_concurrent_with_custom_kwargs(
        self, default_config: ExecutorConfig
    ) -> None:
        """Concurrent invocation correctly passes custom kwargs per task."""
        executor = SubagentExecutor(config=default_config)

        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(
            return_value={
                "output": "result",
                "input_tokens": 1,
                "output_tokens": 1,
                "cost_usd": 0.0001,
            }
        )

        task = SubagentTask(
            subagent=mock_agent, input_data={"key": "value"}, kwargs={"param": "arg"}
        )
        results = await executor.invoke_concurrent([task])

        assert len(results) == 1
        mock_agent.execute.assert_awaited_once_with({"key": "value"}, param="arg")

    @pytest.mark.asyncio
    async def test_retry_exception_type_matching(self) -> None:
        """Exception type matching respects inheritance; unmatched types are not retried."""
        config = ExecutorConfig(
            max_retries=2,
            retry_delay=0.01,
            retry_on_exceptions=(ValueError,),
        )
        executor = SubagentExecutor(config=config)

        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(side_effect=RuntimeError("Not retried"))

        result = await executor.invoke(mock_agent, {})

        assert result.status == ExecutionStatus.FAILED
        assert mock_agent.execute.await_count == 1

    @pytest.mark.asyncio
    async def test_backoff_multiplier_produces_increasing_delays(self) -> None:
        """Backoff multiplier > 1.0 produces increasing retry delays."""
        config = ExecutorConfig(
            max_retries=3,
            retry_delay=0.01,
            retry_backoff_multiplier=2.0,
            timeout=5.0,
        )
        executor = SubagentExecutor(config=config)
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(side_effect=RuntimeError("Always fails"))

        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await executor.invoke(mock_agent, {})

        # Delays: 0.01 * 2^0 = 0.01, 0.01 * 2^1 = 0.02, 0.01 * 2^2 = 0.04
        assert mock_sleep.await_count == 3
        calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert calls[0] == pytest.approx(0.01)
        assert calls[1] == pytest.approx(0.02)
        assert calls[2] == pytest.approx(0.04)

    @pytest.mark.asyncio
    async def test_fallback_receives_kwargs(
        self, default_config: ExecutorConfig, mock_fallback_subagent: AsyncMock
    ) -> None:
        """Fallback subagent receives the same kwargs as the primary."""
        executor = SubagentExecutor(
            config=default_config, fallback_subagent=mock_fallback_subagent
        )
        mock_primary = AsyncMock(spec=Subagent)
        mock_primary.execute = AsyncMock(side_effect=RuntimeError("Primary error"))

        await executor.invoke(mock_primary, {"key": "val"}, temperature=0.5)

        mock_fallback_subagent.execute.assert_awaited_once_with(
            {"key": "val"}, temperature=0.5
        )

    @pytest.mark.asyncio
    async def test_single_concurrent_task(self, executor: SubagentExecutor) -> None:
        """Single-task concurrent invocation works correctly."""
        mock_agent = AsyncMock(spec=Subagent)
        mock_agent.execute = AsyncMock(
            return_value={
                "output": "solo",
                "input_tokens": 1,
                "output_tokens": 1,
                "cost_usd": 0.0001,
            }
        )

        tasks = [SubagentTask(subagent=mock_agent, input_data={})]
        results = await executor.invoke_concurrent(tasks)

        assert len(results) == 1
        assert results[0].status == ExecutionStatus.SUCCESS
        assert results[0].output == "solo"

    @pytest.mark.asyncio
    async def test_cost_reset_then_new_invocation(
        self, executor: SubagentExecutor, mock_subagent: AsyncMock
    ) -> None:
        """After reset, new invocations accumulate from zero."""
        await executor.invoke(mock_subagent, {})
        executor.reset_cost_tracking()
        await executor.invoke(mock_subagent, {})

        summary = executor.get_cost_summary()
        assert summary.invocation_count == 1
        assert summary.total_input_tokens == 10