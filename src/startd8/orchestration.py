"""
Orchestration module for sequential LLM workflows

Combines benchmarking capabilities with LangChain-style pipelines
for multi-step agent workflows with full metrics tracking.
"""

import time
import asyncio
import random
import uuid
from typing import List, Dict, Any, Optional, Callable, Union
from datetime import datetime, timezone
from dataclasses import dataclass, field

from .models import TokenUsage, AgentResponse, ResponseMetadata
from .agents import BaseAgent
from .events import EventBus, EventType, Event
from .exceptions import AgentError, APIError, ConfigurationError

# Graceful OTel import — no-op when not installed (FR-403)
try:
    from opentelemetry import trace as _otel_trace
    _tracer = _otel_trace.get_tracer("startd8.orchestration")
except ImportError:
    _otel_trace = None  # type: ignore[assignment]
    _tracer = None

# Observability manifest descriptor — consumed by generate_manifest(), zero runtime cost.
# Pipeline-innate (REQ-OBS-SHARED-001): pipeline orchestration telemetry.
_OTEL_DESCRIPTORS = {
    "category": "pipeline_innate",
    "orientation": "system",
    "spans": [
        {
            "name_pattern": "pipeline.{name}",
            "kind": "INTERNAL",
            "attributes": [
                "pipeline.name",
                "pipeline.id",
                "step.count",
                "pipeline.total_tokens",
                "pipeline.total_cost",
                "pipeline.total_time_ms",
            ],
            "events": [],
        },
        {
            "name_pattern": "pipeline.{name}.step.{step_name}",
            "kind": "INTERNAL",
            "attributes": [
                "step.name",
                "step.index",
                "agent.name",
                "agent.model",
                "tokens",
                "cost",
                "response_time_ms",
                "retry_count",
            ],
            "events": [],
        },
    ],
}

try:
    from contextlib import nullcontext as _nullcontext
except ImportError:
    from contextlib import contextmanager as _cm

    @_cm
    def _nullcontext(enter_result=None):
        yield enter_result


@dataclass
class PipelineStep:
    """A single step in a pipeline"""
    name: str
    agent: BaseAgent
    transform: Optional[Callable[[str], str]] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ConditionalStep:
    """A pipeline step that branches based on a predicate (FR-311)."""
    name: str
    predicate: Callable[[str], bool]   # Receives previous step output
    if_step: PipelineStep              # Run if predicate returns True
    else_step: Optional[PipelineStep] = None  # Run if predicate returns False
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ParallelStep:
    """A pipeline step that runs multiple steps concurrently (FR-320)."""
    name: str
    steps: List[PipelineStep] = field(default_factory=list)
    aggregator: Optional[Callable[[List[str]], str]] = None  # Default: join
    failure_policy: str = "collect_all"  # "fail_fast" | "collect_all"
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.aggregator is None:
            self.aggregator = lambda outputs: "\n---\n".join(outputs)


@dataclass
class WorkflowStep:
    """A pipeline step that delegates to a sub-workflow (FR-330)."""
    name: str
    workflow: Any  # WorkflowBase instance (forward ref to avoid circular import)
    config_mapping: Callable[[str], Dict[str, Any]]  # Transform output to config
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


# Type alias for all step types (FR-310)
StepType = Union[PipelineStep, ConditionalStep, ParallelStep, WorkflowStep]


def is_retryable(exc: Exception, retryable_codes: List[int]) -> bool:
    """Classify exception as retryable or fatal (FR-301).

    Retryable: ConnectionError, TimeoutError, HTTP 429/5xx.
    Fatal: ValidationError, ConfigurationError, HTTP 400/401/403.
    """
    if isinstance(exc, (ConnectionError, TimeoutError, asyncio.TimeoutError)):
        return True
    # Check httpx status errors
    try:
        import httpx
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in retryable_codes
    except ImportError:
        pass
    # Check for status_code attribute on other exception types
    status_code = getattr(exc, 'status_code', None)
    if status_code is not None and isinstance(status_code, int):
        return status_code in retryable_codes
    # ConfigurationError and validation errors are never retryable
    if isinstance(exc, ConfigurationError):
        return False
    return False


@dataclass
class PipelineResult:
    """Result from running a pipeline"""
    steps: List[Dict[str, Any]]
    final_output: str
    total_time_ms: int
    total_tokens: int
    total_cost: float
    pipeline_id: str
    timestamp: datetime


class Pipeline:
    """
    Sequential agent pipeline with metrics tracking
    
    Inspired by LangChain's sequential chains but with full
    benchmarking and metrics support from startd8.
    
    Example:
        ```python
        pipeline = Pipeline(name="design-implement")
        
        # Add steps
        pipeline.add_step(
            name="planner",
            agent=ClaudeAgent(),
            transform=None
        )
        
        pipeline.add_step(
            name="implementer",
            agent=GPT4Agent(),
            transform=lambda spec: f"Implement this design:\\n\\n{spec}"
        )
        
        # Run with tracking
        result = pipeline.run("Design a new feature")
        print(f"Total cost: ${result.total_cost:.4f}")
        print(f"Total time: {result.total_time_ms}ms")
        ```
    """
    
    def __init__(self, name: str = "pipeline", framework=None):
        """
        Initialize pipeline
        
        Args:
            name: Pipeline name
            framework: Optional AgentFramework for storage
        """
        self.name = name
        self.framework = framework
        self.steps: List[StepType] = []

    def add_step(
        self,
        name: str,
        agent: BaseAgent,
        transform: Optional[Callable[[str], str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> 'Pipeline':
        """
        Add a sequential step to the pipeline.

        Args:
            name: Step name (e.g., "planner", "implementer")
            agent: Agent to use for this step
            transform: Optional function to transform input before sending to agent
            metadata: Optional step metadata

        Returns:
            Self for chaining
        """
        step = PipelineStep(
            name=name,
            agent=agent,
            transform=transform,
            metadata=metadata or {}
        )
        self.steps.append(step)
        return self

    def add_conditional(
        self,
        name: str,
        predicate: Callable[[str], bool],
        if_agent: BaseAgent,
        else_agent: Optional[BaseAgent] = None,
        if_transform: Optional[Callable[[str], str]] = None,
        else_transform: Optional[Callable[[str], str]] = None,
    ) -> 'Pipeline':
        """Add a conditional branching step (FR-312).

        Args:
            name: Step name
            predicate: Function receiving previous output, returns True/False
            if_agent: Agent for the True branch
            else_agent: Optional agent for the False branch (skip if None)
            if_transform: Optional transform for True branch input
            else_transform: Optional transform for False branch input

        Returns:
            Self for chaining
        """
        if_step = PipelineStep(name=f"{name}_if", agent=if_agent, transform=if_transform)
        else_step = (
            PipelineStep(name=f"{name}_else", agent=else_agent, transform=else_transform)
            if else_agent else None
        )
        self.steps.append(ConditionalStep(
            name=name, predicate=predicate, if_step=if_step, else_step=else_step
        ))
        return self

    def add_parallel(
        self,
        name: str,
        steps: List[PipelineStep],
        aggregator: Optional[Callable[[List[str]], str]] = None,
        failure_policy: str = "collect_all",
    ) -> 'Pipeline':
        """Add a parallel execution step (FR-321).

        Args:
            name: Step name
            steps: List of PipelineSteps to run concurrently
            aggregator: Function to combine outputs (default: join with separator)
            failure_policy: "fail_fast" or "collect_all"

        Returns:
            Self for chaining
        """
        self.steps.append(ParallelStep(
            name=name, steps=steps, aggregator=aggregator,
            failure_policy=failure_policy,
        ))
        return self

    def add_workflow(
        self,
        name: str,
        workflow: Any,
        config_mapping: Callable[[str], Dict[str, Any]],
    ) -> 'Pipeline':
        """Add a sub-workflow step (FR-331).

        Args:
            name: Step name
            workflow: WorkflowBase instance to delegate to
            config_mapping: Transform previous output to sub-workflow config dict

        Returns:
            Self for chaining
        """
        self.steps.append(WorkflowStep(
            name=name, workflow=workflow, config_mapping=config_mapping
        ))
        return self
    
    async def arun(
        self,
        initial_input: str,
        store: bool = True,
        retry_policy: Optional[Any] = None,
    ) -> PipelineResult:
        """
        Run the pipeline asynchronously with isinstance dispatch (FR-310)
        and optional retry support (FR-300).

        Args:
            initial_input: Initial input to first agent
            store: Whether to store results in framework (if available)
            retry_policy: Optional RetryPolicy for transient error recovery

        Returns:
            PipelineResult with all step details
        """
        pipeline_id = f"pipeline-{uuid.uuid4().hex[:12]}"
        start_time = time.time()

        # Emit pipeline start event
        EventBus.emit(Event(
            type=EventType.PIPELINE_START,
            source="Pipeline",
            data={
                "pipeline_id": pipeline_id,
                "pipeline_name": self.name,
                "steps": [getattr(s, 'name', str(s)) for s in self.steps]
            },
            correlation_id=pipeline_id
        ))

        current_input = initial_input
        step_results = []
        total_tokens = 0
        total_cost = 0.0
        total_retries = 0

        # Create a prompt if framework available
        if self.framework and store:
            prompt = self.framework.create_prompt(
                content=initial_input,
                version="1.0.0",
                tags=[self.name, "pipeline"],
                metadata={
                    "pipeline_id": pipeline_id,
                    "pipeline_name": self.name,
                    "steps": [getattr(s, 'name', str(s)) for s in self.steps]
                }
            )
            prompt_id = prompt.id
        else:
            prompt_id = None

        tracking_prompt_id = prompt_id or f"prompt-{uuid.uuid4().hex[:12]}"
        completed_steps: List[int] = []  # FR-302: checkpoint tracking

        # OTel parent span wrapping entire pipeline (child step spans nest under this)
        _span_ctx = (
            _tracer.start_as_current_span(
                f"pipeline.{self.name}",
                attributes={
                    "pipeline.name": self.name,
                    "pipeline.id": pipeline_id,
                    "step.count": len(self.steps),
                },
            )
            if _tracer
            else _nullcontext()
        )

        with _span_ctx as pipeline_span:
            try:
                # Execute each step — dispatch by type (FR-310)
                for i, step in enumerate(self.steps):
                    if isinstance(step, PipelineStep):
                        output, step_data, tokens, cost, retries = await self._execute_sequential_step(
                            step, i, current_input, pipeline_id, tracking_prompt_id,
                            prompt_id, store, retry_policy,
                        )
                    elif isinstance(step, ConditionalStep):
                        output, step_data, tokens, cost, retries = await self._execute_conditional_step(
                            step, i, current_input, pipeline_id, tracking_prompt_id,
                            prompt_id, store, retry_policy,
                        )
                    elif isinstance(step, ParallelStep):
                        output, step_data, tokens, cost, retries = await self._execute_parallel_step(
                            step, i, current_input, pipeline_id, tracking_prompt_id,
                            prompt_id, store, retry_policy,
                        )
                    elif isinstance(step, WorkflowStep):
                        output, step_data, tokens, cost, retries = await self._execute_workflow_step(
                            step, i, current_input, pipeline_id,
                        )
                    else:
                        raise TypeError(f"Unknown step type: {type(step)}")

                    current_input = output
                    step_results.extend(step_data if isinstance(step_data, list) else [step_data])
                    total_tokens += tokens
                    total_cost += cost
                    total_retries += retries
                    completed_steps.append(i)

                end_time = time.time()
                total_time_ms = int((end_time - start_time) * 1000)

                if pipeline_span:
                    pipeline_span.set_attribute("pipeline.total_tokens", total_tokens)
                    pipeline_span.set_attribute("pipeline.total_cost", total_cost)
                    pipeline_span.set_attribute("pipeline.total_time_ms", total_time_ms)

                result = PipelineResult(
                    steps=step_results,
                    final_output=current_input,
                    total_time_ms=total_time_ms,
                    total_tokens=total_tokens,
                    total_cost=total_cost,
                    pipeline_id=pipeline_id,
                    timestamp=datetime.now(timezone.utc)
                )

                EventBus.emit(Event(
                    type=EventType.PIPELINE_COMPLETE,
                    source="Pipeline",
                    data={
                        "pipeline_id": pipeline_id,
                        "total_time_ms": total_time_ms,
                        "total_tokens": total_tokens,
                        "total_cost": total_cost,
                        "total_retries": total_retries,
                    },
                    correlation_id=pipeline_id
                ))

                return result

            except (AgentError, APIError, ConfigurationError) as e:
                if pipeline_span and _otel_trace:
                    pipeline_span.set_status(_otel_trace.StatusCode.ERROR, str(e))
                    pipeline_span.record_exception(e)
                from .logging_config import get_logger
                logger = get_logger(__name__)
                logger.error(
                    f"Pipeline '{self.name}' failed: {e}",
                    exc_info=True,
                    extra={
                        "pipeline_id": pipeline_id,
                        "pipeline_name": self.name,
                        "error_type": type(e).__name__,
                        "pipeline_error": str(e)
                    }
                )
                raise
            except Exception as e:
                if pipeline_span and _otel_trace:
                    pipeline_span.set_status(_otel_trace.StatusCode.ERROR, str(e))
                    pipeline_span.record_exception(e)
                from .logging_config import get_logger
                logger = get_logger(__name__)
                logger.error(
                    f"Unexpected error in pipeline '{self.name}': {e}",
                    exc_info=True,
                    extra={
                        "pipeline_id": pipeline_id,
                        "pipeline_name": self.name,
                        "error_type": type(e).__name__,
                        "steps": [getattr(s, 'name', str(s)) for s in self.steps]
                    }
                )
                EventBus.emit(Event(
                    type=EventType.PIPELINE_ERROR,
                    source="Pipeline",
                    data={
                        "pipeline_id": pipeline_id,
                        "error": str(e),
                        "error_type": type(e).__name__
                    },
                    correlation_id=pipeline_id
                ))
                raise AgentError(
                    f"Unexpected error in pipeline '{self.name}': {e}",
                    agent_name=getattr(e, 'agent_name', None),
                    original_error=e
                ) from e

    # =========================================================================
    # Private step execution methods (FR-310 extract-method refactoring)
    # =========================================================================

    async def _execute_sequential_step(
        self, step: PipelineStep, step_index: int, current_input: str,
        pipeline_id: str, tracking_prompt_id: str,
        prompt_id: Optional[str], store: bool,
        retry_policy: Optional[Any],
    ) -> tuple:
        """Execute a single sequential PipelineStep with optional retry (FR-300).

        Returns:
            (output_text, step_result_dict, tokens, cost, retry_count)
        """
        EventBus.emit(Event(
            type=EventType.PIPELINE_STEP_START,
            source="Pipeline",
            data={
                "pipeline_id": pipeline_id,
                "step_number": step_index + 1,
                "step_name": step.name,
                "agent": step.agent.name
            },
            correlation_id=pipeline_id
        ))

        step_input = step.transform(current_input) if step.transform else current_input

        valid_metadata_fields = set(ResponseMetadata.__annotations__.keys())
        step_metadata: ResponseMetadata = {
            "pipeline_id": pipeline_id,
            "step_number": step_index + 1,
            "agent_name": step.agent.name,
            "model": step.agent.model,
            **{k: v for k, v in step.metadata.items() if k in valid_metadata_fields}
        }

        # OTel child span using start_as_current_span for proper nesting (FR-401)
        _step_span_ctx = (
            _tracer.start_as_current_span(
                f"pipeline.{self.name}.step.{step.name}",
                attributes={
                    "step.name": step.name,
                    "step.index": step_index,
                    "agent.name": step.agent.name,
                    "agent.model": step.agent.model,
                },
            )
            if _tracer
            else _nullcontext()
        )

        with _step_span_ctx as step_span:
            try:
                # Retry loop (FR-300)
                max_attempts = 1 + (retry_policy.max_retries if retry_policy else 0)
                retry_count = 0
                last_error = None

                for attempt in range(max_attempts):
                    try:
                        agent_response = await step.agent.acreate_response(
                            prompt_id=tracking_prompt_id,
                            prompt=step_input,
                            metadata=step_metadata,
                            tags=[self.name, "pipeline", step.name],
                            pipeline_id=pipeline_id
                        )
                        break
                    except Exception as e:
                        if not retry_policy or not is_retryable(
                            e, retry_policy.retryable_status_codes
                        ):
                            raise
                        last_error = e
                        retry_count = attempt + 1
                        delay = min(
                            retry_policy.backoff_base * (2 ** attempt),
                            retry_policy.backoff_max
                        )
                        if retry_policy.jitter:
                            delay += random.uniform(0, delay * 0.1)

                        # Emit retry event (FR-410)
                        EventBus.emit(Event(
                            type=EventType.PIPELINE_STEP_RETRY,
                            source="Pipeline",
                            data={
                                "step_name": step.name,
                                "attempt_number": retry_count,
                                "error": str(e),
                                "delay_seconds": delay,
                            },
                            correlation_id=pipeline_id
                        ))
                        await asyncio.sleep(delay)
                else:
                    raise last_error  # type: ignore[misc]

                response_text = agent_response.response
                response_time_ms = agent_response.response_time_ms
                token_usage = agent_response.token_usage

                tokens = token_usage.total if token_usage else 0
                cost = token_usage.cost_estimate if token_usage else 0

                # Set span metrics (FR-401)
                if step_span:
                    step_span.set_attribute("tokens", tokens)
                    step_span.set_attribute("cost", cost)
                    step_span.set_attribute("response_time_ms", response_time_ms)
                    step_span.set_attribute("retry_count", retry_count)

                step_result = {
                    "step_number": step_index + 1,
                    "step_name": step.name,
                    "agent": step.agent.name,
                    "model": step.agent.model,
                    "input": step_input[:200] + "..." if len(step_input) > 200 else step_input,
                    "output": response_text,
                    "response_time_ms": response_time_ms,
                    "tokens": tokens,
                    "cost": cost,
                    "metadata": {**step.metadata, "retry_count": retry_count},
                }
            except Exception as e:
                if step_span and _otel_trace:
                    step_span.set_status(_otel_trace.StatusCode.ERROR, str(e))
                    step_span.record_exception(e)
                raise

        EventBus.emit(Event(
            type=EventType.PIPELINE_STEP_COMPLETE,
            source="Pipeline",
            data={
                "pipeline_id": pipeline_id,
                "step_number": step_index + 1,
                "step_name": step.name,
                "response_time_ms": response_time_ms,
                "tokens": tokens,
            },
            correlation_id=pipeline_id
        ))

        if self.framework and store and prompt_id:
            self.framework.record_response(
                prompt_id=prompt_id,
                agent_name=f"{self.name}:{step.name}",
                model=step.agent.model,
                response=response_text,
                response_time_ms=response_time_ms,
                token_usage=token_usage,
                metadata={
                    "pipeline_id": pipeline_id,
                    "step_number": step_index + 1,
                    "step_name": step.name,
                    **step.metadata
                },
                response_id=agent_response.id,
                timestamp=agent_response.timestamp,
            )

        return response_text, step_result, tokens, cost, retry_count

    async def _execute_conditional_step(
        self, step: ConditionalStep, step_index: int, current_input: str,
        pipeline_id: str, tracking_prompt_id: str,
        prompt_id: Optional[str], store: bool,
        retry_policy: Optional[Any],
    ) -> tuple:
        """Execute a ConditionalStep by evaluating predicate and running matching branch."""
        branch_taken = step.predicate(current_input)
        target = step.if_step if branch_taken else step.else_step

        if target is None:
            # No else_step and predicate was False — pass through
            return current_input, {
                "step_number": step_index + 1,
                "step_name": step.name,
                "branch": "skipped",
                "metadata": {**step.metadata, "branch_taken": branch_taken},
            }, 0, 0.0, 0

        output, step_data, tokens, cost, retries = await self._execute_sequential_step(
            target, step_index, current_input, pipeline_id,
            tracking_prompt_id, prompt_id, store, retry_policy,
        )
        # Enrich metadata with branch info
        if isinstance(step_data, dict):
            step_data["metadata"] = {
                **step_data.get("metadata", {}),
                "branch_taken": branch_taken,
                "conditional_name": step.name,
            }
        return output, step_data, tokens, cost, retries

    async def _execute_parallel_step(
        self, step: ParallelStep, step_index: int, current_input: str,
        pipeline_id: str, tracking_prompt_id: str,
        prompt_id: Optional[str], store: bool,
        retry_policy: Optional[Any],
    ) -> tuple:
        """Execute a ParallelStep by running sub-steps concurrently (FR-322)."""
        async def run_sub(sub_step: PipelineStep) -> tuple:
            return await self._execute_sequential_step(
                sub_step, step_index, current_input, pipeline_id,
                tracking_prompt_id, prompt_id, store, retry_policy,
            )

        total_tokens = 0
        total_cost = 0.0
        total_retries = 0
        all_step_data = []

        if step.failure_policy == "fail_fast":
            results = await asyncio.gather(
                *[run_sub(s) for s in step.steps]
            )
        else:  # collect_all
            results = await asyncio.gather(
                *[run_sub(s) for s in step.steps],
                return_exceptions=True
            )

        outputs = []
        for r in results:
            if isinstance(r, BaseException) and not isinstance(r, Exception):
                raise r
            if isinstance(r, Exception):
                outputs.append(f"[ERROR: {r}]")
            else:
                output_text, step_data, tokens, cost, retries = r
                outputs.append(output_text)
                all_step_data.append(step_data)
                total_tokens += tokens
                total_cost += cost
                total_retries += retries

        aggregated = step.aggregator(outputs)

        # Wrap parallel results in a summary entry
        summary = {
            "step_number": step_index + 1,
            "step_name": step.name,
            "type": "parallel",
            "sub_steps": len(step.steps),
            "output": aggregated[:200] + "..." if len(aggregated) > 200 else aggregated,
            "metadata": {**step.metadata, "failure_policy": step.failure_policy},
        }

        return aggregated, [summary] + all_step_data, total_tokens, total_cost, total_retries

    async def _execute_workflow_step(
        self, step: WorkflowStep, step_index: int, current_input: str,
        pipeline_id: str,
    ) -> tuple:
        """Execute a WorkflowStep by delegating to a sub-workflow (FR-332)."""
        config = step.config_mapping(current_input)

        # Validate sub-workflow
        validation = step.workflow.validate_config(config)
        if not validation.valid:
            raise ConfigurationError(
                f"Sub-workflow '{step.name}' validation failed: {validation.errors}"
            )

        # Execute sub-workflow (prefer async)
        if hasattr(step.workflow, 'arun'):
            result = await step.workflow.arun(config, agents=config.get('agents'))
        else:
            result = step.workflow.run(config, agents=config.get('agents'))

        # Aggregate metrics (FR-332)
        tokens = 0
        cost = 0.0
        if result.metrics:
            tokens = result.metrics.input_tokens + result.metrics.output_tokens
            cost = result.metrics.total_cost

        # Flatten sub-workflow steps with namespace prefix
        sub_step_data = []
        for sub_step in result.steps:
            sub_step_data.append({
                "step_number": step_index + 1,
                "step_name": f"{step.name}:{sub_step.step_name}",
                "agent": sub_step.agent_name or "",
                "output": sub_step.output[:200] + "..." if len(sub_step.output) > 200 else sub_step.output,
                "tokens": sub_step.input_tokens + sub_step.output_tokens,
                "cost": sub_step.cost,
                "metadata": {**step.metadata, "sub_workflow": True},
            })

        output = str(result.output) if result.output else ""
        return output, sub_step_data or [{
            "step_number": step_index + 1,
            "step_name": step.name,
            "type": "workflow",
            "output": output[:200] + "..." if len(output) > 200 else output,
            "metadata": step.metadata,
        }], tokens, cost, 0
    
    def run(
        self,
        initial_input: str,
        store: bool = True,
        retry_policy: Optional[Any] = None,
    ) -> PipelineResult:
        """
        Run the pipeline (synchronous wrapper)

        Args:
            initial_input: Initial input to first agent
            store: Whether to store results in framework (if available)
            retry_policy: Optional RetryPolicy for transient error recovery

        Returns:
            PipelineResult with all step details
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(initial_input, store, retry_policy))

        import concurrent.futures
        import contextvars

        ctx = contextvars.copy_context()

        def _runner() -> PipelineResult:
            return asyncio.run(self.arun(initial_input, store, retry_policy))

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(ctx.run, _runner)
            return future.result()
    
    async def arun_parallel_agents(
        self, 
        initial_input: str, 
        agents: List[BaseAgent]
    ) -> List[tuple[str, int, TokenUsage]]:
        """
        Run multiple agents in parallel on the same input.
        
        This is useful for comparing responses from different models
        or getting consensus from multiple agents.
        
        Args:
            initial_input: Input to send to all agents
            agents: List of agents to run in parallel
            
        Returns:
            List of (response_text, response_time_ms, token_usage) tuples
        """
        tasks = [agent.agenerate(initial_input) for agent in agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out exceptions and log them
        successful_results = []
        for i, result in enumerate(results):
            if isinstance(result, BaseException) and not isinstance(result, Exception):
                raise result
            if isinstance(result, Exception):
                EventBus.emit(Event(
                    type=EventType.AGENT_CALL_ERROR,
                    source="Pipeline",
                    data={
                        "agent_name": agents[i].name,
                        "error": str(result)
                    }
                ))
            else:
                successful_results.append(result)
        
        return successful_results
    
    def to_dict(self) -> Dict[str, Any]:
        """Export pipeline configuration"""
        return {
            "name": self.name,
            "steps": [
                {
                    "name": step.name,
                    "agent": step.agent.name,
                    "model": step.agent.model,
                    "metadata": step.metadata
                }
                for step in self.steps
            ]
        }


class WorkflowTemplates:
    """Pre-built workflow templates"""
    
    @staticmethod
    def planner_implementer(planner_agent: BaseAgent, implementer_agent: BaseAgent) -> Pipeline:
        """
        Classic planner → implementer workflow
        
        Args:
            planner_agent: Agent for design/planning
            implementer_agent: Agent for implementation guidance
            
        Returns:
            Configured Pipeline
        """
        pipeline = Pipeline(name="planner-implementer")
        
        pipeline.add_step(
            name="planner",
            agent=planner_agent,
            metadata={"role": "designer"}
        )
        
        pipeline.add_step(
            name="implementer",
            agent=implementer_agent,
            transform=lambda spec: (
                f"Here is the design spec:\n\n{spec}\n\n"
                f"Now provide implementation guidance for a developer."
            ),
            metadata={"role": "developer"}
        )
        
        return pipeline
    
    @staticmethod
    def code_review(reviewer_agent: BaseAgent, improver_agent: BaseAgent) -> Pipeline:
        """
        Code review → improvement workflow
        
        Args:
            reviewer_agent: Agent for reviewing code
            improver_agent: Agent for suggesting improvements
            
        Returns:
            Configured Pipeline
        """
        pipeline = Pipeline(name="code-review")
        
        pipeline.add_step(
            name="reviewer",
            agent=reviewer_agent,
            transform=lambda code: (
                f"Review this code and identify issues:\n\n{code}"
            ),
            metadata={"role": "reviewer"}
        )
        
        pipeline.add_step(
            name="improver",
            agent=improver_agent,
            transform=lambda review: (
                f"Based on this code review:\n\n{review}\n\n"
                f"Provide specific improvements."
            ),
            metadata={"role": "improver"}
        )
        
        return pipeline
    
    @staticmethod
    def design_review_chain(
        drafter_agent: BaseAgent,
        reviewer_agent: BaseAgent,
        final_reviewer_agent: BaseAgent
    ) -> Pipeline:
        """
        Design document creation chain: Draft → Review → Final Polish
        
        Args:
            drafter_agent: Agent to create the first draft (e.g., Sonnet 4.5)
            reviewer_agent: Agent to review the draft (e.g., GPT-4)
            final_reviewer_agent: Agent for final review/polish (e.g., Composer)
            
        Returns:
            Configured Pipeline
        """
        pipeline = Pipeline(name="design-review-chain")
        
        pipeline.add_step(
            name="drafter",
            agent=drafter_agent,
            metadata={"role": "drafter", "task": "create_initial_draft"}
        )
        
        pipeline.add_step(
            name="reviewer",
            agent=reviewer_agent,
            transform=lambda draft: (
                f"Review the following design document draft. Identify gaps, inconsistencies, "
                f"and areas for improvement. Be critical and constructive.\n\n"
                f"DRAFT:\n{draft}"
            ),
            metadata={"role": "reviewer", "task": "review_draft"}
        )
        
        pipeline.add_step(
            name="final_reviewer",
            agent=final_reviewer_agent,
            transform=lambda review_feedback: (
                f"Based on the previous review, provide a final polished version of the design document. "
                f"incorporate the feedback where appropriate and ensure the document is complete and professional.\n\n"
                f"REVIEW FEEDBACK:\n{review_feedback}"
            ),
            metadata={"role": "final_reviewer", "task": "final_polish"}
        )
        
        return pipeline
    
    @staticmethod
    def design_polish_chain(
        polisher_agent: BaseAgent,
        updater_agent: BaseAgent,
        final_polisher_agent: BaseAgent,
        prompt_instructions: Optional[str] = None
    ) -> Pipeline:
        """
        Design document polish chain: Polish → Suggest Updates → Final Polish
        
        Starts with an existing drafted design document and refines it through
        three stages: initial polish, update suggestions, and final polish.
        
        Args:
            polisher_agent: Agent for initial polish pass (e.g., Claude Sonnet)
            updater_agent: Agent to suggest updates/improvements (e.g., GPT-4)
            final_polisher_agent: Agent for final polish incorporating suggestions (e.g., Claude Opus)
            prompt_instructions: Optional custom instructions from prompt file to use for the first agent (polisher) only
            
        Returns:
            Configured Pipeline
        """
        pipeline = Pipeline(name="design-polish-chain")
        
        # Base instructions for each step
        polish_base = (
            "Review and polish the following design document. Improve clarity, "
            "structure, and professional presentation while maintaining all core content."
        )
        
        updater_base = (
            "Review the polished design document below and suggest specific updates, "
            "improvements, or additions. Be constructive and specific about what should "
            "be changed or added. Focus on:\n"
            "- Missing sections or details\n"
            "- Areas that need clarification\n"
            "- Technical improvements\n"
            "- Better organization or structure"
        )
        
        final_polish_base = (
            "Based on the update suggestions below, create a final polished version "
            "of the design document. Incorporate the suggested improvements while "
            "maintaining professional quality and completeness."
        )
        
        # Incorporate prompt instructions if provided (only for the first agent/polisher)
        if prompt_instructions:
            polish_instructions = f"{polish_base}\n\n## Polishing Instructions\n\n{prompt_instructions}"
        else:
            polish_instructions = polish_base
        
        # Other steps use base instructions only
        updater_instructions = updater_base
        final_polish_instructions = final_polish_base
        
        pipeline.add_step(
            name="polish",
            agent=polisher_agent,
            transform=lambda document: (
                f"{polish_instructions}\n\n"
                f"DOCUMENT:\n{document}"
            ),
            metadata={"role": "polisher", "task": "initial_polish"}
        )
        
        pipeline.add_step(
            name="suggest_updates",
            agent=updater_agent,
            transform=lambda polished_doc: (
                f"{updater_instructions}\n\n"
                f"POLISHED DOCUMENT:\n{polished_doc}\n\n"
                f"Provide your suggestions in a clear, actionable format."
            ),
            metadata={"role": "updater", "task": "suggest_updates"}
        )
        
        pipeline.add_step(
            name="final_polish",
            agent=final_polisher_agent,
            transform=lambda suggestions: (
                f"{final_polish_instructions}\n\n"
                f"UPDATE SUGGESTIONS:\n{suggestions}\n\n"
                f"Provide the complete, final polished design document."
            ),
            metadata={"role": "final_polisher", "task": "final_polish"}
        )
        
        return pipeline
    
    @staticmethod
    def error_analysis_chain(analyzer_agent: BaseAgent) -> Pipeline:
        """
        Error analysis chain: Analyzes error and generates prompt with solution.
        
        Takes error information and uses an agent to:
        1. Analyze and isolate the issue
        2. Generate a prompt describing the understanding
        3. Suggest a solution
        
        Args:
            analyzer_agent: Agent for analyzing the error
            
        Returns:
            Configured Pipeline
        """
        pipeline = Pipeline(name="error-analysis-chain")
        
        pipeline.add_step(
            name="analyze_error",
            agent=analyzer_agent,
            transform=lambda error_text: (
                f"Analyze the following error from a log file. Your task is to:\n\n"
                f"1. Identify the root cause of the error\n"
                f"2. Isolate the specific issue (what went wrong and why)\n"
                f"3. Understand the context and impact\n"
                f"4. Suggest a concrete solution to fix the issue\n\n"
                f"ERROR INFORMATION:\n{error_text}\n\n"
                f"Provide a comprehensive analysis that includes:\n"
                f"- Clear identification of the root cause\n"
                f"- Explanation of why this error occurred\n"
                f"- Specific steps to resolve the issue\n"
                f"- Prevention strategies if applicable"
            ),
            metadata={"role": "error_analyzer", "task": "analyze_and_suggest"}
        )
        
        return pipeline

    @staticmethod
    def agent_config_error_analysis_chain(analyzer_agent: BaseAgent) -> Pipeline:
        """
        Agent configuration error analysis workflow
        
        Analyzes agent configuration errors to:
        1. Identify the root cause of configuration failures
        2. Understand what's wrong with the agent setup
        3. Suggest specific fixes
        
        Args:
            analyzer_agent: Agent for analyzing the configuration errors
            
        Returns:
            Configured Pipeline
        """
        pipeline = Pipeline(name="agent-config-error-analysis-chain")
        
        pipeline.add_step(
            name="analyze_config_error",
            agent=analyzer_agent,
            transform=lambda error_info: (
                f"Analyze the following agent configuration error. Your task is to:\n\n"
                f"1. Identify why the agent configuration is invalid or failing\n"
                f"2. Determine what specific configuration issue is causing the problem\n"
                f"3. Understand the relationship between the error and the agent configuration\n"
                f"4. Provide specific, actionable steps to fix the configuration\n\n"
                f"AGENT CONFIGURATION ERROR:\n{error_info}\n\n"
                f"Provide a comprehensive analysis that includes:\n"
                f"- Clear identification of the configuration problem\n"
                f"- Explanation of why this configuration is invalid\n"
                f"- Specific steps to correct the agent configuration\n"
                f"- Verification steps to ensure the fix works\n"
                f"- Prevention tips for avoiding similar issues in the future"
            ),
            metadata={"role": "config_error_analyzer", "task": "analyze_and_fix"}
        )
        
        return pipeline

    @staticmethod
    def iterative_refinement(
        agents: List[BaseAgent],
        iterations: int = 2
    ) -> Pipeline:
        """
        Iterative refinement workflow
        
        Args:
            agents: List of agents to cycle through
            iterations: Number of iterations
            
        Returns:
            Configured Pipeline
        """
        pipeline = Pipeline(name="iterative-refinement")
        
        for i in range(iterations):
            for j, agent in enumerate(agents):
                pipeline.add_step(
                    name=f"iteration-{i+1}-agent-{j+1}",
                    agent=agent,
                    transform=lambda x: f"Refine this further:\n\n{x}",
                    metadata={
                        "iteration": i + 1,
                        "agent_index": j + 1
                    }
                )
        
        return pipeline


class PipelineComparison:
    """Compare different pipeline configurations"""
    
    def __init__(self, framework=None):
        """
        Initialize pipeline comparison
        
        Args:
            framework: Optional AgentFramework for storage
        """
        self.framework = framework
        self.results: List[PipelineResult] = []
    
    def add_result(self, result: PipelineResult):
        """Add a pipeline result to comparison"""
        self.results.append(result)
    
    def compare(self) -> Dict[str, Any]:
        """
        Compare pipeline results
        
        Returns:
            Comparison dictionary
        """
        if not self.results:
            return {"error": "No results to compare"}
        
        comparisons = []
        for result in self.results:
            comparisons.append({
                "pipeline_id": result.pipeline_id,
                "steps": len(result.steps),
                "total_time_ms": result.total_time_ms,
                "total_tokens": result.total_tokens,
                "total_cost": result.total_cost,
                "timestamp": result.timestamp.isoformat()
            })
        
        # Rankings
        by_speed = sorted(comparisons, key=lambda x: x["total_time_ms"])
        by_cost = sorted(comparisons, key=lambda x: x["total_cost"])
        by_tokens = sorted(comparisons, key=lambda x: x["total_tokens"])
        
        return {
            "total_pipelines": len(self.results),
            "comparisons": comparisons,
            "rankings": {
                "by_speed": by_speed,
                "by_cost": by_cost,
                "by_tokens": by_tokens
            },
            "averages": {
                "time_ms": sum(c["total_time_ms"] for c in comparisons) / len(comparisons),
                "tokens": sum(c["total_tokens"] for c in comparisons) / len(comparisons),
                "cost": sum(c["total_cost"] for c in comparisons) / len(comparisons)
            }
        }
    
    def generate_report(self) -> str:
        """Generate markdown report"""
        comparison = self.compare()
        
        if "error" in comparison:
            return comparison["error"]
        
        lines = [
            "# Pipeline Comparison Report",
            "",
            f"**Total Pipelines**: {comparison['total_pipelines']}",
            "",
            "## Averages",
            "",
            f"- **Time**: {comparison['averages']['time_ms']:.2f}ms",
            f"- **Tokens**: {comparison['averages']['tokens']:.0f}",
            f"- **Cost**: ${comparison['averages']['cost']:.4f}",
            "",
            "## Rankings",
            "",
            "### By Speed",
            ""
        ]
        
        for i, p in enumerate(comparison['rankings']['by_speed'][:5], 1):
            lines.append(f"{i}. Pipeline `{p['pipeline_id']}` - {p['total_time_ms']}ms")
        
        lines.extend([
            "",
            "### By Cost",
            ""
        ])
        
        for i, p in enumerate(comparison['rankings']['by_cost'][:5], 1):
            lines.append(f"{i}. Pipeline `{p['pipeline_id']}` - ${p['total_cost']:.4f}")
        
        return "\n".join(lines)

