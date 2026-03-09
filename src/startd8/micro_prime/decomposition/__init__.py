"""Decomposition core types and utilities (REQ-MP-910).

Re-exports all public symbols from core.py for convenient import paths:
    from startd8.micro_prime.decomposition import DecompositionContext, RecursionPolicy
"""

from startd8.micro_prime.decomposition.core import (
    DecompositionContext,
    DecompositionNode,
    DecompositionPlanGraph,
    RecursionPolicy,
    compute_graph_confidence,
    make_fingerprint,
)

__all__ = [
    "DecompositionContext",
    "DecompositionNode",
    "DecompositionPlanGraph",
    "RecursionPolicy",
    "compute_graph_confidence",
    "make_fingerprint",
]
