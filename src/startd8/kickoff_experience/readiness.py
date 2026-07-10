"""M2 — Readiness surface + performance budgets.

Wraps the concierge ``build_assess`` (which itself wraps the wireframe machinery — FR-C10, never
recomputes provisioning state) into a typed :class:`ReadinessView` that hangs off the canonical
state. Read-only, ``$0``.

Adds the R5-S3 performance-budget hooks: a live kickoff surface must not silently freeze on a large
input package. We time the readiness build and flag ``over_budget`` (with a "large project / still
checking" fallback signal) when a threshold is exceeded — advisory telemetry, never a hard failure.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

# R5-S3 performance budgets (milliseconds). Advisory: exceeding a budget sets a flag + a
# user-facing "large project" fallback signal; it never raises.
BUDGET_INITIAL_MS = 2000      # first full extraction + readiness for a typical package
BUDGET_REFRESH_MS = 750       # post-capture incremental refresh
BUDGET_RENDER_MS = 250        # serialize the canonical state for a surface


@dataclass(frozen=True)
class PerfSample:
    """One timed phase against its budget (R5-S3)."""

    phase: str
    elapsed_ms: float
    budget_ms: float

    @property
    def over_budget(self) -> bool:
        return self.elapsed_ms > self.budget_ms

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "budget_ms": self.budget_ms,
            "over_budget": self.over_budget,
        }


class _Timer:
    """Context-managed wall-clock timer (``time.perf_counter`` — real code, not a workflow script)."""

    def __init__(self) -> None:
        self.elapsed_ms = 0.0

    def __enter__(self) -> "_Timer":
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc: object) -> None:
        self.elapsed_ms = (time.perf_counter() - self._t0) * 1000.0


@dataclass(frozen=True)
class ReadinessView:
    """Typed readiness state — the M2 layer of the canonical view-model (FR-7).

    A projection of ``build_assess`` into the few fields the surfaces actually render: a readiness
    score, status counts, the blocking-gap list, and per-domain input provenance. Plus the R5-S3
    perf sample so a surface can show a "large project / still checking" state.
    """

    readiness: Optional[object]                   # raw per-stage map {stage: status} (or None)
    cascade_status: str                           # "ok" | "inputs_error" | "absent"
    status_counts: Mapping[str, int]
    blockers: Tuple[Mapping[str, Any], ...]
    input_domains: Mapping[str, Mapping[str, Any]]  # domain -> {status, provenance_default?}
    perf: Optional[PerfSample] = None
    error: Optional[str] = None

    @property
    def over_budget(self) -> bool:
        return bool(self.perf and self.perf.over_budget)

    @property
    def score(self) -> Optional[float]:
        """A 0..1 readiness score derived from the raw cascade readiness.

        ``build_assess`` reports ``readiness`` as a per-stage status map
        (``{"scaffold": "ready", "backend": "blocked(...)"}``); the fraction of ``ready`` stages is
        the surfaceable meter value. A plain number is passed through; anything else → None.
        """
        r = self.readiness
        if isinstance(r, bool):  # guard: bool is an int subclass
            return 1.0 if r else 0.0
        if isinstance(r, (int, float)):
            return float(r)
        if isinstance(r, dict) and r:
            ready = sum(1 for v in r.values() if str(v).strip().lower() == "ready")
            return ready / len(r)
        return None

    @classmethod
    def from_assess(
        cls,
        assess: Mapping[str, Any],
        *,
        perf: Optional[PerfSample] = None,
    ) -> "ReadinessView":
        cascade = dict(assess.get("cascade") or {})
        status = cascade.get("status", "absent")
        kickoff_inputs = dict(assess.get("kickoff_inputs") or {})
        return cls(
            readiness=cascade.get("readiness"),
            cascade_status=status,
            status_counts=dict(cascade.get("status_counts") or {}),
            blockers=tuple(cascade.get("blockers") or ()),
            input_domains=dict(kickoff_inputs.get("domains") or {}),
            perf=perf,
            error=cascade.get("error") if status == "inputs_error" else None,
        )

    def to_dict(self) -> dict:
        d: Dict[str, Any] = {
            "readiness": self.readiness,
            "score": self.score,
            "cascade_status": self.cascade_status,
            "status_counts": dict(sorted(self.status_counts.items())),
            "blockers": [dict(b) for b in self.blockers],
            "input_domains": {k: dict(v) for k, v in sorted(self.input_domains.items())},
            "over_budget": self.over_budget,
        }
        if self.perf is not None:
            d["perf"] = self.perf.to_dict()
        if self.error is not None:
            d["error"] = self.error
        return d


def build_readiness(
    project_root: str | Path,
    *,
    budget_ms: float = BUDGET_INITIAL_MS,
    assess: Optional[Mapping[str, Any]] = None,
) -> ReadinessView:
    """Assess readiness for *project_root* (read-only, ``$0``), timed against a perf budget.

    Degrades gracefully: a missing/partial kickoff package surfaces as ``cascade_status`` rather
    than raising, so a brand-new project still renders a (low) readiness view.

    *assess* (CRP R1-S1/R1-F2): a caller that has already fetched ``build_assess(project_root)`` may
    thread it in so the tree is **not scanned twice** in one state build. When provided, the internal
    fetch is skipped (the perf sample then reflects ~0ms — the scan happened at the caller).
    """
    # Imported here so a missing concierge/wireframe dep degrades at call time, not import time.
    from ..concierge import build_assess

    with _Timer() as timer:
        assessed = build_assess(project_root) if assess is None else assess
    perf = PerfSample(phase="readiness", elapsed_ms=timer.elapsed_ms, budget_ms=budget_ms)
    return ReadinessView.from_assess(assessed, perf=perf)
