"""Per-turn / per-session dollar cost for consultations (QW-1).

Thin wrapper over the SDK's ``PricingService``: converts a turn's token counts to USD for the
turn's model. Roster keys are ``provider:model`` (e.g. ``anthropic:claude-opus-4-8``) — the provider
prefix is stripped before pricing lookup. Unknown-model pricing degrades to ``None`` rather than
raising, so cost display never breaks a consultation.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from .models import ConsultationSession, TurnRole


@lru_cache(maxsize=1)
def _pricing():
    from ..costs.pricing import PricingService

    return PricingService()


def _model_name(model_id: str) -> str:
    return (model_id or "").split(":")[-1]


def turn_cost_usd(model_id: str, input_tokens, output_tokens) -> Optional[float]:
    """USD for one turn's tokens, or ``None`` if it can't be priced."""
    if input_tokens is None and output_tokens is None:
        return None
    try:
        return _pricing().calculate_total_cost(
            _model_name(model_id), int(input_tokens or 0), int(output_tokens or 0)
        )
    except Exception:  # noqa: BLE001 — cost display must never break the run
        return None


def session_cost(session: ConsultationSession) -> "tuple[dict[str, float], float]":
    """Return ``(per_model_usd, total_usd)`` — prefers persisted ``cost_usd``, else computes."""
    per: dict[str, float] = {}
    for model_id in session.roster:
        acc = 0.0
        for turn in session.turns_by_model.get(model_id, []):
            if turn.role != TurnRole.assistant:
                continue
            if turn.cost_usd is not None:
                acc += turn.cost_usd
            else:
                c = turn_cost_usd(model_id, turn.input_tokens, turn.output_tokens)
                if c:
                    acc += c
        per[model_id] = acc
    return per, sum(per.values())
