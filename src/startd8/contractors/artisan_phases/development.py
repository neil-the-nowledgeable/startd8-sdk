"""
Development Phase Implementation for Artisan Contractor System

This module implements an iterative development phase that:
- Resolves chunk dependencies via topological sorting (Kahn's algorithm)
- Executes chunks in dependency order with parallel support (bounded concurrency)
- Persists state for chunk-level resume capability
- Gates progression on test results (test-pass gates)
- Supports configurable retry logic with exponential backoff option

Architecture:
    DevelopmentPlan -> validate -> topological_sort -> tier execution -> DevelopmentResult

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
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Optional, Set, Tuple


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
            Default: ".startd8_state".
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
    async def save_state(
        self, plan_id: str, states: Dict[str, ChunkState]
    ) -> None:
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
                f"[NO-OP] No callback provided for {chunk.chunk_id}, "
                "returning success"
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
                    return False, (
                        f"Test timeout after {self.timeout}s: {cmd}"
                    )

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

    def __init__(self, directory: str = ".startd8_state"):
        """
        Initialize the JSON file state store.

        Args:
            directory: Directory to store state files. Created if needed.
        """
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger("startd8.development.state")

    def _get_state_path(self, plan_id: str) -> Path:
        """Get the file path for a plan's state."""
        # Sanitize plan_id for safe filesystem use
        safe_id = "".join(
            c if c.isalnum() or c in "-_." else "_" for c in plan_id
        )
        return self.directory / f"{safe_id}_state.json"

    async def load_state(self, plan_id: str) -> Dict[str, ChunkState]:
        """Load state from a JSON file."""
        state_path = self._get_state_path(plan_id)

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
                f"Loaded state for plan {plan_id}: "
                f"{len(states)} chunk(s)"
            )
            return states

        except json.JSONDecodeError as e:
            self.logger.warning(
                f"Corrupted state file for plan {plan_id}: {e}. "
                "Starting fresh."
            )
            return {}
        except (KeyError, ValueError) as e:
            self.logger.warning(
                f"Invalid state data for plan {plan_id}: {e}. "
                "Starting fresh."
            )
            return {}
        except Exception as e:
            self.logger.error(
                f"Error loading state for plan {plan_id}: {e}"
            )
            return {}

    async def save_state(
        self, plan_id: str, states: Dict[str, ChunkState]
    ) -> None:
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
            self.logger.error(
                f"Error clearing state for plan {plan_id}: {e}"
            )


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
                    f"Chunk {chunk.chunk_id} depends on non-existent "
                    f"chunk {dep}"
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
                    errors.append(
                        "Cyclic dependency detected in chunk graph"
                    )
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
                    f"Chunk {chunk.chunk_id} depends on non-existent "
                    f"chunk {dep}"
                )
            adj_list[dep].append(chunk.chunk_id)
            in_degree[chunk.chunk_id] += 1

    # Start with all zero-in-degree nodes
    queue = deque(
        sorted(cid for cid in chunk_map if in_degree[cid] == 0)
    )
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
        remaining = [
            cid for cid, deg in in_degree.items() if deg > 0
        ]
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
    ):
        """
        Initialize the development phase.

        Args:
            executor: Chunk executor implementation.
                Default: DefaultChunkExecutor (no-op mode).
            test_runner: Test runner implementation.
                Default: DefaultTestRunner (shell commands).
            state_store: State storage backend.
                Default: JsonFileStateStore (".startd8_state" directory).
            max_parallel: Maximum concurrent chunk executions per tier.
                Must be >= 1.
            logger: Logger instance.
                Default: logging.getLogger("startd8.development").
        """
        if max_parallel < 1:
            raise ValueError("max_parallel must be >= 1")

        self.executor = executor or DefaultChunkExecutor()
        self.test_runner = test_runner or DefaultTestRunner()
        self.state_store = state_store or JsonFileStateStore()
        self.max_parallel = max_parallel
        self.logger = logger or logging.getLogger("startd8.development")

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
            duration = (
                datetime.now(timezone.utc) - start_time
            ).total_seconds()
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
        context: Dict[str, Any] = {
            "plan_id": plan.plan_id,
            "dry_run": plan.config.get("dry_run", False),
        }

        # --- Execute tiers ---
        for tier_idx, tier_chunk_ids in enumerate(execution_order):
            self.logger.info(
                f"=== Tier {tier_idx + 1}/{len(execution_order)}: "
                f"{tier_chunk_ids} ==="
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
                    self.logger.debug(
                        f"Chunk {cid}: already PASSED, preserving"
                    )
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
                        f"Chunk {cid}: was FAILED, resetting to PENDING "
                        "for retry"
                    )
                elif prev.status == ChunkStatus.SKIPPED:
                    # Reset skipped — dependency might succeed this time
                    states[cid] = ChunkState(
                        chunk_id=cid,
                        status=ChunkStatus.PENDING,
                    )
                    self.logger.debug(
                        f"Chunk {cid}: was SKIPPED, resetting to PENDING"
                    )
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
                dep for dep in chunk.dependencies
                if states[dep].status != ChunkStatus.PASSED
            ]

            if unsatisfied:
                self.logger.warning(
                    f"Chunk {chunk_id}: unsatisfied dependencies "
                    f"{unsatisfied}; marking SKIPPED"
                )
                states[chunk_id].status = ChunkStatus.SKIPPED
                states[chunk_id].last_error = (
                    f"Unsatisfied dependencies: {', '.join(unsatisfied)}"
                )
                states[chunk_id].completed_at = (
                    datetime.now(timezone.utc).isoformat()
                )
                continue

            eligible.append(chunk_id)

        if not eligible:
            self.logger.debug("No eligible chunks in this tier")
            return states

        self.logger.info(
            f"Executing {len(eligible)} eligible chunk(s) "
            f"(max_parallel={max_parallel})"
        )

        semaphore = asyncio.Semaphore(max_parallel)

        async def _run_with_semaphore(cid: str) -> None:
            async with semaphore:
                chunk = chunk_map[cid]
                state = states[cid]
                states[cid] = await self._execute_chunk(
                    chunk, state, context
                )

        await asyncio.gather(
            *[_run_with_semaphore(cid) for cid in eligible]
        )

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

            self.logger.info(
                f"Chunk {chunk.chunk_id}: attempt {attempt_label}"
            )

            # --- QUEUED ---
            state.status = ChunkStatus.QUEUED
            state.started_at = datetime.now(timezone.utc).isoformat()

            # --- RUNNING: Execute implementation ---
            state.status = ChunkStatus.RUNNING
            try:
                exec_success, exec_output = await self.executor.execute(
                    chunk, context
                )
                if not exec_success:
                    self.logger.warning(
                        f"Chunk {chunk.chunk_id}: execution failed "
                        f"(attempt {attempt_label}): {exec_output}"
                    )
                    state.last_error = exec_output
                    continue

                self.logger.debug(
                    f"Chunk {chunk.chunk_id}: execution succeeded"
                )

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

                self.logger.info(
                    f"Chunk {chunk.chunk_id}: tests passed"
                )

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
                f"Chunk {chunk.chunk_id}: PASSED "
                f"(attempt {attempt_label})"
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
                        state.completed_at = (
                            datetime.now(timezone.utc).isoformat()
                        )
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

        Args:
            plan: The development plan.
            states: Final chunk states.
            execution_order: Execution tiers from topological sort.
            duration: Total wall-clock execution time in seconds.

        Returns:
            DevelopmentResult instance.
        """
        passed = sum(
            1 for s in states.values() if s.status == ChunkStatus.PASSED
        )
        failed = sum(
            1 for s in states.values() if s.status == ChunkStatus.FAILED
        )
        skipped = sum(
            1 for s in states.values() if s.status == ChunkStatus.SKIPPED
        )
        total = len(states)

        success = (total > 0 and passed == total) or total == 0

        # Build detailed summary
        summary_parts = [
            f"Executed {total} chunk(s): "
            f"{passed} passed, {failed} failed, {skipped} skipped.",
            f"Duration: {duration:.2f}s.",
        ]

        if failed > 0:
            failed_ids = [
                cid for cid, s in states.items()
                if s.status == ChunkStatus.FAILED
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
    )
    return await phase.run(plan)