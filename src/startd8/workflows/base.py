"""
WorkflowBase protocol defining the interface for workflow implementations.

Workflows implement this protocol to be discoverable and executable
through the WorkflowRegistry.
"""

from typing import Any, Callable, Dict, List, Optional, Protocol, Union, runtime_checkable
import asyncio

from .models import (
    WorkflowMetadata,
    WorkflowResult,
    ValidationResult,
    ProjectContext,
)


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
        agents: Optional[List['BaseAgent']] = None,
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
        agents: Optional[List['BaseAgent']] = None,
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

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """
        Default validation checks required inputs from metadata.

        Override for custom validation logic.
        """
        errors = []
        meta = self.metadata

        # Check required inputs
        for inp in meta.inputs:
            if inp.required and inp.name not in config:
                errors.append(f"Missing required input: {inp.name}")

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

        if errors:
            return ValidationResult.failure(errors)
        return ValidationResult.success()

    def run(
        self,
        config: Dict[str, Any],
        agents: Optional[List['BaseAgent']] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> WorkflowResult:
        """
        Synchronous execution wrapper.

        Calls _execute if implemented, otherwise wraps _aexecute synchronously.
        """
        # Validate first
        validation = self.validate_config(config)
        if not validation.valid:
            return WorkflowResult.from_error(
                self.metadata.workflow_id,
                f"Validation failed: {'; '.join(validation.errors)}"
            )

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
            return self._execute(config, agents, on_progress)

        # Fall back to async wrapped synchronously
        if has_async:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            if loop.is_running():
                # Already in async context - can't use run_until_complete
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self._aexecute(config, agents, on_progress)
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self._aexecute(config, agents, on_progress)
                )

        # Neither implemented
        raise NotImplementedError(
            "Subclasses must implement _execute or _aexecute"
        )

    async def arun(
        self,
        config: Dict[str, Any],
        agents: Optional[List['BaseAgent']] = None,
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
            return WorkflowResult.from_error(
                self.metadata.workflow_id,
                f"Validation failed: {'; '.join(validation.errors)}"
            )

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
            return await self._aexecute(config, agents, on_progress)

        # Fall back to sync in executor
        if has_sync:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                lambda: self._execute(config, agents, on_progress)
            )

        # Neither implemented
        raise NotImplementedError(
            "Subclasses must implement _execute or _aexecute"
        )

    def _execute(
        self,
        config: Dict[str, Any],
        agents: Optional[List['BaseAgent']],
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
        agents: Optional[List['BaseAgent']],
        on_progress: Optional[ProgressCallback],
    ) -> WorkflowResult:
        """
        Asynchronous execution implementation.

        Override this OR _execute in subclasses.
        """
        raise NotImplementedError(
            "Subclasses must implement _execute or _aexecute"
        )

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
