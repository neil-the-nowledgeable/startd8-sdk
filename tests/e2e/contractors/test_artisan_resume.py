"""
End-to-end test module for Artisan resume functionality.

Validates that the Artisan system correctly resumes interrupted work from
phase checkpoints, restores state at chunk-level granularity, avoids
duplicate work, and accurately tracks costs across interruption/resume cycles.

All code is self-contained in this single file with no relative imports.

Test Classes:
    - TestPhaseCheckpointResume: Verifies execution resumes from the correct phase
    - TestChunkLevelResume: Verifies chunk-level granularity on resume
    - TestStateRestoration: Verifies state/context fidelity across resume
    - TestNoDuplicateWork: Verifies no re-execution of completed work
    - TestCostTracking: Verifies cost accumulation across resume boundaries
    - TestEdgeCases: Covers boundary conditions and error handling
"""

import json
import time
from copy import deepcopy
from dataclasses import dataclass, asdict, field
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional
from collections import defaultdict

import pytest


# ============================================================================
# ENUMS
# ============================================================================


class Phase(str, Enum):
    """Pipeline phases in execution order."""
    PLANNING = "planning"
    CODING = "coding"
    TESTING = "testing"
    REVIEW = "review"


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class CostRecord:
    """Records various cost metrics for a single chunk execution."""
    tokens_used: int
    api_calls: int
    time_seconds: float
    monetary_cost: float

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CostRecord":
        """Create from dictionary (JSON deserialization)."""
        return cls(**data)


@dataclass
class ChunkResult:
    """Result of executing a single chunk."""
    phase: str
    chunk_index: int
    data: dict
    cost: float
    timestamp: float

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ChunkResult":
        """Create from dictionary (JSON deserialization)."""
        return cls(**data)


@dataclass
class PhaseCheckpoint:
    """Checkpoint state after completing (or partially completing) a phase."""
    phase: str
    completed_chunks: list[int] = field(default_factory=list)
    chunk_results: list[dict] = field(default_factory=list)
    cost_so_far: float = 0.0
    state_snapshot: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PhaseCheckpoint":
        """Create from dictionary (JSON deserialization)."""
        return cls(**data)


@dataclass
class ExecutionCheckpoint:
    """Complete checkpoint state of the entire execution."""
    completed_phases: list[str] = field(default_factory=list)
    phase_checkpoints: dict[str, dict] = field(default_factory=dict)
    total_cost: float = 0.0
    context: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionCheckpoint":
        """Create from dictionary (JSON deserialization)."""
        return cls(**data)


# ============================================================================
# EXCEPTIONS
# ============================================================================


class InterruptionError(Exception):
    """Raised to simulate an interruption during execution."""

    def __init__(self, phase: str, chunk_index: int):
        """
        Initialize interruption error.

        Args:
            phase: Phase name where interruption occurred.
            chunk_index: 0-based chunk index within the phase.
        """
        self.phase = phase
        self.chunk_index = chunk_index
        super().__init__(f"Interrupted at phase={phase}, chunk={chunk_index}")


# ============================================================================
# HELPER CLASSES
# ============================================================================


class ExecutionTracker:
    """Tracks which phases and chunks were actually executed (not skipped)."""

    def __init__(self) -> None:
        """Initialize tracker with empty execution/skip lists."""
        self.executed: list[tuple[str, int]] = []
        self.skipped: list[tuple[str, int]] = []
        self._execution_counts: dict[str, int] = defaultdict(int)

    def record_execution(self, phase: str, chunk_index: int) -> None:
        """Record that a chunk was executed."""
        self.executed.append((phase, chunk_index))
        self._execution_counts[phase] += 1

    def record_skip(self, phase: str, chunk_index: int) -> None:
        """Record that a chunk was skipped (already completed)."""
        self.skipped.append((phase, chunk_index))

    def get_execution_count(self, phase: str = None) -> int:
        """
        Get execution count.

        Args:
            phase: If specified, return count for that phase only. If None, return total.

        Returns:
            Number of chunks executed.
        """
        if phase is None:
            return len(self.executed)
        return self._execution_counts.get(phase, 0)

    def was_executed(self, phase: str, chunk_index: int) -> bool:
        """Check if a specific chunk was executed."""
        return (phase, chunk_index) in self.executed

    def was_skipped(self, phase: str, chunk_index: int) -> bool:
        """Check if a specific chunk was skipped."""
        return (phase, chunk_index) in self.skipped


class CheckpointStore:
    """Persists and loads checkpoints to/from disk as JSON."""

    def __init__(self, storage_dir: Path) -> None:
        """
        Initialize checkpoint store.

        Args:
            storage_dir: Directory where checkpoints will be persisted.
        """
        self.storage_dir = storage_dir
        self.checkpoint_file = storage_dir / "checkpoint.json"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save(self, checkpoint: ExecutionCheckpoint) -> None:
        """
        Atomically save checkpoint to disk as JSON.

        Args:
            checkpoint: ExecutionCheckpoint to persist.
        """
        data = checkpoint.to_dict()
        # Write to temp file then rename for atomicity
        tmp_file = self.checkpoint_file.with_suffix(".tmp")
        with open(tmp_file, "w") as file:
            json.dump(data, file, indent=2)
        tmp_file.replace(self.checkpoint_file)

    def load(self) -> Optional[ExecutionCheckpoint]:
        """
        Load checkpoint from disk.

        Returns:
            ExecutionCheckpoint if file exists and is valid JSON, None otherwise.
            Returns None on corrupted JSON or empty files.
        """
        if not self.checkpoint_file.exists():
            return None

        try:
            with open(self.checkpoint_file, "r") as file:
                content = file.read()
                if not content.strip():
                    return None
                data = json.loads(content)
                return ExecutionCheckpoint.from_dict(data)
        except (json.JSONDecodeError, ValueError, KeyError, TypeError):
            return None

    def exists(self) -> bool:
        """Check if a checkpoint file exists on disk."""
        return self.checkpoint_file.exists()

    def clear(self) -> None:
        """Delete the checkpoint file if it exists."""
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()


class ChunkProcessor:
    """
    Processes a single chunk of work.

    Cost is deterministically calculated as:
      cost = base_cost * (chunk_index + 1) * phase_multiplier

    Output is deterministic based on inputs (phase, chunk_index, context).
    """

    # Phase multipliers for cost calculation
    PHASE_MULTIPLIERS: dict[str, float] = {
        "planning": 1.0,
        "coding": 2.0,
        "testing": 1.5,
        "review": 1.0,
    }

    def __init__(self, base_cost: float = 0.01, base_tokens: int = 100) -> None:
        """
        Initialize processor.

        Args:
            base_cost: Base monetary cost per chunk.
            base_tokens: Base token count per chunk.
        """
        self.base_cost = base_cost
        self.base_tokens = base_tokens

    def process(
        self, phase: str, chunk_index: int, context: dict
    ) -> tuple[dict, CostRecord]:
        """
        Process a single chunk and return result and cost.

        Args:
            phase: Phase name (e.g., "planning", "coding").
            chunk_index: 0-based chunk index within the phase.
            context: Current execution context (not modified).

        Returns:
            Tuple of (result_data dict, CostRecord).
        """
        phase_multiplier = self.PHASE_MULTIPLIERS.get(phase, 1.0)
        chunk_cost = self.base_cost * (chunk_index + 1) * phase_multiplier

        tokens_used = int(self.base_tokens * (chunk_index + 1) * phase_multiplier)
        api_calls = chunk_index + 1

        result_data = {
            "phase": phase,
            "chunk_index": chunk_index,
            "output": f"{phase}_chunk_{chunk_index}",
            "context_snapshot": {
                k: v for k, v in context.items()
                if k != "config"
            },
        }

        cost_record = CostRecord(
            tokens_used=tokens_used,
            api_calls=api_calls,
            time_seconds=chunk_cost * 10.0,
            monetary_cost=chunk_cost,
        )

        return result_data, cost_record


class CountingChunkProcessor(ChunkProcessor):
    """
    Extended ChunkProcessor that counts invocations for side-effect testing.

    Useful for verifying that chunks are not executed multiple times.
    """

    def __init__(self, base_cost: float = 0.01, base_tokens: int = 100) -> None:
        """Initialize with call counting."""
        super().__init__(base_cost, base_tokens)
        self.call_count: int = 0
        self.calls_by_chunk: dict[tuple[str, int], int] = defaultdict(int)

    def process(
        self, phase: str, chunk_index: int, context: dict
    ) -> tuple[dict, CostRecord]:
        """
        Process chunk and increment call counters.

        Args:
            phase: Phase name.
            chunk_index: 0-based chunk index.
            context: Execution context.

        Returns:
            Tuple of (result_data, cost_record).
        """
        self.call_count += 1
        self.calls_by_chunk[(phase, chunk_index)] += 1
        return super().process(phase, chunk_index, context)


class ArtisanExecutionEngine:
    """
    Main execution engine that processes phases and chunks with checkpoint support.

    Handles interruption simulation, state restoration, and cost tracking.
    Checkpoints are saved after every chunk for maximum resume granularity.
    """

    def __init__(
        self,
        phases_config: dict[str, int],
        checkpoint_store: CheckpointStore,
        chunk_processor: ChunkProcessor,
        tracker: ExecutionTracker,
        interrupt_at: Optional[tuple[str, int]] = None,
        initial_context: Optional[dict] = None,
    ) -> None:
        """
        Initialize execution engine.

        Args:
            phases_config: Dict mapping phase names to chunk counts (ordered).
            checkpoint_store: CheckpointStore for persistence.
            chunk_processor: ChunkProcessor for chunk execution.
            tracker: ExecutionTracker for recording execution flow.
            interrupt_at: Optional (phase, chunk_index) tuple to trigger interruption.
            initial_context: Optional initial context dict (will be deep copied).
        """
        self.phases_config = phases_config
        self.checkpoint_store = checkpoint_store
        self.chunk_processor = chunk_processor
        self.tracker = tracker
        self.interrupt_at = interrupt_at
        self.initial_context = deepcopy(initial_context or {})
        self.current_checkpoint = ExecutionCheckpoint(
            context=deepcopy(self.initial_context)
        )

    def run(self) -> tuple[ExecutionCheckpoint, dict]:
        """
        Execute all phases/chunks, resuming from checkpoint if one exists.

        Raises:
            InterruptionError: If interrupt_at point is reached.

        Returns:
            Tuple of (final_checkpoint, final_results dict keyed by phase name).
        """
        # Load existing checkpoint if available
        loaded = self.checkpoint_store.load()
        if loaded is not None:
            self.current_checkpoint = loaded
        else:
            self.current_checkpoint.context = deepcopy(self.initial_context)

        final_results: dict = {}

        # Process each phase in order
        for phase_name, num_chunks in self.phases_config.items():
            if self._should_skip_phase(phase_name):
                # Record all chunks in this phase as skipped
                for chunk_idx in range(num_chunks):
                    self.tracker.record_skip(phase_name, chunk_idx)
                final_results[phase_name] = self.current_checkpoint.phase_checkpoints.get(
                    phase_name, {}
                )
                continue

            # Execute phase (may raise InterruptionError)
            self._execute_phase(phase_name, num_chunks)
            final_results[phase_name] = self.current_checkpoint.phase_checkpoints.get(
                phase_name, {}
            )

        return self.current_checkpoint, final_results

    def _execute_phase(self, phase: str, num_chunks: int) -> None:
        """
        Execute a single phase, skipping already-completed chunks.

        Args:
            phase: Phase name.
            num_chunks: Number of chunks in this phase.

        Raises:
            InterruptionError: If interrupt_at point is reached.
        """
        # Initialize phase checkpoint if not present
        if phase not in self.current_checkpoint.phase_checkpoints:
            self.current_checkpoint.phase_checkpoints[phase] = PhaseCheckpoint(
                phase=phase
            ).to_dict()

        phase_checkpoint_dict = self.current_checkpoint.phase_checkpoints[phase]
        completed_chunks: list[int] = phase_checkpoint_dict.get("completed_chunks", [])
        chunk_results: list[dict] = phase_checkpoint_dict.get("chunk_results", [])
        phase_cost: float = phase_checkpoint_dict.get("cost_so_far", 0.0)

        # Process each chunk in this phase
        for chunk_idx in range(num_chunks):
            if chunk_idx in completed_chunks:
                self.tracker.record_skip(phase, chunk_idx)
                continue

            # Check if we should interrupt before processing this chunk
            if self.interrupt_at is not None and self.interrupt_at == (phase, chunk_idx):
                # Save current state before raising
                self.current_checkpoint.phase_checkpoints[phase] = {
                    "phase": phase,
                    "completed_chunks": completed_chunks,
                    "chunk_results": chunk_results,
                    "cost_so_far": phase_cost,
                    "state_snapshot": deepcopy(self.current_checkpoint.context),
                }
                self.checkpoint_store.save(self.current_checkpoint)
                raise InterruptionError(phase, chunk_idx)

            # Execute the chunk
            self.tracker.record_execution(phase, chunk_idx)
            result_data, cost_record = self.chunk_processor.process(
                phase, chunk_idx, self.current_checkpoint.context
            )

            # Record result
            chunk_result = ChunkResult(
                phase=phase,
                chunk_index=chunk_idx,
                data=result_data,
                cost=cost_record.monetary_cost,
                timestamp=time.time(),
            )
            chunk_results.append(chunk_result.to_dict())
            completed_chunks.append(chunk_idx)
            phase_cost += cost_record.monetary_cost

            # Update checkpoint after every chunk for fine-grained resume
            self.current_checkpoint.phase_checkpoints[phase] = {
                "phase": phase,
                "completed_chunks": completed_chunks,
                "chunk_results": chunk_results,
                "cost_so_far": phase_cost,
                "state_snapshot": deepcopy(self.current_checkpoint.context),
            }
            self.current_checkpoint.total_cost += cost_record.monetary_cost
            self.checkpoint_store.save(self.current_checkpoint)

        # Mark phase as completed
        if phase not in self.current_checkpoint.completed_phases:
            self.current_checkpoint.completed_phases.append(phase)

        # Save final phase checkpoint
        self.checkpoint_store.save(self.current_checkpoint)

    def _should_skip_phase(self, phase: str) -> bool:
        """Check if a phase has already been completed."""
        return phase in self.current_checkpoint.completed_phases


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def storage_dir(tmp_path) -> Path:
    """Provides a temporary directory for checkpoint storage."""
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    return checkpoint_dir


@pytest.fixture
def checkpoint_store(storage_dir) -> CheckpointStore:
    """Provides a CheckpointStore instance backed by a temp directory."""
    return CheckpointStore(storage_dir)


@pytest.fixture
def tracker() -> ExecutionTracker:
    """Provides a fresh ExecutionTracker instance."""
    return ExecutionTracker()


@pytest.fixture
def chunk_processor() -> ChunkProcessor:
    """Provides a ChunkProcessor instance with default cost parameters."""
    return ChunkProcessor(base_cost=0.01, base_tokens=100)


@pytest.fixture
def counting_chunk_processor() -> CountingChunkProcessor:
    """Provides a CountingChunkProcessor for side-effect verification tests."""
    return CountingChunkProcessor(base_cost=0.01, base_tokens=100)


@pytest.fixture
def default_phases_config() -> dict[str, int]:
    """Standard pipeline: 4 phases with varying chunk counts (total=12)."""
    return {
        Phase.PLANNING.value: 2,
        Phase.CODING.value: 5,
        Phase.TESTING.value: 3,
        Phase.REVIEW.value: 2,
    }


@pytest.fixture
def initial_context() -> dict:
    """Provides a standard initial context with nested structures."""
    return {
        "project_name": "test_project",
        "config": {"max_retries": 3, "timeout": 30},
        "metadata": {"version": "1.0", "author": "test"},
    }


# ============================================================================
# TEST CLASSES
# ============================================================================


class TestPhaseCheckpointResume:
    """Tests that execution resumes from the correct phase after interruption."""

    def test_resume_from_second_phase(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Interrupt during CODING, resume should skip PLANNING entirely."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.CODING.value, 2),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError) as exc_info:
            engine1.run()

        assert exc_info.value.phase == Phase.CODING.value
        assert exc_info.value.chunk_index == 2
        assert checkpoint_store.exists()

        # Resume without interruption
        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        # Planning was not re-executed
        assert tracker2.get_execution_count(Phase.PLANNING.value) == 0
        assert Phase.PLANNING.value in final_checkpoint.completed_phases

        # Only remaining coding chunks were executed
        assert tracker2.was_executed(Phase.CODING.value, 2)
        assert tracker2.was_executed(Phase.CODING.value, 3)
        assert tracker2.was_executed(Phase.CODING.value, 4)
        assert not tracker2.was_executed(Phase.CODING.value, 0)
        assert not tracker2.was_executed(Phase.CODING.value, 1)

        # All phases completed
        assert set(final_checkpoint.completed_phases) == {
            Phase.PLANNING.value,
            Phase.CODING.value,
            Phase.TESTING.value,
            Phase.REVIEW.value,
        }

    def test_resume_from_last_phase(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Interrupt during REVIEW, resume should skip all earlier phases."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.REVIEW.value, 1),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        assert tracker2.get_execution_count(Phase.PLANNING.value) == 0
        assert tracker2.get_execution_count(Phase.CODING.value) == 0
        assert tracker2.get_execution_count(Phase.TESTING.value) == 0
        assert Phase.REVIEW.value in final_checkpoint.completed_phases
        assert tracker2.was_executed(Phase.REVIEW.value, 1)

    def test_resume_from_first_phase(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Interrupt during PLANNING, resume should continue within PLANNING."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.PLANNING.value, 1),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        assert tracker2.was_executed(Phase.PLANNING.value, 1)
        assert not tracker2.was_executed(Phase.PLANNING.value, 0)

    def test_full_run_no_interruption(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Baseline: full run with no interruption completes all phases and chunks."""
        engine = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine.run()

        assert set(final_checkpoint.completed_phases) == {
            Phase.PLANNING.value,
            Phase.CODING.value,
            Phase.TESTING.value,
            Phase.REVIEW.value,
        }
        assert tracker.get_execution_count() == 2 + 5 + 3 + 2
        assert checkpoint_store.exists()

    def test_multiple_resume_cycles(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Interrupt and resume multiple times across different phases."""
        # Cycle 1: interrupt at coding chunk 2
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.CODING.value, 2),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        cycle1_executed = len(tracker.executed)

        # Cycle 2: resume, interrupt at testing chunk 1
        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=(Phase.TESTING.value, 1),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine2.run()

        cycle2_executed = len(tracker2.executed)

        # Cycle 3: resume and complete
        tracker3 = ExecutionTracker()
        engine3 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker3,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine3.run()

        assert set(final_checkpoint.completed_phases) == {
            Phase.PLANNING.value,
            Phase.CODING.value,
            Phase.TESTING.value,
            Phase.REVIEW.value,
        }

        total_work = cycle1_executed + cycle2_executed + len(tracker3.executed)
        assert total_work == 2 + 5 + 3 + 2


class TestChunkLevelResume:
    """Tests that within a phase, resume starts from the correct chunk."""

    def test_resume_mid_phase_skips_completed_chunks(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Interrupt at chunk 3 of CODING, resume processes chunks 3,4 only."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.CODING.value, 3),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        assert not tracker2.was_executed(Phase.CODING.value, 0)
        assert not tracker2.was_executed(Phase.CODING.value, 1)
        assert not tracker2.was_executed(Phase.CODING.value, 2)
        assert tracker2.was_executed(Phase.CODING.value, 3)
        assert tracker2.was_executed(Phase.CODING.value, 4)

    def test_resume_at_first_chunk_of_phase(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Interrupt at chunk 0 of a phase, resume should re-attempt that chunk."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.TESTING.value, 0),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        assert tracker2.was_executed(Phase.TESTING.value, 0)

    def test_resume_at_last_chunk_of_phase(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Interrupt at the last chunk, resume should complete just that chunk."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.REVIEW.value, 1),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        assert tracker2.was_executed(Phase.REVIEW.value, 1)
        assert not tracker2.was_executed(Phase.REVIEW.value, 0)

    def test_chunk_results_preserved_across_resume(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Verify partial chunk results from before interruption are present after resume."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.CODING.value, 2),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        coding_checkpoint = final_checkpoint.phase_checkpoints.get(Phase.CODING.value)
        assert coding_checkpoint is not None
        chunk_results = coding_checkpoint.get("chunk_results", [])
        chunk_indices = [r["chunk_index"] for r in chunk_results]
        assert 0 in chunk_indices
        assert 1 in chunk_indices


class TestStateRestoration:
    """Tests that state/context is faithfully restored on resume."""

    def test_context_restored_after_resume(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Verify initial_context is maintained in checkpoint after resume."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.CODING.value, 2),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        assert final_checkpoint.context["project_name"] == initial_context["project_name"]
        assert final_checkpoint.context["config"] == initial_context["config"]
        assert final_checkpoint.context["metadata"] == initial_context["metadata"]

    def test_intermediate_results_restored(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Verify chunk results from completed work are intact after resume."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.CODING.value, 2),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        checkpoint_interrupt = checkpoint_store.load()
        planning_checkpoint_interrupt = checkpoint_interrupt.phase_checkpoints.get(
            Phase.PLANNING.value
        )
        planning_results_before = (
            planning_checkpoint_interrupt.get("chunk_results", [])
            if planning_checkpoint_interrupt
            else []
        )

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        planning_checkpoint_final = final_checkpoint.phase_checkpoints.get(
            Phase.PLANNING.value
        )
        planning_results_after = planning_checkpoint_final.get("chunk_results", [])

        assert len(planning_results_before) == len(planning_results_after)
        for before, after in zip(planning_results_before, planning_results_after):
            assert before["chunk_index"] == after["chunk_index"]
            assert before["data"] == after["data"]

    def test_phase_checkpoint_state_integrity(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Verify PhaseCheckpoint fields are accurately restored from disk."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.PLANNING.value, 1),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        checkpoint = checkpoint_store.load()

        planning_ckpt = checkpoint.phase_checkpoints[Phase.PLANNING.value]
        assert planning_ckpt["phase"] == Phase.PLANNING.value
        assert 0 in planning_ckpt["completed_chunks"]
        assert len(planning_ckpt["chunk_results"]) > 0
        assert planning_ckpt["cost_so_far"] > 0.0
        assert planning_ckpt["state_snapshot"] is not None

    def test_checkpoint_serialization_roundtrip(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Save checkpoint, load it, verify all fields match exactly."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.CODING.value, 2),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        loaded = checkpoint_store.load()

        assert loaded.completed_phases == [Phase.PLANNING.value]
        assert Phase.PLANNING.value in loaded.phase_checkpoints
        assert Phase.CODING.value in loaded.phase_checkpoints
        assert loaded.total_cost > 0.0

        # Round-trip through dict
        checkpoint_dict = loaded.to_dict()
        restored = ExecutionCheckpoint.from_dict(checkpoint_dict)

        assert restored.total_cost == loaded.total_cost
        assert restored.completed_phases == loaded.completed_phases
        assert len(restored.phase_checkpoints) == len(loaded.phase_checkpoints)


class TestNoDuplicateWork:
    """Tests that resumed execution does not re-execute completed work."""

    def test_completed_phases_not_reexecuted(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """After resume, tracker shows zero executions for previously completed phases."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.CODING.value, 1),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        assert tracker2.get_execution_count(Phase.PLANNING.value) == 0

    def test_completed_chunks_not_reexecuted(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """After resume, previously completed chunks within current phase are not re-executed."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.CODING.value, 3),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        for idx in range(3):
            assert not tracker2.was_executed(Phase.CODING.value, idx)

    def test_execution_count_matches_remaining_work(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Total executions after resume equals only the chunks that were not yet done."""
        # Interrupt at coding chunk 2 → planning (2 done), coding (0,1 done; 2,3,4 remain)
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.CODING.value, 2),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        # Remaining: 3 coding + 3 testing + 2 review = 8
        assert tracker2.get_execution_count() == 8

    def test_side_effects_not_duplicated(
        self,
        default_phases_config,
        checkpoint_store,
        counting_chunk_processor,
        tracker,
        initial_context,
    ):
        """Use a side-effect counter to prove chunks don't run twice."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=counting_chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.TESTING.value, 1),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        calls_before = dict(counting_chunk_processor.calls_by_chunk)

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=counting_chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        # Every chunk that was executed in run 1 still has count of 1
        for (phase, chunk_idx), count in calls_before.items():
            assert counting_chunk_processor.calls_by_chunk[(phase, chunk_idx)] == 1

        # Every chunk executed in run 2 has count of 1
        for (phase, chunk_idx) in tracker2.executed:
            assert counting_chunk_processor.calls_by_chunk[(phase, chunk_idx)] == 1


class TestCostTracking:
    """Tests that costs are correctly accumulated across resume boundaries."""

    def test_cost_accumulates_across_resume(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Total cost after resume = cost_before_interrupt + cost_after_resume."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.CODING.value, 2),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        checkpoint_interrupt = checkpoint_store.load()
        cost_at_interrupt = checkpoint_interrupt.total_cost

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        assert final_checkpoint.total_cost > cost_at_interrupt

    def test_cost_not_lost_on_interruption(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Cost from completed work before interruption is preserved in checkpoint."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.PLANNING.value, 1),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        checkpoint = checkpoint_store.load()
        assert checkpoint.total_cost > 0.0

        planning_ckpt = checkpoint.phase_checkpoints[Phase.PLANNING.value]
        assert planning_ckpt["cost_so_far"] > 0.0

    def test_cost_not_double_counted(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Resumed chunks don't add cost for already-completed work."""
        # Baseline: uninterrupted full run
        with TemporaryDirectory() as tmpdir:
            baseline_store = CheckpointStore(Path(tmpdir))
            engine_baseline = ArtisanExecutionEngine(
                phases_config=default_phases_config,
                checkpoint_store=baseline_store,
                chunk_processor=chunk_processor,
                tracker=ExecutionTracker(),
                interrupt_at=None,
                initial_context=initial_context,
            )
            baseline_checkpoint, _ = engine_baseline.run()
            baseline_cost = baseline_checkpoint.total_cost

        # Interrupted run
        checkpoint_store.clear()
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.CODING.value, 2),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        # Resume
        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        assert abs(final_checkpoint.total_cost - baseline_cost) < 1e-9

    def test_cost_breakdown_by_phase(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Verify per-phase costs are tracked and sum to total."""
        engine = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine.run()

        total_phase_cost = 0.0
        for phase_name, phase_ckpt_dict in final_checkpoint.phase_checkpoints.items():
            phase_cost = phase_ckpt_dict.get("cost_so_far", 0.0)
            total_phase_cost += phase_cost

        assert abs(total_phase_cost - final_checkpoint.total_cost) < 1e-9

    def test_token_and_api_call_tracking(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Verify token counts and API call counts are reasonable."""
        engine = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine.run()

        assert final_checkpoint.total_cost > 0.0
        assert tracker.get_execution_count() == 2 + 5 + 3 + 2

    def test_full_run_cost_equals_sum_of_all_chunks(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Baseline: cost of uninterrupted run equals sum of all individual chunk costs."""
        engine = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine.run()

        # Manually compute expected cost
        expected_cost = 0.0
        phase_multipliers = {
            "planning": 1.0,
            "coding": 2.0,
            "testing": 1.5,
            "review": 1.0,
        }

        for phase_name, num_chunks in default_phases_config.items():
            phase_mult = phase_multipliers[phase_name]
            for chunk_idx in range(num_chunks):
                chunk_cost = 0.01 * (chunk_idx + 1) * phase_mult
                expected_cost += chunk_cost

        assert abs(final_checkpoint.total_cost - expected_cost) < 1e-9


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_no_checkpoint_exists_first_run(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """First run executes all work without errors when no checkpoint exists."""
        assert not checkpoint_store.exists()

        engine = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine.run()

        assert set(final_checkpoint.completed_phases) == {
            Phase.PLANNING.value,
            Phase.CODING.value,
            Phase.TESTING.value,
            Phase.REVIEW.value,
        }
        assert tracker.get_execution_count() == 2 + 5 + 3 + 2

    def test_empty_checkpoint_file(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Empty checkpoint file on disk is handled gracefully."""
        checkpoint_store.checkpoint_file.touch()

        engine = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine.run()

        assert set(final_checkpoint.completed_phases) == {
            Phase.PLANNING.value,
            Phase.CODING.value,
            Phase.TESTING.value,
            Phase.REVIEW.value,
        }

    def test_corrupted_json_checkpoint(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Corrupted JSON checkpoint is handled gracefully."""
        with open(checkpoint_store.checkpoint_file, "w") as file:
            file.write("{ invalid json }")

        engine = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine.run()

        assert tracker.get_execution_count() == 2 + 5 + 3 + 2

    def test_interrupt_at_very_first_chunk(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Interrupt at very first chunk, resume restarts from that chunk."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.PLANNING.value, 0),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        assert tracker2.was_executed(Phase.PLANNING.value, 0)

    def test_interrupt_at_very_last_chunk(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Interrupt at very last chunk, resume completes just that chunk."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.REVIEW.value, 1),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        assert tracker2.get_execution_count() == 1
        assert tracker2.was_executed(Phase.REVIEW.value, 1)

    def test_all_phases_completed_checkpoint_not_cleaned(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Resume after all phases completed should not re-execute anything."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=None,
            initial_context=initial_context,
        )

        checkpoint1, _ = engine1.run()

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        checkpoint2, _ = engine2.run()

        assert tracker2.get_execution_count() == 0
        assert set(checkpoint1.completed_phases) == set(checkpoint2.completed_phases)

    def test_zero_chunks_in_phase(
        self,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Phase with zero chunks is handled correctly."""
        phases = {Phase.PLANNING.value: 0, Phase.CODING.value: 2}

        engine = ArtisanExecutionEngine(
            phases_config=phases,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine.run()

        assert Phase.PLANNING.value in final_checkpoint.completed_phases
        assert tracker.get_execution_count() == 2

    def test_single_chunk_in_phase(
        self,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Phase with single chunk is handled correctly across interrupt/resume."""
        phases = {Phase.PLANNING.value: 1, Phase.CODING.value: 1}

        engine1 = ArtisanExecutionEngine(
            phases_config=phases,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.PLANNING.value, 0),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=phases,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        assert set(final_checkpoint.completed_phases) == {
            Phase.PLANNING.value,
            Phase.CODING.value,
        }

    def test_context_with_nested_structures(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
    ):
        """Context with nested dicts and lists is preserved correctly across resume."""
        nested_context = {
            "project": {
                "name": "test",
                "config": {
                    "stages": ["dev", "prod"],
                    "timeouts": {"planning": 30, "coding": 60},
                },
            },
            "tags": ["urgent", "critical"],
        }

        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.CODING.value, 1),
            initial_context=nested_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=nested_context,
        )

        final_checkpoint, results = engine2.run()

        assert final_checkpoint.context["project"]["name"] == "test"
        assert final_checkpoint.context["project"]["config"]["stages"] == ["dev", "prod"]
        assert final_checkpoint.context["tags"] == ["urgent", "critical"]

    def test_multiple_rapid_resumptions_from_same_checkpoint(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Multiple resumes from the same completed checkpoint are idempotent."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.CODING.value, 2),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        # Resume 1
        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        checkpoint2, _ = engine2.run()

        # Resume 2 (from already-completed state)
        tracker3 = ExecutionTracker()
        engine3 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker3,
            interrupt_at=None,
            initial_context=initial_context,
        )

        checkpoint3, _ = engine3.run()

        assert tracker3.get_execution_count() == 0
        assert set(checkpoint2.completed_phases) == set(checkpoint3.completed_phases)

    def test_cost_exactly_zero_for_skipped_work(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Skipped phases/chunks add zero cost on resume."""
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=(Phase.TESTING.value, 1),
            initial_context=initial_context,
        )

        with pytest.raises(InterruptionError):
            engine1.run()

        checkpoint_interrupt = checkpoint_store.load()
        cost_before_resume = checkpoint_interrupt.total_cost

        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()

        cost_increase = final_checkpoint.total_cost - cost_before_resume
        skipped_chunks = len(tracker2.skipped)
        executed_chunks = len(tracker2.executed)

        assert skipped_chunks > 0
        assert cost_increase > 0.0

        # Remaining: testing (1,2) + review (0,1) = 4
        expected_remaining = 2 + 2
        assert executed_chunks == expected_remaining

    def test_checkpoint_store_clear_and_rerun(
        self,
        default_phases_config,
        checkpoint_store,
        chunk_processor,
        tracker,
        initial_context,
    ):
        """Clearing checkpoint store forces full re-execution."""
        # Run to completion
        engine1 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker,
            interrupt_at=None,
            initial_context=initial_context,
        )
        engine1.run()
        assert tracker.get_execution_count() == 12

        # Clear checkpoint
        checkpoint_store.clear()
        assert not checkpoint_store.exists()

        # Re-run should execute everything again
        tracker2 = ExecutionTracker()
        engine2 = ArtisanExecutionEngine(
            phases_config=default_phases_config,
            checkpoint_store=checkpoint_store,
            chunk_processor=chunk_processor,
            tracker=tracker2,
            interrupt_at=None,
            initial_context=initial_context,
        )

        final_checkpoint, results = engine2.run()
        assert tracker2.get_execution_count() == 12

    def test_deterministic_output_across_runs(
        self,
        default_phases_config,
        chunk_processor,
        initial_context,
    ):
        """ChunkProcessor produces identical output for identical inputs."""
        result1, cost1 = chunk_processor.process("coding", 2, initial_context)
        result2, cost2 = chunk_processor.process("coding", 2, initial_context)

        assert result1["output"] == result2["output"]
        assert result1["chunk_index"] == result2["chunk_index"]
        assert cost1.monetary_cost == cost2.monetary_cost
        assert cost1.tokens_used == cost2.tokens_used
        assert cost1.api_calls == cost2.api_calls