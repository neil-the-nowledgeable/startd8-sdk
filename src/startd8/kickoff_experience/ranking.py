"""Next-action ranking (R2-S3 / FR-11) — a deterministic function of M1/M2 state.

Both surfaces (web M4, TUI M5) call this, so they recommend the **same** next action — the parity
guarantee for the guided experience. The ranking is:

  1. readiness blockers          (a gap the cascade itself reports — highest leverage)
  2. author-actionable gaps      (BLOCKED extraction fields — required, not yet satisfiable as-is)
  3. defaulted values to review  (REVIEW — provenance-critical estimates, FR-NEW-5)
  4. done                        (no blocking gaps remain)

Ties within a tier break by the canonical, byte-stable field-identity order (and readiness blockers
arrive pre-ordered by the wireframe's section order).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .readiness import ReadinessView
from .state import Attention, KickoffState

KIND_BLOCKER = "resolve_blocker"
KIND_FILL = "fill_field"
KIND_REVIEW = "review_default"
KIND_DONE = "done"


@dataclass(frozen=True)
class NextAction:
    kind: str
    title: str
    detail: str
    value_path: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"kind": self.kind, "title": self.title, "detail": self.detail}
        if self.value_path is not None:
            d["value_path"] = self.value_path
        return d


def next_action(
    state: KickoffState,
    readiness: Optional[ReadinessView] = None,
) -> NextAction:
    """The single deterministic recommendation both surfaces render (R2-S3)."""
    # Tier 1 — readiness blockers (cascade-level gaps).
    if readiness is not None and readiness.blockers:
        b = dict(readiness.blockers[0])
        section = str(b.get("section", "unknown"))
        return NextAction(
            kind=KIND_BLOCKER,
            title=f"Resolve readiness blocker: {section}",
            detail=str(b.get("consequence") or b.get("status") or ""),
        )

    # Tier 2 — author-actionable extraction gaps (already identity-sorted).
    blocked = state.blocked_fields()
    if blocked:
        f = blocked[0]
        return NextAction(
            kind=KIND_FILL,
            title=f"Fix {f.value_path}",
            detail=f.reason or f"{f.ambiguity}",
            value_path=f.value_path,
        )

    # Tier 3 — defaulted values that need human review (provenance-critical).
    review = [f for f in state.fields if f.attention == Attention.REVIEW]
    if review:
        f = review[0]
        return NextAction(
            kind=KIND_REVIEW,
            title=f"Review defaulted value: {f.value_path}",
            detail=f"current value: {f.value!r} (defaulted — confirm or change)",
            value_path=f.value_path,
        )

    return NextAction(kind=KIND_DONE, title="Kickoff is build-ready", detail="No blocking gaps remain.")
