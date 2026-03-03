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
import copy
import json
import logging
import os
import re
import sys
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional, Set, Tuple

from startd8.contractors.artisan_contractor import _NoOpTracer
from startd8.contractors.protocols import (
    DRAFT_MODEL_CLAUDE_HAIKU,
    VALIDATE_MODEL_CLAUDE_SONNET,
)
from startd8.logging_config import get_logger
from startd8.otel_conventions import AttributeKeys

# OTel instrumentation (graceful degradation when unavailable)
try:
    from opentelemetry import trace as _trace
    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False

_implement_tracer = _trace.get_tracer("startd8.artisan.implement") if _HAS_OTEL else _NoOpTracer()


_log = get_logger(__name__)

# AR-411: template-default placeholders that indicate stale .contextcore.yaml fields.
# When ALL non-empty sub-fields of a section match these markers, the entire section
# is suppressed to avoid wasting tokens and injecting contradictory constraints.
_STALE_CONTEXT_MARKERS: Dict[str, List[str]] = {
    "objectives": ["Example objective", "update with real business goal"],
    "constraints": ["Do NOT proceed to Phase 1"],
    "service_metadata": ["HEALTHCHECK type MUST match transport_protocol"],
}

# ---------------------------------------------------------------------------
# L-3: Module-level constants (extracted from scattered inline literals)
# ---------------------------------------------------------------------------

#: Default ``max_tokens`` override for LLM code-generation agents.
_DEFAULT_MAX_TOKENS: int = 64_000

#: Aggregate byte budget for existing-file context in prompts (PC-B3 pattern).
_EXISTING_FILES_BUDGET_BYTES: int = 60_000

#: Scope-mismatch ratio threshold — output below this fraction of design lines
#: triggers a warning for possible partial implementation.
_SCOPE_MISMATCH_RATIO_THRESHOLD: float = 0.25

#: Minimum output lines below which scope-mismatch detection fires (combined
#: with ``_SCOPE_MISMATCH_RATIO_THRESHOLD``).
_SCOPE_MISMATCH_MIN_OUTPUT_LINES: int = 100

#: Maximum characters for the project identity prompt section.
_PROJECT_IDENTITY_MAX_CHARS: int = 500

#: Character budget for architectural context in supplementary sections (TM-3).
_ARCH_CTX_BUDGET: int = 4_096

#: Character budget for plan_context in supplementary sections.
_PLAN_CTX_BUDGET: int = 4_000

#: Character budget for requirements text in supplementary sections (TM-3).
_REQ_TEXT_BUDGET: int = 8_000

#: Character budget for prompt constraints in supplementary sections (TM-3).
_CONSTRAINTS_BUDGET: int = 4_000

#: Maximum parameter_sources entries shown in prompts before truncation.
_MAX_PARAMETER_SOURCES: int = 20

#: Default timeout in seconds for individual test commands.
_DEFAULT_TEST_TIMEOUT_SECONDS: int = 300


def _format_implement_prompt(template_name: str, **kwargs: Any) -> Optional[str]:
    """Load and format a template from ``implement.yaml``.

    Returns the formatted string on success.  When the YAML file or
    template is unavailable (e.g. downstream installs that haven't
    updated), falls back to ``_INLINE_FALLBACK_TEMPLATES`` so callers
    always receive a usable prompt string for known templates.

    Returns ``None`` only for template names with no registered fallback.
    """
    try:
        from startd8.contractors.artisan_phases.prompts import format_prompt

        # M-16: validate provided kwargs against declared placeholders
        try:
            from startd8.contractors.artisan_phases.prompts import _load_file

            data = _load_file("implement")
            entry = data.get("prompts", {}).get(template_name)
            if isinstance(entry, dict) and "placeholders" in entry:
                declared = set(entry["placeholders"])
                provided = set(kwargs.keys())
                missing = declared - provided
                extra = provided - declared
                if missing or extra:
                    _log.warning(
                        "implement/%s placeholder mismatch: "
                        "declared=%s, provided=%s, missing=%s, extra=%s",
                        template_name,
                        sorted(declared),
                        sorted(provided),
                        sorted(missing),
                        sorted(extra),
                    )
        except Exception:
            pass  # Best-effort validation; don't block prompt rendering

        return format_prompt("implement", template_name, **kwargs)
    except (FileNotFoundError, KeyError) as exc:
        fallback = _INLINE_FALLBACK_TEMPLATES.get(template_name)
        if fallback is not None:
            _log.info(
                "YAML template implement/%s unavailable — using inline fallback "
                "(original error: %s: %s)",
                template_name,
                type(exc).__name__,
                exc,
            )
            try:
                return fallback.format(**kwargs)
            except KeyError as fmt_exc:
                _log.info(
                    "Inline fallback for implement/%s failed to format "
                    "(original load error: %s: %s, format error: %s)",
                    template_name,
                    type(exc).__name__,
                    exc,
                    fmt_exc,
                )
                return fallback  # Return unformatted rather than None
        _log.info(
            "YAML template implement/%s unavailable, no inline fallback "
            "(error: %s: %s)",
            template_name,
            type(exc).__name__,
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# Inline fallback templates — mirrors of implement.yaml for resilience.
# These ensure the LLM always receives structured prompt sections even
# when the YAML file is missing or a template key was renamed.
# Keep in sync with implement.yaml; see artisan-pipeline.contract.yaml.
# ---------------------------------------------------------------------------
_INLINE_FALLBACK_TEMPLATES: Dict[str, str] = {
    "project_identity": (
        "## Project Identity\n"
        "**Project:** {project_name}\n"
        "{project_root_line}\n"
        "{goals_block}"
    ),
    "target_files_edit": (
        "## Target Files\n"
        "You MUST update the following existing file(s). Focus on applying the\n"
        "changes described in the design document — do NOT rewrite from scratch.\n"
        "{file_list}"
    ),
    "target_files_create": (
        "## Target Files\n"
        "You MUST generate the following file(s). Focus on implementing\n"
        "the PRIMARY artifact — do NOT generate test code.\n"
        "{file_list}"
    ),
    "importable_modules": (
        "## Importable Modules (ground truth)\n"
        "The following modules ACTUALLY EXIST in the project. When writing\n"
        "import statements, ONLY use module paths from this list. Do NOT\n"
        "invent module paths from the design document if they are not listed here.\n\n"
        "{module_list}"
    ),
    "edit_first_directive": (
        "## Edit-First Directive\n"
        "**CRITICAL:** The target files shown above already exist in the project. "
        "You MUST:\n"
        "1. PRESERVE all existing functions, classes, imports, and logic "
        "that are not explicitly being changed\n"
        "2. ADD or MODIFY only what the design document specifies\n"
        "3. NEVER remove existing code unless the design explicitly requires it\n"
        "4. MAINTAIN backward compatibility — existing callers must continue to work\n"
        "5. Keep existing docstrings, type hints, and error handling intact\n\n"
        "Treat this as an EDIT to production code, not a greenfield implementation. "
        "If the design document describes new functionality, integrate it alongside "
        "the existing code.\n\n"
        "**SIZE CONSTRAINT:** The existing file(s) total {total_lines} lines. "
        "Your output MUST be AT LEAST {min_lines} lines (80% of original). "
        "Outputs significantly shorter than the original will be REJECTED.\n"
    ),
    "edit_mode_classification": (
        "## Edit Mode Classification\n"
        "**Task mode:** {mode_upper} (confidence: {confidence})\n"
        "{per_file_details}\n"
        "{signal_conflicts}\n"
        "{mode_guidance}"
    ),
    "design_doc_edit": (
        "## AUTHORITATIVE Design Changes\n"
        "The following design document describes CHANGES to apply to the "
        "existing code shown above. It is the AUTHORITATIVE specification "
        "for what to ADD or MODIFY.\n\n"
        "**CRITICAL:** Apply these changes to the existing code. "
        "Do NOT rewrite the file from scratch. The existing code is the "
        "foundation — the design document describes what to change, not "
        "what the entire file should look like.\n\n"
        "**Design Scope:** {design_lines} lines across {design_sections} "
        "sections. A partial implementation that omits designed sections "
        "will be rejected in review.\n"
    ),
    "design_doc_create": (
        "## AUTHORITATIVE Design Document\n"
        "The following design document was approved during the DESIGN phase. "
        "It is the AUTHORITATIVE specification for this task.\n\n"
        "**CRITICAL:** This design document OVERRIDES the Task Summary below "
        "when they differ in scope or detail. The Task Summary is only a brief "
        "label. The design document defines the FULL scope of what must be "
        "implemented — all sections, rules, structures, and patterns specified "
        "in the design MUST appear in your output.\n\n"
        "**Design Scope:** {design_lines} lines across {design_sections} "
        "sections. A partial implementation that omits designed sections "
        "will be rejected in review.\n"
    ),
    "task_summary_label": (
        "## Task Summary (label only — see AUTHORITATIVE Design Document "
        "above for full scope)\n"
    ),
    "retry_feedback": (
        "## Retry Feedback\n"
        "The previous attempt failed. Please fix the issues and regenerate.\n"
        "{error_block}\n"
        "{test_block}"
    ),
    "design_doc_sr_disambiguation": (
        "**NOTE:** The design document below uses SEARCH/REPLACE notation "
        "to specify the changes to apply. These blocks describe WHAT to "
        "change in the existing code \u2014 they are NOT your output format. "
        "Follow the output format instructions in your system prompt.\n"
    ),
    "skeleton_file_guidance": (
        "## Pre-Existing Skeleton Files\n"
        "The following target files ALREADY EXIST with correct function/class\n"
        "signatures (created deterministically from the design contract):\n"
        "{skeleton_file_list}\n\n"
        "Rules:\n"
        "- NEVER change function signatures, class definitions, or type hints\n"
        "- NEVER remove existing imports, decorators, or docstrings\n"
        "- Fill in function bodies with complete implementations\n"
        "- Replace `raise NotImplementedError` with working code\n"
        "- Add internal helper functions/variables as needed INSIDE function bodies\n"
    ),
}


def _normalize_target_path(value: str) -> str:
    """Normalize relative target paths for deterministic comparisons."""
    path = Path(value)
    normalized = path.as_posix()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def _detect_missing_targets(
    *,
    expected_targets: List[str],
    written_files: List[Path],
    output_dir: Path,
) -> Set[str]:
    """Return expected target paths that were not produced by the executor."""
    expected = {_normalize_target_path(target) for target in expected_targets}
    actual: Set[str] = set()
    for written in written_files:
        try:
            relative = written.resolve().relative_to(output_dir.resolve())
            actual.add(_normalize_target_path(str(relative)))
        except ValueError:
            actual.add(_normalize_target_path(str(written)))
    return expected - actual


# ============================================================================
# ENUMS
# ============================================================================


class TaskComplexityTier(str, Enum):
    """Complexity-Driven Model Router tier classification (REQ-CMR-000).

    Determines which model architecture is used per IMPLEMENT chunk:
        TIER_1: Haiku only — T2 refinement skipped (simple greenfield tasks)
        TIER_2: Haiku + T2 Sonnet — current default behavior
        TIER_3: Opus as T1 drafter — highest-capability model for complex edits
    """

    TIER_1 = "tier_1"
    TIER_2 = "tier_2"
    TIER_3 = "tier_3"


# Default complexity tier used when no manifest data is available.
_DEFAULT_COMPLEXITY_TIER = TaskComplexityTier.TIER_2


@dataclass(frozen=True)
class TaskComplexitySignals:
    """Per-task complexity signals extracted from manifest data (REQ-CMR-001).

    All fields use primitive types with safe defaults that classify as TIER_2
    (the current default behavior) when no manifest data is available.
    """

    blast_radius: int = 0
    caller_count: int = 0
    has_dynamic_dispatch: bool = False
    is_closure: bool = False
    estimated_loc: int = 0
    target_file_count: int = 1
    edit_mode: str = "unknown"
    mro_depth: int = 0
    unresolved_call_count: int = 0
    has_cross_file_edges: bool = False
    manifest_coverage: str = "none"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON storage and forensic logging.

        Uses ``dataclasses.asdict`` so new fields are automatically included.
        """
        from dataclasses import asdict

        return asdict(self)


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
        self.logger = get_logger(__name__)

    async def execute(
        self, chunk: DevelopmentChunk, context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Execute the chunk via callback or dry-run/no-op mode."""
        if context.get("dry_run", False):
            self.logger.debug(f"[DRY-RUN] Executing chunk {chunk.chunk_id}")
            return True, "Dry-run: implementation skipped"

        if self.callback is None:
            self.logger.warning(
                "Chunk %s: no callback provided — no code generated. "
                "Register an LLM callback to produce real output.",
                chunk.chunk_id,
            )
            return False, "No callback: no code was generated"

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
        max_tokens: int = _DEFAULT_MAX_TOKENS,
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
                when creating agents.  Defaults to ``_DEFAULT_MAX_TOKENS``
                (suitable for large code generation).
        """
        self._drafter_spec = drafter_agent
        self._lead_spec = lead_agent
        self._output_dir = output_dir or Path("generated")
        self._max_tokens = max_tokens

        # Lazily resolved agent instances (cached after first call)
        self._drafter: Optional[Any] = None
        self._lead: Optional[Any] = None

        self.logger = get_logger(__name__)

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
            if target in per_file_code:
                content = per_file_code[target]
            elif per_file_code:
                # M-13: For multi-file chunks, if a target is missing from
                # per_file_code (edge case — stubs should cover all targets),
                # generate a stub rather than falling back to the full code.
                # Falling back to full code would write the primary module's
                # preamble (imports, docstring) to secondary files.
                from startd8.utils.code_extraction import (
                    _generate_stub as _gen_stub,
                )
                content = _gen_stub(target)
                self.logger.warning(
                    "Multi-file fallback: generating stub for %s "
                    "(chunk %s, not in per_file_code)",
                    target, chunk.chunk_id,
                )
            else:
                # Single-file path: per_file_code is empty, full code is correct
                content = code
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

            # CS4: Forensic log for implement.chunk
            from startd8.contractors.forensic_log import emit_forensic_log
            emit_forensic_log(
                call_type="implement.chunk",
                call={
                    "prompt_length": len(prompt),
                    "max_tokens": self._max_tokens,
                    "model_spec": self._drafter_spec,
                    "response_time_ms": time_ms,
                    "tokens_input": token_usage.input,
                    "tokens_output": token_usage.output,
                    "cost_usd": token_usage.cost_estimate,
                    "attempt": context.get("_retry_attempt", 1),
                },
                task={
                    "task_id": chunk.chunk_id,
                    "title": chunk.description,
                    "phase": "implement",
                    "target_files": chunk.file_targets,
                },
                context_propagation={
                    "domain_defaulted": context.get("_domain_defaulted"),
                    "design_doc_present": context.get("project_context") is not None,
                    "prompt_constraints_count": len(context.get("domain_constraints", []))
                        if isinstance(context.get("domain_constraints"), list) else 0,
                    "environment_checks_count": context.get("_environment_checks_count"),
                    "complexity_manifest_coverage": (
                        chunk.metadata.get("_complexity_signals", {}) or {}
                    ).get("manifest_coverage", "none"),
                },
            )

            # Extract code from the response
            from startd8.utils.code_extraction import extract_code_from_response

            code = extract_code_from_response(response_text)

            if not code or not code.strip():
                return False, "LLM returned empty code after extraction"

            # Write generated files
            written_files = self._write_generated_files(code, chunk)

            # Check for missing target files
            if written_files and chunk.file_targets:
                missing = _detect_missing_targets(
                    expected_targets=chunk.file_targets,
                    written_files=written_files,
                    output_dir=self._output_dir,
                )
                if missing:
                    chunk.metadata["_missing_targets"] = sorted(missing)
                    self.logger.warning(
                        "IMPLEMENT: chunk %s missing %d of %d target files: %s",
                        chunk.chunk_id,
                        len(missing),
                        len(chunk.file_targets),
                        sorted(missing),
                    )

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

    #: Minimum fraction of existing file size that output must retain.
    #: Used in Edit-First Directive and Edit Mode Classification guidance.
    _MIN_OUTPUT_FRACTION: float = 0.80

    #: Maximum phantom element warnings shown in structural delta section.
    _MAX_PHANTOM_WARNINGS_SHOWN: int = 5

    #: Maximum truncated file paths shown in structural delta section.
    _MAX_TRUNCATED_FILES_SHOWN: int = 3

    #: File extension → human-readable format hint for Target Files section.
    _EXT_FORMAT_HINTS: Dict[str, str] = {
        "yaml": "Valid YAML configuration",
        "yml": "Valid YAML configuration",
        "json": "Valid JSON",
        "md": "Markdown document",
        "py": "Python module",
    }

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
        project_root: Optional[Path] = None,
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
        self._project_root = project_root
        self._generator: Optional[Any] = None
        self.logger = get_logger(__name__)

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

        # PCA-502: Read existing file contents — project_root first, staging overrides.
        # This ensures the LLM sees production files when modifying existing code.
        for target in chunk.file_targets:
            # Layer 1: read from project_root (production files)
            if self._project_root is not None:
                prod_path = self._project_root / target
                if prod_path.exists():
                    try:
                        content = prod_path.read_text(encoding="utf-8")
                        # I-3: Save original line count before truncation
                        _original_line_count = len(content.splitlines())
                        gen_ctx.setdefault(
                            "_existing_files_original_lines", {},
                        )[target] = _original_line_count
                        if len(content) > self._MAX_EXISTING_FILE_BYTES:
                            content = (
                                content[: self._MAX_EXISTING_FILE_BYTES]
                                + f"\n\n# ... truncated ({len(content)} bytes total)"
                            )
                        gen_ctx.setdefault("existing_files", {})[target] = content
                    except (UnicodeDecodeError, OSError) as exc:
                        self.logger.warning(
                            "Could not read existing file %s: %s", prod_path, exc,
                        )
            # Layer 2: staging overrides (latest generation takes precedence)
            staging_path = self._output_dir / target
            if staging_path.exists():
                try:
                    content = staging_path.read_text(encoding="utf-8")
                    # I-3: Save original line count before truncation
                    _original_line_count = len(content.splitlines())
                    gen_ctx.setdefault(
                        "_existing_files_original_lines", {},
                    )[target] = _original_line_count
                    if len(content) > self._MAX_EXISTING_FILE_BYTES:
                        content = (
                            content[: self._MAX_EXISTING_FILE_BYTES]
                            + f"\n\n# ... truncated ({len(content)} bytes total)"
                        )
                    gen_ctx.setdefault("existing_files", {})[target] = content
                except (UnicodeDecodeError, OSError) as exc:
                    self.logger.warning(
                        "Could not read existing file %s: %s", staging_path, exc,
                    )

        # Micro Prime: inject pre-filled skeletons as existing content for partial chunks.
        # Only injects files NOT already loaded from production/staging above so that
        # real on-disk content always takes precedence over the pre-pass output.
        mp_skeletons = chunk.metadata.get("_micro_prime_filled_skeletons")
        if mp_skeletons and not chunk.metadata.get("_micro_prime_complete"):
            for fp, content in mp_skeletons.items():
                if fp not in gen_ctx.get("existing_files", {}):
                    gen_ctx.setdefault("existing_files", {})[fp] = content

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

        # PCA-300: project architecture context
        arch_ctx = meta.get("architectural_context")
        if arch_ctx:
            gen_ctx["architectural_context"] = arch_ctx

        plan_goals = meta.get("plan_goals")
        if plan_goals:
            gen_ctx["plan_goals"] = plan_goals

        plan_context = meta.get("plan_context")
        if plan_context:
            gen_ctx["plan_context"] = plan_context

        # PCA-301/400: service metadata
        svc_meta = meta.get("service_metadata")
        if svc_meta:
            gen_ctx["service_metadata"] = svc_meta

        # PCA-600: edit mode classification for downstream workflow consumption
        # Stored as dict in metadata (via to_dict()); pass as dict for
        # downstream LeadContractorWorkflow which uses dict-based access.
        edit_mode_info = meta.get("_edit_mode")
        if edit_mode_info:
            gen_ctx["edit_mode"] = edit_mode_info  # dict for workflow consumption

        return gen_ctx

    # ------------------------------------------------------------------
    # Task description builder (refactored into helpers using YAML)
    # ------------------------------------------------------------------

    def _build_task_description(
        self,
        chunk: DevelopmentChunk,
        context: Dict[str, Any],
    ) -> str:
        """Build the task description string for ``generator.generate()``.

        Enriches the chunk description with the design document (if available),
        prompt constraints, and retry feedback for error-informed retries.

        Each logical section is built by a helper method that loads its
        template from ``implement.yaml`` (falling back to an inline string
        when the YAML file is absent, e.g. in downstream installs that
        haven't updated).

        Args:
            chunk: The chunk being executed.
            context: Execution context.

        Returns:
            Enriched task description string.
        """
        parts: List[str] = []
        _existing = chunk.metadata.get("_existing_file_contents", {})
        _edit_mode = chunk.metadata.get("_edit_mode")
        is_edit = bool(_existing) or (
            _edit_mode is not None and _edit_mode.get("mode") == "edit"
        )

        parts.extend(self._build_project_identity(chunk))
        parts.extend(self._build_target_files(chunk, is_edit))       # B-1/B-7 fix
        parts.extend(self._build_importable_modules(chunk))          # AR-150
        parts.extend(self._build_manifest_context(chunk))            # Phase 4
        parts.extend(self._build_forward_contracts(chunk))           # Phase 5
        parts.extend(self._build_skeleton_guidance(chunk))           # Phase 6a
        parts.extend(self._build_call_graph_context(chunk))          # Phase 6
        parts.extend(self._build_structural_delta(chunk))            # Gap 3
        parts.extend(self._build_existing_files(_existing, _edit_mode))
        if _existing:
            _orig_lines = chunk.metadata.get("_existing_files_original_lines")
            parts.extend(self._build_edit_first_directive(_existing, _orig_lines))
        parts.extend(self._build_edit_mode_classification(_edit_mode))  # B-3 fix
        parts.extend(self._build_design_framing(chunk, _existing))      # B-5 fix
        parts.append(chunk.description)
        parts.extend(self._build_supplementary_context(chunk))
        parts.extend(self._build_retry_feedback(context))
        return "\n".join(parts)

    # -- helper: project identity ------------------------------------------

    def _build_project_identity(
        self, chunk: DevelopmentChunk
    ) -> List[str]:
        """PCA-500: Project identity header.

        Args:
            chunk: The development chunk whose metadata carries project
                name, root path, and plan goals.
        """
        _proj_name = chunk.metadata.get("project_name")
        if not _proj_name:
            return []

        _proj_root = chunk.metadata.get("project_root_path")
        project_root_line = f"**Root:** `{_proj_root}`" if _proj_root else ""

        _pg = chunk.metadata.get("plan_goals", [])
        if _pg:
            goals_block = "**Goals:**\n" + "\n".join(f"- {g}" for g in _pg[:2])
        else:
            goals_block = ""

        text = _format_implement_prompt(
            "project_identity",
            project_name=_proj_name,
            project_root_line=project_root_line,
            goals_block=goals_block,
        )
        if text is None:
            return []

        if len(text) > _PROJECT_IDENTITY_MAX_CHARS:
            text = text[:_PROJECT_IDENTITY_MAX_CHARS] + "\n..."
        return [text, "\n---\n"]

    # -- helper: target files (B-1/B-7 fix) --------------------------------

    def _build_target_files(
        self, chunk: DevelopmentChunk, is_edit: bool
    ) -> List[str]:
        """Target file listing — verb conditioned on edit vs create mode.

        Args:
            chunk: The development chunk whose ``file_targets`` list the
                files the drafter must produce.
            is_edit: When ``True``, the section uses "update" language;
                otherwise it uses "generate" language.
        """
        if not chunk.file_targets:
            return []

        file_list_parts: List[str] = []
        for target in chunk.file_targets:
            ext = target.rsplit(".", 1)[-1] if "." in target else ""
            fmt_hint = self._EXT_FORMAT_HINTS.get(ext, "")
            file_list_parts.append(
                f"- `{target}`" + (f" ({fmt_hint})" if fmt_hint else "")
            )
        file_list = "\n".join(file_list_parts)

        template_name = "target_files_edit" if is_edit else "target_files_create"
        text = _format_implement_prompt(template_name, file_list=file_list)
        if text is None:
            return []

        return [text, "\n---\n"]

    # -- helper: importable modules (AR-150) --------------------------------

    _MAX_IMPORTABLE_MODULES = 50

    def _build_importable_modules(
        self, chunk: DevelopmentChunk
    ) -> List[str]:
        """AR-150: Ground-truth importable modules for the target packages.

        Lists actual ``.py`` modules on disk for each package directory
        that contains a target file.  This prevents the LLM from inventing
        import paths that don't exist (e.g. from a design doc typo).

        Args:
            chunk: The development chunk whose ``file_targets`` determine
                which package directories to scan.

        Returns:
            List of prompt text fragments (section text + separator), or
            an empty list when no importable modules are found.
        """
        project_root = getattr(self, "_project_root", None)
        if project_root is None:
            return []

        py_targets = [t for t in chunk.file_targets if t.endswith(".py")]
        if not py_targets:
            return []

        # Determine the src prefix used in the project
        src_dir = project_root / "src"
        search_root = src_dir if src_dir.is_dir() else project_root

        # Collect unique parent package directories from target files
        package_dirs: Dict[str, Path] = {}  # dotted_parent -> absolute path
        for target in py_targets:
            target_path = Path(target)
            parent = target_path.parent
            if not parent.parts:
                continue
            abs_parent = search_root / parent
            if not abs_parent.is_dir():
                # Also try under project_root directly
                abs_parent = project_root / parent
                if not abs_parent.is_dir():
                    continue
            # Convert path to dotted module prefix
            # Strip src/ or lib/ prefix for dotted path
            try:
                rel = abs_parent.relative_to(search_root)
            except ValueError:
                try:
                    rel = abs_parent.relative_to(project_root)
                except ValueError:
                    continue
            dotted = str(rel).replace(os.sep, ".")
            package_dirs[dotted] = abs_parent

        if not package_dirs:
            return []

        # Build module list
        module_entries: List[str] = []
        for dotted_prefix, pkg_dir in sorted(package_dirs.items()):
            try:
                children = sorted(pkg_dir.iterdir())
            except OSError as exc:
                _log.debug(
                    "AR-150: cannot list modules in %s: %s", pkg_dir, exc,
                )
                continue
            for child in children:
                if (
                    child.suffix == ".py"
                    and child.name != "__init__.py"
                    and child.is_file()
                ):
                    module_entries.append(f"- `{dotted_prefix}.{child.stem}`")
                elif child.is_dir() and (child / "__init__.py").exists():
                    module_entries.append(f"- `{dotted_prefix}.{child.name}` (package)")
                if len(module_entries) >= self._MAX_IMPORTABLE_MODULES:
                    break
            if len(module_entries) >= self._MAX_IMPORTABLE_MODULES:
                break

        # AR-822: Supplement with SCAFFOLD module inventory for project-wide coverage
        scaffold_inventory = chunk.metadata.get("module_inventory", [])
        if scaffold_inventory:
            already_listed = {e.split("`")[1].split(".")[0] for e in module_entries if "`" in e}
            new_entries = [
                f"- `{m}` (package)" for m in scaffold_inventory
                if m.split(".")[0] not in already_listed
            ]
            if new_entries:
                remaining = self._MAX_IMPORTABLE_MODULES - len(module_entries)
                module_entries.extend(new_entries[:remaining])

        if not module_entries:
            return []

        module_list = "\n".join(module_entries)

        text = _format_implement_prompt(
            "importable_modules", module_list=module_list
        )
        if text is None:
            return []

        if scaffold_inventory:
            text += "\nImport ONLY from the modules listed above. Do not invent import paths."

        return [text, "\n---\n"]

    # -- helper: post-generation manifest diff (Phase 4, IM-5) ---------------

    def _manifest_post_generate_diff(
        self,
        written_files: List[Path],
        chunk: DevelopmentChunk,
        context: Dict[str, Any],
    ) -> None:
        """Compare generated files against original manifests (IM-5).

        After _write_generated_files(), if a manifest registry is available,
        parse the generated file and diff it against the original manifest.
        If public elements were removed, emit a WARNING log.

        This is best-effort — parse failures are logged and swallowed.
        """
        registry = context.get("project_manifests")
        if registry is None:
            return

        try:
            from startd8.utils.code_manifest import generate_file_manifest
            from startd8.utils.manifest_registry import ManifestDiff
        except ImportError:
            return

        project_root = self._project_root or self._output_dir
        for gen_file in written_files:
            # Determine relative path for registry lookup
            try:
                rel_path = str(gen_file.relative_to(self._output_dir))
            except ValueError:
                continue

            original = registry.get(rel_path)
            if original is None:
                continue  # New file, no comparison

            try:
                fresh = generate_file_manifest(gen_file, project_root)
            except Exception as exc:
                self.logger.debug(
                    "manifest.post_generate: parse failed for %s: %s",
                    gen_file, exc,
                )
                continue

            try:
                diff = ManifestDiff.diff(original, fresh)
            except Exception as exc:
                self.logger.debug(
                    "manifest.post_generate: diff failed for %s: %s",
                    gen_file, exc,
                )
                continue

            if diff.removed_public:
                self.logger.warning(
                    "manifest.post_generate: chunk %s removed %d public "
                    "element(s) from %s: %s",
                    chunk.chunk_id,
                    len(diff.removed_public),
                    rel_path,
                    diff.removed_public[:5],
                )
                chunk.metadata.setdefault("_manifest_removed_public", {})[
                    rel_path
                ] = diff.removed_public

            # CG-IM-5: Post-generation caller compatibility check
            try:
                for fqn, old_sig, new_sig in diff.changed_signatures:
                    callers = registry.callers_of(fqn)
                    if callers:
                        self.logger.warning(
                            "manifest.post_generate: chunk %s changed signature of %s "
                            "(%d callers may break) — old=%s, new=%s",
                            chunk.chunk_id, fqn, len(callers), old_sig, new_sig,
                        )
                        chunk.metadata.setdefault("_sig_change_caller_warnings", []).append({
                            "fqn": fqn,
                            "callers": len(callers),
                            "old_sig": old_sig,
                            "new_sig": new_sig,
                        })
            except Exception as exc:
                self.logger.debug(
                    "manifest.post_generate: CG-IM-5 caller check failed for %s: %s",
                    gen_file, exc,
                )

    # -- helper: forward contracts (Phase 5) --------------------------------

    @staticmethod
    def _build_forward_contracts(
        chunk: DevelopmentChunk,
    ) -> List[str]:
        """Phase 5: Forward interface contracts injected into prompt.
        
        Contracts are extracted and formatted by map_forward_contracts_for_task
        in context_seed_handlers.py and passed via metadata.
        """
        contracts_text = chunk.metadata.get("forward_contracts")
        if not contracts_text:
            return []

        return [contracts_text, "\n---\n"]

    # -- helper: skeleton file guidance (Phase 6a) --------------------------

    @staticmethod
    def _build_skeleton_guidance(
        chunk: DevelopmentChunk,
    ) -> List[str]:
        """Phase 6a: Body-only fill-in guidance when skeleton files exist.

        Reads ``skeleton_files_present`` and ``skeleton_file_list`` from chunk
        metadata (injected by ImplementPhaseHandler) and formats the
        ``skeleton_file_guidance`` template from implement.yaml.
        """
        if not chunk.metadata.get("skeleton_files_present"):
            return []
        skeleton_list = chunk.metadata.get("skeleton_file_list", "")
        if not skeleton_list:
            return []
        rendered = _format_implement_prompt(
            "skeleton_file_guidance",
            skeleton_file_list=skeleton_list,
        )
        if rendered:
            return [rendered]
        return []

    # -- helper: manifest context (Phase 4) ---------------------------------

    @staticmethod
    def _build_manifest_context(
        chunk: DevelopmentChunk,
    ) -> List[str]:
        """Phase 4: Code structure context from manifest data.

        Reads ``_manifest_context`` from chunk metadata (injected by
        ImplementPhaseHandler) and formats as a ``## Code Structure`` section.

        Prompt injection risk note (req R2-S7): manifest summaries contain
        user-authored strings (FQNs, docstrings, signatures) that sit alongside
        LLM instruction text. This is an accepted risk — manifest data is
        AST-extracted (not raw file content), limiting the attack surface.
        """
        manifest_ctx = chunk.metadata.get("_manifest_context")
        if not manifest_ctx:
            return []

        _log.debug(
            "IMPLEMENT: manifest context included (%d chars)", len(manifest_ctx)
        )

        return [
            "## Code Structure\n"
            "The following shows the existing code structure (classes, functions, "
            "signatures) for the target files. Preserve existing public APIs unless "
            "the design document explicitly requires changes.\n\n"
            + manifest_ctx,
            "\n---\n",
        ]

    # -- helper: call graph context (Phase 6) ---------------------------------

    @staticmethod
    def _build_call_graph_context(
        chunk: DevelopmentChunk,
    ) -> List[str]:
        """Phase 6: Function call dependency context from call graph data.

        Reads ``_call_graph_context`` and ``_call_graph_callers`` from chunk
        metadata (injected by ImplementPhaseHandler) and formats as a
        ``## Function Call Dependencies`` section.
        """
        cg_ctx = chunk.metadata.get("_call_graph_context")
        cg_callers = chunk.metadata.get("_call_graph_callers")
        if not cg_ctx and not cg_callers:
            return []

        parts: List[str] = [
            "## Function Call Dependencies\n"
            "The following shows call relationships for the target files. "
            "Functions with many callers have high blast radius — changes to "
            "their signatures require updating all callers.\n",
        ]

        if cg_ctx:
            parts.append(cg_ctx)

        if cg_callers:
            high_impact = [c for c in cg_callers if c.get("blast_radius", 0) > 5]
            if high_impact:
                parts.append("\n**High-impact functions** (blast radius > 5):")
                for entry in high_impact[:10]:
                    parts.append(
                        f"- `{entry['fqn']}`: {len(entry.get('direct_callers', []))} "
                        f"direct callers, blast radius {entry.get('blast_radius', 0)}"
                    )

        parts.append("\n---\n")

        _log.debug(
            "IMPLEMENT: call graph context included (%d chars)",
            sum(len(p) for p in parts),
        )
        return parts

    # -- helper: structural delta (Gap 3) ------------------------------------

    @staticmethod
    def _build_structural_delta(
        chunk: DevelopmentChunk,
    ) -> List[str]:
        """Gap 3: Element-level structural intent from DESIGN phase.

        Renders the ``_design_structural_delta`` metadata as a structured
        section that tells the LLM exactly which elements to add, modify,
        or preserve per file.
        """
        delta = chunk.metadata.get("_design_structural_delta")
        if not delta:
            return []

        parts: List[str] = [
            "## Structural Intent (from DESIGN phase)\n"
            "The following element-level actions were specified in the design. "
            "Adhere to these precisely — do NOT add, modify, or remove elements "
            "beyond what is listed.\n",
        ]
        for fpath, elements in delta.items():
            parts.append(f"\n### `{fpath}`")
            for elem in elements:
                action = elem.get("action", "modify")
                name = elem.get("element", "")
                detail = elem.get("detail", "")
                prefix = {"add": "+", "modify": "~", "preserve": "="}.get(action, "?")
                if name:
                    parts.append(f"  {prefix} `{name}`: {detail}")
                else:
                    parts.append(f"  {prefix} {detail}")
        parts.append("\n---\n")

        # Gap 1: Phantom element warnings
        phantom_warnings = chunk.metadata.get("_phantom_element_warnings")
        if phantom_warnings:
            parts.append(
                "**WARNING:** The design references elements not found in the "
                "current code manifest. These may be new elements to create, or "
                "may indicate stale design references:\n"
            )
            for ref in phantom_warnings[:LeadContractorChunkExecutor._MAX_PHANTOM_WARNINGS_SHOWN]:
                parts.append(f"  - `{ref}`")
            parts.append("")

        # Gap 5: Truncation tier awareness
        trunc_tiers = chunk.metadata.get("_manifest_truncation_tier", {})
        truncated_files = [
            f for f, tier in trunc_tiers.items()
            if tier not in ("full", "unavailable")
        ]
        if truncated_files:
            parts.append(
                "**Note:** Structural context was truncated for some files "
                f"({', '.join(f'`{f}`' for f in truncated_files[:LeadContractorChunkExecutor._MAX_TRUNCATED_FILES_SHOWN])}). "
                "The actual file may contain additional elements not shown.\n"
            )

        return parts

    # -- helper: existing file contents ------------------------------------

    @staticmethod
    def _build_existing_files(
        existing: Dict[str, str],
        edit_mode: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """PCA-503/TM-1: Existing file contents with budget + priority ordering.

        Shows existing target files within a 60KB aggregate budget.
        Files are priority-sorted: edit-mode files first, then by size
        descending (largest first).  Files that cross the budget boundary
        are partially included with a line-aware truncation marker.
        Files beyond the budget are listed as omitted.

        This matches the prime contractor's ``_build_existing_files_section``
        budgeting pattern (PC-B3).
        """
        if not existing:
            return []

        # Priority ordering: edit files first, then by size descending
        per_file_modes: Dict[str, Dict] = {}
        if edit_mode and edit_mode.get("per_file"):
            per_file_modes = edit_mode["per_file"]

        def _sort_key(item: tuple) -> tuple:
            path, content = item
            mode = per_file_modes.get(path, {}).get("mode", "create")
            mode_order = 0 if mode == "edit" else 1
            return (mode_order, -len(content))

        sorted_files = sorted(existing.items(), key=_sort_key)

        full_kb = sum(len(c) for c in existing.values()) / 1024
        total_count = len(existing)
        total_bytes = 0
        included_count = 0
        omitted: List[tuple] = []  # (path, line_count)
        file_parts: List[str] = []

        for ef_path, ef_content in sorted_files:
            ef_size = len(ef_content.encode("utf-8", errors="replace"))
            ef_lines = len(ef_content.splitlines())

            if total_bytes + ef_size <= _EXISTING_FILES_BUDGET_BYTES:
                # Full inclusion
                _nonce = uuid.uuid4().hex[:8]
                file_parts.append(f"\n### `{ef_path}` ({ef_lines} lines)")
                file_parts.append(f"```source-{_nonce}\n{ef_content}\n```")
                total_bytes += ef_size
                included_count += 1
            elif total_bytes < _EXISTING_FILES_BUDGET_BYTES:
                # Partial inclusion — truncate at budget boundary
                remaining_budget = _EXISTING_FILES_BUDGET_BYTES - total_bytes
                lines = ef_content.splitlines()
                included_lines: List[str] = []
                running = 0
                for line in lines:
                    line_bytes = len(line.encode("utf-8", errors="replace")) + 1
                    if running + line_bytes > remaining_budget:
                        break
                    included_lines.append(line)
                    running += line_bytes
                remaining_lines = ef_lines - len(included_lines)
                truncated_content = "\n".join(included_lines)
                truncated_content += (
                    f"\n# ... [TRUNCATED: {remaining_lines} lines omitted "
                    f"— full file is {ef_lines} lines] ..."
                )
                _nonce = uuid.uuid4().hex[:8]
                file_parts.append(f"\n### `{ef_path}` ({ef_lines} lines, truncated)")
                file_parts.append(f"```source-{_nonce}\n{truncated_content}\n```")
                total_bytes = _EXISTING_FILES_BUDGET_BYTES
                included_count += 1
            else:
                omitted.append((ef_path, ef_lines))

        included_kb = total_bytes / 1024

        # Build header with inclusion stats
        header_parts: List[str] = [
            f"## Existing Files (showing {included_count}/{total_count} files, "
            f"{included_kb:.1f}KB of {full_kb:.1f}KB)\n",
            "The following target files ALREADY EXIST in the project. "
            "Your output MUST preserve existing functionality and only "
            "add or modify what is specified in the design document.",
        ]

        if omitted:
            omitted_list = ", ".join(
                f"`{p}` ({n} lines)" for p, n in omitted
            )
            header_parts.append(
                f"\n**Omitted files** (exceed context budget — preserve as-is): "
                f"{omitted_list}"
            )

        return header_parts + file_parts + ["\n---\n"]

    # -- helper: edit-first directive --------------------------------------

    @classmethod
    def _build_edit_first_directive(
        cls,
        existing: Dict[str, str],
        original_lines: Optional[Dict[str, int]] = None,
    ) -> List[str]:
        """PCA-503/605b: Edit-First Directive with quantitative size constraint.

        Args:
            existing: Mapping of target path to (possibly truncated) file content.
            original_lines: Optional mapping of target path to original (pre-truncation)
                line count.  When provided, uses these counts for accurate min_lines
                calculation instead of counting truncated content lines (I-3 fix).
        """
        # R2-I4: Only count lines from files that were actually included in
        # the prompt (not budget-omitted).  Replicate the budget check from
        # _build_existing_files to determine which files the LLM can see.
        included_paths: set = set()
        _budget_used = 0
        for ef_path, ef_content in existing.items():
            ef_size = len(ef_content.encode("utf-8", errors="replace"))
            if _budget_used + ef_size <= _EXISTING_FILES_BUDGET_BYTES:
                included_paths.add(ef_path)
                _budget_used += ef_size
            elif _budget_used < _EXISTING_FILES_BUDGET_BYTES:
                # Partially included — still counts
                included_paths.add(ef_path)
                _budget_used = _EXISTING_FILES_BUDGET_BYTES
            # else: omitted — don't count

        # I-3: Use original line counts when available to avoid under-counting
        # after double truncation (_MAX_EXISTING_FILE_BYTES + _EXISTING_FILES_BUDGET_BYTES).
        if original_lines:
            total_lines = sum(
                lc for path, lc in original_lines.items()
                if path in included_paths
            )
        else:
            total_lines = sum(
                len(c.splitlines()) for path, c in existing.items()
                if path in included_paths
            )
        min_lines = int(total_lines * cls._MIN_OUTPUT_FRACTION)

        text = _format_implement_prompt(
            "edit_first_directive",
            total_lines=total_lines,
            min_lines=min_lines,
        )
        if text is None:
            return []

        return [text, "\n---\n"]

    # -- helper: edit mode classification (B-3 fix) ------------------------

    @classmethod
    def _build_edit_mode_classification(
        cls,
        edit_mode: Optional[Dict[str, Any]],
    ) -> List[str]:
        """PCA-600: Edit mode classification — shown for ALL modes (B-3 fix).

        Previously this section was only rendered when ``mode == "edit"``.
        Now it is rendered whenever upstream classification is available,
        giving the LLM a clear signal regardless of classification result.
        """
        if not edit_mode:
            return []

        mode = edit_mode.get("mode", "unknown")
        mode_upper = mode.upper()
        confidence = edit_mode.get("confidence", "unknown")

        # Per-file details (single-pass partition into edit/create buckets)
        per_file_lines: List[str] = []
        _per_file = edit_mode.get("per_file", {})
        if isinstance(_per_file, dict) and _per_file:
            _edit_files: List[str] = []
            _create_files: List[str] = []
            for fpath, info in _per_file.items():
                file_mode = info.get("mode") if isinstance(info, dict) else None
                if file_mode == "edit":
                    _edit_files.append(fpath)
                elif file_mode == "create":
                    _create_files.append(fpath)
                staleness = info.get("staleness", "") if isinstance(info, dict) else ""
                if staleness:
                    per_file_lines.append(f"- `{fpath}`: staleness={staleness}")
            if _edit_files:
                per_file_lines.insert(
                    0,
                    "**Files being EDITED:** "
                    + ", ".join(f"`{f}`" for f in _edit_files),
                )
            if _create_files:
                per_file_lines.insert(
                    1 if _edit_files else 0,
                    "**Files being CREATED:** "
                    + ", ".join(f"`{f}`" for f in _create_files),
                )
        per_file_details = "\n".join(per_file_lines)

        # Signal conflicts
        _conflicts = edit_mode.get("signal_conflicts", [])
        if _conflicts:
            signal_conflicts = (
                "\n**Signal conflicts detected:**\n"
                + "\n".join(f"- {c}" for c in _conflicts[:3])
            )
        else:
            signal_conflicts = ""

        # Mode-appropriate guidance
        pct = int(cls._MIN_OUTPUT_FRACTION * 100)
        if mode == "edit":
            mode_guidance = (
                f"\n**MINIMUM OUTPUT:** Your output must be AT LEAST {pct}% of the "
                "existing file size. Outputs that drop below this threshold will "
                "be REJECTED by automated guards. Do NOT rewrite from scratch — "
                "EDIT the existing code."
            )
        else:
            mode_guidance = (
                "\n**NEW FILE:** This task creates a new file. Implement all "
                "sections described in the design document. Do not leave "
                "placeholder or stub implementations."
            )

        text = _format_implement_prompt(
            "edit_mode_classification",
            mode_upper=mode_upper,
            confidence=confidence,
            per_file_details=per_file_details,
            signal_conflicts=signal_conflicts,
            mode_guidance=mode_guidance,
        )
        if text is None:
            return []

        return [text, "\n---\n"]

    # -- helper: design doc target-file filtering (DF-1) -------------------

    # File extension pattern for recognising file paths in ### headings.
    _DESIGN_FILE_EXT_RE = re.compile(
        r"\.(?:py|toml|yaml|yml|json|md|txt|cfg|ini|typed|html|css|"
        r"js|ts|tsx|jsx|go|rs|java|rb|sh|sql|xml|env|bat|csv)\s*$"
    )

    @staticmethod
    def _filter_design_doc_for_targets(
        design_doc: str,
        file_targets: List[str],
    ) -> str:
        """Filter design doc to redact code blocks belonging to non-target files.

        When a ``### <filepath>`` heading names a file that is **not** in
        *file_targets*, every fenced code block within that section is replaced
        with a short placeholder note.  Prose is preserved so the drafter still
        gets the architectural context without being tempted to generate code
        for files it is not responsible for.

        Args:
            design_doc: Raw markdown text from the DESIGN phase.
            file_targets: Paths the current chunk must generate.

        Returns:
            Filtered markdown with non-target code blocks replaced.
        """
        if not file_targets:
            return design_doc

        # Build a normalised set for flexible matching (full path + basename).
        target_set: Set[str] = set()
        for t in file_targets:
            clean = t.lstrip("./")
            target_set.add(clean)
            target_set.add(os.path.basename(clean))

        ext_re = LeadContractorChunkExecutor._DESIGN_FILE_EXT_RE

        lines = design_doc.splitlines(keepends=True)
        result: List[str] = []

        # State: the non-target file detected for the current ### section,
        # or None when we are in prose / a target-file section.
        section_file: Optional[str] = None
        in_fence = False
        skip_fence = False

        for line in lines:
            stripped = line.strip()

            # --- section boundary tracking (only outside fences) -----------
            if not in_fence and stripped.startswith("### "):
                heading = stripped[4:].strip().strip("`")
                if ext_re.search(heading):
                    clean = heading.lstrip("./")
                    basename = os.path.basename(clean)
                    if clean not in target_set and basename not in target_set:
                        section_file = clean
                    else:
                        section_file = None
                else:
                    section_file = None
                result.append(line)
                continue

            # Reset at ## level (broader sections are always preserved).
            if not in_fence and stripped.startswith("## ") and not stripped.startswith("### "):
                section_file = None
                result.append(line)
                continue

            # --- fenced code block boundaries ------------------------------
            if stripped.startswith("```"):
                if not in_fence:
                    in_fence = True
                    if section_file is not None:
                        skip_fence = True
                        result.append(
                            f"> *[Code for `{section_file}` omitted — "
                            f"not a target file for this task]*\n\n"
                        )
                    else:
                        skip_fence = False
                        result.append(line)
                else:
                    in_fence = False
                    if not skip_fence:
                        result.append(line)
                    skip_fence = False
                continue

            # Inside a skipped fence — drop the line silently.
            if in_fence and skip_fence:
                continue

            result.append(line)

        return "".join(result)

    # -- helper: design document framing (B-5 fix) -------------------------

    @staticmethod
    def _build_design_framing(
        chunk: DevelopmentChunk,
        existing: Dict[str, str],
    ) -> List[str]:
        """Authoritative design document framing + task summary demotion."""
        design_doc = chunk.metadata.get("design_document")
        if not design_doc:
            return []

        # DF-1: Filter the design doc so code blocks for non-target files
        # are replaced with placeholders.  This prevents the drafter from
        # generating code for files outside its responsibility.
        filtered_doc = LeadContractorChunkExecutor._filter_design_doc_for_targets(
            design_doc, getattr(chunk, "file_targets", []),
        )

        # Compute scope metrics from the *filtered* doc so the framing
        # line-count matches what the drafter actually sees.
        design_lines = 0
        design_sections = 0
        for line in filtered_doc.strip().splitlines():
            design_lines += 1
            if line.strip().startswith("##"):
                design_sections += 1

        # B-5 fix: use edit framing when existing files are present,
        # greenfield framing ONLY when there are truly no existing files.
        template_name = "design_doc_edit" if existing else "design_doc_create"

        framing = _format_implement_prompt(
            template_name,
            design_lines=design_lines,
            design_sections=design_sections,
        )
        summary_label = _format_implement_prompt("task_summary_label")

        if framing is None:
            # All fallbacks are now in _INLINE_FALLBACK_TEMPLATES — if we still
            # got None, the template name itself is unrecognised.
            _log.warning(
                "Design framing template %s has no fallback — prompt will lack "
                "authoritative design context", template_name,
            )
            framing = f"## Design Document ({design_lines} lines, {design_sections} sections)\n"
        if summary_label is None:
            summary_label = _INLINE_FALLBACK_TEMPLATES["task_summary_label"]

        # AR-410: disambiguate when design doc contains S/R specification blocks
        _has_sr = "<<<<<<< SEARCH" in filtered_doc or ">>>>>>> REPLACE" in filtered_doc
        sr_note = ""
        if _has_sr and template_name == "design_doc_edit":
            sr_note = _format_implement_prompt("design_doc_sr_disambiguation") or ""

        parts = [framing]
        if sr_note:
            parts.append(sr_note)
        parts.extend([filtered_doc, "\n---\n", summary_label])
        return parts

    # -- helper: stale context detection (AR-411) --------------------------

    @staticmethod
    def _is_stale_context(field: str, values: Any) -> bool:
        """Return True if *values* contain template-default placeholders."""
        markers = _STALE_CONTEXT_MARKERS.get(field, [])
        if not markers:
            return False
        text = str(values) if not isinstance(values, str) else values
        return any(m in text for m in markers)

    # -- helper: supplementary context sections ----------------------------

    @staticmethod
    def _build_supplementary_context(chunk: DevelopmentChunk) -> List[str]:
        """IMP-7, PCA-300/301/401/403/404: supplementary context sections."""
        parts: List[str] = []

        # IMP-7: Design completeness warning
        completeness_warning = chunk.metadata.get("design_completeness_warning", "")
        if completeness_warning:
            parts.append("\n## Design Completeness Warning")
            parts.append(completeness_warning)

        # PCA-300: project architecture section (AR-411: suppress stale template defaults)
        # TM-3: capped at _ARCH_CTX_BUDGET chars to match prime contractor budget.
        arch_ctx = chunk.metadata.get("architectural_context")
        if arch_ctx and isinstance(arch_ctx, dict):
            objectives = arch_ctx.get("objectives")
            arch_constraints = arch_ctx.get("constraints")
            _obj_stale = LeadContractorChunkExecutor._is_stale_context("objectives", objectives) if objectives else True
            _con_stale = LeadContractorChunkExecutor._is_stale_context("constraints", arch_constraints) if arch_constraints else True
            if _obj_stale and _con_stale:
                _log.debug("AR-411: suppressed stale architectural_context (template defaults)")
            else:
                _arch_parts: List[str] = []
                if objectives and not _obj_stale:
                    _arch_parts.append("**Objectives:**")
                    for obj in (objectives if isinstance(objectives, list) else [objectives])[:3]:
                        _arch_parts.append(f"- {obj}")
                if arch_constraints and not _con_stale:
                    _arch_parts.append("**Constraints:**")
                    for con in (arch_constraints if isinstance(arch_constraints, list) else [arch_constraints])[:5]:
                        _arch_parts.append(f"- {con}")
                if _arch_parts:
                    arch_text = "\n".join(_arch_parts)
                    if len(arch_text) > _ARCH_CTX_BUDGET:
                        arch_text = arch_text[:_ARCH_CTX_BUDGET] + "\n... [truncated]"
                    parts.append("\n## Project Architecture")
                    parts.append(arch_text)

        plan_goals = chunk.metadata.get("plan_goals")
        if plan_goals and isinstance(plan_goals, list):
            parts.append("\n## Project Goals")
            for goal in plan_goals[:5]:
                parts.append(f"- {goal}")

        # PCA-301: service metadata section (AR-411: suppress stale boilerplate)
        svc_meta = chunk.metadata.get("service_metadata")
        if svc_meta and isinstance(svc_meta, dict):
            tp = svc_meta.get("transport_protocol")
            rd = svc_meta.get("runtime_dependencies")
            _has_useful_svc = bool(tp) or (rd and isinstance(rd, list) and len(rd) > 0)
            if not _has_useful_svc:
                # AR-411: dict has no transport_protocol and no runtime_dependencies
                # — the section would only contain the hardcoded boilerplate constraint.
                _log.debug("AR-411: suppressed stale service_metadata (no transport_protocol, no runtime_dependencies)")
            else:
                parts.append("\n## Service Metadata")
                if tp:
                    parts.append(f"- Transport protocol: {tp}")
                if rd and isinstance(rd, list):
                    parts.append(f"- Runtime dependencies: {', '.join(str(d) for d in rd)}")
                parts.append(
                    "HEALTHCHECK type MUST match transport_protocol. "
                    "Do NOT add capabilities the service does not use."
                )

        # PCA-401: plan context section
        plan_context = chunk.metadata.get("plan_context")
        if plan_context and isinstance(plan_context, str):
            parts.append("\n## Plan Context")
            parts.append(plan_context[:_PLAN_CTX_BUDGET])

        # PCA-404: requirements text section (IMP-R1: authoritative framing)
        # TM-3: capped at _REQ_TEXT_BUDGET chars to prevent prompt bloat.
        req_text = chunk.metadata.get("requirements_text")
        if req_text and isinstance(req_text, str):
            parts.append(
                "\n## Requirements (verbatim — authoritative for parameter details)"
            )
            if len(req_text) > _REQ_TEXT_BUDGET:
                parts.append(req_text[:_REQ_TEXT_BUDGET] + "\n... [truncated]")
            else:
                parts.append(req_text)

        # PCA-403: prior implementations section
        prior_impls = chunk.metadata.get("prior_implementations")
        if prior_impls and isinstance(prior_impls, list):
            parts.append("\n## Prior Implementations")
            for pi in prior_impls[:3]:
                _tid = pi.get("task_id", "unknown")
                _files = ", ".join(pi.get("files", [])[:3])
                parts.append(f"- {_tid}: {_files}")

        # IMP-5: grouped prompt constraints
        # TM-3: capped at _CONSTRAINTS_BUDGET chars to prevent prompt bloat.
        constraints = chunk.metadata.get("prompt_constraints", [])
        if constraints:
            from startd8.contractors.artisan_phases.prompts import format_constraints
            # Normalize: if constraints are dicts, extract 'text' field
            normalized = []
            for c in constraints:
                if isinstance(c, dict):
                    cat = c.get("category", "")
                    text = c.get("text", str(c))
                    normalized.append(f"[{cat}] {text}" if cat else text)
                else:
                    normalized.append(str(c))
            formatted = format_constraints(normalized)
            if len(formatted) > _CONSTRAINTS_BUDGET:
                formatted = formatted[:_CONSTRAINTS_BUDGET] + "\n... [truncated]"
            parts.append("\n## Constraints")
            parts.append(formatted)

        # Mottainai Rule 5: parameter provenance
        param_sources = chunk.metadata.get("parameter_sources")
        if param_sources and isinstance(param_sources, dict):
            parts.append("\n## Parameter Sources (use these names exactly)")
            items = list(param_sources.items())
            if len(items) > _MAX_PARAMETER_SOURCES:
                _log.warning(
                    "parameter_sources truncated from %d to %d entries",
                    len(items),
                    _MAX_PARAMETER_SOURCES,
                )
            for name, source in items[:_MAX_PARAMETER_SOURCES]:
                if isinstance(source, dict):
                    origin = source.get("origin", source.get("source", ""))
                    parts.append(f"- `{name}`: {origin}")
                else:
                    parts.append(f"- `{name}`: {source}")

        # Mottainai Rule 5: semantic naming conventions
        sem_conv = chunk.metadata.get("semantic_conventions")
        if sem_conv and isinstance(sem_conv, dict):
            parts.append("\n## Semantic Conventions")
            for key, value in list(sem_conv.items())[:10]:
                if isinstance(value, dict):
                    rule = value.get("rule", value.get("convention", str(value)))
                    parts.append(f"- {key}: {rule}")
                else:
                    parts.append(f"- {key}: {value}")

        return parts

    # -- helper: retry feedback --------------------------------------------

    @staticmethod
    def _build_retry_feedback(context: Dict[str, Any]) -> List[str]:
        """Retry feedback section for error-informed retries."""
        last_error = context.get("last_error")
        test_output = context.get("test_output")
        if not last_error and not test_output:
            return []

        error_block = f"\nPrevious error:\n{last_error}" if last_error else ""
        test_block = f"\nTest output:\n{test_output}" if test_output else ""

        text = _format_implement_prompt(
            "retry_feedback",
            error_block=error_block,
            test_block=test_block,
        )
        if text is None:
            return []

        return [text]

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
            gen_ctx = self._build_generation_context(chunk, context)

            # PCA-503: Store existing file contents in chunk metadata so
            # _build_task_description can render them in the prompt.
            existing_files = gen_ctx.get("existing_files")
            if existing_files:
                chunk.metadata["_existing_file_contents"] = existing_files
            # I-3: Store original line counts for accurate min_lines calculation
            original_lines = gen_ctx.get("_existing_files_original_lines")
            if original_lines:
                chunk.metadata["_existing_files_original_lines"] = original_lines

            task_desc = self._build_task_description(chunk, context)

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
                    design_lines = chunk.metadata.get("_design_lines") or len(
                        design_doc.strip().splitlines()
                    )
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
                    if scope_ratio < _SCOPE_MISMATCH_RATIO_THRESHOLD and total_output_lines < _SCOPE_MISMATCH_MIN_OUTPUT_LINES:
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


# ── Search/replace threshold ─────────────────────────────────────────
#: Minimum lines in an existing file to trigger search/replace mode.
#: Files shorter than this threshold use the whole-file edit-first path.
_SEARCH_REPLACE_LINE_THRESHOLD: int = 50

#: Inline fallback for search/replace system prompt (when YAML unavailable).
_SR_SYSTEM_FALLBACK: str = (
    "You are an expert Python engineer editing existing source code files.\n"
    "When Parameter Sources or Semantic Conventions are provided, use those "
    "names and conventions exactly.\n\n"
    "Output your changes as "
    "SEARCH/REPLACE blocks. Each block identifies existing code and its "
    "replacement:\n\n"
    "<<<<<<< SEARCH\n"
    "exact lines from the existing file\n"
    "=======\n"
    "your replacement (modified lines)\n"
    ">>>>>>> REPLACE\n\n"
    "Rules:\n"
    "- SEARCH must be an exact copy from the existing file (copy-paste)\n"
    "- Include 2-3 lines of surrounding context for unambiguous matching\n"
    "- Multiple blocks allowed, applied top-to-bottom\n"
    "- To ADD code, include the insertion point in SEARCH and add new lines in REPLACE\n"
    "- To DELETE code, use an empty REPLACE section\n"
    "- Do NOT output the entire file"
)

#: Inline fallback for CREATE mode system prompt (when YAML unavailable).
_CREATE_SYSTEM_FALLBACK: str = (
    "You are an expert Python engineer generating production-quality source code.\n\n"
    "Code quality expectations:\n"
    "- Complete implementations only — no stubs, no TODO placeholders, no pass bodies\n"
    "- Proper type hints on all public functions and methods\n"
    "- Follow PEP 8 and project naming conventions\n\n"
    "Provenance rules (Mottainai Rule 5):\n"
    "- When Parameter Sources are listed, use those parameter names EXACTLY as specified\n"
    "- When Semantic Conventions are listed, follow those naming rules\n"
    "- Do NOT rename or abbreviate names from upstream design documents\n\n"
    "Output the complete Python file inside a single fenced code block."
)

#: Inline fallback for EDIT mode system prompt (when YAML unavailable).
_EDIT_SYSTEM_FALLBACK: str = (
    "You are an expert Python engineer editing existing source code.\n\n"
    "Edit-first discipline:\n"
    "- PRESERVE all existing functions, classes, imports, and logic not being changed\n"
    "- ADD or MODIFY only what the design document specifies\n"
    "- NEVER remove existing code unless the design explicitly requires it\n"
    "- Your output MUST be at least 80% the size of the input\n\n"
    "Provenance rules (Mottainai Rule 5):\n"
    "- When Parameter Sources are listed, use those parameter names EXACTLY as specified\n"
    "- When Semantic Conventions are listed, follow those naming rules\n"
    "- Do NOT rename or abbreviate names from upstream design documents\n\n"
    "Output the complete modified Python file inside a single fenced code block."
)


class ArtisanChunkExecutor(LeadContractorChunkExecutor):
    """Chunk executor using direct ``agenerate()`` calls.

    Inherits all prompt-building helpers from
    :class:`LeadContractorChunkExecutor` (``_build_task_description``,
    ``_build_generation_context``, and ~10 section helpers).

    Key differences from the parent:
    - Calls ``drafter.agenerate()`` directly instead of routing through
      ``LeadContractorCodeGenerator`` (no lead/drafter review loop).
    - Adds search/replace edit block support for large existing files.
    - Constructor takes ``drafter_spec`` instead of ``code_generator``.

    Example::

        executor = ArtisanChunkExecutor(
            drafter_spec="anthropic:claude-sonnet-4-6",
            output_dir=Path("staging"),
            project_root=Path("/my/project"),
        )
        phase = DevelopmentPhase(executor=executor)
        result = await phase.run(plan)
    """

    def __init__(
        self,
        drafter_spec: str = DRAFT_MODEL_CLAUDE_HAIKU.agent_spec,
        refiner_spec: Optional[str] = None,
        tier3_drafter_spec: Optional[str] = None,
        tier2_gate_escalation: bool = False,
        output_dir: Optional[Path] = None,
        max_tokens: Optional[int] = None,
        project_root: Optional[Path] = None,
        **kwargs: Any,
    ):
        """Initialize the Artisan chunk executor.

        Args:
            drafter_spec: Agent spec string for the T1 implementation drafter.
            refiner_spec: Agent spec string for the T2 refiner. When ``None``,
                T2 refinement is skipped and T1 output is used directly.
            tier3_drafter_spec: Agent spec for Tier 3 Opus drafter (REQ-CMR-021).
                When ``None``, Tier 3 chunks fall back to the default drafter_spec.
            tier2_gate_escalation: Enable gate-driven Tier 2 escalation (REQ-CMR-022).
            output_dir: Staging directory for writing generated files.
            max_tokens: Override max_tokens for agent creation.
            project_root: Project root for reading existing files.
        """
        # Initialize parent for prompt helpers; lead_agent is unused
        # but required by the parent constructor.
        super().__init__(
            lead_agent=drafter_spec,  # unused, satisfies parent
            drafter_agent=drafter_spec,
            output_dir=output_dir,
            max_tokens=max_tokens,
            project_root=project_root,
            **kwargs,
        )
        self._drafter_spec = drafter_spec
        self._refiner_spec = refiner_spec
        self._tier3_drafter_spec = tier3_drafter_spec
        self._tier2_gate_escalation = tier2_gate_escalation
        self._artisan_drafter: Optional[Any] = None
        self._artisan_refiner: Optional[Any] = None
        self._artisan_tier3_drafter: Optional[Any] = None
        self._artisan_max_tokens = max_tokens or _DEFAULT_MAX_TOKENS
        self.logger = get_logger(__name__)

    # ------------------------------------------------------------------
    # Agent resolution (lazy, cached)
    # ------------------------------------------------------------------

    def _resolve_artisan_drafter(self) -> Any:
        """Resolve the drafter agent spec to a BaseAgent (cached)."""
        if self._artisan_drafter is not None:
            return self._artisan_drafter

        from startd8.utils.agent_resolution import resolve_agent_spec

        self.logger.info("Resolving artisan drafter agent: %s", self._drafter_spec)
        self._artisan_drafter = resolve_agent_spec(
            self._drafter_spec,
            name="artisan-drafter",
            max_tokens=self._artisan_max_tokens,
        )
        return self._artisan_drafter

    def _resolve_artisan_refiner(self) -> Optional[Any]:
        """Resolve the T2 refiner agent spec to a BaseAgent (cached).

        Returns ``None`` when ``refiner_spec`` is not configured.
        """
        if self._refiner_spec is None:
            return None
        if self._artisan_refiner is not None:
            return self._artisan_refiner

        from startd8.utils.agent_resolution import resolve_agent_spec

        self.logger.info("Resolving artisan T2 refiner agent: %s", self._refiner_spec)
        self._artisan_refiner = resolve_agent_spec(
            self._refiner_spec,
            name="artisan-refiner-t2",
            max_tokens=self._artisan_max_tokens,
        )
        return self._artisan_refiner

    def _resolve_tier3_drafter(self) -> Optional[Any]:
        """Resolve the Tier 3 Opus drafter agent spec (lazy, cached) (REQ-CMR-021).

        Returns ``None`` when ``tier3_drafter_spec`` is not configured.
        """
        if self._tier3_drafter_spec is None:
            return None
        if self._artisan_tier3_drafter is not None:
            return self._artisan_tier3_drafter

        from startd8.utils.agent_resolution import resolve_agent_spec

        self.logger.info("Resolving Tier 3 Opus drafter agent: %s", self._tier3_drafter_spec)
        self._artisan_tier3_drafter = resolve_agent_spec(
            self._tier3_drafter_spec,
            name="artisan-drafter-tier3",
            max_tokens=self._artisan_max_tokens,
        )
        return self._artisan_tier3_drafter

    # ------------------------------------------------------------------
    # T2 condensed context (AR-412)
    # ------------------------------------------------------------------

    def _build_t2_context(self, chunk: "DevelopmentChunk", context: Dict[str, Any]) -> str:
        """Build condensed context for T2 refinement (AR-412).

        Includes: project name (1-line), target files, design document,
        task description, key constraints (parameter_sources, semantic_conventions,
        prompt_constraints).
        Excludes: existing file content, S/R instructions, edit-first directive,
        full project identity, plan goals/context.
        """
        parts: List[str] = []

        # 1-line project summary
        proj_name = chunk.metadata.get("project_name", "")
        if proj_name:
            parts.append(f"**Project:** {proj_name}")

        # Target files
        if chunk.file_targets:
            parts.append("**Target files:** " + ", ".join(f"`{f}`" for f in chunk.file_targets))

        # Design document (the core specification T2 must match)
        # R2-I3: Filter the design doc to only include sections relevant
        # to this chunk's target files, preventing cross-task leakage
        # in multi-task features where Task B's T2 refiner would
        # otherwise see Task A's design sections.
        design_doc = chunk.metadata.get("design_document")
        if design_doc:
            file_targets = getattr(chunk, "file_targets", [])
            if file_targets:
                design_doc = LeadContractorChunkExecutor._filter_design_doc_for_targets(
                    design_doc, file_targets,
                )
            parts.append("\n## Design Document")
            parts.append(
                f"**Focus ONLY on the code for "
                f"{', '.join(f'`{f}`' for f in file_targets) if file_targets else 'this task'}"
                f" — ignore sections about other files.**"
            )
            parts.append(design_doc)

        # Task description (chunk.description only, NOT the full assembled T1 prompt)
        parts.append("\n## Task Description")
        parts.append(chunk.description)

        # Key constraints (reuse relevant parts from _build_supplementary_context)
        constraints = chunk.metadata.get("prompt_constraints", [])
        if constraints:
            from startd8.contractors.artisan_phases.prompts import format_constraints
            parts.append("\n## Constraints")
            parts.append(format_constraints(constraints))

        param_sources = chunk.metadata.get("parameter_sources")
        if param_sources and isinstance(param_sources, dict):
            parts.append("\n## Parameter Sources (use these names exactly)")
            ps_items = list(param_sources.items())
            if len(ps_items) > _MAX_PARAMETER_SOURCES:
                _log.warning(
                    "parameter_sources truncated from %d to %d entries",
                    len(ps_items),
                    _MAX_PARAMETER_SOURCES,
                )
            for name, source in ps_items[:_MAX_PARAMETER_SOURCES]:
                if isinstance(source, dict):
                    origin = source.get("origin", source.get("source", ""))
                    parts.append(f"- `{name}`: {origin}")
                else:
                    parts.append(f"- `{name}`: {source}")

        sem_conv = chunk.metadata.get("semantic_conventions")
        if sem_conv and isinstance(sem_conv, dict):
            parts.append("\n## Semantic Conventions")
            for key, value in list(sem_conv.items())[:10]:
                if isinstance(value, dict):
                    rule = value.get("rule", value.get("convention", str(value)))
                    parts.append(f"- {key}: {rule}")
                else:
                    parts.append(f"- {key}: {value}")

        # IMP-CS: coding standards for T2 refiner (matches T1 user prompt)
        coding_std = _format_implement_prompt("coding_standards")
        if coding_std:
            parts.append(coding_std)

        # I-4: For edit-mode tasks, include existing file signatures so T2 can
        # verify that T1 (Haiku) preserved existing code.  Full content is
        # excluded to keep T2 context small; signatures (def/class/import lines)
        # give enough signal for structural verification.
        if chunk.metadata.get("_edit_mode", {}).get("mode") == "edit":
            existing = chunk.metadata.get("_existing_file_contents", {})
            if existing:
                parts.append("\n## Existing File Signatures (for edit verification)")
                for path, content in existing.items():
                    sig_lines = [
                        line
                        for line in content.splitlines()
                        if line.strip().startswith(
                            ("def ", "class ", "import ", "from ", "async def ")
                        )
                    ]
                    parts.append(
                        f"### `{path}` — {len(content.splitlines())} total lines"
                    )
                    if sig_lines:
                        parts.append("```python")
                        parts.append("\n".join(sig_lines[:50]))
                        parts.append("```")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # T2 refinement pass
    # ------------------------------------------------------------------

    async def _refine_written_files(
        self,
        written_files: List[Path],
        task_desc: str,
        chunk: "DevelopmentChunk",
        context: Dict[str, Any],
    ) -> Optional[Tuple[List[Path], Dict[str, Any]]]:
        """Run T2 refinement on files produced by the T1 drafter.

        Reads back written files, builds a refinement prompt, calls T2,
        and overwrites staging files with refined content.

        Returns:
            ``(updated_written_files, refine_info)`` on success, or ``None``
            if refinement fails (caller keeps T1 output).
        """
        refiner = self._resolve_artisan_refiner()
        if refiner is None:
            return None

        try:
            # 1. Read back the T1-written files
            draft_blocks: List[str] = []
            for fpath in written_files:
                try:
                    content = fpath.read_text(encoding="utf-8")
                    # Use relative path from output_dir for clean markers
                    rel = fpath.relative_to(self._output_dir) if self._output_dir else fpath
                    draft_blocks.append(
                        f"```python\n# {rel}\n{content}\n```"
                    )
                except (OSError, UnicodeDecodeError) as exc:
                    self.logger.warning(
                        "T2 refine: could not read %s: %s", fpath, exc,
                    )

            if not draft_blocks:
                self.logger.warning("T2 refine: no readable draft files — skipping")
                return None

            draft_code = "\n\n".join(draft_blocks)

            # 2. Build refinement prompt from YAML templates (with fallback)
            refine_sys = _format_implement_prompt("refine_system")
            if refine_sys is None:
                refine_sys = (
                    "You are a senior software engineer performing code refinement. "
                    "Fix bugs, improve types, match the design, follow conventions. "
                    "Output the complete refined file(s) in fenced code blocks."
                )

            # AR-412: use condensed T2 context instead of full T1 prompt
            t2_context = self._build_t2_context(chunk, context)
            refine_user = _format_implement_prompt(
                "refine_directive",
                task_description=t2_context,
                draft_code=draft_code,
            )
            if refine_user is None:
                refine_user = (
                    f"## T2 Refinement Pass\n\n"
                    f"### Task Context\n{t2_context}\n\n"
                    f"### Draft Code (T1 output)\n{draft_code}\n\n"
                    f"Emit the complete refined file(s)."
                )

            # 3. Call T2
            self.logger.info(
                "T2 refinement for chunk %s (%d draft files, prompt %d chars)",
                chunk.chunk_id,
                len(written_files),
                len(refine_user),
            )
            refine_text, refine_time_ms, refine_usage = await refiner.agenerate(
                refine_user, system_prompt=refine_sys,
            )

            self.logger.info(
                "T2 chunk %s: responded in %dms (%d in / %d out tokens)",
                chunk.chunk_id,
                refine_time_ms,
                refine_usage.input,
                refine_usage.output,
            )

            # 4. Extract refined code
            from startd8.utils.code_extraction import (
                extract_code_from_response,
                extract_multi_file_code,
            )

            targets = chunk.file_targets or [str(f.relative_to(self._output_dir)) for f in written_files]
            refined_files: Dict[str, str] = {}

            if len(targets) > 1:
                refined_files = extract_multi_file_code(refine_text, targets)

            # Fallback: single-file or multi-file extraction failed
            if not refined_files:
                single_code = extract_code_from_response(refine_text)
                if single_code and single_code.strip():
                    refined_files[targets[0]] = single_code

            if not refined_files:
                self.logger.warning(
                    "T2 refine: empty extraction for chunk %s — keeping T1 output",
                    chunk.chunk_id,
                )
                return None

            # 5. Overwrite staging files with refined content
            updated_files: List[Path] = []
            for target in targets:
                if target in refined_files:
                    out_path = self._output_dir / target if self._output_dir else Path(target)
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(refined_files[target], encoding="utf-8")
                    updated_files.append(out_path)
                    self.logger.info("T2 refined file: %s", out_path)
                else:
                    # Keep T1 version for files not in refined output
                    orig = self._output_dir / target if self._output_dir else Path(target)
                    if orig.exists():
                        updated_files.append(orig)

            # 6. Build refine info for cost accumulation
            refine_info: Dict[str, Any] = {
                "refine_cost_usd": refine_usage.cost_estimate,
                "refine_input_tokens": refine_usage.input,
                "refine_output_tokens": refine_usage.output,
                "refine_time_ms": refine_time_ms,
                "refine_model": getattr(refiner, "model", self._refiner_spec),
                "refine_files_count": len(refined_files),
            }

            # CS4-T2: Forensic log for implement.chunk.refine
            from startd8.contractors.forensic_log import emit_forensic_log
            emit_forensic_log(
                call_type="implement.chunk.refine",
                call={
                    "prompt_length": len(refine_user),
                    "max_tokens": self._artisan_max_tokens,
                    "model_spec": self._refiner_spec,
                    "response_time_ms": refine_time_ms,
                    "tokens_input": refine_usage.input,
                    "tokens_output": refine_usage.output,
                    "cost_usd": refine_usage.cost_estimate,
                },
                task={
                    "task_id": chunk.chunk_id,
                    "title": chunk.description,
                    "phase": "implement",
                    "target_files": chunk.file_targets,
                },
                context_propagation={
                    "tier": "T2",
                    "refined_files": list(refined_files.keys()),
                },
            )

            return updated_files or written_files, refine_info

        except Exception as exc:
            self.logger.warning(
                "T2 refinement failed for chunk %s (non-fatal, keeping T1): %s",
                chunk.chunk_id,
                exc,
            )
            # R2-I8: Store error details so caller can populate t2_error.
            chunk.metadata["_t2_failure_detail"] = str(exc)
            return None

    # ------------------------------------------------------------------
    # Walkthrough prompt persistence
    # ------------------------------------------------------------------

    def _persist_walkthrough_prompts(
        self,
        chunk: "DevelopmentChunk",
        task_desc: str,
        sys_prompt: Optional[str],
        context: Dict[str, Any],
        *,
        complexity_tier: str,
        effective_drafter_spec: str,
    ) -> None:
        """Persist IMPLEMENT prompts to walkthrough directory (no LLM call)."""
        project_root = self._project_root or Path(".")
        wt_dir = project_root / ".startd8" / "walkthrough" / "implement" / chunk.chunk_id
        wt_dir.mkdir(parents=True, exist_ok=True)

        # T1 prompts
        (wt_dir / "t1_system_prompt.md").write_text(
            sys_prompt or "(no system prompt)", encoding="utf-8",
        )
        (wt_dir / "t1_user_prompt.md").write_text(task_desc, encoding="utf-8")

        # T2 prompts (AR-412: condensed context instead of full T1 prompt)
        t2_context = ""
        if self._refiner_spec:
            t2_context = self._build_t2_context(chunk, context)
            refine_sys = _format_implement_prompt("refine_system") or (
                "You are a senior software engineer performing code refinement."
            )
            refine_user = _format_implement_prompt(
                "refine_directive",
                task_description=t2_context,
                draft_code="{draft_code}",
            ) or (
                f"## T2 Refinement Pass\n\n"
                f"### Task Context\n{t2_context}\n\n"
                f"### Draft Code (T1 output)\n{{draft_code}}\n\n"
                f"Emit the complete refined file(s)."
            )
            (wt_dir / "t2_refine_system_prompt.md").write_text(
                refine_sys, encoding="utf-8",
            )
            (wt_dir / "t2_refine_user_prompt.md").write_text(
                refine_user, encoding="utf-8",
            )

        # Metadata
        metadata = {
            "chunk_id": chunk.chunk_id,
            "description": chunk.description,
            "target_files": chunk.file_targets,
            "drafter_spec": self._drafter_spec,
            "refiner_spec": self._refiner_spec,
            "complexity_tier": complexity_tier,
            "complexity_signals": chunk.metadata.get("_complexity_signals", {}),
            "effective_drafter": effective_drafter_spec,
            "t1_system_prompt_chars": len(sys_prompt) if sys_prompt else 0,
            "t1_user_prompt_chars": len(task_desc),
            "estimated_t1_tokens": len(task_desc) // 4,
            "estimated_t2_context_chars": len(t2_context) if self._refiner_spec else 0,
        }
        (wt_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8",
        )
        self.logger.info(
            "Walkthrough: persisted IMPLEMENT prompts for chunk %s → %s",
            chunk.chunk_id,
            wt_dir,
        )

    # ------------------------------------------------------------------
    # Search/replace prompt helpers
    # ------------------------------------------------------------------

    def _build_search_replace_directive(
        self,
        existing: Dict[str, str],
    ) -> List[str]:
        """Build the search/replace directive section.

        Replaces the edit-first directive when files exceed the
        search/replace line threshold.  Uses actual file sizes from disk
        when available (``_existing_file_contents`` may be truncated by
        ``_MAX_EXISTING_FILE_BYTES``).
        """
        # Compute line count from full files on disk when possible.
        total_lines = 0
        for target, content in existing.items():
            actual_content = content
            if self._project_root is not None:
                full_path = self._project_root / target
                if full_path.exists():
                    try:
                        actual_content = full_path.read_text(encoding="utf-8")
                    except (UnicodeDecodeError, OSError):
                        pass  # fall back to truncated content line count
            total_lines += len(actual_content.splitlines())

        text = _format_implement_prompt(
            "search_replace_directive",
            total_lines=total_lines,
        )
        if text is None:
            text = (
                "## Output Format: Search/Replace Blocks\n\n"
                f"The existing file has {total_lines} lines. Instead of "
                "outputting the entire file, output ONLY the sections that "
                "change using SEARCH/REPLACE blocks.\n\n"
                "Each block:\n"
                "<<<<<<< SEARCH\n"
                "(exact lines copied from the existing file above)\n"
                "=======\n"
                "(your modified version of those lines)\n"
                ">>>>>>> REPLACE\n\n"
                "Copy the SEARCH text exactly from the existing file shown "
                "above. Include enough context (2-3 surrounding lines) for "
                "unambiguous matching."
            )

        return [text, "\n---\n"]

    # -- helper: coding standards (IMP-CS) ----------------------------------

    @staticmethod
    def _build_coding_standards() -> List[str]:
        """IMP-CS: Coding standards section for the user prompt.

        Mirrors the prime contractor's inline coding standards in the
        draft template, ensuring the LLM sees ruff/linter rules in both
        the system prompt and the user prompt for reinforcement.
        """
        text = _format_implement_prompt("coding_standards")
        if text is None:
            text = (
                "## Coding Standards (ruff/linter compliance)\n"
                "- NEVER use single-letter variable names `l`, `O`, or "
                "`I` — they are ambiguous (ruff E741).\n"
                "- Do NOT import modules not in stdlib or pyproject.toml "
                "dependencies.\n"
                "- Define helper functions BEFORE callsites that reference "
                "them."
            )
        return [text, "\n---\n"]

    # -- helper: output format (IMP-OF) -------------------------------------

    @staticmethod
    def _build_output_format(chunk: DevelopmentChunk) -> List[str]:
        """IMP-OF: Structured output format instructions.

        Single-file tasks get a simple single-block format.
        Multi-file tasks get explicit per-file fencing instructions with
        a verification checklist — matching the prime contractor's
        ``single_file_output`` / ``multi_file_output`` templates.
        """
        targets = chunk.file_targets
        if not targets:
            return []

        # Search/replace mode already has its own output directive — don't
        # add a conflicting 'complete implementation' instruction.
        if chunk.metadata.get("_use_search_replace"):
            return []

        if len(targets) == 1:
            text = _format_implement_prompt("output_format_single")
            if text is None:
                text = (
                    "## Output Format\n"
                    "Provide your complete implementation inside a single "
                    "fenced code block.\n"
                    "Do NOT split output across multiple code blocks.\n"
                    "Do NOT include explanatory text outside the code block."
                )
            return [text, "\n---\n"]

        # Multi-file: build file list + checklist
        file_list = "\n".join(f"  - `{f}`" for f in targets)
        file_checklist = "\n".join(
            f"  - [ ] `{f}` has a code block" for f in targets
        )
        text = _format_implement_prompt(
            "output_format_multi",
            file_list=file_list,
            file_checklist=file_checklist,
        )
        if text is None:
            text = (
                "## Output Format\n"
                "This task requires MULTIPLE files. Produce a SEPARATE "
                "fenced code block for each file.\n\n"
                f"REQUIRED files:\n{file_list}\n\n"
                "## VERIFICATION CHECKLIST\n"
                f"{file_checklist}"
            )
        return [text, "\n---\n"]

    # -- helper: critical parameters (IMP-CP) --------------------------------

    @staticmethod
    def _build_critical_parameters(chunk: DevelopmentChunk) -> List[str]:
        """IMP-CP: Critical parameter elevation.

        Surfaces ``critical_parameters`` from chunk metadata into a
        dedicated prompt section — matching the prime contractor's
        ``critical_parameters_section`` pattern.
        """
        critical = chunk.metadata.get("critical_parameters")
        if not critical:
            return []

        if isinstance(critical, list):
            params_str = "\n".join(f"- {p}" for p in critical)
        elif isinstance(critical, str):
            params_str = critical
        else:
            import json as _json
            params_str = _json.dumps(critical, indent=2)

        text = _format_implement_prompt(
            "critical_parameters", parameters=params_str,
        )
        if text is None:
            text = (
                "## Critical Parameters (from requirements — include "
                "verbatim in implementation)\n" + params_str
            )
        return [text, "\n---\n"]

    # -- helper: forward contracts (IMP-FC) ----------------------------------

    @staticmethod
    def _build_forward_contracts_implement(
        chunk: DevelopmentChunk,
    ) -> List[str]:
        """IMP-FC: Forward contract bindings in the implement phase.

        The design phase already injects forward contracts, but the LLM
        may lose track of them during implementation. This re-surfaces
        them in the implement prompt — matching the prime contractor's
        ``forward_contracts_section`` pattern.
        """
        contracts = chunk.metadata.get("forward_contracts")
        if not contracts:
            return []

        if isinstance(contracts, str):
            contracts_str = contracts.strip()
        elif isinstance(contracts, list):
            contracts_str = "\n".join(f"- {c}" for c in contracts)
        else:
            import json as _json
            contracts_str = _json.dumps(contracts, indent=2)

        if not contracts_str:
            return []

        text = _format_implement_prompt(
            "forward_contracts", contracts=contracts_str,
        )
        if text is None:
            text = (
                "## Interface Contract Bindings (must enforce)\n"
                + contracts_str
            )
        return [text, "\n---\n"]

    # -- helper: completeness warning (IMP-CW) -------------------------------

    @staticmethod
    def _build_completeness_warning(
        chunk: DevelopmentChunk,
    ) -> List[str]:
        """IMP-CW: Warn when design parameters are missing from implementation.

        Uses ``find_missing_parameters`` from ``prompt_utils`` to detect
        parameters from the design document that haven't been referenced
        in the chunk's description or prior output.
        """
        resolved_params = chunk.metadata.get("resolved_parameters")
        if not resolved_params or not isinstance(resolved_params, list):
            return []

        from startd8.contractors.prompt_utils import find_missing_parameters

        # Check against the chunk description (the closest proxy for
        # what the LLM will implement).
        missing = find_missing_parameters(
            chunk.description, resolved_params,
        )
        if not missing:
            return []

        missing_lines = "\n".join(
            f"- `{p.get('key_name', p.get('key_value', '?'))}`: "
            f"{p.get('key_value', '?')}"
            for p in missing[:10]
        )

        text = _format_implement_prompt(
            "completeness_warning", missing_lines=missing_lines,
        )
        if text is None:
            text = (
                "## Implementation Completeness Warning\n"
                "The following parameters from the design document are "
                "NOT yet reflected. Ensure these are included:\n"
                + missing_lines
            )
        return [text, "\n---\n"]

    def _get_system_prompt(self, chunk: DevelopmentChunk) -> Optional[str]:
        """Return a mode-aware system prompt for this chunk.

        Returns the appropriate system prompt based on the chunk's mode:
        - search/replace mode → search_replace_system
        - whole-file edit mode → edit_system
        - greenfield create mode → create_system
        """
        if chunk.metadata.get("_use_search_replace"):
            return _format_implement_prompt("search_replace_system") or _SR_SYSTEM_FALLBACK
        # Detect edit vs create (same logic as _build_task_description)
        _existing = chunk.metadata.get("_existing_file_contents", {})
        _edit_mode = chunk.metadata.get("_edit_mode")
        is_edit = bool(_existing) or (
            _edit_mode is not None and _edit_mode.get("mode") == "edit"
        )
        if is_edit:
            return _format_implement_prompt("edit_system") or _EDIT_SYSTEM_FALLBACK
        return _format_implement_prompt("create_system") or _CREATE_SYSTEM_FALLBACK

    # ------------------------------------------------------------------
    # Override _build_task_description to support search/replace
    # ------------------------------------------------------------------

    def _build_task_description(
        self,
        chunk: DevelopmentChunk,
        context: Dict[str, Any],
    ) -> str:
        """Build the task description, choosing search/replace or
        edit-first directive based on existing file size."""
        parts: List[str] = []
        _existing = chunk.metadata.get("_existing_file_contents", {})
        _edit_mode = chunk.metadata.get("_edit_mode")
        is_edit = bool(_existing) or (
            _edit_mode is not None and _edit_mode.get("mode") == "edit"
        )

        # Decide search/replace vs whole-file
        use_search_replace = (
            is_edit
            and _existing
            and any(
                len(c.splitlines()) >= _SEARCH_REPLACE_LINE_THRESHOLD
                for c in _existing.values()
            )
        )
        chunk.metadata["_use_search_replace"] = use_search_replace

        parts.extend(self._build_project_identity(chunk))
        parts.extend(self._build_target_files(chunk, is_edit))
        parts.extend(self._build_importable_modules(chunk))          # AR-150
        parts.extend(self._build_manifest_context(chunk))            # Phase 4
        parts.extend(self._build_call_graph_context(chunk))          # Phase 6
        parts.extend(self._build_structural_delta(chunk))            # Gap 3
        parts.extend(self._build_existing_files(_existing, _edit_mode))

        if _existing:
            if use_search_replace:
                parts.extend(self._build_search_replace_directive(_existing))
            else:
                _orig_lines = chunk.metadata.get("_existing_files_original_lines")
                parts.extend(self._build_edit_first_directive(_existing, _orig_lines))

        parts.extend(self._build_edit_mode_classification(_edit_mode))
        parts.extend(self._build_design_framing(chunk, _existing))
        parts.append(chunk.description)
        parts.extend(self._build_supplementary_context(chunk))
        parts.extend(self._build_critical_parameters(chunk))
        parts.extend(self._build_forward_contracts_implement(chunk))
        parts.extend(self._build_skeleton_guidance(chunk))
        parts.extend(self._build_coding_standards())
        parts.extend(self._build_output_format(chunk))
        parts.extend(self._build_completeness_warning(chunk))
        parts.extend(self._build_retry_feedback(context))
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # File writing helpers
    # ------------------------------------------------------------------

    def _write_micro_prime_files(
        self,
        filled_skeletons: Dict[str, str],
        chunk: DevelopmentChunk,
    ) -> List[Path]:
        """Write Micro Prime filled skeletons to staging directory.

        Args:
            filled_skeletons: Mapping of relative file paths to filled
                source code from the Micro Prime pre-pass.
            chunk: The chunk whose ``file_targets`` determine which
                skeletons to write.

        Returns:
            List of paths that were successfully written.
        """
        written: List[Path] = []
        resolved_base = self._output_dir.resolve()
        for file_path in chunk.file_targets:
            out = (self._output_dir / file_path).resolve()
            if not out.is_relative_to(resolved_base):
                self.logger.warning(
                    "Micro Prime: skipping path traversal %s", file_path,
                )
                continue
            content = filled_skeletons.get(file_path)
            if content is not None:
                try:
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_text(content, encoding="utf-8")
                    written.append(out)
                except OSError as exc:
                    self.logger.error(
                        "Micro Prime: failed to write %s: %s",
                        out, exc,
                    )
        return written

    def _write_generated_files(
        self,
        code: str,
        chunk: DevelopmentChunk,
    ) -> List[Path]:
        """Write extracted code to staging for create-mode chunks.

        For multi-file chunks, splits the response into per-file blocks
        using :func:`extract_multi_file_code`.  For single-file chunks,
        writes the code directly.

        Args:
            code: Extracted code from the LLM response.
            chunk: The chunk (for ``file_targets``).

        Returns:
            List of paths that were written.
        """
        written: List[Path] = []

        if not chunk.file_targets:
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
                unmatched = [
                    f for f in chunk.file_targets if f not in per_file_code
                ]
                # When the splitter matched nothing but there is
                # substantial code, assign the full output to the
                # primary (first) target file instead of stubbing
                # everything.  Only secondary targets get stubs.
                if not per_file_code and code and len(code.strip()) > 100:
                    primary = chunk.file_targets[0]
                    per_file_code[primary] = code
                    unmatched = [
                        f for f in chunk.file_targets[1:]
                        if f not in per_file_code
                    ]
                    self.logger.info(
                        "Multi-file split found no file markers for chunk "
                        "%s — assigning full output (%d chars) to primary "
                        "target %s; stubbing %d secondary target(s).",
                        chunk.chunk_id,
                        len(code),
                        primary,
                        len(unmatched),
                    )
                else:
                    self.logger.warning(
                        "Multi-file split incomplete for chunk %s: matched "
                        "%s but not %s. Generating stubs for missing files.",
                        chunk.chunk_id,
                        list(per_file_code.keys()),
                        unmatched,
                    )
                for missing_file in unmatched:
                    per_file_code[missing_file] = _generate_stub(missing_file)
                chunk.metadata.setdefault("_stubbed_files", []).extend(
                    unmatched,
                )

        for target in chunk.file_targets:
            output_path = self._output_dir / target
            output_path.parent.mkdir(parents=True, exist_ok=True)
            if target in per_file_code:
                content = per_file_code[target]
            elif per_file_code:
                # M-13: For multi-file chunks, if a target is missing from
                # per_file_code (edge case — stubs should cover all targets),
                # generate a stub rather than falling back to the full code.
                # Falling back to full code would write the primary module's
                # preamble (imports, docstring) to secondary files.
                from startd8.utils.code_extraction import _generate_stub
                content = _generate_stub(target)
                self.logger.warning(
                    "Multi-file fallback: generating stub for %s "
                    "(chunk %s, not in per_file_code)",
                    target, chunk.chunk_id,
                )
            else:
                # Single-file path: per_file_code is empty, full code is correct
                content = code
            output_path.write_text(content, encoding="utf-8")
            written.append(output_path)
            self.logger.info("Wrote generated file: %s", output_path)

        return written

    def _write_applied_files(
        self,
        applied_files: Dict[str, str],
        chunk: DevelopmentChunk,
    ) -> List[Path]:
        """Write search/replace-applied content to staging.

        Args:
            applied_files: Mapping of relative file path → final content.
            chunk: The development chunk.

        Returns:
            List of paths written.
        """
        written: List[Path] = []
        for target, content in applied_files.items():
            output_path = self._output_dir / target
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(content, encoding="utf-8")
            written.append(output_path)
            self.logger.info(
                "Wrote search/replace applied file: %s (%d lines)",
                output_path,
                len(content.splitlines()),
            )
        return written

    def _decide_t2_refinement(
        self,
        *,
        complexity_tier: str,
        written_files: List[Path],
        missing_targets: Set[str],
        chunk: DevelopmentChunk,
    ) -> Tuple[bool, str]:
        """Return whether T2 should run and the reason code."""
        if complexity_tier == TaskComplexityTier.TIER_1.value:
            return False, "tier_1"
        if not written_files or not self._refiner_spec:
            return False, "refiner_unavailable"
        if not (
            self._tier2_gate_escalation
            and complexity_tier == TaskComplexityTier.TIER_2.value
        ):
            return True, "default_refine"

        escalation_reasons: List[str] = []
        if missing_targets:
            escalation_reasons.append("missing_targets")
        if chunk.metadata.get("_stubbed_files"):
            escalation_reasons.append("stubbed_files")
        if int(chunk.metadata.get("_search_replace_failed_blocks", 0) or 0) > 0:
            escalation_reasons.append("search_replace_failed_blocks")
        if escalation_reasons:
            return True, ",".join(escalation_reasons)
        return False, "tier2_gate_clear"

    # ------------------------------------------------------------------
    # Core execute (replaces LeadContractor path with direct agenerate)
    # ------------------------------------------------------------------

    async def execute(
        self, chunk: DevelopmentChunk, context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Execute the chunk via direct ``agenerate()`` call.

        Workflow:
        1. Build enriched generation context (existing files, retry info).
        2. Build task description (with search/replace or edit-first).
        3. Resolve the drafter agent (lazy, cached).
        4. Select system prompt (search/replace instructions or None).
        5. Call ``drafter.agenerate(prompt, system_prompt=sys_prompt)``.
        6. Process response: apply search/replace blocks or extract whole file.
        7. Write files to staging directory.
        8. Accumulate cost/token metrics.
        9. Return ``(True, code)`` or ``(False, error)``.
        """
        # Dry-run short-circuit
        if context.get("dry_run", False):
            self.logger.debug("[DRY-RUN] Artisan chunk %s", chunk.chunk_id)
            return True, "Dry-run: Artisan execution skipped"

        # Micro Prime short-circuit: all elements filled locally
        if chunk.metadata.get("_micro_prime_complete"):
            filled = chunk.metadata.get("_micro_prime_filled_skeletons") or {}
            if not filled:
                self.logger.warning(
                    "Micro Prime: chunk %s marked complete but has no filled skeletons — "
                    "falling through to normal execution",
                    chunk.chunk_id,
                )
            else:
                written = self._write_micro_prime_files(filled, chunk)
                expected = len(chunk.file_targets)
                if len(written) < expected:
                    written_rel = {
                        str(p.relative_to(self._output_dir.resolve()))
                        for p in written
                    }
                    missing = sorted(
                        set(chunk.file_targets) - written_rel,
                    )
                    self.logger.warning(
                        "Micro Prime: chunk %s wrote %d/%d file(s), missing: %s",
                        chunk.chunk_id, len(written), expected,
                        ", ".join(missing) or "(unknown)",
                    )
                self.logger.info(
                    "Micro Prime: chunk %s fully local — %d file(s), 0 tokens",
                    chunk.chunk_id, len(written),
                )
                return True, f"Micro Prime: {len(written)} file(s) filled locally"

        try:
            # Build context + description
            gen_ctx = self._build_generation_context(chunk, context)

            # Store existing file contents in chunk metadata for prompt
            existing_files = gen_ctx.get("existing_files")
            if existing_files:
                chunk.metadata["_existing_file_contents"] = existing_files
            # I-3: Store original line counts for accurate min_lines calculation
            original_lines = gen_ctx.get("_existing_files_original_lines")
            if original_lines:
                chunk.metadata["_existing_files_original_lines"] = original_lines

            task_desc = self._build_task_description(chunk, context)

            # CMR: Select drafter based on complexity tier (REQ-CMR-020/021)
            _complexity_tier = chunk.metadata.get(
                "_complexity_tier", _DEFAULT_COMPLEXITY_TIER.value,
            )
            if _complexity_tier == TaskComplexityTier.TIER_3.value:
                tier3 = self._resolve_tier3_drafter()
                drafter = tier3 if tier3 is not None else self._resolve_artisan_drafter()
                _effective_drafter_spec = self._tier3_drafter_spec or self._drafter_spec
            else:
                drafter = self._resolve_artisan_drafter()
                _effective_drafter_spec = self._drafter_spec

            # Select system prompt
            sys_prompt = self._get_system_prompt(chunk)

            # ── Walkthrough short-circuit ────────────────────────────
            if context.get("walkthrough"):
                self._persist_walkthrough_prompts(
                    chunk,
                    task_desc,
                    sys_prompt,
                    context,
                    complexity_tier=_complexity_tier,
                    effective_drafter_spec=_effective_drafter_spec,
                )
                return True, "Walkthrough: prompts persisted, LLM call skipped"

            self.logger.info(
                "Generating code for chunk %s via Artisan direct agenerate "
                "(%d file targets, prompt %d chars, search_replace=%s, "
                "tier=%s, drafter=%s, t2_skip=%s)",
                chunk.chunk_id,
                len(chunk.file_targets),
                len(task_desc),
                chunk.metadata.get("_use_search_replace", False),
                _complexity_tier,
                _effective_drafter_spec,
                _complexity_tier == "tier_1",
            )

            # M-12: Per-task max_tokens from design calibration, passed as
            # a per-call kwarg to avoid mutating the shared cached agent.
            _per_task_max_tokens = chunk.metadata.get("max_output_tokens")

            # Call the LLM
            response_text, time_ms, token_usage = await drafter.agenerate(
                task_desc,
                system_prompt=sys_prompt,
                max_tokens=_per_task_max_tokens,
            )

            self.logger.info(
                "Chunk %s: LLM responded in %dms (%d in / %d out tokens)",
                chunk.chunk_id,
                time_ms,
                token_usage.input,
                token_usage.output,
            )

            # TM-2: Output truncation detection (matches prime contractor)
            # R2-I7: Flag used to discard last S/R block when truncated.
            _truncation_detected = False
            if self._check_truncation:
                try:
                    from startd8.truncation_detection import detect_truncation
                    trunc_result = detect_truncation(
                        response_text,
                        strict_mode=self._strict_truncation,
                    )
                    if trunc_result.is_truncated:
                        _truncation_detected = True
                        _trunc_reason = "; ".join(trunc_result.indicators) if trunc_result.indicators else "unknown"
                        _is_high_confidence = trunc_result.confidence >= 0.7
                        if _is_high_confidence and self._fail_on_truncation:
                            self.logger.error(
                                "Chunk %s: high-confidence truncation detected — failing: %s",
                                chunk.chunk_id, _trunc_reason,
                            )
                            return False, f"Truncation detected (confidence={trunc_result.confidence:.0%}): {_trunc_reason}"
                        self.logger.warning(
                            "Chunk %s: truncation detected (confidence=%.0f%%): %s",
                            chunk.chunk_id,
                            trunc_result.confidence * 100,
                            _trunc_reason,
                        )
                except ImportError:
                    pass  # truncation_detection not available

            # CS4: Forensic log for implement.chunk (REQ-CMR-032)
            from startd8.contractors.forensic_log import emit_forensic_log
            emit_forensic_log(
                call_type="implement.chunk",
                call={
                    "prompt_length": len(task_desc),
                    "max_tokens": self._artisan_max_tokens,
                    "model_spec": _effective_drafter_spec,
                    "response_time_ms": time_ms,
                    "tokens_input": token_usage.input,
                    "tokens_output": token_usage.output,
                    "cost_usd": token_usage.cost_estimate,
                    "attempt": context.get("_retry_attempt", 1),
                    "mode": "search_replace" if chunk.metadata.get("_use_search_replace") else "whole_file",
                    "complexity_tier": _complexity_tier,
                    "drafter_model": _effective_drafter_spec,
                },
                task={
                    "task_id": chunk.chunk_id,
                    "title": chunk.description,
                    "phase": "implement",
                    "target_files": chunk.file_targets,
                    "complexity_signals": chunk.metadata.get("_complexity_signals", {}),
                },
                context_propagation={
                    "domain_defaulted": context.get("_domain_defaulted"),
                    "design_doc_present": context.get("project_context") is not None,
                    "prompt_constraints_count": len(context.get("domain_constraints", []))
                        if isinstance(context.get("domain_constraints"), list) else 0,
                    "environment_checks_count": context.get("_environment_checks_count"),
                },
            )

            # ── Process response ──────────────────────────────────────
            use_sr = chunk.metadata.get("_use_search_replace", False)
            existing = chunk.metadata.get("_existing_file_contents", {})
            chunk.metadata["_search_replace_failed_blocks"] = 0

            if use_sr and existing:
                from startd8.utils.search_replace import (
                    apply_edit_blocks,
                    has_edit_markers,
                    parse_edit_blocks,
                )

                if has_edit_markers(response_text):
                    blocks = parse_edit_blocks(response_text)

                    # R2-I7: Discard the last S/R block when truncation
                    # was detected — the last block is most likely to be
                    # incomplete (search pattern present but replacement
                    # text cut off), and applying it would corrupt code.
                    if blocks and _truncation_detected and len(blocks) > 1:
                        discarded = blocks[-1]
                        blocks = blocks[:-1]
                        preview = discarded.search_text[:80].replace("\n", "\\n")
                        self.logger.warning(
                            "R2-I7: Discarded last S/R block (index %d) for "
                            "chunk %s due to truncation detection — block may "
                            "be incomplete. Search text: %r",
                            discarded.block_index,
                            chunk.chunk_id,
                            preview,
                        )

                    if blocks:
                        applied_files: Dict[str, str] = {}
                        all_failed: List[str] = []

                        # M-10: Read full file contents for all targets first,
                        # then scope each block to only the file(s) whose
                        # content actually contains the search text.
                        full_contents: Dict[str, str] = {}
                        for target, original in existing.items():
                            full_content = original
                            if self._project_root is not None:
                                full_path = self._project_root / target
                                if full_path.exists():
                                    try:
                                        full_content = full_path.read_text(
                                            encoding="utf-8",
                                        )
                                    except (UnicodeDecodeError, OSError) as exc:
                                        self.logger.warning(
                                            "Could not read full file %s for "
                                            "search/replace — using truncated: %s",
                                            full_path,
                                            exc,
                                        )
                            full_contents[target] = full_content

                        # R2-I5: Route each block to the file it was
                        # generated for.  When a block has a file_hint
                        # (extracted from filename comments preceding the
                        # SEARCH marker), scope it to that file only.
                        # Otherwise, fall back to content matching — but
                        # when the search text appears in multiple files,
                        # scope to the first match and warn.
                        per_file_blocks: Dict[str, list] = {t: [] for t in full_contents}
                        unrouted_blocks: list = []
                        for block in blocks:
                            routed = False

                            # R2-I5: file_hint-based scoping (preferred)
                            if getattr(block, "file_hint", None):
                                hint = block.file_hint
                                hint_basename = os.path.basename(hint)
                                # Try exact match, then basename, then suffix
                                for target in full_contents:
                                    if (
                                        target == hint
                                        or os.path.basename(target) == hint_basename
                                        or target.endswith("/" + hint)
                                    ):
                                        if block.search_text in full_contents[target]:
                                            per_file_blocks[target].append(block)
                                            routed = True
                                            break
                                # Hint matched a target but search text not found
                                if not routed and any(
                                    os.path.basename(t) == hint_basename
                                    for t in full_contents
                                ):
                                    # Still route to the hinted file — it will
                                    # fail during apply_edit_blocks and be
                                    # recorded as a failed block with a clear
                                    # error message.
                                    for target in full_contents:
                                        if os.path.basename(target) == hint_basename:
                                            per_file_blocks[target].append(block)
                                            routed = True
                                            break

                            # Content-based fallback (no file_hint or hint
                            # didn't match any target)
                            if not routed:
                                matching_targets = [
                                    t for t, fc in full_contents.items()
                                    if block.search_text in fc
                                ]
                                if len(matching_targets) == 1:
                                    per_file_blocks[matching_targets[0]].append(block)
                                    routed = True
                                elif len(matching_targets) > 1:
                                    # R2-I5: Multi-file match — scope to first
                                    # match only and warn.
                                    preview = block.search_text[:80].replace("\n", "\\n")
                                    self.logger.warning(
                                        "R2-I5: S/R block %d matches %d files %s "
                                        "— scoping to first match %s only. "
                                        "Search text: %r",
                                        block.block_index,
                                        len(matching_targets),
                                        matching_targets,
                                        matching_targets[0],
                                        preview,
                                    )
                                    per_file_blocks[matching_targets[0]].append(block)
                                    routed = True

                            if not routed:
                                unrouted_blocks.append(block)

                        if unrouted_blocks:
                            for ub in unrouted_blocks:
                                preview = ub.search_text[:80].replace("\n", "\\n")
                                all_failed.append(
                                    f"(unrouted): Block {ub.block_index}: "
                                    f"search text not found in any target file: {preview!r}"
                                )

                        for target, fc in full_contents.items():
                            target_blocks = per_file_blocks[target]
                            if not target_blocks:
                                # No blocks routed to this file — keep original
                                applied_files[target] = fc
                                continue
                            result = apply_edit_blocks(fc, target_blocks)
                            if result.failed:
                                for _block, reason in result.failed:
                                    all_failed.append(f"{target}: {reason}")
                                self.logger.warning(
                                    "Edit blocks partially failed for %s: %d/%d applied",
                                    target,
                                    result.applied,
                                    len(target_blocks),
                                )
                            applied_files[target] = result.content

                        if all_failed:
                            chunk.metadata["_search_replace_failed_blocks"] = len(all_failed)
                            self.logger.warning(
                                "Search/replace had %d failed block(s): %s",
                                len(all_failed),
                                "; ".join(all_failed[:3]),
                            )
                        else:
                            chunk.metadata["_search_replace_failed_blocks"] = 0

                        # I-6: When >30% of S/R blocks fail, the partial result
                        # is unreliable — fall back to whole-file extraction
                        # ONLY for create-mode tasks.  For edit-mode tasks,
                        # whole-file fallback destroys existing code, so we
                        # keep the partial S/R results instead.
                        if blocks and len(all_failed) / len(blocks) > 0.3:
                            _edit_mode_meta = chunk.metadata.get("_edit_mode")
                            _is_edit_mode = (
                                bool(existing)
                                and _edit_mode_meta is not None
                                and _edit_mode_meta.get("mode") == "edit"
                            )
                            if _is_edit_mode:
                                # R2-I2: Edit-mode — keep partial S/R results
                                # to preserve existing code.  Whole-file
                                # fallback would replace the entire file with
                                # just the LLM output, losing existing code.
                                self.logger.warning(
                                    "Chunk %s: %d/%d S/R blocks failed (%.0f%%) "
                                    "— keeping partial S/R result (edit-mode: "
                                    "whole-file fallback would destroy existing code)",
                                    chunk.chunk_id,
                                    len(all_failed),
                                    len(blocks),
                                    len(all_failed) / len(blocks) * 100,
                                )
                                written_files = self._write_applied_files(
                                    applied_files, chunk,
                                )
                            else:
                                self.logger.warning(
                                    "Chunk %s: %d/%d S/R blocks failed (%.0f%%) "
                                    "— falling back to whole-file extraction",
                                    chunk.chunk_id,
                                    len(all_failed),
                                    len(blocks),
                                    len(all_failed) / len(blocks) * 100,
                                )
                                from startd8.utils.code_extraction import (
                                    extract_code_from_response,
                                )
                                code = extract_code_from_response(response_text)
                                if code and code.strip():
                                    written_files = self._write_generated_files(
                                        code, chunk,
                                    )
                                else:
                                    # Fallback extraction also empty — use partial S/R result
                                    self.logger.warning(
                                        "Chunk %s: whole-file fallback also empty "
                                        "— using partial S/R result",
                                        chunk.chunk_id,
                                    )
                                    written_files = self._write_applied_files(
                                        applied_files, chunk,
                                    )
                        else:
                            written_files = self._write_applied_files(applied_files, chunk)
                    else:
                        # Markers present but no valid blocks parsed — fall through
                        self.logger.warning(
                            "Chunk %s: search/replace markers found but no valid "
                            "blocks parsed — falling back to whole-file extraction",
                            chunk.chunk_id,
                        )
                        from startd8.utils.code_extraction import extract_code_from_response
                        code = extract_code_from_response(response_text)
                        if not code or not code.strip():
                            return False, "LLM returned empty code after extraction"
                        written_files = self._write_generated_files(code, chunk)
                else:
                    # LLM ignored search/replace format — whole-file fallback
                    self.logger.info(
                        "Chunk %s: LLM did not use search/replace format — "
                        "falling back to whole-file extraction",
                        chunk.chunk_id,
                    )
                    from startd8.utils.code_extraction import extract_code_from_response
                    code = extract_code_from_response(response_text)
                    if not code or not code.strip():
                        return False, "LLM returned empty code after extraction"
                    written_files = self._write_generated_files(code, chunk)
            else:
                # Whole-file path (create mode or small edit)
                from startd8.utils.code_extraction import extract_code_from_response
                code = extract_code_from_response(response_text)
                if not code or not code.strip():
                    return False, "LLM returned empty code after extraction"
                written_files = self._write_generated_files(code, chunk)

            # ── Check for missing target files ────────────────────────
            missing: Set[str] = set()
            if written_files and chunk.file_targets:
                missing = _detect_missing_targets(
                    expected_targets=chunk.file_targets,
                    written_files=written_files,
                    output_dir=self._output_dir,
                )
                if missing:
                    chunk.metadata["_missing_targets"] = sorted(missing)
                    self.logger.warning(
                        "IMPLEMENT: chunk %s missing %d of %d target files: %s",
                        chunk.chunk_id,
                        len(missing),
                        len(chunk.file_targets),
                        sorted(missing),
                    )

            # ── T2 Refinement pass (REQ-CMR-020/022) ──────────────────
            refine_info: Dict[str, Any] = {}
            _attempt_t2, _t2_reason = self._decide_t2_refinement(
                complexity_tier=_complexity_tier,
                written_files=written_files,
                missing_targets=missing,
                chunk=chunk,
            )
            if _t2_reason == "tier_1":
                self.logger.info(
                    "CMR: Tier 1 — skipping T2 refinement for chunk %s",
                    chunk.chunk_id,
                )
            elif _t2_reason == "tier2_gate_clear":
                self.logger.info(
                    "CMR: Tier 2 gate escalation skipped for chunk %s (no gate issues)",
                    chunk.chunk_id,
                )
            elif _attempt_t2 and _t2_reason != "default_refine":
                self.logger.info(
                    "CMR: Tier 2 gate escalation for chunk %s (reasons=%s)",
                    chunk.chunk_id,
                    _t2_reason,
                )

            # R2-I8: Track T2 status with distinct values so downstream
            # analysis can distinguish intentional skips from failures.
            #   "skipped"   — T2 intentionally not attempted (with reason)
            #   "failed"    — T2 attempted but failed (with error details)
            #   "completed" — T2 attempted and succeeded
            _t2_status: str = "skipped"  # default; overwritten below
            _t2_error: Optional[str] = None

            if _attempt_t2:
                refined_result = await self._refine_written_files(
                    written_files, task_desc, chunk, context,
                )
                if refined_result is not None:
                    written_files, refine_info = refined_result
                    _t2_status = "completed"
                else:
                    # R2-I8: T2 was attempted but returned None (failed).
                    _t2_status = "failed"
                    _failure_detail = chunk.metadata.pop("_t2_failure_detail", None)
                    _t2_error = (
                        f"T2 refinement failed: {_failure_detail}"
                        if _failure_detail
                        else "T2 refinement returned None — extraction empty "
                             "or refiner unavailable (keeping T1 output)"
                    )
                    # REQ-CMR-032: record attempted-but-not-applied refinement path.
                    emit_forensic_log(
                        call_type="implement.chunk.refine",
                        call={
                            "prompt_length": 0,
                            "max_tokens": self._artisan_max_tokens,
                            "model_spec": self._refiner_spec,
                            "response_time_ms": 0,
                            "tokens_input": 0,
                            "tokens_output": 0,
                            "cost_usd": 0.0,
                            "t2_decision": "attempted_keep_t1",
                            "reason": _t2_reason,
                        },
                        task={
                            "task_id": chunk.chunk_id,
                            "title": chunk.description,
                            "phase": "implement",
                            "target_files": chunk.file_targets,
                        },
                        context_propagation={
                            "tier": "T2",
                            "decision": "attempted_keep_t1",
                            "reason": _t2_reason,
                        },
                    )
            else:
                _t2_status = "skipped"
                # REQ-CMR-032: explicit forensic record for T2 skip decision.
                emit_forensic_log(
                    call_type="implement.chunk.refine",
                    call={
                        "prompt_length": 0,
                        "max_tokens": self._artisan_max_tokens,
                        "model_spec": self._refiner_spec,
                        "response_time_ms": 0,
                        "tokens_input": 0,
                        "tokens_output": 0,
                        "cost_usd": 0.0,
                        "t2_decision": "skipped",
                        "reason": _t2_reason,
                    },
                    task={
                        "task_id": chunk.chunk_id,
                        "title": chunk.description,
                        "phase": "implement",
                        "target_files": chunk.file_targets,
                    },
                    context_propagation={
                        "tier": "T2",
                        "decision": "skipped",
                        "reason": _t2_reason,
                    },
                )

            # ── Accumulate cost metrics (T1 + T2) ────────────────────
            t1_cost = token_usage.cost_estimate
            t2_cost = refine_info.get("refine_cost_usd", 0.0)
            cost = t1_cost + t2_cost

            context["_llm_cost_usd"] = context.get("_llm_cost_usd", 0.0) + cost
            context["_llm_input_tokens"] = (
                context.get("_llm_input_tokens", 0)
                + token_usage.input
                + refine_info.get("refine_input_tokens", 0)
            )
            context["_llm_output_tokens"] = (
                context.get("_llm_output_tokens", 0)
                + token_usage.output
                + refine_info.get("refine_output_tokens", 0)
            )

            # Store per-chunk cost in metadata for detailed reporting
            chunk.metadata["llm_cost_usd"] = cost
            chunk.metadata["llm_input_tokens"] = token_usage.input
            chunk.metadata["llm_output_tokens"] = token_usage.output
            chunk.metadata["llm_time_ms"] = time_ms
            chunk.metadata["llm_model"] = getattr(drafter, "model", _effective_drafter_spec)
            chunk.metadata["generated_files"] = [str(p) for p in written_files]
            # CMR: record effective drafter and T2 decision (REQ-CMR-032)
            chunk.metadata["drafter_model"] = _effective_drafter_spec
            chunk.metadata["t2_skipped"] = not bool(refine_info)
            chunk.metadata["t2_decision_reason"] = _t2_reason
            # R2-I8: Distinct t2_status — "skipped" / "failed" / "completed"
            chunk.metadata["t2_status"] = _t2_status
            if _t2_error is not None:
                chunk.metadata["t2_error"] = _t2_error
            # T2 refinement metadata
            if refine_info:
                chunk.metadata["refine_cost_usd"] = t2_cost
                chunk.metadata["refine_input_tokens"] = refine_info.get("refine_input_tokens", 0)
                chunk.metadata["refine_output_tokens"] = refine_info.get("refine_output_tokens", 0)
                chunk.metadata["refine_time_ms"] = refine_info.get("refine_time_ms", 0)
                chunk.metadata["refine_model"] = refine_info.get("refine_model", "")
            # iterations = 2 when T2 ran, 1 otherwise
            iterations = 2 if refine_info else 1
            chunk.metadata["iterations"] = iterations

            # ── Build GenerationResult for downstream phases ──────────
            from startd8.contractors.protocols import GenerationResult
            gen_result = GenerationResult(
                success=True,
                generated_files=written_files,
                input_tokens=token_usage.input + refine_info.get("refine_input_tokens", 0),
                output_tokens=token_usage.output + refine_info.get("refine_output_tokens", 0),
                cost_usd=cost,
                iterations=iterations,
                model=getattr(drafter, "model", self._drafter_spec),
            )
            chunk.metadata["_generation_result"] = gen_result

            # ── Post-generation manifest comparison (IM-5) ─────────────
            self._manifest_post_generate_diff(written_files, chunk, context)

            # ── Post-generation scope validation ──────────────────────
            design_doc = chunk.metadata.get("design_document")
            if design_doc and written_files:
                design_lines = chunk.metadata.get("_design_lines") or len(
                    design_doc.strip().splitlines()
                )
                total_output_lines = 0
                for gen_file in written_files:
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
                if scope_ratio < _SCOPE_MISMATCH_RATIO_THRESHOLD and total_output_lines < _SCOPE_MISMATCH_MIN_OUTPUT_LINES:
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
                "Chunk %s: generation succeeded (%d files, $%.4f)",
                chunk.chunk_id,
                len(written_files),
                cost,
            )
            file_list = ", ".join(str(f) for f in written_files)
            return True, f"Generated files: {file_list}"

        except Exception as e:
            self.logger.exception(
                "Artisan execution failed for chunk %s: %s",
                chunk.chunk_id,
                e,
            )
            return False, f"Artisan execution error: {str(e)}"


class DefaultTestRunner(TestRunner):
    """Default test runner that executes shell commands via subprocess.

    Each test command is run sequentially. If any command fails
    (non-zero exit code) or times out, the entire test suite for
    the chunk is considered failed.
    """

    def __init__(self, timeout: int = _DEFAULT_TEST_TIMEOUT_SECONDS):
        """
        Initialize the default test runner.

        Args:
            timeout: Timeout in seconds for each individual test command.
        """
        self.timeout = timeout
        self.logger = get_logger(__name__)

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
        self.logger = get_logger(__name__)

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
                Default: get_logger(__name__).
            domain_checklist: Optional DomainChecklist instance for injecting
                domain-aware prompt constraints into chunk execution context.
        """
        if max_parallel < 1:
            raise ValueError("max_parallel must be >= 1")

        self.executor = executor or DefaultChunkExecutor()
        self.test_runner = test_runner or DefaultTestRunner()
        self.state_store = state_store or JsonFileStateStore()
        self.max_parallel = max_parallel
        self.logger = logger or get_logger(__name__)
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
            "walkthrough": plan.config.get("walkthrough", False),
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
        state_lock = asyncio.Lock()

        async def _run_with_semaphore(cid: str) -> None:
            async with semaphore:
                chunk = chunk_map[cid]
                async with state_lock:
                    state = states[cid]
                chunk_context = copy.deepcopy(context)  # Per-chunk deep copy to avoid race conditions
                try:
                    result = await self._execute_chunk(chunk, state, chunk_context)
                except Exception as exc:
                    self.logger.exception(
                        "Chunk %s raised unexpected exception: %s", cid, exc,
                    )
                    state.status = ChunkStatus.FAILED
                    state.last_error = f"Unexpected exception: {type(exc).__name__}: {exc}"
                    result = state
                async with state_lock:
                    states[cid] = result

        try:
            await asyncio.gather(*[_run_with_semaphore(cid) for cid in eligible])
        except BaseException as gather_exc:
            self.logger.warning(
                "asyncio.gather raised %s during concurrent chunk execution; "
                "Chunks use context managers and exception guards for span cleanup, "
                "%d of %d chunks have results in state dict. "
                "Partial state will be returned for persistence.",
                type(gather_exc).__name__,
                sum(1 for s in states.values() if s.status in (ChunkStatus.PASSED, ChunkStatus.FAILED)),
                len(eligible),
            )
            raise

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
        _chunk_span_cm = _implement_tracer.start_as_current_span(
            f"implement.chunk.{chunk.chunk_id}",
            attributes={
                "chunk.id": chunk.chunk_id,
                "chunk.file_targets": ",".join(chunk.file_targets[:5]),
                "chunk.max_retries": chunk.max_retries,
            },
        )
        _chunk_span = _chunk_span_cm.__enter__()
        try:
            result = await self._execute_chunk_inner(chunk, state, context, max_attempts, _chunk_span, _chunk_span_cm)
        except BaseException:
            _chunk_span_cm.__exit__(*sys.exc_info())
            raise
        else:
            _chunk_span_cm.__exit__(None, None, None)
        return result

    async def _execute_chunk_inner(
        self,
        chunk: "DevelopmentChunk",
        state: "ChunkState",
        context: "ExecutionContext",
        max_attempts: int,
        _chunk_span: Any,
        _chunk_span_cm: Any,
    ) -> "ChunkState":
        """Inner execution loop for a single chunk, wrapped by span try/finally."""
        if _chunk_span and hasattr(_chunk_span, "set_attribute"):
            _signals = chunk.metadata.get("_complexity_signals", {}) or {}
            _chunk_span.set_attribute(
                AttributeKeys.TASK_COMPLEXITY_TIER,
                chunk.metadata.get("_complexity_tier", _DEFAULT_COMPLEXITY_TIER.value),
            )
            _chunk_span.set_attribute(
                AttributeKeys.TASK_BLAST_RADIUS,
                int(_signals.get("blast_radius", 0) or 0),
            )
            _chunk_span.set_attribute(
                AttributeKeys.TASK_CALLER_COUNT,
                int(_signals.get("caller_count", 0) or 0),
            )
            _chunk_span.set_attribute(
                AttributeKeys.TASK_HAS_DYNAMIC_DISPATCH,
                bool(_signals.get("has_dynamic_dispatch", False)),
            )

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
                f"Chunk {chunk.chunk_id}: attempt {attempt_label} "
                f"(phase elapsed {elapsed_s:.1f}s / {elapsed_m:.2f}min)"
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
                            f"Chunk {chunk.chunk_id}: domain={enrichment.domain.value}, "
                            f"{len(enrichment.prompt_constraints)} constraints injected"
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
                            except ImportError:
                                pass  # OTel not installed — non-fatal
                        except (OSError, TypeError, ValueError) as _prop_err:
                            self.logger.debug(
                                f"Chunk {chunk.chunk_id}: propagation tracking failed (non-fatal): {_prop_err}"
                            )
                except Exception as e:
                    self.logger.warning(
                        f"Chunk {chunk.chunk_id}: domain checklist failed (non-fatal): {e}"
                    )

            # --- Inject retry feedback for error-informed retries ---
            if state.attempts > 1 and state.last_error:
                context["last_error"] = state.last_error
                if state.test_output:
                    context["test_output"] = state.test_output
                self.logger.debug(
                    f"Chunk {chunk.chunk_id}: injecting retry feedback (attempt {attempt_label})"
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
                                        f"Chunk {chunk.chunk_id}: post-gen {issue.validator}: "
                                        f"{issue.message} (line {issue.line})"
                                    )
                    except Exception as e:
                        self.logger.debug(f"Post-validation skipped: {e}")

            except Exception as e:
                self.logger.exception(
                    f"Chunk {chunk.chunk_id}: unexpected execution error: {e}"
                )
                state.last_error = f"Execution exception: {e}"
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
                state.last_error = f"Test exception: {e}"
                continue

            # --- PASSED ---
            state.status = ChunkStatus.PASSED
            state.completed_at = datetime.now(timezone.utc).isoformat()
            self.logger.info(
                f"Chunk {chunk.chunk_id}: PASSED (attempt {attempt_label})"
            )
            if _chunk_span and hasattr(_chunk_span, "set_attribute"):
                _chunk_span.set_attribute("chunk.status", "passed")
                _chunk_span.set_attribute("chunk.attempts", state.attempts)
            return state

        # All retries exhausted
        state.status = ChunkStatus.FAILED
        state.completed_at = datetime.now(timezone.utc).isoformat()
        self.logger.error(
            f"Chunk {chunk.chunk_id}: FAILED after {state.attempts} "
            f"attempt(s). Last error: {state.last_error}"
        )
        if _chunk_span and hasattr(_chunk_span, "set_attribute"):
            _chunk_span.set_attribute("chunk.status", "failed")
            _chunk_span.set_attribute("chunk.attempts", state.attempts)
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
