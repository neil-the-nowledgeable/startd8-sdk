"""
Budget constants and truncation utilities for the implementation engine.

Co-locates all budget/size constants and provides deterministic truncation.

Total prompt budget follows the micro_prime pattern: a hard token cap with
priority-ordered section removal when the prompt exceeds budget.
"""

from typing import Any, Dict, List, Optional


__all__ = [
    "PLAN_CONTEXT_MAX_CHARS",
    "ARCH_CONTEXT_MAX_CHARS",
    "SPEC_CONTEXT_BUDGET_CHARS",
    "EXISTING_FILES_BUDGET_BYTES",
    "TRUNCATION_MARKER",
    "SEARCH_REPLACE_LINE_THRESHOLD",
    "DRAFT_SIZE_REGRESSION_THRESHOLD",
    "DRAFT_SIZE_REGRESSION_MIN_LINES",
    "SUPPLEMENTARY_BUDGET_CHARS",
    "ENRICHMENT_BUDGET_CHARS",
    "TOTAL_SPEC_BUDGET_TOKENS",
    "TOTAL_DRAFT_BUDGET_TOKENS",
    "CHARS_PER_TOKEN",
    "EXEMPLAR_BUDGET_CHARS",
    "truncate_with_marker",
    "truncate_arch_context",
    "estimate_tokens",
    "enforce_prompt_budget",
    "budget_tokens_for_tier",
]


# Spec prompt section budgets
PLAN_CONTEXT_MAX_CHARS: int = 6_000
ARCH_CONTEXT_MAX_CHARS: int = 4_096
SPEC_CONTEXT_BUDGET_CHARS: int = 12_000

# Existing file content budget for draft prompts
EXISTING_FILES_BUDGET_BYTES: int = 40 * 1024  # 40 KB

# Truncation marker appended when text is cut
TRUNCATION_MARKER: str = "... [truncated; full plan in artifacts]"

# Line threshold for search/replace vs whole-file edit mode
SEARCH_REPLACE_LINE_THRESHOLD: int = 50

# Size regression detection for edit-mode drafts:
# Draft with < THRESHOLD of existing file lines is flagged as catastrophically truncated.
# Only applies when existing files exceed MIN_LINES (skip for very small files).
DRAFT_SIZE_REGRESSION_THRESHOLD: float = 0.20  # 20% of existing
DRAFT_SIZE_REGRESSION_MIN_LINES: int = 50

# CR-H3: Size explosion detection — upper bound.
# Draft with > EXPLOSION_THRESHOLD × existing lines is flagged as hallucinated/duplicated.
# Only applies when existing files exceed MIN_LINES (skip for very small files).
DRAFT_SIZE_EXPLOSION_THRESHOLD: float = 3.0  # 300% of existing

# Supplementary context budgets for optional prompt sections.
# T1 drafter agents get a smaller budget; T2 reviewer agents get more.
SUPPLEMENTARY_BUDGET_CHARS: int = 4_000   # ~1000 tokens — draft prompt (T1)
ENRICHMENT_BUDGET_CHARS: int = 8_000      # ~2000 tokens — review prompt (T2)

# Total prompt budget (modeled after micro_prime's 1024-token input budget).
# These are hard caps; sections are dropped by priority when exceeded.
TOTAL_SPEC_BUDGET_TOKENS: int = 4_096     # Spec prompt (architect agent)
TOTAL_DRAFT_BUDGET_TOKENS: int = 8_192    # Draft prompt (includes existing files)
CHARS_PER_TOKEN: int = 4                  # Rough estimate matching micro_prime

# Exemplar injection budget (REQ-PEP-101/102)
EXEMPLAR_BUDGET_CHARS: int = 3_200        # ~800 tokens for exemplar section

# CR-H2: Tier-aware budget multipliers.  COMPLEX tasks with large existing
# files need more prompt headroom for context injection; TRIVIAL tasks need
# less.  Callers use ``budget_tokens_for_tier()`` to get the adjusted budget.
# AC-R4-R2: MODERATE aligned to COMPLEX (1.25 → 1.75) since the default tier
# collapsed from MODERATE → COMPLEX (AC-R3-R7).  Tasks formerly classified as
# MODERATE now receive COMPLEX budgets to avoid under-budgeted prompts.
_TIER_BUDGET_MULTIPLIERS: Dict[str, float] = {
    "TRIVIAL": 0.75,
    "SIMPLE": 1.0,
    "MODERATE": 1.75,
    "COMPLEX": 1.75,
}


def budget_tokens_for_tier(
    base_budget: int,
    tier: Optional[str] = None,
) -> int:
    """Return tier-adjusted token budget.

    Args:
        base_budget: Base token budget (e.g. TOTAL_DRAFT_BUDGET_TOKENS).
        tier: Complexity tier string (TRIVIAL/SIMPLE/MODERATE/COMPLEX).
            When None or unrecognized, returns base_budget unchanged.

    Returns:
        Adjusted token budget (always >= base_budget * 0.5 to prevent
        starvation).
    """
    if not tier:
        return base_budget
    multiplier = _TIER_BUDGET_MULTIPLIERS.get(tier.upper(), 1.0)
    return max(int(base_budget * multiplier), base_budget // 2)


def truncate_with_marker(text: str, max_chars: int,
                         marker: str = TRUNCATION_MARKER) -> str:
    """Truncate text to max_chars, appending marker if truncated.

    Args:
        text: The text to truncate.
        max_chars: Maximum length of the result (including marker).
        marker: Suffix to append when truncation occurs.

    Returns:
        Original text if within limit; otherwise truncated text + marker.
        If max_chars <= 0, returns empty string.
        If max_chars <= len(marker), returns marker truncated to max_chars.
    """
    if max_chars <= 0:
        return ""
    if not text or len(text) <= max_chars:
        return text
    if max_chars <= len(marker):
        return marker[:max_chars]
    return text[: max_chars - len(marker)] + marker


def truncate_arch_context(arch_ctx: Any, max_chars: int) -> str:
    """Truncate or summarize architectural context.

    When dict: keep objectives (first 3), constraints (first 5), drop verbose nested.
    When str: truncate with marker.

    Args:
        arch_ctx: Architectural context as dict, str, or other (stringified).
        max_chars: Maximum length of the result.

    Returns:
        Summarized or truncated string; empty if arch_ctx is falsy.
    """
    if not arch_ctx:
        return ""
    if isinstance(arch_ctx, str):
        return truncate_with_marker(arch_ctx, max_chars, TRUNCATION_MARKER)
    if isinstance(arch_ctx, dict):
        summary_parts: List[str] = []
        obj = arch_ctx.get("objectives") or arch_ctx.get("project_objectives")
        if isinstance(obj, list):
            summary_parts.append(
                "### Objectives\n" + "\n".join(f"- {str(o)}" for o in obj[:3])
            )
        elif isinstance(obj, str):
            summary_parts.append(f"### Objectives\n{obj[:500]}")
        constraints = arch_ctx.get("constraints")
        if isinstance(constraints, list):
            summary_parts.append(
                "### Constraints\n"
                + "\n".join(f"- {str(c)}" for c in constraints[:5])
            )
        result = "\n\n".join(summary_parts)
        if len(result) > max_chars:
            return truncate_with_marker(result, max_chars, TRUNCATION_MARKER)
        return result
    return truncate_with_marker(str(arch_ctx), max_chars, TRUNCATION_MARKER)


def estimate_tokens(text: str) -> int:
    """Estimate token count using chars/4 heuristic (matches micro_prime)."""
    return len(text) // CHARS_PER_TOKEN


def enforce_prompt_budget(
    sections: List[tuple],
    budget_tokens: int,
    logger: Optional[Any] = None,
) -> str:
    """Assemble prompt sections within a token budget.

    Follows the micro_prime pattern: priority-ordered section removal.
    Each section is a ``(priority, label, text)`` tuple where lower
    priority numbers are kept first.

    Priority levels:
        P0 — Never dropped (task description, spec, target)
        P1 — Dropped last (critical parameters, forward contracts)
        P2 — Dropped second (arch context, plan context, supplementary)
        P3 — Dropped first (examples, verbose instructions, call graphs)

    Args:
        sections: List of ``(priority, label, text)`` tuples.
        budget_tokens: Maximum token budget.
        logger: Optional logger for truncation warnings.

    Returns:
        Assembled prompt string within budget.
    """
    # Sort by priority (stable — preserves order within same priority)
    ordered = sorted(sections, key=lambda s: s[0])

    # Try all sections first
    full = "\n\n".join(text for _, _, text in ordered if text)
    if estimate_tokens(full) <= budget_tokens:
        return full

    # Progressive removal: drop highest priority number first
    max_priority = max(p for p, _, _ in ordered)
    result_sections = list(ordered)

    for drop_priority in range(max_priority, 0, -1):
        result_sections = [s for s in result_sections if s[0] < drop_priority]
        candidate = "\n\n".join(text for _, _, text in result_sections if text)
        if logger:
            dropped = [lbl for p, lbl, _ in ordered if p >= drop_priority]
            logger.info(
                "Prompt budget: dropping P%d sections (%s), %d→%d tokens",
                drop_priority, ", ".join(dropped),
                estimate_tokens(full), estimate_tokens(candidate),
            )
        if estimate_tokens(candidate) <= budget_tokens:
            return candidate

    # Emergency: P0 only, hard-truncate
    p0_text = "\n\n".join(text for p, _, text in ordered if p == 0 and text)
    budget_chars = budget_tokens * CHARS_PER_TOKEN
    if len(p0_text) > budget_chars:
        if logger:
            logger.warning(
                "Prompt budget: P0 sections exceed budget (%d > %d tokens), truncating",
                estimate_tokens(p0_text), budget_tokens,
            )
        return truncate_with_marker(p0_text, budget_chars)
    return p0_text
