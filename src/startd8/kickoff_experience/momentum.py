"""Close-the-loop momentum + leverage (roadmap Tier D) — feed the project's own history back into
the recommendation so the cockpit *directs* progress, not just reports it.

Two pure, deterministic functions over data the oracle already has ($0, no LLM):

1. :func:`readiness_trend` — reads the Tier-B activation ledger's readiness observations and returns
   whether readiness is **rising / stalled / falling** (the burndown slope), so a surface can say
   "readiness stalled at 60%" instead of a bare "60%". This is the *momentum* half of the loop.

2. :func:`leverage_groups` — groups the not-yet-ok fields by their field **class** (the value-path
   head) and ranks the classes by how many fields each would clear. The top class is the
   **highest-leverage** next batch: resolving it moves readiness the most. This is the *direction*
   half — it turns "fix this one field" into "fix this class, it clears N".

Neither mutates the deterministic :func:`ranking.next_action` (the web/TUI parity contract stays
byte-stable); they *enrich* the recommendation alongside it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence, Tuple

# Attention classes that are NOT yet "ok" (resolving any of them raises readiness = ok / total).
_ACTIONABLE = ("blocked", "review")

TREND_RISING = "rising"
TREND_STALLED = "stalled"
TREND_FALLING = "falling"
TREND_UNKNOWN = "unknown"


@dataclass(frozen=True)
class ReadinessTrend:
    """The readiness slope from the activation ledger — the momentum half of the loop."""

    trend: str  # TREND_*
    latest: Optional[int]
    previous: Optional[int]
    delta: Optional[int]
    points: int  # number of readiness observations available
    summary: str

    def to_dict(self) -> dict:
        return {
            "trend": self.trend,
            "latest": self.latest,
            "previous": self.previous,
            "delta": self.delta,
            "points": self.points,
            "summary": self.summary,
        }


def readiness_trend(ledger_entries: Sequence[dict]) -> ReadinessTrend:
    """Compute the readiness slope from activation-ledger rows (chronological order).

    Uses the last two readiness-bearing observations; ``delta == 0`` across them reads as *stalled*
    (readiness didn't move even though something changed). Degrades to ``unknown`` with < 2 points."""
    from .activation import readiness_readings

    readings = readiness_readings(ledger_entries)
    points = len(readings)
    if points == 0:
        return ReadinessTrend(TREND_UNKNOWN, None, None, None, 0, "no readiness history yet")
    latest = readings[-1]
    if points == 1:
        return ReadinessTrend(
            TREND_UNKNOWN, latest, None, None, 1, f"readiness {latest}% (first observation)"
        )
    previous = readings[-2]
    delta = latest - previous
    if delta > 0:
        trend = TREND_RISING
        summary = f"readiness rising: {previous}% → {latest}% (+{delta})"
    elif delta < 0:
        trend = TREND_FALLING
        summary = f"readiness falling: {previous}% → {latest}% ({delta})"
    else:
        trend = TREND_STALLED
        summary = f"readiness stalled at {latest}%"
    return ReadinessTrend(trend, latest, previous, delta, points, summary)


@dataclass(frozen=True)
class LeverageGroup:
    """One field class (value-path head) and how many not-ok fields resolving it would clear."""

    subject: str
    count: int
    blocked: int
    review: int
    sample_value_path: str

    def to_dict(self) -> dict:
        return {
            "subject": self.subject,
            "count": self.count,
            "blocked": self.blocked,
            "review": self.review,
            "sample_value_path": self.sample_value_path,
        }


def _value_path_head(value_path: str) -> str:
    """The leading dotted segment of a value path — the user-meaningful field class."""
    vp = str(value_path or "")
    return vp.split(".", 1)[0] if vp else "(unknown)"


def leverage_groups(state: Any) -> Tuple[LeverageGroup, ...]:
    """Rank the not-ok field classes by how many fields each would clear (highest leverage first).

    Ties break by subject name (byte-stable). Empty when ``state`` is None or fully ok."""
    if state is None:
        return ()
    fields = list(getattr(state, "fields", ()) or ())
    agg: dict = {}
    for f in fields:
        attention = str(getattr(f, "attention", "") or "")
        if attention not in _ACTIONABLE:
            continue
        head = _value_path_head(getattr(f, "value_path", ""))
        g = agg.setdefault(head, {"blocked": 0, "review": 0, "sample": getattr(f, "value_path", "")})
        g[attention] = g.get(attention, 0) + 1
    groups = [
        LeverageGroup(
            subject=head,
            count=v["blocked"] + v["review"],
            blocked=v["blocked"],
            review=v["review"],
            sample_value_path=str(v["sample"]),
        )
        for head, v in agg.items()
    ]
    # Highest leverage first; tie-break by subject for byte-stability.
    groups.sort(key=lambda g: (-g.count, g.subject))
    return tuple(groups)


def leverage_nudge(state: Any, trend: Optional[ReadinessTrend] = None) -> Optional[str]:
    """A one-line, motivation-carrying nudge combining the top-leverage class + momentum, or ``None``.

    e.g. "resolve `conventions` — clears 3 fields · readiness stalled at 60%". ``None`` when nothing
    is actionable (fully ok / no state)."""
    groups = leverage_groups(state)
    if not groups:
        return None
    top = groups[0]
    plural = "field" if top.count == 1 else "fields"
    nudge = f"resolve `{top.subject}` — clears {top.count} {plural}"
    if trend is not None and trend.trend in (TREND_STALLED, TREND_FALLING):
        nudge += f" · {trend.summary}"
    return nudge
