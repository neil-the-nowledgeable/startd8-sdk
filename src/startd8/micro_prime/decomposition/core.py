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
