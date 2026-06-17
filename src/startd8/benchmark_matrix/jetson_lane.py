"""Jetson on-prem lane runner — enforces the contamination firewall at runtime (FR-J5a/J6/J6b/J8).

This is the runtime wiring for the firewall verdict logic in ``firewall.py``. It runs **in-process**
(NOT the benchmark subprocess path): the runner holds the agent, so it reads the FR-J5a/J6 capture
(``last_system_fingerprint`` + ``last_system_prompt``) directly off the agent after each call and
feeds it to ``evaluate_jetson_cell``. Each cell gets its verdict attached to provenance; invalidated
cells are dropped from scoring; results partition into general / in-domain / invalid tracks.

The Jetson is a **separate on-prem lane** (OQ-J3): every record is tagged ``cost_lane="on-prem"`` and
is never ranked against cloud models on cost.

Why in-process: the normal benchmark cell runs the agent inside a ``run_prime_workflow`` subprocess,
so the parent cannot read agent attributes. The on-prem lane sidesteps that seam by driving the
``JetsonProvider`` agent directly — which also makes the firewall fully testable offline with a mock
agent.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .firewall import (
    evaluate_jetson_cell,
    TRACK_GENERAL,
    TRACK_IN_DOMAIN,
    TRACK_INVALID,
)
from ..logging_config import get_logger

logger = get_logger(__name__)

# Canonical neutral system prompt for fair on-prem cells (vendor-uniform; FR-J6). Deliberately free
# of any corpus/house-style tokens — it must pass the firewall's banned-token check itself.
NEUTRAL_SYSTEM_PROMPT = (
    "You are a senior software engineer. Implement the requested service completely and correctly. "
    "Return only runnable source code."
)

# Default inference config recorded for FR-J6b. Deterministic (greedy) so base vs adapter are
# comparable; callers may override but must keep it identical across a compared track.
DEFAULT_SAMPLING: Dict[str, Any] = {"temperature": 0.0, "top_p": 1.0, "seed": 0}
DEFAULT_QUANT = "nf4"


@dataclass
class JetsonCellRecord:
    alias: str
    text: Optional[str]
    track: str
    scored: bool                              # False ⇒ invalidated, dropped from scoring
    firewall: Dict[str, Any]                  # FirewallVerdict.as_provenance()
    cost_lane: str = "on-prem"                # OQ-J3: never ranked against cloud on cost
    server_commit_sha: Optional[str] = None   # FR-J6 artifact: pinned edge-brains fastapi_serve SHA
    sampling: Optional[Dict[str, Any]] = None
    quant: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alias": self.alias,
            "track": self.track,
            "scored": self.scored,
            "cost_lane": self.cost_lane,
            "server_commit_sha": self.server_commit_sha,
            "sampling": self.sampling,
            "quant": self.quant,
            "firewall": self.firewall,
            # text intentionally last; may be large
            "text": self.text,
        }


async def run_jetson_cell(
    agent: Any,
    *,
    requested_alias: str,
    prompt: str,
    sampling: Optional[Dict[str, Any]] = None,
    quant: str = DEFAULT_QUANT,
    expected_neutral: str = NEUTRAL_SYSTEM_PROMPT,
    server_commit_sha: Optional[str] = None,
) -> JetsonCellRecord:
    """Run one on-prem cell and render its firewall verdict.

    Sends the NEUTRAL system prompt (FR-J6) and the configured sampling (FR-J6b), then reads the
    agent's FR-J5a/J6 capture and judges it. An invalidated cell (wrong/absent applied-adapter echo)
    is recorded but ``scored=False`` so it never enters any leaderboard.
    """
    sampling = sampling or dict(DEFAULT_SAMPLING)
    result = await agent.agenerate(
        prompt,
        system_prompt=expected_neutral,
        temperature=sampling.get("temperature"),
    )

    verdict = evaluate_jetson_cell(
        requested_alias=requested_alias,
        system_fingerprint=getattr(agent, "last_system_fingerprint", None),
        sent_prompt=getattr(agent, "last_system_prompt", None),
        expected_neutral=expected_neutral,
        sampling=sampling,
        quant=quant,
    )

    # Drop from scoring if it lands in `invalid` for ANY reason — a wrong/absent applied-adapter echo
    # (verdict.invalidated) OR a clean-labeled cell that failed the prompt/determinism vectors. Both
    # are inadmissible; only `general`/`in-domain` cells are scored.
    scored = verdict.track != TRACK_INVALID
    if not scored:
        logger.warning(
            "Jetson on-prem cell %r INADMISSIBLE (dropped from scoring): %s",
            requested_alias, "; ".join(verdict.reasons) or "firewall failure",
        )

    return JetsonCellRecord(
        alias=requested_alias,
        text=getattr(result, "text", None),
        track=verdict.track,
        scored=scored,
        firewall=verdict.as_provenance(),
        server_commit_sha=server_commit_sha,
        sampling=sampling,
        quant=quant,
    )


def partition_by_track(cells: List[JetsonCellRecord]) -> Dict[str, List[JetsonCellRecord]]:
    """Split cells into general / in-domain / invalid tracks (unknown tracks → invalid)."""
    out: Dict[str, List[JetsonCellRecord]] = {TRACK_GENERAL: [], TRACK_IN_DOMAIN: [], TRACK_INVALID: []}
    for c in cells:
        out.get(c.track, out[TRACK_INVALID]).append(c)
    return out


def scored_cells(cells: List[JetsonCellRecord]) -> List[JetsonCellRecord]:
    """Cells admissible to *some* lane (not invalidated). General vs in-domain still separate."""
    return [c for c in cells if c.scored]
