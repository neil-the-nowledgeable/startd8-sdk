"""Token budget enforcement with simple drop policy.

Replaces the 4-tier compression cascade in prompt_utils.py with a
straightforward 3-step drop:
1. Drop "guidance" fragments (advisory, never critical)
2. Drop droppable "prior_art" fragments (summaries)
3. Drop "enrichment" fragments, replacing with a compact tombstone
   that preserves parameter names (prevents LLM from inventing names)
4. Never drop "identity", "constraints", or "scope"
"""

from __future__ import annotations

import re
from typing import Sequence

from .modules import PromptFragment, _estimate_tokens

DEFAULT_PROMPT_TOKEN_BUDGET = 3000


def _build_enrichment_tombstone(enrichment_fragment: PromptFragment) -> PromptFragment:
    """Create a compact tombstone preserving parameter names from a dropped enrichment fragment.

    Extracts parameter names from ``- `param_name`: ...`` lines and emits a
    short note so the LLM knows ground-truth names existed.
    """
    param_names: list[str] = []
    for match in re.finditer(r"^- `([^`]+)`:", enrichment_fragment.text, re.MULTILINE):
        param_names.append(match.group(1))

    if not param_names:
        # No extractable parameter names — nothing useful for a tombstone
        return PromptFragment(
            category="constraints",
            text="",
            token_estimate=0,
            droppable=False,
        )

    names_csv = ", ".join(f"`{n}`" for n in param_names)
    text = (
        "**NOTE:** Parameter naming conventions and semantic sources were "
        "available but omitted for budget. Use standard naming conventions "
        f"for: {names_csv}."
    )
    return PromptFragment(
        category="constraints",  # never dropped — survives all rounds
        text=text,
        token_estimate=_estimate_tokens(text),
        droppable=False,
    )


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
    total = sum(f.token_estimate for f in kept)
    if total <= budget:
        return kept

    # Round 3: drop enrichment, replacing with a compact tombstone that
    # preserves parameter names so the LLM doesn't invent alternatives.
    enrichment_frags = [f for f in kept if f.category == "enrichment"]
    if enrichment_frags:
        kept = [f for f in kept if f.category != "enrichment"]
        for ef in enrichment_frags:
            tombstone = _build_enrichment_tombstone(ef)
            if tombstone.text:
                kept.append(tombstone)

    # Accept remaining total -- never drop identity/constraints/scope
    return kept
