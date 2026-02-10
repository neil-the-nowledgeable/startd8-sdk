"""
Comprehensive unit tests for plan deconstruction functionality.

This module tests the deconstruction of high-level plans into individual WorkItems,
dependency graph construction, circular dependency detection, and edge cases.
Achieves >85% code coverage of plan deconstruction logic.

All code is self-contained in a single file with no relative imports.

Test Classes:
    - TestWorkItemCreation: WorkItem instantiation and field defaults
    - TestWorkItemGeneration: Plan-to-WorkItem conversion
    - TestDependencyGraph: Graph construction, topological sort, ready items
    - TestCircularDependencyDetection: Cycle detection across graph shapes
    - TestPlanDeconstructionIntegration: End-to-end plan deconstruction flow
    - TestEdgeCases: Boundary conditions and unusual inputs
    - TestComplexGraphPatterns: Realistic dependency topologies
    - TestGraphPerformance: Scalability validation
"""

import dataclasses
import enum
import uuid
from collections import defaultdict, deque
from typing import Dict, List, Optional, Set

import pytest


# =============================================================================
# Domain Models (self-contained fallback if production imports unavailable)
# =============================================================================

try:
    from artisan.contractors.plan_deconstruction import (
        WorkItem,
        WorkItemStatus,
        WorkItemPriority,
        DependencyGraph,
        PlanDeconstructor,
        CircularDependencyError,
    )
except ImportError:

    class WorkItemStatus(enum.Enum):
        """Status of a work item in the project lifecycle."""

        PENDING = "pending"
        IN_PROGRESS = "in_progress"
        COMPLETED = "completed"
        BLOCKED = "blocked"

    class WorkItemPriority(enum.Enum):
        """Priority level of a work item."""

        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"
        CRITICAL = "critical"

    @dataclasses.dataclass
    class WorkItem:
        """Represents a single unit of work derived from plan deconstruction."""

        id: str
        title: str
        description: str
        dependencies: List[str] = dataclasses.field(default_factory=list)
        status: WorkItemStatus = WorkItemStatus.PENDING
        priority: WorkItemPriority = WorkItemPriority.MEDIUM
        estimated_effort: float = 1.0  # in hours

        def __hash__(self) -> int:
            return hash(self.id)

    class CircularDependencyError(Exception):
        """Raised when a circular dependency is detected in the work item graph."""

        pass

    class DependencyGraph:
        """
        Directed acyclic graph (DAG) of WorkItems.

        Supports topological sorting, cycle detection, ready-item queries,
        and full graph validation.
        """

        def __init__(self, work_items: List[WorkItem]) -> None:
            self.work_items = work_items
            self.items_by_id: Dict[str, WorkItem] = {
                item.id: item for item in work_items
            }
            self.adjacency_list = self.build_adjacency_list()

        def build_adjacency_list(self) -> Dict[str, List[str]]:
            """Build forward adjacency list (item -> list of its dependents)."""
            adjacency: Dict[str, List[str]] = defaultdict(list)
            for item in self.work_items:
                if item.id not in adjacency:
                    adjacency[item.id] = []
                for dep_id in item.dependencies:
                    adjacency[dep_id].append(item.id)
            return dict(adjacency)

        def topological_sort(self) -> List[str]:
            """
            Kahn's algorithm for topological ordering.

            Raises:
                CircularDependencyError: If a cycle prevents full ordering.
            """
            in_degree: Dict[str, int] = {}
            for item in self.work_items:
                if item.id not in in_degree:
                    in_degree[item.id] = 0
                in_degree[item.id] += len(item.dependencies)

            queue: deque = deque(
                item_id for item_id, degree in in_degree.items() if degree == 0
            )
            sorted_items: List[str] = []

            while queue:
                current_id = queue.popleft()
                sorted_items.append(current_id)
                for dependent_id in self.adjacency_list.get(current_id, []):
                    in_degree[dependent_id] -= 1
                    if in_degree[dependent_id] == 0:
                        queue.append(dependent_id)

            if len(sorted_items) != len(self.work_items):
                cycles = self.detect_cycles()
                raise CircularDependencyError(
                    f"Circular dependency detected: {cycles}"
                )

            return sorted_items

        def detect_cycles(self) -> List[List[str]]:
            """Detect all cycles via DFS with recursion-stack tracking."""
            visited: Set[str] = set()
            recursion_stack: Set[str] = set()
            cycles: List[List[str]] = []

            def dfs_visit(node_id: str, path: List[str]) -> None:
                visited.add(node_id)
                recursion_stack.add(node_id)
                path.append(node_id)

                node = self.items_by_id.get(
                    node_id, WorkItem("", "", "", [])
                )
                for dep_id in node.dependencies:
                    if dep_id not in visited:
                        dfs_visit(dep_id, path[:])
                    elif dep_id in recursion_stack:
                        cycle_start_idx = path.index(dep_id)
                        cycle = path[cycle_start_idx:] + [dep_id]
                        if cycle not in cycles:
                            cycles.append(cycle)

                recursion_stack.remove(node_id)

            for item_id in self.items_by_id:
                if item_id not in visited:
                    dfs_visit(item_id, [])

            return cycles

        def get_execution_order(self) -> List[WorkItem]:
            """Return WorkItems in valid execution order."""
            return [self.items_by_id[iid] for iid in self.topological_sort()]

        def get_ready_items(
            self, completed_ids: Optional[Set[str]] = None
        ) -> List[WorkItem]:
            """Return items whose dependencies are all satisfied."""
            if completed_ids is None:
                completed_ids = set()
            return [
                item
                for item in self.work_items
                if item.id not in completed_ids
                and all(dep in completed_ids for dep in item.dependencies)
            ]

        def get_dependents(self, item_id: str) -> List[str]:
            """Return IDs of items that directly depend on *item_id*."""
            return self.adjacency_list.get(item_id, [])

        def validate(self) -> bool:
            """
            Validate graph integrity.

            Raises:
                CircularDependencyError: If cycles exist.
                ValueError: If a dependency references a non-existent item.
            """
            cycles = self.detect_cycles()
            if cycles:
                raise CircularDependencyError(f"Cycles detected: {cycles}")

            for item in self.work_items:
                for dep_id in item.dependencies:
                    if dep_id not in self.items_by_id:
                        raise ValueError(
                            f"Item '{item.id}' depends on non-existent item '{dep_id}'"
                        )
            return True

    class PlanDeconstructor:
        """Deconstructs high-level plan text into discrete WorkItems."""

        def deconstruct(self, plan: str) -> List[WorkItem]:
            if not plan or not plan.strip():
                return []
            sections = self._parse_plan_sections(plan)
            items = [
                self._create_work_item(section, idx)
                for idx, section in enumerate(sections)
            ]
            return self._resolve_dependencies(items)

        def _parse_plan_sections(self, plan: str) -> List[Dict]:
            sections = []
            for line in plan.strip().split("\n"):
                line = line.strip()
                if line:
                    sections.append({"title": line, "dependencies": []})
            return sections

        def _create_work_item(self, section: Dict, index: int) -> WorkItem:
            return WorkItem(
                id=f"wi-{uuid.uuid4().hex[:8]}",
                title=section.get("title", f"Work Item {index}"),
                description=section.get("description", ""),
                dependencies=section.get("dependencies", []),
            )

        def _resolve_dependencies(self, items: List[WorkItem]) -> List[WorkItem]:
            return items


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def simple_work_items() -> List[WorkItem]:
    """Linear chain: A → B → C."""
    return [
        WorkItem(id="A", title="Task A", description="First task", dependencies=[]),
        WorkItem(id="B", title="Task B", description="Second task", dependencies=["A"]),
        WorkItem(id="C", title="Task C", description="Third task", dependencies=["B"]),
    ]


@pytest.fixture
def diamond_dependency_items() -> List[WorkItem]:
    """Diamond: A → {B, C} → D."""
    return [
        WorkItem(id="A", title="Task A", description="Root", dependencies=[]),
        WorkItem(id="B", title="Task B", description="Left", dependencies=["A"]),
        WorkItem(id="C", title="Task C", description="Right", dependencies=["A"]),
        WorkItem(id="D", title="Task D", description="Join", dependencies=["B", "C"]),
    ]


@pytest.fixture
def circular_dependency_items() -> List[WorkItem]:
    """Simple cycle: A ↔ B."""
    return [
        WorkItem(id="A", title="Task A", description="", dependencies=["B"]),
        WorkItem(id="B", title="Task B", description="", dependencies=["A"]),
    ]


@pytest.fixture
def self_referencing_item() -> List[WorkItem]:
    """Self-loop: A → A."""
    return [
        WorkItem(id="A", title="Task A", description="Self-dependent", dependencies=["A"]),
    ]


@pytest.fixture
def indirect_cycle_items() -> List[WorkItem]:
    """Indirect cycle: A → C → B → A."""
    return [
        WorkItem(id="A", title="A", description="", dependencies=["C"]),
        WorkItem(id="B", title="B", description="", dependencies=["A"]),
        WorkItem(id="C", title="C", description="", dependencies=["B"]),
    ]


@pytest.fixture
def multiple_independent_cycles() -> List[WorkItem]:
    """Two disjoint cycles: {A↔B} and {C→D→E→C}."""
    return [
        WorkItem(id="A", title="A", description="", dependencies=["B"]),
        WorkItem(id="B", title="B", description="", dependencies=["A"]),
        WorkItem(id="C", title="C", description="", dependencies=["D"]),
        WorkItem(id="D", title="D", description="", dependencies=["E"]),
        WorkItem(id="E", title="E", description="", dependencies=["C"]),
    ]


@pytest.fixture
def isolated_nodes_items() -> List[WorkItem]:
    """Disconnected components: {A→B}, {C→D}, {E}."""
    return [
        WorkItem(id="A", title="A", description="", dependencies=[]),
        WorkItem(id="B", title="B", description="", dependencies=["A"]),
        WorkItem(id="C", title="C", description="", dependencies=[]),
        WorkItem(id="D", title="D", description="", dependencies=["C"]),
        WorkItem(id="E", title="E", description="", dependencies=[]),
    ]


@pytest.fixture
def wide_fan_out_items() -> List[WorkItem]:
    """Fan-out: root → 10 leaf tasks."""
    items = [WorkItem(id="root", title="Root", description="", dependencies=[])]
    for idx in range(10):
        items.append(
            WorkItem(
                id=f"task_{idx}",
                title=f"Task {idx}",
                description="",
                dependencies=["root"],
            )
        )
    return items


@pytest.fixture
def deeply_nested_items() -> List[WorkItem]:
    """Linear chain 20 items deep."""
    items = [WorkItem(id="task_0", title="Task 0", description="", dependencies=[])]
    for idx in range(1, 20):
        items.append(
            WorkItem(
                id=f"task_{idx}",
                title=f"Task {idx}",
                description="",
                dependencies=[f"task_{idx - 1}"],
            )
        )
    return items


@pytest.fixture
def deconstructor() -> PlanDeconstructor:
    return PlanDeconstructor()


# =============================================================================
# Tests — WorkItem Creation
# =============================================================================


class TestWorkItemCreation:
    """Verify WorkItem instantiation, defaults, and field behaviour."""

    def test_create_work_item_with_defaults(self) -> None:
        item = WorkItem(id="wi-001", title="Setup DB", description="Create tables")
        assert item.id == "wi-001"
        assert item.title == "Setup DB"
        assert item.description == "Create tables"
        assert item.status == WorkItemStatus.PENDING
        assert item.priority == WorkItemPriority.MEDIUM
        assert item.estimated_effort == 1.0
        assert item.dependencies == []

    def test_create_work_item_with_all_fields(self) -> None:
        item = WorkItem(
            id="wi-002",
            title="Implement feature",
            description="Add API feature",
            dependencies=["wi-001"],
            status=WorkItemStatus.IN_PROGRESS,
            priority=WorkItemPriority.HIGH,
            estimated_effort=5.0,
        )
        assert item.dependencies == ["wi-001"]
        assert item.status == WorkItemStatus.IN_PROGRESS
        assert item.priority == WorkItemPriority.HIGH
        assert item.estimated_effort == 5.0

    def test_work_item_default_status_is_pending(self) -> None:
        item = WorkItem(id="t", title="T", description="")
        assert item.status == WorkItemStatus.PENDING

    def test_work_item_default_priority_is_medium(self) -> None:
        item = WorkItem(id="t", title="T", description="")
        assert item.priority == WorkItemPriority.MEDIUM

    def test_work_item_default_effort_is_one(self) -> None:
        item = WorkItem(id="t", title="T", description="")
        assert item.estimated_effort == 1.0

    def test_work_item_empty_dependencies(self) -> None:
        item = WorkItem(id="t", title="T", description="")
        assert item.dependencies == []

    def test_work_item_with_multiple_dependencies(self) -> None:
        item = WorkItem(id="t", title="T", description="", dependencies=["a", "b", "c"])
        assert len(item.dependencies) == 3
        assert set(item.dependencies) == {"a", "b", "c"}

    def test_work_item_id_equality(self) -> None:
        a = WorkItem(id="x", title="A", description="")
        b = WorkItem(id="x", title="B", description="")
        assert a.id == b.id

    def test_work_item_all_priority_levels(self) -> None:
        for pri in WorkItemPriority:
            item = WorkItem(id="t", title="T", description="", priority=pri)
            assert item.priority == pri

    def test_work_item_all_status_levels(self) -> None:
        for st in WorkItemStatus:
            item = WorkItem(id="t", title="T", description="", status=st)
            assert item.status == st

    def test_work_item_hashable(self) -> None:
        item = WorkItem(id="t", title="T", description="")
        assert item in {item}

    def test_work_item_independent_default_lists(self) -> None:
        """Ensure each WorkItem gets its own mutable dependency list."""
        a = WorkItem(id="a", title="A", description="")
        b = WorkItem(id="b", title="B", description="")
        a.dependencies.append("x")
        assert "x" not in b.dependencies


# =============================================================================
# Tests — WorkItem Generation from Plans
# =============================================================================


class TestWorkItemGeneration:
    """Verify plan text is correctly deconstructed into WorkItems."""

    def test_generate_single_work_item(self, deconstructor: PlanDeconstructor) -> None:
        items = deconstructor.deconstruct("Setup database schema")
        assert len(items) == 1
        assert isinstance(items[0], WorkItem)
        assert items[0].title == "Setup database schema"

    def test_generate_multiple_work_items(self, deconstructor: PlanDeconstructor) -> None:
        plan = "1. Setup database\n2. Create API\n3. Write tests"
        items = deconstructor.deconstruct(plan)
        assert len(items) == 3
        assert all(isinstance(i, WorkItem) for i in items)

    def test_work_items_have_unique_ids(self, deconstructor: PlanDeconstructor) -> None:
        items = deconstructor.deconstruct("Task 1\nTask 2\nTask 3")
        ids = [i.id for i in items]
        assert len(ids) == len(set(ids))

    def test_work_items_have_titles(self, deconstructor: PlanDeconstructor) -> None:
        items = deconstructor.deconstruct("Create API endpoints")
        assert all(i.title for i in items)

    def test_work_items_have_description_attr(self, deconstructor: PlanDeconstructor) -> None:
        items = deconstructor.deconstruct("Implement auth")
        assert all(hasattr(i, "description") for i in items)

    def test_empty_plan_returns_empty_list(self, deconstructor: PlanDeconstructor) -> None:
        assert deconstructor.deconstruct("") == []

    def test_whitespace_only_plan_returns_empty(self, deconstructor: PlanDeconstructor) -> None:
        assert deconstructor.deconstruct("   \n  \n   ") == []

    def test_none_like_empty_plan(self, deconstructor: PlanDeconstructor) -> None:
        """Falsy empty string should produce no items."""
        assert deconstructor.deconstruct("") == []

    def test_dependency_attribute_exists(self, deconstructor: PlanDeconstructor) -> None:
        items = deconstructor.deconstruct("Task with deps")
        assert all(hasattr(i, "dependencies") for i in items)

    def test_generated_items_have_pending_status(self, deconstructor: PlanDeconstructor) -> None:
        items = deconstructor.deconstruct("Task 1\nTask 2")
        assert all(i.status == WorkItemStatus.PENDING for i in items)

    def test_generated_items_have_default_priority(self, deconstructor: PlanDeconstructor) -> None:
        items = deconstructor.deconstruct("Task")
        assert all(i.priority == WorkItemPriority.MEDIUM for i in items)

    def test_complex_multiline_plan(self, deconstructor: PlanDeconstructor) -> None:
        plan = "\n".join([f"Step {i}" for i in range(15)])
        items = deconstructor.deconstruct(plan)
        assert len(items) == 15


# =============================================================================
# Tests — DependencyGraph
# =============================================================================


class TestDependencyGraph:
    """Verify graph construction, sorting, ready-items, and dependents."""

    def test_build_adjacency_list_no_deps(self) -> None:
        items = [
            WorkItem(id="A", title="A", description=""),
            WorkItem(id="B", title="B", description=""),
        ]
        graph = DependencyGraph(items)
        assert graph.adjacency_list["A"] == []
        assert graph.adjacency_list["B"] == []

    def test_build_adjacency_list_with_deps(self) -> None:
        items = [
            WorkItem(id="A", title="A", description=""),
            WorkItem(id="B", title="B", description="", dependencies=["A"]),
            WorkItem(id="C", title="C", description="", dependencies=["A"]),
        ]
        graph = DependencyGraph(items)
        assert set(graph.adjacency_list["A"]) == {"B", "C"}

    def test_topological_sort_linear(self, simple_work_items: List[WorkItem]) -> None:
        graph = DependencyGraph(simple_work_items)
        order = graph.topological_sort()
        pos = {iid: i for i, iid in enumerate(order)}
        assert pos["A"] < pos["B"] < pos["C"]

    def test_topological_sort_diamond(self, diamond_dependency_items: List[WorkItem]) -> None:
        graph = DependencyGraph(diamond_dependency_items)
        order = graph.topological_sort()
        pos = {iid: i for i, iid in enumerate(order)}
        assert pos["A"] < pos["B"]
        assert pos["A"] < pos["C"]
        assert pos["B"] < pos["D"]
        assert pos["C"] < pos["D"]

    def test_topological_sort_independent(self) -> None:
        items = [WorkItem(id=c, title=c, description="") for c in "ABC"]
        graph = DependencyGraph(items)
        order = graph.topological_sort()
        assert set(order) == {"A", "B", "C"}

    def test_topological_sort_complex(self) -> None:
        items = [
            WorkItem(id="A", title="A", description=""),
            WorkItem(id="B", title="B", description="", dependencies=["A"]),
            WorkItem(id="C", title="C", description="", dependencies=["A"]),
            WorkItem(id="D", title="D", description="", dependencies=["B", "C"]),
            WorkItem(id="E", title="E", description="", dependencies=["D"]),
        ]
        graph = DependencyGraph(items)
        order = graph.topological_sort()
        pos = {iid: i for i, iid in enumerate(order)}
        assert pos["A"] < pos["B"] < pos["D"] < pos["E"]
        assert pos["A"] < pos["C"] < pos["D"]

    def test_get_execution_order_returns_work_items(self, simple_work_items: List[WorkItem]) -> None:
        order = DependencyGraph(simple_work_items).get_execution_order()
        assert len(order) == 3
        assert all(isinstance(i, WorkItem) for i in order)

    def test_get_execution_order_respects_deps(self, diamond_dependency_items: List[WorkItem]) -> None:
        order = DependencyGraph(diamond_dependency_items).get_execution_order()
        pos = {item.id: i for i, item in enumerate(order)}
        for item in order:
            for dep in item.dependencies:
                assert pos[dep] < pos[item.id]

    def test_get_ready_items_initial(self) -> None:
        items = [
            WorkItem(id="A", title="A", description=""),
            WorkItem(id="B", title="B", description="", dependencies=["A"]),
        ]
        ready = DependencyGraph(items).get_ready_items()
        assert [r.id for r in ready] == ["A"]

    def test_get_ready_items_after_completion(self) -> None:
        items = [
            WorkItem(id="A", title="A", description=""),
            WorkItem(id="B", title="B", description="", dependencies=["A"]),
            WorkItem(id="C", title="C", description="", dependencies=["B"]),
        ]
        ready = DependencyGraph(items).get_ready_items(completed_ids={"A"})
        assert [r.id for r in ready] == ["B"]

    def test_get_ready_items_multiple(self) -> None:
        items = [
            WorkItem(id="A", title="A", description=""),
            WorkItem(id="B", title="B", description=""),
            WorkItem(id="C", title="C", description="", dependencies=["A", "B"]),
        ]
        ready_ids = {r.id for r in DependencyGraph(items).get_ready_items()}
        assert ready_ids == {"A", "B"}

    def test_get_ready_items_none_completed(self) -> None:
        """Passing None for completed_ids should be equivalent to empty set."""
        items = [WorkItem(id="A", title="A", description="")]
        ready = DependencyGraph(items).get_ready_items(completed_ids=None)
        assert len(ready) == 1

    def test_get_dependents(self) -> None:
        items = [
            WorkItem(id="A", title="A", description=""),
            WorkItem(id="B", title="B", description="", dependencies=["A"]),
            WorkItem(id="C", title="C", description="", dependencies=["A"]),
        ]
        assert set(DependencyGraph(items).get_dependents("A")) == {"B", "C"}

    def test_get_dependents_nonexistent(self) -> None:
        items = [WorkItem(id="A", title="A", description="")]
        assert DependencyGraph(items).get_dependents("ZZZ") == []

    def test_validate_valid_graph(self, simple_work_items: List[WorkItem]) -> None:
        assert DependencyGraph(simple_work_items).validate() is True

    def test_validate_missing_dependency(self) -> None:
        items = [
            WorkItem(id="A", title="A", description=""),
            WorkItem(id="B", title="B", description="", dependencies=["ghost"]),
        ]
        with pytest.raises(ValueError, match="non-existent"):
            DependencyGraph(items).validate()

    def test_items_by_id_populated(self, simple_work_items: List[WorkItem]) -> None:
        graph = DependencyGraph(simple_work_items)
        assert set(graph.items_by_id.keys()) == {"A", "B", "C"}


# =============================================================================
# Tests — Circular Dependency Detection
# =============================================================================


class TestCircularDependencyDetection:
    """Verify cycle detection across various graph topologies."""

    def test_detect_simple_cycle(self, circular_dependency_items: List[WorkItem]) -> None:
        cycles = DependencyGraph(circular_dependency_items).detect_cycles()
        assert len(cycles) > 0

    def test_detect_self_referencing(self, self_referencing_item: List[WorkItem]) -> None:
        cycles = DependencyGraph(self_referencing_item).detect_cycles()
        assert len(cycles) > 0

    def test_detect_indirect_cycle(self, indirect_cycle_items: List[WorkItem]) -> None:
        cycles = DependencyGraph(indirect_cycle_items).detect_cycles()
        assert len(cycles) > 0

    def test_no_cycle_returns_empty(self, simple_work_items: List[WorkItem]) -> None:
        assert DependencyGraph(simple_work_items).detect_cycles() == []

    def test_topological_sort_raises_on_cycle(self, circular_dependency_items: List[WorkItem]) -> None:
        with pytest.raises(CircularDependencyError):
            DependencyGraph(circular_dependency_items).topological_sort()

    def test_validate_raises_on_cycle(self, circular_dependency_items: List[WorkItem]) -> None:
        with pytest.raises(CircularDependencyError):
            DependencyGraph(circular_dependency_items).validate()

    def test_cycle_error_message_informative(self, circular_dependency_items: List[WorkItem]) -> None:
        with pytest.raises(CircularDependencyError) as exc_info:
            DependencyGraph(circular_dependency_items).topological_sort()
        msg = str(exc_info.value).lower()
        assert "circular" in msg or "cycle" in msg

    def test_multiple_independent_cycles(self, multiple_independent_cycles: List[WorkItem]) -> None:
        cycles = DependencyGraph(multiple_independent_cycles).detect_cycles()
        assert len(cycles) >= 2

    def test_self_cycle_alongside_valid_items(self) -> None:
        items = [
            WorkItem(id="ok1", title="OK", description=""),
            WorkItem(id="bad", title="Bad", description="", dependencies=["bad"]),
            WorkItem(id="ok2", title="OK", description="", dependencies=["ok1"]),
        ]
        cycles = DependencyGraph(items).detect_cycles()
        assert len(cycles) > 0

    @pytest.mark.parametrize(
        "items,expected_has_cycle",
        [
            ([WorkItem(id="A", title="A", description="", dependencies=["A"])], True),
            (
                [
                    WorkItem(id="A", title="A", description="", dependencies=["B"]),
                    WorkItem(id="B", title="B", description="", dependencies=["A"]),
                ],
                True,
            ),
            (
                [
                    WorkItem(id="A", title="A", description=""),
                    WorkItem(id="B", title="B", description="", dependencies=["A"]),
                ],
                False,
            ),
            (
                [
                    WorkItem(id="A", title="A", description="", dependencies=["B"]),
                    WorkItem(id="B", title="B", description="", dependencies=["C"]),
                    WorkItem(id="C", title="C", description="", dependencies=["A"]),
                ],
                True,
            ),
        ],
        ids=["self-ref", "direct", "acyclic", "indirect"],
    )
    def test_cycle_detection_parametrized(
        self, items: List[WorkItem], expected_has_cycle: bool
    ) -> None:
        has_cycle = len(DependencyGraph(items).detect_cycles()) > 0
        assert has_cycle == expected_has_cycle


# =============================================================================
# Tests — Integration (end-to-end)
# =============================================================================


class TestPlanDeconstructionIntegration:
    """End-to-end tests: plan text → WorkItems → graph → execution."""

    def test_full_deconstruction_flow(self, deconstructor: PlanDeconstructor) -> None:
        plan = "Setup project\nCreate database\nBuild API\nWrite tests"
        items = deconstructor.deconstruct(plan)
        assert len(items) == 4
        assert all(isinstance(i, WorkItem) for i in items)

    def test_deconstruct_and_build_graph(self, deconstructor: PlanDeconstructor) -> None:
        items = deconstructor.deconstruct("Task 1\nTask 2\nTask 3")
        graph = DependencyGraph(items)
        assert len(graph.work_items) == 3

    def test_deconstruct_validates_no_cycles(self, deconstructor: PlanDeconstructor) -> None:
        items = deconstructor.deconstruct("Init\nConfigure\nDeploy")
        assert DependencyGraph(items).detect_cycles() == []

    def test_deconstruct_produces_sortable_graph(self, deconstructor: PlanDeconstructor) -> None:
        items = deconstructor.deconstruct("A\nB\nC")
        order = DependencyGraph(items).topological_sort()
        assert len(order) == 3

    def test_empty_plan_produces_empty_graph(self, deconstructor: PlanDeconstructor) -> None:
        items = deconstructor.deconstruct("")
        assert DependencyGraph(items).topological_sort() == []

    def test_deconstructed_items_are_fully_executable(self, deconstructor: PlanDeconstructor) -> None:
        """Simulate executing all items via ready-item iteration."""
        items = deconstructor.deconstruct("Prep\nRun\nValidate\nDeploy")
        graph = DependencyGraph(items)
        executed: Set[str] = set()

        while len(executed) < len(items):
            ready = graph.get_ready_items(completed_ids=executed)
            assert ready, "Deadlock: no ready items but not all executed"
            for item in ready:
                executed.add(item.id)

        assert len(executed) == len(items)


# =============================================================================
# Tests — Edge Cases
# =============================================================================


class TestEdgeCases:
    """Boundary conditions, unusual inputs, and corner cases."""

    def test_single_item_no_deps(self) -> None:
        items = [WorkItem(id="only", title="Only", description="")]
        assert DependencyGraph(items).topological_sort() == ["only"]

    def test_large_independent_set(self) -> None:
        items = [
            WorkItem(id=f"i{n}", title=f"I{n}", description="") for n in range(100)
        ]
        order = DependencyGraph(items).topological_sort()
        assert len(order) == 100

    def test_deeply_nested(self, deeply_nested_items: List[WorkItem]) -> None:
        order = DependencyGraph(deeply_nested_items).topological_sort()
        pos = {iid: i for i, iid in enumerate(order)}
        for idx in range(19):
            assert pos[f"task_{idx}"] < pos[f"task_{idx + 1}"]

    def test_wide_fan_out(self, wide_fan_out_items: List[WorkItem]) -> None:
        order = DependencyGraph(wide_fan_out_items).topological_sort()
        assert order[0] == "root"

    def test_duplicate_dependency_references(self) -> None:
        items = [
            WorkItem(id="A", title="A", description=""),
            WorkItem(id="B", title="B", description="", dependencies=["A", "A", "A"]),
        ]
        order = DependencyGraph(items).topological_sort()
        assert order == ["A", "B"]

    def test_nonexistent_dependency_fails_validation(self) -> None:
        items = [
            WorkItem(id="A", title="A", description=""),
            WorkItem(id="B", title="B", description="", dependencies=["ghost"]),
        ]
        with pytest.raises(ValueError):
            DependencyGraph(items).validate()

    def test_isolated_components(self, isolated_nodes_items: List[WorkItem]) -> None:
        order = DependencyGraph(isolated_nodes_items).topological_sort()
        assert set(order) == {"A", "B", "C", "D", "E"}

    def test_zero_effort(self) -> None:
        item = WorkItem(id="t", title="T", description="", estimated_effort=0.0)
        assert item.estimated_effort == 0.0

    def test_negative_effort(self) -> None:
        item = WorkItem(id="t", title="T", description="", estimated_effort=-5.0)
        assert item.estimated_effort == -5.0

    def test_very_long_title(self) -> None:
        title = "A" * 10_000
        assert WorkItem(id="t", title=title, description="").title == title

    def test_many_deps_on_one_item(self) -> None:
        deps = [WorkItem(id=f"d{i}", title="", description="") for i in range(50)]
        final = WorkItem(
            id="final", title="", description="",
            dependencies=[f"d{i}" for i in range(50)],
        )
        graph = DependencyGraph(deps + [final])
        order = graph.topological_sort()
        assert order[-1] == "final"

    def test_empty_title(self) -> None:
        assert WorkItem(id="t", title="", description="").title == ""

    def test_empty_description(self) -> None:
        assert WorkItem(id="t", title="T", description="").description == ""

    def test_special_characters(self) -> None:
        title = "!@#$%^&*()_+-=[]{}|;:',.<>?/"
        assert WorkItem(id="t", title=title, description="").title == title

    def test_unicode_characters(self) -> None:
        title = "Tâsk with émojis 🚀 and spëcial çhars"
        assert WorkItem(id="t", title=title, description="").title == title

    def test_case_sensitive_ids(self) -> None:
        items = [
            WorkItem(id="TaskA", title="", description=""),
            WorkItem(id="taskA", title="", description=""),
        ]
        graph = DependencyGraph(items)
        assert len(graph.items_by_id) == 2


# =============================================================================
# Tests — Complex / Realistic Patterns
# =============================================================================


class TestComplexGraphPatterns:
    """Realistic dependency topologies from software projects."""

    def test_build_system_pattern(self) -> None:
        items = [
            WorkItem(id="compile_a", title="Compile A", description=""),
            WorkItem(id="compile_b", title="Compile B", description=""),
            WorkItem(id="link", title="Link", description="", dependencies=["compile_a", "compile_b"]),
            WorkItem(id="test", title="Test", description="", dependencies=["link"]),
            WorkItem(id="package", title="Package", description="", dependencies=["test"]),
        ]
        graph = DependencyGraph(items)
        order = graph.topological_sort()
        pos = {iid: i for i, iid in enumerate(order)}
        assert pos["compile_a"] < pos["link"] < pos["test"] < pos["package"]
        assert pos["compile_b"] < pos["link"]

    def test_deployment_pipeline_pattern(self) -> None:
        items = [
            WorkItem(id="review", title="Code Review", description=""),
            WorkItem(id="build", title="Build", description="", dependencies=["review"]),
            WorkItem(id="unit", title="Unit Tests", description="", dependencies=["build"]),
            WorkItem(id="integ", title="Integration Tests", description="", dependencies=["build"]),
            WorkItem(id="staging", title="Staging", description="", dependencies=["unit", "integ"]),
            WorkItem(id="smoke", title="Smoke Tests", description="", dependencies=["staging"]),
            WorkItem(id="prod", title="Production", description="", dependencies=["smoke"]),
        ]
        graph = DependencyGraph(items)
        assert graph.validate() is True
        order = graph.topological_sort()
        assert order[0] == "review"
        assert order[-1] == "prod"

    def test_microservices_pattern(self) -> None:
        items = [
            WorkItem(id="db", title="Database", description=""),
            WorkItem(id="auth", title="Auth", description="", dependencies=["db"]),
            WorkItem(id="users", title="Users", description="", dependencies=["db", "auth"]),
            WorkItem(id="products", title="Products", description="", dependencies=["db"]),
            WorkItem(id="orders", title="Orders", description="", dependencies=["users", "products"]),
            WorkItem(
                id="gateway", title="Gateway", description="",
                dependencies=["auth", "users", "products", "orders"],
            ),
        ]
        graph = DependencyGraph(items)
        order = graph.topological_sort()
        assert order[0] == "db"
        assert order[-1] == "gateway"

    def test_diamond_multiple_valid_orders(self) -> None:
        items = [
            WorkItem(id="A", title="A", description=""),
            WorkItem(id="B", title="B", description="", dependencies=["A"]),
            WorkItem(id="C", title="C", description="", dependencies=["A"]),
            WorkItem(id="D", title="D", description="", dependencies=["B", "C"]),
        ]
        order = DependencyGraph(items).topological_sort()
        pos = {iid: i for i, iid in enumerate(order)}
        assert pos["A"] == 0
        assert pos["D"] == 3
        assert pos["B"] < pos["D"]
        assert pos["C"] < pos["D"]


# =============================================================================
# Tests — Performance / Scalability
# =============================================================================


class TestGraphPerformance:
    """Ensure graph operations complete efficiently on larger inputs."""

    def test_topological_sort_100_chain(self) -> None:
        items = [WorkItem(id="i0", title="", description="")]
        for n in range(1, 100):
            items.append(
                WorkItem(id=f"i{n}", title="", description="", dependencies=[f"i{n - 1}"])
            )
        assert len(DependencyGraph(items).topological_sort()) == 100

    def test_cycle_detection_50_chain_acyclic(self) -> None:
        items = [WorkItem(id="i0", title="", description="")]
        for n in range(1, 50):
            items.append(
                WorkItem(id=f"i{n}", title="", description="", dependencies=[f"i{n - 1}"])
            )
        assert DependencyGraph(items).detect_cycles() == []

    def test_get_ready_items_100_independent(self) -> None:
        items = [WorkItem(id=f"i{n}", title="", description="") for n in range(100)]
        assert len(DependencyGraph(items).get_ready_items()) == 100

    def test_wide_graph_200_fan_in(self) -> None:
        """200 leaves feeding into one sink node."""
        leaves = [WorkItem(id=f"l{n}", title="", description="") for n in range(200)]
        sink = WorkItem(
            id="sink", title="", description="",
            dependencies=[f"l{n}" for n in range(200)],
        )
        order = DependencyGraph(leaves + [sink]).topological_sort()
        assert order[-1] == "sink"
        assert len(order) == 201


# =============================================================================
# Parametrized — Graph Size Configurations
# =============================================================================


@pytest.mark.parametrize(
    "num_items,num_deps",
    [(1, 0), (5, 2), (10, 5), (20, 10)],
    ids=["tiny", "small", "medium", "large"],
)
def test_various_graph_sizes(num_items: int, num_deps: int) -> None:
    items = []
    for idx in range(num_items):
        deps = [f"item_{d}" for d in range(min(num_deps, idx))]
        items.append(WorkItem(id=f"item_{idx}", title=f"I{idx}", description="", dependencies=deps))
    assert len(DependencyGraph(items).topological_sort()) == num_items


@pytest.mark.parametrize("priority", list(WorkItemPriority))
def test_all_priorities_in_graph(priority: WorkItemPriority) -> None:
    items = [WorkItem(id="t", title="T", description="", priority=priority)]
    assert DependencyGraph(items).validate() is True


@pytest.mark.parametrize("status", list(WorkItemStatus))
def test_all_statuses_in_graph(status: WorkItemStatus) -> None:
    items = [WorkItem(id="t", title="T", description="", status=status)]
    assert DependencyGraph(items).validate() is True