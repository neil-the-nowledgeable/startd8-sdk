"""
Development Phase Implementation for Artisan Contractor System

This module implements an iterative development phase that:
- Resolves chunk dependencies via topological sorting (Kahn's algorithm)
- Executes chunks in dependency order with parallel support (bounded concurrency)
- Persists state for chunk-level resume capability
- Gates progression on test results (test-pass gates)
- Supports configurable retry logic with exponential backoff option

Architecture:
    DevelopmentPlan -> validate -> topological_sort
    -> tier execution -> DevelopmentResult

    Each tier contains chunks whose dependencies are fully satisfied.
    Chunks within a tier execute concurrently (bounded by max_parallel).
    State is persisted after each tier for crash recovery.

Usage:
    from development_phase import (
        DevelopmentPlan, DevelopmentChunk, DevelopmentPhase,
        run_development_phase,
    )

    plan = DevelopmentPlan(
        plan_id="my-project",
        chunks=[
            DevelopmentChunk(
                chunk_id="setup",
                description="Initialize project structure",
                dependencies=[],
                file_targets=["setup.py"],
                implementation_prompt="Create setup.py with ...",
                test_commands=["python -m pytest tests/test_setup.py"],
            ),
            DevelopmentChunk(
                chunk_id="core",
                description="Implement core logic",
                dependencies=["setup"],
                file_targets=["src/core.py"],
                implementation_prompt="Implement the core module ...",
                test_commands=["python -m pytest tests/test_core.py"],
            ),
        ],
        config={"dry_run": False},
    )

    result = await run_development_phase(plan, max_parallel=4)
    print(result.summary)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional, Set, Tuple

from startd8.contractors.protocols import (
    DRAFT_MODEL_CLAUDE_HAIKU,
    VALIDATE_MODEL_CLAUDE_SONNET,
)


# ============================================================================
# ENUMS
# ============================================================================


class ChunkStatus(str, Enum):
    """Lifecycle states for a development chunk.

    State machine:
        PENDING -> QUEUED -> RUNNING -> TESTING -> PASSED
                                  |          |
                                  v          v
                               (retry)    (retry)
                                  |          |
                                  +----+-----+
                                       |
                                       v
                                    FAILED -> SKIPPED (dependents)
    """

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    TESTING = "testing"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


# ============================================================================
# EXCEPTIONS
# ============================================================================


class DevelopmentPhaseError(Exception):
    """Base exception for development phase errors."""

    pass


class CyclicDependencyError(DevelopmentPhaseError):
    """Raised when chunk dependencies contain a cycle."""

    pass


class MissingDependencyError(DevelopmentPhaseError):
    """Raised when a chunk depends on a non-existent chunk_id."""

    pass


class PlanValidationError(DevelopmentPhaseError):
    """Raised when a development plan fails validation.

    Attributes:
        errors: List of individual validation error messages.
    """

    def __init__(self, errors: List[str]):
        self.errors = list(errors)
        super().__init__(f"Plan validation failed: {'; '.join(self.errors)}")


class ChunkExecutionError(DevelopmentPhaseError):
    """Raised when a chunk fails execution after all retries."""

    def __init__(self, chunk_id: str, attempts: int, last_error: str):
        self.chunk_id = chunk_id
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"Chunk {chunk_id} failed after {attempts} attempts: {last_error}"
        )


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class DevelopmentChunk:
    """A unit of development work with dependencies and test gates.

    Each chunk represents an atomic unit of implementation that:
    - May depend on other chunks (must complete first)
    - Targets specific files
    - Has an implementation prompt for the executor
    - Has test commands that gate progression
    - Supports configurable retry count
    """

    chunk_id: str
    """Unique identifier for this chunk."""

    description: str
    """Human-readable description of the chunk's purpose."""

    dependencies: List[str]
    """List of chunk_ids that must PASS before this chunk can execute."""

    file_targets: List[str]
    """Paths to files this chunk modifies or creates."""

    implementation_prompt: str
    """Instructions for implementing the chunk's work."""

    test_commands: List[str]
    """Shell commands to verify the chunk's work. All must pass."""

    max_retries: int = 5
    """Maximum number of retries (total attempts = max_retries + 1 = 6)."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional metadata for the chunk (passed through to executor)."""


@dataclass
class ChunkState:
    """Persisted execution state for a single chunk.

    This state is saved after each tier completes, enabling
    crash recovery and resume from the last successful tier.
    """

    chunk_id: str
    """Chunk identifier."""

    status: ChunkStatus
    """Current status in the lifecycle."""

    attempts: int = 0
    """Number of execution attempts made so far."""

    last_error: Optional[str] = None
    """Last error message, if any."""

    started_at: Optional[str] = None
    """ISO 8601 timestamp of execution start."""

    completed_at: Optional[str] = None
    """ISO 8601 timestamp of execution completion."""

    test_output: Optional[str] = None
    """Output from test execution, if any."""


@dataclass
class DevelopmentPlan:
    """Input specification for the development phase.

    Configuration options (via ``config`` dict):
        dry_run (bool): If True, skip actual execution and tests.
            Default: False.
        max_parallel (int): Override for max concurrent chunks.
            Default: uses DevelopmentPhase.max_parallel.
        state_dir (str): Directory for state files.
            Default: ".startd8/state".
    """

    plan_id: str
    """Unique identifier for this plan."""

    chunks: List[DevelopmentChunk]
    """List of chunks to execute."""

    config: Dict[str, Any] = field(default_factory=dict)
    """Configuration options."""


@dataclass
class DevelopmentResult:
    """Output from the development phase execution.

    Attributes:
        success: True only if every chunk reached PASSED status.
    """

    plan_id: str
    """Plan identifier."""

    success: bool
    """True only if all chunks passed; False if any failed or were skipped."""

    chunk_states: Dict[str, ChunkState]
    """Final state of each chunk, keyed by chunk_id."""

    execution_order: List[List[str]]
    """Tiers of chunk_ids in dependency-resolved execution order."""

    total_duration_seconds: float
    """Total wall-clock execution time in seconds."""

    summary: str
    """Human-readable summary of execution results."""

    total_cost_usd: float = 0.0
    """Total LLM cost in USD across all chunk executions."""

    total_input_tokens: int = 0
    """Total input tokens consumed across all chunk executions."""

    total_output_tokens: int = 0
    """Total output tokens generated across all chunk executions."""


# ============================================================================
# ABSTRACT BASE CLASSES
# ============================================================================


class ChunkExecutor(ABC):
    """Abstract base for executing a chunk's implementation work.

    Implementations should be idempotent where possible, since chunks
    may be retried after partial execution.
    """

    @abstractmethod
    async def execute(
        self, chunk: DevelopmentChunk, context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Execute the chunk's implementation.

        Args:
            chunk: The chunk to execute.
            context: Execution context containing at minimum:
                - plan_id (str)
                - dry_run (bool)

        Returns:
            Tuple of (success: bool, output_or_error: str).
        """
        ...


class TestRunner(ABC):
    """Abstract base for running tests after chunk execution.

    Test runners validate that a chunk's implementation is correct
    before allowing dependent chunks to proceed.
    """

    @abstractmethod
    async def run_tests(
        self, chunk: DevelopmentChunk, context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        Run the test commands for a chunk.

        Args:
            chunk: The chunk whose tests to run.
            context: Execution context.

        Returns:
            Tuple of (all_passed: bool, test_output: str).
        """
        ...


class StateStore(ABC):
    """Abstract base for persisting chunk execution state.

    State stores enable resume capability by saving chunk states
    after each tier completes. On restart, previously PASSED chunks
    are skipped and execution resumes from the first incomplete tier.
    """

    @abstractmethod
    async def load_state(self, plan_id: str) -> Dict[str, ChunkState]:
        """
        Load previously persisted state for a plan.

        Args:
            plan_id: The plan identifier.

        Returns:
            Dictionary mapping chunk_id to ChunkState.
            Empty dict if no prior state exists.
        """
        ...

    @abstractmethod
    async def save_state(self, plan_id: str, states: Dict[str, ChunkState]) -> None:
        """
        Persist the current state of all chunks.

        Must be atomic (all-or-nothing) to prevent corruption.

        Args:
            plan_id: The plan identifier.
            states: Dictionary mapping chunk_id to ChunkState.
        """
        ...

    @abstractmethod
    async def clear_state(self, plan_id: str) -> None:
        """
        Remove persisted state (typically after successful completion).

        Args:
            plan_id: The plan identifier.
        """
        ...


# ============================================================================
# DEFAULT IMPLEMENTATIONS
# ============================================================================


class DefaultChunkExecutor(ChunkExecutor):
    """Default executor that runs a chunk via callback or dry-run mode.

    If no callback is provided, operates in a no-op mode that logs
    the chunk execution and returns success. This is useful for
    testing the orchestration logic without actual implementation.
    """

    def __init__(self, callback: Optional[Any] = None):
        """
        Initialize the default executor.

        Args:
            callback: Optional async callable with signature
                ``(chunk: DevelopmentChunk, context: dict) -> (bool, str)``.
                If None, operates in no-op mode.
        """
        self.callback = callback
        self.logger = logging.getLogger("startd8.development.executor")

    async def execute(
        self, chunk: DevelopmentChunk, context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Execute the chunk via callback or dry-run/no-op mode."""
        if context.get("dry_run", False):
            self.logger.debug(f"[DRY-RUN] Executing chunk {chunk.chunk_id}")
            return True, "Dry-run: implementation skipped"

        if self.callback is None:
            self.logger.debug(
                f"[NO-OP] No callback provided for {chunk.chunk_id}, returning success"
            )
            return True, "No callback: implementation logged"

        try:
            self.logger.debug(f"Executing chunk {chunk.chunk_id}")
            result = await self.callback(chunk, context)
            if not isinstance(result, tuple) or len(result) != 2:
                return False, (
                    f"Callback returned invalid result type: {type(result)}. "
                    "Expected Tuple[bool, str]."
                )
            return result
        except Exception as e:
            self.logger.exception(
                f"Unexpected error executing chunk {chunk.chunk_id}: {e}"
            )
            return False, f"Execution error: {str(e)}"


class LLMChunkExecutor(ChunkExecutor):
    """Chunk executor that generates code via LLM agents.

    Resolves agent specs to :class:`BaseAgent` instances and calls
    ``agent.agenerate(prompt)`` to produce code for each chunk.  Generated
    code is extracted from the LLM response, written to
    ``output_dir / <file_target>``, and returned to the orchestrator.

    Supports error-informed retry: when the orchestrator retries a failed
    chunk, prior error information (from :attr:`ChunkState.last_error` and
    :attr:`ChunkState.test_output`) is appended to the prompt so the LLM
    can self-correct.

    Cost tracking is surfaced through the execution context so that
    :class:`DevelopmentPhase` can aggregate it into
    :class:`DevelopmentResult`.

    Example::

        executor = LLMChunkExecutor(
            drafter_agent=DRAFT_MODEL_CLAUDE_HAIKU.agent_spec,
            output_dir=Path("generated/my-project"),
        )
        phase = DevelopmentPhase(executor=executor)
        result = await phase.run(plan)
        print(f"Total LLM cost: ${result.total_cost_usd:.4f}")
    """

    def __init__(
        self,
        drafter_agent: str = DRAFT_MODEL_CLAUDE_HAIKU.agent_spec,
        lead_agent: Optional[str] = None,
        output_dir: Optional[Path] = None,
        max_tokens: int = 64000,
    ):
        """
        Initialize the LLM chunk executor.

        Args:
            drafter_agent: Agent spec string for the implementation drafter.
                Defaults to ``DRAFT_MODEL_CLAUDE_HAIKU`` from the model catalog.
            lead_agent: Optional agent spec for review gating.  When set,
                generated code is sent to the lead agent for a quality
                review before being accepted.  If ``None``, no review
                gate is applied and the drafter output is used directly.
            output_dir: Directory for writing generated files.
                Defaults to ``Path("generated")``.
            max_tokens: ``max_tokens`` override passed to the provider
                when creating agents.  Defaults to 64 000 (suitable for
                large code generation).
        """
        self._drafter_spec = drafter_agent
        self._lead_spec = lead_agent
        self._output_dir = output_dir or Path("generated")
        self._max_tokens = max_tokens

        # Lazily resolved agent instances (cached after first call)
        self._drafter: Optional[Any] = None
        self._lead: Optional[Any] = None

        self.logger = logging.getLogger("startd8.development.llm_executor")

    # ------------------------------------------------------------------
    # Agent resolution (lazy, cached)
    # ------------------------------------------------------------------

    def _resolve_drafter(self) -> Any:
        """Resolve the drafter agent spec to a BaseAgent (cached)."""
        if self._drafter is not None:
            return self._drafter

        from startd8.utils.agent_resolution import resolve_agent_spec

        self.logger.info("Resolving drafter agent: %s", self._drafter_spec)
        self._drafter = resolve_agent_spec(
            self._drafter_spec,
            name="dev-drafter",
            max_tokens=self._max_tokens,
        )
        return self._drafter

    def _resolve_lead(self) -> Optional[Any]:
        """Resolve the lead agent spec to a BaseAgent (cached).

        Returns ``None`` if no lead agent was configured.
        """
        if self._lead_spec is None:
            return None
        if self._lead is not None:
            return self._lead

        from startd8.utils.agent_resolution import resolve_agent_spec

        self.logger.info("Resolving lead agent: %s", self._lead_spec)
        self._lead = resolve_agent_spec(
            self._lead_spec,
            name="dev-lead",
            max_tokens=self._max_tokens,
        )
        return self._lead

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        chunk: DevelopmentChunk,
        context: Dict[str, Any],
    ) -> str:
        """Assemble the full prompt for a chunk.

        Combines the chunk's ``implementation_prompt`` with contextual
        information injected by the orchestrator (domain constraints,
        project context, prior error feedback for retries).

        Args:
            chunk: The chunk to build a prompt for.
            context: Execution context (may contain ``domain_constraints``,
                ``project_context``, ``last_error``, ``test_output``).

        Returns:
            The assembled prompt string.
        """
        parts: List[str] = []

        # Primary implementation prompt
        parts.append(chunk.implementation_prompt)

        # Domain constraints (injected by DomainChecklist at line 1148)
        domain_constraints = context.get("domain_constraints")
        if domain_constraints:
            parts.append("\n## Domain Constraints")
            if isinstance(domain_constraints, list):
                for constraint in domain_constraints:
                    parts.append(f"- {constraint}")
            else:
                parts.append(str(domain_constraints))

        # Project-level context (file contents, design docs, etc.)
        project_context = context.get("project_context")
        if project_context:
            parts.append("\n## Project Context")
            parts.append(str(project_context))

        # File targets hint
        if chunk.file_targets:
            parts.append("\n## Target Files")
            for target in chunk.file_targets:
                parts.append(f"- {target}")

        # Error-informed retry feedback
        last_error = context.get("last_error")
        test_output = context.get("test_output")
        if last_error or test_output:
            parts.append("\n## Retry Feedback")
            parts.append(
                "The previous attempt failed. Please fix the issues "
                "and regenerate."
            )
            if last_error:
                parts.append(f"\nPrevious error:\n{last_error}")
            if test_output:
                parts.append(f"\nTest output:\n{test_output}")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # File writing
    # ------------------------------------------------------------------

    def _write_generated_files(
        self,
        code: str,
        chunk: DevelopmentChunk,
    ) -> List[Path]:
        """Write extracted code to the chunk's file targets.

        For multi-file chunks, splits the response into per-file blocks
        using :func:`extract_multi_file_code`.  Fails with ValueError if
        the split does not produce distinct content for every target file.

        Args:
            code: Extracted code from the LLM response.
            chunk: The chunk (for ``file_targets``).

        Returns:
            List of paths that were written.
        """
        written: List[Path] = []

        if not chunk.file_targets:
            # No explicit targets — write to a default file
            default_path = self._output_dir / f"{chunk.chunk_id}.py"
            default_path.parent.mkdir(parents=True, exist_ok=True)
            default_path.write_text(code, encoding="utf-8")
            written.append(default_path)
            return written

        # Multi-file splitting
        per_file_code: Dict[str, str] = {}
        if len(chunk.file_targets) > 1:
            from startd8.utils.code_extraction import (
                _generate_stub,
                extract_multi_file_code,
            )

            per_file_code = extract_multi_file_code(code, chunk.file_targets)
            if len(per_file_code) < len(chunk.file_targets):
                unmatched = [f for f in chunk.file_targets if f not in per_file_code]
                self.logger.warning(
                    "Multi-file split incomplete for chunk %s: matched %s but not %s. "
                    "Generating stubs for missing files.",
                    chunk.chunk_id,
                    list(per_file_code.keys()),
                    unmatched,
                )
                # Defense-in-depth: inject stubs directly into the existing
                # extraction results rather than re-parsing the full response.
                for missing_file in unmatched:
                    per_file_code[missing_file] = _generate_stub(missing_file)
                self.logger.warning(
                    "Multi-file stub recovery: auto-generated stubs for %s "
                    "(chunk %s). These are minimal placeholders — downstream "
                    "tasks or manual edits may be needed.",
                    unmatched,
                    chunk.chunk_id,
                )
                # Tag chunk metadata so downstream phases know stubs were used
                chunk.metadata.setdefault("_stubbed_files", []).extend(unmatched)

        for target in chunk.file_targets:
            output_path = self._output_dir / target
            output_path.parent.mkdir(parents=True, exist_ok=True)
            content = per_file_code.get(target, code)
            output_path.write_text(content, encoding="utf-8")
            written.append(output_path)
            self.logger.info("Wrote generated file: %s", output_path)

        return written

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(
        self, chunk: DevelopmentChunk, context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Execute the chunk by calling an LLM agent.

        Workflow:
        1. Resolve the drafter agent (lazy, cached).
        2. Inject retry feedback from ``ChunkState`` into context.
        3. Build the prompt from the chunk + context.
        4. Call ``agent.agenerate(prompt)`` for the LLM response.
        5. Extract code from the response.
        6. Write files to ``output_dir / file_target``.
        7. Accumulate cost/token metrics in context.
        8. Return ``(True, code)`` or ``(False, error)``.

        Args:
            chunk: The chunk to execute.
            context: Execution context (mutated to add cost metrics).

        Returns:
            ``(success, output_or_error)`` tuple.
        """
        # Dry-run short-circuit
        if context.get("dry_run", False):
            self.logger.debug("[DRY-RUN] LLM chunk %s", chunk.chunk_id)
            return True, "Dry-run: LLM execution skipped"

        try:
            # Resolve agent
            drafter = self._resolve_drafter()

            # Build prompt with retry feedback
            prompt = self._build_prompt(chunk, context)

            self.logger.info(
                "Generating code for chunk %s (%d file targets, prompt %d chars)",
                chunk.chunk_id,
                len(chunk.file_targets),
                len(prompt),
            )

            # Call the LLM
            response_text, time_ms, token_usage = await drafter.agenerate(prompt)

            self.logger.info(
                "Chunk %s: LLM responded in %dms (%d in / %d out tokens)",
                chunk.chunk_id,
                time_ms,
                token_usage.input,
                token_usage.output,
            )

            # Extract code from the response
            from startd8.utils.code_extraction import extract_code_from_response

            code = extract_code_from_response(response_text)

            if not code or not code.strip():
                return False, "LLM returned empty code after extraction"

            # Write generated files
            written_files = self._write_generated_files(code, chunk)

            # Accumulate cost metrics in context for DevelopmentPhase
            cost = token_usage.cost_estimate
            context["_llm_cost_usd"] = context.get("_llm_cost_usd", 0.0) + cost
            context["_llm_input_tokens"] = (
                context.get("_llm_input_tokens", 0) + token_usage.input
            )
            context["_llm_output_tokens"] = (
                context.get("_llm_output_tokens", 0) + token_usage.output
            )

            # Store per-chunk cost in metadata for detailed reporting
            chunk.metadata["llm_cost_usd"] = cost
            chunk.metadata["llm_input_tokens"] = token_usage.input
            chunk.metadata["llm_output_tokens"] = token_usage.output
            chunk.metadata["llm_time_ms"] = time_ms
            chunk.metadata["llm_model"] = getattr(drafter, "model", self._drafter_spec)
            chunk.metadata["generated_files"] = [str(p) for p in written_files]

            return True, code

        except Exception as e:
            self.logger.exception(
                "LLM execution failed for chunk %s: %s", chunk.chunk_id, e
            )
            return False, f"LLM execution error: {str(e)}"


class LeadContractorChunkExecutor(ChunkExecutor):
    """Chunk executor that wraps :class:`LeadContractorCodeGenerator`.

    Bridges the synchronous ``generator.generate()`` call into the async
    ``ChunkExecutor`` interface using ``run_in_executor``.  Stores the
    full :class:`GenerationResult` in ``chunk.metadata["_generation_result"]``
    so that downstream phases (TEST, REVIEW, FINALIZE) can access it after
    :class:`DevelopmentPhase` completes.

    Supports error-informed retry: when the orchestrator retries a failed
    chunk, prior error information is injected into the generation context
    so the LeadContractor can self-correct.

    Example::

        executor = LeadContractorChunkExecutor(
            lead_agent=VALIDATE_MODEL_CLAUDE_SONNET.agent_spec,
            drafter_agent=DRAFT_MODEL_CLAUDE_HAIKU.agent_spec,
            output_dir=Path("my-project"),
        )
        phase = DevelopmentPhase(executor=executor)
        result = await phase.run(plan)
    """

    #: Maximum bytes to read from an existing file before truncating.
    _MAX_EXISTING_FILE_BYTES: int = 60_000

    def __init__(
        self,
        lead_agent: str = VALIDATE_MODEL_CLAUDE_SONNET.agent_spec,
        drafter_agent: str = DRAFT_MODEL_CLAUDE_HAIKU.agent_spec,
        output_dir: Optional[Path] = None,
        max_iterations: int = 3,
        pass_threshold: int = 80,
        max_tokens: Optional[int] = None,
        fail_on_truncation: bool = True,
        check_truncation: bool = True,
        strict_truncation: bool = False,
    ):
        """
        Initialize the LeadContractor chunk executor.

        Args:
            lead_agent: Agent spec for architect/reviewer.
            drafter_agent: Agent spec for drafter.
            output_dir: Project root / output directory for generated files.
            max_iterations: Maximum draft → review iterations per task.
            pass_threshold: Minimum review score (0-100) to pass.
            max_tokens: Override max_tokens for agent creation.
            fail_on_truncation: Fail on detected truncation.
            check_truncation: Enable truncation detection.
            strict_truncation: Use strict detection threshold.
        """
        self._lead_agent = lead_agent
        self._drafter_agent = drafter_agent
        self._output_dir = output_dir or Path("generated")
        self._max_iterations = max_iterations
        self._pass_threshold = pass_threshold
        self._max_tokens = max_tokens
        self._fail_on_truncation = fail_on_truncation
        self._check_truncation = check_truncation
        self._strict_truncation = strict_truncation
        self._generator: Optional[Any] = None
        self.logger = logging.getLogger("startd8.development.lead_executor")

    # ------------------------------------------------------------------
    # Generator resolution (lazy, cached)
    # ------------------------------------------------------------------

    def _resolve_generator(self) -> Any:
        """Resolve or create the LeadContractorCodeGenerator (cached)."""
        if self._generator is not None:
            return self._generator

        from startd8.contractors.generators.lead_contractor import (
            LeadContractorCodeGenerator,
        )

        self.logger.info(
            "Creating LeadContractorCodeGenerator (lead=%s, drafter=%s)",
            self._lead_agent,
            self._drafter_agent,
        )
        self._generator = LeadContractorCodeGenerator(
            lead_agent=self._lead_agent,
            drafter_agent=self._drafter_agent,
            max_iterations=self._max_iterations,
            pass_threshold=self._pass_threshold,
            output_dir=self._output_dir,
            max_tokens=self._max_tokens,
            fail_on_truncation=self._fail_on_truncation,
            check_truncation=self._check_truncation,
            strict_truncation=self._strict_truncation,
        )
        return self._generator

    # ------------------------------------------------------------------
    # Context building
    # ------------------------------------------------------------------

    def _build_generation_context(
        self,
        chunk: DevelopmentChunk,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Assemble the context dict for ``generator.generate()``.

        Includes existing file contents, dependency outputs, prompt
        constraints, and retry feedback.

        Args:
            chunk: The chunk to build context for.
            context: Execution context from the orchestrator.

        Returns:
            Context dict suitable for ``CodeGenerator.generate()``.
        """
        meta = chunk.metadata
        gen_ctx: Dict[str, Any] = {
            "task_id": chunk.chunk_id,
            "feature_id": meta.get("feature_id", ""),
            "domain": meta.get("domain", "unknown"),
            "target_files": chunk.file_targets,
            "estimated_loc": meta.get("estimated_loc", 0),
            "prompt_constraints": meta.get("prompt_constraints", []),
            "environment_checks": meta.get("environment_checks", []),
            "project_root": str(self._output_dir),
        }
        # Per-task max_output_tokens from design_calibration (implement_max_output_tokens)
        mt = meta.get("max_output_tokens")
        if mt is not None:
            gen_ctx["max_tokens"] = mt

        # Read existing file contents for modify-in-place tasks
        for target in chunk.file_targets:
            target_path = self._output_dir / target
            if target_path.exists():
                try:
                    content = target_path.read_text(encoding="utf-8")
                    if len(content) > self._MAX_EXISTING_FILE_BYTES:
                        content = (
                            content[: self._MAX_EXISTING_FILE_BYTES]
                            + f"\n\n# ... truncated ({len(content)} bytes total)"
                        )
                    gen_ctx.setdefault("existing_files", {})[target] = content
                except (UnicodeDecodeError, OSError) as exc:
                    self.logger.warning(
                        "Could not read existing file %s: %s", target_path, exc,
                    )

        # Inject retry feedback from orchestrator context
        last_error = context.get("last_error")
        test_output = context.get("test_output")
        if last_error:
            gen_ctx["retry_feedback"] = {
                "last_error": last_error,
                "test_output": test_output,
            }

        # Inject domain constraints from DomainChecklist (if present)
        domain_constraints = context.get("domain_constraints")
        if domain_constraints:
            gen_ctx["domain_constraints"] = domain_constraints

        # Inject design document from DESIGN phase (if present in chunk metadata)
        design_doc = meta.get("design_document")
        if design_doc:
            gen_ctx["design_document"] = design_doc

        # Item 9: inject example artifacts for chunk's artifact_types_addressed
        all_examples = context.get("example_artifacts", {})
        artifact_types = meta.get("artifact_types_addressed", [])
        if all_examples and artifact_types:
            types_norm = {t.lower().replace("-", "_") for t in artifact_types}
            examples_for_chunk = {
                k: v for k, v in all_examples.items()
                if k.lower().replace("-", "_") in types_norm
            }
            if examples_for_chunk:
                gen_ctx["example_artifacts"] = examples_for_chunk

        return gen_ctx

    def _build_task_description(
        self,
        chunk: DevelopmentChunk,
        context: Dict[str, Any],
    ) -> str:
        """Build the task description string for ``generator.generate()``.

        Enriches the chunk description with the design document (if available),
        prompt constraints, and retry feedback for error-informed retries.

        Args:
            chunk: The chunk being executed.
            context: Execution context.

        Returns:
            Enriched task description string.
        """
        parts: List[str] = []

        # Prepend target file format hint so the drafter knows WHAT to generate
        # before reading the design doc (which may contain test examples).
        if chunk.file_targets:
            parts.append("## Target Files\n")
            parts.append(
                "You MUST generate the following file(s). Focus on implementing "
                "the PRIMARY artifact — do NOT generate test code.\n"
            )
            for target in chunk.file_targets:
                ext = target.rsplit(".", 1)[-1] if "." in target else ""
                fmt_hint = {
                    "yaml": "Valid YAML configuration",
                    "yml": "Valid YAML configuration",
                    "json": "Valid JSON",
                    "md": "Markdown document",
                    "py": "Python module",
                }.get(ext, "")
                parts.append(f"- `{target}`" + (f" ({fmt_hint})" if fmt_hint else ""))
            parts.append("\n---\n")

        # ── Layer 2: Authoritative design document framing ────────────
        # When a design document is present and substantial, make it the
        # AUTHORITATIVE specification and demote the task summary to a label.
        # This prevents the LLM from latching onto the shorter task
        # description and ignoring the comprehensive design.
        design_doc = chunk.metadata.get("design_document")
        if design_doc:
            design_lines = len(design_doc.strip().splitlines())
            design_sections = sum(
                1
                for line in design_doc.splitlines()
                if line.strip().startswith("##")
            )

            parts.append("## AUTHORITATIVE Design Document\n")
            parts.append(
                "The following design document was approved during the DESIGN phase. "
                "It is the AUTHORITATIVE specification for this task.\n"
            )
            parts.append(
                "**CRITICAL:** This design document OVERRIDES the Task Summary below "
                "when they differ in scope or detail. The Task Summary is only a brief "
                "label. The design document defines the FULL scope of what must be "
                "implemented — all sections, rules, structures, and patterns specified "
                "in the design MUST appear in your output.\n"
            )
            parts.append(
                f"**Design Scope:** {design_lines} lines across {design_sections} "
                f"sections. A partial implementation that omits designed sections "
                f"will be rejected in review.\n"
            )
            parts.append(design_doc)
            parts.append("\n---\n")
            parts.append(
                "## Task Summary (label only — see AUTHORITATIVE Design Document "
                "above for full scope)\n"
            )

        parts.append(chunk.description)

        # Append prompt constraints from enrichment
        constraints = chunk.metadata.get("prompt_constraints", [])
        if constraints:
            parts.append("\n## Constraints")
            for c in constraints:
                parts.append(f"- {c}")

        # Append retry feedback
        last_error = context.get("last_error")
        test_output = context.get("test_output")
        if last_error or test_output:
            parts.append("\n## Retry Feedback")
            parts.append(
                "The previous attempt failed. Please fix the issues "
                "and regenerate."
            )
            if last_error:
                parts.append(f"\nPrevious error:\n{last_error}")
            if test_output:
                parts.append(f"\nTest output:\n{test_output}")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Core execute
    # ------------------------------------------------------------------

    async def execute(
        self, chunk: DevelopmentChunk, context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Execute the chunk via LeadContractorCodeGenerator.

        Wraps the synchronous ``generator.generate()`` in a thread pool
        executor so it doesn't block the async event loop.

        Workflow:
        1. Build enriched task description and generation context.
        2. Resolve/create the generator (lazy, cached).
        3. Run ``generator.generate()`` via ``run_in_executor``.
        4. Store ``GenerationResult`` in ``chunk.metadata["_generation_result"]``.
        5. Accumulate cost/token metrics in context.
        6. Return ``(success, code_or_error)``.

        Args:
            chunk: The chunk to execute.
            context: Execution context (mutated to add cost metrics).

        Returns:
            ``(success, output_or_error)`` tuple.
        """
        # Dry-run short-circuit
        if context.get("dry_run", False):
            self.logger.debug("[DRY-RUN] LeadContractor chunk %s", chunk.chunk_id)
            return True, "Dry-run: LeadContractor execution skipped"

        try:
            generator = self._resolve_generator()
            task_desc = self._build_task_description(chunk, context)
            gen_ctx = self._build_generation_context(chunk, context)

            self.logger.info(
                "Generating code for chunk %s via LeadContractor (%d file targets)",
                chunk.chunk_id,
                len(chunk.file_targets),
            )

            # Run synchronous generator.generate() in thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                generator.generate,
                task_desc,
                gen_ctx,
                chunk.file_targets,
            )

            # Store full GenerationResult in chunk metadata for downstream phases
            chunk.metadata["_generation_result"] = result

            # Accumulate cost metrics in context for DevelopmentPhase
            context["_llm_cost_usd"] = (
                context.get("_llm_cost_usd", 0.0) + result.cost_usd
            )
            context["_llm_input_tokens"] = (
                context.get("_llm_input_tokens", 0) + result.input_tokens
            )
            context["_llm_output_tokens"] = (
                context.get("_llm_output_tokens", 0) + result.output_tokens
            )

            # Store per-chunk cost in metadata for detailed reporting
            chunk.metadata["llm_cost_usd"] = result.cost_usd
            chunk.metadata["llm_input_tokens"] = result.input_tokens
            chunk.metadata["llm_output_tokens"] = result.output_tokens
            chunk.metadata["llm_model"] = result.model
            chunk.metadata["iterations"] = result.iterations

            if result.success:
                # ── Layer 3: Post-generation scope validation ────────────
                design_doc = chunk.metadata.get("design_document")
                if design_doc and result.generated_files:
                    design_lines = len(design_doc.strip().splitlines())
                    total_output_lines = 0
                    for gen_file in result.generated_files:
                        try:
                            if gen_file.exists():
                                total_output_lines += len(
                                    gen_file.read_text(encoding="utf-8")
                                    .strip()
                                    .splitlines()
                                )
                        except (OSError, UnicodeDecodeError):
                            pass

                    scope_ratio = (
                        total_output_lines / design_lines
                        if design_lines > 0
                        else 1.0
                    )
                    if scope_ratio < 0.25 and total_output_lines < 100:
                        self.logger.warning(
                            "SCOPE MISMATCH: chunk %s output (%d lines) is %.0f%% "
                            "of design (%d lines) — possible partial implementation",
                            chunk.chunk_id,
                            total_output_lines,
                            scope_ratio * 100,
                            design_lines,
                        )
                        chunk.metadata["_scope_mismatch"] = {
                            "design_lines": design_lines,
                            "output_lines": total_output_lines,
                            "ratio": round(scope_ratio, 2),
                        }

                self.logger.info(
                    "Chunk %s: generation succeeded (%d files, $%.4f, %d iterations)",
                    chunk.chunk_id,
                    len(result.generated_files),
                    result.cost_usd,
                    result.iterations,
                )
                # Return a summary as the "code" output
                file_list = ", ".join(str(f) for f in result.generated_files)
                return True, f"Generated files: {file_list}"
            else:
                self.logger.warning(
                    "Chunk %s: generation failed: %s",
                    chunk.chunk_id,
                    result.error,
                )
                return False, result.error or "Generation failed"

        except Exception as e:
            self.logger.exception(
                "LeadContractor execution failed for chunk %s: %s",
                chunk.chunk_id,
                e,
            )
            return False, f"LeadContractor execution error: {str(e)}"


class DefaultTestRunner(TestRunner):
    """Default test runner that executes shell commands via subprocess.

    Each test command is run sequentially. If any command fails
    (non-zero exit code) or times out, the entire test suite for
    the chunk is considered failed.
    """

    def __init__(self, timeout: int = 300):
        """
        Initialize the default test runner.

        Args:
            timeout: Timeout in seconds for each individual test command.
        """
        self.timeout = timeout
        self.logger = logging.getLogger("startd8.development.tests")

    async def run_tests(
        self, chunk: DevelopmentChunk, context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Run all test commands for a chunk sequentially."""
        if context.get("dry_run", False):
            self.logger.debug(f"[DRY-RUN] Testing chunk {chunk.chunk_id}")
            return True, "Dry-run: tests skipped"

        if not chunk.test_commands:
            self.logger.debug(f"No test commands for {chunk.chunk_id}")
            return True, "No tests configured"

        output_lines: List[str] = []
        for i, cmd in enumerate(chunk.test_commands, 1):
            try:
                self.logger.debug(
                    f"Running test {i}/{len(chunk.test_commands)} "
                    f"for {chunk.chunk_id}: {cmd}"
                )
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=self.timeout
                    )
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    return False, (f"Test timeout after {self.timeout}s: {cmd}")

                stdout_text = stdout.decode(errors="replace")
                stderr_text = stderr.decode(errors="replace")

                if proc.returncode != 0:
                    return (
                        False,
                        f"Test failed (exit {proc.returncode}): {cmd}\n"
                        f"stdout: {stdout_text}\n"
                        f"stderr: {stderr_text}",
                    )

                output_lines.append(stdout_text)

            except FileNotFoundError:
                return False, f"Test command not found: {cmd}"
            except Exception as e:
                self.logger.exception(
                    f"Unexpected error running test for {chunk.chunk_id}: {e}"
                )
                return False, f"Test error: {str(e)}"

        return True, "\n".join(output_lines)


class JsonFileStateStore(StateStore):
    """Persists chunk execution state to JSON files on disk.

    Uses atomic writes (write to temp file, then ``os.replace``) to
    prevent corruption from crashes during save operations.

    State files are named ``{plan_id}_state.json`` within the
    configured directory.
    """

    def __init__(self, directory: str = ".startd8/state"):
        """
        Initialize the JSON file state store.

        Args:
            directory: Directory to store state files. Created if needed.
                Defaults to ``.startd8/state``.  The legacy
                ``.startd8_state`` directory is checked on read when
                the primary directory has no matching file.
        """
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        # Legacy fallback: check the old location when reading state
        self._legacy_directory = Path(
            str(directory).replace(".startd8/state", ".startd8_state")
        ) if ".startd8/state" in str(directory) else None
        self.logger = logging.getLogger("startd8.development.state")

    def _get_state_path(self, plan_id: str) -> Path:
        """Get the file path for a plan's state."""
        # Sanitize plan_id for safe filesystem use
        safe_id = "".join(c if c.isalnum() or c in "-_." else "_" for c in plan_id)
        return self.directory / f"{safe_id}_state.json"

    async def load_state(self, plan_id: str) -> Dict[str, ChunkState]:
        """Load state from a JSON file.

        Falls back to the legacy ``.startd8_state/`` directory if the
        primary path does not exist.
        """
        state_path = self._get_state_path(plan_id)

        if not state_path.exists() and self._legacy_directory:
            safe_id = "".join(c if c.isalnum() or c in "-_." else "_" for c in plan_id)
            legacy_path = self._legacy_directory / f"{safe_id}_state.json"
            if legacy_path.exists():
                self.logger.info(
                    "Migrating state from legacy %s → %s", legacy_path, state_path,
                )
                state_path = legacy_path

        if not state_path.exists():
            self.logger.debug(f"No persisted state found for plan {plan_id}")
            return {}

        try:
            with open(state_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            states: Dict[str, ChunkState] = {}
            for chunk_id, chunk_data in data.items():
                states[chunk_id] = ChunkState(
                    chunk_id=chunk_data["chunk_id"],
                    status=ChunkStatus(chunk_data["status"]),
                    attempts=chunk_data.get("attempts", 0),
                    last_error=chunk_data.get("last_error"),
                    started_at=chunk_data.get("started_at"),
                    completed_at=chunk_data.get("completed_at"),
                    test_output=chunk_data.get("test_output"),
                )

            self.logger.debug(
                f"Loaded state for plan {plan_id}: {len(states)} chunk(s)"
            )
            return states

        except json.JSONDecodeError as e:
            self.logger.warning(
                f"Corrupted state file for plan {plan_id}: {e}. Starting fresh."
            )
            return {}
        except (KeyError, ValueError) as e:
            self.logger.warning(
                f"Invalid state data for plan {plan_id}: {e}. Starting fresh."
            )
            return {}
        except Exception as e:
            self.logger.error(f"Error loading state for plan {plan_id}: {e}")
            return {}

    async def save_state(self, plan_id: str, states: Dict[str, ChunkState]) -> None:
        """Save state to a JSON file atomically."""
        state_path = self._get_state_path(plan_id)

        data: Dict[str, Any] = {}
        for chunk_id, state in states.items():
            data[chunk_id] = {
                "chunk_id": state.chunk_id,
                "status": state.status.value,
                "attempts": state.attempts,
                "last_error": state.last_error,
                "started_at": state.started_at,
                "completed_at": state.completed_at,
                "test_output": state.test_output,
            }

        tmp_path: Optional[str] = None
        try:
            with NamedTemporaryFile(
                mode="w",
                dir=str(self.directory),
                delete=False,
                suffix=".json.tmp",
                encoding="utf-8",
            ) as tmp:
                tmp_path = tmp.name
                json.dump(data, tmp, indent=2, ensure_ascii=False)
                tmp.flush()
                os.fsync(tmp.fileno())

            os.replace(tmp_path, state_path)
            tmp_path = None  # Prevent cleanup after successful replace
            self.logger.debug(f"Saved state for plan {plan_id}")

        except Exception as e:
            self.logger.error(f"Error saving state for plan {plan_id}: {e}")
            raise
        finally:
            if tmp_path is not None and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    async def clear_state(self, plan_id: str) -> None:
        """Remove persisted state file."""
        state_path = self._get_state_path(plan_id)
        try:
            if state_path.exists():
                state_path.unlink()
                self.logger.debug(f"Cleared state for plan {plan_id}")
        except Exception as e:
            self.logger.error(f"Error clearing state for plan {plan_id}: {e}")


# ============================================================================
# VALIDATION AND SORTING
# ============================================================================


def validate_plan(plan: DevelopmentPlan) -> List[str]:
    """
    Validate a development plan for structural correctness.

    Checks performed:
    1. No empty chunk_ids
    2. No duplicate chunk_ids
    3. No self-dependencies
    4. All dependencies reference existing chunks
    5. No cyclic dependencies (via DFS)
    6. Plan has a valid plan_id

    Args:
        plan: The development plan to validate.

    Returns:
        List of error messages. Empty list means the plan is valid.
    """
    errors: List[str] = []

    # Check plan_id
    if not plan.plan_id or not plan.plan_id.strip():
        errors.append("Plan has empty or whitespace-only plan_id")

    chunk_ids_seen: Set[str] = set()

    # Check for duplicates and empty IDs
    for chunk in plan.chunks:
        if not chunk.chunk_id or not chunk.chunk_id.strip():
            errors.append("Chunk has empty chunk_id")
        elif chunk.chunk_id in chunk_ids_seen:
            errors.append(f"Duplicate chunk_id: {chunk.chunk_id}")
        chunk_ids_seen.add(chunk.chunk_id)

    # Check for self-dependencies
    for chunk in plan.chunks:
        if chunk.chunk_id in chunk.dependencies:
            errors.append(f"Chunk {chunk.chunk_id} depends on itself")

    # Check for missing dependencies
    for chunk in plan.chunks:
        for dep in chunk.dependencies:
            if dep not in chunk_ids_seen:
                errors.append(
                    f"Chunk {chunk.chunk_id} depends on non-existent chunk {dep}"
                )

    # Check for cycles using DFS (only if no structural errors found)
    if not errors:
        adj_list: Dict[str, List[str]] = defaultdict(list)
        for chunk in plan.chunks:
            for dep in chunk.dependencies:
                adj_list[dep].append(chunk.chunk_id)

        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def _has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)

            for neighbor in adj_list[node]:
                if neighbor not in visited:
                    if _has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.discard(node)
            return False

        for chunk_id in chunk_ids_seen:
            if chunk_id not in visited:
                if _has_cycle(chunk_id):
                    errors.append("Cyclic dependency detected in chunk graph")
                    break

    return errors


def topological_sort(chunks: List[DevelopmentChunk]) -> List[List[str]]:
    """
    Topological sort using Kahn's algorithm (BFS-based).

    Returns chunks organized into "tiers" where all chunks in the same
    tier have their dependencies satisfied by previous tiers, enabling
    parallel execution within each tier.

    Example:
        Given A -> B -> D and A -> C -> D:
        - Tier 0: [A]
        - Tier 1: [B, C]  (can run in parallel)
        - Tier 2: [D]

    Args:
        chunks: List of development chunks to sort.

    Returns:
        List of tiers, where each tier is a list of chunk_ids.

    Raises:
        MissingDependencyError: If a chunk references a non-existent dependency.
        CyclicDependencyError: If dependencies contain a cycle.
    """
    if not chunks:
        return []

    chunk_map = {c.chunk_id: c for c in chunks}
    in_degree: Dict[str, int] = {c.chunk_id: 0 for c in chunks}
    adj_list: Dict[str, List[str]] = defaultdict(list)

    for chunk in chunks:
        for dep in chunk.dependencies:
            if dep not in chunk_map:
                raise MissingDependencyError(
                    f"Chunk {chunk.chunk_id} depends on non-existent chunk {dep}"
                )
            adj_list[dep].append(chunk.chunk_id)
            in_degree[chunk.chunk_id] += 1

    # Start with all zero-in-degree nodes
    queue = deque(sorted(cid for cid in chunk_map if in_degree[cid] == 0))
    tiers: List[List[str]] = []
    processed_count = 0

    while queue:
        tier = sorted(queue)  # Sort for deterministic ordering
        tiers.append(tier)
        processed_count += len(tier)

        next_queue: deque[str] = deque()
        for chunk_id in tier:
            for neighbor in adj_list[chunk_id]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    next_queue.append(neighbor)

        queue = next_queue

    # If we didn't process all nodes, there's a cycle
    if processed_count != len(chunks):
        remaining = [cid for cid, deg in in_degree.items() if deg > 0]
        raise CyclicDependencyError(
            f"Cyclic dependency detected involving chunks: "
            f"{', '.join(sorted(remaining))}"
        )

    return tiers


# ============================================================================
# MAIN DEVELOPMENT PHASE CLASS
# ============================================================================


class DevelopmentPhase:
    """
    Orchestrates the iterative development phase.

    Manages chunk execution in dependency order with:
    - State persistence for crash recovery and resume
    - Test gating (chunks must pass tests to be considered complete)
    - Configurable retry logic per chunk
    - Bounded parallel execution within dependency tiers

    Lifecycle:
        1. Validate the plan
        2. Compute topological sort into tiers
        3. Load persisted state (for resume)
        4. For each tier:
           a. Determine eligible chunks (deps satisfied, not already passed)
           b. Execute eligible chunks concurrently (bounded)
           c. Propagate skips for failed dependencies
           d. Persist state
        5. Build and return result
    """

    def __init__(
        self,
        executor: Optional[ChunkExecutor] = None,
        test_runner: Optional[TestRunner] = None,
        state_store: Optional[StateStore] = None,
        max_parallel: int = 4,
        logger: Optional[logging.Logger] = None,
        domain_checklist: Optional[Any] = None,
    ):
        """
        Initialize the development phase.

        Args:
            executor: Chunk executor implementation.
                Default: DefaultChunkExecutor (no-op mode).
            test_runner: Test runner implementation.
                Default: DefaultTestRunner (shell commands).
            state_store: State storage backend.
                Default: JsonFileStateStore (".startd8/state" directory).
            max_parallel: Maximum concurrent chunk executions per tier.
                Must be >= 1.
            logger: Logger instance.
                Default: logging.getLogger("startd8.development").
            domain_checklist: Optional DomainChecklist instance for injecting
                domain-aware prompt constraints into chunk execution context.
        """
        if max_parallel < 1:
            raise ValueError("max_parallel must be >= 1")

        self.executor = executor or DefaultChunkExecutor()
        self.test_runner = test_runner or DefaultTestRunner()
        self.state_store = state_store or JsonFileStateStore()
        self.max_parallel = max_parallel
        self.logger = logger or logging.getLogger("startd8.development")
        self.domain_checklist = domain_checklist

    async def run(self, plan: DevelopmentPlan) -> DevelopmentResult:
        """
        Execute the full development phase.

        This is the main entry point. It validates the plan, resolves
        dependencies, loads any persisted state for resume, executes
        chunks tier by tier, and returns a comprehensive result.

        Args:
            plan: The development plan to execute.

        Returns:
            DevelopmentResult with execution outcomes.

        Raises:
            PlanValidationError: If the plan fails validation.
            CyclicDependencyError: If chunk dependencies contain a cycle.
            MissingDependencyError: If a dependency references a missing chunk.
        """
        start_time = datetime.now(timezone.utc)

        # --- Validate plan ---
        validation_errors = validate_plan(plan)
        if validation_errors:
            raise PlanValidationError(validation_errors)

        self.logger.info(
            f"Starting development phase for plan '{plan.plan_id}' "
            f"with {len(plan.chunks)} chunk(s)"
        )

        # --- Handle empty plan ---
        if not plan.chunks:
            self.logger.info("Plan has no chunks; returning success")
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            return DevelopmentResult(
                plan_id=plan.plan_id,
                success=True,
                chunk_states={},
                execution_order=[],
                total_duration_seconds=duration,
                summary="Empty plan; no chunks to execute.",
            )

        # --- Resolve dependency order ---
        execution_order = topological_sort(plan.chunks)
        self.logger.info(
            f"Topological sort produced {len(execution_order)} tier(s): "
            f"{[len(t) for t in execution_order]} chunks per tier"
        )

        # --- Load persisted state for resume ---
        persisted_states = await self.state_store.load_state(plan.plan_id)
        if persisted_states:
            self.logger.info(
                f"Resuming: loaded {len(persisted_states)} chunk state(s) "
                f"from previous run"
            )
        else:
            self.logger.debug("No prior state found; starting fresh")

        # --- Initialize states ---
        states = self._initialize_states(plan, persisted_states)

        # --- Build lookup and context ---
        chunk_map = {c.chunk_id: c for c in plan.chunks}
        max_parallel = plan.config.get("max_parallel", self.max_parallel)
        phase_started_mono = time.monotonic()
        context: Dict[str, Any] = {
            "plan_id": plan.plan_id,
            "dry_run": plan.config.get("dry_run", False),
            "example_artifacts": plan.config.get("example_artifacts", {}),
            "_dev_phase_started_mono": phase_started_mono,
        }

        # --- Execute tiers ---
        for tier_idx, tier_chunk_ids in enumerate(execution_order):
            self.logger.info(
                f"=== Tier {tier_idx + 1}/{len(execution_order)}: {tier_chunk_ids} ==="
            )

            states = await self._execute_tier(
                tier_chunk_ids, chunk_map, states, context, max_parallel
            )

            # Propagate SKIPPED to dependents of failed/skipped chunks
            self._propagate_skips(states, plan.chunks)

            # Persist state after each tier for crash recovery
            await self.state_store.save_state(plan.plan_id, states)

        # --- Build result ---
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        result = self._build_result(plan, states, execution_order, duration)

        self.logger.info(
            f"Development phase completed: success={result.success}, "
            f"duration={duration:.2f}s"
        )
        self.logger.info(f"Summary: {result.summary}")

        # Clear persisted state if fully successful
        if result.success:
            await self.state_store.clear_state(plan.plan_id)
            self.logger.debug("Cleared persisted state after success")

        return result

    def _initialize_states(
        self,
        plan: DevelopmentPlan,
        persisted_states: Dict[str, ChunkState],
    ) -> Dict[str, ChunkState]:
        """
        Initialize chunk states, handling resume scenarios.

        Resume policy:
        - PASSED: preserved (don't re-execute successful chunks)
        - RUNNING, TESTING: reset to PENDING (interrupted mid-execution)
        - FAILED: reset to PENDING (allow fresh retry)
        - SKIPPED: reset to PENDING (dependency may now be satisfied)
        - PENDING, QUEUED: reset to PENDING

        Args:
            plan: The development plan.
            persisted_states: Previously saved states from state store.

        Returns:
            Dictionary of chunk states ready for execution.
        """
        states: Dict[str, ChunkState] = {}

        for chunk in plan.chunks:
            cid = chunk.chunk_id

            if cid in persisted_states:
                prev = persisted_states[cid]

                if prev.status == ChunkStatus.PASSED:
                    # Keep — don't re-execute successful chunks
                    states[cid] = prev
                    self.logger.debug(f"Chunk {cid}: already PASSED, preserving")
                elif prev.status in (
                    ChunkStatus.RUNNING,
                    ChunkStatus.TESTING,
                ):
                    # Interrupted mid-execution — reset fully
                    states[cid] = ChunkState(
                        chunk_id=cid,
                        status=ChunkStatus.PENDING,
                    )
                    self.logger.debug(
                        f"Chunk {cid}: was {prev.status.value} "
                        "(interrupted), resetting to PENDING"
                    )
                elif prev.status == ChunkStatus.FAILED:
                    # Allow retry on failed chunks
                    states[cid] = ChunkState(
                        chunk_id=cid,
                        status=ChunkStatus.PENDING,
                    )
                    self.logger.debug(
                        f"Chunk {cid}: was FAILED, resetting to PENDING for retry"
                    )
                elif prev.status == ChunkStatus.SKIPPED:
                    # Reset skipped — dependency might succeed this time
                    states[cid] = ChunkState(
                        chunk_id=cid,
                        status=ChunkStatus.PENDING,
                    )
                    self.logger.debug(f"Chunk {cid}: was SKIPPED, resetting to PENDING")
                else:
                    # PENDING, QUEUED — reset cleanly
                    states[cid] = ChunkState(
                        chunk_id=cid,
                        status=ChunkStatus.PENDING,
                    )
            else:
                # New chunk
                states[cid] = ChunkState(
                    chunk_id=cid,
                    status=ChunkStatus.PENDING,
                )

        return states

    async def _execute_tier(
        self,
        tier_chunk_ids: List[str],
        chunk_map: Dict[str, DevelopmentChunk],
        states: Dict[str, ChunkState],
        context: Dict[str, Any],
        max_parallel: int,
    ) -> Dict[str, ChunkState]:
        """
        Execute all eligible chunks in a tier concurrently.

        Chunks are eligible if:
        - Status is PENDING (not already PASSED or SKIPPED)
        - All dependencies have PASSED

        Concurrency is bounded by ``max_parallel`` via a semaphore.

        Args:
            tier_chunk_ids: Chunk IDs in this tier.
            chunk_map: Mapping of chunk_id to DevelopmentChunk.
            states: Current execution states (mutated in place).
            context: Execution context.
            max_parallel: Maximum concurrent executions.

        Returns:
            Updated states dictionary.
        """
        eligible: List[str] = []

        for chunk_id in tier_chunk_ids:
            state = states[chunk_id]

            if state.status == ChunkStatus.PASSED:
                self.logger.debug(f"Chunk {chunk_id}: already PASSED, skip")
                continue

            if state.status == ChunkStatus.SKIPPED:
                self.logger.debug(f"Chunk {chunk_id}: already SKIPPED, skip")
                continue

            # Verify all dependencies have PASSED
            chunk = chunk_map[chunk_id]
            unsatisfied = [
                dep
                for dep in chunk.dependencies
                if states[dep].status != ChunkStatus.PASSED
            ]

            if unsatisfied:
                self.logger.warning(
                    f"Chunk {chunk_id}: unsatisfied dependencies "
                    f"{unsatisfied}; marking SKIPPED"
                )
                states[chunk_id].status = ChunkStatus.SKIPPED
                states[
                    chunk_id
                ].last_error = f"Unsatisfied dependencies: {', '.join(unsatisfied)}"
                states[chunk_id].completed_at = datetime.now(timezone.utc).isoformat()
                continue

            eligible.append(chunk_id)

        if not eligible:
            self.logger.debug("No eligible chunks in this tier")
            return states

        self.logger.info(
            f"Executing {len(eligible)} eligible chunk(s) (max_parallel={max_parallel})"
        )
        previous_chunk_queued_mono: Optional[float] = None
        phase_started_mono = context.get("_dev_phase_started_mono")
        for idx, cid in enumerate(eligible, start=1):
            now = time.monotonic()
            elapsed_s = (
                now - phase_started_mono
                if isinstance(phase_started_mono, (int, float))
                else 0.0
            )
            elapsed_m = elapsed_s / 60.0
            delta_s = (
                0.0
                if previous_chunk_queued_mono is None
                else now - previous_chunk_queued_mono
            )
            self.logger.info(
                "IMPLEMENT chunk %d/%d queued: %s (elapsed %.1fs / %.2fmin, +%.1fs since previous chunk)",
                idx,
                len(eligible),
                cid,
                elapsed_s,
                elapsed_m,
                delta_s,
            )
            previous_chunk_queued_mono = now

        semaphore = asyncio.Semaphore(max_parallel)

        async def _run_with_semaphore(cid: str) -> None:
            async with semaphore:
                chunk = chunk_map[cid]
                state = states[cid]
                chunk_context = dict(context)  # Per-chunk copy to avoid race conditions
                states[cid] = await self._execute_chunk(chunk, state, chunk_context)

        await asyncio.gather(*[_run_with_semaphore(cid) for cid in eligible])

        return states

    async def _execute_chunk(
        self,
        chunk: DevelopmentChunk,
        state: ChunkState,
        context: Dict[str, Any],
    ) -> ChunkState:
        """
        Execute a single chunk with retry logic and test gating.

        Execution flow per attempt:
        1. Mark QUEUED -> RUNNING
        2. Call executor.execute()
        3. If execution fails, retry (if attempts remain)
        4. Mark TESTING
        5. Call test_runner.run_tests()
        6. If tests fail, retry (if attempts remain)
        7. If both pass, mark PASSED

        Total attempts = max_retries + 1.

        Args:
            chunk: The chunk to execute.
            state: Current state (will be mutated and returned).
            context: Execution context.

        Returns:
            Updated ChunkState.
        """
        max_attempts = chunk.max_retries + 1

        while state.attempts < max_attempts:
            state.attempts += 1
            attempt_label = f"{state.attempts}/{max_attempts}"
            phase_started_mono = context.get("_dev_phase_started_mono")
            elapsed_s = (
                time.monotonic() - phase_started_mono
                if isinstance(phase_started_mono, (int, float))
                else 0.0
            )
            elapsed_m = elapsed_s / 60.0
            self.logger.info(
                "Chunk %s: attempt %s (phase elapsed %.1fs / %.2fmin)",
                chunk.chunk_id,
                attempt_label,
                elapsed_s,
                elapsed_m,
            )

            # --- QUEUED ---
            state.status = ChunkStatus.QUEUED
            state.started_at = datetime.now(timezone.utc).isoformat()

            # --- Domain pre-flight: inject constraints if checklist is configured ---
            if self.domain_checklist is not None:
                try:
                    enrichment = self.domain_checklist.get_enrichment(
                        chunk.chunk_id, chunk.file_targets
                    )
                    if enrichment is not None:
                        context["domain_constraints"] = enrichment.prompt_constraints
                        context["domain"] = enrichment.domain.value
                        context["post_generation_validators"] = enrichment.post_generation_validators
                        self.logger.info(
                            "Chunk %s: domain=%s, %d constraints injected",
                            chunk.chunk_id, enrichment.domain.value,
                            len(enrichment.prompt_constraints),
                        )
                        # --- WCP-003: Track propagation provenance ---
                        try:
                            from contextcore.contracts.propagation import (
                                PropagationTracker,
                                emit_boundary_result,
                            )
                            _tracker = PropagationTracker()
                            _tracker.stamp(context, "implement", "domain_constraints", enrichment.prompt_constraints)
                            _tracker.stamp(context, "implement", "domain", enrichment.domain.value)
                        except ImportError:
                            # Fallback: emit inline span event if contextcore not available
                            try:
                                from opentelemetry import trace
                                span = trace.get_current_span()
                                if span and span.is_recording():
                                    span.add_event("context.propagated", attributes={
                                        "context.field": "domain_constraints",
                                        "context.value": enrichment.domain.value,
                                        "context.source_phase": "domain_checklist",
                                        "context.target_phase": "implement",
                                        "context.task_id": chunk.chunk_id,
                                        "context.constraint_count": len(enrichment.prompt_constraints),
                                    })
                            except Exception:
                                pass  # OTel not available — non-fatal
                        except Exception:
                            pass  # Non-fatal
                except Exception as e:
                    self.logger.warning(
                        "Chunk %s: domain checklist failed (non-fatal): %s",
                        chunk.chunk_id, e,
                    )

            # --- Inject retry feedback for error-informed retries ---
            if state.attempts > 1 and state.last_error:
                context["last_error"] = state.last_error
                if state.test_output:
                    context["test_output"] = state.test_output
                self.logger.debug(
                    "Chunk %s: injecting retry feedback (attempt %s)",
                    chunk.chunk_id, attempt_label,
                )
            else:
                # Clear stale feedback from prior chunks sharing this context
                context.pop("last_error", None)
                context.pop("test_output", None)

            # --- RUNNING: Execute implementation ---
            state.status = ChunkStatus.RUNNING
            try:
                exec_success, exec_output = await self.executor.execute(chunk, context)
                if not exec_success:
                    self.logger.warning(
                        f"Chunk {chunk.chunk_id}: execution failed "
                        f"(attempt {attempt_label}): {exec_output}"
                    )
                    state.last_error = exec_output
                    continue

                self.logger.debug(f"Chunk {chunk.chunk_id}: execution succeeded")

                # Advisory post-generation validation
                if (self.domain_checklist is not None
                        and "post_generation_validators" in context):
                    try:
                        from .domain_checklist import validate_generated_code
                        enrichment = self.domain_checklist.get_enrichment(
                            chunk.chunk_id, chunk.file_targets
                        )
                        if enrichment is not None:
                            result = validate_generated_code(exec_output, enrichment)
                            if not result.passed:
                                for issue in result.issues:
                                    self.logger.warning(
                                        "Chunk %s: post-gen %s: %s (line %s)",
                                        chunk.chunk_id, issue.validator,
                                        issue.message, issue.line,
                                    )
                    except Exception as e:
                        self.logger.debug("Post-validation skipped: %s", e)

            except Exception as e:
                self.logger.exception(
                    f"Chunk {chunk.chunk_id}: unexpected execution error: {e}"
                )
                state.last_error = f"Execution exception: {str(e)}"
                continue

            # --- TESTING: Run test gate ---
            state.status = ChunkStatus.TESTING
            try:
                tests_passed, test_output = await self.test_runner.run_tests(
                    chunk, context
                )
                state.test_output = test_output

                if not tests_passed:
                    self.logger.warning(
                        f"Chunk {chunk.chunk_id}: tests failed "
                        f"(attempt {attempt_label}): {test_output}"
                    )
                    state.last_error = f"Tests failed: {test_output}"
                    continue

                self.logger.info(f"Chunk {chunk.chunk_id}: tests passed")

            except Exception as e:
                self.logger.exception(
                    f"Chunk {chunk.chunk_id}: unexpected test error: {e}"
                )
                state.last_error = f"Test exception: {str(e)}"
                continue

            # --- PASSED ---
            state.status = ChunkStatus.PASSED
            state.completed_at = datetime.now(timezone.utc).isoformat()
            self.logger.info(
                f"Chunk {chunk.chunk_id}: PASSED (attempt {attempt_label})"
            )
            return state

        # All retries exhausted
        state.status = ChunkStatus.FAILED
        state.completed_at = datetime.now(timezone.utc).isoformat()
        self.logger.error(
            f"Chunk {chunk.chunk_id}: FAILED after {state.attempts} "
            f"attempt(s). Last error: {state.last_error}"
        )
        return state

    def _propagate_skips(
        self,
        states: Dict[str, ChunkState],
        chunks: List[DevelopmentChunk],
    ) -> None:
        """
        Transitively propagate SKIPPED status to dependents of failed chunks.

        Any PENDING chunk whose dependency chain includes a FAILED or
        SKIPPED chunk is marked SKIPPED. Uses iterative propagation
        until a fixed point is reached.

        Args:
            states: Current chunk states (mutated in place).
            chunks: All chunks in the plan.
        """
        changed = True
        while changed:
            changed = False

            for chunk in chunks:
                state = states[chunk.chunk_id]

                # Only propagate to chunks still PENDING
                if state.status != ChunkStatus.PENDING:
                    continue

                for dep_id in chunk.dependencies:
                    dep_state = states[dep_id]
                    if dep_state.status in (
                        ChunkStatus.FAILED,
                        ChunkStatus.SKIPPED,
                    ):
                        state.status = ChunkStatus.SKIPPED
                        state.last_error = (
                            f"Skipped: dependency '{dep_id}' is "
                            f"{dep_state.status.value}"
                        )
                        state.completed_at = datetime.now(timezone.utc).isoformat()
                        self.logger.info(
                            f"Chunk {chunk.chunk_id}: SKIPPED due to "
                            f"dependency '{dep_id}' ({dep_state.status.value})"
                        )
                        changed = True
                        break

    def _build_result(
        self,
        plan: DevelopmentPlan,
        states: Dict[str, ChunkState],
        execution_order: List[List[str]],
        duration: float,
    ) -> DevelopmentResult:
        """
        Build the final DevelopmentResult.

        Success is True only if every chunk reached PASSED status.
        Aggregates LLM cost and token metrics from chunk metadata
        (populated by :class:`LLMChunkExecutor`).

        Args:
            plan: The development plan.
            states: Final chunk states.
            execution_order: Execution tiers from topological sort.
            duration: Total wall-clock execution time in seconds.

        Returns:
            DevelopmentResult instance.
        """
        passed = sum(1 for s in states.values() if s.status == ChunkStatus.PASSED)
        failed = sum(1 for s in states.values() if s.status == ChunkStatus.FAILED)
        skipped = sum(1 for s in states.values() if s.status == ChunkStatus.SKIPPED)
        total = len(states)

        success = (total > 0 and passed == total) or total == 0

        # Aggregate LLM costs from chunk metadata
        total_cost_usd = 0.0
        total_input_tokens = 0
        total_output_tokens = 0
        for chunk in plan.chunks:
            total_cost_usd += chunk.metadata.get("llm_cost_usd", 0.0)
            total_input_tokens += chunk.metadata.get("llm_input_tokens", 0)
            total_output_tokens += chunk.metadata.get("llm_output_tokens", 0)

        # Build detailed summary
        summary_parts = [
            f"Executed {total} chunk(s): "
            f"{passed} passed, {failed} failed, {skipped} skipped.",
            f"Duration: {duration:.2f}s.",
        ]

        if total_cost_usd > 0:
            summary_parts.append(f"LLM cost: ${total_cost_usd:.4f}.")

        if failed > 0:
            failed_ids = [
                cid for cid, s in states.items() if s.status == ChunkStatus.FAILED
            ]
            summary_parts.append(f"Failed chunks: {', '.join(failed_ids)}.")

        summary = " ".join(summary_parts)

        return DevelopmentResult(
            plan_id=plan.plan_id,
            success=success,
            chunk_states=states,
            execution_order=execution_order,
            total_duration_seconds=duration,
            summary=summary,
            total_cost_usd=total_cost_usd,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
        )


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================


async def run_development_phase(
    plan: DevelopmentPlan,
    executor: Optional[ChunkExecutor] = None,
    test_runner: Optional[TestRunner] = None,
    state_store: Optional[StateStore] = None,
    max_parallel: int = 4,
    domain_checklist: Optional[Any] = None,
) -> DevelopmentResult:
    """
    Convenience function to execute a development phase.

    Creates a ``DevelopmentPhase`` instance with the given parameters
    and runs the plan. Suitable for simple use cases where you don't
    need to reuse the phase instance.

    Args:
        plan: The development plan to execute.
        executor: Chunk executor (optional; defaults to DefaultChunkExecutor).
        test_runner: Test runner (optional; defaults to DefaultTestRunner).
        state_store: State storage (optional; defaults to JsonFileStateStore).
        max_parallel: Maximum concurrent chunk executions (default: 4).
        domain_checklist: Optional DomainChecklist for domain-aware constraints.

    Returns:
        DevelopmentResult with execution outcomes.

    Raises:
        PlanValidationError: If the plan is invalid.
        CyclicDependencyError: If dependencies contain a cycle.

    Example::

        result = await run_development_phase(plan, max_parallel=8)
        if result.success:
            print("All chunks passed!")
        else:
            print(f"Issues: {result.summary}")
    """
    phase = DevelopmentPhase(
        executor=executor,
        test_runner=test_runner,
        state_store=state_store,
        max_parallel=max_parallel,
        domain_checklist=domain_checklist,
    )
    return await phase.run(plan)
