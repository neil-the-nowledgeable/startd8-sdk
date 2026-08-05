"""Team composite scores — mean_tier_quality_v1 (FR-DT-5 / FR-DT-16).

Own module — do not overload scorecard ``_provider`` or portal reviewer ``_team_metrics``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence

from .entrant_roster import EntrantRoster, labs_with_complete_tiers

TEAM_METRIC_ID = "mean_tier_quality_v1"
_TIERS = ("flagship", "mid", "fast")


@dataclass(frozen=True)
class TeamRow:
    lab: str
    quality: float
    cost_usd: float
    members: Dict[str, str]  # tier → model id chosen for that tier
    metric_id: str = TEAM_METRIC_ID


def eligible_labs(
    roster: EntrantRoster,
    models_present: Iterable[str],
    *,
    team_lane: Optional[Sequence[str]] = None,
) -> List[str]:
    """Labs that are Team-eligible.

    Always require the FR-DT-4 conjunct (flagship+mid+fast present). When ``team_lane`` is
    provided (tournament mode / FR-DT-16), also require ``lab ∈ team_lane``. When ``team_lane``
    is None (legacy / no RoundRoster), presence-only conjunct applies (degrade path).
    """
    complete = labs_with_complete_tiers(roster, models_present)
    if team_lane is None:
        return complete
    lane = set(team_lane)
    return [lab for lab in complete if lab in lane]


def _quality_key(by_model: Dict[str, Dict], mid: str) -> float:
    """Sort key: prefer higher quality_median; missing → -inf (never wins a tie)."""
    q = by_model[mid].get("quality_median")
    return q if isinstance(q, (int, float)) else float("-inf")


def _member_cost_usd(stats: Dict) -> float:
    """Prefer mean cost; fall back to total; treat both missing as 0.0."""
    c = stats.get("cost_mean_usd")
    if c is None:
        c = stats.get("cost_total_usd") or 0.0
    return float(c)


def _best_per_tier(
    roster: EntrantRoster,
    lab: str,
    by_model: Dict[str, Dict],
    models_present: Iterable[str],
) -> Optional[Dict[str, str]]:
    """Pick the model with best quality_median per tier; None if any tier missing."""
    present = set(models_present)
    chosen: Dict[str, str] = {}
    for tier in _TIERS:
        candidates = [
            m for m, meta in roster.items()
            if meta.lab == lab and meta.tier == tier and m in present and m in by_model
        ]
        if not candidates:
            return None
        chosen[tier] = max(candidates, key=lambda mid: _quality_key(by_model, mid))
    return chosen


def team_rows(
    agg: Dict,
    roster: EntrantRoster,
    *,
    team_lane: Optional[Sequence[str]] = None,
    models_present: Optional[Iterable[str]] = None,
) -> List[TeamRow]:
    """Build Team medal rows (best→worst by quality, then cost).

    Args:
        agg: ``aggregate_cells`` result (needs ``by_model``).
        roster: Entrant roster for lab/tier tags.
        team_lane: When set, only labs in this sequence may medal (FR-DT-16).
        models_present: Override presence set; default = ``by_model`` keys.

    Returns:
        Sorted TeamRow list (quality desc, cost asc, lab asc).
    """
    by_model = agg.get("by_model") or {}
    present = list(models_present) if models_present is not None else list(by_model.keys())
    labs = eligible_labs(roster, present, team_lane=team_lane)
    rows: List[TeamRow] = []
    for lab in labs:
        members = _best_per_tier(roster, lab, by_model, present)
        if not members:
            continue
        qualities: List[float] = []
        costs: List[float] = []
        for tier in _TIERS:
            mid = members[tier]
            s = by_model[mid]
            q = s.get("quality_median")
            if not isinstance(q, (int, float)):
                qualities = []
                break
            qualities.append(float(q))
            costs.append(_member_cost_usd(s))
        if len(qualities) != 3:
            continue
        rows.append(TeamRow(
            lab=lab,
            quality=sum(qualities) / 3.0,
            cost_usd=sum(costs),
            members=members,
        ))
    rows.sort(key=lambda r: (-r.quality, r.cost_usd, r.lab))
    return rows
