"""
WorkflowBase protocol defining the interface for workflow implementations.

Workflows implement this protocol to be discoverable and executable
through the WorkflowRegistry.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Protocol, TYPE_CHECKING, runtime_checkable
import asyncio

from .models import (
    WorkflowMetadata,
    WorkflowResult,
    ValidationResult,
    ProjectContext,
    DryRunResult,
)

if TYPE_CHECKING:
    from ..agents import BaseAgent

# Graceful OTel import — no-op when not installed (FR-403)
try:
    from opentelemetry import trace as _otel_trace
    _tracer = _otel_trace.get_tracer("startd8.workflows")
except ImportError:
    _otel_trace = None  # type: ignore[assignment]
    _tracer = None

# Observability manifest descriptor — consumed by generate_manifest(), zero runtime cost.
_OTEL_DESCRIPTORS = {
    "spans": [
        {
            "name_pattern": "workflow.{workflow_id}",
            "kind": "INTERNAL",
            "attributes": [
                "workflow.id",
                "workflow.name",
                "workflow.version",
                "workflow.success",
            ],
            "events": [],
        },
    ],
}


# Type alias for progress callbacks
# Signature: (current_step: int, total_steps: int, message: str) -> None
ProgressCallback = Callable[[int, int, str], None]


@runtime_checkable
class Workflow(Protocol):
    """
    Protocol defining the interface for workflow implementations.

    Workflows provide a standardized way to execute multi-step operations
    that may involve one or more agents. They can be discovered via the
    WorkflowRegistry and invoked programmatically, via CLI, or through MCP.

    Example implementation:
        class MyWorkflow:
            @property
            def metadata(self) -> WorkflowMetadata:
                return WorkflowMetadata(
                    workflow_id="my-workflow",
                    name="My Workflow",
                    description="Does something useful",
                    capabilities=["document-processing"],
                    inputs=[
                        WorkflowInput(name="document", type="text", required=True),
                    ]
                )

            def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
                if "document" not in config:
                    return ValidationResult.failure(["Missing required input: document"])
                return ValidationResult.success()

            def run(self, config, agents=None, on_progress=None) -> WorkflowResult:
                # Implementation here
                return WorkflowResult(...)
    """

    @property
    def metadata(self) -> WorkflowMetadata:
        """
        Return metadata describing this workflow.

        The metadata includes:
        - workflow_id: Unique identifier
        - name: Human-readable name
        - description: What the workflow does
        - capabilities: List of capability tags
        - inputs: List of WorkflowInput definitions
        - agent requirements
        """
        ...

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """
        Validate workflow configuration before execution.

        Args:
            config: Configuration dictionary with input values

        Returns:
            ValidationResult with valid=True if config is acceptable,
            or valid=False with a list of error messages.

        Example:
            result = workflow.validate_config({"document": "...", "agents": [...]})
            if not result.valid:
                print(f"Errors: {result.errors}")
        """
        ...

    def run(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> WorkflowResult:
        """
        Execute the workflow synchronously.

        Args:
            config: Configuration dictionary with input values
            agents: Optional list of pre-resolved BaseAgent instances.
                   If not provided, workflow may create agents from
                   agent specs in config.
            on_progress: Optional callback for progress updates.
                        Called with (current_step, total_steps, message).

        Returns:
            WorkflowResult containing success status, output, metrics,
            and step-by-step results.

        Raises:
            ConfigurationError: If config is invalid
            WorkflowError: If execution fails

        Example:
            result = workflow.run(
                config={"document": "...", "instructions": "..."},
                agents=[claude_agent, gpt_agent],
                on_progress=lambda c, t, m: print(f"[{c}/{t}] {m}")
            )
        """
        ...


class AsyncWorkflow(Workflow, Protocol):
    """
    Extended protocol for workflows that support async execution.

    Workflows implementing this protocol can be run asynchronously,
    which is useful for concurrent agent calls and non-blocking execution.
    """

    async def arun(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> WorkflowResult:
        """
        Execute the workflow asynchronously.

        Args:
            config: Configuration dictionary with input values
            agents: Optional list of pre-resolved BaseAgent instances
            on_progress: Optional callback for progress updates

        Returns:
            WorkflowResult containing success status, output, and metrics

        Example:
            result = await workflow.arun(
                config={"document": "..."},
                agents=[agent],
            )
        """
        ...


class WorkflowBase:
    """
    Base class providing default implementations for common workflow operations.

    Inherit from this class to get:
    - Default sync/async wrappers
    - Progress callback helpers
    - Common validation logic

    Subclasses must implement:
    - metadata property
    - _execute() or _aexecute() method
    """

    @property
    def metadata(self) -> WorkflowMetadata:
        """Override to provide workflow metadata."""
        raise NotImplementedError("Subclasses must implement metadata property")

    # Type mapping for auto-validation (FR-110)
    _TYPE_MAP = {
        "string": str, "text": str, "file": str,
        "number": (int, float), "boolean": bool,
        "agent_spec": str, "agent_spec_list": list,
    }

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """
        Default validation checks required inputs from metadata.

        Performs three layers of validation:
        1. Required-field presence check
        2. Type checking against WorkflowInput.type definitions (FR-110)
        3. Optional JSON Schema validation when jsonschema is installed (FR-111)
        4. Custom validation via _custom_validate() hook (FR-112)

        Override for custom validation logic. Subclass overrides bypass
        all auto-validation; use _custom_validate() to extend instead.
        """
        errors = []
        meta = self.metadata

        # Check required inputs
        for inp in meta.inputs:
            if inp.required and inp.name not in config:
                errors.append(f"Missing required input: {inp.name}")

        # Type checking (FR-110)
        for inp in meta.inputs:
            if inp.name in config:
                val = config[inp.name]
                if val is None and not inp.required:
                    continue  # Explicitly allowing None for optional inputs
                expected = self._TYPE_MAP.get(inp.type)
                if expected and not isinstance(val, expected):
                    errors.append(
                        f"Input '{inp.name}': expected {inp.type}, "
                        f"got {type(val).__name__}"
                    )

        # Optional JSON Schema validation (FR-111)
        try:
            import jsonschema
            schema = meta.get_input_schema()
            jsonschema.validate(config, schema)
        except ImportError:
            pass  # Graceful fallback — jsonschema not installed
        except Exception as e:
            # Handle both ValidationError and SchemaError
            errors.append(f"Schema validation: {e.message}")

        # Check agent count if agents provided
        agents = config.get("agents", [])
        if meta.requires_agents:
            if len(agents) < meta.min_agents:
                errors.append(
                    f"Requires at least {meta.min_agents} agent(s), got {len(agents)}"
                )
            if meta.max_agents is not None and len(agents) > meta.max_agents:
                errors.append(
                    f"Maximum {meta.max_agents} agent(s) allowed, got {len(agents)}"
                )

        # Custom validation hook (FR-112)
        errors.extend(self._custom_validate(config))

        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()

    def _custom_validate(self, config: Dict[str, Any]) -> List[str]:
        """Override for workflow-specific validation. Returns error messages."""
        return []

    def run(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]] = None,
        on_progress: Optional[ProgressCallback] = None,
        dry_run: bool = False,
    ) -> WorkflowResult:
        """
        Synchronous execution wrapper.

        Calls _execute if implemented, otherwise wraps _aexecute synchronously.
        If dry_run=True, returns an execution plan without making API calls (FR-103).
        """
        # Validate first
        validation = self.validate_config(config)
        if not validation.valid:
            result = WorkflowResult.from_error(
                self.metadata.workflow_id,
                f"Validation failed: {'; '.join(validation.errors)}"
            )
            self._persist_error_result(result, config)
            return result

        # Dry run interception (FR-340)
        if dry_run:
            return self._build_dry_run_result(config, agents)

        # OTel parent span via start_as_current_span so child spans nest (FR-400)
        with self._create_workflow_span(config) as span:
            self._enrich_span_with_project_context(span, config)

            try:
                # Check if _execute is overridden (not the base class version)
                has_sync = (
                    hasattr(self, '_execute') and
                    type(self)._execute is not WorkflowBase._execute
                )
                has_async = (
                    hasattr(self, '_aexecute') and
                    type(self)._aexecute is not WorkflowBase._aexecute
                )

                # Prefer sync execution if available
                if has_sync:
                    result = self._execute(config, agents, on_progress)
                    if span:
                        span.set_attribute("workflow.success", result.success)
                    if not result.success:
                        self._persist_error_result(result, config)
                    return result

                # Fall back to async wrapped synchronously
                if has_async:
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                    if loop.is_running():
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            future = pool.submit(
                                asyncio.run,
                                self._aexecute(config, agents, on_progress)
                            )
                            result = future.result()
                    else:
                        result = loop.run_until_complete(
                            self._aexecute(config, agents, on_progress)
                        )
                    if span:
                        span.set_attribute("workflow.success", result.success)
                    if not result.success:
                        self._persist_error_result(result, config)
                    return result

                # Neither implemented
                raise NotImplementedError(
                    "Subclasses must implement _execute or _aexecute"
                )
            except Exception as e:
                if span and _otel_trace:
                    span.set_status(_otel_trace.StatusCode.ERROR, str(e))
                    span.record_exception(e)
                raise

    async def arun(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> WorkflowResult:
        """
        Asynchronous execution wrapper.

        If the subclass implements _execute (sync), wraps it in executor.
        Otherwise, calls _aexecute directly.
        """
        # Validate first
        validation = self.validate_config(config)
        if not validation.valid:
            result = WorkflowResult.from_error(
                self.metadata.workflow_id,
                f"Validation failed: {'; '.join(validation.errors)}"
            )
            self._persist_error_result(result, config)
            return result

        # OTel parent span via start_as_current_span so child spans nest
        with self._create_workflow_span(config) as span:
            self._enrich_span_with_project_context(span, config)

            try:
                # Check if methods are overridden (not the base class version)
                has_sync = (
                    hasattr(self, '_execute') and
                    type(self)._execute is not WorkflowBase._execute
                )
                has_async = (
                    hasattr(self, '_aexecute') and
                    type(self)._aexecute is not WorkflowBase._aexecute
                )

                # Prefer async execution if available
                if has_async:
                    result = await self._aexecute(config, agents, on_progress)
                elif has_sync:
                    # Fall back to sync in executor
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None,
                        lambda: self._execute(config, agents, on_progress)
                    )
                else:
                    raise NotImplementedError(
                        "Subclasses must implement _execute or _aexecute"
                    )

                if span:
                    span.set_attribute("workflow.success", result.success)
                if not result.success:
                    self._persist_error_result(result, config)
                return result
            except Exception as e:
                if span and _otel_trace:
                    span.set_status(_otel_trace.StatusCode.ERROR, str(e))
                    span.record_exception(e)
                raise

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """
        Synchronous execution implementation.

        Override this OR _aexecute in subclasses.
        """
        raise NotImplementedError(
            "Subclasses must implement _execute or _aexecute"
        )

    async def _aexecute(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """
        Asynchronous execution implementation.

        Override this OR _execute in subclasses.
        """
        raise NotImplementedError(
            "Subclasses must implement _execute or _aexecute"
        )

    def _build_dry_run_result(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]],
    ) -> WorkflowResult:
        """Build execution plan without making API calls (FR-340)."""
        meta = self.metadata
        steps = []
        for i, inp in enumerate(meta.inputs):
            steps.append({
                "step": i + 1,
                "name": inp.name,
                "type": inp.type,
                "agent": agents[i].name if agents and i < len(agents) else "unassigned",
            })

        step_order = [inp.name for inp in meta.inputs]
        estimated_tokens = self._estimate_tokens(config)
        estimated_cost = self._estimate_cost(estimated_tokens)

        dry_result = DryRunResult(
            execution_plan=steps,
            estimated_tokens=estimated_tokens,
            estimated_cost=estimated_cost,
            step_order=step_order,
        )
        return WorkflowResult(
            workflow_id=meta.workflow_id,
            success=True,
            output=dry_result.to_dict(),
            metadata={"dry_run": True},
        )

    def _estimate_tokens(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Estimate tokens from input character count — chars/4 heuristic (FR-341)."""
        estimates: Dict[str, Any] = {}
        for inp in self.metadata.inputs:
            value = config.get(inp.name, "")
            char_count = len(str(value))
            input_tokens = char_count // 4
            output_tokens = input_tokens * 2
            estimates[inp.name] = {"input": input_tokens, "output": output_tokens}
        return estimates

    def _estimate_cost(self, token_estimates: Dict[str, Any]) -> float:
        """Estimate cost using PricingService if available (FR-341)."""
        try:
            from ..costs.pricing import PricingService
            pricing = PricingService()
            total = 0.0
            for name, tokens in token_estimates.items():
                total += pricing.calculate_total_cost(
                    "claude-sonnet-4-6",  # Default model for estimation
                    tokens["input"],
                    tokens["output"],
                )
            return total
        except (ImportError, Exception):
            # Fallback: rough $3/$15 per million tokens estimate
            total = 0.0
            for name, tokens in token_estimates.items():
                total += tokens["input"] * 3.0 / 1_000_000
                total += tokens["output"] * 15.0 / 1_000_000
            return total

    def _create_workflow_span(self, config: Dict[str, Any]):
        """Create and configure an OTel span for this workflow execution.

        Returns a context manager that yields the span (or None if OTel unavailable).
        """
        if not _tracer:
            from contextlib import nullcontext
            return nullcontext(None)

        span_ctx = _tracer.start_as_current_span(
            f"workflow.{self.metadata.workflow_id}",
            attributes={
                "workflow.id": self.metadata.workflow_id,
                "workflow.name": self.metadata.name,
                "workflow.version": self.metadata.version,
            },
        )
        return span_ctx

    def _enrich_span_with_project_context(self, span, config: Dict[str, Any]) -> None:
        """Attach ProjectContext labels to a span (FR-402)."""
        if span is None:
            return
        project_ctx = self._extract_project_context(config)
        if not project_ctx.is_empty():
            for key, value in project_ctx.to_labels().items():
                span.set_attribute(f"io.contextcore.{key}", value)

    def _emit_progress(
        self,
        callback: Optional[ProgressCallback],
        current: int,
        total: int,
        message: str,
    ) -> None:
        """Helper to safely emit progress updates."""
        if callback:
            try:
                callback(current, total, message)
            except Exception:
                pass  # Don't let callback errors break workflow

    def _persist_error_result(
        self,
        result: WorkflowResult,
        config: Dict[str, Any],
    ) -> None:
        """Best-effort persistence of a failed WorkflowResult to .startd8/task_errors/.

        Never raises — errors in the error-recording path are silently logged.
        """
        if result.success:
            return
        try:
            from ..storage.error_store import TaskErrorStore

            project_root = config.get("project_root") or "."
            store = TaskErrorStore(project_root=project_root)
            store.record_workflow_result_error(
                workflow_id=result.workflow_id,
                error_message=result.error or "Unknown workflow error",
                steps=[s.to_dict() for s in result.steps] if result.steps else None,
                metrics=result.metrics.to_dict() if result.metrics else None,
            )
        except Exception:
            pass  # Never let error persistence break the workflow

    def _extract_project_context(self, config: Dict[str, Any]) -> ProjectContext:
        """
        Extract ContextCore project context from workflow config.
        
        Supports two formats:
        1. Nested: {"project_context": {"project_id": "...", ...}}
        2. Top-level: {"project_id": "...", "task_id": "...", ...}
        
        Args:
            config: Workflow configuration dictionary
            
        Returns:
            ProjectContext instance (may be empty if no context provided)
        """
        return ProjectContext.from_config(config)
