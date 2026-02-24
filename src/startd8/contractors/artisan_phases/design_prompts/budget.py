"""Token budget enforcement with simple drop policy.

Replaces the 4-tier compression cascade in prompt_utils.py with a
straightforward 2-step drop:
1. Drop "guidance" fragments (advisory, never critical)
2. Drop droppable "prior_art" fragments (summaries)
3. Never drop "identity", "constraints", or "scope"
"""

from __future__ import annotations

from typing import Sequence

from .modules import PromptFragment

DEFAULT_PROMPT_TOKEN_BUDGET = 3000


def enforce_budget(
    fragments: Sequence[PromptFragment],
    budget: int = DEFAULT_PROMPT_TOKEN_BUDGET,
) -> list[PromptFragment]:
    """Drop fragments to fit within token budget.

    Args:
        fragments: Rendered prompt fragments from modules.
        budget: Soft token budget (default 3000 tokens ~12KB).

    Returns:
        List of fragments to include in the prompt.
    """
    total = sum(f.token_estimate for f in fragments)
    if total <= budget:
        return list(fragments)

    # Round 1: drop guidance
    kept = [f for f in fragments if f.category != "guidance"]
    total = sum(f.token_estimate for f in kept)
    if total <= budget:
        return kept

    # Round 2: drop droppable prior_art (summaries, not dependency designs)
    kept = [f for f in kept if not (f.category == "prior_art" and f.droppable)]

    # Accept remaining total -- never drop identity/constraints/scope
    return kept
