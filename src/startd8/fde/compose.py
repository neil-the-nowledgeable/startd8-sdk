# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Optional LLM narrative polish (FR-15(b) / R3-S2).

This is the ONLY FDE module permitted to import agent/provider machinery. It is *off by
default* — the deterministic path (``deterministic_compose.py``) produces the report. When
enabled (``--narrative=enhance`` + budget), the LLM may add a prose bridge that references
already-emitted claim ids; the result is re-checked by the labeling guard so no unlabeled
mechanism claim can be smuggled in (FR-6/FR-21). Keeping this in a separate file is what lets
the import-guard test prove the deterministic core never touches an LLM.
"""

from __future__ import annotations

from ..logging_config import get_logger
from typing import Optional

from .deterministic_compose import assert_all_labeled
from .models import FdeExplanation

logger = get_logger(__name__)


def enhance_explanation_narrative(
    exp: FdeExplanation,
    base_markdown: str,
    *,
    agent_spec: Optional[str] = None,
    max_cost_usd: Optional[float] = None,
) -> str:
    """Append an LLM-authored ``## Narrative`` that only references existing claim ids.

    Returns the base markdown with the narrative appended. On any failure (no key, budget,
    guard violation) it returns the base markdown unchanged — the deterministic report always
    stands on its own. Marks ``exp.llm_used``/``exp.cost_usd`` as a side effect.
    """
    try:
        # lazy: the LLM boundary lives only in this module (import-guard relies on it)
        from ..utils.agent_resolution import resolve_agent_spec
    except Exception:
        logger.debug(
            "FDE narrative: agent resolution unavailable; returning deterministic report"
        )
        return base_markdown

    claim_ids = [c.claim_id for c in exp.all_claims() if c.claim_id]
    prompt = (
        "You are the SDK's Forward Deployed Engineer. Below is a source-labeled mechanism "
        "report. Write a 2-4 sentence plain-language narrative that ONLY references these "
        f"claim ids: {claim_ids}. Do NOT introduce any new factual/mechanism claim; do not "
        "restate a mechanism without referencing its claim id. Output only the narrative.\n\n"
        f"{exp.to_prompt_section()}"
    )
    try:
        agent = resolve_agent_spec(agent_spec or "anthropic:claude-haiku-4-5-20251001")
        result = agent.generate(prompt)
        narrative = getattr(result, "text", str(result)).strip()
        # GenerateResult is (text, time_ms, token_usage) — no cost field. Derive it from the
        # token usage via the SDK's pricing source (same source as cost tracking; no drift).
        usage = getattr(result, "token_usage", None)
        cost = 0.0
        if usage is not None and hasattr(usage, "cost_estimate"):
            try:
                cost = float(usage.cost_estimate())
            except Exception:
                cost = 0.0
        if max_cost_usd is not None and cost > max_cost_usd:
            logger.warning(
                "FDE narrative exceeded budget; dropping (deterministic report stands)"
            )
            return base_markdown
        exp.llm_used = True
        exp.cost_usd += cost
        combined = (
            base_markdown
            + "\n## Narrative (LLM, references labeled claims only)\n\n"
            + narrative
            + "\n"
        )
        assert_all_labeled(combined)  # the narrative must not smuggle unlabeled claims
        return combined
    except Exception:
        logger.warning(
            "FDE narrative generation failed; returning deterministic report",
            exc_info=True,
        )
        return base_markdown
