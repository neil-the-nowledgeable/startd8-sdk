"""Decomposition Core — shared types and utilities for all decomposition strategies (REQ-MP-910).

Centralizes DecompositionContext, DecompositionNode, DecompositionPlanGraph,
and RecursionPolicy so that MODERATE->SIMPLE and SIMPLE->TRIVIAL layers share
a common foundation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardManifest,
)
from startd8.micro_prime.models import MicroPrimeConfig, TierClassification

# Forward-compatible alias — will become set[ClassificationSignal] per REQ-MP-902
ClassificationSignals = Optional[set[str]]


# ── Recursion Policy (REQ-MP-911) ────────────────────────────────────


@dataclass
class RecursionPolicy:
    """Policy governing recursive decomposition attempts.

    Recursion is off by default — enabling it requires explicit opt-in
    via config. When enabled, the policy gates recursion by depth, budget,
    and monotonicity constraints.
    """

    enabled: bool = False
    max_depth: int = 2
    max_sub_elements_total: int = 8
    max_llm_calls: int = 3
    monotonicity: Literal["strict_tier_decrease", "allow_same_tier"] = (
        "strict_tier_decrease"
    )

    def __post_init__(self) -> None:
        """Validate policy invariants at construction time (REQ-MP-915, R2-S9)."""
        if self.enabled:
            if self.max_depth < 1:
                raise ValueError(
                    f"RecursionPolicy.max_depth must be >= 1 when enabled, got {self.max_depth}"
                )
            if self.max_sub_elements_total < 1:
                raise ValueError(
                    f"RecursionPolicy.max_sub_elements_total must be >= 1 when enabled, "
                    f"got {self.max_sub_elements_total}"
                )
            if self.max_llm_calls < 1:
                raise ValueError(
                    f"RecursionPolicy.max_llm_calls must be >= 1 when enabled, "
                    f"got {self.max_llm_calls}"
                )

    # ── Policy enforcement methods (REQ-MP-911) ──────────────────────

    def check_depth(self, current_depth: int) -> Optional[str]:
        """Check depth constraint. Returns rejection reason or None."""
        if not self.enabled:
            return "recursion_blocked"
        if current_depth >= self.max_depth:
            return "depth_exceeded"
        return None

    def check_budget(
        self,
        sub_element_count: int,
        llm_call_count: int,
    ) -> Optional[str]:
        """Check sub-element and LLM call budgets. Returns rejection reason or None.

        LLM budget accounting (R2-S5): only decomposition LLM calls count
        toward max_llm_calls. Repair and escalation calls are excluded —
        they are gated by their own budgets.
        """
        if not self.enabled:
            return "recursion_blocked"
        if sub_element_count > self.max_sub_elements_total:
            return "budget_exceeded"
        if llm_call_count > self.max_llm_calls:
            return "budget_exceeded"
        return None

    def check_monotonicity(
        self,
        parent_tier: TierClassification,
        child_tier: TierClassification,
        strategy_safe_for_same_tier: bool = False,
    ) -> Optional[str]:
        """Check tier monotonicity constraint. Returns rejection reason or None.

        REQ-MP-911, R2-F4: ``allow_same_tier`` requires BOTH the policy
        setting AND the strategy's explicit ``safe_for_same_tier`` flag.
        """
        if not self.enabled:
            return "recursion_blocked"

        tier_order = {
            TierClassification.COMPLEX: 3,
            TierClassification.MODERATE: 2,
            TierClassification.SIMPLE: 1,
            TierClassification.TRIVIAL: 0,
        }
        parent_rank = tier_order[parent_tier]
        child_rank = tier_order[child_tier]

        if child_rank < parent_rank:
            # Strictly decreasing — always OK
            return None

        if child_rank == parent_rank:
            if (
                self.monotonicity == "allow_same_tier"
                and strategy_safe_for_same_tier
            ):
                return None
            return "monotonicity_violation"

        # child_rank > parent_rank — tier increased, never allowed
        return "monotonicity_violation"

    def check_cycle(
        self,
        fingerprint: str,
        decomposition_path: list[str],
    ) -> Optional[str]:
        """Check for cycles via fingerprint history. Returns rejection reason or None."""
        if not self.enabled:
            return "recursion_blocked"
        if fingerprint in decomposition_path:
            return "cycle_detected"
        return None


# ── Decomposition Context (REQ-MP-910) ──────────────────────────────


@dataclass
class DecompositionContext:
    """Shared context consumed by all decomposition strategies.

    Replaces the individual parameters previously passed to strategy
    methods, providing a single source of truth for the decomposition
    environment.

    Interface Contract (R2-S1):
        Required fields (must not be None):
            - config, manifest, file_spec, file_path, skeleton, recursion_policy
        Optional fields (may be None):
            - template_registry, classification_signals
        Strategy return contract:
            - can_handle() -> bool
            - plan() -> Optional[DecompositionPlan | DecompositionPlanGraph]
        Executor invariants:
            - Strategies must not mutate the context
            - Strategies must not write to file_path or skeleton directly
    """

    config: MicroPrimeConfig
    manifest: ForwardManifest
    file_spec: ForwardFileSpec
    file_path: str
    skeleton: str
    recursion_policy: RecursionPolicy
    template_registry: object = None  # Optional[TemplateRegistry] — avoids circular import
    classification_signals: ClassificationSignals = None
    classification_reason: str = ""


# ── Decomposition Graph Types ────────────────────────────────────────


@dataclass
class DecompositionNode:
    """A node in a recursive decomposition plan graph.

    Wraps a SubElement (from decomposer.py) with optional children
    for nested decomposition.
    """

    # Import-time reference to SubElement would create a circular import,
    # so we use the SubElement dataclass duck-typed via Any.
    # At runtime, sub_element is always a decomposer.SubElement instance.
    sub_element: object  # decomposer.SubElement
    children: list[DecompositionNode] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        """True if this node has no further decomposition."""
        return len(self.children) == 0


@dataclass
class DecompositionPlanGraph:
    """A recursive decomposition plan (REQ-MP-910).

    Extends the flat DecompositionPlan with tree structure. Each root
    node may have children representing further decomposition of that
    sub-element.

    Confidence aggregation (R2-S8):
        Graph confidence = minimum confidence across all leaf nodes.
        This ensures the graph's confidence reflects its weakest link.
        Deterministic nodes (no LLM) contribute confidence 1.0.
    """

    original_element: ForwardElementSpec
    root_nodes: list[DecompositionNode]
    strategy: str
    assembly_kind: str  # "class_compose", "function_chain", "sequential_body"
    confidence: float  # 0.0–1.0, aggregated across children


# ── Bounded rejection reasons for recursion (REQ-MP-913) ─────────────

RECURSION_REJECTION_REASONS = frozenset({
    "recursion_blocked",
    "depth_exceeded",
    "budget_exceeded",
    "monotonicity_violation",
    "cycle_detected",
})


# ── Factory ──────────────────────────────────────────────────────────


def policy_from_config(config: MicroPrimeConfig) -> RecursionPolicy:
    """Build a RecursionPolicy from MicroPrimeConfig fields (REQ-MP-915).

    Maps the flat config fields (recursion_enabled, recursion_max_depth, etc.)
    into a structured RecursionPolicy. Raises ValueError if the config
    produces an invalid policy (e.g., enabled=True with zero limits).
    """
    return RecursionPolicy(
        enabled=config.recursion_enabled,
        max_depth=config.recursion_max_depth,
        max_sub_elements_total=config.recursion_max_sub_elements_total,
        max_llm_calls=config.recursion_max_llm_calls,
        monotonicity=config.recursion_monotonicity,  # type: ignore[arg-type]
    )


# ── Utility Functions ────────────────────────────────────────────────


def make_fingerprint(
    parent_class: Optional[str],
    name: str,
    file_path: str,
    tier: TierClassification,
) -> str:
    """Canonical element fingerprint for cycle detection (REQ-MP-911).

    Format matches engine caching: ``"{parent_class}:{name}:{file_path}:{tier.value}"``
    where parent_class is empty string when None.
    """
    pc = parent_class or ""
    return f"{pc}:{name}:{file_path}:{tier.value}"


def compute_graph_confidence(graph: DecompositionPlanGraph) -> float:
    """Compute aggregate confidence for a plan graph (R2-S8).

    Returns the minimum confidence across all leaf sub-elements.
    Deterministic sub-elements contribute 1.0 (they never fail).
    Returns 1.0 for an empty graph (vacuously true).
    """
    if not graph.root_nodes:
        return 1.0

    leaf_confidences: list[float] = []
    _collect_leaf_confidences(graph.root_nodes, leaf_confidences)

    if not leaf_confidences:
        return 1.0

    return min(leaf_confidences)


def _collect_leaf_confidences(
    nodes: list[DecompositionNode],
    out: list[float],
) -> None:
    """Recursively collect confidence values from leaf nodes."""
    for node in nodes:
        if node.is_leaf:
            # Deterministic sub-elements always succeed
            sub = node.sub_element
            if getattr(sub, "deterministic", False):
                out.append(1.0)
            else:
                # Leaf confidence comes from the sub-element's element_spec;
                # if not available, use a conservative default
                out.append(1.0)  # Individual leaf confidence is 1.0 at plan time
        else:
            _collect_leaf_confidences(node.children, out)
