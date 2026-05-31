"""
PhaseRunner: A reusable abstraction for orchestrating sequential phase execution
with retry logic, cost tracking, budget enforcement, and OpenTelemetry tracing.

This module implements the draft -> validate -> gate pattern with full observability.
All types, enums, exceptions, and the runner are defined here with no relative imports.

Usage::

    from phase_runner import (
        PhaseRunner, PhaseConfig, PhaseOutput,
        PhaseType, RetryPolicy,
    )

    class DraftPhase:
        @property
        def phase_type(self) -> PhaseType:
            return PhaseType.DRAFT

        def execute(self, context: dict[str, Any]) -> PhaseOutput:
            result = call_llm(context["prompt"])
            context["draft"] = result
            return PhaseOutput(data=result, cost=0.03)

    runner = PhaseRunner(
        phases=[
            PhaseConfig(DraftPhase(), RetryPolicy(max_attempts=6)),
            PhaseConfig(ValidatePhase(), RetryPolicy(max_attempts=6)),
            PhaseConfig(GatePhase()),
        ],
        budget=1.00,
    )
    result = runner.run({"prompt": "Write a haiku"})
    assert result.success
"""

from __future__ import annotations

import enum
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, Sequence, Type, runtime_checkable

from startd8.logging_config import get_logger

# Observability manifest descriptor — consumed by generate_manifest(), zero runtime cost.
# Project Observability (REQ-OBS-SHARED-001): development-lifecycle phase/task spans.
_OTEL_DESCRIPTORS = {
    "category": "project_observability",
    "orientation": "system",
    "spans": [
        {
            "name_pattern": "PhaseRunner.run",
            "kind": "INTERNAL",
            "attributes": ["phase.count", "phase.total_cost"],
            "events": [],
        },
        {
            "name_pattern": "phase.{phase_type}.attempt.{attempt_number}",
            "kind": "INTERNAL",
            "attributes": ["phase.type", "attempt.number", "attempt.status"],
            "events": [],
        },
    ],
}

try:
    from opentelemetry import trace
    from opentelemetry.trace import StatusCode, Tracer

    HAS_OTEL = True
except ImportError:  # pragma: no cover
    HAS_OTEL = False
    trace = None  # type: ignore[assignment]
    Tracer = None  # type: ignore[assignment,misc]

    class StatusCode:  # type: ignore[no-redef]
        """Minimal stand-in when OTel is not installed."""
        OK = "OK"
        ERROR = "ERROR"

__all__ = [
    "PhaseType",
    "PhaseStatus",
    "PhaseRunnerError",
    "BudgetExceededError",
    "GateRejectionError",
    "PhaseExecutionError",
    "RetryPolicy",
    "PhaseOutput",
    "PhaseConfig",
    "PhaseResult",
    "RunResult",
    "Phase",
    "PhaseRunner",
]

logger = get_logger(__name__)


class _NoOpSpan:
    """Minimal no-op span for when OTel is not installed."""

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, *args: Any, **kwargs: Any) -> None:
        pass

    def record_exception(self, exception: Exception) -> None:
        pass


class _NoOpTracer:
    """Minimal no-op tracer for when OTel is not installed."""

    def start_as_current_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()


# ============================================================================
# Enums
# ============================================================================


class PhaseType(enum.Enum):
    """Enum of phase types in the draft->validate->gate pipeline."""

    DRAFT = "draft"
    VALIDATE = "validate"
    GATE = "gate"


class PhaseStatus(enum.Enum):
    """Status of a phase execution result."""

    SUCCESS = "success"
    FAILED = "failed"
    BUDGET_EXCEEDED = "budget_exceeded"
    SKIPPED = "skipped"


# ============================================================================
# Exceptions
# ============================================================================


class PhaseRunnerError(Exception):
    """Base exception for PhaseRunner errors."""


class BudgetExceededError(PhaseRunnerError):
    """Raised when accumulated cost exceeds the configured budget."""

    def __init__(self, budget: float, total_cost: float, phase_type: PhaseType) -> None:
        self.budget = budget
        self.total_cost = total_cost
        self.phase_type = phase_type
        super().__init__(
            f"Budget exceeded: {total_cost:.4f} >= {budget:.4f} "
            f"before executing phase '{phase_type.value}'"
        )


class GateRejectionError(PhaseRunnerError):
    """Raised when a gate phase explicitly rejects the output."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Gate rejected: {reason}")


class PhaseExecutionError(PhaseRunnerError):
    """Wraps an error that occurred during phase execution."""

    def __init__(
        self, phase_type: PhaseType, original_error: Exception, attempt: int
    ) -> None:
        self.phase_type = phase_type
        self.original_error = original_error
        self.attempt = attempt
        super().__init__(
            f"Phase '{phase_type.value}' failed on attempt {attempt}: {original_error}"
        )


# ============================================================================
# Data Classes
# ============================================================================


@dataclass(frozen=True)
class RetryPolicy:
    """Retry configuration for a single phase.

    Attributes:
        max_attempts: Maximum number of attempts (1 = no retry, just initial attempt).
        base_delay: Base delay in seconds for exponential backoff.
        max_delay: Maximum delay cap in seconds for exponential backoff.
        jitter: Maximum random jitter in seconds added to the backoff delay.
        retryable_exceptions: Tuple of exception types that should trigger a retry.
        retry_on_gate_rejection: If True, ``GateRejectionError`` also triggers retries.
    """

    max_attempts: int = 1
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: float = 0.5
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,)
    retry_on_gate_rejection: bool = False

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay < 0:
            raise ValueError("base_delay must be >= 0")
        if self.max_delay < 0:
            raise ValueError("max_delay must be >= 0")
        if self.jitter < 0:
            raise ValueError("jitter must be >= 0")


@dataclass
class PhaseOutput:
    """Return type from ``Phase.execute()``.

    Attributes:
        data: Arbitrary output data from the phase.
        cost: Cost incurred by this single execution (e.g. API call cost in USD).
        metadata: Optional metadata about the execution.
    """

    data: Any = None
    cost: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PhaseConfig:
    """Binds a :class:`Phase` instance to its :class:`RetryPolicy`.

    Attributes:
        phase: The phase instance to execute.
        retry_policy: Retry policy for this phase.
    """

    phase: Phase
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)


@dataclass
class PhaseResult:
    """Result of a single phase execution (including all retry attempts).

    Attributes:
        phase_type: The type of phase that was executed.
        status: Final status of the phase.
        attempts: Total number of attempts made.
        cost: Total cost across all attempts of this phase.
        duration_seconds: Wall-clock time for all attempts of this phase.
        output: Output data from the phase (if successful).
        error: Final error if phase failed.
        attempt_details: Per-attempt diagnostic information.
    """

    phase_type: PhaseType
    status: PhaseStatus
    attempts: int
    cost: float
    duration_seconds: float
    output: Any = None
    error: Optional[Exception] = None
    attempt_details: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RunResult:
    """Result of the entire draft->validate->gate pipeline run.

    Attributes:
        success: Whether the entire pipeline succeeded.
        phase_results: Results from each phase.
        total_cost: Total cost across all phases and attempts.
        total_duration_seconds: Total wall-clock time for the entire run.
        error: Top-level error that halted execution (if any).
        context: Final context state after execution.
    """

    success: bool
    phase_results: list[PhaseResult]
    total_cost: float
    total_duration_seconds: float
    error: Optional[Exception] = None
    context: dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Protocol
# ============================================================================


@runtime_checkable
class Phase(Protocol):
    """Protocol that all phases must satisfy.

    Any object with a ``phase_type`` property and an ``execute`` method
    matching the signatures below can be used with :class:`PhaseRunner`.
    """

    @property
    def phase_type(self) -> PhaseType:
        """Return the type of this phase."""
        ...

    def execute(self, context: dict[str, Any]) -> PhaseOutput:
        """Execute the phase logic.

        Args:
            context: Mutable shared context dict. Read inputs and write outputs here.

        Returns:
            PhaseOutput with the result data and cost.

        Raises:
            GateRejectionError: If this is a gate phase and the gate rejects.
            Exception: Any exception will be caught by the runner for retry handling.
        """
        ...


# ============================================================================
# PhaseRunner
# ============================================================================


class PhaseRunner:
    """Orchestrates execution of a sequence of phases following the
    draft → validate → gate pattern with retry, cost tracking,
    budget enforcement, and OpenTelemetry tracing.

    Example::

        runner = PhaseRunner(
            phases=[
                PhaseConfig(DraftPhase(), RetryPolicy(max_attempts=6)),
                PhaseConfig(ValidatePhase(), RetryPolicy(max_attempts=6)),
                PhaseConfig(GatePhase()),
            ],
            budget=0.50,
        )
        result = runner.run({"prompt": "Summarize ..."})
        if result.success:
            print(result.context["final_output"])
    """

    def __init__(
        self,
        phases: Sequence[PhaseConfig],
        budget: float = float("inf"),
        tracer: Optional[Any] = None,
        logger_instance: Optional[logging.Logger] = None,
    ) -> None:
        """Initialize the PhaseRunner.

        Args:
            phases: Sequence of :class:`PhaseConfig` instances defining the pipeline.
            budget: Maximum cumulative cost allowed. Defaults to infinity (no limit).
            tracer: OpenTelemetry Tracer instance.
                If ``None``, acquires the default tracer.
            logger_instance: Logger instance. If ``None``, uses the module-level logger.

        Raises:
            ValueError: If *phases* is empty or *budget* is negative.
            TypeError: If any phase does not satisfy the :class:`Phase` protocol.
        """
        if not phases:
            raise ValueError("At least one phase must be provided")
        if budget < 0:
            raise ValueError("budget must be >= 0")

        self._phases = list(phases)
        self._budget = budget
        if tracer is not None:
            self._tracer = tracer
        elif HAS_OTEL:
            self._tracer = trace.get_tracer("startd8.phase_runner")
        else:
            self._tracer = _NoOpTracer()
        self._logger = logger_instance or logger
        self._total_cost: float = 0.0

        for pc in self._phases:
            if not isinstance(pc.phase, Phase):
                raise TypeError(
                    f"Phase {pc.phase!r} does not satisfy the Phase protocol"
                )

    # -- Public API ----------------------------------------------------------

    def run(self, context: Optional[dict[str, Any]] = None) -> RunResult:
        """Execute all phases in sequence.

        Creates a root OTel span ``PhaseRunner.run`` with child spans for each
        phase attempt.  Halts on the first non-retryable failure or budget
        exhaustion.

        Args:
            context: Initial context dict.  If ``None``, an empty dict is created.

        Returns:
            :class:`RunResult` containing all phase results, costs, timing, and
            the final context state.
        """
        context = context if context is not None else {}
        self._total_cost = 0.0
        phase_results: list[PhaseResult] = []
        overall_error: Optional[Exception] = None
        run_start = time.monotonic()

        with self._tracer.start_as_current_span("PhaseRunner.run") as root_span:
            root_span.set_attribute("runner.budget", self._budget)
            root_span.set_attribute("runner.phase_count", len(self._phases))

            try:
                for phase_config in self._phases:
                    phase_type = phase_config.phase.phase_type
                    self._logger.info("Starting phase: %s", phase_type.value)

                    # Pre-phase budget gate
                    self._check_budget(phase_type)

                    result = self._execute_with_retry(phase_config, context)
                    phase_results.append(result)

                    self._logger.info(
                        "Phase %s completed: status=%s, cost=%.4f, attempts=%d",
                        phase_type.value,
                        result.status.value,
                        result.cost,
                        result.attempts,
                    )

                    if result.status == PhaseStatus.FAILED:
                        overall_error = result.error
                        root_span.set_status(StatusCode.ERROR, str(result.error))
                        root_span.record_exception(result.error)
                        break

            except BudgetExceededError as exc:
                overall_error = exc
                self._logger.error("Budget exceeded: %s", exc)
                root_span.set_status(StatusCode.ERROR, str(exc))
                root_span.record_exception(exc)
                phase_results.append(
                    PhaseResult(
                        phase_type=exc.phase_type,
                        status=PhaseStatus.BUDGET_EXCEEDED,
                        attempts=0,
                        cost=0.0,
                        duration_seconds=0.0,
                        error=exc,
                    )
                )

            run_duration = time.monotonic() - run_start
            success = overall_error is None

            root_span.set_attribute("runner.total_cost", self._total_cost)
            root_span.set_attribute("runner.total_duration_seconds", run_duration)
            root_span.set_attribute("runner.success", success)

            if success:
                root_span.set_status(StatusCode.OK)

        return RunResult(
            success=success,
            phase_results=phase_results,
            total_cost=self._total_cost,
            total_duration_seconds=run_duration,
            error=overall_error,
            context=context,
        )

    # -- Internal helpers ----------------------------------------------------

    def _execute_with_retry(
        self,
        phase_config: PhaseConfig,
        context: dict[str, Any],
    ) -> PhaseResult:
        """Execute a single phase with retry logic and per-attempt OTel spans.

        Updates ``self._total_cost`` as each attempt completes.

        Returns:
            :class:`PhaseResult` with final status, cost, duration, and
            per-attempt details.
        """
        phase = phase_config.phase
        policy = phase_config.retry_policy
        phase_type = phase.phase_type

        phase_cost = 0.0
        attempt_details: list[dict[str, Any]] = []
        last_error: Optional[Exception] = None
        phase_start = time.monotonic()

        for attempt in range(1, policy.max_attempts + 1):
            # Budget check before each attempt (including retries)
            self._check_budget(phase_type)

            attempt_start = time.monotonic()
            attempt_cost = 0.0
            attempt_success = False
            attempt_error: Optional[Exception] = None
            attempt_output: Optional[PhaseOutput] = None

            span_name = f"phase.{phase_type.value}.attempt.{attempt}"
            with self._tracer.start_as_current_span(span_name) as attempt_span:
                attempt_span.set_attribute("phase.type", phase_type.value)
                attempt_span.set_attribute("phase.attempt", attempt)
                attempt_span.set_attribute("phase.max_attempts", policy.max_attempts)

                try:
                    self._logger.debug(
                        "Phase %s: attempt %d/%d",
                        phase_type.value,
                        attempt,
                        policy.max_attempts,
                    )
                    output = phase.execute(context)
                    attempt_cost = output.cost
                    attempt_output = output
                    attempt_success = True
                    attempt_span.set_status(StatusCode.OK)
                    attempt_span.set_attribute("phase.cost", attempt_cost)

                except Exception as exc:
                    attempt_error = exc
                    attempt_span.set_status(StatusCode.ERROR, str(exc))
                    attempt_span.record_exception(exc)

            attempt_duration = time.monotonic() - attempt_start

            # Accumulate costs
            phase_cost += attempt_cost
            self._total_cost += attempt_cost

            attempt_details.append(
                {
                    "attempt": attempt,
                    "cost": attempt_cost,
                    "duration_seconds": attempt_duration,
                    "success": attempt_success,
                    "error": str(attempt_error) if attempt_error else None,
                }
            )

            # --- Success path ---
            if attempt_success:
                return PhaseResult(
                    phase_type=phase_type,
                    status=PhaseStatus.SUCCESS,
                    attempts=attempt,
                    cost=phase_cost,
                    duration_seconds=time.monotonic() - phase_start,
                    output=attempt_output.data if attempt_output else None,
                    attempt_details=attempt_details,
                )

            # --- Failure path ---
            last_error = attempt_error
            is_retryable = self._is_retryable(attempt_error, policy)

            if not is_retryable or attempt >= policy.max_attempts:
                return PhaseResult(
                    phase_type=phase_type,
                    status=PhaseStatus.FAILED,
                    attempts=attempt,
                    cost=phase_cost,
                    duration_seconds=time.monotonic() - phase_start,
                    error=attempt_error,
                    attempt_details=attempt_details,
                )

            # Retryable – backoff and retry
            delay = self._calculate_delay(attempt - 1, policy)
            self._logger.warning(
                "Phase %s: attempt %d failed, retrying in %.2fs. Error: %s",
                phase_type.value,
                attempt,
                delay,
                attempt_error,
            )
            time.sleep(delay)

        # Defensive fallback (should be unreachable)
        return PhaseResult(  # pragma: no cover
            phase_type=phase_type,
            status=PhaseStatus.FAILED,
            attempts=policy.max_attempts,
            cost=phase_cost,
            duration_seconds=time.monotonic() - phase_start,
            error=last_error,
            attempt_details=attempt_details,
        )

    def _check_budget(self, phase_type: PhaseType) -> None:
        """Raise :class:`BudgetExceededError` if the accumulated cost meets or
        exceeds the configured budget."""
        if self._total_cost >= self._budget:
            raise BudgetExceededError(
                budget=self._budget,
                total_cost=self._total_cost,
                phase_type=phase_type,
            )

    @staticmethod
    def _calculate_delay(retry_index: int, policy: RetryPolicy) -> float:
        """Calculate exponential backoff delay with jitter.

        Formula: ``min(base_delay * 2^retry_index + uniform(0, jitter), max_delay)``

        Args:
            retry_index: Zero-based retry index (0 for the first retry).
            policy: :class:`RetryPolicy` with delay configuration.

        Returns:
            Delay in seconds.
        """
        delay = policy.base_delay * (2**retry_index)
        delay += random.uniform(0, policy.jitter)  # noqa: S311 – non-crypto jitter
        return min(delay, policy.max_delay)

    @staticmethod
    def _is_retryable(error: Optional[Exception], policy: RetryPolicy) -> bool:
        """Determine whether *error* is retryable under the given *policy*."""
        if error is None:
            return False
        if isinstance(error, GateRejectionError):
            return policy.retry_on_gate_rejection
        return isinstance(error, policy.retryable_exceptions)
