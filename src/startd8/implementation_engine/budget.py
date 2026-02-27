"""
Budget constants and truncation utilities for the implementation engine.

Co-locates all budget/size constants and provides deterministic truncation.
"""

from typing import Any, List


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
    "truncate_with_marker",
    "truncate_arch_context",
]


# Spec prompt section budgets
PLAN_CONTEXT_MAX_CHARS: int = 16_384
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

# Supplementary context budgets for optional prompt sections.
# T1 drafter agents get a smaller budget; T2 reviewer agents get more.
SUPPLEMENTARY_BUDGET_CHARS: int = 4_000   # ~1000 tokens — draft prompt (T1)
ENRICHMENT_BUDGET_CHARS: int = 8_000      # ~2000 tokens — review prompt (T2)


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
