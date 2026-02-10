"""
Plan Deconstruction Phase Module

Implements the Plan Deconstruction Phase of an Artisan contractor system.
Takes a high-level task/plan and breaks it down into atomic WorkItem objects
following a draft->validate pattern, with explicit acceptance criteria and
dependency graph management.

This module is self-contained with no relative imports.
"""

import dataclasses
import enum
import logging
import uuid
from collections import deque, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple
from copy import deepcopy

logger = logging.getLogger(__name__)


# ─── Enums ───


class WorkItemStatus(enum.Enum):
    """Status of a WorkItem through its lifecycle."""

    DRAFT = "draft"
    VALIDATED = "validated"
    REJECTED = "rejected"


class ComplexityLevel(enum.Enum):
    """Estimated complexity of a WorkItem."""

    TRIVIAL = "trivial"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ─── Exceptions ───


class PlanDeconstructionError(Exception):
    """Base exception for plan deconstruction errors."""

    pass


class CycleDetectedError(PlanDeconstructionError):
    """Raised when a cycle is detected in the dependency graph."""

    pass


class ValidationError(PlanDeconstructionError):
    """Raised when WorkItem validation fails."""

    pass


class InvalidPlanError(PlanDeconstructionError):
    """Raised when the input plan is invalid or malformed."""

    pass


# ─── Data Classes ───


@dataclasses.dataclass
class AcceptanceCriterion:
    """A single acceptance criterion for a WorkItem."""

    id: str
    description: str
    verifiable: bool = True

    def __post_init__(self) -> None:
        """Validate criterion on initialization."""
        if not self.description or not str(self.description).strip():
            raise ValueError("AcceptanceCriterion description cannot be empty")


@dataclasses.dataclass
class WorkItem:
    """
    An atomic unit of work with acceptance criteria and dependencies.

    Follows a draft->validate lifecycle: items are created as DRAFT,
    then transition to VALIDATED or REJECTED after validation.
    """

    id: str
    title: str
    description: str
    status: WorkItemStatus
    acceptance_criteria: List[AcceptanceCriterion]
    dependencies: List[str]  # List of WorkItem IDs this item depends on
    complexity: ComplexityLevel
    metadata: Dict[str, Any] = dataclasses.field(default_factory=dict)
    parent_plan_key: str = ""
    rejection_reason: str = ""

    def __post_init__(self) -> None:
        """Validate WorkItem state on initialization."""
        if self.status == WorkItemStatus.REJECTED and not self.rejection_reason:
            raise ValueError(
                "WorkItem with REJECTED status must have a non-empty rejection_reason"
            )


@dataclasses.dataclass
class DeconstructionResult:
    """Result of the plan deconstruction process."""

    work_items: List[WorkItem]  # Validated items only
    rejected_items: List[WorkItem]  # Rejected items with reasons
    dependency_graph: "DependencyGraph"  # DAG of dependencies
    execution_order: List[str]  # Topologically sorted WorkItem IDs
    summary: Dict[str, Any]  # Statistics and metadata


# ─── Dependency Graph ───


class DependencyGraph:
    """
    Directed Acyclic Graph (DAG) of WorkItem dependencies.

    Edge semantics: an edge from A -> B means "A depends on B",
    i.e., B must complete before A can start.

    Supports cycle detection, topological sorting, and dependency queries.
    """

    def __init__(self) -> None:
        """Initialize an empty dependency graph."""
        # _adjacency[node] = set of nodes that `node` depends on
        self._adjacency: Dict[str, Set[str]] = {}
        self._all_nodes: Set[str] = set()

    def add_node(self, work_item_id: str) -> None:
        """Add a node to the graph (idempotent)."""
        self._all_nodes.add(work_item_id)
        if work_item_id not in self._adjacency:
            self._adjacency[work_item_id] = set()

    def add_edge(self, from_id: str, to_id: str) -> None:
        """
        Add a directed edge: from_id depends on to_id.

        Args:
            from_id: The dependent WorkItem ID.
            to_id: The dependency (prerequisite) WorkItem ID.
        """
        self.add_node(from_id)
        self.add_node(to_id)
        self._adjacency[from_id].add(to_id)

    def has_cycle(self) -> bool:
        """
        Check if the graph contains a cycle using DFS with coloring.

        Returns:
            True if a cycle exists, False otherwise.
        """
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {node: WHITE for node in self._all_nodes}

        def dfs(node: str) -> bool:
            color[node] = GRAY
            for neighbor in self._adjacency.get(node, set()):
                if color[neighbor] == GRAY:
                    return True  # back edge → cycle
                if color[neighbor] == WHITE and dfs(neighbor):
                    return True
            color[node] = BLACK
            return False

        for node in self._all_nodes:
            if color[node] == WHITE:
                if dfs(node):
                    return True
        return False

    def topological_sort(self) -> List[str]:
        """
        Return topologically sorted WorkItem IDs using Kahn's algorithm.

        Dependencies come before the items that depend on them.

        Raises:
            CycleDetectedError: If the graph contains a cycle.

        Returns:
            List of WorkItem IDs in valid execution order.
        """
        # Compute in-degree: for each node, count how many edges point TO it.
        # An edge from A->B (A depends on B) means B has an incoming "reverse"
        # perspective. But for execution order, we want B before A.
        # We model: edge A->B means A depends on B.
        # In-degree of a node = number of nodes that list it as a dependency
        # i.e., number of edges pointing TO this node in the "depends-on" graph
        # Actually for Kahn's on execution order:
        #   We want to produce nodes whose prerequisites are satisfied.
        #   A node's "in-degree" = number of its dependencies = len(_adjacency[node])

        in_degree: Dict[str, int] = {}
        for node in self._all_nodes:
            in_degree[node] = len(self._adjacency.get(node, set()))

        # Nodes with no dependencies can execute first
        queue: deque[str] = deque(
            sorted(node for node in self._all_nodes if in_degree[node] == 0)
        )

        result: List[str] = []

        while queue:
            current = queue.popleft()
            result.append(current)

            # For each node that depends on `current`, reduce its in-degree
            for node in sorted(self._all_nodes):
                if current in self._adjacency.get(node, set()):
                    in_degree[node] -= 1
                    if in_degree[node] == 0:
                        queue.append(node)

        if len(result) != len(self._all_nodes):
            raise CycleDetectedError(
                "Dependency graph contains a cycle; topological sort impossible"
            )

        return result

    def get_dependencies(self, work_item_id: str) -> Set[str]:
        """Get direct dependencies (prerequisites) of a WorkItem."""
        return set(self._adjacency.get(work_item_id, set()))

    def get_dependents(self, work_item_id: str) -> Set[str]:
        """Get items that directly depend on the given WorkItem."""
        dependents: Set[str] = set()
        for node, deps in self._adjacency.items():
            if work_item_id in deps:
                dependents.add(node)
        return dependents

    def get_roots(self) -> List[str]:
        """Get items with no dependencies (can start immediately)."""
        return sorted(
            node for node in self._all_nodes if not self._adjacency.get(node, set())
        )

    def get_leaves(self) -> List[str]:
        """Get items that no other item depends on (final deliverables)."""
        return sorted(node for node in self._all_nodes if not self.get_dependents(node))

    @property
    def nodes(self) -> Set[str]:
        """All node IDs in the graph."""
        return set(self._all_nodes)

    @property
    def edges(self) -> List[Tuple[str, str]]:
        """All edges as (from_id, to_id) tuples."""
        result = []
        for node, deps in self._adjacency.items():
            for dep in deps:
                result.append((node, dep))
        return result

    def to_dict(self) -> Dict[str, List[str]]:
        """Export adjacency list as a plain dictionary."""
        return {node: sorted(list(deps)) for node, deps in self._adjacency.items()}


# ─── Validation ───


class WorkItemValidator:
    """
    Validates draft WorkItems against configurable rules.

    Implements the validate step of the draft->validate pattern.
    Each draft item is checked and transitioned to VALIDATED or REJECTED.
    """

    def __init__(self, known_item_ids: Optional[Set[str]] = None) -> None:
        """
        Initialize the validator.

        Args:
            known_item_ids: Set of valid WorkItem IDs for dependency reference checks.
        """
        self.known_item_ids: Set[str] = known_item_ids or set()

    def validate(self, work_item: WorkItem) -> WorkItem:
        """
        Validate a draft WorkItem and return a new instance with updated status.

        Uses dataclasses.replace() to maintain immutability of state transitions.

        Args:
            work_item: A WorkItem in DRAFT status.

        Returns:
            A new WorkItem with status VALIDATED or REJECTED.
        """
        if work_item.status != WorkItemStatus.DRAFT:
            return work_item

        checks = [
            self._check_title,
            self._check_description,
            self._check_acceptance_criteria,
            self._check_no_self_dependency,
            self._check_dependencies,
        ]

        for check_func in checks:
            reason = check_func(work_item)
            if reason:
                logger.warning(
                    "WorkItem '%s' (id=%s) rejected: %s",
                    work_item.title,
                    work_item.id,
                    reason,
                )
                return dataclasses.replace(
                    work_item,
                    status=WorkItemStatus.REJECTED,
                    rejection_reason=reason,
                )

        logger.debug("WorkItem '%s' (id=%s) validated", work_item.title, work_item.id)
        return dataclasses.replace(work_item, status=WorkItemStatus.VALIDATED)

    def _check_title(self, wi: WorkItem) -> Optional[str]:
        """Title must be non-empty."""
        if not wi.title or not str(wi.title).strip():
            return "Title is empty or missing"
        return None

    def _check_description(self, wi: WorkItem) -> Optional[str]:
        """Description must be non-empty."""
        if not wi.description or not str(wi.description).strip():
            return "Description is empty or missing"
        return None

    def _check_acceptance_criteria(self, wi: WorkItem) -> Optional[str]:
        """At least one acceptance criterion is required."""
        if not wi.acceptance_criteria:
            return "At least one acceptance criterion is required"
        return None

    def _check_no_self_dependency(self, wi: WorkItem) -> Optional[str]:
        """WorkItem must not depend on itself."""
        if wi.id in wi.dependencies:
            return "WorkItem cannot depend on itself"
        return None

    def _check_dependencies(self, wi: WorkItem) -> Optional[str]:
        """All listed dependencies must reference known WorkItem IDs."""
        for dep_id in wi.dependencies:
            if dep_id not in self.known_item_ids:
                return f"Dependency '{dep_id}' does not reference a known WorkItem"
        return None


# ─── Plan Deconstructor ───


class PlanDeconstructor:
    """
    Main orchestrator for plan deconstruction.

    Pipeline: parse plan -> draft WorkItems -> validate -> build DAG -> result.

    Implements the draft->validate pattern where every WorkItem starts as DRAFT
    and is explicitly transitioned to VALIDATED or REJECTED.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize the deconstructor.

        Args:
            config: Optional configuration dictionary:
                - auto_suffix_duplicates (bool, default True): rename duplicate titles
                - strict_cycles (bool, default True): raise on cycle detection
        """
        self.config: Dict[str, Any] = config or {}
        self.auto_suffix_duplicates: bool = self.config.get(
            "auto_suffix_duplicates", True
        )
        self.strict_cycles: bool = self.config.get("strict_cycles", True)

    def deconstruct(self, plan: Dict[str, Any]) -> DeconstructionResult:
        """
        Full deconstruction pipeline.

        Steps:
            1. Validate plan input structure
            2. Extract all tasks as DRAFT WorkItems
            3. Validate all drafts (draft->validate pattern)
            4. Build dependency graph from validated items
            5. Compute execution order via topological sort
            6. Generate summary statistics

        Args:
            plan: High-level plan dict. Must contain 'tasks' and/or 'phases'.
                  Each task dict should have: title, description,
                  and optionally: depends_on, acceptance_criteria, complexity.

        Returns:
            DeconstructionResult with validated items, rejected items,
            dependency graph, execution order, and summary.

        Raises:
            InvalidPlanError: If plan structure is invalid.
            CycleDetectedError: If dependency graph has cycles (strict mode).
        """
        logger.info("Starting plan deconstruction")
        self._validate_plan_input(plan)

        # Step 1: Extract all tasks as DRAFT WorkItems
        draft_items = self._extract_work_items(plan)
        logger.info("Extracted %d draft work items", len(draft_items))

        # Step 2: Validate all draft items (draft -> validate pattern)
        validated_items, rejected_items = self._validate_work_items(draft_items)
        logger.info(
            "Validation complete: %d validated, %d rejected",
            len(validated_items),
            len(rejected_items),
        )

        # Step 3: Build dependency graph from validated items only
        dependency_graph = self._build_dependency_graph(validated_items)

        # Step 4: Compute execution order
        execution_order = dependency_graph.topological_sort()
        logger.info("Execution order computed: %d items", len(execution_order))

        # Step 5: Generate summary
        summary = self._generate_summary(
            validated_items, rejected_items, dependency_graph, execution_order
        )

        logger.info("Plan deconstruction complete: %s", summary)

        return DeconstructionResult(
            work_items=validated_items,
            rejected_items=rejected_items,
            dependency_graph=dependency_graph,
            execution_order=execution_order,
            summary=summary,
        )

    def _validate_plan_input(self, plan: Dict[str, Any]) -> None:
        """
        Validate the top-level plan structure.

        Raises:
            InvalidPlanError: If plan is not a dict, is empty,
                              or lacks 'tasks'/'phases'.
        """
        if not isinstance(plan, dict):
            raise InvalidPlanError("Plan must be a dictionary")
        if not plan:
            raise InvalidPlanError("Plan cannot be empty")
        if "tasks" not in plan and "phases" not in plan:
            raise InvalidPlanError('Plan must contain "tasks" or "phases" or both')

    def _extract_work_items(self, plan: Dict[str, Any]) -> List[WorkItem]:
        """
        Parse plan and produce DRAFT WorkItems.

        Maintains a global title->id map so dependencies can reference
        items across phases and standalone tasks.

        Args:
            plan: Validated plan dictionary.

        Returns:
            List of WorkItems in DRAFT status.
        """
        # Global title-to-id mapping for cross-reference dependency resolution
        title_to_id: Dict[str, str] = {}
        all_raw_tasks: List[Tuple[Dict[str, Any], str]] = []  # (task_dict, parent_key)

        # Collect all tasks with their parent keys
        if "phases" in plan:
            phases = plan["phases"]
            if isinstance(phases, list):
                for phase_idx, phase in enumerate(phases):
                    if not isinstance(phase, dict):
                        logger.warning("Phase %d is not a dict, skipping", phase_idx)
                        continue
                    phase_name = str(phase.get("name") or f"Phase {phase_idx}").strip()
                    phase_tasks = phase.get("tasks", [])
                    if isinstance(phase_tasks, list):
                        for task in phase_tasks:
                            if isinstance(task, dict):
                                all_raw_tasks.append((task, phase_name))

        if "tasks" in plan:
            tasks = plan["tasks"]
            if isinstance(tasks, list):
                for task in tasks:
                    if isinstance(task, dict):
                        all_raw_tasks.append((task, "standalone"))

        # First pass: assign IDs and build title map
        task_entries: List[
            Tuple[Dict[str, Any], str, str]
        ] = []  # (task, parent_key, id)

        for task, parent_key in all_raw_tasks:
            task_id = str(uuid.uuid4())
            title = str(task.get("title") or "").strip()

            if title:
                if title in title_to_id and self.auto_suffix_duplicates:
                    # Find a unique suffixed title
                    count = 2
                    candidate = f"{title} ({count})"
                    while candidate in title_to_id:
                        count += 1
                        candidate = f"{title} ({count})"
                    title_to_id[candidate] = task_id
                    logger.debug(
                        "Duplicate title '%s' renamed to '%s'", title, candidate
                    )
                else:
                    title_to_id[title] = task_id

            task_entries.append((task, parent_key, task_id))

        # Collect phase-level dependency info
        phase_task_ids: Dict[str, List[str]] = defaultdict(list)
        phase_depends_on: Dict[str, str] = {}

        if "phases" in plan and isinstance(plan["phases"], list):
            entry_idx = 0
            for phase_idx, phase in enumerate(plan["phases"]):
                if not isinstance(phase, dict):
                    continue
                phase_name = str(phase.get("name") or f"Phase {phase_idx}").strip()
                phase_tasks = phase.get("tasks", [])
                if isinstance(phase_tasks, list):
                    for task in phase_tasks:
                        if isinstance(task, dict) and entry_idx < len(task_entries):
                            _, pk, tid = task_entries[entry_idx]
                            if pk == phase_name:
                                phase_task_ids[phase_name].append(tid)
                                entry_idx += 1

                dep_phase = phase.get("depends_on_phase")
                if dep_phase:
                    phase_depends_on[phase_name] = str(dep_phase).strip()

        # Second pass: create WorkItem objects
        draft_items: List[WorkItem] = []

        for task, parent_key, task_id in task_entries:
            title = str(task.get("title") or "").strip()
            description = str(task.get("description") or "").strip()
            complexity_str = str(task.get("complexity") or "medium").lower()

            # Parse complexity
            try:
                complexity = ComplexityLevel(complexity_str)
            except ValueError:
                try:
                    complexity = ComplexityLevel[complexity_str.upper()]
                except (KeyError, AttributeError):
                    complexity = ComplexityLevel.MEDIUM

            # Resolve task-level dependencies (by title)
            depends_on_raw = task.get("depends_on", [])
            if isinstance(depends_on_raw, str):
                depends_on_raw = [depends_on_raw]
            if not isinstance(depends_on_raw, list):
                depends_on_raw = []

            resolved_deps: List[str] = []
            raw_dep_titles: List[str] = []

            for dep_ref in depends_on_raw:
                dep_str = str(dep_ref).strip()
                raw_dep_titles.append(dep_str)
                if dep_str in title_to_id:
                    resolved_deps.append(title_to_id[dep_str])
                else:
                    # Could be an ID directly
                    resolved_deps.append(dep_str)
                    logger.debug(
                        "Dependency '%s' not found in title map; keeping as raw ID",
                        dep_str,
                    )

            # Add inter-phase dependencies
            if parent_key in phase_depends_on:
                predecessor_phase = phase_depends_on[parent_key]
                predecessor_ids = phase_task_ids.get(predecessor_phase, [])
                for pid in predecessor_ids:
                    if pid not in resolved_deps:
                        resolved_deps.append(pid)

            # Generate acceptance criteria
            acceptance_criteria = self._parse_acceptance_criteria(task)

            # Build metadata
            metadata: Dict[str, Any] = {
                "_raw_depends_on": raw_dep_titles,
            }
            # Copy non-internal fields from original task
            for key, value in task.items():
                if key not in (
                    "title",
                    "description",
                    "complexity",
                    "depends_on",
                    "acceptance_criteria",
                    "_generated_id",
                ):
                    metadata[key] = deepcopy(value)

            work_item = WorkItem(
                id=task_id,
                title=title,
                description=description,
                status=WorkItemStatus.DRAFT,
                acceptance_criteria=acceptance_criteria,
                dependencies=resolved_deps,
                complexity=complexity,
                metadata=metadata,
                parent_plan_key=parent_key,
                rejection_reason="",
            )

            logger.debug(
                "Created draft WorkItem: '%s' (id=%s, deps=%d)",
                title,
                task_id,
                len(resolved_deps),
            )
            draft_items.append(work_item)

        return draft_items

    def _parse_acceptance_criteria(
        self, task: Dict[str, Any]
    ) -> List[AcceptanceCriterion]:
        """
        Parse or generate acceptance criteria for a task.

        Supports three formats:
            - List of strings: each becomes a criterion
            - List of dicts with 'description' and optional 'verifiable'
            - Auto-generated from task description if none provided

        Args:
            task: Task dictionary.

        Returns:
            List of AcceptanceCriterion objects.
        """
        criteria: List[AcceptanceCriterion] = []
        explicit = task.get("acceptance_criteria", [])

        if isinstance(explicit, list):
            for item in explicit:
                if isinstance(item, str):
                    text = item.strip()
                    if text:
                        criteria.append(
                            AcceptanceCriterion(
                                id=str(uuid.uuid4()),
                                description=text,
                                verifiable=True,
                            )
                        )
                elif isinstance(item, dict):
                    desc = str(item.get("description") or "").strip()
                    if desc:
                        criteria.append(
                            AcceptanceCriterion(
                                id=str(uuid.uuid4()),
                                description=desc,
                                verifiable=item.get("verifiable", True),
                            )
                        )
        elif isinstance(explicit, str):
            text = explicit.strip()
            if text:
                criteria.append(
                    AcceptanceCriterion(
                        id=str(uuid.uuid4()),
                        description=text,
                        verifiable=True,
                    )
                )

        # Auto-generate from description if no explicit criteria provided
        if not criteria:
            description = str(task.get("description") or "").strip()
            if description:
                criteria.append(
                    AcceptanceCriterion(
                        id=str(uuid.uuid4()),
                        description=f"Implementation complete: {description}",
                        verifiable=True,
                    )
                )

        return criteria

    def _validate_work_items(
        self, drafts: List[WorkItem]
    ) -> Tuple[List[WorkItem], List[WorkItem]]:
        """
        Run the validate step of draft->validate on all items.

        Args:
            drafts: List of DRAFT WorkItems.

        Returns:
            Tuple of (validated_items, rejected_items).
        """
        known_ids: Set[str] = {item.id for item in drafts}
        validator = WorkItemValidator(known_item_ids=known_ids)

        validated: List[WorkItem] = []
        rejected: List[WorkItem] = []

        for item in drafts:
            result = validator.validate(item)
            if result.status == WorkItemStatus.VALIDATED:
                validated.append(result)
            elif result.status == WorkItemStatus.REJECTED:
                rejected.append(result)
            else:
                # Should not happen, but handle gracefully
                logger.warning(
                    "WorkItem '%s' remained in %s after validation",
                    item.title,
                    result.status,
                )
                rejected.append(
                    dataclasses.replace(
                        result,
                        status=WorkItemStatus.REJECTED,
                        rejection_reason="Unexpected status after validation",
                    )
                )

        return validated, rejected

    def _build_dependency_graph(
        self, validated_items: List[WorkItem]
    ) -> DependencyGraph:
        """
        Build a DAG from validated WorkItems.

        Only includes dependencies that reference other validated items.

        Args:
            validated_items: List of VALIDATED WorkItems.

        Returns:
            DependencyGraph instance.

        Raises:
            CycleDetectedError: If strict_cycles is True and cycle found.
        """
        graph = DependencyGraph()
        valid_ids: Set[str] = {item.id for item in validated_items}

        # Add all validated items as nodes
        for item in validated_items:
            graph.add_node(item.id)

        # Add edges for dependencies (only to other validated items)
        for item in validated_items:
            for dep_id in item.dependencies:
                if dep_id in valid_ids:
                    graph.add_edge(item.id, dep_id)

        # Check for cycles
        if graph.has_cycle():
            if self.strict_cycles:
                raise CycleDetectedError(
                    "Dependency graph contains a cycle; cannot proceed"
                )
            else:
                logger.warning(
                    "Cycle detected in dependency graph; continuing in non-strict mode"
                )

        return graph

    def _generate_summary(
        self,
        validated: List[WorkItem],
        rejected: List[WorkItem],
        graph: DependencyGraph,
        execution_order: List[str],
    ) -> Dict[str, Any]:
        """
        Generate summary statistics for the deconstruction result.

        Args:
            validated: Validated WorkItems.
            rejected: Rejected WorkItems.
            graph: Built dependency graph.
            execution_order: Topological execution order.

        Returns:
            Summary dictionary.
        """
        # Complexity distribution
        complexity_counts: Dict[str, int] = defaultdict(int)
        for item in validated:
            complexity_counts[item.complexity.value] += 1

        # Calculate critical path length (longest path in the DAG)
        critical_path_length = self._compute_critical_path_length(graph)

        roots = graph.get_roots()
        leaves = graph.get_leaves()

        total_criteria = sum(len(item.acceptance_criteria) for item in validated)

        summary: Dict[str, Any] = {
            "total_drafted": len(validated) + len(rejected),
            "validated": len(validated),
            "rejected": len(rejected),
            "complexity_distribution": dict(complexity_counts),
            "critical_path_length": critical_path_length,
            "max_depth": critical_path_length,
            "num_roots": len(roots),
            "num_leaves": len(leaves),
            "total_acceptance_criteria": total_criteria,
        }

        return summary

    def _compute_critical_path_length(self, graph: DependencyGraph) -> int:
        """
        Compute the longest path (critical path) in the DAG.

        Uses dynamic programming on the topological order.

        Args:
            graph: Dependency graph (must be acyclic).

        Returns:
            Length of the longest path (number of nodes).
        """
        if not graph.nodes:
            return 0

        try:
            topo_order = graph.topological_sort()
        except CycleDetectedError:
            return 0

        # dist[node] = longest path ending at node (in # of nodes)
        dist: Dict[str, int] = {node: 1 for node in topo_order}

        for node in topo_order:
            # Find all nodes that depend on this node
            dependents = graph.get_dependents(node)
            for dep in dependents:
                if dist[node] + 1 > dist[dep]:
                    dist[dep] = dist[node] + 1

        return max(dist.values()) if dist else 0


# ─── Module-level convenience function ───


def deconstruct_plan(
    plan: Dict[str, Any], config: Optional[Dict[str, Any]] = None
) -> DeconstructionResult:
    """
    Deconstruct a high-level plan into atomic WorkItems.

    Convenience function that creates a PlanDeconstructor and runs the
    full draft->validate pipeline.

    Example plan structure::

        {
            "title": "Build a web app",
            "description": "Full-stack web application",
            "tasks": [
                {
                    "title": "Set up database",
                    "description": "Create PostgreSQL schema",
                    "complexity": "medium",
                    "acceptance_criteria": [
                        "Schema migration runs without errors",
                        "All tables created with correct constraints"
                    ]
                },
                {
                    "title": "Build API layer",
                    "description": "REST API endpoints",
                    "complexity": "high",
                    "depends_on": ["Set up database"],
                    "acceptance_criteria": [
                        "All endpoints return correct status codes",
                        "Authentication middleware works"
                    ]
                }
            ]
        }

    Or with phases::

        {
            "phases": [
                {
                    "name": "Foundation",
                    "tasks": [...]
                },
                {
                    "name": "Implementation",
                    "depends_on_phase": "Foundation",
                    "tasks": [...]
                }
            ]
        }

    Args:
        plan: High-level plan dictionary.
        config: Optional configuration dictionary.

    Returns:
        DeconstructionResult with validated items and dependency graph.

    Raises:
        InvalidPlanError: If the plan is malformed.
        CycleDetectedError: If the dependency graph contains a cycle.
    """
    deconstructor = PlanDeconstructor(config=config)
    return deconstructor.deconstruct(plan)
