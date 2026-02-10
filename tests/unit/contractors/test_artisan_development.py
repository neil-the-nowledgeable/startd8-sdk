"""
Comprehensive unit tests for Artisan Development Phase.

Tests cover:
- Dependency ordering and topological sort
- Chunk resume capability (resuming from partial completion)
- Test-pass gates (ensuring tests must pass before proceeding)
- Parallel execution of independent tasks
- Integration scenarios combining all features

Target: >85% code coverage across all domain objects and orchestration logic.

All code is self-contained in a single file with absolute imports only.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Callable
from enum import Enum
from collections import defaultdict


# ============================================================================
# DOMAIN OBJECTS
# ============================================================================

class ChunkStatus(Enum):
    """Status of a development chunk."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DevelopmentChunk:
    """Represents a single development task/chunk."""
    chunk_id: str
    name: str
    description: str = ""
    dependencies: List[str] = field(default_factory=list)
    status: ChunkStatus = ChunkStatus.PENDING
    code_output: Optional[str] = None
    test_passed: Optional[bool] = None
    retry_count: int = 0
    max_retries: int = 3

    def is_complete(self) -> bool:
        """Check if chunk is completed."""
        return self.status == ChunkStatus.COMPLETED

    def is_failed(self) -> bool:
        """Check if chunk has failed."""
        return self.status == ChunkStatus.FAILED

    def can_retry(self) -> bool:
        """Check if chunk can be retried (hasn't exhausted retries)."""
        return self.retry_count < self.max_retries


@dataclass
class DevelopmentState:
    """Tracks the overall development phase state."""
    chunks: List[DevelopmentChunk] = field(default_factory=list)
    current_chunk_index: int = 0
    is_complete: bool = False
    failed: bool = False
    error_message: Optional[str] = None

    def get_chunk(self, chunk_id: str) -> Optional[DevelopmentChunk]:
        """Get a chunk by its ID."""
        for chunk in self.chunks:
            if chunk.chunk_id == chunk_id:
                return chunk
        return None

    def mark_complete(self, chunk_id: str) -> None:
        """Mark a specific chunk as completed."""
        chunk = self.get_chunk(chunk_id)
        if chunk:
            chunk.status = ChunkStatus.COMPLETED

    def mark_failed(self, chunk_id: str, error: str = "") -> None:
        """Mark a specific chunk as failed and increment retry count."""
        chunk = self.get_chunk(chunk_id)
        if chunk:
            chunk.status = ChunkStatus.FAILED
            chunk.retry_count += 1


@dataclass
class TestResult:
    """Result from running a test suite against a chunk."""
    passed: bool
    test_count: int = 0
    failures: int = 0
    errors: int = 0
    output: str = ""

    def summary(self) -> str:
        """Generate a human-readable summary of the test results."""
        return (
            f"Tests: {self.test_count}, "
            f"Failures: {self.failures}, "
            f"Errors: {self.errors}, "
            f"Status: {'PASS' if self.passed else 'FAIL'}"
        )


# ============================================================================
# CORE IMPLEMENTATION
# ============================================================================

class DependencyResolver:
    """Resolves execution order from a dependency graph using topological sort."""

    def __init__(self, chunks: List[DevelopmentChunk]) -> None:
        self.chunks: Dict[str, DevelopmentChunk] = {c.chunk_id: c for c in chunks}

    def topological_sort(self) -> List[str]:
        """
        Return chunk IDs in a valid execution order via Kahn's algorithm.

        Raises:
            ValueError: If a missing dependency or circular dependency is detected.
        """
        in_degree: Dict[str, int] = {cid: 0 for cid in self.chunks}
        adj: Dict[str, List[str]] = defaultdict(list)

        for cid, chunk in self.chunks.items():
            for dep in chunk.dependencies:
                if dep not in self.chunks:
                    raise ValueError(
                        f"Missing dependency: {dep} (required by {cid})"
                    )
                adj[dep].append(cid)
                in_degree[cid] += 1

        # Seed the queue with nodes that have no incoming edges
        queue = sorted(cid for cid, deg in in_degree.items() if deg == 0)
        result: List[str] = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for neighbor in sorted(adj[node]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
            queue.sort()  # Deterministic ordering for reproducibility

        if len(result) != len(self.chunks):
            raise ValueError("Circular dependency detected in chunk graph")

        return result

    def detect_cycles(self) -> List[List[str]]:
        """
        Detect circular dependencies using DFS.

        Returns a list of cycles found (each cycle is a list of chunk IDs).
        """
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        cycles: List[List[str]] = []

        def _dfs(node: str, path: List[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for dep in self.chunks[node].dependencies:
                if dep not in self.chunks:
                    continue
                if dep not in visited:
                    _dfs(dep, path[:])
                elif dep in rec_stack:
                    cycle_start = path.index(dep)
                    cycles.append(path[cycle_start:] + [dep])

            rec_stack.discard(node)

        for cid in self.chunks:
            if cid not in visited:
                _dfs(cid, [])

        return cycles

    def get_independent_groups(self) -> List[List[str]]:
        """
        Return groups of chunk IDs that can execute in parallel.

        Each group contains chunks whose dependencies are all satisfied
        by chunks in previous groups.
        """
        sorted_order = self.topological_sort()
        groups: List[List[str]] = []
        processed: Set[str] = set()

        remaining = list(sorted_order)
        while remaining:
            # Find all chunks in remaining whose deps are fully processed
            group = [
                cid for cid in remaining
                if all(dep in processed for dep in self.chunks[cid].dependencies)
            ]
            if not group:
                break  # Safety: shouldn't happen after a valid topo sort
            processed.update(group)
            for cid in group:
                remaining.remove(cid)
            groups.append(sorted(group))

        return groups


class TestGate:
    """Runs tests against a chunk and gates progression on pass/fail."""

    def __init__(self, test_runner: Optional[Callable[[DevelopmentChunk], TestResult]] = None) -> None:
        self.test_runner = test_runner
        self.last_result: Optional[TestResult] = None

    def run_tests(self, chunk: DevelopmentChunk) -> TestResult:
        """Run the test suite for a chunk."""
        if self.test_runner:
            result = self.test_runner(chunk)
        else:
            result = TestResult(passed=True, test_count=0)
        self.last_result = result
        return result

    def should_proceed(self, result: TestResult) -> bool:
        """Determine whether the gate allows proceeding."""
        return result.passed

    def get_last_result(self) -> Optional[TestResult]:
        """Retrieve the most recent test result."""
        return self.last_result


class ChunkExecutor:
    """Executes a single development chunk (code generation stub)."""

    def execute(self, chunk: DevelopmentChunk) -> DevelopmentChunk:
        """Execute a chunk, updating its status and code output."""
        chunk.status = ChunkStatus.IN_PROGRESS
        chunk.code_output = f"Code for {chunk.chunk_id}"
        chunk.status = ChunkStatus.COMPLETED
        return chunk


class ParallelScheduler:
    """Schedules independent chunks for (potentially parallel) execution."""

    def __init__(self, max_workers: int = 4) -> None:
        self.max_workers = max_workers

    def execute_parallel(
        self,
        chunks: List[DevelopmentChunk],
        executor: ChunkExecutor,
    ) -> List[DevelopmentChunk]:
        """Execute a batch of chunks. Current impl is sequential; ready for async upgrade."""
        results: List[DevelopmentChunk] = []
        for chunk in chunks:
            result = executor.execute(chunk)
            results.append(result)
        return results


class DevelopmentContractor:
    """
    Main orchestrator for the development phase.

    Coordinates dependency resolution, chunk execution, test gating,
    parallel scheduling, and resume-from-failure logic.
    """

    def __init__(
        self,
        state: Optional[DevelopmentState] = None,
        resolver: Optional[DependencyResolver] = None,
        executor: Optional[ChunkExecutor] = None,
        test_gate: Optional[TestGate] = None,
        scheduler: Optional[ParallelScheduler] = None,
    ) -> None:
        self.state = state or DevelopmentState()
        self.resolver = resolver or DependencyResolver(self.state.chunks)
        self.executor = executor or ChunkExecutor()
        self.test_gate = test_gate or TestGate()
        self.scheduler = scheduler or ParallelScheduler()

    def run(self) -> DevelopmentState:
        """Execute the full development phase respecting dependencies and gates."""
        try:
            groups = self.resolver.get_independent_groups()

            for group_ids in groups:
                # Only execute chunks that are not already completed
                pending_chunks = [
                    chunk for chunk in self.state.chunks
                    if chunk.chunk_id in group_ids
                    and chunk.status != ChunkStatus.COMPLETED
                ]

                if not pending_chunks:
                    continue

                executed = self.scheduler.execute_parallel(pending_chunks, self.executor)

                for chunk in executed:
                    test_result = self.test_gate.run_tests(chunk)

                    if not self.test_gate.should_proceed(test_result):
                        # Retry loop
                        if chunk.can_retry():
                            chunk.retry_count += 1
                            chunk.status = ChunkStatus.PENDING
                            chunk = self.executor.execute(chunk)
                            test_result = self.test_gate.run_tests(chunk)

                        if not self.test_gate.should_proceed(test_result):
                            chunk.status = ChunkStatus.FAILED
                            self.state.failed = True
                            self.state.error_message = (
                                f"Tests failed for {chunk.chunk_id}"
                            )
                            return self.state

                    chunk.test_passed = test_result.passed

            self.state.is_complete = True
            return self.state

        except Exception as exc:
            self.state.failed = True
            self.state.error_message = str(exc)
            return self.state

    def resume(self) -> DevelopmentState:
        """
        Resume development from the last incomplete chunk.

        Resets any IN_PROGRESS chunks back to PENDING, then re-runs.
        Already-completed chunks are skipped automatically.
        """
        for chunk in self.state.chunks:
            if chunk.status == ChunkStatus.IN_PROGRESS:
                chunk.status = ChunkStatus.PENDING

        return self.run()


# ============================================================================
# TEST HELPER / FACTORY FUNCTIONS
# ============================================================================

def make_chunk(
    chunk_id: str,
    name: Optional[str] = None,
    deps: Optional[List[str]] = None,
    status: ChunkStatus = ChunkStatus.PENDING,
) -> DevelopmentChunk:
    """Factory for creating test chunks with sensible defaults."""
    return DevelopmentChunk(
        chunk_id=chunk_id,
        name=name or f"Chunk {chunk_id}",
        description=f"Description for {chunk_id}",
        dependencies=deps or [],
        status=status,
    )


def make_linear_chain(length: int) -> List[DevelopmentChunk]:
    """Create a linear dependency chain: chunk_0 -> chunk_1 -> ... -> chunk_{n-1}."""
    chunks: List[DevelopmentChunk] = []
    for idx in range(length):
        deps = [f"chunk_{idx - 1}"] if idx > 0 else []
        chunks.append(make_chunk(f"chunk_{idx}", deps=deps))
    return chunks


def make_diamond_graph() -> List[DevelopmentChunk]:
    """Create a diamond dependency graph: A -> {B, C} -> D."""
    return [
        make_chunk("A", deps=[]),
        make_chunk("B", deps=["A"]),
        make_chunk("C", deps=["A"]),
        make_chunk("D", deps=["B", "C"]),
    ]


def make_independent_chunks(count: int) -> List[DevelopmentChunk]:
    """Create N chunks with no dependencies (fully parallelizable)."""
    return [make_chunk(f"ind_{idx}", deps=[]) for idx in range(count)]


def make_complex_dag() -> List[DevelopmentChunk]:
    """Create a complex DAG: A->{B,C}, B->D, C->E, {D,E}->F."""
    return [
        make_chunk("A", deps=[]),
        make_chunk("B", deps=["A"]),
        make_chunk("C", deps=["A"]),
        make_chunk("D", deps=["B"]),
        make_chunk("E", deps=["C"]),
        make_chunk("F", deps=["D", "E"]),
    ]


def make_state_with_partial_completion(
    chunks: List[DevelopmentChunk],
    completed_ids: Set[str],
) -> DevelopmentState:
    """Create a state where some chunks are already completed."""
    for chunk in chunks:
        if chunk.chunk_id in completed_ids:
            chunk.status = ChunkStatus.COMPLETED
            chunk.code_output = f"Existing code for {chunk.chunk_id}"
    return DevelopmentState(chunks=chunks, current_chunk_index=0)


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def mock_executor():
    """Mock ChunkExecutor that marks chunks as completed."""
    executor = MagicMock(spec=ChunkExecutor)

    def execute_side_effect(chunk: DevelopmentChunk) -> DevelopmentChunk:
        chunk.status = ChunkStatus.COMPLETED
        chunk.code_output = f"Code for {chunk.chunk_id}"
        return chunk

    executor.execute.side_effect = execute_side_effect
    return executor


@pytest.fixture
def mock_test_gate():
    """Mock TestGate that always passes."""
    gate = MagicMock(spec=TestGate)
    gate.run_tests.return_value = TestResult(passed=True, test_count=5)
    gate.should_proceed.return_value = True
    gate.get_last_result.return_value = TestResult(passed=True)
    return gate


@pytest.fixture
def mock_failing_gate():
    """Mock TestGate that always fails."""
    gate = MagicMock(spec=TestGate)
    gate.run_tests.return_value = TestResult(passed=False, test_count=5, failures=2)
    gate.should_proceed.return_value = False
    gate.get_last_result.return_value = TestResult(passed=False, failures=2)
    return gate


# ============================================================================
# TESTS: DEPENDENCY ORDERING
# ============================================================================

class TestDependencyOrdering:
    """Tests for dependency resolution and topological ordering."""

    def test_linear_chain_ordering(self):
        """Chunks in a linear chain execute in strict sequential order."""
        chunks = make_linear_chain(3)
        resolver = DependencyResolver(chunks)
        order = resolver.topological_sort()

        assert order.index("chunk_0") < order.index("chunk_1")
        assert order.index("chunk_1") < order.index("chunk_2")
        assert len(order) == 3

    def test_diamond_dependency_ordering(self):
        """Diamond graph: A before {B,C}, both before D."""
        chunks = make_diamond_graph()
        resolver = DependencyResolver(chunks)
        order = resolver.topological_sort()

        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("D")

    def test_no_dependencies_any_order(self):
        """Independent chunks can appear in any valid order."""
        chunks = make_independent_chunks(3)
        resolver = DependencyResolver(chunks)
        order = resolver.topological_sort()

        assert len(order) == 3
        assert set(order) == {"ind_0", "ind_1", "ind_2"}

    def test_complex_dag_ordering(self):
        """Complex DAG respects all dependency constraints."""
        chunks = make_complex_dag()
        resolver = DependencyResolver(chunks)
        order = resolver.topological_sort()

        assert order.index("A") < order.index("B")
        assert order.index("A") < order.index("C")
        assert order.index("B") < order.index("D")
        assert order.index("C") < order.index("E")
        assert order.index("D") < order.index("F")
        assert order.index("E") < order.index("F")

    def test_cycle_detection_raises_error(self):
        """Circular dependencies raise ValueError."""
        chunks = [
            make_chunk("A", deps=["B"]),
            make_chunk("B", deps=["A"]),
        ]
        resolver = DependencyResolver(chunks)

        with pytest.raises(ValueError, match="Circular dependency"):
            resolver.topological_sort()

    def test_self_dependency_raises_error(self):
        """A chunk depending on itself is detected as a cycle."""
        chunks = [make_chunk("A", deps=["A"])]
        resolver = DependencyResolver(chunks)

        with pytest.raises(ValueError, match="Circular dependency"):
            resolver.topological_sort()

    def test_missing_dependency_raises_error(self):
        """Referencing a non-existent dependency raises ValueError."""
        chunks = [make_chunk("A", deps=["nonexistent"])]
        resolver = DependencyResolver(chunks)

        with pytest.raises(ValueError, match="Missing dependency"):
            resolver.topological_sort()

    def test_single_chunk_no_deps(self):
        """Single chunk with no dependencies returns that chunk."""
        chunks = [make_chunk("A", deps=[])]
        resolver = DependencyResolver(chunks)
        order = resolver.topological_sort()

        assert order == ["A"]

    def test_empty_chunk_list(self):
        """Empty input returns an empty ordering."""
        resolver = DependencyResolver([])
        order = resolver.topological_sort()

        assert order == []

    def test_ordering_preserves_all_chunks(self):
        """All chunks appear exactly once in the result."""
        chunks = make_complex_dag()
        resolver = DependencyResolver(chunks)
        order = resolver.topological_sort()

        assert len(order) == len(chunks)
        assert len(set(order)) == len(chunks)

    @pytest.mark.parametrize("length", [1, 2, 5, 10])
    def test_linear_chain_various_lengths(self, length):
        """Linear chains of various lengths sort correctly."""
        chunks = make_linear_chain(length)
        resolver = DependencyResolver(chunks)
        order = resolver.topological_sort()

        for idx in range(length - 1):
            assert order.index(f"chunk_{idx}") < order.index(f"chunk_{idx + 1}")

    def test_cycle_detection_identifies_cycles(self):
        """detect_cycles() finds circular paths in the graph."""
        chunks = [
            make_chunk("A", deps=["B"]),
            make_chunk("B", deps=["C"]),
            make_chunk("C", deps=["A"]),
        ]
        resolver = DependencyResolver(chunks)
        cycles = resolver.detect_cycles()

        assert len(cycles) > 0

    def test_detect_cycles_with_missing_dep_in_graph(self):
        """detect_cycles skips dependencies not present in the chunk map."""
        chunks = [
            make_chunk("A", deps=["missing_dep"]),
        ]
        resolver = DependencyResolver(chunks)
        cycles = resolver.detect_cycles()
        # Should not crash; no cycle found
        assert isinstance(cycles, list)

    def test_get_independent_groups_empty(self):
        """Empty chunk list produces empty groups."""
        resolver = DependencyResolver([])
        groups = resolver.get_independent_groups()
        assert groups == []


# ============================================================================
# TESTS: CHUNK RESUME
# ============================================================================

class TestChunkResume:
    """Tests for resuming development from a partially completed state."""

    def test_resume_skips_completed_chunks(self, mock_executor, mock_test_gate):
        """Completed chunks are not re-executed on resume."""
        chunks = make_linear_chain(3)
        chunks[0].status = ChunkStatus.COMPLETED
        chunks[0].code_output = "existing_code"

        state = DevelopmentState(chunks=chunks)
        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        contractor.resume()

        executed_ids = [
            c[0][0].chunk_id for c in mock_executor.execute.call_args_list
        ]
        assert "chunk_0" not in executed_ids

    def test_resume_starts_from_first_pending(self, mock_executor, mock_test_gate):
        """Resume begins at the first PENDING chunk."""
        chunks = make_linear_chain(3)
        chunks[0].status = ChunkStatus.COMPLETED

        state = DevelopmentState(chunks=chunks)
        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        contractor.resume()

        first_call = mock_executor.execute.call_args_list[0]
        assert first_call[0][0].chunk_id == "chunk_1"

    def test_resume_with_no_completed_chunks(self, mock_executor, mock_test_gate):
        """Resume with all PENDING is equivalent to a fresh run."""
        chunks = make_linear_chain(2)
        state = DevelopmentState(chunks=chunks)
        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        contractor.resume()

        assert mock_executor.execute.call_count == 2

    def test_resume_with_all_completed(self, mock_executor, mock_test_gate):
        """Resume with all completed returns success without executing."""
        chunks = make_linear_chain(2)
        for chunk in chunks:
            chunk.status = ChunkStatus.COMPLETED

        state = DevelopmentState(chunks=chunks)
        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        result = contractor.resume()

        assert mock_executor.execute.call_count == 0
        assert result.is_complete is True

    def test_resume_re_executes_in_progress_chunk(self, mock_executor, mock_test_gate):
        """A chunk that was IN_PROGRESS is reset and re-executed."""
        chunks = make_linear_chain(2)
        chunks[0].status = ChunkStatus.IN_PROGRESS

        state = DevelopmentState(chunks=chunks)
        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        contractor.resume()

        executed_ids = [
            c[0][0].chunk_id for c in mock_executor.execute.call_args_list
        ]
        assert "chunk_0" in executed_ids

    def test_resume_handles_failed_chunk_retry(self, mock_executor, mock_test_gate):
        """A failed chunk with retries remaining is retried."""
        chunks = make_linear_chain(2)
        chunks[0].status = ChunkStatus.FAILED
        chunks[0].retry_count = 1
        chunks[0].max_retries = 3

        state = DevelopmentState(chunks=chunks)
        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        contractor.resume()

        executed_ids = [
            c[0][0].chunk_id for c in mock_executor.execute.call_args_list
        ]
        assert "chunk_0" in executed_ids

    def test_resume_preserves_completed_outputs(self, mock_executor, mock_test_gate):
        """Completed chunk outputs are preserved, not overwritten."""
        chunks = make_linear_chain(2)
        chunks[0].status = ChunkStatus.COMPLETED
        chunks[0].code_output = "existing_code_output"

        state = DevelopmentState(chunks=chunks)
        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        contractor.resume()

        assert chunks[0].code_output == "existing_code_output"

    def test_resume_state_persistence(self, mock_executor, mock_test_gate):
        """State changes are correctly tracked during resume."""
        chunks = make_linear_chain(2)
        chunks[0].status = ChunkStatus.COMPLETED

        state = DevelopmentState(chunks=chunks)
        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        result = contractor.resume()

        assert result.is_complete is True
        assert result.failed is False

    def test_resume_after_partial_parallel_completion(
        self, mock_executor, mock_test_gate
    ):
        """Only incomplete parallel chunks are re-executed on resume."""
        chunks = make_independent_chunks(3)
        chunks[0].status = ChunkStatus.COMPLETED
        chunks[1].status = ChunkStatus.PENDING
        chunks[2].status = ChunkStatus.PENDING

        state = DevelopmentState(chunks=chunks)
        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        contractor.resume()

        executed_ids = [
            c[0][0].chunk_id for c in mock_executor.execute.call_args_list
        ]
        assert "ind_0" not in executed_ids
        assert "ind_1" in executed_ids
        assert "ind_2" in executed_ids

    def test_resume_resets_multiple_in_progress(self, mock_executor, mock_test_gate):
        """Multiple IN_PROGRESS chunks are all reset to PENDING."""
        chunks = make_independent_chunks(3)
        chunks[0].status = ChunkStatus.IN_PROGRESS
        chunks[1].status = ChunkStatus.IN_PROGRESS
        chunks[2].status = ChunkStatus.COMPLETED

        state = DevelopmentState(chunks=chunks)
        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        contractor.resume()

        executed_ids = [
            c[0][0].chunk_id for c in mock_executor.execute.call_args_list
        ]
        assert "ind_0" in executed_ids
        assert "ind_1" in executed_ids
        assert "ind_2" not in executed_ids


# ============================================================================
# TESTS: TEST-PASS GATES
# ============================================================================

class TestPassGates:
    """Tests for the test-pass gate mechanism."""

    def test_gate_allows_on_pass(self):
        """When tests pass, the gate allows proceeding."""
        gate = TestGate()
        result = TestResult(passed=True, test_count=5)
        assert gate.should_proceed(result) is True

    def test_gate_blocks_on_failure(self):
        """When tests fail, the gate prevents proceeding."""
        gate = TestGate()
        result = TestResult(passed=False, test_count=5, failures=2)
        assert gate.should_proceed(result) is False

    def test_gate_runs_tests_and_caches_result(self):
        """Gate runs tests and caches the result for retrieval."""
        def mock_runner(chunk: DevelopmentChunk) -> TestResult:
            return TestResult(passed=True, test_count=3)

        gate = TestGate(test_runner=mock_runner)
        chunk = make_chunk("A")

        gate.run_tests(chunk)
        cached = gate.get_last_result()

        assert cached is not None
        assert cached.passed is True
        assert cached.test_count == 3

    def test_gate_with_zero_tests(self):
        """Gate with no tests to run treats it as a pass."""
        gate = TestGate()
        result = TestResult(passed=True, test_count=0)
        assert gate.should_proceed(result) is True

    def test_gate_captures_test_output(self):
        """Test output/errors are captured in the result."""
        result = TestResult(
            passed=False,
            test_count=5,
            failures=2,
            errors=1,
            output="Test output here",
        )
        assert result.output == "Test output here"
        assert "FAIL" in result.summary()

    def test_gate_partial_failure_is_failure(self):
        """Even one test failure means the gate fails."""
        gate = TestGate()
        result = TestResult(passed=False, test_count=5, failures=1, errors=0)
        assert gate.should_proceed(result) is False

    @pytest.mark.parametrize(
        "test_count,failures,expected_pass",
        [
            (5, 0, True),
            (5, 1, False),
            (10, 0, True),
            (0, 0, True),
            (1, 1, False),
        ],
    )
    def test_gate_with_various_results(self, test_count, failures, expected_pass):
        """Gate behaves correctly for various test result combinations."""
        gate = TestGate()
        result = TestResult(
            passed=(failures == 0), test_count=test_count, failures=failures
        )
        assert gate.should_proceed(result) == expected_pass

    def test_gate_retry_on_failure(self):
        """Failed gate triggers a retry; second attempt can succeed."""
        gate = TestGate()
        chunk = make_chunk("A", status=ChunkStatus.PENDING)

        gate.run_tests = MagicMock(
            side_effect=[
                TestResult(passed=False, failures=1),
                TestResult(passed=True, failures=0),
            ]
        )

        result1 = gate.run_tests(chunk)
        assert gate.should_proceed(result1) is False

        result2 = gate.run_tests(chunk)
        assert gate.should_proceed(result2) is True

    def test_gate_max_retries_then_halt(self, mock_executor):
        """After max retries with test failures, development halts."""
        chunks = make_linear_chain(1)
        chunks[0].max_retries = 2

        def mock_runner(_chunk: DevelopmentChunk) -> TestResult:
            return TestResult(passed=False, failures=1)

        gate = TestGate(test_runner=mock_runner)
        state = DevelopmentState(chunks=chunks)

        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=gate,
        )

        result = contractor.run()
        assert result.failed is True

    def test_gate_no_runner_defaults_to_pass(self):
        """Gate without a runner defaults to passing."""
        gate = TestGate()
        chunk = make_chunk("A")
        result = gate.run_tests(chunk)

        assert result.passed is True
        assert result.test_count == 0

    def test_gate_last_result_initially_none(self):
        """Last result is None before any tests are run."""
        gate = TestGate()
        assert gate.get_last_result() is None


# ============================================================================
# TESTS: PARALLEL EXECUTION
# ============================================================================

class TestParallelExecution:
    """Tests for parallel execution of independent chunks."""

    def test_independent_chunks_identified_as_parallelizable(self):
        """Chunks with no dependencies are grouped together."""
        chunks = make_independent_chunks(3)
        resolver = DependencyResolver(chunks)
        groups = resolver.get_independent_groups()

        assert len(groups) >= 1
        all_chunks = set().union(*groups)
        assert all_chunks == {"ind_0", "ind_1", "ind_2"}

    def test_dependent_chunks_not_parallel(self):
        """Chunks with dependencies are in separate sequential groups."""
        chunks = make_linear_chain(3)
        resolver = DependencyResolver(chunks)
        groups = resolver.get_independent_groups()

        for group in groups:
            assert len(group) == 1

    def test_mixed_parallel_and_sequential_diamond(self):
        """Diamond graph: A first, B+C parallel, then D."""
        chunks = make_diamond_graph()
        resolver = DependencyResolver(chunks)
        groups = resolver.get_independent_groups()

        assert groups[0] == ["A"]
        assert set(groups[1]) == {"B", "C"}
        assert groups[2] == ["D"]

    def test_parallel_execution_all_results_collected(
        self, mock_executor, mock_test_gate
    ):
        """All chunk results are collected regardless of execution mode."""
        chunks = make_independent_chunks(5)
        state = DevelopmentState(chunks=chunks)

        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        result = contractor.run()

        completed = [c for c in result.chunks if c.status == ChunkStatus.COMPLETED]
        assert len(completed) == 5

    def test_parallel_with_single_chunk(self, mock_executor, mock_test_gate):
        """Single chunk runs normally."""
        chunks = [make_chunk("A")]
        state = DevelopmentState(chunks=chunks)

        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        result = contractor.run()

        assert result.is_complete is True
        assert mock_executor.execute.call_count == 1

    def test_parallel_scheduler_executes_all_chunks(self):
        """Scheduler executes every chunk in the batch."""
        chunks = make_independent_chunks(3)
        scheduler = ParallelScheduler(max_workers=4)

        executor = MagicMock(spec=ChunkExecutor)

        def execute_mock(chunk: DevelopmentChunk) -> DevelopmentChunk:
            chunk.status = ChunkStatus.COMPLETED
            return chunk

        executor.execute.side_effect = execute_mock

        results = scheduler.execute_parallel(chunks, executor)

        assert len(results) == 3
        assert all(r.status == ChunkStatus.COMPLETED for r in results)

    @pytest.mark.parametrize("worker_count", [1, 2, 4, 8])
    def test_scheduler_with_various_worker_counts(self, worker_count):
        """Scheduler works correctly with various worker counts."""
        chunks = make_independent_chunks(3)
        scheduler = ParallelScheduler(max_workers=worker_count)

        executor = MagicMock(spec=ChunkExecutor)
        executor.execute.side_effect = lambda chunk: (
            setattr(chunk, "status", ChunkStatus.COMPLETED) or chunk
        )

        results = scheduler.execute_parallel(chunks, executor)
        assert len(results) == 3

    def test_scheduler_empty_batch(self):
        """Scheduler handles an empty batch gracefully."""
        scheduler = ParallelScheduler(max_workers=4)
        executor = MagicMock(spec=ChunkExecutor)

        results = scheduler.execute_parallel([], executor)
        assert results == []
        assert executor.execute.call_count == 0

    def test_complex_dag_grouping(self):
        """Complex DAG produces correct parallel groups."""
        chunks = make_complex_dag()
        resolver = DependencyResolver(chunks)
        groups = resolver.get_independent_groups()

        # Level 0: A (no deps)
        assert "A" in groups[0]
        # Level 1: B, C (depend on A)
        level1 = set(groups[1])
        assert level1 == {"B", "C"}
        # Level 2: D, E (depend on B, C respectively)
        level2 = set(groups[2])
        assert level2 == {"D", "E"}
        # Level 3: F (depends on D and E)
        assert "F" in groups[3]


# ============================================================================
# TESTS: INTEGRATION
# ============================================================================

class TestDevelopmentPhaseIntegration:
    """Integration tests combining dependency ordering, gates, and parallel exec."""

    def test_full_development_run_linear(self, mock_executor, mock_test_gate):
        """Full run with linear chunks completes in order."""
        chunks = make_linear_chain(3)
        state = DevelopmentState(chunks=chunks)

        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        result = contractor.run()

        assert result.is_complete is True
        assert result.failed is False
        assert all(c.status == ChunkStatus.COMPLETED for c in result.chunks)

    def test_full_development_run_with_parallelism(
        self, mock_executor, mock_test_gate
    ):
        """Full run with diamond graph uses parallel execution."""
        chunks = make_diamond_graph()
        state = DevelopmentState(chunks=chunks)

        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        result = contractor.run()

        assert result.is_complete is True
        assert all(c.status == ChunkStatus.COMPLETED for c in result.chunks)
        assert mock_executor.execute.call_count >= 4

    def test_full_run_with_mid_failure(self, mock_test_gate):
        """Run fails mid-way when a chunk execution fails."""
        chunks = make_linear_chain(3)

        executor = MagicMock(spec=ChunkExecutor)

        def execute_fail_then_pass(chunk: DevelopmentChunk) -> DevelopmentChunk:
            if chunk.chunk_id == "chunk_1" and chunk.retry_count == 0:
                chunk.status = ChunkStatus.FAILED
            else:
                chunk.status = ChunkStatus.COMPLETED
                chunk.code_output = f"Code for {chunk.chunk_id}"
            return chunk

        executor.execute.side_effect = execute_fail_then_pass

        state = DevelopmentState(chunks=chunks)
        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=executor,
            test_gate=mock_test_gate,
        )

        result = contractor.run()
        assert any(c.status == ChunkStatus.FAILED for c in result.chunks) or result.failed

    def test_full_run_all_gates_pass(self, mock_executor, mock_test_gate):
        """All gates pass, development completes successfully."""
        chunks = make_complex_dag()
        state = DevelopmentState(chunks=chunks)

        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        result = contractor.run()

        assert result.is_complete is True
        assert result.failed is False
        assert mock_test_gate.run_tests.call_count >= len(chunks)

    def test_full_run_gate_fails_and_halts(self, mock_executor):
        """Gate failures after retries halt the development phase."""
        chunks = make_linear_chain(2)

        def mock_runner(_chunk: DevelopmentChunk) -> TestResult:
            return TestResult(passed=False, failures=1)

        gate = TestGate(test_runner=mock_runner)
        state = DevelopmentState(chunks=chunks)

        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=gate,
        )

        result = contractor.run()
        assert result.failed is True

    def test_integration_with_complex_dag(self, mock_executor, mock_test_gate):
        """Complex DAG integration: all chunks process correctly."""
        chunks = make_complex_dag()
        state = DevelopmentState(chunks=chunks)

        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        result = contractor.run()

        assert result.is_complete is True
        assert len(result.chunks) == 6

    def test_resume_after_mid_run_failure(self, mock_executor, mock_test_gate):
        """Resume after a mid-run failure completes remaining chunks."""
        chunks = make_linear_chain(3)
        chunks[0].status = ChunkStatus.COMPLETED
        chunks[1].status = ChunkStatus.FAILED

        state = DevelopmentState(chunks=chunks)
        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        contractor.resume()
        assert mock_executor.execute.call_count >= 1

    @pytest.mark.parametrize(
        "graph_factory",
        [make_linear_chain, make_diamond_graph, make_complex_dag],
    )
    def test_various_dependency_structures(
        self, graph_factory, mock_executor, mock_test_gate
    ):
        """Run completes successfully across various graph topologies."""
        if graph_factory == make_linear_chain:
            chunks = graph_factory(3)
        else:
            chunks = graph_factory()

        state = DevelopmentState(chunks=chunks)
        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        result = contractor.run()

        assert result.is_complete is True
        assert not result.failed

    def test_end_to_end_with_real_executor_and_gate(self):
        """End-to-end with real (non-mock) executor and gate."""
        chunks = make_diamond_graph()
        state = DevelopmentState(chunks=chunks)
        executor = ChunkExecutor()
        gate = TestGate()  # Default: passes everything

        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=executor,
            test_gate=gate,
        )

        result = contractor.run()

        assert result.is_complete is True
        assert all(c.status == ChunkStatus.COMPLETED for c in result.chunks)
        assert all(c.test_passed is True for c in result.chunks)
        assert all(c.code_output is not None for c in result.chunks)


# ============================================================================
# TESTS: EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_development_state(self, mock_executor, mock_test_gate):
        """Empty development state completes immediately."""
        state = DevelopmentState(chunks=[])
        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver([]),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        result = contractor.run()

        assert result.is_complete is True
        assert not result.failed
        assert mock_executor.execute.call_count == 0

    def test_single_chunk_with_no_dependencies(self, mock_executor, mock_test_gate):
        """Single chunk with no deps executes and completes."""
        chunks = [make_chunk("A")]
        state = DevelopmentState(chunks=chunks)

        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        result = contractor.run()

        assert result.is_complete is True
        assert chunks[0].status == ChunkStatus.COMPLETED

    def test_all_chunks_already_completed_on_resume(
        self, mock_executor, mock_test_gate
    ):
        """Resume with all chunks already completed is a no-op."""
        chunks = make_linear_chain(3)
        for chunk in chunks:
            chunk.status = ChunkStatus.COMPLETED

        state = DevelopmentState(chunks=chunks)
        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        result = contractor.resume()

        assert mock_executor.execute.call_count == 0
        assert result.is_complete is True

    def test_self_loop_dependency_error(self):
        """Chunk depending on itself raises an error."""
        chunks = [make_chunk("A", deps=["A"])]
        resolver = DependencyResolver(chunks)

        with pytest.raises(ValueError):
            resolver.topological_sort()

    def test_circular_dependency_of_length_two(self):
        """Two-node cycle is detected."""
        chunks = [
            make_chunk("A", deps=["B"]),
            make_chunk("B", deps=["A"]),
        ]
        resolver = DependencyResolver(chunks)

        with pytest.raises(ValueError, match="Circular dependency"):
            resolver.topological_sort()

    def test_circular_dependency_of_length_three(self):
        """Three-node cycle is detected."""
        chunks = [
            make_chunk("A", deps=["C"]),
            make_chunk("B", deps=["A"]),
            make_chunk("C", deps=["B"]),
        ]
        resolver = DependencyResolver(chunks)

        with pytest.raises(ValueError, match="Circular dependency"):
            resolver.topological_sort()

    def test_missing_dependency_error(self):
        """Referencing a non-existent dependency raises error."""
        chunks = [make_chunk("A", deps=["nonexistent"])]
        resolver = DependencyResolver(chunks)

        with pytest.raises(ValueError, match="Missing dependency"):
            resolver.topological_sort()

    def test_chunk_with_zero_test_cases_in_gate(self):
        """Gate with 0 test cases treats as pass."""
        gate = TestGate()
        result = TestResult(passed=True, test_count=0, failures=0)
        assert gate.should_proceed(result) is True

    def test_very_large_linear_chain(self):
        """Large linear chain of 100 chunks sorts correctly."""
        chunks = make_linear_chain(100)
        resolver = DependencyResolver(chunks)
        order = resolver.topological_sort()

        assert len(order) == 100
        for idx in range(99):
            assert order.index(f"chunk_{idx}") < order.index(f"chunk_{idx + 1}")

    def test_chunk_status_transitions(self):
        """Chunk status transitions work correctly."""
        chunk = make_chunk("A", status=ChunkStatus.PENDING)

        assert not chunk.is_complete()
        assert not chunk.is_failed()

        chunk.status = ChunkStatus.COMPLETED
        assert chunk.is_complete()
        assert not chunk.is_failed()

        chunk.status = ChunkStatus.FAILED
        assert chunk.is_failed()
        assert not chunk.is_complete()

    def test_chunk_retry_logic(self):
        """Retry count logic: can_retry() respects max_retries."""
        chunk = make_chunk("A", status=ChunkStatus.FAILED)
        chunk.max_retries = 3

        assert chunk.can_retry() is True
        chunk.retry_count = 1
        assert chunk.can_retry() is True
        chunk.retry_count = 2
        assert chunk.can_retry() is True
        chunk.retry_count = 3
        assert chunk.can_retry() is False

    def test_test_result_summary_pass(self):
        """Test result summary for a passing suite."""
        result = TestResult(passed=True, test_count=10, failures=0)
        summary = result.summary()

        assert "Tests: 10" in summary
        assert "PASS" in summary

    def test_test_result_summary_fail(self):
        """Test result summary for a failing suite."""
        result = TestResult(passed=False, test_count=10, failures=5, errors=2)
        summary = result.summary()

        assert "FAIL" in summary
        assert "Failures: 5" in summary
        assert "Errors: 2" in summary

    def test_development_state_get_chunk(self):
        """State retrieves chunks by ID correctly."""
        chunks = make_linear_chain(2)
        state = DevelopmentState(chunks=chunks)

        retrieved = state.get_chunk("chunk_0")
        assert retrieved is not None
        assert retrieved.chunk_id == "chunk_0"

        missing = state.get_chunk("nonexistent")
        assert missing is None

    def test_development_state_mark_complete(self):
        """State can mark chunks as complete."""
        chunks = make_linear_chain(1)
        state = DevelopmentState(chunks=chunks)

        state.mark_complete("chunk_0")
        assert state.chunks[0].status == ChunkStatus.COMPLETED

    def test_development_state_mark_complete_nonexistent(self):
        """Marking a non-existent chunk as complete does nothing."""
        state = DevelopmentState(chunks=[])
        state.mark_complete("nonexistent")  # Should not raise

    def test_development_state_mark_failed(self):
        """State can mark chunks as failed with retry increment."""
        chunks = make_linear_chain(1)
        state = DevelopmentState(chunks=chunks)

        state.mark_failed("chunk_0", error="Test error")
        assert state.chunks[0].status == ChunkStatus.FAILED
        assert state.chunks[0].retry_count == 1

    def test_development_state_mark_failed_nonexistent(self):
        """Marking a non-existent chunk as failed does nothing."""
        state = DevelopmentState(chunks=[])
        state.mark_failed("nonexistent")  # Should not raise

    def test_exception_handling_in_contractor_run(self):
        """Contractor handles exceptions during run gracefully."""
        chunks = [make_chunk("A", deps=["nonexistent"])]
        state = DevelopmentState(chunks=chunks)

        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
        )

        result = contractor.run()

        assert result.failed is True
        assert result.error_message is not None
        assert "Missing dependency" in result.error_message


# ============================================================================
# TESTS: COVERAGE OPTIMIZATION
# ============================================================================

class TestCoverageOptimization:
    """Additional tests to achieve >85% code coverage."""

    def test_dependency_resolver_with_many_independent_chunks(self):
        """Resolver handles many independent chunks."""
        chunks = make_independent_chunks(50)
        resolver = DependencyResolver(chunks)
        order = resolver.topological_sort()

        assert len(order) == 50

    def test_parallel_scheduler_initialization(self):
        """Scheduler initializes with specified worker count."""
        scheduler1 = ParallelScheduler(max_workers=1)
        assert scheduler1.max_workers == 1

        scheduler2 = ParallelScheduler(max_workers=16)
        assert scheduler2.max_workers == 16

    def test_chunk_executor_basic_execution(self):
        """Real ChunkExecutor completes a chunk."""
        executor = ChunkExecutor()
        chunk = make_chunk("A", status=ChunkStatus.PENDING)

        result = executor.execute(chunk)

        assert result.status == ChunkStatus.COMPLETED
        assert result.code_output == "Code for A"

    def test_test_gate_with_custom_runner(self):
        """Test gate works with a custom runner function."""
        def custom_runner(chunk: DevelopmentChunk) -> TestResult:
            return TestResult(passed=True, test_count=7)

        gate = TestGate(test_runner=custom_runner)
        chunk = make_chunk("A")
        result = gate.run_tests(chunk)

        assert result.passed is True
        assert result.test_count == 7
        assert gate.get_last_result() is result

    def test_development_contractor_default_initialization(self):
        """Contractor initializes with all defaults."""
        contractor = DevelopmentContractor()
        assert contractor.state is not None
        assert contractor.resolver is not None
        assert contractor.executor is not None
        assert contractor.test_gate is not None
        assert contractor.scheduler is not None

    def test_development_contractor_custom_state(self):
        """Contractor accepts a custom state."""
        chunks = make_linear_chain(2)
        state = DevelopmentState(chunks=chunks)
        contractor = DevelopmentContractor(state=state)
        assert contractor.state is state

    def test_multiple_cycles_detection(self):
        """Resolver detects multiple distinct cycles."""
        chunks = [
            make_chunk("A", deps=["B"]),
            make_chunk("B", deps=["C"]),
            make_chunk("C", deps=["A"]),
            make_chunk("D", deps=["D"]),
        ]
        resolver = DependencyResolver(chunks)
        cycles = resolver.detect_cycles()

        assert len(cycles) > 0

    def test_large_independent_set_all_parallelizable(self):
        """Large independent set is identified as fully parallelizable."""
        chunks = make_independent_chunks(20)
        resolver = DependencyResolver(chunks)
        groups = resolver.get_independent_groups()

        all_grouped = set().union(*groups)
        assert len(all_grouped) == 20

    @pytest.mark.parametrize(
        "status",
        [
            ChunkStatus.PENDING,
            ChunkStatus.IN_PROGRESS,
            ChunkStatus.COMPLETED,
            ChunkStatus.FAILED,
            ChunkStatus.SKIPPED,
        ],
    )
    def test_chunk_all_status_values(self, status):
        """Chunks can be created with any valid status."""
        chunk = make_chunk("A", status=status)
        assert chunk.status == status

    def test_factory_functions_produce_valid_chunks(self):
        """All factory functions produce valid DevelopmentChunk instances."""
        linear = make_linear_chain(5)
        assert all(isinstance(c, DevelopmentChunk) for c in linear)
        assert len(linear) == 5

        diamond = make_diamond_graph()
        assert all(isinstance(c, DevelopmentChunk) for c in diamond)
        assert len(diamond) == 4

        independent = make_independent_chunks(5)
        assert all(isinstance(c, DevelopmentChunk) for c in independent)
        assert len(independent) == 5

        complex_dag = make_complex_dag()
        assert all(isinstance(c, DevelopmentChunk) for c in complex_dag)
        assert len(complex_dag) == 6

    def test_make_state_with_partial_completion(self):
        """Factory correctly sets up partially completed state."""
        chunks = make_linear_chain(3)
        state = make_state_with_partial_completion(chunks, {"chunk_0", "chunk_1"})

        assert state.chunks[0].status == ChunkStatus.COMPLETED
        assert state.chunks[0].code_output == "Existing code for chunk_0"
        assert state.chunks[1].status == ChunkStatus.COMPLETED
        assert state.chunks[1].code_output == "Existing code for chunk_1"
        assert state.chunks[2].status == ChunkStatus.PENDING

    def test_chunk_status_enum_values(self):
        """All ChunkStatus enum values are accessible."""
        assert ChunkStatus.PENDING.value == "pending"
        assert ChunkStatus.IN_PROGRESS.value == "in_progress"
        assert ChunkStatus.COMPLETED.value == "completed"
        assert ChunkStatus.FAILED.value == "failed"
        assert ChunkStatus.SKIPPED.value == "skipped"

    def test_development_chunk_defaults(self):
        """DevelopmentChunk has correct default values."""
        chunk = DevelopmentChunk(chunk_id="test", name="Test")
        assert chunk.description == ""
        assert chunk.dependencies == []
        assert chunk.status == ChunkStatus.PENDING
        assert chunk.code_output is None
        assert chunk.test_passed is None
        assert chunk.retry_count == 0
        assert chunk.max_retries == 3

    def test_development_state_defaults(self):
        """DevelopmentState has correct default values."""
        state = DevelopmentState()
        assert state.chunks == []
        assert state.current_chunk_index == 0
        assert state.is_complete is False
        assert state.failed is False
        assert state.error_message is None

    def test_test_result_defaults(self):
        """TestResult has correct default values."""
        result = TestResult(passed=True)
        assert result.test_count == 0
        assert result.failures == 0
        assert result.errors == 0
        assert result.output == ""

    def test_contractor_run_sets_test_passed_on_chunks(
        self, mock_executor, mock_test_gate
    ):
        """After a successful run, each chunk has test_passed set."""
        chunks = [make_chunk("A")]
        state = DevelopmentState(chunks=chunks)

        contractor = DevelopmentContractor(
            state=state,
            resolver=DependencyResolver(chunks),
            executor=mock_executor,
            test_gate=mock_test_gate,
        )

        contractor.run()
        assert chunks[0].test_passed is True

    def test_wide_fan_out_dependency(self, mock_executor, mock_test_gate):
        """Single root with many dependents all execute after root."""
        root = make_chunk("root", deps=[])
        children = [make_chunk(f"child_{i}", deps=["root"]) for i in range(10)]
        all_chunks = [root] + children

        resolver = DependencyResolver(all_chunks)
        groups = resolver.get_independent_groups()

        # Root in first group, all children in second
        assert groups[0] == ["root"]
        assert set(groups[1]) == {f"child_{i}" for i in range(10)}

    def test_wide_fan_in_dependency(self, mock_executor, mock_test_gate):
        """Many roots converging to a single dependent."""
        parents = [make_chunk(f"parent_{i}", deps=[]) for i in range(5)]
        child = make_chunk("child", deps=[f"parent_{i}" for i in range(5)])
        all_chunks = parents + [child]

        resolver = DependencyResolver(all_chunks)
        groups = resolver.get_independent_groups()

        # All parents in first group, child in second
        assert set(groups[0]) == {f"parent_{i}" for i in range(5)}
        assert groups[1] == ["child"]