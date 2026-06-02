"""CKG Phase 2 — render ProjectKnowledge to a spec-context section (REQ-CKG-522/523/525).

Reuses the Phase-1 renderers for the positive sections (`render_upstream_interfaces`,
and the same Prisma header/instruction as `render_prisma_field_sets`) so the
injected text converges with what the Verifier already speaks. Adds two sections
the provider owns: **explicit negatives** (D2) and **omissions** (D3) — the
latter is *stated*, never rendered as an empty authority.

REQ-CKG-525: rendering is size-bounded and logs the injected-token estimate.
"""

from __future__ import annotations

from typing import List

from ...logging_config import get_logger
from ..upstream_interface import render_upstream_interfaces
from .models import ProjectKnowledge

__all__ = ["render", "estimate_tokens", "PRISMA_HEADER", "PRISMA_INSTRUCTION"]

logger = get_logger(__name__)

# Kept byte-identical to upstream_interface.render_prisma_field_sets (drift-guarded
# in tests) so the provider and the Phase-1 renderer speak the same section.
PRISMA_HEADER = "## Prisma data model — mirror these field names/types EXACTLY"
PRISMA_INSTRUCTION = (
    "Zod/TypeScript schemas MUST use these exact field names and compatible types. "
    "Do NOT invent fields (no `bio` when Prisma declares `summary`) or foreign keys "
    "the model does not declare."
)
NEGATIVES_HEADER = "## Do NOT use these invented module paths"
OMISSIONS_HEADER = "## Unavailable — state, do not assume"

_DEFAULT_BUDGET_TOKENS = 800


def estimate_tokens(text: str) -> int:
    """Coarse token estimate (~4 chars/token) — for the REQ-525 budget log."""
    return (len(text) + 3) // 4


def _render_field_sets(pk: ProjectKnowledge) -> str:
    if not pk.field_sets:
        return ""
    rows = [
        f"- `{fs.entity}`: " + ", ".join(f.render() for f in fs.fields)
        for fs in pk.field_sets
    ]
    return "\n".join([PRISMA_HEADER, PRISMA_INSTRUCTION, *rows])


def _render_negatives(pk: ProjectKnowledge) -> str:
    if not pk.negatives:
        return ""
    lines = [NEGATIVES_HEADER]
    for neg in pk.negatives:
        suffix = f" ({neg.note})" if neg.note else ""
        lines.append(f"- `{neg.invented}` is not a module path — use `{neg.correct}`{suffix}")
    return "\n".join(lines)


def _render_omissions(pk: ProjectKnowledge) -> str:
    if not pk.omissions:
        return ""
    return "\n".join([OMISSIONS_HEADER, *(f"- {o}" for o in pk.omissions)])


def render(
    pk: ProjectKnowledge,
    *,
    budget_tokens: int = _DEFAULT_BUDGET_TOKENS,
    log: bool = True,
) -> str:
    """Render the feature-scoped knowledge into a spec-context markdown section.

    Sections, in order: upstream interfaces, Prisma field-set authority,
    explicit negatives, omissions. Empty sections are dropped. Logs the injected
    token estimate vs ``budget_tokens`` (REQ-525); over-budget is a loud warning,
    not a truncation — bounding is the caller's scoping responsibility.
    """
    sections: List[str] = [
        render_upstream_interfaces(list(pk.interfaces)),
        _render_field_sets(pk),
        _render_negatives(pk),
        _render_omissions(pk),
    ]
    out = "\n\n".join(s for s in sections if s)
    if log:
        tokens = estimate_tokens(out)
        if tokens > budget_tokens:
            logger.warning(
                "ProjectKnowledge section over budget: %d tok > %d (entities=%d, negatives=%d)",
                tokens, budget_tokens, len(pk.field_sets), len(pk.negatives),
            )
        else:
            logger.debug(
                "ProjectKnowledge section: %d tok (budget %d)", tokens, budget_tokens,
            )
    return out
