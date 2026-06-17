"""Local Ollama contestant lane (FR-LO-1..11).

Lean sibling of ``jetson_lane``: drives a localhost Ollama agent **in-process**, sends the shared
neutral system prompt + recorded sampling, and records a ``LocalCellRecord`` with honest provenance.

**No firewall verdict** — these are clean *general* code models with no LoRA adapters, so there is
nothing to firewall (Ollama returns ``system_fingerprint="fp_ollama"``, never a ``served_adapter=``
echo, so the Jetson applied-adapter check would wrongly invalidate every clean cell). What still
applies, per the spec: the FR-J6 neutral-prompt fairness rule (sent here) and the honest
pretraining-memorization caveat (clean of OUR vectors, NOT of pretraining — recorded via
``contestant_kind``; the FR-47 probe is the only partial mitigation).

Cost lane is ``"local"`` and is **never ranked against cloud models on cost** (FR-LO-7 — the Jetson
OQ-J3 decision applied verbatim). Localhost needs no opt-in gate (it is the SDK's nulled-key case).
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Share ONLY the neutral prompt + sampling defaults (the spec's "share the constant" guidance) —
# deliberately NOT the firewall verdict machinery.
from .jetson_lane import NEUTRAL_SYSTEM_PROMPT, DEFAULT_SAMPLING
from ..logging_config import get_logger

logger = get_logger(__name__)

COST_LANE = "local"
# Clean of OUR contamination vectors (no corpus fine-tune, no corpus prompt) but NOT of pretraining
# exposure — these are famous public models (FR-LO-8/11; Jetson FR-J8 residual / NR-J7 analogue).
CONTESTANT_KIND = "local-pretraining-caveat"


@dataclass
class LocalCellRecord:
    model: str
    text: Optional[str]
    cost_lane: str = COST_LANE
    contestant_kind: str = CONTESTANT_KIND
    scored: bool = True                          # general lane; no firewall verdict to invalidate on
    sampling: Optional[Dict[str, Any]] = None
    system_prompt_sent: Optional[str] = None     # FR-J6 fairness evidence (the prompt actually sent)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "cost_lane": self.cost_lane,
            "contestant_kind": self.contestant_kind,
            "scored": self.scored,
            "sampling": self.sampling,
            "system_prompt_sent": self.system_prompt_sent,
            "text": self.text,
        }


async def run_local_cell(
    agent: Any,
    *,
    model: str,
    prompt: str,
    sampling: Optional[Dict[str, Any]] = None,
    expected_neutral: str = NEUTRAL_SYSTEM_PROMPT,
) -> LocalCellRecord:
    """Run one local-lane cell: send the neutral prompt + recorded sampling, record honest provenance.

    No firewall verdict (FR-LO-8) — every clean local cell is scored. The ``system_prompt_sent`` is
    captured from the agent so a reader can verify the FR-J6 neutral-prompt fairness rule held.
    """
    sampling = sampling or dict(DEFAULT_SAMPLING)
    result = await agent.agenerate(
        prompt,
        system_prompt=expected_neutral,
        temperature=sampling.get("temperature"),
    )
    return LocalCellRecord(
        model=model,
        text=getattr(result, "text", None),
        sampling=sampling,
        system_prompt_sent=getattr(agent, "last_system_prompt", None),
    )


def scored_cells(cells: List[LocalCellRecord]) -> List[LocalCellRecord]:
    """All local cells are scored (no firewall verdict); helper mirrors the jetson_lane API."""
    return [c for c in cells if c.scored]
